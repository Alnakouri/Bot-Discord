# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/media_handler.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

"""
media_handler.py — Traitement multimodal centralisé (Vision + Audio).
Utilisé par les 6 bots Discord. Envoie images et audio à Gemini 2.5 Flash.
"""
import logging

import aiohttp
import asyncio
import base64
import json
from google.genai import types
import PIL.Image

try:
    from shared.models import GEMINI_FLASH, GEMINI_FLASH_LITE, GROQ_FAST, MISTRAL_MAIN, OPENROUTER_FREE
except ImportError:  # bot déployé seul, sans shared/
    GEMINI_FLASH      = "gemini-3.5-flash"
    GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"
    GROQ_FAST         = "openai/gpt-oss-120b"
    # mistral-large est hors abonnement (403 tier_not_allowed, 2026-08-30) : ce repli
    # le ressuscitait des qu'un bot tournait sans shared/. Cf. MISTRAL_HORS_TIER.
    MISTRAL_MAIN      = "mistral-small-latest"
    OPENROUTER_FREE   = "nvidia/nemotron-3-super-120b-a12b:free"

logger = logging.getLogger("media_handler")

MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10 MB

async def _download_attachment(attachment) -> tuple[bytes | None, str]:
    """Télécharge un attachment Discord. Retourne (bytes, mime_type)."""
    mime_type = attachment.content_type or "application/octet-stream"
    if attachment.size and attachment.size > MAX_MEDIA_SIZE:
        logger.warning(f"[MEDIA] Rejeté (trop grand): {attachment.size / 1024 / 1024:.1f} MB")
        return None, mime_type
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    return None, mime_type
                data = await resp.read()
                return data, mime_type
    except Exception as e:
        logger.error(f"[MEDIA] Erreur téléchargement: {e}")
        return None, mime_type




import os

OLLAMA_VISION_URL = os.getenv("OLLAMA_VISION_URL", "http://localhost:11445")

# Cache de disponibilité Ollama (évite de spammer le healthcheck)
_ollama_available = None
_ollama_check_time = 0
_OLLAMA_CHECK_INTERVAL = 60  # Revérifier toutes les 60 secondes

async def _check_ollama_available(ollama_url: str) -> bool:
    """Vérifie rapidement si Ollama est up et moondream est chargé."""
    global _ollama_available, _ollama_check_time
    import time
    now = time.time()
    
    # Utiliser le cache si récent
    if _ollama_available is not None and (now - _ollama_check_time) < _OLLAMA_CHECK_INTERVAL:
        return _ollama_available
    
    try:
        timeout = aiohttp.ClientTimeout(total=3)  # 3s max pour le check
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{ollama_url}/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    _ollama_available = any("moondream" in m for m in models)
                    if not _ollama_available:
                        logger.debug("[OLLAMA] Service up mais moondream non installé")
                    else:
                        logger.info(f"✅ [OLLAMA] Service disponible (URL: {ollama_url})")
                else:
                    _ollama_available = False
                    logger.warning(f"⚠️ [OLLAMA] Service a renvoyé HTTP {resp.status}")
    except Exception as e:
        _ollama_available = False
        logger.debug(f"[OLLAMA] Service injoignable: {e}")
    
    _ollama_check_time = now
    return _ollama_available


async def process_image_ollama(attachment, personality_prompt: str,
                               user_message: str = "",
                               ollama_url: str = None) -> str | None:
    """
    Analyse une image via Moondream sur Ollama.
    Vérifie d'abord si le service est disponible (fast-fail en 3s).
    """
    if ollama_url is None:
        ollama_url = OLLAMA_VISION_URL
    
    # Fast-fail : ne pas attendre 30s si Ollama est down
    if not await _check_ollama_available(ollama_url):
        logger.debug("[OLLAMA VISION] Service indisponible, skip rapide")
        return None
    
    image_data, _ = await _download_attachment(attachment)
    if not image_data:
        return None

    img_base64 = base64.b64encode(image_data).decode('utf-8')
    text_part = user_message.strip() or "Décris cette image."
    
    prompt = f"SYSTEM: {personality_prompt}\n\n[VISION] {text_part} Réponds de manière concise en restant dans ta personnalité."

    try:
        timeout = aiohttp.ClientTimeout(total=45)  # Moondream peut être lent
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{ollama_url}/api/generate", json={
                "model": "moondream:latest",
                "prompt": prompt,
                "images": [img_base64],
                "stream": False
            }) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get("response", "").strip()
                    if result:
                        logger.info(f"✅ [OLLAMA VISION] Image analysée par Moondream ({len(result)} chars)")
                        return result
                    logger.warning("[OLLAMA VISION] Réponse vide de Moondream")
                    return None
                else:
                    body = await resp.text()
                    logger.error(f"❌ [OLLAMA VISION] Erreur API: {resp.status} — {body[:200]}")
                    # Invalider le cache si erreur
                    global _ollama_available
                    _ollama_available = None
                    return None
    except asyncio.TimeoutError:
        logger.warning("⏱️ [OLLAMA VISION] Timeout (45s) — Moondream trop lent")
        return None
    except Exception as e:
        logger.error(f"❌ [OLLAMA VISION] Erreur: {e}")
        return None

