# -*- coding: utf-8 -*-
"""
Gestionnaire d'événements serveur pour les bots Discord.
Messages de bienvenue/départ et anniversaires.
"""
import discord
import logging
import random

# Import de la base de données (local)
from shared.shared_database import (
    get_todays_birthdays, has_user_interacted,
    log_event
)

# ⚠️ Ce nom doit rester dans la liste des `shared_name` de `bot_logger.setup_logger`,
# sinon ces lignes ne partent NI dans logs/<bot>_<date>.log NI dans le JSONL du
# tableau de bord : elles ne survivraient que par le `lastResort` de `logging`,
# qui ignore INFO.
logger = logging.getLogger("server_events")


# MESSAGES DE BIENVENUE

WELCOME_MESSAGES = {
    "alfred": [
        "🤵 Bienvenue, {user}. Je suis Alfred, le majordome de ce serveur. "
        "Si vous avez besoin de quoi que ce soit... eh bien, débrouillez-vous d'abord, puis demandez-moi.",
        
        "☕ Ah, {user}. Un autre invité à servir. "
        "Bienvenue. Le thé sera prêt quand je l'aurai décidé.",
        
        "🎩 {user}, je présume ? Bienvenue. Tâchez de ne pas faire de désordre. "
        "Je viens juste de nettoyer.",
    ],
    "sugar": [
        "Un nouveau visage, et déjà plus d'allure que la moyenne par ici. "
        "Bienvenue {user}, tu vas te plaire. 🍬",

        "{user} débarque. Installe-toi, sers-toi, "
        "et ne crois pas un mot de ce qu'on te racontera sur moi.",
    ],
}

GOODBYE_MESSAGES = {
    "alfred": [
        "🤵 {user} nous quitte. Je rangerai son verre. Bonne continuation.",
        
        "👋 Au revoir, {user}. N'oubliez pas : la porte est toujours... fermée. "
        "Mais on peut toujours la rouvrir.",
    ],
    "sugar": [
        "{user} s'en va. On garde la place au chaud, on ne touche à rien. ✨",

        "Partir, c'est mourir un peu — mais {user} reviendra. Ils reviennent tous.",
    ],
}


# ⚠️ Le nom que chaque bot passe a ces fonctions n'est PAS la cle de ses pools.
# « M'aiq » donne "m'aiq" et « Sugar Bot » donne "sugar bot" : ni l'un ni l'autre
# n'existe dans les dictionnaires ci-dessus, et le repli `.get(cle, ...["sheogorath"])`
# leur faisait dire les repliques de SHEOGORATH — « NOUVEAU MORTEL ! Bienvenue dans mon
# royaume de folie ». Johnny, lui, n'a aucun pool du tout. Le defaut ne s'etait jamais
# vu parce que `on_member_join` etait du code mort sur M'aiq jusqu'au 11/09 et qu'une
# arrivee est rare ET tiree au sort.
#
# Cette table est donc la SEULE traduction autorisee. Un nom absent rend None : le bot
# se TAIT (et le journal le dit). Se taire est correct ; parler avec la voix d'un autre
# ne l'est pas.
_CLE_PAR_BOT = {
    "sheogorath": "sheogorath",
    "m'aiq": "maiq",
    "alfred": "alfred",
    "johnny": "johnny",
    "malena": "malena",
    "sugar bot": "sugar",
}

# DECISION du 2026-09-13 : seuls Alfred et Sugar accueillent, saluent les departs et
# souhaitent les anniversaires. Les quatre autres se taisent — ce n'est PAS un defaut,
# c'est un choix, et il ne doit donc rien journaliser d'alarmant
# ([[gotcha-alerte-qui-crie-pour-du-nominal]]).
#
# C'est ce qui separe les deux silences :
#   - nom connu, hors de cet ensemble  -> silence VOULU  (journal : debug)
#   - nom inconnu, ou pool manquant    -> silence SUBI   (journal : warning)
# Sans cette distinction, la seule facon de se taire serait de sortir le bot de
# `_CLE_PAR_BOT`, et on perdrait le cri qui rattrape une faute de nom.
_PORTE_PAROLE = {"alfred", "sugar"}

# Seuils de tirage au sort (probabilité d'envoi si le bot participe).
# Seuls les porte-parole peuvent figurer dans ces tables (décision du 2026-09-13).
SEUILS_BIENVENUE = {"alfred": 0.2, "sugar": 0.3}
SEUILS_DEPART = {"alfred": 0.2, "sugar": 0.2}
SEUILS_ANNIVERSAIRE = {"alfred": 0.2, "sugar": 0.2}


def cle_persona(bot_name: str):
    """Cle de pool pour ce bot, ou None si ce nom n'est pas celui d'un des 6 bots."""
    return _CLE_PAR_BOT.get((bot_name or "").strip().lower())


def participe_aux_evenements(bot_name: str) -> bool:
    """Ce bot dit-il bienvenue / au revoir / bon anniversaire ?"""
    return cle_persona(bot_name) in _PORTE_PAROLE


def _tirer(pools: dict, bot_name: str, gabarit: str, **format_kwargs):
    """Tire une replique dans le pool du bot. None s'il ne doit pas parler."""
    cle = cle_persona(bot_name)
    if cle is not None and cle not in _PORTE_PAROLE:
        # Silence VOULU : ce bot ne participe pas a ces evenements.
        logger.debug(f"[EVENEMENTS] {bot_name} ne participe pas aux messages {gabarit}.")
        return None

    messages = pools.get(cle) if cle else None
    if not messages:
        logger.warning(
            f"⚠️ [EVENEMENTS] Aucune replique {gabarit} pour '{bot_name}' — "
            "il se tait. Nom inconnu, ou pool manquant pour un porte-parole : "
            "dans les deux cas c'est un defaut, pas une decision."
        )
        return None
    return random.choice(messages).format(**format_kwargs)


def get_welcome_message(bot_name: str, user: discord.Member):
    """Retourne un message de bienvenue personnalisé, ou None."""
    return _tirer(WELCOME_MESSAGES, bot_name, "de bienvenue", user=user.mention)


def get_goodbye_message(bot_name: str, user: discord.Member):
    """Retourne un message de départ personnalisé, ou None."""
    return _tirer(GOODBYE_MESSAGES, bot_name, "de depart", user=user.display_name)


# MESSAGES D'ANNIVERSAIRE

BIRTHDAY_MESSAGES = {
    "alfred": [
        "🎂 Joyeux anniversaire, {user}. J'ai préparé un gâteau. "
        "Non, vous ne pouvez pas choisir la saveur. C'est Earl Grey. Comme le thé.",
        
        "🤵 {user}, il semblerait que ce soit votre anniversaire. "
        "Une bougie sur un scone fera l'affaire. Faites un vœu. Rapidement.",
    ],
    "sugar": [
        "Un an de plus au compteur pour {user}, et ça ne se voit toujours pas. "
        "C'est ta journée, profites-en. 🍬",

        "C'est l'anniversaire de {user} : aujourd'hui tout lui est permis. "
        "Demain, on reparlera de ses goûts en musique.",
    ],
}


def get_birthday_message(bot_name: str, user: discord.Member):
    """Retourne un message d'anniversaire personnalisé, ou None."""
    return _tirer(BIRTHDAY_MESSAGES, bot_name, "d'anniversaire", user=user.mention)


# FONCTIONS POUR LES ÉVÉNEMENTS

async def handle_member_join(bot, member: discord.Member, bot_name: str):
    """Gère l'arrivée d'un nouveau membre."""
    # ⚠️ Cette ligne est la seule preuve que le gestionnaire a TOURNE. L'envoi qui suit
    # est tire au sort (20-30 %), donc l'absence de message ne dit RIEN — sans cette
    # trace on ne peut pas distinguer « le dé a dit non » de « l'evenement n'est jamais
    # arrive » (le cas de M'aiq et Sheogorath jusqu'au 11/09 : intent manquant).
    logger.info(f"👋 [ARRIVEE] {member} sur '{member.guild.name}' — vu par {bot_name}")

    if not participe_aux_evenements(bot_name):
        logger.debug(f"[ARRIVEE] {bot_name} ne participe pas aux messages d'accueil.")
        return

    # Chercher le canal de bienvenue ou la taverne des bots
    target_channel = None
    for channel in member.guild.text_channels:
        if "taverne" in channel.name.lower() and "bot" in channel.name.lower():
            target_channel = channel
            break
        elif "bienvenue" in channel.name.lower() or "welcome" in channel.name.lower():
            target_channel = channel

    if not target_channel:
        logger.info(
            f"[ARRIVEE] Aucun salon d'accueil sur '{member.guild.name}' "
            "(cherche : « taverne »+« bot », « bienvenue », « welcome ») — rien d'envoye."
        )
        return

    # Probabilité de message (pour éviter le spam si plusieurs bots)
    seuil = SEUILS_BIENVENUE.get(cle_persona(bot_name), 0.2)
    if random.random() >= seuil:
        logger.info(f"[ARRIVEE] {bot_name} se tait (tirage, seuil {seuil:.0%}).")
        return

    message = get_welcome_message(bot_name, member)
    if not message:
        return          # pool absent : deja journalise par _tirer, et on se TAIT
    await target_channel.send(message)
    log_event(bot_name, "INFO", f"Message de bienvenue envoyé pour {member.name}")


async def handle_member_remove(bot, member: discord.Member, bot_name: str):
    """Gère le départ d'un membre (seulement s'il a interagi)."""
    logger.info(f"👋 [DEPART] {member} a quitté '{member.guild.name}' — vu par {bot_name}")

    if not participe_aux_evenements(bot_name):
        logger.debug(f"[DEPART] {bot_name} ne participe pas aux messages de départ.")
        return

    # Vérifier si le membre a interagi avec les bots
    if not has_user_interacted(member.id):
        logger.debug(f"[DEPART] {member} n'a jamais interagi — aucun message.")
        return

    # Chercher le canal
    target_channel = None
    for channel in member.guild.text_channels:
        if "taverne" in channel.name.lower() and "bot" in channel.name.lower():
            target_channel = channel
            break

    if not target_channel:
        logger.info(
            f"[DEPART] Aucun salon trouvé sur '{member.guild.name}' "
            "(cherche : « taverne »+« bot ») — rien d'envoyé."
        )
        return

    seuil = SEUILS_DEPART.get(cle_persona(bot_name), 0.2)
    if random.random() >= seuil:
        logger.info(f"[DEPART] {bot_name} se tait (tirage, seuil {seuil:.0%}).")
        return

    message = get_goodbye_message(bot_name, member)
    if not message:
        return      # pool absent : deja journalise par _tirer, et on se TAIT
    await target_channel.send(message)
    log_event(bot_name, "INFO", f"Message de départ pour {member.name}")


async def check_and_send_birthdays(bot, bot_name: str):
    """Vérifie et envoie les messages d'anniversaire."""
    birthday_user_ids = get_todays_birthdays()

    if not birthday_user_ids:
        return

    logger.info(f"🎂 [ANNIVERSAIRE] {len(birthday_user_ids)} anniversaire(s) — vu par {bot_name}")

    if not participe_aux_evenements(bot_name):
        logger.debug(f"[ANNIVERSAIRE] {bot_name} ne participe pas aux messages d'anniversaire.")
        return

    # Chercher le canal
    target_channel = None
    for guild in bot.guilds:
        for channel in guild.text_channels:
            if "taverne" in channel.name.lower() and "bot" in channel.name.lower():
                target_channel = channel
                break
        if target_channel:
            break

    if not target_channel:
        logger.info(
            "[ANNIVERSAIRE] Aucun salon d'anniversaire trouvé "
            "(cherche : « taverne »+« bot ») — rien d'envoyé."
        )
        return

    seuil = SEUILS_ANNIVERSAIRE.get(cle_persona(bot_name), 0.2)
    for user_id in birthday_user_ids:
        # Récupérer le membre
        member = None
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                break

        if member:
            # Probabilité pour éviter les doublons entre bots
            # Un seul bot envoie le message
            if random.random() >= seuil:
                logger.info(f"[ANNIVERSAIRE] {bot_name} se tait (tirage, seuil {seuil:.0%}).")
                continue
            message = get_birthday_message(bot_name, member)
            if not message:
                continue   # pool absent : deja journalise, et on se TAIT
            await target_channel.send(message)
            log_event(bot_name, "INFO", f"Anniversaire souhaité à {member.name}")
