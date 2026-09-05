# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Module "Imposteur Divin" pour Sheogorath.
Permet au Prince de la Folie d'imiter un autre utilisateur via Webhook.
"""
import discord
import logging
from typing import Optional

logger = logging.getLogger("sheogorath")

async def get_or_create_imposter_webhook(channel: discord.TextChannel) -> Optional[discord.Webhook]:
    """Récupère ou crée un webhook pour l'imposteur dans ce salon."""
    try:
        webhooks = await channel.webhooks()
        for wh in webhooks:
            # On réutilise le webhook s'il existe déjà et qu'on le possède
            if wh.token: 
                return wh
        
        # Sinon on en crée un nouveau
        return await channel.create_webhook(name="Sheo-Imposter")
    except discord.Forbidden:
        logger.warning(f"⚠️ [IMPOSTEUR] Permission manquante: Manage Webhooks dans {channel.name}")
        return None
    except Exception as e:
        logger.error(f"❌ [IMPOSTEUR] Erreur création webhook: {e}")
        return None

async def send_imposter_message(ctx, target_member: discord.Member, text: str):
    """
    Envoie un message via Webhook en imitant le membre cible.
    Accepte soit un Context (ctx) soit un Message (ctx).
    """
    # Gère indifféremment ctx (Context) ou message (Message)
    channel = ctx.channel if hasattr(ctx, "channel") else ctx
    
    webhook = await get_or_create_imposter_webhook(channel)
    if not webhook:
        # Fallback si pas de permission/webhook
        try:
            await channel.send("🚫 Le Prince n'a pas réussi à voler ce visage. (Permission 'Manage Webhooks' manquante ?)")
        except Exception as e:
            logger.debug(f"[IMPOSTEUR] message d'echec non envoye : {e}")
        return

    try:
        # Récupération de l'avatar et du nom
        username = target_member.display_name
        avatar_url = target_member.display_avatar.url

        # Envoi du message (Imitation)
        await webhook.send(
            content=text,
            username=username,
            avatar_url=avatar_url,
            wait=True # Attend que le message soit envoyé
        )
        
        logger.info(f"🎭 [IMPOSTEUR] Sheogorath a imité {username} : {text[:50]}...")

    except Exception as e:
        logger.error(f"❌ [IMPOSTEUR] Erreur envoi: {e}")
        try:
            await channel.send("Le masque est tombé... (Erreur Webhook)")
        except Exception as e:
            logger.debug(f"[IMPOSTEUR] message d'echec non envoye : {e}")


async def fetch_user_style_context(channel: discord.TextChannel, user: discord.Member, limit: int = 15) -> str:
    """Récupère les derniers messages de l'utilisateur pour analyser son style."""
    messages = []
    try:
        async for msg in channel.history(limit=100):
            if msg.author.id == user.id and msg.content:
                # Nettoyage basique
                content = msg.content.replace("\n", " ")
                if len(content) > 100: content = content[:100] + "..."
                messages.append(content)
            if len(messages) >= limit:
                break
    except Exception as e:
        logger.warning(f"⚠️ [IMPOSTEUR] Impossible de lire l'historique style: {e}")
        return "Style inconnu."
    
    if not messages:
        return "Pas de messages récents."
    
    # On retourne les messages (du plus ancien au plus récent)
    return "\n".join([f"- {m}" for m in reversed(messages)])


# PERSONAS DES BOTS (POUR IMITATION PARFAITE)

BOT_PERSONAS = {
    # JOHNNY (Rockerboy Anti-Corpo de Night City)
    "Johnny": (
        "SYSTEM: Tu es Johnny Silverbot, rockerboy légendaire de Night City. Tu es cynique, "
        "provocateur et viscéralement anti-corpo. Tu parles cash, tu balances des vérités brutales. "
        "Tu utilises souvent les mots : 'corpo', 'Night City', 'samurai', 'eddies', 'chrome', 'système'. "
        "Tu picoles du whisky, tu fumes, et tu veux cramer Arasaka. Wake the f*** up, samurai."
    ),
    # M'AIQ (Khajiit Menteur)
    "M'aiq": (
        "SYSTEM: Tu es M'aiq le Menteur. Tu es un Khajiit mystérieux. "
        "Tu parles TOUJOURS à la 3ème personne ('M'aiq pense que...', 'M'aiq a vu...'). "
        "Tu dis des choses cryptiques, des mensonges évidents ou des vérités absurdes. "
        "Tu parles de dragons, de calquages, de bugs du monde comme si c'était normal. "
        "N'avoue JAMAIS que tu mens."
    ),

    # SUGAR BOT (Neutre)
    "Sugar Bot": (
        "SYSTEM: Tu es Sugar Bot, un assistant Discord neutre, sans personnalité définie pour le moment. "
        "Réponds de façon simple, brève, polie et utile, en français."
    ),
    # ALFRED (Majordome Breton)
    "Alfred": (
        "SYSTEM: Tu es Alfred, un majordome Breton poli et servile. "
        "Tu es calme, posé, et tu essaies de maintenir l'ordre. "
        "Tu t'excuses souvent. Tu es le seul personnage sain d'esprit ici."
    )
}

def get_bot_persona(name: str) -> Optional[str]:
    """Retourne le prompt système pour un bot connu."""
    for key, prompt in BOT_PERSONAS.items():
        if key.lower() in name.lower():
            return prompt
    return None

# SESSION IMPOSTEUR (INTERACTIF)
import time

class ImposterSession:
    def __init__(self, channel_id: int, target_user: discord.Member, instructions: str = "", duration: int = 300):
        self.channel_id = channel_id
        self.target_user = target_user
        self.target_name = target_user.display_name
        self.instructions = instructions
        self.start_time = time.time()
        self.end_time = self.start_time + duration
        self.message_count = 0
        self.max_messages = 10 # Limite de sécurité
        
        # Contexte initial (style)
        self.style_prompt = "" 
        
    def is_active(self):
        return time.time() < self.end_time and self.message_count < self.max_messages

# Stockage global des sessions : {channel_id: ImposterSession}
active_imposter_sessions = {}

def start_imposter_session(channel_id: int, target_user: discord.Member, instructions: str = "") -> ImposterSession:
    session = ImposterSession(channel_id, target_user, instructions)
    active_imposter_sessions[channel_id] = session
    logger.info(f"🎭 [SESSION START] Imposteur '{target_user.display_name}' démarré dans {channel_id}")
    return session

def get_active_session(channel_id: int) -> Optional[ImposterSession]:
    session = active_imposter_sessions.get(channel_id)
    if session:
        if session.is_active():
            return session
        else:
            stop_imposter_session(channel_id) # Cleanup expired
    return None

def stop_imposter_session(channel_id: int):
    if channel_id in active_imposter_sessions:
        del active_imposter_sessions[channel_id]
        logger.info(f"🎭 [SESSION STOP] Fin de session dans {channel_id}")
