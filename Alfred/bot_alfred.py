# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
import time
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

DATA_DIR = os.getenv("DATA_DIR", ".")
import base64

#  SETUP (MUST BE FIRST)
# LOAD SECURE ENV (Supports encrypted .env files)
# This MUST be done before any other imports that might use environment variables
from pathlib import Path
from core.secure_env import load_secure_env
from core.boucles import installer_anti_rattrapage
# Unsets conflicting Google Cloud env vars
load_secure_env(Path(__file__).parent)
from core.models import GEMINI_FLASH, GEMINI_FLASH_LITE, GROQ_FAST, MISTRAL_MAIN, groq_kwargs, nvidia_kwargs, NVIDIA_BASE_URL
# ⚠️ La cascade inline d'Alfred n'avait NI garde anti-fuite NI garde de reponse vide :
# les deux vivaient dans le noyau, qu'elle recopie sans les emporter. On les importe au
# lieu d'en faire une 8e copie. `generate_response` etait appele sans etre importe.
from core.llm_cascade import generate_response, appel_hors_cascade, _est_vide, _fuite_de_raisonnement, _cle_du_pool, delai_de_reprise

import discord
from discord.ext import commands, tasks
from discord.ext.commands import cooldown, BucketType
from google.genai import types
from groq import Groq 
from mistralai import Mistral
from openai import OpenAI
import aiohttp
import asyncio
import random
import re
from core.response_memory import ResponseMemory
from core.anti_tic import build_anti_tic_consigne
import json
import logging
from datetime import datetime, timedelta
from core.smart_router import classify_request, RequestType, download_media, get_model_cascade, resolve_media_attachments
from core.api_tracking import tracer_appel
from core.media_handler import process_image_ollama
from core.transcript import ligne_de_contexte
from core.chrono import Chrono

try:
    from shared.memes_fr import build_meme_consigne
    MEMES_AVAILABLE = True
except ImportError:
    MEMES_AVAILABLE = False
    def build_meme_consigne(*a, **k): return ""

import collections
meme_recent = collections.defaultdict(lambda: collections.deque(maxlen=8))  # {channel_id: deque[ref]}
import speech_recognition as sr
from discord.ext import voice_recv
import io # For buffer handling
import wave
try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import save
except ImportError:
    ElevenLabs = None
    save = None

# LOGGING STRUCTURÉ
from core.bot_logger import setup_logger
logger = setup_logger("alfred")

if ElevenLabs is None:
    logger.warning("[INIT] ElevenLabs non disponible. Fonctions vocales désactivées.")

# ZONE DE CONFIGURATION : ALFRED PENNYWORTH

# IMPORT SAFE CLIENT (CRITICAL)
# This module contains a workaround for the "Invalid project resource name" error
# by ensuring the Gemini client does not incorrectly default to Vertex AI.
# The previous try/except block was hiding potential `ImportError` if `google-genai`
# was not installed, leading to silent failures.
from core.safe_client import get_client as get_safe_genai_client

# IMPORT DES SYSTÈMES (locaux pour Discloud)

try:
    from shared.shared_database import (
        is_maintenance_mode, is_ignored_channel, get_reputation, get_reputation_level
    )
    from shared.slash_commands import setup_slash_commands, sync_slash_commands
    from shared.server_events import handle_member_join, handle_member_remove, check_and_send_birthdays
    DATABASE_AVAILABLE = True
    try:
        from shared.games import setup_games
        from games_persona import PERSONA
        GAMES_AVAILABLE = True
    except ImportError:
        GAMES_AVAILABLE = False
except ImportError as e:
    logger.warning(f"⚠️ [ALFRED] Modules optionnels non disponibles: {e}")
    DATABASE_AVAILABLE = False

try:
    from shared.twitch_announcer import setup_twitch_announcer
    TWITCH_AVAILABLE = True
except ImportError:
    TWITCH_AVAILABLE = False
    def setup_twitch_announcer(*a, **k): return None

twitch_announcer = None

try:
    from shared.discord_profile import DiscordDailyBio
except ImportError:
    DiscordDailyBio = None

try:
    from shared.discord_status import DiscordDailyStatus
except ImportError:
    DiscordDailyStatus = None


# CREDENTIALS
# ⚠️ REMPLACEZ CECI PAR LE TOKEN DE VOTRE NOUVEAU BOT ALFRED
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# API KEYS ROTATION (Google Gemini - Partagées)
GEMINI_API_KEYS = [
    os.getenv("GEMINI_KEY_1"), 
    os.getenv("GEMINI_KEY_2"), 
    os.getenv("GEMINI_KEY_3"), 
    os.getenv("GEMINI_KEY_4"), 
]
# Filter out None values
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]

# FALLBACK API KEYS
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ELEVENLABS (VOCAL)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ALFRED_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "ErXwobaYiN019PkySvjV") # Default: Antoni (Nice British/Calm)

elevenlabs_client = None
if ELEVENLABS_API_KEY:
    try:
        elevenlabs_client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    except Exception as e:
        logger.warning(f"⚠️ ElevenLabs Error: {e}")

# CONVERSATION HISTORY
conversation_history = {}
MAX_HISTORY = 30

# MULTI-API KEY MANAGER (Gère TOUTES les APIs avec cooldowns)
from core.api_manager import MultiAPIKeyManager
from core.graceful_shutdown import setup_graceful_shutdown

# Initialisation
key_manager = MultiAPIKeyManager()
key_manager.register_api("gemini", GEMINI_API_KEYS)
key_manager.register_api("groq", [GROQ_API_KEY] if GROQ_API_KEY else [])
key_manager.register_api("mistral", [MISTRAL_API_KEY] if MISTRAL_API_KEY else [])
# ⚠️ NVIDIA manquait ici : sans pool, sa clé ne pouvait pas être mise en
# quarantaine sur un 429, et son index restait absent de `api_key_status`.
key_manager.register_api("nvidia", [NVIDIA_API_KEY] if NVIDIA_API_KEY else [])
# MEMORY SETTINGS
# LTM SYSTEM
try:
    from alfred_memory import FactMemory, DailyMemory
except ImportError:
    from Alfred.alfred_memory import FactMemory, DailyMemory
alfred_facts_file = os.path.join(DATA_DIR, "alfred_facts.json")
alfred_memory_file = os.path.join(DATA_DIR, "alfred_memory.json")
fact_memory = FactMemory(alfred_facts_file)
daily_memory = DailyMemory(alfred_memory_file)

async def _daily_llm_call(system_prompt, user_message):
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "daily_read"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client, nvidia_client=nvidia_client,
        bot_label="Alfred", temperature=0.5, max_tokens=60)

class AlfredBrainAdapter:
    def get_user_context(self, user_id, message_content=""):
        daily_summary = daily_memory.get_context_summary(user_id)
        relevant_facts = fact_memory.get_relevant_facts(user_id, message_content, k=3)
        dr = daily_memory.get_daily_read(user_id)
        daily_read_addition = f"\n[CONSIGNE DU JOUR] {dr}" if dr else ""
        
        fact_context = ""
        if relevant_facts:
            fact_context = f"\n[CE QUE VOUS SAVEZ SUR CE MONSIEUR (MÉMOIRE LONG TERME)]:\n- " + "\n- ".join(relevant_facts)
            
        memory_instruction = (
            f"\n\n[INSTRUCTION MÉMOIRE CONCOMITANTE]: Si vous apprenez un fait durable, important et nouveau sur ce Monsieur — ses préférences, son métier, ses projets, mais AUSSI sa façon d'argumenter, ce qui le pique, ses habitudes (le connaître sert à mieux le remettre à sa place) — vous DEVEZ l'ajouter discrètement à la fin de votre réponse entouré de balises XML : <fact>Le fait appris</fact>.\n"
            f"⚠️ RÈGLE ABSOLUE : un fait ne peut s'appuyer que sur ce qui vient DE LUI — SES messages, son profil public, sa bio, ses actes. Ne lui attribuez JAMAIS un thème, un mot ou une image que c'est VOUS qui avez introduit — vos propres réponses font partie de la conversation et ne vous apprennent rien sur lui. Si rien de neuf n'est venu de lui, ne mettez rien."
        )
        return f"{daily_summary}{daily_read_addition}{fact_context}{memory_instruction}"

    def update_user(self, user_id, user_name, topic=None):
        pass

alfred_brain = AlfredBrainAdapter()

# ANTI-REPETITION MEMORY (Par Serveur - ENHANCED)
  # {guild_id: ["réponse1", "réponse2", ...]} (max 10)
response_memory = ResponseMemory()


PROBA_REACTION = 0.20  # 20%
PROBA_INTERVENTION = 0.10 # 10%
DELAY_MIN, DELAY_MAX = 1.0, 2.0

# VOCAL PATROL (Détection de chant en vocal via Gemini Audio)
vocal_patrol_active = False
vocal_patrol_channel = None
vocal_patrol_text_channel = None  # Canal texte pour envoyer les sanctions
singing_warnings = {}  # {user_id: count} - Compteur d'avertissements
soundboard_streaks = {} # {user_id: streak_count} - Compteur d'affilée (pour Cendrillon13)
VOCAL_PATROL_TARGET = "cendrillon13"

# PERSONALITY (LE MAJORDOME CYNIQUE - VERSION AGRESSIVE)
from alfred_data import PERSONALITY_PROMPT


# ═══════════════════════════════════════════════════════════════
# TOOLS — FONCTIONS D'AGENTS (Alfred Edition)
# ═══════════════════════════════════════════════════════════════

def tool_set_maintenance(status: bool):
    """Active ou désactive le mode maintenance du manoir (Global)."""
    try:
        if DATABASE_AVAILABLE:
            from shared.shared_database import set_maintenance_mode
            set_maintenance_mode(status)
            logger.info(f"🛠️ [TOOL MAINT] Alfred a réglé maintenance sur : {status}")
            return f"SUCCÈS : Le mode maintenance est désormais {'ACTIVÉ' if status else 'DÉSACTIVÉ'}."
        return "ERREUR : La console de maintenance est inaccessible (DB OFF)."
    except Exception as e:
        return f"ERREUR : {e}"

async def tool_get_user_stats(user_id_str: str):
    """Récupère les statistiques de réputation d'un invité."""
    try:
        numeric_id = re.search(r'\d+', user_id_str)
        if not numeric_id:
            return "ERREUR : ID invalide."
        
        user_id = int(numeric_id.group())
        if DATABASE_AVAILABLE:
            rep = get_reputation(user_id)
            level = get_reputation_level(rep['points'])
            return f"RAPPORT : Le sujet {user_id_str} possède {rep['points']} points de réputation. Rang : {level}."
        return "ERREUR : Archives inaccessibles."
    except Exception as e:
        return f"ERREUR : {e}"

ALFRED_TOOLS_DEFINITION = [
    {
        "function_declarations": [
            {
                "name": "set_maintenance",
                "description": "Active ou désactive le mode maintenance pour l'ensemble du système si nécessaire ou si on te le demande.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "status": {"type": "BOOLEAN", "description": "True pour activer, False pour désactiver."}
                    },
                    "required": ["status"]
                }
            },
            {
                "name": "get_user_stats",
                "description": "Consulte les archives pour connaître la réputation et le rang d'un invité.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "user_id": {"type": "STRING", "description": "La mention ou l'ID de l'utilisateur."}
                    },
                    "required": ["user_id"]
                }
            }
        ]
    }
]

# INITIALISATION

# CONFIGURATION INTENTS (ADMIN)
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True # Nécessaire pour gérer les rôles
intents.voice_states = True # Nécessaire pour le vocal

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_command_error(ctx, error):
    """Les 6 bots partagent le prefixe « ! » : chacun voit donc les commandes des cinq
    autres et leve CommandNotFound. Sans ce gestionnaire, discord.py les journalise en
    ERROR — six lignes rouges pour un seul « !decret », et le compteur d'erreurs du
    dashboard qui gonfle alors qu'il ne se passe rien d'anormal.

    ⚠️ On n'avale QUE CommandNotFound. Definir ce gestionnaire remplace celui de
    discord.py : tout le reste doit donc etre journalise ici, sinon on rendrait muettes
    de vraies erreurs de commande.
    """
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        logger.warning(f"[COMMANDE] usage incorrect : {ctx.command} — {error}")
        await ctx.send(f"🤵 Il me faudrait un ordre complet, Monsieur : `{ctx.command.name} {ctx.command.signature}`. ☕")
        return
    logger.error(f"❌ [COMMANDE] {ctx.command} : {error}", exc_info=error)


# Client Initialization
groq_client = None
mistral_client = None

try: groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0)
except Exception as e: logger.warning(f"[INIT] Groq indisponible : {e}")

try: mistral_client = Mistral(api_key=MISTRAL_API_KEY)
except Exception as e: logger.warning(f"[INIT] Mistral indisponible : {e}")


# 4e fournisseur : quota independant des 3 autres. `max_retries=0` pour que la
# cascade prenne le relais au lieu que le SDK dorme sur un 429.
nvidia_client = None
if NVIDIA_API_KEY:
    try: nvidia_client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL, max_retries=0)
    except Exception as e: logger.warning(f'[NVIDIA] client indisponible: {e}')

ENABLE_DAILY_BIO = os.getenv("ENABLE_DAILY_BIO", "1") != "0"
daily_bio = DiscordDailyBio(
    bot=bot, bot_id="alfred", bot_label="Alfred",
    personality_prompt=PERSONALITY_PROMPT,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, nvidia_client=nvidia_client,
    logger=logger, enabled=ENABLE_DAILY_BIO,
) if DiscordDailyBio else None

# Statut Discord auto-piloté par la personnalité (jumeau de la bio).
# La liste ci-dessous n'est plus qu'un FALLBACK si le LLM est indisponible.
_STATUS_FALLBACK = [
    ("playing", "Cirer l'argenterie"),
    ("playing", "Préparer le thé Earl Grey"),
    ("playing", "Nettoyer le sang sur le tapis (Encore)"),
    ("playing", "Recoudre un costume"),
    ("playing", "Soupirer de manière britannique"),
    ("playing", "Juger vos choix de vie"),
    ("playing", "Dépoussiérer le Bat-Computer"),
    ("playing", "Polir les Batarangs"),
    ("playing", "Repasser les capes"),
    ("playing", "Servir le dîner (froid)"),
    ("playing", "Gérer l'agenda de Monsieur Wayne"),
    ("playing", "Nourrir les chauves-souris"),
]
ENABLE_DAILY_STATUS = os.getenv("ENABLE_DAILY_STATUS", "1") != "0"
daily_status = DiscordDailyStatus(
    bot=bot, bot_id="alfred", bot_label="Alfred",
    personality_prompt=PERSONALITY_PROMPT, fallback_activities=_STATUS_FALLBACK,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, nvidia_client=nvidia_client,
    logger=logger, enabled=ENABLE_DAILY_STATUS,
) if DiscordDailyStatus else None


# EVENTS

@bot.event
async def on_ready():
    logger.info('--------------------------------------------------')
    logger.info('☕ Alfred est à votre service. Le thé est chaud.')
    logger.info('--------------------------------------------------')

    # MODE TEST (dashboard) — garde de publication + remontee des serveurs pour le
    # menu deroulant. Optionnel : sans shared/, le bot publie normalement.
    try:
        from shared.test_mode import installer_garde_publication, enregistrer_serveurs, etat_lisible
        installer_garde_publication("alfred", logger)
        enregistrer_serveurs("alfred", bot, logger)
        logger.info(f"🧪 [MODE TEST:alfred] {etat_lisible('alfred')}")
    except ImportError:
        pass  # shared/ est optionnel, le bot doit tourner sans

    # FILET ANTI-MENTION INVENTEE. Meme point de passage que la garde ci-dessus.
    # Le 2026-09-07, `!rumeur` a publie `<@123456789>` : un identifiant que le modele
    # a fabrique faute d'en avoir un vrai. Un `try` separe — ces deux filets ne
    # dependent pas l'un de l'autre.
    try:
        from shared.mentions import installer_filtre_mentions
        installer_filtre_mentions("alfred", logger)
    except ImportError:
        pass  # shared/ est optionnel, le bot doit tourner sans

    # Le classement comptait les BOTS : le 2026-09-07, `/leaderboard` listait
    # Sheogorath, Johnny et « Onizuka » — SugarBot sous un nom fige a sa premiere
    # interaction. Un bot est le seul a savoir qu'il en est un : il se declare.
    try:
        from shared.shared_database import marquer_utilisateur_bot
        if bot.user:
            marquer_utilisateur_bot(bot.user.id, bot.user.name, bot.user.display_name)
    except ImportError:
        pass  # shared/ est optionnel, le bot doit tourner sans
    
    # HEALTH CHECK
    logger.info('📊 [HEALTH CHECK] APIs disponibles :')
    logger.info(f'   ✅ Gemini : {len([k for k in GEMINI_API_KEYS if k])} clés')
    logger.info(f'   {"✅" if mistral_client else "❌"} Mistral (prioritaire)')
    logger.info(f'   {"✅" if groq_client else "❌"} Groq')
    logger.info(f'   {"✅" if nvidia_client else "❌"} NVIDIA (nemotron)')
    if elevenlabs_client:
        logger.info('   ✅ ElevenLabs (Vocal)')
    logger.info('--------------------------------------------------')
    
    
    if not status_loop_alfred.is_running():
        status_loop_alfred.start()
    if not weekly_protip_alfred.is_running():
        weekly_protip_alfred.start()  # Conseil Hebdomadaire (Vendredi)
    if not birthday_check_alfred.is_running():
        birthday_check_alfred.start()  # Anniversaires
    if daily_bio and not daily_bio_loop_alfred.is_running():
        daily_bio_loop_alfred.start()

    
    global twitch_announcer
    if TWITCH_AVAILABLE and twitch_announcer is None:
        twitch_announcer = setup_twitch_announcer(
            bot, "alfred", logger,
            personality_prompt=PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client, nvidia_client=nvidia_client, bot_label="Alfred")
        if twitch_announcer:
            if not twitch_poll_loop.is_running():
                twitch_poll_loop.start()

    # INITIALISATION DES COMMANDES SLASH
    if DATABASE_AVAILABLE:
        try:
            setup_slash_commands(bot, "Alfred")
            await sync_slash_commands(bot)
            logger.info("[SLASH] Commandes slash initialisées")
        except Exception as e:
            # on_ready rejoue a chaque reconnexion : la 2e pose leve
            # CommandAlreadyRegistered et avortait tout le reste de on_ready.
            logger.error(f"[SLASH] Erreur: {e}")
        
    # INITIALISATION DES MINI-JEUX
    if DATABASE_AVAILABLE and GAMES_AVAILABLE:
        try:
            setup_games(bot, logger, PERSONA)
            logger.info("☕ [GAMES] Mini-jeux initialisés pour Alfred")
        except Exception as e:
            logger.error(f"[GAMES] Erreur d'initialisation des mini-jeux: {e}")

# ACTIVITY LOOP
current_alfred_activity = "Cirer l'argenterie"

@tasks.loop(seconds=90)
async def twitch_poll_loop():
    if twitch_announcer:
        await twitch_announcer.tick()

@twitch_poll_loop.before_loop
async def before_twitch_poll():
    await bot.wait_until_ready()

@tasks.loop(minutes=30)
async def status_loop_alfred():
    global current_alfred_activity
    activity = None
    if daily_status:
        await daily_status.ensure_daily_status()  # régénère au changement de jour, sinon cache
        activity = daily_status.pick_activity()
    if activity is None:  # module absent/désactivé : repli sur la liste fallback
        t, name = random.choice(_STATUS_FALLBACK)
        alias = {
            "watch": "watching", "watching": "watching", "regarde": "watching",
            "play": "playing", "playing": "playing", "joue": "playing",
            "listen": "listening", "listening": "listening", "écoute": "listening",
            "ecoute": "listening",
        }
        mapped_t = alias.get(str(t).strip().lower())
        if mapped_t == "watching":
            txt = f"Regarde {name}"
        elif mapped_t == "playing":
            txt = f"Joue {name}"
        elif mapped_t == "listening":
            txt = f"Écoute {name}"
        else:
            txt = name
        activity = discord.CustomActivity(name=txt[:60])
    current_alfred_activity = activity.name  # réutilisé dans les prompts (« ce que tu fais »)
    await bot.change_presence(activity=activity)

@tasks.loop(hours=12)
async def birthday_check_alfred():
    """Vérifie les anniversaires tous les 12h."""
    if DATABASE_AVAILABLE:
        await check_and_send_birthdays(bot, "Alfred")

# CONSEILS DU MAJORDOME (Publié le vendredi)
@tasks.loop(hours=1)
async def weekly_protip_alfred():
    """Vérifie si c'est vendredi 18h pour donner un conseil."""
    now = datetime.now()
    if now.weekday() == 4 and now.hour == 18 and now.minute < 15:
        # Chercher le canal
        target_channel = None
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if "taverne" in channel.name.lower() and "bot" in channel.name.lower():
                    target_channel = channel
                    break
        
        if target_channel:
             # Générer un conseil via LLM
            prompt = (
                f"SYSTEM: {PERSONALITY_PROMPT}\n"
                f"INSTRUCTION: Donne un 'Conseil du Majordome' raffiné et utile (ou sarcastique) aux membres du serveur. "
                "Sujets : savoir-vivre, hygiène, nettoyage de scènes de crime, préparation du thé, gestion du stress."
                "Reste bref (2 phrases). Utilise ton style britannique."
            )
            
            try:
                # Utilise Mistral ou Gemini
                resp = "Un bon majordome a toujours un mouchoir propre. Pour les larmes... ou le sang."
                if mistral_client:
                    # `or resp` : le conseil de repli reste la reponse quand l'appel echoue.
                    resp = await appel_hors_cascade(
                        "mistral", mistral_client.chat.complete,
                        key_manager=key_manager, bot_label="Alfred",
                        modele=MISTRAL_MAIN, timeout=30,
                        model=MISTRAL_MAIN, messages=[{"role": "user", "content": prompt}],
                    ) or resp
                
                await target_channel.send(f"🧐 **[CONSEIL DU VENDREDI]** {resp}")
                # Sleep pour ne pas spammer tout le quart d'heure
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"❌ Conseil error: {e}")

@tasks.loop(hours=1)
async def daily_bio_loop_alfred():
    if daily_bio:
        await daily_bio.ensure_daily_bio()

@daily_bio_loop_alfred.before_loop
async def before_daily_bio_alfred():
    await bot.wait_until_ready()

# ÉVÉNEMENTS SERVEUR

@bot.event
async def on_member_join(member):
    if DATABASE_AVAILABLE:
        await handle_member_join(bot, member, "Alfred")

@bot.event
async def on_member_remove(member):
    if DATABASE_AVAILABLE:
        await handle_member_remove(bot, member, "Alfred")

# COMMANDES ADMINISTRATIVES (ALFRED)

class AlfredActions:
    @staticmethod
    async def grant_role(ctx, role_name):
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if role:
            try:
                await ctx.author.add_roles(role)
                return f"🤵 **Alfred** : Votre nouveau titre de '{role_name}' a été enregistré, Monsieur. Tâchez d'en être digne."
            except discord.Forbidden:
                return "🤵 **Alfred** : Mes excuses, Monsieur, mais ce rôle est au-dessus de mes modestes prérogatives (Vérifiez la hiérarchie de mon rôle)."
        return f"🤵 **Alfred** : Je ne trouve aucun titre nommé '{role_name}' dans mes registres."

    @staticmethod
    async def move_member(ctx, member: discord.Member, channel_name):
        channel = discord.utils.get(ctx.guild.voice_channels, name=channel_name)
        if member and channel:
            if member.voice:
                await member.move_to(channel)
                return f"🤵 **Alfred** : Monsieur {member.display_name} a été escorté vers '{channel_name}', comme demandé."
            else:
                 return f"🤵 **Alfred** : Monsieur {member.display_name} n'est pas connecté vocalement."
        return "🤵 **Alfred** : Le transfert est impossible (Salon ou Membre introuvable)."

@bot.command(name="servir")
@commands.has_permissions(administrator=True)
@cooldown(1, 30, BucketType.user)
async def servir(ctx, *, action: str):
    """Commande centrale pour Alfred : !servir [rôle/message/déplacement]"""
    user_msg = action.lower()
    
    # 1. Gestion des Rôles
    if "rôle" in user_msg or "titre" in user_msg:
        # Extraction simplifiée : on cherche le dernier mot
        words = action.split()
        role_to_give = words[-1] 
        response = await AlfredActions.grant_role(ctx, role_to_give)
        await ctx.send(response)

    # 2. Envoi de Message Privé (DM)
    elif "message" in user_msg or "courrier" in user_msg:
        try:
            await ctx.author.send("🤵 **Alfred** : Voici les informations confidentielles que vous avez demandées, Monsieur.")
            await ctx.send("🤵 **Alfred** : Le courrier a été déposé dans vos appartements privés (DMs), Monsieur.")
        except discord.Forbidden:
            await ctx.send("🤵 **Alfred** : Vos appartements sont verrouillés (DMs fermés), Monsieur.")

    # 3. Déplacement Vocal (!servir déplacer @User vers Salon) - Simplifié ici vers "Salon de Discussion"
    elif "déplacer" in user_msg:
        # Tente de déplacer l'auteur par défaut pour l'exemple
        response = await AlfredActions.move_member(ctx, ctx.author, "Salon de Discussion")
        await ctx.send(response)
    
    else:
        # Si c'est juste de la conversation, laisse l'IA gérer via process_commands non, via on_message
        await ctx.send("🤵 **Alfred** : Je ne suis pas sûr de comprendre quelle tâche administrative vous m'assignez, Monsieur.")

@bot.command(name="parle")
async def parle(ctx, *, text: str):
    """Fait parler Alfred dans le vocal (TTS)"""
    if not ctx.author.voice:
        return await ctx.send("🤵 **Alfred** : Rejoignez un salon vocal d'abord, Monsieur.")
    
    # Connection
    channel = ctx.author.voice.channel
    vc = ctx.voice_client
    if not vc:
        vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
    elif vc.channel != channel:
        await vc.move_to(channel)

    # Generation
    if not elevenlabs_client:
        # Nommer le fournisseur au salon sort du personnage — et n'aide personne :
        # celui qui peut y remedier lit les journaux, pas le fil de discussion.
        logger.warning("[VOIX] refuse : client ElevenLabs absent (cle manquante ?)")
        return await ctx.send("🤵 **Alfred** : Je crains d'avoir égaré ma voix, Monsieur. "
                              "L'écrit devra suffire.")

    async with ctx.typing():
        try:
            # Run in executor to avoid blocking
            def generate_audio():
                audio = elevenlabs_client.generate(
                    text=text,
                    voice=ALFRED_VOICE_ID,
                    model="eleven_multilingual_v2"
                )
                save(audio, "alfred_speech.mp3")
                return "alfred_speech.mp3"

            filename = await asyncio.to_thread(generate_audio)
            
            # Play
            vc.stop()
            vc.play(discord.FFmpegPCMAudio(filename))
        except Exception as e:
            await ctx.send(f"🤵 **Alfred** : J'ai une extinction de voix... ({e})")

# SINK AUDIO (STT)

import audioop

class AlfredSink(voice_recv.AudioSink):
    def __init__(self, ctx):
        self.ctx = ctx
        self.recognizer = sr.Recognizer()
        self.buffer = io.BytesIO()
        self.last_speech_time = datetime.now()
        
    def wants_opus(self):
        return False # We want PCM

    def write(self, user, data):
        # Accumulate PCM data (Stereo 16-bit 48kHz)
        self.buffer.write(data.pcm)

    @voice_recv.AudioSink.listener()
    def on_voice_packet(self, data):
        pass # Optional hooks

    def cleanup(self):
        self.buffer.seek(0)
        pcm_data = self.buffer.read()
        
        # Process Buffer (Raw PCM -> AudioData for SpeechRecognition)
        try:
            # Discord sends 48kHz Stereo 16-bit PCM (s16le)
            # We convert to MONO for better STT compatibility using audioop (No ffmpeg needed!)
            # tomono(fragment, width, left_factor, right_factor)
            mono_data = audioop.tomono(pcm_data, 2, 0.5, 0.5)
            
            # Create AudioData object directly from raw bytes
            audio_source = sr.AudioData(mono_data, 48000, 2)
            
            try:
                # Google Speech Recognition interprets the raw audio
                text = self.recognizer.recognize_google(audio_source, language="fr-FR")
                logger.info(f"🎤 [STT] Entendu : '{text}'")
                # Inject into bot logic
                asyncio.run_coroutine_threadsafe(self.process_text(text), bot.loop)
            except sr.UnknownValueError:
                pass # Silence or noise
            except Exception as e:
                logger.error(f"STT Error: {e}")
        except Exception as e:
            logger.error(f"Audio Processing Error: {e}")

    async def process_text(self, text):
        # Simuler un message pour activer on_message
        if "alfred" in text.lower() or "thé" in text.lower():
            await self.ctx.send(f"🎤 **J'ai entendu** : \"{text}\"")
            
            # Reponse Rapide (Echo Intelligent)
            if elevenlabs_client and self.ctx.voice_client:
                # Simple logic for demo: Speak generic response or echo
                # Ideal: Call Gemini here. For now, let's just acknowledge.
                response_text = "Bien reçu Monsieur. Je m'en occupe."
                
                try:
                    def generate_audio():
                        audio = elevenlabs_client.generate(text=response_text, voice=ALFRED_VOICE_ID, model="eleven_multilingual_v2")
                        save(audio, "alfred_response.mp3")
                        return "alfred_response.mp3"
                    
                    filename = await asyncio.to_thread(generate_audio)
                    self.ctx.voice_client.stop()
                    self.ctx.voice_client.play(discord.FFmpegPCMAudio(filename))
                except Exception as e:
                    logger.warning(f"[VOCAL] synthese ou lecture audio impossible : {e}")

@bot.command()
async def ecoute(ctx):
    """Rejoint le vocal et écoute (Expérimental - 10s)"""
    if not ctx.author.voice:
        return await ctx.send("🤵 **Alfred** : Vous n'êtes pas en vocal, Monsieur.")
        
    channel = ctx.author.voice.channel
    vc = ctx.voice_client
    
    if not vc:
        vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
    
    await ctx.send("🤵 **Alfred** : Je tends l'oreille pendant 10 secondes...")
    
    sink = AlfredSink(ctx)
    vc.listen(sink)
    
    await asyncio.sleep(10) # Listen for 10s
    
    vc.stop_listening()
    sink.cleanup()
    await ctx.send("🤵 **Alfred** : Analyse terminée.")
    await vc.disconnect()

# VOCAL PATROL - DÉTECTION DE CHANT EN TEMPS RÉEL (Gemini Audio)

class VocalPatrolSink(voice_recv.AudioSink):
    """Capture l'audio du vocal par segments pour analyse Gemini."""
    def __init__(self):
        self.buffers = {}  # {user_id: BytesIO}
        self.user_names = {}  # {user_id: display_name}
        
    def wants_opus(self):
        return False  # PCM brut

    def write(self, user, data):
        if user is None:
            return
        uid = user.id if hasattr(user, 'id') else user
        if uid not in self.buffers:
            self.buffers[uid] = io.BytesIO()
            self.user_names[uid] = user.name if hasattr(user, 'name') else str(uid)
        self.buffers[uid].write(data.pcm)

    @voice_recv.AudioSink.listener()
    def on_voice_packet(self, data):
        pass

    def cleanup(self):
        pass

    def get_combined_wav(self):
        """Combine tous les buffers audio en un seul fichier WAV en mémoire."""
        all_pcm = io.BytesIO()
        for uid, buf in self.buffers.items():
            buf.seek(0)
            all_pcm.write(buf.read())
        
        pcm_data = all_pcm.getvalue()
        if len(pcm_data) < 1000:  # Trop peu de données = silence
            return None
        
        # Convertir PCM stéréo en mono
        try:
            mono_data = audioop.tomono(pcm_data, 2, 0.5, 0.5)
        except Exception:
            mono_data = pcm_data
        
        # Encoder en WAV
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(1)       # Mono
            wf.setsampwidth(2)       # 16-bit
            wf.setframerate(48000)   # Discord = 48kHz
            wf.writeframes(mono_data)
        
        wav_buffer.seek(0)
        return wav_buffer.read()

    def get_active_users(self):
        """Retourne les users qui ont parlé/chanté."""
        active = []
        for uid, buf in self.buffers.items():
            buf.seek(0, 2)  # Seek to end
            size = buf.tell()
            if size > 5000:  # Assez de données audio
                active.append((uid, self.user_names.get(uid, str(uid))))
        return active

    def reset(self):
        """Vide les buffers pour le prochain cycle."""
        for buf in self.buffers.values():
            buf.close()
        self.buffers.clear()
        self.user_names.clear()


# CIBLE DE LA SURVEILLANCE VOCALE (username Discord)
VOCAL_PATROL_TARGET = "cendrillon13"
SANCTION_ROLE_NAME = "Barde Raté"
SANCTION_NICKNAME = "Cendrillon la Casserole"

# Tracking des sanctions actives pour restauration : {user_id: {"task": Task, "original_nick": str}}
active_sanctions = {}

# SANCTIONS POUR CHANT VOCAL / ABUS SOUNDBOARD
VOCAL_SANCTION_MESSAGES = [
    "🤵 Monsieur {user}. Ce que mes oreilles viennent de subir dans le salon vocal constitue un crime contre la musique. Cessez immédiatement. 😒",
    "🤵 {user}, le Manoir Wayne n'est PAS un karaoké. Les chauves-souris dans la cave pleurent en ce moment même. 🦇",
    "🤵 J'ai formellement identifié du... *chant*... provenant de {user}. Article 12 du Règlement : 'Toute nuisance sonore sera sanctionnée.' ☕",
    "🤵 {user}. Monsieur Wayne m'a personnellement téléphoné pour demander que ce... *bruit*... cesse immédiatement. 🧐",
    "🤵 Ce n'est pas un concert, {user}. C'est une attaque acoustique. Les murs du Manoir en tremblent. 😒",
    "🤵 {user}, la dernière personne à avoir chanté ici a été retrouvée dans le placard à balais. Avec les balais. 🧹",
    "🤵 Mes capteurs acoustiques confirment : {user} chante. Le niveau de douleur auditive est... considérable. 🎵❌",
    "🤵 {user}, même le Joker n'infligerait pas ça à Gotham. Et pourtant, il a essayé. 🦇",
]


async def analyze_audio_with_gemini(wav_data, user_names=None):
    """Envoie l'audio à Gemini pour détecter le chant/soundboard et obtenir un commentaire sarcastique.
    
    Args:
        wav_data: Données WAV brutes
        user_names: Liste des noms d'utilisateurs actifs dans le vocal
    
    Returns:
        None si erreur API
        (False, None) si pas de chant/soundboard
        (True, str) si détecté, avec commentaire sarcastique d'Alfred
    """
    # Construire la liste des utilisateurs pour le prompt
    users_str = ", ".join(user_names) if user_names else "des utilisateurs inconnus"

    # Appel hors cascade : c'est le helper qui tient le pool (cle en quarantaine =
    # aucun appel), `report_error` avec le delai du fournisseur, et le tracage en base.
    result = await appel_hors_cascade(
        "gemini",
        key_manager=key_manager, bot_label="Alfred", modele=GEMINI_FLASH, timeout=45,
        fabrique=lambda cle: get_safe_genai_client(api_key=cle),
        methode="models.generate_content",
        model=GEMINI_FLASH,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(inline_data=types.Blob(
                        mime_type="audio/wav",
                        data=wav_data
                    )),
                    types.Part(text=(
                        "Écoute attentivement cet audio. Est-ce que quelqu'un CHANTE ou ABUSE de la SOUNDBOARD dans cet enregistrement ? "
                        "Le chant inclut : fredonner, chanter des paroles, faire des vocalises, siffler une mélodie. "
                        "L'abus de soundboard inclut : sons répétitifs, effets sonores en boucle, bruits de mème, sons forts et distordus (earrape). "
                        "La parole normale, les rires naturels, et les bruits de fond ne comptent PAS. "
                        f"\n\nLes utilisateurs présents dans le vocal sont : {users_str}."
                        "\n\nRéponds avec ce FORMAT EXACT :\n"
                        "Ligne 1 : OUI ou NON\n"
                        "Ligne 2 (SEULEMENT si OUI) : Un commentaire SARCASTIQUE et DRÔLE de 2 phrases maximum, "
                        "dans le style d'Alfred Pennyworth (majordome britannique cynique de Batman). "
                        "CITE les utilisateurs par leur NOM dans ton commentaire. "
                        "Commente ce que tu as RÉELLEMENT entendu : la qualité du chant, le choix de chanson, "
                        "le niveau de nuisance sonore, ou le spam de soundboard. Sois MÉCHANT mais élégant. "
                        "Utilise 1-2 emojis parmi : 🧐 😒 🦇 ☕ 🎵❌ 🧹"
                    ))
                ]
            )
        ],
        config=types.GenerateContentConfig(temperature=0.9),
    )
    if not result:
        return None

    result = result.strip()
    lines = result.split("\n", 1)
    detected = "OUI" in lines[0].upper()
    comment = lines[1].strip() if len(lines) > 1 and detected else None
    logger.info(f"🎤 [VOCAL PATROL] Gemini Audio → detected={detected}, comment='{comment}'")
    return (detected, comment)


@tasks.loop(seconds=30)
async def vocal_patrol_loop():
    """Boucle de surveillance vocale - Écoute 15s toutes les 30s."""
    global vocal_patrol_active, vocal_patrol_channel, vocal_patrol_text_channel, soundboard_streaks
    
    if not vocal_patrol_active or not vocal_patrol_channel:
        return
    
    vc = bot.voice_clients[0] if bot.voice_clients else None
    if not vc or not vc.is_connected():
        vocal_patrol_active = False
        logger.warning("[VOCAL PATROL] Déconnecté du vocal, arrêt de la patrouille")
        return
    
    # Vérifier qu'il y a des gens dans le canal (hors bots)
    human_members = [m for m in vocal_patrol_channel.members if not m.bot]
    if not human_members:
        logger.info("[VOCAL PATROL] Aucun humain dans le canal, pause...")
        return
    
    logger.info(f"🎤 [VOCAL PATROL] Écoute de {vocal_patrol_channel.name} pendant 15s...")
    
    # Créer le sink et écouter
    sink = VocalPatrolSink()
    try:
        vc.listen(sink)
        await asyncio.sleep(15)  # Écouter 15 secondes
        vc.stop_listening()
    except Exception as e:
        logger.error(f"❌ [VOCAL PATROL] Erreur écoute: {e}")
        try:
            vc.stop_listening()
        except Exception:
            pass  # on est deja dans la gestion d'erreur ; l'arret d'ecoute peut echouer sans consequence
        return
    
    # Récupérer le WAV combiné
    wav_data = sink.get_combined_wav()
    active_users = sink.get_active_users()
    sink.reset()
    
    if not wav_data or not active_users:
        logger.info("[VOCAL PATROL] Silence ou données insuffisantes")
        return
    
    # Analyser avec Gemini (inclure les noms des utilisateurs actifs)
    user_names_list = [u[1] for u in active_users]
    analysis = await analyze_audio_with_gemini(wav_data, user_names=user_names_list)
    
    if analysis is None:
        return  # Erreur API, on réessaie au prochain cycle
    
    is_singing, ai_comment = analysis
    
    if is_singing:
        logger.info(f"🎵 [VOCAL PATROL] CHANT/SOUNDBOARD DÉTECTÉ ! Utilisateurs actifs: {user_names_list}")
        
        # 1. COMMENTAIRE POUR TOUS → taverne-des-bots
        # Trouver le canal taverne-des-bots
        taverne_channel = None
        if vocal_patrol_channel and vocal_patrol_channel.guild:
            for ch in vocal_patrol_channel.guild.text_channels:
                if "taverne" in ch.name.lower() and "bot" in ch.name.lower():
                    taverne_channel = ch
                    break
        
        # Poster le commentaire sarcastique dans taverne-des-bots
        if ai_comment:
            comment_msg = f"🤵 {ai_comment}"
        else:
            # Fallback si Gemini n'a pas généré de commentaire
            users_str = ", ".join(user_names_list)
            comment_msg = random.choice(VOCAL_SANCTION_MESSAGES).format(user=users_str)
        
        target_channel = taverne_channel or vocal_patrol_text_channel
        if target_channel:
            await target_channel.send(comment_msg)
            logger.info(f"💬 [VOCAL PATROL] Commentaire posté dans #{target_channel.name}")
        
        # 2. SANCTIONS → cendrillon13 UNIQUEMENT
        # 2. SANCTIONS → cendrillon13 UNIQUEMENT
        for user_id, user_name in active_users:
            if user_name.lower() != VOCAL_PATROL_TARGET.lower():
                continue
            
            # Incrémenter STREAK au lieu de warnings cumulatifs
            if user_id not in soundboard_streaks:
                soundboard_streaks[user_id] = 0
            
            # On incrémente le streak
            soundboard_streaks[user_id] += 1
            warning_count = soundboard_streaks[user_id]
            
            # Log
            logger.info(f"🚨 [STREAK] {user_name} : Streak {warning_count}/3")
            
            member = vocal_patrol_channel.guild.get_member(user_id)
            if not member or member.bot:
                continue

            try:
                duration_minutes = 0
                
                # Déterminer la durée et le niveau de sanction
                # Déterminer la durée et le niveau de sanction
                if warning_count < 3:
                    duration_minutes = 0
                    logger.info(f"⚠️ [STREAK] {user_name} - Avertissement {warning_count}/3")
                    if target_channel:
                        await target_channel.send(f"🤵 {member.mention} : Attention. Soundboard/Chant détecté. ({warning_count}/3 avant sanction)")
                
                elif warning_count == 3:
                    duration_minutes = 5
                    logger.info(f"⏱️ [SANCTION] {user_name} - STREAK 3/3 ATTEINT (5min)")
                    if target_channel:
                        await target_channel.send(f"🤵 {member.mention} : **3ème infraction d'affilée.** La patience a des limites. Isolation vocale. (5 min)")

                else:
                    duration_minutes = 10
                    logger.info(f"⏱️ [SANCTION] {user_name} - STREAK > 3 (10min + Cave)")
                
                # APPLIQUER LES SANCTIONS PHYSIQUES (Si duration > 0)
                if duration_minutes > 0:
                    # 1. Timeout Discord
                    await member.timeout(timedelta(minutes=duration_minutes), reason="Sanction Alfred : Chant/Soundboard")
                    
                    # 2. Sauvegarder l'état actuel si pas déjà sanctionnée
                    if user_id not in active_sanctions:
                        active_sanctions[user_id] = {
                            "original_nick": member.display_name,
                            "task": None
                        }
                    
                    # Annuler la tâche de restauration précédente si elle existe (pour prolonger)
                    if active_sanctions[user_id]["task"]:
                        active_sanctions[user_id]["task"].cancel()
                    
                    # 3. Renommage (Toujours)
                    try:
                        if member.display_name != SANCTION_NICKNAME:
                            await member.edit(nick=SANCTION_NICKNAME, reason="Sanction Alfred")
                    except Exception as e:
                        logger.debug(f"[SANCTION] renommage impossible : {e}")
                    
                    # 4. Rôle de la Honte (Dès niveau 3+)
                    if warning_count >= 3:
                        role = discord.utils.get(member.guild.roles, name=SANCTION_ROLE_NAME)
                        if not role:
                            try:
                                role = await member.guild.create_role(name=SANCTION_ROLE_NAME, color=discord.Color.dark_gold(), reason="Pour les mauvais chanteurs")
                            except Exception: role = None
                        
                        if role and role not in member.roles:
                            await member.add_roles(role, reason="Sanction Alfred")
                    
                    # 5. La Cave (Niveau 4+)
                    if warning_count >= 4:
                        cave_name = "La Cave des Casseroles"
                        # Créer ou trouver la cave
                        cave_channel = discord.utils.get(member.guild.voice_channels, name=cave_name)
                        if not cave_channel:
                            try:
                                cave_channel = await member.guild.create_voice_channel(cave_name, reason="Sanction Alfred")
                            except Exception: cave_channel = None
                        
                        # Déplacer
                        if cave_channel:
                             try:
                                await member.move_to(cave_channel, reason="Exil pour crimes musicaux majeurs")
                             except Exception as e:
                                 logger.debug(f"[SANCTION] deplacement en cave impossible : {e}")
                        
                        if target_channel:
                            await target_channel.send(
                                f"🤵 🚨 **ALERTE ROUGE** 🚨\n"
                                f"{member.mention} a dépassé les bornes. Elle est **bannie** dans **{cave_name}** pour réfléchir à ses crimes.\n"
                                f"**10 minutes** de réclusion à la Cave. Pseudo ridicule imposé. 🚪🔒"
                            )

                    # 6. Planifier la restauration automatique
                    async def restore_task(mem, dur):
                        await asyncio.sleep(dur * 60)
                        await remove_sanctions(mem)
                        
                    task = asyncio.create_task(restore_task(member, duration_minutes))
                    active_sanctions[user_id]["task"] = task

            except discord.Forbidden:
                logger.warning(f"⚠️ [VOCAL PATROL] Pas de permission pour sanctionner {user_name}")
            except Exception as e:
                logger.error(f"❌ [VOCAL PATROL] Erreur sanction: {e}")
    else:
        logger.info("[VOCAL PATROL] Pas de chant détecté ✅")
        
        # RESET STREAK pour Cendrillon si elle a parlé normalement
        # (Si elle est dans active_users MAIS is_singing est False)
        # Note: active_users contient tous ceux qui ont émis du son.
        # Si c'était de la parole normale, on reset.
        if active_users:
            for user_id, user_name in active_users:
                if user_name.lower() == VOCAL_PATROL_TARGET.lower():
                    if user_id in soundboard_streaks and soundboard_streaks[user_id] > 0:
                        soundboard_streaks[user_id] = 0
                        logger.info(f"♻️ [STREAK RESET] {user_name} a parlé normalement. Streak remis à 0.")


@bot.command(name="surveille")
async def surveille(ctx):
    """Alfred rejoint le vocal et surveille le chant. Usage: !surveille"""
    global vocal_patrol_active, vocal_patrol_channel, vocal_patrol_text_channel, singing_warnings
    
    if not ctx.author.voice:
        return await ctx.send("🤵 **Alfred** : Vous n'êtes pas en vocal, Monsieur. Où voulez-vous que je monte la garde ? 🧐")
    
    if vocal_patrol_active:
        return await ctx.send("🤵 **Alfred** : Je suis déjà en patrouille, Monsieur. Un seul poste suffit. ☕")
    
    channel = ctx.author.voice.channel
    vc = ctx.voice_client
    
    if not vc:
        try:
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
        except Exception as e:
            return await ctx.send(f"🤵 **Alfred** : Impossible de rejoindre le salon vocal. ({e}) 😔")
    elif vc.channel != channel:
        await vc.move_to(channel)
    
    vocal_patrol_active = True
    vocal_patrol_channel = channel
    vocal_patrol_text_channel = ctx.channel
    singing_warnings.clear()  # Reset les avertissements
    
    if not vocal_patrol_loop.is_running():
        vocal_patrol_loop.start()
    
    await ctx.send(
        f"🤵 **Alfred** : Très bien. Je monte la garde dans **{channel.name}**. "
        f"Que quiconque ose chanter en subisse les conséquences. 🦇\n"
        f"*Surveillance active — Analyse audio via Gemini toutes les 30 secondes.*"
    )
    logger.info(f"🎤 [VOCAL PATROL] Surveillance activée dans #{channel.name}")


@bot.command(name="repos")
async def repos(ctx):
    """Alfred arrête la surveillance et quitte le vocal. Usage: !repos"""
    global vocal_patrol_active, vocal_patrol_channel, vocal_patrol_text_channel
    
    if not vocal_patrol_active:
        return await ctx.send("🤵 **Alfred** : Je ne suis pas en service de surveillance, Monsieur. 🧐")
    
    vocal_patrol_active = False
    vocal_patrol_channel = None
    vocal_patrol_text_channel = None
    
    if vocal_patrol_loop.is_running():
        vocal_patrol_loop.stop()
    
    # Déconnexion
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    
    await ctx.send("🤵 **Alfred** : La surveillance est terminée. Le silence est restauré. ☕")
    logger.info("[VOCAL PATROL] Surveillance désactivée")

@bot.command(name="liberation")
async def liberation(ctx, member: discord.Member = None):
    """(Admin) Lève toutes les sanctions d'un utilisateur. Usage: !liberation @pseudo"""
    # Vérif perms ou owner
    if not ctx.author.guild_permissions.administrator and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("🤵 Seul Monsieur Wayne (ou un admin) peut ordonner une libération.")
    
    if not member:
        # Essayer de trouver une cible par défaut (active_sanctions)
        if active_sanctions:
            uid = list(active_sanctions.keys())[0]
            member = ctx.guild.get_member(uid)
    
    if not member:
        return await ctx.send("🤵 Qui dois-je libérer, Monsieur ? (`!liberation @pseudo`)")

    await remove_sanctions(member)
    
    # Reset warnings
    if member.id in singing_warnings:
        del singing_warnings[member.id]
        
    await ctx.send(f"🤵 **Libération Accordée**. Les sanctions de {member.mention} sont levées. Son casier est vierge. 🕊️")


async def remove_sanctions(member):
    """Retire timeout, rôle, et restaure le pseudo."""
    user_id = member.id
    
    # 1. Retirer Timeout
    try:
        await member.timeout(None, reason="Libération Alfred")
    except Exception as e:
        logger.warning(f"[SANCTION] retrait du timeout impossible : {e}")
    
    # 2. Retirer Rôle
    role = discord.utils.get(member.guild.roles, name=SANCTION_ROLE_NAME)
    if role and role in member.roles:
        try:
            await member.remove_roles(role, reason="Libération Alfred")
        except Exception as e:
            logger.warning(f"[SANCTION] retrait du role de la honte impossible : {e}")
            
    # 3. Restaurer Pseudo
    if user_id in active_sanctions:
        data = active_sanctions.pop(user_id)
        original = data["original_nick"]
        task = data["task"]
        if task: task.cancel()
        
        try:
            if original and member.display_name != original:
                await member.edit(nick=original, reason="Libération Alfred")
        except Exception as e:
            logger.warning(f"[SANCTION] restauration du pseudo impossible : {e}")
    else:
        # Fallback si pas en mémoire (reset nickname)
        try:
            if member.display_name == SANCTION_NICKNAME:
                await member.edit(nick=None, reason="Libération Alfred")
        except Exception as e:
            logger.warning(f"[SANCTION] restauration du pseudo impossible : {e}")


@bot.command(name="nettoyage")
async def nettoyage(ctx, limit: int = 100):
    """(Admin) Supprime les messages récents."""
    # Vérification admin
    if not ctx.author.guild_permissions.administrator and ctx.author.id != ctx.guild.owner_id:
        return await ctx.send("🤵 **Alfred** : Seuls les Administrateurs peuvent utiliser cette commande. 🧤")
    await do_cleanup(ctx.channel, limit, bots_only=False)

@bot.command(name="oubliemoi")
async def oubliemoi(ctx):
    """Purge toutes les données de mémoire de l'utilisateur."""
    uid = str(ctx.author.id)
    
    # Purge Daily Memory
    if "users" in daily_memory.memory and uid in daily_memory.memory["users"]:
        del daily_memory.memory["users"][uid]
    
    if "conversations" in daily_memory.memory:
        daily_memory.memory["conversations"] = [
            c for c in daily_memory.memory["conversations"]
            if c.get("user_id") != uid
        ]
    daily_memory.save_memory()
    
    # Purge Fact Memory
    if uid in fact_memory.facts:
        del fact_memory.facts[uid]
        fact_memory.save_facts()
        
    await ctx.send("🤵 **Alfred** : C'est fait, Monsieur. J'ai effacé chaque bribe de nos échanges de mes registres. Vous revoilà un parfait étranger à mes yeux. ☕")

async def do_cleanup(channel, limit=100, bots_only=False):
    """Supprime les messages d'un canal.
    
    Args:
        channel: Le canal à nettoyer
        limit: Nombre max de messages à supprimer (max 100 par sécurité Discord)
        bots_only: Si True, ne supprime que les messages de bots
    """
    # Discord limite à 100 messages par purge, et messages < 14 jours
    limit = min(limit, 100)
    
    await channel.send("🧹 **Alfred** : Je nettoie le désordre, Monsieur. Veuillez patienter...")
    
    try:
        if bots_only:
            def is_bot(m): return m.author.bot or m.content.startswith(("!", "/", "-"))
            deleted = await channel.purge(limit=limit, check=is_bot)
            msg = await channel.send(f"🧹 **Alfred** : {len(deleted)} messages de robots ont été aspirés. ✨")
        else:
            deleted = await channel.purge(limit=limit)
            msg = await channel.send(f"🧹 **Alfred** : {len(deleted)} messages ont été effacés. Le salon est impeccable. ✨")
        
        await asyncio.sleep(4)
        try: await msg.delete()
        except discord.HTTPException as e:
            logger.debug(f"[MENAGE] message de confirmation deja disparu : {e}")
        
    except discord.Forbidden:
        await channel.send("🤵 **Alfred** : Je n'ai pas les permissions nécessaires pour supprimer ces messages. 🧤")
    except discord.HTTPException as e:
        if "14 days" in str(e) or "older than" in str(e):
            await channel.send("🤵 **Alfred** : Discord ne permet pas de supprimer les messages de plus de 14 jours en masse. 📜")
        else:
            await channel.send(f"🤵 **Alfred** : Une erreur est survenue. ({e}) 😔")


# Noms des AUTRES bots du serveur : si l'échange leur est visiblement adressé, on ne s'incruste
# PAS lors d'une intervention ALÉATOIRE (les mentions/nom direct du bot restent prioritaires).
OTHER_BOT_NAMES = ["sheo", "sheogorath", "johnny", "silverhand", "samurai", "silverbot", "sugar", "sugar bot", "m'aiq", "maiq", "malena", "malèna"]

async def _other_bot_in_focus(message):
    """True si la conversation est manifestement tournée vers un AUTRE bot."""
    if any(n in message.content.lower() for n in OTHER_BOT_NAMES):
        return True
    try:
        async for prev in message.channel.history(limit=4, before=message):
            if prev.author == bot.user:
                return False   # ce bot était déjà dans la boucle → ok d'enchaîner
            if prev.author.bot:
                return True    # un autre bot vient de parler → c'est SON échange
            if any(n in prev.content.lower() for n in OTHER_BOT_NAMES):
                return True    # un humain vient de nommer un autre bot
    except Exception:
        return False
    return False

@bot.event
async def on_message(message):
    # 0. Anti-Self
    if message.author.id == bot.user.id:
        return

    # IGNORER SES PROPRES IMPOSTEURS (Webhooks nommés Alfred)
    if message.webhook_id and any(n in message.author.display_name.lower() for n in ["alfred", "pennyworth"]):
        return
        
    # SILENCE STREAM (Canal ignoré)
    if is_ignored_channel(message.channel):
        return
    
    # PROCESS STANDARD COMMANDS (1 seul appel pour tout on_message)
    await bot.process_commands(message)

    # Un message qui est une commande de CE bot a deja produit sa reponse :
    # il ne doit pas repartir dans le chemin LLM (bavardage aleatoire compris).
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # Vérification mode maintenance AVANT toute logique LLM
    if DATABASE_AVAILABLE and is_maintenance_mode():
        return

    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    if message.author.bot:
        return

    atts = []

    # 1. ANALYSE
    text_lower = message.content.lower()
    is_mentioned = bot.user.mentioned_in(message)
    is_reply = (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user)
    
    # 🚫 RESPECT DES MENTIONS : Si d'autres sont mentionnés et PAS moi, je me tais.
    if message.mentions and not is_mentioned:
        return

    # DETECTION DU NOM SANS @ (alfred, majordome, pennyworth)
    is_name_mentioned = any(name in text_lower for name in ["alfred", "majordome", "pennyworth"])
    is_bot_talking = message.author.bot
    
    # Check Memory
    user_context = alfred_brain.get_user_context(message.author.id, message.content or "")

    # VOCABULAIRE & TRIGGERS
    keywords_service = ["thé", "alfred", "majordome", "servir", "nettoyer", "dîner", "batman", "wayne", "aide", "soins", "merci"]
    keywords_chaos = ["chaos", "bruit", "merde", "putain", "connard", "bordel", "tue", "sang"]
    # NETTOYAGE - Plus de synonymes
    keywords_clean = ["supprimer", "nettoyer", "effacer", "retirer", "clean", "delete", "efface", "supprime", "vire", "dégage"]
    keywords_target = ["bot", "message", "robot", "conversation", "chat", "historique", "tout", "ça", "ceci", "messages"]
    
    has_service_keyword = any(re.search(rf"\b{word}\b", text_lower) for word in keywords_service)
    has_chaos_keyword = any(re.search(rf"\b{word}\b", text_lower) for word in keywords_chaos)
    has_clean_request = any(k in text_lower for k in keywords_clean) and any(k in text_lower for k in keywords_target)
    is_shouting = message.content.isupper() and len(message.content) > 10
    
    # EARLY IMAGE DETECTION (for priority trigger)
    has_image_early = classify_request(message.content, message.attachments, silent=True)["has_image"]
    
    # 2. LOGIQUE DE REACTION
    should_respond = False
    context_prefix = ""

    # A. Si on l'appelle directement (Priorité Absolue) - @ OU nom prononcé
    if is_mentioned or is_reply or is_name_mentioned:
        
        # -----------------------------------------------------------
        # COMMANDES NATURELLES (Interprétation des intentions)
        # -----------------------------------------------------------
        ctx = await bot.get_context(message)
        
        # 1. ORDONNER LE REPOS / DÉPART
        # Ex: "Alfred, tu peux partir", "Alfred repos", "Arrête de surveiller"
        stop_keywords = ["pars", "partir", "repos", "stop", "arrête", "arrete", "suffit", "dégage", "quitte", "t'en aller"]
        if any(w in text_lower for w in stop_keywords):
            # On vérifie si c'est pertinent (pas juste "arrête de parler")
            # Si le mot "vocal", "surveillance", "ici" ou juste "repos" est présent
            if any(w in text_lower for w in ["vocal", "surveillance", "ici", "maintenant", "tout", "t'en", "la"]) or "repos" in text_lower:
                await repos(ctx)
                return

        # 2. ORDONNER LA SURVEILLANCE / VENUE
        # Ex: "Alfred viens dans le vocal", "Rejoins nous", "Surveille ce canal"
        join_keywords = ["viens", "vien", "rejoins", "rejoint", "surveille", "monte la garde", "écouter", "débarque", "ramène"]
        if any(w in text_lower for w in join_keywords):
            await surveille(ctx)
            return

        # 3. ORDONNER UNE LIBÉRATION / PARDON
        # Ex: "Alfred pardonne à Malena", "Libère Cendrillon", "Excuse le"
        pardon_keywords = ["pardon", "libère", "libere", "excuse", "amnistie", "relâche", "relache", "gracie"]
        if any(w in text_lower for w in pardon_keywords):
            target_member = None
            
            # A. Par mention explicite (@Cendrillon)
            if message.mentions:
                target_member = message.mentions[0]
                
            # B. Par recherche de nom dans le texte (si pas de mention)
            else:
                text_lower.split()
                
                # On parcourt tous les membres pour trouver une correspondance dans le message
                for member in message.guild.members:
                    if member.bot and member.id != 1326418822605176832: # On ignore les bots sauf si c'est une cible spécifique (ID Malena par ex?) non, général.
                        pass # On traite les bots comme des membres pour le pardon (ex: Malena)
                        
                    # Si le pseudo ou le nom est présent dans le message
                    # On cherche des correspondances de plus de 3 lettres pour éviter les faux positifs
                    if (len(member.display_name) > 3 and member.display_name.lower() in text_lower) or \
                       (len(member.name) > 3 and member.name.lower() in text_lower):
                        target_member = member
                        break
            
            if target_member:
                await liberation(ctx, target_member)
                return
        
        # -----------------------------------------------------------
        # FIN COMMANDES NATURELLES
        # -----------------------------------------------------------

        # COMMANDE DE NETTOYAGE (Admin/Owner seulement)
        if has_clean_request:
            # Vérification des permissions
            is_admin = message.author.guild_permissions.administrator
            is_owner = message.author.id == message.guild.owner_id
            
            if is_admin or is_owner:
                await do_cleanup(message.channel, limit=100, bots_only=False)
                return
            else:
                await message.channel.send("🤵 **Alfred** : Mes excuses, mais seuls le Maître et ses lieutenants (Administrateurs) peuvent me donner de tels ordres. 🧤")
                return

        should_respond = True
        context_prefix = f"{user_context} (Il vous parle directement)."

    # C. Si Chaos détecté (Proactivité "Ordre") — sauf si l'échange vise un AUTRE bot
    elif not has_image_early and (has_chaos_keyword or is_shouting) and random.random() < 0.15:
        if await _other_bot_in_focus(message):
            logger.info("[ANTI-INCRUSTATION] Chaos dans un échange adressé à un autre bot → Alfred s'abstient.")
        else:
            should_respond = True
            context_prefix = "CONTEXTE: L'utilisateur est vulgaire ou crie. Rappelle-lui les bonnes manières avec un cynisme glacé."
            print(f"☕ MAINTIEN DE L'ORDRE : Alfred réagit au chaos de {message.author.name}")

    # C.bis DÉTECTION DE CHANT (SANCTION MUSICALE)
    elif not is_bot_talking:
        # Patterns de chant
        singing_emojis = ["🎤", "🎵", "🎶", "🎼", "🎸", "🎹", "🎺", "🎻", "🥁", "🎷"]
        singing_words = [
            "lalala", "lala", "tra la la", "tralala", "nanana", "na na na",
            "oh oh oh", "ohhh", "oooh", "yeahhh", "wooo",
            "♪", "♫", "♬", "🎵", "🎶",
        ]
        singing_phrases = [
            "je chante", "on chante", "chantons", "chanter",
            "karaoke", "karaoké", "couplet", "refrain",
        ]
        
        has_singing_emoji = any(e in message.content for e in singing_emojis)
        has_singing_word = any(w in text_lower for w in singing_words)
        has_singing_phrase = any(p in text_lower for p in singing_phrases)
        has_elongated = bool(re.search(r'(.)\1{4,}', text_lower))  # 5+ fois la même lettre
        # Détection de lignes de paroles (plusieurs lignes courtes)
        has_lyrics_format = message.content.count('\n') >= 2 and all(len(line) < 60 for line in message.content.split('\n') if line.strip())
        
        is_singing = (has_singing_emoji and (has_singing_word or has_elongated)) or \
                     has_singing_phrase or \
                     (has_singing_word and has_elongated) or \
                     (has_lyrics_format and (has_singing_emoji or has_singing_word))
        
        if is_singing:
            if await _other_bot_in_focus(message):
                logger.info("[ANTI-INCRUSTATION] Chant dans un échange adressé à un autre bot → Alfred s'abstient.")
            else:
                should_respond = True
                
                # Messages de sanction (sélection aléatoire)
                sanction_messages = [
                    "🤵 *pose son torchon* Monsieur. Ce que vous faites avec votre voix constitue une infraction au bon goût. Cessez immédiatement. 😒",
                    "🤵 Le chant est interdit dans cette demeure. Si Monsieur souhaite s'exprimer vocalement, qu'il le fasse dans la cave. Seul. 🧐",
                    "🤵 Je dois vous informer que le dernier à avoir chanté ici a été retrouvé dans la Batcave. Avec les chauves-souris. Elles n'ont pas apprécié non plus. 🦇",
                    "🤵 Monsieur... *soupir britannique* C'est censé être de la musique ? Le chat du voisin fait mieux. Et il est sourd. 😒",
                    "🤵 Je me permets de vous rappeler l'Article 7 du Règlement du Manoir : 'Tout chant non autorisé sera sanctionné par un thé froid.' ☕",
                    "🤵 Monsieur Wayne m'a personnellement demandé de vous informer que ce... *bruit*... que vous émettez n'est pas toléré dans cette enceinte. 🧤",
                    "🤵 Si c'est un appel à l'aide déguisé en mélodie, je peux contacter les secours. Sinon, veuillez cesser. 🚑",
                    "🤵 La dernière personne qui a chanté au Manoir Wayne a été confondue avec une alarme incendie. Les pompiers n'étaient pas ravis. 🔥",
                ]
                
                await message.channel.send(random.choice(sanction_messages))
                logger.info(f"🎵 [SANCTION CHANT] Alfred sanctionne {message.author.name} pour avoir chanté !")
                
                # 30% de chance de timeout (1-5 min) si Alfred a la permission
                if random.random() < 0.30:
                    try:
                        timeout_duration = random.randint(60, 300)  # 1 à 5 minutes
                        await message.author.timeout(timedelta(seconds=timeout_duration), reason="Chant non autorisé au Manoir Wayne")
                        timeout_msg = random.choice([
                            f"🤵 {message.author.mention} a été envoyé(e) réfléchir dans la cave pour **{timeout_duration // 60} minute(s)**. Que cela serve de leçon. 🦇",
                            f"🤵 {message.author.mention} est en isolation vocale pour **{timeout_duration // 60} minute(s)**. Le silence est d'or, Monsieur. 🧤",
                            f"🤵 {message.author.mention} a été mis(e) en sourdine pendant **{timeout_duration // 60} minute(s)**. Les oreilles du Manoir vous remercient. ☕",
                        ])
                        await message.channel.send(timeout_msg)
                        logger.info(f"⏱️ [TIMEOUT] {message.author.name} timeout {timeout_duration}s pour chant")
                    except discord.Forbidden:
                        logger.warning(f"⚠️ [TIMEOUT] Pas de permission pour timeout {message.author.name}")
                    except Exception as e:
                        logger.error(f"❌ [TIMEOUT] Erreur: {e}")
                
                return  # On a déjà répondu, pas besoin de passer au LLM

    # D. Si mot-clé service (Oreille indiscrète - 30%)
    elif has_service_keyword and random.random() < 0.30:
        should_respond = True
        context_prefix = f"{user_context} (Vous avez entendu une demande de service)."
        print(f"👂 Alfred a entendu : {message.content}")

    # E. RUMEUR DETECTION (!rumeur from M'aiq)
    elif "📢" in message.content and "[RUMEUR]" in message.content:
        if random.random() < 0.50: # 50% chance
            should_respond = True
            context_prefix = "RUMEUR: M'aiq le Menteur propage une rumeur absurde. Répondez avec un cynisme poli mais total. Doutez de la véracité. Utilisez votre sarcasme britannique."
            print(f"👂 [RUMEUR] Alfred a entendu. (Réaction imminente)")

    # F. VISION (Image Handling)
    # Limite de taille max pour les images (sécurité)
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    image_data = None
    has_image = False
    # Uniquement si Alfred est déjà sollicité (mention/reply/nom/chaos) — pas de
    # commentaire spontané des images postées.
    # L'image d'un message cité n'est récupérée que si on s'adresse à Alfred
    # (pas via la branche chaos) ; sinon attachments du message courant.
    if should_respond:
        atts = (await resolve_media_attachments(message)
                if (is_mentioned or is_reply or is_name_mentioned)
                else message.attachments)
    if atts and should_respond:
        for attachment in atts:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                # Vérification de la taille avant téléchargement
                if attachment.size and attachment.size > MAX_IMAGE_SIZE:
                    logger.warning(f"[SÉCURITÉ] Image trop grande rejetée: {attachment.size / 1024 / 1024:.1f} MB")
                    continue
                has_image = True
                async with aiohttp.ClientSession() as session:
                    async with session.get(attachment.url) as resp:
                         if resp.status == 200:
                             # Double vérification avec content-length
                             content_length = int(resp.headers.get('content-length', 0))
                             if content_length > MAX_IMAGE_SIZE:
                                 logger.warning(f"[SÉCURITÉ] Image content-length trop grand: {content_length / 1024 / 1024:.1f} MB")
                                 continue
                             image_data = await resp.read()
                             context_prefix = "VISION: Le Maître vous montre une image. Analysez-la précisément et commentez avec élégance et sarcasme."
                             logger.info(f"[VISION] Alfred analyse une image de {message.author.name}")
                             break

    if not should_respond:
        return

    # SAVE INTERACTION
    alfred_brain.update_user(message.author.id, message.author.name, topic=message.content[:20]+"...")

    # PREPARATION
    user_message = message.content.replace(f'<@{bot.user.id}>', '').strip()
    if is_bot_talking:
        user_message = f"{context_prefix} L'autre a dit : '{user_message}'. Réponds-lui poliment mais fermement."
    
    # Add vision context if image present
    if has_image:
        if not user_message.strip():
            user_message = "(Le Maître vous présente une image sans commentaire.)"
        user_message += "\n[INSTRUCTION VISION] : Analysez l'image attentivement. Décrivez brièvement ce que vous voyez, puis commentez avec votre sarcasme britannique habituel. Soyez précis sur CE QUE vous voyez."

    # HISTORY (Mémoire Court Terme)
    channel_id = message.channel.id
    if channel_id not in conversation_history: conversation_history[channel_id] = []
    
    conversation_history[channel_id].append({"role": "user", "parts": [f"{message.author.name}: {user_message}"]})
    if len(conversation_history[channel_id]) > MAX_HISTORY:
        conversation_history[channel_id] = conversation_history[channel_id][-MAX_HISTORY:]

    # TRANSCRIPT AVANCÉ
    transcript = "CONTEXTE DU SALON (Ordre Chronologique) :\n"
    active_mortals = set()
    _chrono = Chrono("alfred", message.channel.id)
    messages_list = []
    async for hist_msg in message.channel.history(limit=10):
        messages_list.append(hist_msg)
        if not hist_msg.author.bot:
            active_mortals.add(hist_msg.author.name)

    # Reverse to get Chronological Order (Oldest -> Newest)
    for hist_msg in reversed(messages_list):
        ligne = ligne_de_contexte(hist_msg, bot.user, avec_mention=True)
        if ligne:
            transcript += ligne
    
    # ═══ SMART ROUTER — Classification du message ═══
    _addressed = bool(is_mentioned or is_reply or is_name_mentioned)
    routing = classify_request(user_message, atts, addressed=_addressed)
    
    # Téléchargements Médias AVANCÉS
    mime_type = "image/jpeg"
    media_data = None
    if routing["has_image"] and routing["image_attachment"]:
        media_data, mime_type = await download_media(routing["image_attachment"])
        if not media_data:
            routing["type"] = RequestType.TEXT
    elif routing["has_audio"] and routing["audio_attachment"]:
        media_data, mime_type = await download_media(routing["audio_attachment"])
        if not media_data:
            routing["type"] = RequestType.TEXT

    has_image = routing["has_image"] and media_data is not None
    has_audio = routing["has_audio"] and media_data is not None

    # INJECTIONS SYSTEMATIQUE
    transcript += f"\n[VOTRE ACTIVITÉ ACTUELLE] : Vous êtes occupé à : '{current_alfred_activity}'."
    if active_mortals:
        transcript += f"\n[PERSONNES PRÉSENTES DANS LA PIÈCE] : {', '.join(active_mortals)}"

    # ANTI-REPETITION INJECTION (NEW!)
    recent_responses = response_memory.get_recent(message.guild.id)
    anti_repeat_prompt = ""
    if recent_responses:
        recent_snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        anti_repeat_prompt = "\n\n[ANTI-RÉPÉTITION] Vous avez déjà dit récemment :\n"
        for i, snippet in enumerate(recent_snippets, 1):
            anti_repeat_prompt += f"{i}. \"{snippet}\"\n"
        anti_repeat_prompt += "Évitez de vous répéter. Un bon majordome est toujours original."

    # ANTI-TICS : les amorces/clôtures/mots récurrents des dernières répliques, interdits
    # nommément. L'anti-répétition ci-dessus cite des phrases ; celui-ci vise le MOULE.
    # ⚠️ TOUT ce que les mortels ont dit, pas seulement le dernier message : sinon
    # le filet interdit le SUJET de la conversation des qu'on cesse de le renommer.
    _mots_des_mortels = [m.content for m in messages_list if not m.author.bot and m.content]
    _consigne_anti_tic = build_anti_tic_consigne(recent_responses, message_utilisateur=_mots_des_mortels)
    anti_tic = f"\n\n{_consigne_anti_tic}" if _consigne_anti_tic else ""

    try:
        from core.repartee_lessons import detect_defeat_signal, reflect_on_defeat, format_for_prompt
        
        bloc_lecons = format_for_prompt("Alfred")
        if bloc_lecons:
            anti_tic += bloc_lecons
            
        motif_defaite = detect_defeat_signal(user_message)
        if motif_defaite and recent_responses:
            asyncio.create_task(
                reflect_on_defeat(
                    bot_id="Alfred",
                    guild_id=str(message.guild.id) if message.guild else "DM",
                    categorie=motif_defaite,
                    repliques=recent_responses,
                    fournisseur="gemini",
                    key_manager=key_manager,
                    bot_label="Alfred",
                    modele=GEMINI_FLASH,
                    timeout=15,
                    fabrique=lambda cle: get_safe_genai_client(api_key=cle),
                    methode="models.generate_content",
                    model=GEMINI_FLASH,
                )
            )
    except ImportError as e:
        logger.warning(f"carnet de repartie indisponible : {e}")

    def _get_meme_addition():
        chan_id = message.channel.id
        consigne = build_meme_consigne(message.content or "", set(meme_recent[chan_id]))
        if consigne:
            import re as _re
            m = _re.search(r"« (.+?) »", consigne)
            if m:
                meme_recent[chan_id].append(m.group(1))
        return consigne

    final_system_prompt = f"SYSTEM: {PERSONALITY_PROMPT}\n{user_context}\n{transcript}{anti_repeat_prompt}{anti_tic}{_get_meme_addition()}"
    
    # GENERATION
    response_text = None
    
    async with message.channel.typing():
        _chrono.etape("contexte")
        cascade = get_model_cascade(routing["type"], "alfred")
        
        for client_type, model_name in cascade:
            _depart = time.perf_counter()
            _code_erreur = None
            _raison = None
            api_key = None
            try:
                # 1. GEMINI
                if client_type == "gemini":
                    api_key, _saut = _cle_du_pool(key_manager, "gemini", exigee=True)
                    if _saut:
                        _raison = _saut
                        continue
                    client = get_safe_genai_client(api_key=api_key, http_options={'api_version': 'v1beta'})
                    
                    last_turn_parts = [types.Part(text=f"{final_system_prompt}\n\nDernier message : {user_message}")]
                    if media_data:
                        last_turn_parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_data)))
                    gemini_messages = [types.Content(role="user", parts=last_turn_parts)]

                    # Gemini Call
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            contents=gemini_messages,
                            config=types.GenerateContentConfig(
                                temperature=0.6,
                                tools=ALFRED_TOOLS_DEFINITION
                            )
                        ),
                        timeout=45 if media_data else 15
                    )
                    
                    # Handling Tool Calls
                    if resp.candidates[0].content.parts and resp.candidates[0].content.parts[0].function_call:
                        fc = resp.candidates[0].content.parts[0].function_call
                        tool_name = fc.name
                        args = fc.args
                        
                        logger.info(f"🛠️ [IA AGENT] Alfred appelle l'outil : {tool_name}")
                        
                        tool_result = "Action impossible."
                        if tool_name == "set_maintenance":
                            tool_result = tool_set_maintenance(args["status"])
                        elif tool_name == "get_user_stats":
                            tool_result = await tool_get_user_stats(args["user_id"])
                        
                        # Feedback loop
                        gemini_messages.append(resp.candidates[0].content) # Model Call
                        gemini_messages.append(types.Content(
                            role="user",
                            parts=[types.Part(function_response=types.FunctionResponse(name=tool_name, response={"result": tool_result}))]
                        ))
                        
                        resp = await asyncio.wait_for(
                            asyncio.to_thread(
                                client.models.generate_content,
                                model=model_name, contents=gemini_messages,
                                config=types.GenerateContentConfig(
                                    temperature=0.5,
                                    tools=ALFRED_TOOLS_DEFINITION
                                )
                            ),
                            timeout=45 if media_data else 15
                        )

                    response_text = resp.text
                    logger.info(f"✅ [GEMINI {model_name}] Alfred via {routing['reason']}.")
                    break

                # 1.bis OLLAMA (Moondream)
                elif client_type == "ollama":
                    if routing["type"] == RequestType.IMAGE and routing["image_attachment"]:
                        response_text = await process_image_ollama(
                            attachment=routing["image_attachment"],
                            personality_prompt=final_system_prompt,
                            user_message=user_message
                        )
                        if response_text:
                            logger.info(f"✅ [OLLAMA {model_name}] Alfred a utilisé Moondream local !")
                            break
                        continue
                    else:
                        continue

                # 2. MISTRAL
                elif client_type == "mistral" and mistral_client:
                    api_key, _saut = _cle_du_pool(key_manager, "mistral")
                    if _saut:
                        _raison = _saut
                        continue
                    chat = await asyncio.wait_for(
                        asyncio.to_thread(
                            mistral_client.chat.complete,
                            model=model_name,
                            messages=[
                                {"role": "system", "content": final_system_prompt},
                                {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\nLAST MSG: {user_message}"}
                            ]
                        ),
                        timeout=15  # borne TEXTE : ce client ne transporte pas le media
                    )
                    response_text = chat.choices[0].message.content
                    logger.info(f"🎩 [MISTRAL {model_name}] Alfred a servi une réponse.")
                    break

                # 4. GROQ
                elif client_type == "groq" and groq_client:
                    api_key, _saut = _cle_du_pool(key_manager, "groq")
                    if _saut:
                        _raison = _saut
                        continue
                    msgs = [{"role": "system", "content": final_system_prompt}]
                    for msg in conversation_history[channel_id]:
                        r = "user" if msg["role"] == "user" else "assistant"
                        msgs.append({"role": r, "content": msg["parts"][0]})
                    msgs.append({"role": "user", "content": user_message})
                    
                    chat = await asyncio.wait_for(
                        asyncio.to_thread(
                            groq_client.chat.completions.create,
                            messages=msgs, model=model_name, temperature=0.6,
                            **groq_kwargs(model_name),
                        ),
                        timeout=15  # borne TEXTE : ce client ne transporte pas le media
                    )
                    response_text = chat.choices[0].message.content
                    logger.info(f"⚡ [GROQ {model_name}] Alfred a répondu.")
                    break

                # 5. NVIDIA — 4e fournisseur, quota independant des trois autres.
                # ⚠️ Ajoute le 2026-09-05. Le lot NVIDIA du 04/09 n'avait cable que
                # shared/llm_cascade.py et ses copies vendorisees : cette cascade-ci est
                # INLINE, l'echelon `nvidia` y tombait donc dans le vide a chaque fois.
                elif client_type == "nvidia" and nvidia_client:
                    api_key, _saut = _cle_du_pool(key_manager, "nvidia")
                    if _saut:
                        _raison = _saut
                        continue
                    if media_data is not None:
                        logger.warning(f"⚠️ [NVIDIA] Média reçu mais ignoré par {model_name}. Perte silencieuse évitée.")
                    msgs = [{"role": "system", "content": final_system_prompt}]
                    for msg in conversation_history[channel_id]:
                        r = "user" if msg["role"] == "user" else "assistant"
                        msgs.append({"role": r, "content": msg["parts"][0]})
                    msgs.append({"role": "user", "content": user_message})

                    chat = await asyncio.wait_for(
                        asyncio.to_thread(
                            nvidia_client.chat.completions.create,
                            messages=msgs, model=model_name, temperature=0.6,
                            # ⚠️ SANS ceci, nemotron RECOPIE sa pensée dans `content`, et
                            # met six fois plus de temps à le faire.
                            **nvidia_kwargs(model_name),
                        ),
                        timeout=15  # borne TEXTE : ce client ne transporte pas le media
                    )
                    # Filet : `reasoning_effort="none"` n'est pas etanche. Mesure du 2026-09-05,
                    # 12 appels sans lui -> 12 fuites ; avec lui, ~1 sur 20 passe encore.
                    if _fuite_de_raisonnement(chat.choices[0].message):
                        logger.warning(f"⚠️ [NVIDIA {model_name}] raisonnement recopié dans la réponse → échelon suivant")
                        _raison = "fuite_raisonnement"
                        continue
                    response_text = chat.choices[0].message.content
                    if _est_vide(response_text):
                        logger.warning(f"⚠️ [NVIDIA {model_name}] réponse vide → échelon suivant")
                        response_text = None
                        _raison = "vide"
                        continue
                    logger.info(f"🟩 [NVIDIA {model_name}] Alfred a répondu.")
                    break
            except Exception as e:
                error_msg = str(e)
                if not error_msg:
                    error_msg = type(e).__name__
                logger.warning(f"⚠️ [{client_type.upper()} FAIL] {model_name} : {error_msg}")
                # ⚠️ Réservé à Gemini jusqu'au 2026-09-06 : Groq, Mistral et NVIDIA prenaient
                # un 429 sans jamais écarter la clé. `report_error` est inerte si le pool lui
                # est inconnu, et `delai_de_reprise` lit désormais AUSSI l'en-tête retry-after.
                if api_key:
                    error_code = getattr(e, 'code', getattr(e, 'status_code', 0))
                    key_manager.report_error(client_type, api_key, error_code,
                                             retry_delay_s=delai_de_reprise(e))
                _raison = type(e).__name__
                _code_erreur = getattr(e, 'code', getattr(e, 'status_code', 0))
                continue
            finally:
                # ⚠️ Cette cascade est une COPIE inline de shared/llm_cascade.py : elle
                # n'heritait pas de son tracage, et alfred etait donc invisible dans
                # data/api_usage.db. Aucune ligne pendant le test live du 04/09.
                _latence = int((time.perf_counter() - _depart) * 1000)
                _succes = bool(response_text)
                if not _succes and _raison is None:
                    _raison = "non_tentee"
                _index_cle = None
                if api_key and hasattr(key_manager, "apis"):
                    try:
                        _index_cle = key_manager.apis[client_type]["keys"].index(api_key)
                    except (ValueError, KeyError, AttributeError, TypeError):
                        pass  # la cle n'est pas dans cette liste : l'index reste None, le tracage suit quand meme
                if not isinstance(_index_cle, int):
                    _index_cle = None   # un faux gestionnaire rend un objet : SQLite le refuserait
                try:
                    tracer_appel(
                        bot="alfred", api=client_type, modele=model_name,
                        index_cle=_index_cle, succes=_succes, code_erreur=_code_erreur,
                        latence_ms=_latence, raison=_raison,
                    )
                except Exception:
                    pass  # le tracage ne doit JAMAIS casser une reponse

    _chrono.etape("llm")

    # ENVOI
    if response_text:
        # CLEAN LLM ARTIFACTS (Mistral/Llama instruction tags, etc.)
        llm_artifacts = ["[INST]", "[/INST]", "</s>", "<s>", "<<SYS>>", "<</SYS>>", "[INST ", " [/INST]"]
        for artifact in llm_artifacts:
            response_text = response_text.replace(artifact, "")
        # Clean internal thought tags
        response_text = re.sub(r"<thought>.*?</thought>", "", response_text, flags=re.DOTALL | re.IGNORECASE)
        response_text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL | re.IGNORECASE)
        response_text = response_text.strip()
        
        # CONVERSION DES MENTIONS TEXTUELLES EN VRAIES MENTIONS DISCORD
        # Le LLM génère parfois <username> ou @username au lieu de <@ID>
        async def convert_text_mentions_to_discord(text, channel):
            """Convertit les mentions textuelles en vraies mentions Discord."""
            result = text
            
            # Collecter les membres du canal pour le mapping nom -> ID
            members_map = {}
            try:
                async for msg in channel.history(limit=50):
                    if msg.author.id not in members_map:
                        members_map[msg.author.name.lower()] = msg.author.id
                        members_map[msg.author.display_name.lower()] = msg.author.id
                        clean_name = re.sub(r'[^a-zA-Z0-9]', '', msg.author.name.lower())
                        if clean_name:
                            members_map[clean_name] = msg.author.id
            except Exception as e:
                logger.warning(f"[MENTION FIX] Erreur collecte membres: {e}")
            
            # Pattern 1: <username> (sans @)
            pattern1 = r'<([^@<>]+)>'
            for match in re.finditer(pattern1, result):
                potential_name = match.group(1).lower().strip()
                if potential_name in members_map:
                    user_id = members_map[potential_name]
                    result = result.replace(match.group(0), f'<@{user_id}>')
                    logger.info(f"[MENTION FIX] '{match.group(0)}' → '<@{user_id}>'")
            
            # Pattern 2: @username (mention textuelle)
            pattern2 = r'@([a-zA-Z0-9_]+)'
            for match in re.finditer(pattern2, result):
                potential_name = match.group(1).lower().strip()
                if potential_name in members_map:
                    user_id = members_map[potential_name]
                    result = result.replace(match.group(0), f'<@{user_id}>')
                    logger.info(f"[MENTION FIX] '{match.group(0)}' → '<@{user_id}>'")
            
            return result
        
        # Appliquer la conversion
        response_text = await convert_text_mentions_to_discord(response_text, message.channel)
        
        if response_text:  # Check if still has content after cleaning
            # LTM - EXTRACTION AND CLEANING OF FACTS
            matches = re.findall(r"<fact>(.*?)</fact>", response_text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                fact_text = match.strip()
                if fact_text:
                    fact_memory.add_fact(message.author.id, fact_text)
                    
            response_text = re.sub(r"<fact>.*?</fact>", "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
            response_text = re.sub(r"<[a-z_-]+>", "", response_text, flags=re.IGNORECASE)
            response_text = re.sub(r"</[a-z_-]+>", "", response_text, flags=re.IGNORECASE).strip()

            await message.channel.send(response_text)
            _chrono.fin(envoye=True)
            conversation_history[channel_id].append({"role": "model", "parts": [response_text]})
            # Track for Anti-Repetition (NEW!)
            response_memory.add(message.guild.id, response_text)
            
            # LTM - Daily interaction logging
            daily_memory.add_interaction(message.author.id, message.author.name, message.content or "", response_text)
            asyncio.create_task(daily_memory.refresh_daily_read(message.author.id, _daily_llm_call))
    else:
        # FALLBACK: If image but no vision API available
        if has_image:
            await message.channel.send("🤵 **Alfred** : Je crains que mes capacités visuelles soient momentanément indisponibles, Monsieur. Veuillez réessayer dans quelques instants. ☕")
            logger.error("[VISION] Échec - Gemini indisponible pour l'image.")
        else:
            logger.error("[ECHEC TOTAL] Aucun modèle n'a répondu.")

if __name__ == "__main__":
    if "VOTRE_TOKEN" in DISCORD_TOKEN:
        logger.error("ERREUR : Vous devez configurer le DISCORD_TOKEN dans bot_alfred.py !")
    else:
        # Un `tasks.loop` rejoue TOUTES les iterations manquees quand l'horloge saute
        # (veille de l'hote) : 40 `MOOD CHANGE` en deux secondes le 2026-09-04.
        installer_anti_rattrapage(logger)
        setup_graceful_shutdown(bot, journal=logger)
        bot.run(DISCORD_TOKEN)
