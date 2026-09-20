# -*- coding: utf-8 -*-
"""Serveur HTTP pour Laya — le trieur « System One » partage par les six bots.

Laya (convaiinnovations/laya, Apache 2.0) ne genere pas de texte : il rend une reponse
TYPEE avec des probabilites, en un seul passage avant. Les bots s'en servent pour les
decisions qu'ils prennent AVANT d'appeler un LLM, et qui sont aujourd'hui des listes de
mots-cles : ce qu'on demande a Alfred quand on l'interpelle, le ton d'un message adresse
a Sugar, la pertinence d'une intervention spontanee.

POURQUOI UN SERVICE, ET PAS UNE COPIE PAR BOT
---------------------------------------------
Mesure du 2026-09-20 : le modele charge occupe **1 730 Mo de RSS par processus**. Six
conteneurs = 10,4 Go, quand le VM Docker en offre 7,75. Partage, c'est **1,73 Go une
seule fois**, et les poids ne se chargent qu'une fois (37 s au demarrage, pas six fois).
Des DEUX bots equipes, le service est deja moins cher que l'embarque.

⚠️ CE SERVICE EST CONSULTATIF, ET LE RESTE. Il est sans etat, en lecture seule, et
aucune decision de bot n'en depend : le client a une borne dure et retombe sur la regle
en place s'il ne repond pas. S'il tombe, on perd une amelioration — jamais un bot.
C'est le contrat qu'avaient deja `bots-ollama-vision` et `chatterbox-tts` dans ce
compose : « degrade proprement ».

⚠️ Il ne DEFINIT aucune question. Les questions arrivent du bot, parce que c'est le bot
qui sait ce qu'il decide : une decision de persona qui vivrait ici serait une regle de
persona sortie de son fichier, et le depot a deja paye pour ca.

⚠️ CPU uniquement. Le GPU est pris par `chatterbox-server`, et Laya n'en a pas besoin :
105 ms de mediane sur CPU dans la mesure du 20/09.
"""
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("laya-server")

# Le checkpoint multilingue : le francais est notre seule langue de salon.
# ⚠️ Le checkpoint anglais (`laya`, sans sous-dossier) est ANGLAIS SEULEMENT.
VARIANTE = os.getenv("LAYA_VARIANTE", "multilingual")

app = FastAPI(title="laya-server", docs_url=None, redoc_url=None)

_agent = None
_charge_ms = None
_modele = None


class Demande(BaseModel):
    """Le texte a juger, et les questions typees que le BOT definit."""
    state: str
    questions: dict


@app.on_event("startup")
def _charger():
    global _agent, _charge_ms, _modele
    import laya

    modele, revision = laya.DEFAULT_MODELS[VARIANTE]
    _modele = f"{modele}/{revision}" if revision else modele
    logger.info(f"chargement de {_modele} sur CPU...")
    t0 = time.perf_counter()
    _agent = laya.agent.load(modele, subfolder=revision, device="cpu")
    _charge_ms = round((time.perf_counter() - t0) * 1000)
    logger.info(f"pret en {_charge_ms} ms")


@app.get("/health")
def health():
    """Le client s'en sert au demarrage : inutile de borner un service pas encore pret."""
    return {"ok": _agent is not None, "modele": _modele, "charge_ms": _charge_ms}


@app.post("/decide")
def decide(d: Demande):
    """Rend la sortie de Laya telle quelle : answers, probabilites, confiance.

    ⚠️ `answers[<id>]` est un DICT — `{type, <type>, probabilities, confidence}` — et non
    une chaine. Le lire comme une chaine rend un score INFERIEUR AU HASARD et fait
    accuser le modele a tort (vu le 2026-09-20, 0/24).
    """
    if _agent is None:
        raise HTTPException(status_code=503, detail="modele pas encore charge")
    if not d.state or not d.questions:
        raise HTTPException(status_code=400, detail="state et questions sont requis")
    t0 = time.perf_counter()
    try:
        sortie = _agent.system_one(d.state, d.questions)
    except Exception as e:
        logger.warning(f"[DECIDE] refuse : {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    sortie["ms"] = round((time.perf_counter() - t0) * 1000)
    return sortie
