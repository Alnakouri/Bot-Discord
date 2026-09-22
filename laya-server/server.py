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
import threading
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

# ── GARDER LES POIDS CHAUDS ───────────────────────────────────────────────────
# ⚠️ MESURE DU 2026-09-22, et c'est la raison d'etre de ce bloc. Apres 45 h sans
# aucun appel, la premiere rafale depuis le conteneur d'Alfred a donne :
#
#     appel 1 .... 694 ms          -> REPLI (borne du client : 300 ms)
#     appels 2-5 . 301 ms, timeout -> REPLI
#     appel 6 .... 277 ms          -> laya
#     une fois chaud, 10 appels : mediane 135 ms, max 370
#     puis, apres 3 min de pause seulement : 1er appel a 292 ms — 8 ms sous la borne
#
# **Cinq appels sur six repartis au repli.** En prod, Laya est appele rarement : le
# PREMIER appel est donc souvent le SEUL, et c'est precisement celui qui rate la borne.
# La fonction pour laquelle le service existe est celle qu'il servait le plus mal.
#
# Le healthcheck du compose ne corrigeait rien : il tape `/health`, qui ne fait AUCUNE
# inference. Un ping HTTP ne rechauffe pas des poids.
#
# D'ou ce fil : une inference minuscule a intervalle regulier. 30 s est bien sous les
# 3 min ou la latence remonte deja, et coute ~135 ms de CPU toutes les 30 s (0,5 %).
# ⚠️ L'intervalle doit rester NETTEMENT sous le delai de refroidissement observe : le
# remonter sans remesurer rouvre le defaut en silence.
CHAUFFE_S = float(os.getenv("LAYA_CHAUFFE_S", "30"))

# Volontairement minuscules : on ne mesure rien ici, on occupe les poids.
ETAT_DE_CHAUFFE = "bonjour"
QUESTION_DE_CHAUFFE = {"chauffe": {"type": "choice",
                                   "instructions": "De quoi parle ce message ?",
                                   "criteria": {"salutation": "une salutation",
                                                "autre": "autre chose"}}}
_chauffes = 0
_chauffe_ms = None


def _chauffe(agent):
    """Une inference minuscule. Rend sa duree en ms."""
    t0 = time.perf_counter()
    agent.system_one(ETAT_DE_CHAUFFE, QUESTION_DE_CHAUFFE)
    return round((time.perf_counter() - t0) * 1000)


def _boucle_de_chauffe(agent, intervalle, arret=None, une_seule_fois=False):
    """Chauffe, dort, recommence — jusqu'a l'arret.

    ⚠️ Elle n'a JAMAIS le droit de tuer le service : une inference qui echoue se
    journalise et la boucle continue. Le contrat du service est « consultatif », et un
    fil de confort qui ferait tomber le serveur le violerait.
    """
    global _chauffes, _chauffe_ms
    while True:
        try:
            _chauffe_ms = _chauffe(agent)
            _chauffes += 1
            if _chauffes == 1:
                logger.info(f"chauffe active, une inference toutes les {intervalle:g}s "
                            f"(premiere : {_chauffe_ms} ms)")
        except Exception as e:
            logger.warning(f"[CHAUFFE] echouee, sans consequence : {type(e).__name__}: {e}")
        if une_seule_fois:
            return
        if arret is not None and arret.wait(intervalle):
            return
        if arret is None:
            time.sleep(intervalle)


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

    if CHAUFFE_S > 0:
        threading.Thread(target=_boucle_de_chauffe, args=(_agent, CHAUFFE_S),
                         name="chauffe", daemon=True).start()
    else:
        logger.info("chauffe DESACTIVEE (LAYA_CHAUFFE_S=0) : le premier appel apres une "
                    "periode calme retombera au repli chez le client")


@app.get("/health")
def health():
    """Le client s'en sert au demarrage : inutile de borner un service pas encore pret."""
    return {"ok": _agent is not None, "modele": _modele, "charge_ms": _charge_ms,
            # Pour verifier DEPUIS DEHORS que la chauffe tourne : si `chauffes` ne bouge
            # pas entre deux appels, les poids refroidissent et le client repartira au
            # repli sans qu'aucune erreur ne soit levee nulle part.
            "chauffes": _chauffes, "chauffe_ms": _chauffe_ms, "chauffe_s": CHAUFFE_S}


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
