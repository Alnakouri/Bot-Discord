# -*- coding: utf-8 -*-
"""
run_stream_listener.py — Lanceur du hub d'écoute continu (STT) Twitch.
Ce script s'exécute sur la machine possédant le microphone (PC de stream).
Il lit les configurations dans data/twitch_config.json pour un bot pilote (johnny par défaut)
et instancie StreamListenerHub si l'écoute est activée.

Usage:
    python run_stream_listener.py
"""

import os
import json
import asyncio
import logging
from pathlib import Path
import sys

# Console Windows en cp1252 : forcer l'UTF-8 (les logs contiennent des emojis) avant basicConfig.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_stream_listener")

# Add parent directory to sys.path if necessary
_root_dir = os.path.dirname(os.path.abspath(__file__))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

try:
    from shared.stream_listener import StreamListenerHub
except ImportError as e:
    logger.critical(f"❌ Impossible d'importer StreamListenerHub depuis shared.stream_listener: {e}")
    sys.exit(1)

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent / "data"))

def load_listen_config(pilot_bot: str = "johnny") -> dict:
    config_path = os.path.join(DATA_DIR, "twitch_config.json")
    if not os.path.exists(config_path):
        logger.warning(f"⚠️ Fichier config introuvable à {config_path}. Utilisation des valeurs par défaut.")
        return {"enabled": False, "mode": "C", "device": "cpu", "min_interval": 45.0}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        bot_data = data.get(pilot_bot, {})
        listen_cfg = bot_data.get("listen", {})
        
        try:
            min_interval = float(listen_cfg.get("min_interval", 45.0))
        except (ValueError, TypeError):
            min_interval = 45.0
            
        return {
            "enabled": bool(listen_cfg.get("enabled", False)),
            "mode": str(listen_cfg.get("mode", "C")),
            "device": str(listen_cfg.get("device", "cpu")),
            "model": str(listen_cfg.get("model", "large-v3-turbo")),  # small/medium/large-v3-turbo...
            "min_interval": min_interval,
            "input_device": listen_cfg.get("input_device", None),  # index/nom micro ; None = défaut Windows
            "prompt": listen_cfg.get("prompt", None),  # biais vocabulaire Whisper (noms des bots)
            "rms_threshold": float(listen_cfg.get("rms_threshold", 0.02)),  # seuil anti-bruit
            "max_segment_sec": float(listen_cfg.get("max_segment_sec", 12.0))  # plafond durée énoncé
        }
    except Exception as e:
        logger.error(f"❌ Erreur lors de la lecture de la configuration : {e}")
        return {"enabled": False, "mode": "C", "device": "cpu", "model": "large-v3-turbo", "min_interval": 45.0, "input_device": None, "prompt": None, "rms_threshold": 0.02, "max_segment_sec": 12.0}

async def main():
    logger.info("🎙️ Démarrage du service d'écoute en arrière-plan...")
    
    # Lecture initiale de la config
    cfg = load_listen_config()
    
    if not cfg["enabled"]:
        logger.info("💤 L'écoute live (listen) est désactivée dans la configuration. Le hub ne démarre pas.")
        logger.info("Pour l'activer, modifiez les paramètres dans le dashboard et relancez ce script.")
        return

    hub = StreamListenerHub(port=8765, mode=cfg["mode"], model_size=cfg["model"], device=cfg["device"],
                            voice_min_interval=cfg["min_interval"], input_device=cfg.get("input_device"),
                            initial_prompt=cfg.get("prompt"), rms_threshold=cfg.get("rms_threshold", 0.02),
                            max_segment_sec=cfg.get("max_segment_sec", 12.0))
    
    try:
        await hub.start()
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt demandé par l'utilisateur.")
    finally:
        hub.stop()
        logger.info("🔌 Hub d'écoute arrêté.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
