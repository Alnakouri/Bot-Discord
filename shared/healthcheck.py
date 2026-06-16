import time
import aiohttp
import os
import logging

logger = logging.getLogger("healthcheck")
startup_time = time.time()

OLLAMA_VISION_URL = os.getenv("OLLAMA_VISION_URL", "http://localhost:11445")

async def _check_ollama_status() -> dict:
    """Vérifie le status du service Ollama et du modèle Moondream."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{OLLAMA_VISION_URL}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    has_moondream = any("moondream" in m for m in models)
                    return {
                        "status": "healthy" if has_moondream else "no_model",
                        "service": "up",
                        "moondream_loaded": has_moondream,
                        "models": models
                    }
                return {"status": "error", "service": "up", "http_code": resp.status}
    except Exception as e:
        return {"status": "down", "service": "unreachable", "error": str(e)[:100]}


async def run_healthcheck(bot, key_manager) -> dict:
    """Returns the health status of the bot APIs."""
    uptime = time.time() - startup_time
    
    # Check Ollama en parallèle
    ollama_status = await _check_ollama_status()
    
    status = {
        "bot_name": bot.user.name if bot.user else "Starting",
        "uptime_seconds": int(uptime),
        "guilds": len(bot.guilds),
        "apis": {
            "gemini": key_manager.get_status("gemini") if hasattr(key_manager, "get_status") else "N/A",
            "ollama_vision": ollama_status,
        }
    }
    return status
