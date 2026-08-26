import os
import sys
import hmac
import json
import time
import hashlib
import secrets
import subprocess
from pathlib import Path

# Contexte de lancement, fige ICI : `sys.argv[0]` est un chemin RELATIF au repertoire
# de depart (start_dashboard.bat fait « cd dashboard » puis « python backend/app.py »).
# Le relire au moment d'un redemarrage donnerait un chemin faux si le repertoire
# courant avait change entre-temps.
_LANCEMENT_CWD = os.getcwd()
_LANCEMENT_ARGV = list(sys.argv)

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
from bot_manager import BotManager, BOT_REGISTRY
from log_collector import LogCollector
from error_analyzer import ErrorAnalyzer
from api_tracker import APITracker
from conversation_analyzer import ConversationAnalyzer
from report_generator import ReportGenerator
from audit_analyzer import AuditAnalyzer
from twitch_config import TwitchConfigManager
from features_config import FeaturesConfigManager, DEFAULTS
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
DASHBOARD_DB_PATH = DATA_DIR / "dashboard_audit.db"

# Initialisation des managers
bot_manager = BotManager(str(ROOT_DIR))
log_collector = LogCollector(str(ROOT_DIR))
error_analyzer = ErrorAnalyzer(str(BOTS_DB_PATH))
api_tracker = APITracker(str(API_DB_PATH))
conversation_analyzer = ConversationAnalyzer(str(BOTS_DB_PATH))
report_generator = ReportGenerator(
    str(BOTS_DB_PATH),
    bot_manager=bot_manager,
    error_analyzer=error_analyzer,
    api_tracker=api_tracker,
    conversation_analyzer=conversation_analyzer
)
audit_analyzer = AuditAnalyzer(str(DASHBOARD_DB_PATH))
twitch_config_manager = TwitchConfigManager(DATA_DIR)
features_config_manager = FeaturesConfigManager(DATA_DIR)

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
    res = bot_manager.start_bot(bot_name)
    if res.get("success"):
        audit_analyzer.log("start_bot", bot_name, "Démarrage du bot via le dashboard")
    return res

@app.post("/api/bots/{bot_name}/stop")
async def stop_bot(bot_name: str):
    res = bot_manager.stop_bot(bot_name)
    if res.get("success"):
        audit_analyzer.log("stop_bot", bot_name, "Arrêt du bot via le dashboard")
    return res

@app.post("/api/bots/{bot_name}/restart")
async def restart_bot(bot_name: str):
    res = bot_manager.restart_bot(bot_name)
    if res.get("success"):
        audit_analyzer.log("restart_bot", bot_name, "Redémarrage du bot via le dashboard")
    return res

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
        except Exception:
            pass

# --- ERRORS ---
@app.get("/api/errors/count")
async def get_errors_count(hours: int = 24):
    return error_analyzer.count_recent(hours)

@app.post("/api/errors/{error_id}/resolve")
async def resolve_error(error_id: int):
    res = error_analyzer.resolve(error_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Échec de la résolution"))
    # Essayer de trouver le nom du bot pour le log d'audit
    bot_name = None
    try:
        import sqlite3
        from pathlib import Path
        uri = Path(error_analyzer.db_path).absolute().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=20)
        cursor = conn.cursor()
        cursor.execute("SELECT bot_name FROM error_events WHERE id = ?", (error_id,))
        row = cursor.fetchone()
        if row:
            bot_name = row[0]
        conn.close()
    except Exception:
        pass
    audit_analyzer.log("resolve_error", bot_name, f"Erreur #{error_id} résolue")
    return res

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
@app.get("/api/conversations/activity")
async def get_conversation_activity(hours: int = 24):
    return conversation_analyzer.get_activity(hours)

@app.get("/api/conversations")
async def get_conversation_stats(days: int = 7, bot: str = None):
    return conversation_analyzer.get_stats(days, bot)

# --- REPORTS ---
@app.post("/api/reports/generate")
async def generate_report(format: str = "md", scope: str = "all", hours: int = 24):
    res = report_generator.generate(format, scope, hours)
    audit_analyzer.log("generate_report", details=f"Génération rapport scope={scope}, heures={hours}")
    return res

@app.get("/api/reports/download/{filename}")
async def download_report(filename: str):
    import os
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(report_generator.reports_dir, safe_filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    return FileResponse(filepath, media_type="text/markdown", filename=safe_filename)

@app.get("/api/audit-logs")
async def get_audit_logs(limit: int = 100):
    return audit_analyzer.get_logs(limit)

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

class TwitchChatConfigUpdate(BaseModel):
    events: bool
    interjections: bool
    greetings: bool
    viewer_memory: bool
    game_qa: bool
    eventsub: bool = False

class TwitchListenConfigUpdate(BaseModel):
    enabled: bool
    mode: str
    device: str
    chunk_ms: int
    min_interval: int

@app.get("/api/twitch")
async def get_twitch_config():
    return twitch_config_manager.get_all()

@app.put("/api/twitch/all")
async def update_twitch_all(cfg: TwitchEnableAll):
    try:
        twitch_config_manager.set_enabled_all(cfg.enabled, cfg.poll_interval_seconds)
        audit_analyzer.log("update_twitch_all", details=f"Changement état surveillance globale -> {cfg.enabled}")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/twitch/all/subscriptions")
async def add_twitch_subscription_all(sub: TwitchSubscriptionAdd):
    try:
        result = twitch_config_manager.add_subscription_all(
            sub.twitch_login, sub.discord_channel_id, sub.custom_message)
        audit_analyzer.log("add_twitch_subscription_all", details=f"Abonnement global Twitch à {sub.twitch_login} (salon #{sub.discord_channel_id})")
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/twitch/{bot_id}")
async def update_twitch_bot_config(bot_id: str, cfg: TwitchGlobalConfigUpdate):
    try:
        twitch_config_manager.set_bot(bot_id, cfg.enabled, cfg.poll_interval_seconds)
        audit_analyzer.log("update_twitch_bot", bot_id, f"Mise à jour config Twitch -> enabled={cfg.enabled}")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/twitch/{bot_id}/subscriptions")
async def add_twitch_subscription(bot_id: str, sub: TwitchSubscriptionAdd):
    try:
        new_sub = twitch_config_manager.add_subscription(
            bot_id, sub.twitch_login, sub.discord_channel_id, sub.custom_message
        )
        audit_analyzer.log("add_twitch_subscription", bot_id, f"Abonnement Twitch à {sub.twitch_login}")
        return {"status": "ok", "subscription": new_sub}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/twitch/{bot_id}/subscriptions/{index}")
async def delete_twitch_subscription(bot_id: str, index: int):
    try:
        twitch_config_manager.remove_subscription(bot_id, index)
        audit_analyzer.log("delete_twitch_subscription", bot_id, f"Suppression abonnement Twitch index #{index}")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/twitch/chat/{bot_id}")
async def get_twitch_chat_config(bot_id: str):
    try:
        cfg = twitch_config_manager.get_bot(bot_id)
        return cfg.get("chat", {})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/twitch/chat/{bot_id}")
async def update_twitch_chat_config(bot_id: str, cfg: TwitchChatConfigUpdate):
    try:
        twitch_config_manager.update_chat_config(
            bot_id, cfg.events, cfg.interjections, cfg.greetings, cfg.viewer_memory, cfg.game_qa, cfg.eventsub
        )
        audit_analyzer.log("update_twitch_chat", bot_id, "Mise à jour config chat Twitch")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/twitch/links/{bot_id}")
async def get_twitch_links(bot_id: str):
    try:
        links = twitch_config_manager.get_link_commands(bot_id)
        return {"link_commands": links}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/twitch/links/{bot_id}")
async def update_twitch_links(bot_id: str, payload: dict = Body(...)):
    try:
        cleaned = twitch_config_manager.update_link_commands(bot_id, payload.get("link_commands", []))
        audit_analyzer.log("update_twitch_links", bot_id, "Mise à jour des commandes de liens Twitch")
        return {"status": "ok", "link_commands": cleaned}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/twitch/cohost/{bot_id}")
async def get_twitch_cohost(bot_id: str):
    try:
        cfg = twitch_config_manager.get_bot(bot_id)
        return {"cohost_channels": cfg.get("cohost_channels", [])}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/twitch/cohost/{bot_id}")
async def update_twitch_cohost(bot_id: str, payload: dict = Body(...)):
    try:
        cleaned = twitch_config_manager.update_cohost_channels(bot_id, payload.get("cohost_channels", []))
        audit_analyzer.log("update_twitch_cohost", bot_id, "Mise à jour des chaînes co-host Twitch")
        return {"status": "ok", "cohost_channels": cleaned}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/features/{bot_id}")
def get_features(bot_id: str):
    try:
        return features_config_manager.get_bot(bot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/features/all")
def set_feature_all(body: dict):
    try:
        feature = body.get("feature")
        value = body.get("value")
        if feature not in DEFAULTS:
            raise HTTPException(status_code=400, detail=f"Feature '{feature}' inconnue.")
        if not isinstance(value, bool):
            raise HTTPException(status_code=400, detail="'value' doit être un booléen.")
        
        for bot_id in BOT_REGISTRY:
            features_config_manager.set_feature(bot_id, feature, value)
        audit_analyzer.log("update_features_all", details=f"Changement global de feature {feature} -> {value}")
        return {"status": "ok"}
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/features/{bot_id}")
def set_feature(bot_id: str, body: dict):
    try:
        features_config_manager.set_feature(bot_id, body["feature"], body["value"])
        audit_analyzer.log("update_features_bot", bot_id, f"Mise à jour feature {body['feature']} -> {body['value']}")
        return {"status": "ok"}
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

# ═══════════════════════════════════════════════════════════════════════════
# MODE TEST — « les bots ne publient que sur le serveur privé »
#
# Chemin distinct de /api/features/{bot_id} : « global » y serait capturé comme
# un identifiant de bot.
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/testmode")
def get_test_mode():
    """État complet : réglages globaux, état par bot, et serveurs disponibles."""
    try:
        cfg = features_config_manager.get_all()
        glob = features_config_manager.get_global()
        serveurs = features_config_manager.get_guilds()
        return {
            "global": glob,
            "bots": {b: bool(cfg.get(b, {}).get("test_mode", False)) for b in BOT_REGISTRY},
            "guilds": serveurs["guilds"],
            "bots_vus": serveurs["bots_vus"],
            # Mode test actif sans serveur choisi = silence total : le dashboard doit
            # le dire, sinon on croit à des bots en panne.
            "avertissement": (
                "Mode test actif mais aucun serveur privé sélectionné : les bots concernés "
                "ne publieront NULLE PART."
                if glob.get("test_mode") and not glob.get("test_guild_id") else None
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/testmode")
def set_test_mode(body: dict):
    """Bascule l'interrupteur global ou choisit le serveur privé."""
    try:
        modifie = {}
        for cle in ("test_mode", "test_guild_id"):
            if cle in body:
                modifie[cle] = features_config_manager.set_global(cle, body[cle])[cle]
        if not modifie:
            raise HTTPException(status_code=400, detail="Rien à modifier ('test_mode' ou 'test_guild_id').")
        audit_analyzer.log("update_test_mode", details=f"Mode test global -> {modifie}")
        return {"status": "ok", **features_config_manager.get_global()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/testmode/guilds")
def get_test_mode_guilds():
    """Serveurs remontés par les bots, pour alimenter le menu déroulant."""
    return features_config_manager.get_guilds()


@app.get("/api/twitch/rewards/{bot_id}")
async def get_twitch_rewards(bot_id: str):
    try:
        cfg = twitch_config_manager.get_bot(bot_id)
        return cfg.get("reward_map", {})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/twitch/rewards/{bot_id}")
async def update_twitch_rewards(bot_id: str, reward_map: dict = Body(...)):
    try:
        twitch_config_manager.update_reward_map(bot_id, reward_map)
        audit_analyzer.log("update_twitch_rewards", bot_id, "Mise à jour des récompenses Twitch")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/twitch/listen/{bot_id}")
async def get_twitch_listen_config(bot_id: str):
    try:
        cfg = twitch_config_manager.get_bot(bot_id)
        return cfg.get("listen", {})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/twitch/listen/{bot_id}")
async def update_twitch_listen_config(bot_id: str, cfg: TwitchListenConfigUpdate):
    try:
        twitch_config_manager.update_listen_config(
            bot_id, cfg.enabled, cfg.mode, cfg.device, cfg.chunk_ms, cfg.min_interval
        )
        audit_analyzer.log("update_twitch_listen", bot_id, f"Mise à jour config écoute micro -> enabled={cfg.enabled}")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/twitch/channels/{bot_id}")
async def get_twitch_channels(bot_id: str):
    try:
        cfg = twitch_config_manager.get_bot(bot_id)
        return {"chat_channels": cfg.get("chat_channels", [])}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/twitch/channels/{bot_id}")
async def update_twitch_channels(bot_id: str, payload: dict = Body(...)):
    try:
        cleaned = twitch_config_manager.update_chat_channels(bot_id, payload.get("chat_channels", []))
        audit_analyzer.log("update_twitch_channels", bot_id, "Mise à jour des salons Discord de chat Twitch")
        return {"status": "ok", "chat_channels": cleaned}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/twitch/leaderboard/{bot_id}")
async def get_twitch_leaderboard(bot_id: str):
    try:
        return twitch_config_manager.get_leaderboard(bot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ═══════════════════════════════════════════════════════════════════════════
# REDEMARRAGE DU DASHBOARD LUI-MEME
#
# Les bots redemarrent via `docker compose restart`. Le dashboard, lui, est un
# processus Python local : personne d'autre ne peut le relancer. Il delegue donc a
# un petit programme detache (relauncher.py) qui attend sa mort ET la liberation du
# port avant de le rallumer — relancer trop tot donnerait un « address already in
# use » et laisserait l'utilisateur sans dashboard du tout.
# ═══════════════════════════════════════════════════════════════════════════

DASHBOARD_PORT = 8501


@app.post("/api/dashboard/restart")
async def restart_dashboard():
    """Redémarre le dashboard. Répond AVANT de mourir, sinon le navigateur
    afficherait une erreur réseau au lieu d'une confirmation."""
    import threading

    relanceur = Path(__file__).parent / "relauncher.py"
    if not relanceur.exists():
        raise HTTPException(status_code=500, detail="relauncher.py introuvable.")

    commande = [sys.executable, str(relanceur), str(os.getpid()), str(DASHBOARD_PORT),
                _LANCEMENT_CWD, sys.executable] + _LANCEMENT_ARGV

    try:
        options = {}
        if sys.platform == "win32":
            # Détaché : il doit survivre à la mort de son parent, c'est tout son rôle.
            options["creationflags"] = (subprocess.DETACHED_PROCESS
                                        | subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            options["start_new_session"] = True
        subprocess.Popen(commande, **options)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Relanceur non lancé : {e}")

    audit_analyzer.log("restart_dashboard", details="Redémarrage du dashboard via l'interface")

    def _quitter():
        # Laisse la réponse partir, puis coupe net : un arrêt « propre » d'uvicorn
        # peut traîner sur les connexions ouvertes, et le relanceur attend de toute
        # façon que le port soit libre.
        time.sleep(1.0)
        os._exit(0)

    threading.Thread(target=_quitter, daemon=True).start()
    return {"status": "ok", "message": "Redémarrage en cours...", "port": DASHBOARD_PORT}


@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Bind localhost uniquement : ce dashboard expose le contrôle des bots
    # (start/stop) SANS authentification ; il ne doit jamais être joignable
    # depuis le LAN. reload désactivé (pas de mode debug en exécution réelle).
    uvicorn.run("app:app", host="127.0.0.1", port=8501, reload=False)
