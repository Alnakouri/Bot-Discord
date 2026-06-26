# -*- coding: utf-8 -*-
import os, json, time
from pathlib import Path

# Mirror de _load_dashboard_twitch_config (shared/twitch_chat.py:239).
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
_CACHE = {"data": None, "ts": 0.0}
_TTL = 5.0   # relit le fichier au plus toutes les 5 s → toggle quasi-live sans redémarrage

def _load() -> dict:
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _TTL:
        return _CACHE["data"]
    path = os.path.join(DATA_DIR, "bot_features.json")
    data = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = {}   # illisible → on n'empêche jamais la feature (default géré par l'appelant)
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data

def is_feature_enabled(bot_id: str, feature: str, default: bool = True) -> bool:
    """True si la feature est active pour ce bot. Fichier/clé absents → `default`."""
    bot = _load().get(bot_id, {})
    val = bot.get(feature, default)
    return bool(val) if isinstance(val, bool) else default
