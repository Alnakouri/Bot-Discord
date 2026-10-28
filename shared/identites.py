# -*- coding: utf-8 -*-
"""Les identites REELLES restent hors du depot public.

POURQUOI
--------
Le depot est public. Les vrais pseudos (la streameuse preferee de Sugar) et l'ID
Discord du proprietaire n'y sont donc jamais ecrits : le code ne connait que des
valeurs fictives, et la machine qui fait tourner les bots fournit les vraies dans
`data/identites_locales.json`.

Ce fichier n'est ni versionne (`data/*.json` dans .gitignore) ni copie dans l'image
Docker (.dockerignore) : il arrive dans les conteneurs par le volume `./data:/app/data`.

FORMAT (toutes les cles sont facultatives)
------------------------------------------
    {
      "streameuse": "pseudo_twitch_de_la_streameuse",
      "proprietaire_discord_id": "ID numerique (Discord : clic droit > Copier l'identifiant)"
    }

Sans fichier, ou avec un fichier illisible, les valeurs fictives prennent le relais :
les tests et un clone du depot public tournent tels quels.
"""
import json
import os
from pathlib import Path

STREAMEUSE_FICTIVE = "ma_streameuse"

_FICHIER = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))) / "identites_locales.json"


def _charger() -> dict:
    try:
        with open(_FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


_DONNEES = _charger()

STREAMEUSE: str = str(_DONNEES.get("streameuse") or STREAMEUSE_FICTIVE)

# 0 = personne : sans fichier, seul un administrateur du serveur passe.
try:
    PROPRIETAIRE_DISCORD_ID: int = int(_DONNEES.get("proprietaire_discord_id") or 0)
except (TypeError, ValueError):
    PROPRIETAIRE_DISCORD_ID = 0
