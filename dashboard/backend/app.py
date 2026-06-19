import os
import hmac
import json
import time
import hashlib
import secrets
from pathlib import Path
from fastapi import FastAPI, WebSocket, Query, HTTPException, Request, Response, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv optionnel : fonctionne aussi si la variable est déjà dans l'env
    def load_dotenv(*_a, **_k):
        return False

# Importer les composants créés
from bot_manager import BotManager
from log_collector import LogCollector
from error_analyzer import ErrorAnalyzer
from api_tracker import APITracker
from conversation_analyzer import ConversationAnalyzer
from report_generator import ReportGenerator
from twitch_config import TwitchConfigManager
from pydantic import BaseModel
from typing import Optional

# Configuration des chemins
BACKEND_DIR = Path(__file__).parent.resolve()
DASHBOARD_DIR = BACKEND_DIR.parent
ROOT_DIR = DASHBOARD_DIR.parent
DATA_DIR = ROOT_DIR / "data"
FRONTEND_DIR = DASHBOARD_DIR / "frontend"

# --- AUTHENTIFICATION ---------------------------------------------------
# Le dashboard pilote les bots (start/stop) et expose logs/clés : il exige
# un mot de passe défini dans dashboard/.env (DASHBOARD_PASSWORD). Sans lui,
# l'API est verrouillée (fail-closed) : on ne sert jamais ces routes ouvertes.
load_dotenv(DASHBOARD_DIR / ".env")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "").strip()

# --- TRUST / SESSIONS PERSISTANTES ---
# Les sessions survivent au redémarrage du dashboard (fichier local), pour ne pas
# avoir à retaper le mot de passe à chaque démarrage. On ne stocke que le HASH des
# jetons (un vol du fichier ne donne pas de cookie utilisable) avec leur expiration.
# Les sessions sont liées à une empreinte du mot de passe : changer
# DASHBOARD_PASSWORD invalide automatiquement toutes les sessions existantes.
TRUST_DAYS = int(os.getenv("DASHBOARD_TRUST_DAYS", "30"))
SESSION_TTL = TRUST_DAYS * 86400
SESSIONS_FILE = DATA_DIR / "dashboard_sessions.json"
# Routes accessibles sans authentification.
_PUBLIC_PATHS = {"/api/login", "/api/health", "/api/me"}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _pw_fingerprint() -> str:
    return hashlib.sha256(("pwv1:" + DASHBOARD_PASSWORD).encode("utf-8")).hexdigest()


def _load_sessions() -> "dict[str, float]":
    """Charge les sessions valides du disque (purge expirées ; reset si mdp changé)."""
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict) or data.get("pw") != _pw_fingerprint():
        return {}  # mot de passe changé ou fichier invalide -> on repart propre
    now = time.time()
    return {h: exp for h, exp in data.get("sessions", {}).items()
            if isinstance(exp, (int, float)) and exp > now}


def _save_sessions() -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = SESSIONS_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"pw": _pw_fingerprint(), "sessions": _SESSIONS}, f)
        os.replace(tmp, SESSIONS_FILE)
    except Exception as e:
        print(f"[DASHBOARD] Sauvegarde des sessions impossible : {e}")


# {hash_jeton: epoch_expiration}. Rechargé au démarrage -> trust persistant.
_SESSIONS: "dict[str, float]" = _load_sessions()

if not DASHBOARD_PASSWORD:
    print("\n" + "=" * 60)
    print("  ⚠️  DASHBOARD_PASSWORD non défini dans dashboard/.env")
    print("  L'API est VERROUILLÉE tant qu'aucun mot de passe n'est posé.")
    print("  -> Copiez dashboard/.env.example en dashboard/.env")
    print("     et renseignez DASHBOARD_PASSWORD.")
    print("=" * 60 + "\n")


def _password_ok(candidate: str) -> bool:
    """Comparaison à temps constant du mot de passe fourni."""
    if not DASHBOARD_PASSWORD:
        return False
    return hmac.compare_digest(candidate, DASHBOARD_PASSWORD)


def _session_valid(token: str | None) -> bool:
    if not token:
        return False
    h = _hash_token(token)
    exp = _SESSIONS.get(h)
    if exp is None:
        return False
    if exp <= time.time():
        _SESSIONS.pop(h, None)
        _save_sessions()
        return False
    return True

BOTS_DB_PATH = DATA_DIR / "bots_database.db"
API_DB_PATH = DATA_DIR / "api_usage.db"

# Initialisation des managers
bot_manager = BotManager(str(ROOT_DIR))
log_collector = LogCollector(str(ROOT_DIR))
error_analyzer = ErrorAnalyzer(str(BOTS_DB_PATH))
api_tracker = APITracker(str(API_DB_PATH))
conversation_analyzer = ConversationAnalyzer(str(BOTS_DB_PATH))
report_generator = ReportGenerator(str(BOTS_DB_PATH))
twitch_config_manager = TwitchConfigManager(DATA_DIR)

app = FastAPI(title="Bot Discord Dashboard", version="1.0.0")

# CORS restreint au front servi en local (le dashboard pilote les bots :
# pas d'origine arbitraire ni de credentials cross-site).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8501",
        "http://localhost:8501",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_auth(request: Request, call_next):
    """Verrouille toute route /api/* (hors login/health) derrière une session.
    Les WebSockets ne passent pas par ce middleware : ils sont contrôlés
    directement dans leur handler."""
    path = request.url.path
    if path.startswith("/api/") and path not in _PUBLIC_PATHS:
        if not _session_valid(request.cookies.get("dash_session")):
            return JSONResponse({"detail": "Authentification requise"}, status_code=401)
    return await call_next(request)


# --- AUTH ROUTES ---
@app.post("/api/login")
async def login(response: Response, password: str = Body(..., embed=True)):
    if not _password_ok(password):
        # Délai léger pour décourager le bruteforce.
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=401, detail="Mot de passe invalide")
    token = secrets.token_urlsafe(32)
    _SESSIONS[_hash_token(token)] = time.time() + SESSION_TTL
    _save_sessions()
    response.set_cookie(
        "dash_session", token,
        httponly=True, samesite="strict", max_age=SESSION_TTL, path="/",
    )
    return {"status": "ok"}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    tok = request.cookies.get("dash_session")
    if tok:
        _SESSIONS.pop(_hash_token(tok), None)
        _save_sessions()
    response.delete_cookie("dash_session", path="/")
    return {"status": "ok"}


@app.get("/api/me")
async def me(request: Request):
    """Permet au frontend de savoir s'il est authentifié."""
    return {"authenticated": _session_valid(request.cookies.get("dash_session"))}

# --- ROUTES STATIQUES ---
# Au cas où frontend n'existe pas encore
os.makedirs(str(FRONTEND_DIR), exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def root():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        # Fallback si index.html n'est pas encore créé
        return {"status": "Dashboard Backend Running", "message": "Index.html not found"}
    return FileResponse(str(index_path))

# --- BOTS MANAGEMENT ---
@app.get("/api/bots")
async def list_bots():
    return bot_manager.get_all_status()

@app.post("/api/bots/{bot_name}/start")
async def start_bot(bot_name: str):
    return bot_manager.start_bot(bot_name)

@app.post("/api/bots/{bot_name}/stop")
async def stop_bot(bot_name: str):
    return bot_manager.stop_bot(bot_name)

@app.post("/api/bots/{bot_name}/restart")
async def restart_bot(bot_name: str):
    return bot_manager.restart_bot(bot_name)

# --- LOGS ---
@app.get("/api/logs")
async def get_logs(
    bot: str = None, level: str = None, search: str = None,
    date_from: str = None, date_to: str = None,
    page: int = 1, per_page: int = 100
):
    return log_collector.get_logs(bot, level, search, date_from, date_to, page, per_page)

@app.websocket("/api/logs/stream")
async def log_stream(websocket: WebSocket, bot: str = None):
    # Le middleware HTTP ne couvre pas les WebSockets : on vérifie ici.
    if not _session_valid(websocket.cookies.get("dash_session")):
        await websocket.close(code=1008)  # 1008 = Policy Violation
        return
    await websocket.accept()
    try:
        # Utiliser le générateur async du log_collector
        async for log_entry in log_collector.watch(bot=bot):
            await websocket.send_json(log_entry)
    except Exception as e:
        print(f"WebSocket Error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass

# --- ERRORS ---
@app.get("/api/errors")
async def get_errors(bot: str = None, severity: str = None, resolved: bool = None):
    return error_analyzer.get_errors(bot, severity, resolved)

@app.post("/api/errors/analyze")
async def analyze_error(error_id: int):
    return error_analyzer.analyze(error_id)

# --- API USAGE ---
@app.get("/api/api-usage")
async def get_api_usage(hours: int = 24):
    return api_tracker.get_usage(hours)

@app.get("/api/api-usage/keys")
async def get_api_keys_status():
    return api_tracker.get_keys_status()

# --- CONVERSATIONS ---
@app.get("/api/conversations")
async def get_conversation_stats(days: int = 7, bot: str = None):
    return conversation_analyzer.get_stats(days, bot)

# --- REPORTS ---
@app.post("/api/reports/generate")
async def generate_report(format: str = "md", scope: str = "all", hours: int = 24):
    return report_generator.generate(format, scope, hours)

# --- TWITCH ENDPOINTS ---
class TwitchGlobalConfigUpdate(BaseModel):
    enabled: bool
    poll_interval_seconds: int

class TwitchSubscriptionAdd(BaseModel):
    twitch_login: str
    discord_channel_id: str
    custom_message: Optional[str] = None

class TwitchEnableAll(BaseModel):
    enabled: bool
    poll_interval_seconds: Optional[int] = None

@app.get("/api/twitch")
async def get_twitch_config():
    return twitch_config_manager.get_all()

@app.put("/api/twitch/all")
async def update_twitch_all(cfg: TwitchEnableAll):
    try:
        twitch_config_manager.set_enabled_all(cfg.enabled, cfg.poll_interval_seconds)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/twitch/all/subscriptions")
async def add_twitch_subscription_all(sub: TwitchSubscriptionAdd):
    try:
        result = twitch_config_manager.add_subscription_all(
            sub.twitch_login, sub.discord_channel_id, sub.custom_message)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/twitch/{bot_id}")
async def update_twitch_bot_config(bot_id: str, cfg: TwitchGlobalConfigUpdate):
    try:
        twitch_config_manager.set_bot(bot_id, cfg.enabled, cfg.poll_interval_seconds)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/twitch/{bot_id}/subscriptions")
async def add_twitch_subscription(bot_id: str, sub: TwitchSubscriptionAdd):
    try:
        new_sub = twitch_config_manager.add_subscription(
            bot_id, sub.twitch_login, sub.discord_channel_id, sub.custom_message
        )
        return {"status": "ok", "subscription": new_sub}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/twitch/{bot_id}/subscriptions/{index}")
async def delete_twitch_subscription(bot_id: str, index: int):
    try:
        twitch_config_manager.remove_subscription(bot_id, index)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Bind localhost uniquement : ce dashboard expose le contrôle des bots
    # (start/stop) SANS authentification ; il ne doit jamais être joignable
    # depuis le LAN. reload désactivé (pas de mode debug en exécution réelle).
    uvicorn.run("app:app", host="127.0.0.1", port=8501, reload=False)
