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
    "sheogorath": [
        "🧀 **NOUVEAU MORTEL !** Bienvenue dans mon royaume de folie, {user} ! "
        "Prends un fromage, assieds-toi sur ce crâne, et PARLE-MOI DE TES RÊVES LES PLUS ÉTRANGES !",
        
        "🎭 Ah ! {user} a osé entrer ! ES-TU FOU ? Non ? EH BIEN TU LE DEVIENDRAS ! "
        "Bienvenue dans le chaos, mortel !",
        
        "✨ {user} ! Le destin t'a mené ici, ou peut-être était-ce juste un mauvais virage. "
        "BIENVENUE ! N'oublie pas : ici, les règles sont... optionnelles.",
    ],
    
    "maiq": [
        "🐱 M'aiq a vu beaucoup de nouveaux visages... {user} en est un de plus. "
        "Khajiit espère que tu as des histoires intéressantes à raconter.",
        
        "👀 Certains disent que {user} est nouveau ici. M'aiq pense que c'est vrai... ou pas.",
        
        "🗨️ {user} arrive ! M'aiq connaît beaucoup de rumeurs sur les nouveaux arrivants... "
        "mais M'aiq est discret. Pour l'instant.",
    ],
    
    "alfred": [
        "🤵 Bienvenue, {user}. Je suis Alfred, le majordome de ce serveur. "
        "Si vous avez besoin de quoi que ce soit... eh bien, débrouillez-vous d'abord, puis demandez-moi.",
        
        "☕ Ah, {user}. *soupir* Un autre invité à servir. "
        "Bienvenue. Le thé sera prêt quand je l'aurai décidé.",
        
        "🎩 {user}, je présume ? Bienvenue. Tâchez de ne pas faire de désordre. "
        "Je viens juste de nettoyer.",
    ],
    
    "malena": [
        "💅 Oh mais c'est {user} ! Bienvenue ma vie ! Ici c'est chez moi, "
        "fais comme chez toi mais touche à rien ooh ! Bénissou bénissou !",
        
        "✨ Wesh {user} ! T'es nouveau ici toi ? Viens viens, "
        "chui Malena, la seule et unique ! T'as du style ou pas ? 😏",
        
        "🌟 Ay {user} ! Bienvenue dans le quartier ma vie ! "
        "Ici c'est Marseille bébé, et moi chui la reine du Vieux-Port ooh !",
    ],
    "sugar": [
        "Bonjour {user}, bienvenue sur le serveur.",
        "Bienvenue, {user} ! Heureux de t'accueillir parmi nous."
    ],
}

GOODBYE_MESSAGES = {
    "sheogorath": [
        "👋 {user} nous quitte ? NON ! Attends, si en fait... AU REVOIR ! "
        "Ou pas. Reviens quand la folie te manquera !",
        
        "🧀 {user} part ? Prends un fromage pour la route ! "
        "...Non en fait, laisse-le. Plus de fromage pour MOI !",
    ],
    
    "maiq": [
        "🐱 M'aiq a entendu dire que {user} partait... "
        "Certains reviennent toujours. Ou pas.",
        
        "👋 {user} s'en va. M'aiq se souviendra de cette personne... peut-être.",
    ],
    
    "alfred": [
        "🤵 {user} nous quitte. *range un verre* Bonne continuation, Monsieur/Madame.",
        
        "👋 Au revoir, {user}. N'oubliez pas : la porte est toujours... fermée. "
        "Mais on peut toujours la rouvrir.",
    ],
    
    "malena": [
        "👋 Oh {user} sen va ? Beng t'façon ciao ma vie ! "
        "Reviens quand tu veux, y'a toujours de la place ici ooh !",
        
        "😢 Ay {user} nous quitte ! Peuchère... Allez bonne route ! "
        "Mais oublie pas, ici c'est chez toi hein !",
    ],
    "sugar": [
        "Au revoir {user}. Bonne continuation.",
        "{user} a quitté le serveur. Au revoir !"
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
    "malena": "malena",
    "sugar bot": "sugar",
}


def cle_persona(bot_name: str):
    """Cle de pool pour ce bot, ou None s'il n'a pas de repliques a lui."""
    return _CLE_PAR_BOT.get((bot_name or "").strip().lower())


def _tirer(pools: dict, bot_name: str, gabarit: str, **format_kwargs):
    """Tire une replique dans le pool du bot. None s'il n'en a pas."""
    cle = cle_persona(bot_name)
    messages = pools.get(cle) if cle else None
    if not messages:
        logger.warning(
            f"⚠️ [EVENEMENTS] Aucune replique {gabarit} pour '{bot_name}' — "
            "il se tait. Ajouter ses repliques plutot que de le laisser "
            "emprunter la voix d'un autre."
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
    "sheogorath": [
        "🎂🧀 **JOYEUX ANNIVERSAIRE {user} !** Voici un fromage GÉANT pour toi ! "
        "Qu'est-ce ? Tu n'aimes pas le fromage ? TOO BAD ! C'EST TON ANNIVERSAIRE, TU MANGES DU FROMAGE !",
        
        "🎉 {user} ! C'est ton jour de naissance ! Ou comme je l'appelle : "
        "le jour où le chaos a reçu un nouveau serviteur ! FÉLICITATIONS !",
    ],
    
    "maiq": [
        "🎂 M'aiq a entendu une rumeur... {user} serait né(e) aujourd'hui ! "
        "Si c'est vrai, Khajiit te souhaite un joyeux anniversaire.",
        
        "🐱 {user}, certains disent que c'est ton anniversaire. "
        "M'aiq espère que tu recevras de nombreux cadeaux... et des rumeurs.",
    ],
    
    "alfred": [
        "🎂 Joyeux anniversaire, {user}. J'ai préparé un gâteau. "
        "Non, vous ne pouvez pas choisir la saveur. C'est Earl Grey. Comme le thé.",
        
        "🤵 {user}, il semblerait que ce soit votre anniversaire. "
        "*pose une bougie sur un scone* Voilà. Faites un vœu. Rapidement.",
    ],
    
    "malena": [
        "🎂✨ JOYEUX ANNIVERSAIRE {user} !! Oh la la c'est la fête ma vie ! "
        "Viens là que je te fasse la bise ! T'as tarpin grandi ooh ! 🎉💅",
        
        "🌟 {user} C'EST TON ANNIVERSAIRE CON !! Beng viens, "
        "chui tarpin contente pour toi ! Que Dieu te bénisse ma vie ! Bénissou bénissou ! ❤️",
        
        "🎉 Ay {user} ! Bon anniversaire le sang ! "
        "J'espère que t'as un gâteau avec des paillettes et du rose dessus ! "
        "Sinon c'est pas un vrai anniversaire ooh ! 💅✨",
    ],
    "sugar": [
        "Joyeux anniversaire, {user} ! Passe une excellente journée.",
        "Bon anniversaire {user} !"
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
    # Sheogorath: 30%, M'aiq: 20%, Alfred: 20%, Sugar Bot: 30%
    probs = {"sheogorath": 0.3, "maiq": 0.2, "alfred": 0.2, "sugar": 0.3}
    seuil = probs.get(cle_persona(bot_name), 0.3)
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
    # Vérifier si le membre a interagi avec les bots
    if not has_user_interacted(member.id):
        return  # Ne rien dire si l'utilisateur n'a jamais interagi
    
    # Chercher le canal
    target_channel = None
    for channel in member.guild.text_channels:
        if "taverne" in channel.name.lower() and "bot" in channel.name.lower():
            target_channel = channel
            break
    
    if target_channel:
        # Probabilité plus faible pour les départs
        if random.random() < 0.2:  # 20% de chance
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
        return
    
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
            probs = {"sheogorath": 0.4, "maiq": 0.2, "alfred": 0.2, "sugar": 0.2}
            if random.random() < probs.get(cle_persona(bot_name), 0.33):
                message = get_birthday_message(bot_name, member)
                if not message:
                    continue   # pool absent : deja journalise, et on se TAIT
                await target_channel.send(message)
                log_event(bot_name, "INFO", f"Anniversaire souhaité à {member.name}")
