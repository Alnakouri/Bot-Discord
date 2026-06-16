# -*- coding: utf-8 -*-
"""
Gestionnaire d'événements serveur pour les bots Discord.
Messages de bienvenue/départ et anniversaires.
"""
import discord
import random

# Import de la base de données (local)
from shared.shared_database import (
    get_todays_birthdays, has_user_interacted,
    log_event
)


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
}


def get_welcome_message(bot_name: str, user: discord.Member) -> str:
    """Retourne un message de bienvenue personnalisé."""
    messages = WELCOME_MESSAGES.get(bot_name.lower(), WELCOME_MESSAGES["sheogorath"])
    return random.choice(messages).format(user=user.mention)


def get_goodbye_message(bot_name: str, user: discord.Member) -> str:
    """Retourne un message de départ personnalisé."""
    messages = GOODBYE_MESSAGES.get(bot_name.lower(), GOODBYE_MESSAGES["sheogorath"])
    return random.choice(messages).format(user=user.display_name)


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
}


def get_birthday_message(bot_name: str, user: discord.Member) -> str:
    """Retourne un message d'anniversaire personnalisé."""
    messages = BIRTHDAY_MESSAGES.get(bot_name.lower(), BIRTHDAY_MESSAGES["sheogorath"])
    return random.choice(messages).format(user=user.mention)


# FONCTIONS POUR LES ÉVÉNEMENTS

async def handle_member_join(bot, member: discord.Member, bot_name: str):
    """Gère l'arrivée d'un nouveau membre."""
    # Chercher le canal de bienvenue ou la taverne des bots
    target_channel = None
    for channel in member.guild.text_channels:
        if "taverne" in channel.name.lower() and "bot" in channel.name.lower():
            target_channel = channel
            break
        elif "bienvenue" in channel.name.lower() or "welcome" in channel.name.lower():
            target_channel = channel
    
    if target_channel:
        # Probabilité de message (pour éviter le spam si plusieurs bots)
        # Sheogorath: 40%, M'aiq: 30%, Alfred: 30%
        probs = {"sheogorath": 0.4, "maiq": 0.3, "alfred": 0.3}
        if random.random() < probs.get(bot_name.lower(), 0.3):
            message = get_welcome_message(bot_name, member)
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
            probs = {"sheogorath": 0.5, "maiq": 0.25, "alfred": 0.25}
            if random.random() < probs.get(bot_name.lower(), 0.33):
                message = get_birthday_message(bot_name, member)
                await target_channel.send(message)
                log_event(bot_name, "INFO", f"Anniversaire souhaité à {member.name}")
