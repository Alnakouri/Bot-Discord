# -*- coding: utf-8 -*-
"""Mode test : le bot ne publie que sur le serveur prive.

POURQUOI UN PATCH PLUTOT QUE DES GARDES DISSEMINEES
---------------------------------------------------
Les 6 bots publient depuis ~35 boucles periodiques, plus les reponses a la volee,
plus les decrets, plus les slash commands. Poser une garde a chaque endroit, c'est
garantir d'en oublier une — et une seule oubliee suffit a faire fuiter un message
en public, ce que le mode test est precisement cense empecher.

`Message.reply` est un raccourci vers `abc.Messageable.send` (discord.py 2.7).
Donc **un seul** point de passage couvre les reponses, les envois en salon et les
messages prives. On l'entoure d'une garde, et plus rien ne peut passer a cote.

Les slash commands empruntent un autre chemin (`InteractionResponse.send_message`
et `Webhook.send` pour les suivis) : ils sont gardes separement.

Le mode est relu toutes les 5 s depuis `data/bot_features.json` : le basculer
depuis le dashboard ne demande AUCUN redemarrage.
"""
import json
import os
import time
from pathlib import Path

import discord

from shared.bot_features import peut_publier, is_test_mode, test_guild_id

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
FICHIER_SERVEURS = "bot_guilds.json"

_DEJA_INSTALLE = False
# Anti-spam : en mode test un bot bavard produirait une ligne de log par tentative.
_DERNIER_LOG = {}
_INTERVALLE_LOG = 30.0


def _journaliser_blocage(logger, bot_id, ou, guild_id):
    if logger is None:
        return
    maintenant = time.time()
    cle = (ou, guild_id)
    if maintenant - _DERNIER_LOG.get(cle, 0.0) < _INTERVALLE_LOG:
        return
    _DERNIER_LOG[cle] = maintenant
    cible = test_guild_id()
    motif = ("aucun serveur prive choisi dans le dashboard" if cible is None
             else f"hors du serveur prive {cible}")
    endroit = "message prive" if guild_id is None else f"serveur {guild_id}"
    logger.info(
        f"[MODE TEST:{bot_id}] envoi bloque ({ou}, {endroit}) — {motif}."
    )


def _guild_id_de(destination):
    """Le serveur d'une destination d'envoi, ou None pour un message prive."""
    guild = getattr(destination, "guild", None)
    return getattr(guild, "id", None)


def installer_garde_publication(bot_id: str, logger=None):
    """Entoure les sorties Discord d'une garde. Idempotent.

    Ne fait rien de visible hors mode test : la garde laisse tout passer.
    """
    global _DEJA_INSTALLE
    if _DEJA_INSTALLE:
        return False
    _DEJA_INSTALLE = True

    envoi_origine = discord.abc.Messageable.send

    async def envoi_garde(self, *args, **kwargs):
        guild_id = _guild_id_de(self)
        if not peut_publier(bot_id, guild_id):
            _journaliser_blocage(logger, bot_id, "message", guild_id)
            return None          # meme forme qu'un envoi rate : l'appelant ne casse pas
        return await envoi_origine(self, *args, **kwargs)

    discord.abc.Messageable.send = envoi_garde

    # Slash commands : chemin distinct de Messageable.send.
    reponse_origine = discord.InteractionResponse.send_message

    async def reponse_garde(self, *args, **kwargs):
        guild_id = getattr(getattr(self, "_parent", None), "guild_id", None)
        if not peut_publier(bot_id, guild_id):
            _journaliser_blocage(logger, bot_id, "slash command", guild_id)
            return None
        return await reponse_origine(self, *args, **kwargs)

    discord.InteractionResponse.send_message = reponse_garde

    if logger:
        logger.info(f"🧪 [MODE TEST:{bot_id}] garde de publication installée.")
    return True


def enregistrer_serveurs(bot_id: str, bot, logger=None):
    """Publie la liste des serveurs du bot pour le menu deroulant du dashboard.

    Le dashboard n'est pas un client Discord : sans cette remontee, il faudrait
    coller un identifiant de serveur a la main.
    """
    chemin = os.path.join(DATA_DIR, FICHIER_SERVEURS)
    try:
        donnees = {}
        if os.path.exists(chemin):
            with open(chemin, "r", encoding="utf-8") as f:
                donnees = json.load(f) or {}
        if not isinstance(donnees, dict):
            donnees = {}

        donnees[bot_id] = {
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "guilds": [{"id": str(g.id), "name": g.name} for g in bot.guilds],
        }

        os.makedirs(DATA_DIR, exist_ok=True)
        provisoire = chemin + ".tmp"
        with open(provisoire, "w", encoding="utf-8") as f:
            json.dump(donnees, f, indent=2, ensure_ascii=False)
        os.replace(provisoire, chemin)
        return True
    except Exception as e:
        # Un confort de dashboard ne doit JAMAIS empecher un bot de demarrer.
        if logger:
            logger.warning(f"⚠️ [MODE TEST:{bot_id}] serveurs non publiés : {e}")
        return False


def etat_lisible(bot_id: str) -> str:
    """Une ligne pour les logs de demarrage."""
    if not is_test_mode(bot_id):
        return "mode test INACTIF (publication normale)"
    cible = test_guild_id()
    if cible is None:
        return "mode test ACTIF mais AUCUN serveur privé choisi → silence total"
    return f"mode test ACTIF → publie uniquement sur le serveur {cible}"
