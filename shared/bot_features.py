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


# ═══════════════════════════════════════════════════════════════════════════
# MODE TEST — « les bots ne publient que sur le serveur prive »
#
# Reglages globaux stockes sous la cle "_global" du meme fichier, donc pilotes
# par le dashboard et relus avec le meme TTL de 5 s : basculer le mode ne demande
# AUCUN redemarrage.
# ═══════════════════════════════════════════════════════════════════════════
CLE_GLOBALE = "_global"


def get_global(cle: str, defaut=None):
    """Lit un reglage global (hors bot particulier)."""
    section = _load().get(CLE_GLOBALE, {})
    return section.get(cle, defaut) if isinstance(section, dict) else defaut


def is_test_mode(bot_id: str) -> bool:
    """Le bot est-il en mode test ?

    Interrupteur GLOBAL ou case du bot : l'un des deux suffit. Le global permet de
    tout basculer d'un geste, la case par bot de n'isoler qu'un bot.
    """
    if bool(get_global("test_mode", False)):
        return True
    return is_feature_enabled(bot_id, "test_mode", default=False)


def test_guild_id():
    """Identifiant du serveur prive, ou None s'il n'est pas encore choisi."""
    brut = get_global("test_guild_id", None)
    if brut in (None, "", 0):
        return None
    try:
        return int(brut)
    except (TypeError, ValueError):
        return None


def peut_publier(bot_id: str, guild_id) -> bool:
    """Ce bot a-t-il le droit de publier a cet endroit ?

    Hors mode test, tout est permis : le comportement est strictement inchange.

    En mode test, la regle est FERMEE PAR DEFAUT — on n'autorise que ce qui est
    explicitement le serveur prive. En particulier, mode test actif SANS serveur
    choisi = silence total, pas « publie partout ». Pour une fonction dont le seul
    but est d'empecher une publication publique, se tromper dans le sens du silence
    est le seul sens acceptable.

    Les messages prives (guild_id None) sont coupes aussi : en mode test, seul le
    serveur prive parle.
    """
    if not is_test_mode(bot_id):
        return True
    if guild_id is None:
        return False
    cible = test_guild_id()
    if cible is None:
        return False
    try:
        return int(guild_id) == cible
    except (TypeError, ValueError):
        return False
