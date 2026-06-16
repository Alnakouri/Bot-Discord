"""
Serveur HTTP pour Chatterbox TTS — Voice Cloning de Sheogorath (Philippe Bozo, VF TESO).

Remplace Piper TTS. API compatible avec l'ancien endpoint GET /?text=...
+ nouveau POST /tts avec contrôle d'expressivité.

Architecture:
  - Chatterbox Turbo (350M params) sur GPU
  - Voice cloning zero-shot depuis un sample de ~10s de Philippe Bozo
  - Contrôle d'expressivité (exaggeration) et de rythme (cfg_weight)
  - Tags paralinguistiques natifs: [laugh], [cough], [chuckle]
"""

import io
import os
import torch
import logging
import torchaudio as ta
from pathlib import Path
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("chatterbox-server")

app = FastAPI(title="Chatterbox TTS — Sheogorath Voice Clone")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

VOICE_REF_PATH = os.getenv("VOICE_REF_PATH", "/app/voices/sheogorath_ref.wav")
MODEL_TYPE = os.getenv("MODEL_TYPE", "turbo")  # "turbo" ou "multilingual"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Paramètres optimaux pour Sheogorath (théâtral, expressif, dramatique)
# D'après la doc Chatterbox :
#   - exaggeration haute (~0.7) = plus d'expressivité (folie)
#   - cfg_weight bas (~0.3) = rythme plus lent, dramatique
DEFAULT_EXAGGERATION = float(os.getenv("EXAGGERATION", "0.7"))
DEFAULT_CFG_WEIGHT = float(os.getenv("CFG_WEIGHT", "0.3"))

model = None


# ═══════════════════════════════════════════════════════════════
# CHARGEMENT DU MODÈLE
# ═══════════════════════════════════════════════════════════════

def load_model():
    """Charge le modèle Chatterbox (lazy loading)."""
    global model
    if model is not None:
        return model

    logger.info(f"🔊 Chargement du modèle Chatterbox ({MODEL_TYPE}) sur {DEVICE}...")

    if MODEL_TYPE == "turbo":
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        model = ChatterboxTurboTTS.from_pretrained(device=DEVICE)
    elif MODEL_TYPE == "multilingual":
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        model = ChatterboxMultilingualTTS.from_pretrained(device=DEVICE)
    else:
        from chatterbox.tts import ChatterboxTTS
        model = ChatterboxTTS.from_pretrained(device=DEVICE)

    vram = torch.cuda.memory_allocated() / 1e9 if DEVICE == "cuda" else 0
    logger.info(f"✅ Modèle chargé sur {DEVICE} (VRAM: {vram:.1f} Go)")
    return model


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class TTSRequest(BaseModel):
    text: str
    exaggeration: float = DEFAULT_EXAGGERATION
    cfg_weight: float = DEFAULT_CFG_WEIGHT
    language_id: str = "fr"


@app.on_event("startup")
async def startup():
    """Pré-charger le modèle au démarrage."""
    load_model()
    if Path(VOICE_REF_PATH).exists():
        logger.info(f"🎤 Voix de référence chargée : {VOICE_REF_PATH}")
    else:
        logger.warning(f"⚠️ Voix de référence MANQUANTE : {VOICE_REF_PATH}")
        logger.warning("   → Placez un fichier WAV de ~10s de Philippe Bozo (Sheogorath VF)")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": MODEL_TYPE,
        "device": DEVICE,
        "voice_ref_found": Path(VOICE_REF_PATH).exists(),
        "vram_used_gb": round(torch.cuda.memory_allocated() / 1e9, 2) if DEVICE == "cuda" else 0,
        "actor": "Philippe Bozo (Sheogorath VF TESO)"
    }


@app.get("/")
async def tts_get(text: str = Query(..., description="Texte à synthétiser")):
    """
    Endpoint GET compatible avec l'ancien Piper HTTP.
    Permet un remplacement transparent de Piper → Chatterbox.
    """
    return await generate_audio(text, DEFAULT_EXAGGERATION, DEFAULT_CFG_WEIGHT, "fr")


@app.post("/tts")
async def tts_post(req: TTSRequest):
    """
    Endpoint POST avec contrôle fin de l'expressivité.
    
    Paramètres recommandés pour Sheogorath :
      exaggeration=0.7 (folie, sauts de ton)
      cfg_weight=0.3   (rythme dramatique)
    """
    return await generate_audio(req.text, req.exaggeration, req.cfg_weight, req.language_id)


async def generate_audio(text: str, exaggeration: float, cfg_weight: float, language_id: str):
    """Pipeline de génération audio avec voice cloning."""
    if not text or len(text.strip()) < 2:
        raise HTTPException(400, "Texte trop court")

    if not Path(VOICE_REF_PATH).exists():
        raise HTTPException(
            503,
            "Voix de référence non trouvée. Placez sheogorath_ref.wav dans /app/voices/"
        )

    try:
        m = load_model()

        # Générer avec voice cloning de Philippe Bozo
        if MODEL_TYPE == "turbo":
            # Turbo : pas de contrôle exaggeration/cfg, mais tags [laugh] etc.
            wav = m.generate(
                text,
                audio_prompt_path=VOICE_REF_PATH,
            )
        else:
            # Multilingual / Original : contrôle fin
            wav = m.generate(
                text,
                audio_prompt_path=VOICE_REF_PATH,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                language_id=language_id,
            )

        # Convertir en WAV bytes
        buf = io.BytesIO()
        ta.save(buf, wav, m.sr, format="wav")
        buf.seek(0)

        logger.info(
            f"🔊 Audio généré: {len(text)} chars, "
            f"exag={exaggeration}, cfg={cfg_weight}, lang={language_id}"
        )

        return Response(
            content=buf.read(),
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=sheogorath.wav"}
        )

    except Exception as e:
        logger.error(f"❌ Erreur génération: {e}", exc_info=True)
        raise HTTPException(500, f"Erreur de synthèse: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    logger.info("🎭 Démarrage du serveur Chatterbox TTS — Sheogorath Voice Clone")
    logger.info(f"   Acteur: Philippe Bozo (VF TESO)")
    logger.info(f"   Modèle: {MODEL_TYPE}")
    logger.info(f"   Device: {DEVICE}")
    uvicorn.run(app, host="0.0.0.0", port=5000)
