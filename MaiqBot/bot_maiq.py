
# INJECTION SHARED FOLDER
import sys
import os
import time
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import discord
from discord.ext import commands, tasks
from google import genai
from google.genai import types
from groq import Groq 
from mistralai import Mistral
from openai import OpenAI
import aiohttp
import asyncio
import random
import re
import json
import os
from core.response_memory import ResponseMemory
from core.boucles import installer_anti_rattrapage
import logging
from datetime import datetime
import base64

from core.models import GEMINI_FLASH, GEMINI_FLASH_LITE, GROQ_FAST, MISTRAL_MAIN, groq_kwargs, nvidia_kwargs, NVIDIA_BASE_URL
# ⚠️ La cascade inline de M'aiq n'avait NI garde anti-fuite NI garde de reponse vide :
# les deux vivaient dans le noyau, qu'elle recopie sans les emporter. On les importe au
# lieu d'en faire une 8e copie. `generate_response` etait appele sans etre importe.
from core.llm_cascade import generate_response, _est_vide, _fuite_de_raisonnement
from core.smart_router import classify_request, RequestType, download_media, get_model_cascade, resolve_media_attachments
from core.api_tracking import tracer_appel
from core.media_handler import process_image_ollama
from core.transcript import ligne_de_contexte
from core.chrono import Chrono
try:
    from shared.games import setup_games
    from games_persona import PERSONA
    GAMES_AVAILABLE = True
except ImportError:
    GAMES_AVAILABLE = False

try:
    from shared.memes_fr import build_meme_consigne
    MEMES_AVAILABLE = True
except ImportError:
    MEMES_AVAILABLE = False
    def build_meme_consigne(*a, **k): return ""

import collections
meme_recent = collections.defaultdict(lambda: collections.deque(maxlen=8))  # {channel_id: deque[ref]}

# LOGGING STRUCTURÉ
from core.bot_logger import setup_logger
logger = setup_logger("maiq")

# FILE PATHS
DATA_DIR = os.getenv("DATA_DIR", ".")
DATA_FILE = os.path.join(DATA_DIR, "maiq_data.json")

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"⚠️ Lecture {DATA_FILE} impossible ({e}) — valeurs par défaut.")
    return {"calipers": 0, "fatigue": {"count": 0, "last_msg": 0}}

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning(f"⚠️ Sauvegarde {DATA_FILE} impossible ({e}) — état non persisté.")


# ZONE DE CONFIGURATION : M'AIQ LE MENTEUR

# IMPORT SECURE ENV LOADER (Supports encrypted .env files)
from pathlib import Path
from core.secure_env import load_secure_env
load_secure_env(Path(__file__).parent)

# IMPORT SAFE CLIENT
from core.safe_client import get_client as get_safe_genai_client


# IMPORT DES SYSTÈMES (locaux pour Discloud)

try:
    from shared.shared_database import (
        get_or_create_user, add_reputation, log_interaction,
        is_maintenance_mode, complete_quest, is_ignored_channel, get_active_riddle,
        get_reputation, get_reputation_level, get_next_rank_info, get_user_interactions,
        is_riddle_duplicate, add_to_riddle_history, add_riddle_participant, add_riddle_winner,
        get_riddle_winners, delete_active_riddle, add_riddle_streak,
        reset_riddle_streak, get_all_active_riddles
    )
    from shared.slash_commands import setup_slash_commands, sync_slash_commands
    from shared.server_events import handle_member_join, handle_member_remove, check_and_send_birthdays
    from minigames import check_answer, get_hint, start_tracking_riddle
    DATABASE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ [M'aiq] Modules optionnels non disponibles: {e}")
    DATABASE_AVAILABLE = False

try:
    from shared.twitch_announcer import setup_twitch_announcer
    TWITCH_AVAILABLE = True
except ImportError:
    TWITCH_AVAILABLE = False
    def setup_twitch_announcer(*a, **k): return None

twitch_announcer = None

try:
    from shared.ensure_writable import ensure_data_writable
except ImportError:
    def ensure_data_writable(*args, **kwargs): pass

# CREDENTIALS
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
recent_rumor_targets = {}

# API KEYS ROTATION (Google Gemini)
GEMINI_API_KEYS = [
    os.getenv("GEMINI_KEY_1"), 
    os.getenv("GEMINI_KEY_2"), 
    os.getenv("GEMINI_KEY_3"), 
]
# Filter out None values
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]

# FALLBACK API KEYS
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# MEMORY SETTINGS
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
# ANTI-REPETITION MEMORY (Par Serveur - ENHANCED)
  # {guild_id: ["réponse1", "réponse2", ...]} (max 10)
response_memory = ResponseMemory()

try:
    from shared.discord_profile import DiscordDailyBio
except ImportError:
    DiscordDailyBio = None

try:
    from shared.discord_status import DiscordDailyStatus
except ImportError:
    DiscordDailyStatus = None

from maiq_data import PERSONALITY_PROMPT

# LTM SYSTEM
try:
    from maiq_memory import FactMemory, DailyMemory
except ImportError:
    from MaiqBot.maiq_memory import FactMemory, DailyMemory
maiq_facts_file = os.path.join(DATA_DIR, "maiq_facts.json")
maiq_memory_file = os.path.join(DATA_DIR, "maiq_memory.json")
fact_memory = FactMemory(maiq_facts_file)
daily_memory = DailyMemory(maiq_memory_file)

async def _daily_llm_call(system_prompt, user_message):
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "daily_read"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client, nvidia_client=nvidia_client,
        bot_label="Maiq", temperature=0.5, max_tokens=60)



# ═══════════════════════════════════════════════════════════════
# TOOLS — FONCTIONS D'AGENTS (M'aiq Edition)
# ═══════════════════════════════════════════════════════════════

def tool_set_lie_density(percentage: int):
    """Ajuste le niveau de mensonge de M'aiq (0-100)."""
    # Ici on peut imaginer un réglage global ou local
    # Pour l'instant on se contente de confirmer
    logger.info(f"🤥 [TOOL LIE] Niveau de mensonge ajusté à {percentage}%")
    return f"SUCCÈS : M'aiq mentira désormais à {percentage}% !"

MAIQ_TOOLS_DEFINITION = [
    {
        "function_declarations": [
            {
                "name": "set_lie_density",
                "description": "Ajuste ton envie de mentir aujourd'hui.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "percentage": {"type": "INTEGER", "description": "De 0 (vérité pure) à 100 (mensonge total)."}
                    },
                    "required": ["percentage"]
                }
            }
        ]
    }
]

# INITIALISATION

intents = discord.Intents.default()
intents.message_content = True 

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
        await ctx.send(f"😼 M'aiq ne peut pas deviner ce que tu ne dis pas. Utilise : `{ctx.command.name} {ctx.command.signature}`.")
        return
    logger.error(f"❌ [COMMANDE] {ctx.command} : {error}", exc_info=error)


# Client Initialization (Safe Failover)
groq_client = None
mistral_client = None
try:
    if GROQ_API_KEY:
        groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0)
except Exception as e:
    logger.warning(f"[INIT] Groq: {e}")

try:
    if MISTRAL_API_KEY:
        mistral_client = Mistral(api_key=MISTRAL_API_KEY)
except Exception as e:
    logger.warning(f"[INIT] Mistral: {e}")


# 4e fournisseur : quota independant des 3 autres. `max_retries=0` pour que la
# cascade prenne le relais au lieu que le SDK dorme sur un 429.
nvidia_client = None
if NVIDIA_API_KEY:
    try: nvidia_client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL, max_retries=0)
    except Exception as e: logger.warning(f'[NVIDIA] client indisponible: {e}')

ENABLE_DAILY_BIO = os.getenv("ENABLE_DAILY_BIO", "1") != "0"
daily_bio = DiscordDailyBio(
    bot=bot, bot_id="maiq", bot_label="M'aiq le Menteur",
    personality_prompt=PERSONALITY_PROMPT,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, nvidia_client=nvidia_client,
    logger=logger, enabled=ENABLE_DAILY_BIO,
) if DiscordDailyBio else None

# Statut Discord auto-piloté par la personnalité (jumeau de la bio).
# La liste ci-dessous n'est plus qu'un FALLBACK si le LLM est indisponible.
_STATUS_FALLBACK = [
    ("playing", "Chercher des pinces (Calipers)"),
    ("playing", "Fuir un dragon invisible"),
    ("playing", "Manger du sucre lune"),
    ("playing", "Polir ses mensonges"),
    ("playing", "Courir très vite vers nulle part"),
    ("playing", "Nager jusqu'à Yokuda"),
    ("playing", "Essayer de voler au dessus des nuages"),
    ("playing", "Compter les grains de sable"),
    ("playing", "Éviter Sheogorath"),
    ("playing", "Préparer une rumeur"),
]
ENABLE_DAILY_STATUS = os.getenv("ENABLE_DAILY_STATUS", "1") != "0"
daily_status = DiscordDailyStatus(
    bot=bot, bot_id="maiq", bot_label="M'aiq le Menteur",
    personality_prompt=PERSONALITY_PROMPT, fallback_activities=_STATUS_FALLBACK,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, nvidia_client=nvidia_client,
    logger=logger, enabled=ENABLE_DAILY_STATUS,
) if DiscordDailyStatus else None


# EVENTS

@bot.event
async def on_ready():
    # MODE TEST (dashboard) — garde de publication + remontee des serveurs pour le
    # menu deroulant. Optionnel : sans shared/, le bot publie normalement.
    try:
        from shared.test_mode import installer_garde_publication, enregistrer_serveurs, etat_lisible
        installer_garde_publication("maiq", logger)
        enregistrer_serveurs("maiq", bot, logger)
        logger.info(f"🧪 [MODE TEST:maiq] {etat_lisible('maiq')}")
    except ImportError:
        pass  # shared/ est optionnel, le bot doit tourner sans

    logger.info('--------------------------------------------------')
    logger.info('🐱 M\'aiq le Menteur est prêt (Production Mode).')
    logger.info('--------------------------------------------------')
    
    ensure_data_writable("maiq", DATA_DIR, logger)
    
    # HEALTH CHECK
    logger.info('📊 [HEALTH CHECK] APIs disponibles :')
    logger.info(f'   ✅ Gemini : {len([k for k in GEMINI_API_KEYS if k])} clés')
    logger.info(f'   {"✅" if groq_client else "❌"} Groq (prioritaire)')
    logger.info(f'   {"✅" if mistral_client else "❌"} Mistral')
    logger.info(f'   {"✅" if nvidia_client else "❌"} NVIDIA (nemotron)')
    logger.info('--------------------------------------------------')
    
    if not status_loop_maiq.is_running():
        status_loop_maiq.start()
    if not daily_rumor_check.is_running():
        daily_rumor_check.start()  # Rumeur quotidienne (jours pairs)
    # auto_riddle_loop_maiq.start() # Énigmes de M'aiq - DEACTIVATED (ON COMMAND ONLY)
    if not riddle_passive_hint_loop.is_running():
        riddle_passive_hint_loop.start()  # Relance des indices

    
    # NOUVELLES TÂCHES
    if not birthday_check_maiq.is_running():
        birthday_check_maiq.start()  # Vérification anniversaires
    if daily_bio and not daily_bio_loop_maiq.is_running():
        daily_bio_loop_maiq.start()

    
    global twitch_announcer
    if TWITCH_AVAILABLE and twitch_announcer is None:
        twitch_announcer = setup_twitch_announcer(
            bot, "maiq", logger,
            personality_prompt=PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client, nvidia_client=nvidia_client, bot_label="M'aiq")
        if twitch_announcer:
            if not twitch_poll_loop.is_running():
                twitch_poll_loop.start()

    # Rétroactif Riddle Check
    try:
        await check_missed_riddle_answers()
    except Exception as e:
        logger.error(f"❌ [RIDDLE CHECK] Erreur: {e}")

    # INITIALISATION DES COMMANDES SLASH
    if DATABASE_AVAILABLE:
        try:
            setup_slash_commands(bot, "M'aiq")
            await sync_slash_commands(bot)
            logger.info("[SLASH] Commandes slash initialisées")
        except Exception as e:
            # on_ready rejoue a chaque reconnexion : la 2e pose leve
            # CommandAlreadyRegistered et avortait le rattrapage des enigmes.
            logger.error(f"[SLASH] Erreur: {e}")

    # INITIALISATION DES MINI-JEUX
    if GAMES_AVAILABLE:
        try:
            setup_games(bot, logger, PERSONA)
        except Exception as e:
            logger.error(f"[GAMES] Erreur d'initialisation des mini-jeux: {e}")

async def check_missed_riddle_answers():
    """
    Vérifie si des bonnes réponses ont été données pendant que le bot était éteint.
    """
    if not DATABASE_AVAILABLE: return
    
    logger.info("🕵️ [STARTUP] Vérification des réponses manquées...")
    
    active_riddles = get_all_active_riddles()
    if not active_riddles:
        logger.info("✅ [STARTUP] Pas d'énigmes actives.")
        return
        
    for r in active_riddles:
        channel_id = r["channel_id"]
        channel = bot.get_channel(channel_id)
        if not channel: continue
        
        # On ne check que si l'énigme a un message de départ (pour savoir quand ça a commencé)
        if not r.get("started_at"): continue
        
        try:
            start_time = datetime.fromisoformat(r["started_at"])
            # On scanne les mesages APRES le début de l'énigme
            # (Limitons à 100 messages pour éviter d'être trop lent)
            messages = []
            async for m in channel.history(limit=100, after=start_time):
                messages.append(m)
            
            # Check answers
            for m in messages:
                if m.author.bot: continue
                
                # Check if already winner
                if m.author.id in r.get("winners", []): continue
                
                correct, reward, msg_text = check_answer(channel_id, m.content)
                if correct:
                    logger.info(f"⚡ [STARTUP CATCH-UP] Bonne réponse trouvée de {m.author.name} !")
                    
                    # Award logic (simplified replication of on_message)
                    add_riddle_winner(channel_id, m.author.id)
                    new_streak = add_riddle_streak(m.author.id)
                    
                    bonus = 0
                    if new_streak % 3 == 0: bonus = 30
                    
                    total_reward = reward + bonus
                    add_reputation(m.author.id, total_reward, "Rattrapage Enigme (Offline)")
                    complete_quest(m.author.id, "participate_game")
                    
                    # Notify
                    try:
                        await m.reply(f"🎉 **M'aiq s'était endormi...** Mais il a vu ta réponse ! Tu gagnes **+{total_reward}** points ! 💎")
                        await m.add_reaction("✅")
                    except Exception as e:
                        logger.debug(f"[ENIGME] rattrapage hors-ligne : notification impossible : {e}")
                    
        except Exception as e:
            logger.error(f"⚠️ [STARTUP CHECK FAIL] Canal {channel.name}: {e}")


# STATUS VARIABLE
current_maiq_activity = "Chercher des pinces (Calipers)"

@tasks.loop(seconds=90)
async def twitch_poll_loop():
    if twitch_announcer:
        await twitch_announcer.tick()

@twitch_poll_loop.before_loop
async def before_twitch_poll():
    await bot.wait_until_ready()

@tasks.loop(minutes=30)
async def status_loop_maiq():
    global current_maiq_activity
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
    current_maiq_activity = activity.name  # réutilisé dans les prompts (« ce que tu fais »)
    await bot.change_presence(activity=activity)

@tasks.loop(hours=12)
async def birthday_check_maiq():
    """Vérifie les anniversaires tous les 12h."""
    if DATABASE_AVAILABLE:
        await check_and_send_birthdays(bot, "M'aiq")

@tasks.loop(hours=1)
async def daily_bio_loop_maiq():
    if daily_bio:
        await daily_bio.ensure_daily_bio()

@daily_bio_loop_maiq.before_loop
async def before_daily_bio_maiq():
    await bot.wait_until_ready()

# ÉVÉNEMENTS SERVEUR

@bot.event
async def on_member_join(member):
    if DATABASE_AVAILABLE:
        await handle_member_join(bot, member, "M'aiq")

@bot.event
async def on_member_remove(member):
    if DATABASE_AVAILABLE:
        await handle_member_remove(bot, member, "M'aiq")

daily_rumor_published = False  # Flag pour éviter les doublons

@tasks.loop(hours=1)
async def daily_rumor_check():
    """Vérifie si c'est le moment de publier la rumeur quotidienne (jours pairs uniquement)."""
    global daily_rumor_published
    
    now = datetime.now()
    day = now.day
    hour = now.hour
    
    # Reset le flag à minuit
    if hour == 0:
        daily_rumor_published = False
        return
    
    if day % 2 != 0:
        return  # Jour impair = Sheogorath publie, pas nous
    
    # Fenêtre horaire : 14h-22h
    if hour < 14 or hour >= 22:
        return
    
    # Déjà publié aujourd'hui ?
    if daily_rumor_published:
        return
    
    # Probabilité de publication dans cette heure (pour étaler entre 14h-22h)
    if random.random() > 0.125:
        return
    
    # ON PUBLIE !
    daily_rumor_published = True
    await publish_daily_rumor()

async def publish_daily_rumor():
    """Publie une rumeur sur un utilisateur actif dans #la-taverne-des-bots."""
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
        logger.warning("❌ [RUMEUR] Canal 'la-taverne-des-bots' introuvable.")
        return
    
    # Collecter les utilisateurs récents de ce canal
    active_users = []
    try:
        async for msg in target_channel.history(limit=100):
            if not msg.author.bot and msg.author not in active_users:
                active_users.append(msg.author)
            if len(active_users) >= 10:
                break
    except Exception as e:
        logger.error(f"❌ [RUMEUR] Erreur lecture historique: {e}")
        return
    
    if not active_users:
        logger.warning("❌ [RUMEUR] Aucun utilisateur actif trouvé.")
        return
    
    # Choisir une cible
    target_user = random.choice(active_users)
    
    # Générer la rumeur via LLM
    rumor_prompt = (
        f"SYSTEM: {PERSONALITY_PROMPT}\n"
        f"INSTRUCTION: Invente une RUMEUR absurde et drôle sur {target_user.display_name}. "
        "La rumeur doit être courte (1-2 phrases max), dans le style de M'aiq (évasif, mystérieux). "
        "Commence par 'M'aiq a entendu dire que...' ou 'Certains disent que...'. "
        "Sois créatif et fais référence au lore Elder Scrolls si possible. "
        f"IMPORTANT: Mentionne l'utilisateur avec '<@{target_user.id}>' dans la rumeur."
    )
    
    rumor_text = None
    
    # Try GROQ first
    if groq_client:
        try:
            chat = await asyncio.wait_for(
                asyncio.to_thread(
                    groq_client.chat.completions.create,
                    messages=[{"role": "user", "content": rumor_prompt}],
                    model=GROQ_FAST,
                    **groq_kwargs(GROQ_FAST),
                    temperature=0.9
                ),
                timeout=30
            )
            rumor_text = chat.choices[0].message.content
        except Exception as e:
            logger.warning(f"⚠️ [RUMEUR] Groq failed: {e}")
    
    # Fallback Gemini
    if not rumor_text:
        api_key = key_manager.get_key("gemini")
        if api_key:
            try:
                client = get_safe_genai_client(api_key=api_key)
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model='gemini-3.5-flash', contents=rumor_prompt
                    ),
                    timeout=30
                )
                rumor_text = resp.text
            except Exception as e:
                error_code = getattr(e, "code", getattr(e, "status_code", 0))
                key_manager.report_error("gemini", api_key, error_code)
                logger.warning(f"⚠️ [RUMEUR] Gemini failed: {e}")
    
    if not rumor_text:
        # Fallback statique
        rumor_text = f"M'aiq a entendu dire que <@{target_user.id}> a été vu vendant du sucre lunaire à Blancherive. Mais M'aiq n'a rien vu. 🤫"
    
    # Clean artifacts
    llm_artifacts = ["[INST]", "[/INST]", "</s>", "<s>", "<<SYS>>", "<</SYS>>"]
    for artifact in llm_artifacts:
        rumor_text = rumor_text.replace(artifact, "")
    rumor_text = rumor_text.strip()
    
    # Publier avec le tag spécial pour que Sheogorath détecte
    await target_channel.send(f"📢 **[RUMEUR DU JOUR]** {rumor_text}")
    
    # Enregistrer la cible pour l'interactivité
    recent_rumor_targets[target_user.id] = datetime.now().timestamp()
    logger.info(f"🐱 [RUMEUR PUBLIÉE] Cible: {target_user.display_name}")

# ÉNIGMES DE M'AIQ (Transféré de Sheogorath)

@tasks.loop(minutes=5)
async def riddle_passive_hint_loop():
    """Surveille les énigmes actives et poste un indice si bloqué > 15min sans spammer."""
    await bot.wait_until_ready()
    try:
        from shared.shared_database import get_all_active_riddles
        active_riddles = get_all_active_riddles()
        if not active_riddles: return
        
        now = datetime.now()
        for r in active_riddles:
            started_at_str = r.get("started_at")
            if not started_at_str: continue
            
            started_at = datetime.fromisoformat(started_at_str)
            age_mins = (now - started_at).total_seconds() / 60
            
            # Seulement dans la fenêtre 15-20 min pour qu'elle pop exactement 1 fois toutes les énigmes
            if 15.0 <= age_mins < 20.0:
                channel = bot.get_channel(r["channel_id"])
                if channel:
                    hint = r.get("hint", "Aucun indice pour vous.")
                    await channel.send(f"😼 **M'aiq remarque que vos esprits sont lents aujourd'hui...** Un indice : *{hint}*")
    except Exception as e:
        logger.error(f"[HINT LOOP] Erreur: {e}")

# UTILITAIRE : Fermeture propre d'une énigme (Désépingler + Supprimer réponses)

async def close_riddle_cleanup(channel, riddle_message_id: int = None):
    """
    Ferme proprement une énigme :
    - Désépingler le message de l'énigme
    - Supprimer la DB entry
    (On ne purge PAS les messages de réponse pour conserver les réactions ✅/❌ de M'aiq)
    """
    # 1. Désépingler
    if riddle_message_id:
        try:
            ref_msg = await channel.fetch_message(riddle_message_id)
            await ref_msg.unpin()
        except Exception as e:
            logger.debug(f"[ENIGME] desepinglage impossible : {e}")
    
    # 2. Supprimer de la DB
    try: delete_active_riddle(channel.id)
    except Exception as e:
        logger.warning(f"[ENIGME] suppression en base impossible : l'enigme restera active : {e}")

# COMMANDES UTILITAIRES (!enigme, !profil)

@bot.command(name="enigme")
async def force_enigme(ctx):
    """Force M'aiq à poser une nouvelle énigme (efface la précédente si besoin)."""
    if not DATABASE_AVAILABLE: return

    # Effacer l'ancienne énigme si elle existe
    existing = get_active_riddle(ctx.channel.id)
    if existing:
        logger.info(f"🗑️ [ENIGME CMD] Ancienne énigme effacée par {ctx.author.name}")
        await close_riddle_cleanup(ctx.channel, existing.get("message_id"))

    await ctx.send("🐱 M'aiq réfléchit...")
    await generate_and_post_riddle(ctx.channel)

@bot.command(name="profil")
async def show_profile(ctx):
    """Affiche le profil et la réputation du joueur."""
    if not DATABASE_AVAILABLE: return

    user_id = ctx.author.id
    rep_data = get_reputation(user_id)
    username = ctx.author.display_name
    
    points = rep_data.get("points", 0)
    current_level = get_reputation_level(points)
    
    # Next rank info
    next_limit, next_rank_name = get_next_rank_info(points)
    
    # Progress Bar
    if next_limit >= 999999:
        progress_bar = "[██████████] ∞"
        percent = 100
    else:
        # Calculate percent based on previous threshold 
        # (This is approximate, let's just do simple math related to next_limit for now to avoid complexity)
        # Actually proper progress needs prev_limit.
        # Let's just show Points / Goal
        percent = min(100, int((points / next_limit) * 100))
        blocks = int(percent / 10)
        progress_bar = f"[{'█'*blocks}{'░'*(10-blocks)}] {points}/{next_limit}"

    embed = discord.Embed(title=f"📜 Parchemin de {username}", color=0x9B59B6)
    embed.add_field(name="Rang", value=f"**{current_level}**", inline=False)
    embed.add_field(name="Progression", value=f"`{progress_bar}`", inline=False)
    
    # Interactions count
    interactions = get_user_interactions(user_id)
    embed.add_field(name="Activité", value=f"{len(interactions)} interactions récentes", inline=True)
    
    embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text="M'aiq vous observe. Toujours.")
    
    await ctx.send(embed=embed)


async def generate_and_post_riddle(target_channel):
    """Génère et poste une énigme sur le canal donné (efface la précédente si besoin)."""
    import uuid
    MAX_RETRIES = 3

    # Nettoyage préventif : fermer toute énigme résiduelle proprement avant de poster
    leftover = get_active_riddle(target_channel.id)
    if leftover:
        logger.info(f"🧹 [RIDDLE MAIQ] Résidu nettoyé avant nouvelle énigme.")
        await close_riddle_cleanup(target_channel, leftover.get("message_id"))

    # Fetch recent context for thematic riddle
    context_str = ""
    try:
        messages_list = []
        async for hist_msg in target_channel.history(limit=15):
            if not hist_msg.author.bot and hist_msg.content.strip():
                messages_list.append(f"{hist_msg.author.name}: {hist_msg.content}")
        if messages_list:
            context_str = "\\n[CONTEXTE DE LA TAVERNE (Derniers messages)]\\n" + "\\n".join(reversed(messages_list)) + "\\n"
    except Exception as e:
        logger.warning(f"Impossible de fetch le contexte pour énigme: {e}")

    # 10% Chance of IMPOSSIBLE RIDDLE (Troll)
    is_impossible = random.random() < 0.10
    
    for attempt in range(MAX_RETRIES):
        if is_impossible:
            prompt = (
                f"SYSTEM: {PERSONALITY_PROMPT}\\n{context_str}"
                "INSTRUCTION: En t'inspirant (si possible) de la conversation ci-dessus, invente une devinette ABSURDE, SANS SENS, impossible à résoudre. "
                "Elle doit avoir l'air profonde mais n'avoir aucune logique. "
                "Exemple : 'Quelle est la couleur du chiffre 4 quand il a froid ?' "
                "Format de réponse STRICT (JSON) : "
                                '{"question": "texte absurde", "answer": ["IGNORE_THIS"], "hint": "Il n\\\'y a pas de réponse...", "reward": 0}'
                "\\nIMPORTANT : Ne fais AUCUNE référence à l'univers d'Elder Scrolls (Tamriel, Skyrim, Khajiit, etc.) dans l'énigme."
                "\\nNe mets RIEN d'autre que le JSON."
            )
        else:
            prompt = (
                f"SYSTEM: {PERSONALITY_PROMPT}\\n{context_str}"
                "INSTRUCTION: En t'inspirant (si possible) de la thématique de la conversation ci-dessus, invente une devinette LOGIQUE, COHÉRENTE mais DIFFICILE À TROUVER SUR GOOGLE. "
                "ÉVITE les classiques (l'écho, le silence, le vent). Sois créatif et original comme M'aiq. "
                "La réponse doit être un vrai mot ou concept (pas de truc abstrait flou). "
                "Thèmes : Tamriel, Objets du quotidien, Nature, Mensonge, Logique pure. "
                "Format de réponse STRICT (JSON) : "
                                '{"question": "texte de la devinette", "answer": ["réponse1", "réponse2"], "hint": "indice évasif", "reward": 30}'
                "\\nIMPORTANT : Ne fais AUCUNE référence à l'univers d'Elder Scrolls (Tamriel, Skyrim, Oblivion, etc.) dans l'énigme. Les énigmes doivent être universelles (vie quotidienne, nature, objets, logique)."
                "\\nNe mets RIEN d'autre que le JSON."
            )
        
        riddle_data = None
        
        # Essai Groq
        if groq_client:
            try:
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        groq_client.chat.completions.create,
                        messages=[{"role": "user", "content": prompt}],
                        model=GROQ_FAST,
                        **groq_kwargs(GROQ_FAST),
                        temperature=0.9,
                        response_format={"type": "json_object"}
                    ),
                    timeout=30
                )
                riddle_data = json.loads(chat.choices[0].message.content)
            except Exception as e:
                logger.warning(f"⚠️ [RIDDLE MAIQ] Groq JSON fail: {e}")
                
        # Fallback Gemini
        if not riddle_data:
            api_key = key_manager.get_key("gemini")
            if api_key:
                try:
                    client = get_safe_genai_client(api_key=api_key, http_options={'api_version': 'v1beta'})
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model='gemini-3.5-flash',
                            contents=prompt,
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        ),
                        timeout=30
                    )
                    riddle_data = json.loads(resp.text)
                except Exception as e:
                    logger.warning(f"⚠️ [RIDDLE MAIQ] Gemini JSON fail: {e}")
                    key_manager.report_error("gemini", api_key, 500)

        # Validation Anti-Doublon (Uniquement pour les NORMALES)
        if riddle_data and "question" in riddle_data:
            if not is_impossible:
                # Vérification Sémantique (Question + Réponse)
                if is_riddle_duplicate(riddle_data["question"], riddle_data.get("answer")):
                    logger.info(f"♻️ [RIDDLE] Doublon rejeté (Question ou Réponse): {riddle_data['question'][:30]}... (Essai {attempt+1}/{MAX_RETRIES})")
                    riddle_data = None # On rejette et on retente
                    continue
                else:
                    break # C'est bon !
            else:
                break # Impossible riddles don't need dup check
    
    # Validation et Lancement
    if riddle_data and "question" in riddle_data and "answer" in riddle_data:
        
        if is_impossible:
            # Trap Riddle: Answer is a UUID (impossible to guess)
            answers = [str(uuid.uuid4())] 
            riddle_data["reward"] = 0 # No reward
            embed_color = 0xFF0000 # Rouge pour danger/troll
            footer_text = "M'aiq jure que c'est la vérité."
        else:
            answers = [str(a).lower().strip() for a in riddle_data["answer"]]
            embed_color = 0xFFD700
            footer_text = "M'aiq ne connaît pas la réponse. Demandez à Sheogorath."

        embed = discord.Embed(
            title="😼 DEVINETTE DE M'AIQ" if not is_impossible else "👹 ÉNIGME DU MENTEUR",
            description=f"*{riddle_data['question']}*",
            color=embed_color
        )
        
        if not is_impossible:
            embed.add_field(name="Gain", value=f"+{riddle_data.get('reward', 30)} réputation", inline=True)
            
        # Instructions claires pour la réponse
        embed.add_field(name="Comment répondre ?", 
                        value="✍️ **Répondre** à ce message (Reply)\n⚡ `!reponse <votre réponse>`\n🤡 `!soluce` (Sheogorath)", 
                        inline=False) 

        embed.set_footer(text=footer_text)
        
        # 1. Envoyer le message
        msg = await target_channel.send(content="📌 **M'aiq a une question qui gratte.**", embed=embed)
        
        # 2. Épingler le message
        try:
            await msg.pin()
        except Exception:
            pass # Pas grave si pas les perms
            
        # 3. Sauvegarder en DB avec l'ID du message (DB racine partagée → accessible par Sheogorath)
        start_tracking_riddle(
            target_channel.id, 
            riddle_data["question"], 
            answers, 
            riddle_data.get("hint", "La réponse est ailleurs."), 
            riddle_data.get("reward", 30),
            msg.id,
            is_impossible=is_impossible
        )
        
        if not is_impossible:
            # 4. Ajouter à l'historique (avec réponses pour l'anti-répétition sémantique)
            add_to_riddle_history(riddle_data["question"], answers)
        
        logger.info(f"🧩 [RIDDLE MAIQ] Nouvelle devinette épinglée (Impossible={is_impossible}) : {riddle_data['question'][:30]}...")

from discord import app_commands

@bot.tree.command(name="profil_maiq", description="Découvrez ce que M'aiq pense de vous.")
async def profil_maiq_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    
    if not DATABASE_AVAILABLE:
        await interaction.followup.send("M'aiq a perdu ses notes. La base de données est secrète.")
        return
        
    rep_data = get_reputation(interaction.user.id)
    points = rep_data.get("points", 0)
    level = get_reputation_level(points)
    
    # Generate LLM Quote
    quote = "M'aiq ne sait pas qui tu es. Et M'aiq ne s'en soucie pas."
    if groq_client:
        prompt = (
            f"SYSTEM: {PERSONALITY_PROMPT}\\n"
            f"INSTRUCTION: Le mortel {interaction.user.display_name} demande son profil. "
            f"Il a {points} points de réputation et son rang est '{level}'. "
            "Génère une très courte remarque sardonique ou mystérieuse (1-2 phrases maximum) de M'aiq à son sujet."
        )
        try:
            chat = await asyncio.wait_for(
                asyncio.to_thread(
                    groq_client.chat.completions.create,
                    messages=[{"role": "user", "content": prompt}],
                    model=GROQ_FAST,
                    **groq_kwargs(GROQ_FAST),
                    temperature=0.8
                ),
                timeout=15
            )
            quote = chat.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[PROFIL] Groq failed: {e}")
            
    # Remove artifacts
    for artifact in ["[INST]", "[/INST]", "</s>", "<s>", "<<SYS>>", "<</SYS>>"]:
        quote = quote.replace(artifact, "")
    quote = quote.replace('"', "").strip()
    
    embed = discord.Embed(
        title=f"📜 Parchemin de {interaction.user.display_name}",
        description=f"**Réputation :** {points} 💎\\n**Rang :** {level}\\n\\n*« {quote} »*",
        color=0x8A2BE2
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="M'aiq le Menteur vous observe.")
    
    await interaction.followup.send(embed=embed)

@bot.command(name="maiq")
async def maiq_stats(ctx):
    """Affiche les statistiques de M'aiq"""
    data = load_data()
    calipers = data.get("calipers", 0)
    fatigue = data.get("fatigue", {}).get("count", 0)
    
    state = "En pleine forme" if fatigue < 3 else "Fatigué"
    
    await ctx.send(f"🐱 **Statistiques de M'aiq**\n- 📏 **Pinces volées** : {calipers}\n- 💤 **État** : {state} ({fatigue}/3 actions)")

@bot.command(name="rumeur")
async def maiq_rumeur(ctx):
    """Lance une rumeur (Lie) complètement fausse."""
    prompt = f"SYSTEM: {PERSONALITY_PROMPT}\nINSTRUCTION: Invente une rumeur absurde et très courte sur un autre Prince Daedra, un joueur, ou un événement impossible. Commence par 'M'aiq a entendu dire que...' ou 'Certains disent que...'."
    
    response_text = None
    
    # Use Groq (Speed)
    if groq_client:
        try:
             chat = await asyncio.wait_for(
                 asyncio.to_thread(
                     groq_client.chat.completions.create,
                     messages=[{"role": "user", "content": prompt}],
                     model=GROQ_FAST,
                     **groq_kwargs(GROQ_FAST),
                     temperature=0.9
                 ),
                 timeout=30
             )
             response_text = chat.choices[0].message.content
        except Exception as e:
            logger.warning(f"[GROQ RUMEUR] {e}")
        
    # Fallback Gemini
    if not response_text:
        api_key = key_manager.get_key("gemini")
        if api_key:
            try:
                client = get_safe_genai_client(api_key=api_key, http_options={'api_version': 'v1beta'})
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model='gemini-3.5-flash',
                        contents=prompt
                    ),
                    timeout=30
                )
                response_text = resp.text
            except Exception as e:
             error_code = getattr(e, "code", getattr(e, "status_code", 0))
             key_manager.report_error("gemini", api_key, error_code)
             logger.warning(f"[RUMEUR] Gemini rumeur command failed: {e}")
            
    if response_text:
        await ctx.send(f"📢 **[RUMEUR]** {response_text}")
    else:
        await ctx.send("M'aiq a oublié ce qu'il voulait dire.")

@bot.event
async def on_reaction_add(reaction, user):
    """Le Système de Troc de M'aiq (Hidden Feature)"""
    if user.bot: return
    if reaction.message.author.id != bot.user.id: return # Seulement sur les messages de M'aiq

    emoji = str(reaction.emoji)
    
    # 1. LES PINCES (CALIPERS) - Obsession absolue
    if emoji in ["📏", "📐", "🦞"]:
        # M'aiq vole la pince
        try:
            await reaction.remove(user)
            await reaction.message.add_reaction("❤️") # Il aime
            
            # UPDATE COUNTER
            data = load_data()
            data["calipers"] = data.get("calipers", 0) + 1
            save_data(data)
            count = data["calipers"]
            
            chance = random.random()
            if chance < 0.4:
                await reaction.message.channel.send(f"{user.mention} Ah ! Une pince ! M'aiq la prend. (Total volé: {count})")
        except discord.HTTPException as e:
            logger.debug(f"[PINCE] compteur ou reaction : echec Discord : {e}")

    # 2. LE CHEVAL (Nourriture)
    elif emoji in ["🐴", "🐎", "🦄"]:
        await reaction.message.add_reaction("🍴")
        if random.random() < 0.5:
            await reaction.message.channel.send("Mmmmh. Délicieux cheval. M'aiq avait faim.")

    # 3. LE SUCRE LUNE / SKOOMA
    elif emoji in ["🌕", "🌙", "🧂", "🧪"]:
        await reaction.message.add_reaction("🥴")
        await reaction.message.channel.send("M'aiq se sent... étrange. Le monde tourne plus vite.")

    # 4. LES CRABES (Dégoût)
    elif emoji in ["🦀"]:
        await reaction.message.add_reaction("😡")
        await reaction.message.channel.send("Horrible créature ! M'aiq déteste les crabes de boue !")

# Noms des AUTRES bots du serveur : si l'échange leur est visiblement adressé, on ne s'incruste
# PAS lors d'une intervention ALÉATOIRE (les mentions/nom direct du bot restent prioritaires).
OTHER_BOT_NAMES = ["sheo", "sheogorath", "johnny", "silverhand", "samurai", "silverbot", "alfred", "pennyworth", "sugar", "sugar bot", "malena", "malèna"]

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
    # 0. SÉCURITÉ : Ne jamais se répondre à soi-même
    if message.author.id == bot.user.id:
        return
        
    
    # SILENCE STREAM (Canal ignoré)
    if is_ignored_channel(message.channel):
        return
    
    # Vérification mode maintenance AVANT process_commands
    if DATABASE_AVAILABLE and is_maintenance_mode():
        return
    
    await bot.process_commands(message) # Important pour les commandes (!maiq)

    # Un message qui est une commande de CE bot a deja produit sa reponse :
    # il ne doit pas repartir dans le chemin LLM (bavardage aleatoire compris).
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    if message.author.bot:
        return

    # ══════════════════════════════════════════════════
    # TRAITEMENT MULTIMODAL (Vision + Audio Vocal)
    # Uniquement si on s'adresse à M'aiq (mention/reply/nom) — pas de
    # commentaire spontané des images postées.
    # ══════════════════════════════════════════════════
    _addressed_early = (
        bot.user.mentioned_in(message)
        or (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user)
        or any(name in message.content.lower() for name in ["maiq", "m'aiq", "le menteur"])
    )
    atts = (await resolve_media_attachments(message)
            if _addressed_early else message.attachments)
    # ══════════════════════════════════════════════════

    # GESTION DES RÉPONSES AUX ÉNIGMES (PASSIVE + REPLY)
    if DATABASE_AVAILABLE and not message.author.bot:
        try:
            active_riddle = get_active_riddle(message.channel.id)
            if active_riddle:
                is_explicit_reply = (message.reference and hasattr(message.reference, 'message_id') and active_riddle.get("message_id") == message.reference.message_id)
                answer = message.content
                
                # Check silently
                correct, reward, msg_text = check_answer(message.channel.id, answer)
                
                if correct:
                    winners = get_riddle_winners(message.channel.id)
                    if message.author.id in winners:
                         if is_explicit_reply:
                             await message.add_reaction("🚫")
                         return

                    try: add_riddle_participant(message.channel.id, message.author.id)
                    except Exception as e:
                        logger.warning(f"[ENIGME] participant non enregistre en base : {e}")
                    
                    try: await message.add_reaction("✅")
                    except Exception as e:
                        logger.debug(f"[ENIGME] reaction de succes impossible : {e}")
                    
                    existing_winners = get_riddle_winners(message.channel.id)
                    actual_reward = reward
                    bonus_text = ""
                    
                    if not existing_winners:
                        actual_reward = 50 # SPEED BONUS
                        bonus_text = "⚡ **BONUS VITESSE (+50)** ! "
                    else:
                        actual_reward = 15 # STANDARD REWARD
                        
                    add_riddle_winner(message.channel.id, message.author.id)

                    new_streak = add_riddle_streak(message.author.id)
                    streak_bonus = 0
                    if new_streak % 3 == 0:
                        streak_bonus = 30
                        actual_reward += streak_bonus
                        bonus_text += f"🔥 **SÉRIE DE {new_streak} VICTOIRES (+{streak_bonus})** ! "

                    add_reputation(message.author.id, actual_reward, "Devinette réussie")
                    logger.info(f"💎 [WIN] {message.author.name}: +{actual_reward} (Streak: {new_streak})")

                    complete_quest(message.author.id, "participate_game")
                    
                    try: 
                        if active_riddle.get("message_id"):
                            ref_msg = await message.channel.fetch_message(active_riddle["message_id"])
                            await ref_msg.unpin()
                    except Exception as e:
                        logger.debug(f"[ENIGME] desepinglage impossible : {e}")
                    
                    await message.reply(f"🎉 **Exact !** {bonus_text}Tu gagnes **+{actual_reward}** points de réputation ! 💎\n*(L'énigme reste ouverte pour les autres !)*") 
                    return
                else:
                    if is_explicit_reply:
                        try: await message.add_reaction("❌")
                        except Exception as e:
                            logger.debug(f"[ENIGME] reaction d'echec impossible : {e}")
                        reset_riddle_streak(message.author.id)
                        return
                    # Sinon on ignore passivement
        except Exception as e:
            logger.error(f"Erreur check reply riddle: {e}")
        


    # 2. TRIGGER ANALYSIS
    is_mentioned = bot.user.mentioned_in(message)
    is_reply = (message.reference and message.reference.resolved and message.reference.resolved.author == bot.user)
    
    # 🚫 RESPECT DES MENTIONS : Si d'autres sont mentionnés et PAS moi, je me tais.
    if message.mentions and not is_mentioned:
        return

    # DETECTION DU NOM SANS @ (maiq, m'aiq, le menteur)
    is_name_mentioned = any(name in message.content.lower() for name in ["maiq", "m'aiq", "le menteur"])
    
    keywords = [
        "mensonge", "vérité", "dragon", "cheval", "secret", "sable", 
        "sucre", "skooma", "pince", "compas", "crabe", "poisson", 
        "bâtonnet", "loup", "garou", "fourrure", "elsweyr", "khajiit", "lune"
    ]
    # Utilisation de Regex pour éviter les faux positifs (ex: "chevalier" pour "cheval")
    has_keyword = any(re.search(rf"\b{word}\b", message.content.lower()) for word in keywords)
    is_eavesdropping = False
    
    # Détection d'images
    has_attachment_image = classify_request(message.content, message.attachments, silent=True)["has_image"]
    
    # "L'Oreille qui traîne" (Si mot-clé + pas de mention + random 20%)
    if has_keyword and not is_mentioned and not is_reply and not has_attachment_image:
         if random.random() < 0.20:
            if await _other_bot_in_focus(message):
                logger.info("[ANTI-INCRUSTATION] Échange adressé à un autre bot → M'aiq n'écoute pas.")
            else:
                is_eavesdropping = True
                logger.info(f"[OREILLE] Mot-clé détecté dans : {message.content[:50]}")

    # "[RUMEURS INTERACTIVES] Défense ou Réaction"
    is_rumor_defense = False
    if message.author.id in recent_rumor_targets:
        now_ts = datetime.now().timestamp()
        if now_ts - recent_rumor_targets[message.author.id] < 600: # 10 minutes window
             if random.random() < 0.90:  # 90% chance of reacting
                 is_rumor_defense = True
                 logger.info(f"[RUMEUR DEFENSE] M'aiq va réagir à la défense de {message.author.name}")
                 # Remove from target to avoid infinite loop limit
                 del recent_rumor_targets[message.author.id]

    # DECISION FINAL
    should_respond = is_mentioned or is_reply or is_name_mentioned or is_eavesdropping or is_rumor_defense

    if not should_respond:
        return
        
    # FATIGUE SYSTEM (Rate Limit)
    data = load_data()
    now_ts = datetime.now().timestamp()
    fatigue = data.get("fatigue", {"count": 0, "last_msg": 0})
    
    # Reset si plus de 5 minutes (300s)
    if now_ts - fatigue["last_msg"] > 300:
        fatigue["count"] = 0
    
    # Check Limit (5 messages max per burst - augmenté de 3 à 5)
    # BYPASS COMPLET: Si on mentionne M'aiq directement, il répond TOUJOURS
    if not is_mentioned and not is_reply:
        if fatigue["count"] >= 5:
            if random.random() < 0.3: # Spam warning chance (plus poli)
                 await message.channel.send("M'aiq doit se reposer. Sa tête est lourde. Les voyageurs peuvent attendre un peu.")
            logger.info(f"[FATIGUE] M'aiq ignore {message.author.name} (Quota atteint : {fatigue['count']}/5)")
            return

    # Update Logic
    fatigue["count"] += 1
    fatigue["last_msg"] = now_ts
    data["fatigue"] = fatigue
    save_data(data)

    # PREPARATION DE LA REPONSE
    user_message = message.content.replace(f'<@{bot.user.id}>', '').strip()
    
    # Injection du Contexte "Rumeur" - SYSTEM-LEVEL ONLY (Never in user_message to avoid leakage!)
    duel_context = ""
    if is_rumor_defense:
         duel_context = "\n\n[CONFRONTATION RUMEUR] Le mortel tente de nier ou réagit à ta récente rumeur ! Réponds avec une pique flegmatique qui maintient le doute."

    # Gestion de la mémoire (Discord Context)
    channel_id = message.channel.id
    if channel_id not in conversation_history:
        conversation_history[channel_id] = []
    
    # Ajout message user à l'historique
    conversation_history[channel_id].append({"role": "user", "parts": [user_message]})
    
    # TRACKING UTILISATEUR (DATABASE)
    if DATABASE_AVAILABLE:
        try:
            get_or_create_user(message.author.id, message.author.name, message.author.display_name)
            log_interaction(message.author.id, "M'aiq", "message")
            # Chance de gagner de la réputation pour une interaction standard
            if random.random() < 0.1:
                add_reputation(message.author.id, 1, "Discussion avec M'aiq")
        except Exception as e:
            logger.error(f"⚠️ DB Error: {e}")
    if len(conversation_history[channel_id]) > MAX_HISTORY:
        conversation_history[channel_id] = conversation_history[channel_id][-MAX_HISTORY:]

    # Contexte visuel (Transcript) & Active Users
    transcript = "CONTEXTE :\n"
    active_mortals = set()
    _chrono = Chrono("maiq", message.channel.id)
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
            
    # INJECTION ACTIVITÉ (STATUS)
    transcript += f"\n[TON ACTIVITÉ ACTUELLE (STATUS DISCORD)] : Tu es en train de : '{current_maiq_activity}'."

    if active_mortals:
        transcript += f"\n[RUMEURS CIBLES VALIDES] : {', '.join(active_mortals)}"

    # ══════════════════════════════════════════════════
    # LTM SYSTEM - MEMORY INJECTION
    # ══════════════════════════════════════════════════
    user_id = message.author.id
    user_name = message.author.name
    user_msg_content = message.content or ""
    
    relevant_facts = fact_memory.get_relevant_facts(user_id, user_msg_content, k=3)
    daily_summary = daily_memory.get_context_summary(user_id)
    dr = daily_memory.get_daily_read(user_id)
    daily_read_addition = f"\n[CONSIGNE DU JOUR] {dr}" if dr else ""
    
    fact_context = ""
    if relevant_facts:
        fact_context = f"\n[CE QUE TU SAIS SUR {user_name} (MÉMOIRE LONG TERME)]:\n- " + "\n- ".join(relevant_facts)
        
    memory_prompt_addition = (
        f"\n\n[CONTEXTE DE MÉMOIRE]"
        f"{fact_context}"
        f"\n{daily_summary}"
        f"{daily_read_addition}"
        f"\n\n[INSTRUCTION MÉMOIRE CONCOMITANTE]: Si tu apprends un fait durable, important et nouveau sur le voyageur {user_name} dans cette interaction (ex: ses préférences, ses opinions, sa localisation, etc.), ajoute-le discrètement à la fin de ta réponse entouré de balises XML : <fact>Le fait appris</fact>. Sinon, ne mets rien."
    )
    
    def _get_meme_addition():
        chan_id = message.channel.id
        consigne = build_meme_consigne(message.content or "", set(meme_recent[chan_id]))
        if consigne:
            import re as _re
            m = _re.search(r"« (.+?) »", consigne)
            if m:
                meme_recent[chan_id].append(m.group(1))
        return consigne

    current_personality_prompt = PERSONALITY_PROMPT + memory_prompt_addition + _get_meme_addition()

    # ANTI-REPETITION INJECTION (NEW!)
    recent_responses = response_memory.get_recent(message.guild.id)
    anti_repeat_prompt = ""
    if recent_responses:
        recent_snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        anti_repeat_prompt = "\n\n[ANTI-RÉPÉTITION ABSOLUE] M'aiq a déjà dit récemment :\n"
        for i, snippet in enumerate(recent_snippets, 1):
            anti_repeat_prompt += f"{i}. \"{snippet}\"\n"
        anti_repeat_prompt += "⚠️ INTERDICTION de répéter ces phrases. M'aiq dit toujours quelque chose de NOUVEAU !"

    # Limite de taille max pour les images (sécurité)
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    # ═══ SMART ROUTER — Classification du message ═══
    _addressed = bool(is_mentioned or is_reply or is_name_mentioned)
    routing = classify_request(user_message, atts, addressed=_addressed)
    
    media_data = None
    mime_type = "image/jpeg"
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

    if has_image and not user_message.strip():
        user_message = "(Le voyageur vous montre une image sans rien dire.)"
    if has_image:
        user_message += "\n[INSTRUCTION VISION] : Regarde l'image attentivement et commente-la selon ton personnage. Décris brièvement ce que tu vois puis réagis de façon évasive et mystérieuse comme M'aiq."
    if has_audio:
        user_message += "\n[🎤 VOCAL] Le voyageur a envoyé un message vocal. Écoute et commente de façon évasive."

    # GÉNÉRATION (Smart Router)
    response_text = None
    
    # Construire le payload Gemini (unifié pour éviter l'erreur 400 des messages "user" consécutifs)
    last_turn_parts = [types.Part(text=f"SYSTEM: {current_personality_prompt}\nCONTEXT: {transcript}{anti_repeat_prompt}{duel_context}\n\nDernier message : {user_message}")]
    if media_data:
        last_turn_parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_data)))
    gemini_messages = [types.Content(role="user", parts=last_turn_parts)]

    _chrono.etape("contexte")
    cascade = get_model_cascade(routing["type"], "maiq")
    
    for client_type, model_name in cascade:
        _depart = time.perf_counter()
        _code_erreur = None
        _raison = None
        api_key = None
        try:
            # 1. GEMINI
            if client_type == "gemini":
                api_key = key_manager.get_key("gemini")
                if not api_key: continue
                client = get_safe_genai_client(api_key=api_key)
                
                # Gemini Call
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name, contents=gemini_messages,
                        config=types.GenerateContentConfig(
                            temperature=0.7,
                            tools=MAIQ_TOOLS_DEFINITION
                        )
                    ),
                    timeout=45 if media_data else 15
                )
                
                # Handling Tool Calls
                if resp.candidates[0].content.parts and resp.candidates[0].content.parts[0].function_call:
                    fc = resp.candidates[0].content.parts[0].function_call
                    tool_name = fc.name
                    args = fc.args
                    
                    logger.info(f"🛠️ [IA AGENT] M'aiq appelle l'outil : {tool_name}")
                    
                    tool_result = "Action impossible."
                    if tool_name == "set_lie_density":
                        tool_result = tool_set_lie_density(args["percentage"])
                    
                    # Feed back
                    gemini_messages.append(resp.candidates[0].content) # Model call
                    gemini_messages.append(types.Content(
                        role="user",
                        parts=[types.Part(function_response=types.FunctionResponse(name=tool_name, response={"result": tool_result}))]
                    ))
                    
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name, contents=gemini_messages,
                            config=types.GenerateContentConfig(
                                temperature=0.6,
                                tools=MAIQ_TOOLS_DEFINITION
                            )
                        ),
                        timeout=45 if media_data else 15
                    )

                response_text = resp.text
                # THOUGHT STRIPPING
                thought_match = re.search(r"<thought>(.*?)</thought>", response_text, re.DOTALL)
                if thought_match:
                    response_text = response_text.replace(thought_match.group(0), "").strip()
                logger.info(f"✅ [GEMINI {model_name}] M'aiq via {routing['reason']}")
                break

            # 1.bis OLLAMA (Moondream)
            elif client_type == "ollama":
                if routing["type"] == RequestType.IMAGE and routing["image_attachment"]:
                    response_text = await process_image_ollama(
                        attachment=routing["image_attachment"],
                        personality_prompt=current_personality_prompt,
                        user_message=user_message
                    )
                    if response_text:
                        logger.info(f"✅ [OLLAMA {model_name}] M'aiq a utilisé Moondream local !")
                        break
                    continue
                else:
                    continue

            # 2. MISTRAL
            elif client_type == "mistral" and mistral_client:
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        mistral_client.chat.complete,
                        model=model_name,
                        messages=[{"role": "system", "content": f"{current_personality_prompt}\n{transcript}"},
                                  {"role": "user", "content": user_message}]
                    ),
                    timeout=15  # borne TEXTE : ce client ne transporte pas le media
                )
                response_text = chat.choices[0].message.content
                logger.info(f"🌪️ [MISTRAL {model_name}] M'aiq a répondu.")
                break

            # 4. GROQ
            elif client_type == "groq" and groq_client:
                msgs = [{"role": "system", "content": f"{current_personality_prompt}\n{transcript}{anti_repeat_prompt}{duel_context}"}]
                for msg in conversation_history[channel_id]:
                    r = "user" if msg["role"] == "user" else "assistant"
                    msgs.append({"role": r, "content": msg["parts"][0]})
                msgs.append({"role": "user", "content": user_message})
                
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        groq_client.chat.completions.create,
                        messages=msgs, model=model_name, temperature=0.7,
                        **groq_kwargs(model_name),
                    ),
                    timeout=15  # borne TEXTE : ce client ne transporte pas le media
                )
                response_text = chat.choices[0].message.content
                logger.info(f"⚡ [GROQ {model_name}] M'aiq a répondu.")
                break

            # 5. NVIDIA — 4e fournisseur, quota independant des trois autres.
            # ⚠️ Ajoute le 2026-09-05. Le lot NVIDIA du 04/09 n'avait cable que
            # shared/llm_cascade.py et ses copies vendorisees : cette cascade-ci est
            # INLINE, l'echelon `nvidia` y tombait donc dans le vide a chaque fois.
            elif client_type == "nvidia" and nvidia_client:
                if media_data is not None:
                    logger.warning(f"⚠️ [NVIDIA] Média reçu mais ignoré par {model_name}. Perte silencieuse évitée.")
                msgs = [{"role": "system", "content": f"{current_personality_prompt}\n{transcript}{anti_repeat_prompt}{duel_context}"}]
                for msg in conversation_history[channel_id]:
                    r = "user" if msg["role"] == "user" else "assistant"
                    msgs.append({"role": r, "content": msg["parts"][0]})
                msgs.append({"role": "user", "content": user_message})

                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        nvidia_client.chat.completions.create,
                        messages=msgs, model=model_name, temperature=0.7,
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
                logger.info(f"🟩 [NVIDIA {model_name}] M'aiq a répondu.")
                break
        except Exception as e:
            error_msg = str(e)
            if not error_msg:
                error_msg = type(e).__name__
            logger.warning(f"⚠️ [{client_type.upper()} FAIL] {model_name} : {error_msg}")
            if client_type == "gemini" and api_key:
                error_code = getattr(e, 'code', getattr(e, 'status_code', 0))
                key_manager.report_error("gemini", api_key, error_code)
            _raison = type(e).__name__
            _code_erreur = getattr(e, 'code', getattr(e, 'status_code', 0))
            continue
        finally:
            # ⚠️ Cette cascade est une COPIE inline de shared/llm_cascade.py : elle
            # n'heritait pas de son tracage, et maiq etait donc invisible dans
            # data/api_usage.db. Aucune ligne pendant le test live du 04/09.
            _latence = int((time.perf_counter() - _depart) * 1000)
            _succes = bool(response_text)
            if not _succes and _raison is None:
                _raison = "non_tentee"
            _index_cle = None
            if client_type == "gemini" and api_key and hasattr(key_manager, "apis"):
                try:
                    _index_cle = key_manager.apis["gemini"]["keys"].index(api_key)
                except (ValueError, KeyError, AttributeError):
                    pass  # la cle n'est pas dans cette liste : l'index reste None, le tracage suit quand meme
            try:
                tracer_appel(
                    bot="maiq", api=client_type, modele=model_name,
                    index_cle=_index_cle, succes=_succes, code_erreur=_code_erreur,
                    latence_ms=_latence, raison=_raison,
                )
            except Exception:
                pass  # le tracage ne doit JAMAIS casser une reponse

    if not response_text and (has_image or has_audio):
        media_name = "l'image" if has_image else "le message vocal"
        await message.channel.send(f"🌙 M'aiq regarde {media_name}. Mais les lunes sont mal alignées. M'aiq ne comprend pas. 🐾")
        return

    if response_text:
        if response_text.startswith("M'aiq:"): response_text = response_text.replace("M'aiq:", "", 1).strip()
        
        # LTM - EXTRACTION AND CLEANING OF FACTS
        matches = re.findall(r"<fact>(.*?)</fact>", response_text, re.DOTALL | re.IGNORECASE)
        for match in matches:
            fact_text = match.strip()
            if fact_text:
                fact_memory.add_fact(user_id, fact_text)
                
        response_text = re.sub(r"<fact>.*?</fact>", "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
        response_text = re.sub(r"<[a-z_-]+>", "", response_text, flags=re.IGNORECASE)
        response_text = re.sub(r"</[a-z_-]+>", "", response_text, flags=re.IGNORECASE).strip()

        _chrono.etape("llm")
        await message.channel.send(response_text)
        _chrono.fin(envoye=True)
        
        conversation_history[channel_id].append({"role": "model", "parts": [response_text]})
        if message.guild:
            response_memory.add(message.guild.id, response_text)
            
        # LTM - Daily interaction logging
        daily_memory.add_interaction(user_id, user_name, user_msg_content, response_text)
        asyncio.create_task(daily_memory.refresh_daily_read(user_id, _daily_llm_call))


@bot.command(name="reponse")
async def reponse_cmd(ctx, *, answer: str):
    """Répondre à M'aiq (Alternative au Reply)."""
    
    if not DATABASE_AVAILABLE: return

    game = get_active_riddle(ctx.channel.id)
    if not game:
        await ctx.send("Pas d'énigme en cours.")
        return

    # Verification Gagnant Existant
    winners = get_riddle_winners(ctx.channel.id)
    if ctx.author.id in winners:
            await ctx.send(f"🚫 {ctx.author.mention} Tu as déjà trouvé la réponse ! Laisse les autres chercher.")
            return

    # Tracking Participant
    try: add_riddle_participant(ctx.channel.id, ctx.author.id)
    except Exception as e:
        logger.warning(f"[ENIGME] participant non enregistre en base : {e}")

    correct, reward, message_text = check_answer(ctx.channel.id, answer)
    
    if correct:
        # WIN
        # SPEED BONUS CHECK
        existing_winners = get_riddle_winners(ctx.channel.id)
        actual_reward = reward
        bonus_text = ""
        
        if not existing_winners:
            actual_reward = 50 # SPEED BONUS
            bonus_text = "⚡ **BONUS VITESSE (+50)** ! "
        else:
            actual_reward = 15 # STANDARD REWARD
            
        # Add Winner
        add_riddle_winner(ctx.channel.id, ctx.author.id)

        # STREAK SYSTEM
        new_streak = add_riddle_streak(ctx.author.id)
        streak_bonus = 0
        if new_streak % 3 == 0:
            streak_bonus = 30
            actual_reward += streak_bonus
            bonus_text += f"🔥 **SÉRIE DE {new_streak} VICTOIRES (+{streak_bonus})** ! "

        # Add Reputation
        add_reputation(ctx.author.id, actual_reward, "Devinette réussie")
        logger.info(f"💎 [WIN CMD] {ctx.author.name}: +{actual_reward} (Streak: {new_streak})")

        complete_quest(ctx.author.id, "participate_game")
        
        # Unpin ONLY
        if game and game.get("message_id"):
            try:
                ref_msg = await ctx.channel.fetch_message(game["message_id"])
                await ref_msg.unpin()
            except Exception as e:
                logger.debug(f"[ENIGME] desepinglage impossible : {e}")
        
        # Feedback WIN
        try: await ctx.message.add_reaction("✅")
        except Exception as e:
            logger.debug(f"[ENIGME] reaction de succes impossible : {e}")
        await ctx.send(f"🎉 **Exact !** {bonus_text}{ctx.author.mention} gagne **+{actual_reward}** points de réputation ! 💎")
        return

    # ERROR HANDLING
    if "M'aiq ne pose pas" in message_text:
        await ctx.send(f"🐱 {ctx.author.mention} {message_text}")
        return

    # LOSE (Reaction only)
    try: await ctx.message.add_reaction("❌")
    except Exception: await ctx.send("❌")
    
    # RESET STREAK
    reset_riddle_streak(ctx.author.id)

@bot.command(name="indice")
async def indice_cmd(ctx):
    if not DATABASE_AVAILABLE: return
    
    # Check Price
    user_rep = get_reputation(ctx.author.id).get("points", 0)
    PRICE = 5
    
    if user_rep < PRICE:
        await ctx.send(f"🚫 M'aiq ne travaille pas gratuitement. Reviens quand tu auras {PRICE} points.")
        return

    hint = get_hint(ctx.channel.id)
    if hint:
        # Payer
        add_reputation(ctx.author.id, -PRICE, "Achat indice")
        await ctx.send(f"💡 **M'aiq vous aide** (pour {PRICE} pièces) : {hint}")
    else:
        await ctx.send("Pas de devinette. Pas d'indice.")

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
        
    await ctx.send("🐾 M'aiq sait beaucoup de choses, mais M'aiq choisit d'oublier. M'aiq a oublié vos histoires et vos secrets. Les lunes brillent sur un esprit vide. 🐾")

if __name__ == "__main__":
    # Un `tasks.loop` rejoue TOUTES les iterations manquees quand l'horloge saute
    # (veille de l'hote) : 40 `MOOD CHANGE` en deux secondes le 2026-09-04.
    installer_anti_rattrapage(logger)
    setup_graceful_shutdown(bot)
    bot.run(DISCORD_TOKEN)
