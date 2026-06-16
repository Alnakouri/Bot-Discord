import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio

# Importer les composants créés
from bot_manager import BotManager
from log_collector import LogCollector
from error_analyzer import ErrorAnalyzer
from api_tracker import APITracker
from conversation_analyzer import ConversationAnalyzer
from report_generator import ReportGenerator

# Configuration des chemins
BACKEND_DIR = Path(__file__).parent.resolve()
DASHBOARD_DIR = BACKEND_DIR.parent
ROOT_DIR = DASHBOARD_DIR.parent
DATA_DIR = ROOT_DIR / "data"
FRONTEND_DIR = DASHBOARD_DIR / "frontend"

BOTS_DB_PATH = DATA_DIR / "bots_database.db"
API_DB_PATH = DATA_DIR / "api_usage.db"

# Initialisation des managers
bot_manager = BotManager(str(ROOT_DIR))
log_collector = LogCollector(str(ROOT_DIR))
error_analyzer = ErrorAnalyzer(str(BOTS_DB_PATH))
api_tracker = APITracker(str(API_DB_PATH))
conversation_analyzer = ConversationAnalyzer(str(BOTS_DB_PATH))
report_generator = ReportGenerator(str(BOTS_DB_PATH))

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

@app.get("/api/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Bind localhost uniquement : ce dashboard expose le contrôle des bots
    # (start/stop) SANS authentification ; il ne doit jamais être joignable
    # depuis le LAN. reload désactivé (pas de mode debug en exécution réelle).
    uvicorn.run("app:app", host="127.0.0.1", port=8501, reload=False)
