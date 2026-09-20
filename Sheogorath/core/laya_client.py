# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/laya_client.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

# -*- coding: utf-8 -*-
"""Client du service Laya — borne dure, repli sur la regle en place, jamais de silence.

Laya est le trieur « System One » partage par les six bots (`laya-server/`). Il tranche
les decisions que les bots prennent AVANT d'appeler un LLM et qui sont aujourd'hui des
listes de mots-cles.

⚠️ CE MODULE EXISTE POUR UNE SEULE RAISON : rendre le service INOFFENSIF quand il
manque. Le partage d'un service entre six bots n'est acceptable que si sa panne coute
une amelioration, jamais un bot. Trois regles, et elles sont verrouillees par des tests :

  1. BORNE DURE. 300 ms, soit trois fois la mediane mesuree (105 ms le 2026-09-20).
     Au-dela, on n'attend pas : on rend le repli.
  2. TOUTE panne rend le REPLI — celui que l'appelant passe, c'est-a-dire ce que sa
     regle en place aurait decide. Jamais None, jamais une exception qui remonte.
  3. AUCUN ETAT. Pas de cache, pas de memoire entre appels : un redemarrage du service
     ne perd rien, et deux bots ne peuvent pas s'influencer a travers lui.

⚠️ `answers[<id>]` est un DICT — `{type, <type>, probabilities, confidence}` — et non une
chaine. Le lire comme une chaine rend un score INFERIEUR AU HASARD et fait accuser le
modele a tort (vu le 2026-09-20 : 0/24).

⚠️ LA CONFIANCE N'EST PAS UN GARDE-FOU. Mesure du 20/09 : 0,91 sur une erreur
(« quelqu'un sait a quelle heure commence le stream ? » -> `aggro`) contre 0,15 sur une
reussite. Elle est rendue a l'appelant pour le journal, mais ce module ne s'en sert pas
pour filtrer, et personne ne devrait le faire sans l'avoir remesure.
"""
import logging
import os

logger = logging.getLogger("laya_client")

# Nom du service sur `bots-network`. Vide = client desactive, tout part au repli :
# c'est l'etat par defaut tant qu'un bot n'a pas ete explicitement branche.
URL = os.getenv("LAYA_URL", "").rstrip("/")

# 3x la mediane mesuree. Voir la regle 1 en tete.
BORNE_S = float(os.getenv("LAYA_BORNE_S", "0.3"))

_alerte_donnee = False


def _une_seule_fois(message):
    """Une alerte qui crie a chaque message n'est plus une alerte."""
    global _alerte_donnee
    if not _alerte_donnee:
        logger.warning(f"[LAYA] {message} — repli sur la regle en place")
        _alerte_donnee = True


async def choisir(state, question_id, question, repli):
    """Rend `(etiquette, source, confiance)`. `source` vaut "laya" ou "repli".

    `repli` est ce que la regle EN PLACE a decide : c'est lui qui sort des que le
    service manque, tarde, ou repond de travers. L'appelant n'a donc jamais a gerer
    d'erreur, et son comportement d'avant reste son plancher.
    """
    if not URL:
        return repli, "repli", None

    try:
        import aiohttp
    except ImportError:
        _une_seule_fois("aiohttp absent")
        return repli, "repli", None

    borne = aiohttp.ClientTimeout(total=BORNE_S)
    try:
        async with aiohttp.ClientSession(timeout=borne) as session:
            async with session.post(f"{URL}/decide",
                                    json={"state": state,
                                          "questions": {question_id: question}}) as r:
                if r.status != 200:
                    _une_seule_fois(f"HTTP {r.status}")
                    return repli, "repli", None
                sortie = await r.json()
    except Exception as e:
        # Panne, borne depassee, service absent, JSON casse : tout finit ici, et tout
        # finit au repli. C'est la regle 2, et c'est ce qui rend le partage acceptable.
        _une_seule_fois(f"{type(e).__name__}: {e}")
        return repli, "repli", None

    try:
        brut = sortie["answers"][question_id]
        # ⚠️ dict, pas chaine : voir l'avertissement en tete.
        etiquette = brut[brut["type"]]
        return etiquette, "laya", brut.get("confidence")
    except (KeyError, TypeError) as e:
        _une_seule_fois(f"reponse illisible ({type(e).__name__})")
        return repli, "repli", None


def question_choice(instructions, criteres):
    """Fabrique une question `choice`. `criteres` : {etiquette: ce qu'elle recouvre}.

    ⚠️ Les questions se definissent chez le BOT, jamais dans le service : c'est le bot
    qui sait ce qu'il decide, et une regle de persona qui migrerait dans un service
    partage serait une regle sortie de son fichier.
    """
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteres)}
