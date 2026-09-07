# -*- coding: utf-8 -*-
"""Les mentions INVENTEES par un modele n'atteignent pas Discord.

LE DEFAUT, MESURE EN TEST LIVE LE 2026-09-07
--------------------------------------------
`!rumeur` a publie :

    📢 [RUMEUR] M'aiq a entendu dire que <@123456789> collectionne les cuilleres...

Le prompt demande une rumeur « sur un joueur » sans jamais fournir d'identifiant reel :
le modele en a donc fabrique un. Discord ne resout pas cet identifiant et affiche le
`<@123456789>` brut, au milieu de la phrase.

POURQUOI UN FILET DE SORTIE, ET PAS SEULEMENT UNE CONSIGNE
-----------------------------------------------------------
Une consigne de prompt ne garantit rien : elle est suivie la plupart du temps, et
« la plupart du temps » est exactement ce qui a produit ce message-la. Le filet, lui,
tient meme quand le modele desobeit — et il couvre du meme coup les cinq autres bots,
leurs decrets, leurs rumeurs et leurs repliques.

CE QUI EST NEUTRALISE, ET RIEN D'AUTRE
---------------------------------------
⚠️ La regle est **structurelle**, jamais une question de cache. Un identifiant Discord
est un flocon de neige : au moins 17 chiffres, et ses 42 bits de poids fort portent une
date posterieure au 2015-01-01. `123456789` n'a que 9 chiffres — il ne PEUT pas etre un
identifiant, quel que soit le serveur.

Regarder si le membre existe dans le cache serait la mauvaise regle : un membre non
charge ferait effacer une mention parfaitement legitime. Ici, une mention valide ne peut
pas etre touchee : c'est ce qui rend le filet installable sur les six bots sans risque.
"""
import re
import time

try:
    import discord
except ImportError:      # le module doit rester lisible/testable sans discord.py
    discord = None

# 2015-01-01T00:00:00Z, en millisecondes : l'epoque des flocons Discord.
EPOQUE_DISCORD_MS = 1420070400000

# `<@123>` (utilisateur), `<@!123>` (surnom, forme heritee).
# Les roles `<@&...>` et les salons `<#...>` ne sont pas touches : aucun modele n'en a
# invente, et un role efface serait une regression plus visible que le defaut.
_MENTION = re.compile(r"<@!?(\d+)>")

REMPLACEMENT = "quelqu'un"

_DEJA_INSTALLE = False


def identifiant_plausible(brut) -> bool:
    """Un flocon Discord, ou une invention ?"""
    texte = str(brut)
    if not texte.isdigit() or not 17 <= len(texte) <= 20:
        return False
    if texte[0] == "0":
        # Un flocon est un entier ecrit tel quel : Discord n'emet jamais de zeros de
        # tete. `00000000000000001` a bien 17 chiffres et n'est pourtant pas un id.
        return False
    horodatage_ms = (int(texte) >> 22) + EPOQUE_DISCORD_MS
    # Une seconde d'avance est possible (horloges desynchronisees) ; un jour ne l'est pas.
    return EPOQUE_DISCORD_MS <= horodatage_ms <= (time.time() + 86400) * 1000


def neutraliser_mentions_inventees(texte, remplacement=REMPLACEMENT):
    """Rend `(texte_nettoye, nombre_de_mentions_neutralisees)`.

    Un texte qui n'est pas une chaine (None, un embed) ressort tel quel : l'appelant
    est un patch d'envoi, il voit passer toutes les formes.
    """
    if not isinstance(texte, str) or "<@" not in texte:
        return texte, 0

    compte = 0

    def _remplacer(m):
        nonlocal compte
        if identifiant_plausible(m.group(1)):
            return m.group(0)
        compte += 1
        return remplacement

    return _MENTION.sub(_remplacer, texte), compte


def _filtrer(args, kwargs, journaliser):
    """Le `content` d'un envoi Discord : 1er argument positionnel, ou `content=`."""
    if args:
        nettoye, compte = neutraliser_mentions_inventees(args[0])
        if compte:
            journaliser(compte, args[0])
            args = (nettoye,) + tuple(args[1:])
    elif "content" in kwargs:
        nettoye, compte = neutraliser_mentions_inventees(kwargs["content"])
        if compte:
            journaliser(compte, kwargs["content"])
            kwargs = dict(kwargs, content=nettoye)
    return args, kwargs


def installer_filtre_mentions(bot_id: str, logger=None):
    """Entoure les sorties Discord du filet. Idempotent.

    Meme point de passage que le mode test (`abc.Messageable.send` couvre `reply`, les
    envois en salon et les MP), plus les deux chemins des slash commands.
    """
    global _DEJA_INSTALLE
    if _DEJA_INSTALLE or discord is None:
        return False
    _DEJA_INSTALLE = True

    def _journaliser(compte, avant):
        if logger:
            logger.warning(
                f"🚫 [MENTION INVENTEE:{bot_id}] {compte} mention(s) impossible(s) "
                f"neutralisee(s) : {avant[:120]}"
            )

    def _envelopper(origine):
        async def _envoi(self, *args, **kwargs):
            args, kwargs = _filtrer(args, kwargs, _journaliser)
            return await origine(self, *args, **kwargs)
        return _envoi

    discord.abc.Messageable.send = _envelopper(discord.abc.Messageable.send)
    discord.InteractionResponse.send_message = _envelopper(
        discord.InteractionResponse.send_message)
    discord.Webhook.send = _envelopper(discord.Webhook.send)   # suivis de slash commands

    if logger:
        logger.info(f"🛡️ [MENTIONS:{bot_id}] filet anti-mention inventée installé.")
    return True
