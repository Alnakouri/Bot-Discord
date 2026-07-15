
# INJECTION SHARED FOLDER
import sys
import os
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
from datetime import datetime
import os
import base64
from shared.response_memory import ResponseMemory
import logging
from pathlib import Path
from shared.smart_router import classify_request, RequestType, download_media, get_model_cascade
from shared.media_handler import process_image, process_image_ollama, process_voice_message

try:
    from shared.memes_fr import build_meme_consigne
    MEMES_AVAILABLE = True
except ImportError:
    MEMES_AVAILABLE = False
    def build_meme_consigne(*a, **k): return ""

import collections
import time
meme_recent = collections.defaultdict(lambda: collections.deque(maxlen=8))  # {channel_id: deque[ref]}

# --- Continuité conversationnelle ---
# Dernier mortel à qui Sheo a répondu, par salon. Évite que Sheo décroche dès qu'on ne le
# re-mentionne pas en plein échange (ex. il répond, tu enchaînes « tu es bisard » → il doit
# poursuivre le fil, pas rester muet).
last_exchange = {}                 # {channel_id: (user_id, timestamp)}
CONTINUATION_WINDOW = 90.0         # s — au-delà, l'échange est considéré clos
CONTINUATION_PROBA = 0.70          # dans la fenêtre, Sheo poursuit ~7 fois sur 10 (grain de folie)
# Noms des AUTRES bots : si le mortel s'adresse à eux, Sheo ne s'incruste pas via la continuité.
OTHER_BOT_NAMES = ("m'aiq", "maiq", "sugar", "sugar bot", "alfred", "johnny", "silverhand", "malena", "rigurt")

try:
    from shared.bot_features import is_feature_enabled
except ImportError:
    def is_feature_enabled(*a, **k): return True

# Répertoire de données (même convention que sheo_faveur : surchargé par l'env en prod)
DATA_DIR = os.getenv("DATA_DIR", ".")

# IMPORT VOICE MODULE (TTS Piper — Open Source)
try:
    from sheo_voice import (
        send_voice_response, cmd_join_voice, cmd_leave_voice,
        disconnect_if_idle, is_tts_enabled, generate_tts,
        ensure_voice_connection, play_audio, VOICE_AUTO_CHANCE
    )
    VOICE_AVAILABLE = is_tts_enabled()
except ImportError:
    VOICE_AVAILABLE = False
    send_voice_response = None
    logger_msg = "⚠️ [VOICE] Module sheo_voice.py non disponible"

# IMPORT SECURE ENV LOADER (Supports encrypted .env files)
try:
    from shared.secure_env import load_secure_env
    load_secure_env(Path(__file__).parent)
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()

# IMPORT SAFE CLIENT (Fix invalid project name error)
from shared.safe_client import get_client as get_safe_genai_client

try:
    import sheo_data
    from sheo_memory import DailyMemory, FactMemory
    from sheo_punishments import (
        apply_temporary_nickname, get_insult_severity,
        PUNISHMENT_NICKS, DURATION_MAP,
        load_punishments, save_punishments
    )
    from sheo_llm import postprocess_response, build_anti_tic_consigne, sentence_budget, merge_recent_responses
    from sheo_mentions import convert_text_mentions_to_discord
    from sheo_faveur import FaveurSystem, FAVEUR_GAIN_MESSAGES, RANK_UP_MESSAGES
    from sheo_imposter import (
        send_imposter_message, fetch_user_style_context,
        get_bot_persona, start_imposter_session, stop_imposter_session, get_active_session
    )
    from sheo_decrees import generate_decree_image, apply_decree_role, cleanup_old_decree_roles
    from shared.shared_database import add_reputation
except ImportError:
    from Sheogorath import sheo_data
    from Sheogorath.sheo_memory import DailyMemory, FactMemory
    from Sheogorath.sheo_punishments import (
        apply_temporary_nickname, get_insult_severity,
        PUNISHMENT_NICKS, DURATION_MAP,
        load_punishments, save_punishments
    )
    from Sheogorath.sheo_llm import postprocess_response, build_anti_tic_consigne, sentence_budget, merge_recent_responses
    from Sheogorath.sheo_mentions import convert_text_mentions_to_discord
    from Sheogorath.sheo_faveur import FaveurSystem, FAVEUR_GAIN_MESSAGES, RANK_UP_MESSAGES
    from Sheogorath.sheo_imposter import (
        send_imposter_message, fetch_user_style_context,
        get_bot_persona, start_imposter_session, stop_imposter_session, get_active_session
    )
    from Sheogorath.sheo_decrees import generate_decree_image, apply_decree_role, cleanup_old_decree_roles
    from shared.shared_database import add_reputation

# LOGGING STRUCTURÉ
try:
    from shared.bot_logger import setup_logger
    logger = setup_logger("sheogorath")
except ImportError:
    logger = logging.getLogger("sheogorath")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(handler)

# IMPORT DES SYSTÈMES (locaux pour Discloud)

try:
    from shared.shared_database import (
        get_or_create_user, is_maintenance_mode, is_ignored_channel,
        get_active_riddle, delete_active_riddle, get_reputation, get_reputation_level
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
    
    def get_maiq_riddle(channel_id: int):
        """Récupère l'énigme active (DB partagée avec M'aiq)."""
        return get_active_riddle(channel_id)
    
    def delete_maiq_riddle(channel_id: int):
        """Supprime l'énigme active (DB partagée avec M'aiq)."""
        delete_active_riddle(channel_id)
except ImportError as e:
    logger.warning(f"⚠️ [SHEO] Modules optionnels non disponibles: {e}")
    DATABASE_AVAILABLE = False

try:
    from shared.twitch_announcer import setup_twitch_announcer
    TWITCH_AVAILABLE = True
except ImportError:
    TWITCH_AVAILABLE = False
    def setup_twitch_announcer(*a, **k): return None

twitch_announcer = None

try:
    from shared.twitch_chat import setup_twitch_chat
    TWITCH_CHAT_AVAILABLE = True
except ImportError:
    TWITCH_CHAT_AVAILABLE = False
    def setup_twitch_chat(*a, **k): return None

twitch_chat = None
twitch_chat_task = None

try:
    from shared.discord_profile import DiscordDailyBio
except ImportError:
    DiscordDailyBio = None

try:
    from shared.discord_status import DiscordDailyStatus
except ImportError:
    DiscordDailyStatus = None



# GAME LOGIC
try:
    from minigames import jeu_fromage
except ImportError:
    def jeu_fromage(user_id): return {"nom": "Fromage Imaginaire", "effet": "confusion", "points": 0}

# ZONE DE CONFIGURATION : SHEOGORATH

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
current_activity_text = "Compter ses dents"

# API KEYS ROTATION (Google Gemini)
GEMINI_API_KEYS = [
    os.getenv("GEMINI_KEY_1"), 
    os.getenv("GEMINI_KEY_2"), 
    os.getenv("GEMINI_KEY_3"), 
]
# Filter out None values in case of missing keys
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]

# FALLBACK API KEYS
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# MEMORY SETTINGS
conversation_history = {}
MAX_HISTORY = 30 

# MULTI-API KEY MANAGER (Gère TOUTES les APIs avec cooldowns)
from shared.api_manager import MultiAPIKeyManager
from shared.graceful_shutdown import setup_graceful_shutdown

# Initialisation du gestionnaire
key_manager = MultiAPIKeyManager()

# Enregistrement des APIs
key_manager.register_api("gemini", GEMINI_API_KEYS)
key_manager.register_api("groq", [GROQ_API_KEY] if GROQ_API_KEY else [])
key_manager.register_api("mistral", [MISTRAL_API_KEY] if MISTRAL_API_KEY else [])
key_manager.register_api("openrouter", [OPENROUTER_API_KEY] if OPENROUTER_API_KEY else [])


# ANTI-REPETITION MEMORY (Par Serveur - ENHANCED)
# Maintenant on garde les 10 dernières réponses pour éviter les cycles
  # {guild_id: ["réponse1", "réponse2", ...]} (max 10)
response_memory = ResponseMemory()

# MISSED MENTIONS TRACKING
checked_messages_sheo = set()  # IDs de messages déjà vérifiés
MAX_CHECKED_CACHE = 200




def get_smart_string_response(text, guild_id):
    text = text.lower()
    
    # 1. SELECTION DU POOL (avec priorisation intelligente)
    pool = None
    
    # Détection de mentions de fromage intenses
    if any(w in text for w in ["fromage", "cheese", "roquefort", "camembert", "brie", "parmesan", "comté"]):
        # Si c'est une demande directe
        if any(w in text for w in ["donne", "veux", "peux", "avoir", "s'il", "stp", "svp", "please"]):
            pool = sheo_data.SHEO_BRAIN["request"]
        else:
            # Discussion philosophique sur le fromage
            pool = sheo_data.SHEO_BRAIN["cheese"]
    
    # Détection de salutations
    elif any(w in text for w in ["salut", "bonjour", "bonsoir", "hey", "hello", "coucou", "yo"]) and len(text.split()) <= 3:
        pool = sheo_data.SHEO_BRAIN["greeting"]
    
    # Détection de critiques méta (répétition, qualité des réponses)
    elif any(w in text for w in ["nul", "répète", "repete", "radote", "dico", "vocabulaire", "varié", "original", "créatif"]):
        pool = sheo_data.SHEO_BRAIN["meta"]
    
    # Détection d'insultes
    elif any(w in text for w in ["fou", "cul", "idiot", "débile", "naze", "con", "crétin", "imbécile", "abruti"]):
        pool = sheo_data.SHEO_BRAIN["insult"]
    
    # Détection de questions philosophiques/existentielles
    elif any(w in text for w in ["pourquoi", "comment", "ordre", "chaos", "jyggalag", "folie", "logique", "sens"]):
        pool = sheo_data.SHEO_BRAIN["philosophy"]
    
    # Détection de folie pure (wabbajack, délires)
    elif any(w in text for w in ["wabbajack", "bizarre", "étrange", "comprend pas", "quoi", "hein", "wtf"]):
        pool = sheo_data.SHEO_BRAIN["madness"]
    
    # Détection de questions sur le savoir/faits
    elif any(w in text for w in ["sais tu", "savais tu", "fait", "anecdote", "culture", "apprends", "connaissance"]):
        pool = random.choice([sheo_data.SHEO_BRAIN["cheese_facts"], sheo_data.SHEO_BRAIN["madness"], sheo_data.SHEO_BRAIN["philosophy"]])

    # Par défaut : mélange aléatoire
    else:
        # 5% de chance de sortir une anecdote fromagée random (le fromage est un condiment)
        if random.random() < 0.05:
            pool = sheo_data.SHEO_BRAIN["cheese_facts"]
        else:
            pool = random.choice([sheo_data.SHEO_BRAIN["madness"], sheo_data.SHEO_BRAIN["insult"], sheo_data.SHEO_BRAIN["philosophy"]])

    if not pool: pool = sheo_data.SHEO_BRAIN["madness"]

    # 2. FILTRAGE ANTI-REPETITION AMÉLIORÉ (10 dernières réponses)
    recent = response_memory.get_recent(guild_id)
    available = [p for p in pool if p not in recent]
    
    # Si tout est épuisé, on relance avec moins de filtrage (5 dernières)
    if not available:
        available = [p for p in pool if p not in recent[-5:]]
    
    # Dernier recours : tout le pool
    if not available: 
        available = pool
    
    choice = random.choice(available)
    response_memory.add(guild_id, choice)
    return choice

def get_smart_string_response_v2(text, guild_id):
    """Version enrichie avec Easter Eggs, Combos, Events Temporels"""
    global current_mood
    text_lower = text.lower()
    
    # 0. EASTER EGG (1% de chance - bypass tout)
    if random.random() < 0.01:
        egg = random.choice(sheo_data.SHEO_BRAIN["easter_eggs"])
        logger.debug(f"🎰 [EASTER EGG] {egg[:50]}...")
        return egg
    
    # 1. DÉTECTION DE COMBOS (priorité absolue)
    for combo_keys, responses in sheo_data.SHEO_BRAIN["combos"].items():
        if all(key in text_lower for key in combo_keys):
            logger.debug(f"🔗 [COMBO] Détecté: {' + '.join(combo_keys)}")
            return random.choice(responses)
    
    # 2. ÉVÉNEMENTS TEMPORELS (selon l'heure)
    current_hour = datetime.now().hour
    time_response = None
    
    if current_hour == 0:  # Minuit exactement
        time_response = random.choice(sheo_data.SHEO_BRAIN["time_events"]["midnight"])
    elif 22 <= current_hour or current_hour < 6:  # Nuit
        if random.random() < 0.15:  # 15% de chance
            time_response = random.choice(sheo_data.SHEO_BRAIN["time_events"]["night"])
    elif 12 <= current_hour < 14:  # Midi
        if random.random() < 0.20:  # 20% de chance
            time_response = random.choice(sheo_data.SHEO_BRAIN["time_events"]["midday"])
    elif 6 <= current_hour < 8:  # Aube
        if random.random() < 0.10:  # 10% de chance
            time_response = random.choice(sheo_data.SHEO_BRAIN["time_events"]["dawn"])
    
    if time_response:
        logger.debug(f"⏰ [TIME EVENT] Heure: {current_hour}h")
        return time_response
    
    # 3. Utiliser l'ancienne logique
    return get_smart_string_response(text, guild_id)

# Instantiation des mémoires (classes importées de sheo_memory.py)
daily_brain = DailyMemory()

async def _daily_llm_call(system_prompt, user_message):
    from shared.llm_cascade import generate_response
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "daily_read"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client, openrouter_client=openrouter_client,
        bot_label="Sheogorath", temperature=0.5, max_tokens=60)
fact_brain = FactMemory()

# Instantiation du système de Faveur du Prince
faveur_system = FaveurSystem()

# INITIALISATION

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # Voice channel support (TTS Piper)

bot = commands.Bot(command_prefix='!', intents=intents)

# Client Initialization


openrouter_client = None

try:
    if OPENROUTER_API_KEY:
        openrouter_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
        logger.info("✅ [SYSTEM] Cerveau OpenRouter connecté.")
except Exception as e:
    logger.warning(f"⚠️ [SYSTEM] OpenRouter absent : {e}")

groq_client = None
try: 
    if GROQ_API_KEY: groq_client = Groq(api_key=GROQ_API_KEY)
except Exception as e: logger.warning(f"⚠️ [INIT] Groq indisponible : {e}")

mistral_client = None
try: 
    if MISTRAL_API_KEY: mistral_client = Mistral(api_key=MISTRAL_API_KEY)
except Exception as e: logger.warning(f"⚠️ [INIT] Mistral indisponible : {e}")


# EVENTS
# ACTIVITY LOOP
current_mood = "neutral"
current_system_prompt = sheo_data.MOOD_PROMPTS.get("neutral", sheo_data.PERSONALITY_BASE)

def get_current_system_prompt():
    prompt = current_system_prompt
    if "{comebacks_placeholder}" in prompt:
        prompt = prompt.replace("{comebacks_placeholder}", sheo_data.get_random_comebacks(5))
    return prompt

ENABLE_DAILY_BIO = os.getenv("ENABLE_DAILY_BIO", "1") != "0"
daily_bio = DiscordDailyBio(
    bot=bot, bot_id="sheogorath", bot_label="Sheogorath",
    personality_prompt=sheo_data.PERSONALITY_BASE,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, openrouter_client=openrouter_client,
    system_prompt_provider=get_current_system_prompt,  # suit l'humeur du jour
    logger=logger, enabled=ENABLE_DAILY_BIO,
) if DiscordDailyBio else None

# Statut Discord auto-piloté par la personnalité (jumeau de la bio).
# La liste ci-dessous n'est plus qu'un FALLBACK si le LLM est indisponible.
_STATUS_FALLBACK = [
    ("playing", "Compter ses dents"),
    ("playing", "Faire de la corde à sauter avec des intestins"),
    ("playing", "Regarder le fromage vieillir"),
    ("playing", "Déchirer la réalité"),
    ("playing", "Jouer du violon avec un nerf"),
    ("playing", "Collectionner des narines"),
    ("playing", "Enterrer des chaises"),
    ("playing", "Arracher des genoux aux nuages"),
    ("playing", "Transformer des mortels en fourchettes"),
    ("playing", "Discuter avec le fromage"),
    ("playing", "Tricoter avec des cheveux"),
    ("playing", "Compter jusqu'à l'infini"),
    ("playing", "Fabriquer du thé dans un crâne"),
    ("playing", "Organiser ses chaussettes"),
    ("playing", "Écouter chanter ses intestins"),
    ("playing", "Admirer le chaos"),
    ("playing", "Philosopher sur les cuillères"),
    ("playing", "Jouer avec le Wabbajack"),
    ("playing", "Insulter Haskill"),
    ("playing", "Défier Jyggalag aux échecs"),
    ("playing", "Peindre avec du sang"),
    ("playing", "Sculpter des papillons"),
    ("playing", "Méditer sur l'absurdité"),
    ("playing", "Rire sans raison"),
    ("playing", "Pleurer de joie"),
    ("playing", "Danser sur la folie"),
]
ENABLE_DAILY_STATUS = os.getenv("ENABLE_DAILY_STATUS", "1") != "0"
daily_status = DiscordDailyStatus(
    bot=bot, bot_id="sheogorath", bot_label="Sheogorath",
    personality_prompt=sheo_data.PERSONALITY_BASE, fallback_activities=_STATUS_FALLBACK,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, openrouter_client=openrouter_client,
    system_prompt_provider=get_current_system_prompt,  # suit l'humeur du jour
    logger=logger, enabled=ENABLE_DAILY_STATUS,
) if DiscordDailyStatus else None


# ═══════════════════════════════════════════════════════════════
# TOOLS — FONCTIONS D'AGENTS (Function Calling)
# ═══════════════════════════════════════════════════════════════

async def tool_wabbajack(user_id_str: str, reason: str, channel):
    """Lance le Wabbajack sur un utilisateur (Tool IA)."""
    try:
        numeric_id = re.search(r'\d+', user_id_str)
        if not numeric_id:
            return f"ERREUR : '{user_id_str}' n'est pas un mortel valide."
        
        user_id = int(numeric_id.group())
        member = await channel.guild.fetch_member(user_id)
        if not member:
            return f"ERREUR : Le mortel {user_id} est introuvable !"
        
        new_nick = random.choice(PUNISHMENT_NICKS)
        duration = DURATION_MAP.get(2, 600)  # Gravité moyenne
        
        await apply_temporary_nickname(member, new_nick, channel, duration_seconds=duration)
        logger.info(f"🪄 [TOOL WABBAJACK] {member.name} puni par l'IA pour : {reason}")
        return f"SUCCÈS : {member.name} a été transformé en '{new_nick}' ! Raison divine : {reason}"
    except Exception as e:
        return f"ERREUR : Ma magie a fait pschiiit ! ({e})"

def tool_set_mood(mood: str):
    """Change l'humeur de Sheogorath (Tool IA)."""
    global current_mood, current_system_prompt
    mood = mood.lower()
    if mood not in sheo_data.MOOD_PROMPTS:
        return f"ERREUR : L'humeur '{mood}' n'existe pas. Choisis : neutral, mania, dementia, bliss."
    
    current_mood = mood
    current_system_prompt = sheo_data.MOOD_PROMPTS[mood]
    logger.info(f"🎭 [TOOL MOOD] Changement d'humeur IA vers : {mood.upper()}")
    return f"SUCCÈS : Je suis maintenant d'humeur {mood.upper()} ! Gare à vous !"

async def tool_mod_reputation(user_id_str: str, points: int, reason: str):
    """Modifie la réputation (Tool IA)."""
    try:
        numeric_id = re.search(r'\d+', user_id_str)
        if not numeric_id:
            return f"ERREUR : '{user_id_str}' est un inconnu."
        
        user_id = int(numeric_id.group())
        if DATABASE_AVAILABLE:
            new_total = add_reputation(user_id, points, reason)
            logger.info(f"⭐ [TOOL REP] {user_id} a reçu {points} points pour : {reason}")
            return f"SUCCÈS : Réputation de {user_id_str} modifiée ({points}). Nouveau total : {new_total}."
        return "ERREUR : Ma mémoire est défectueuse (DB OFF)."
    except Exception as e:
        return f"ERREUR : {e}"

async def tool_start_impersonation(user_id_str: str, channel):
    """Commence l'usurpation d'identité d'un utilisateur (Tool IA)."""
    try:
        numeric_id = re.search(r'\d+', user_id_str)
        if not numeric_id:
            return f"ERREUR : '{user_id_str}' n'est pas une cible valide pour le vol de visage."
        
        user_id = int(numeric_id.group())
        member = await channel.guild.fetch_member(user_id)
        if not member:
            return f"ERREUR : Le mortel {user_id} a disparu de Mundus !"
        
        # Démarrer la session
        start_imposter_session(channel.id, member)
        logger.info(f"🎭 [TOOL IMPOSTEUR] Sheogorath usurpe l'identité de {member.name}")
        return f"SUCCÈS : J'ai volé le visage de {member.name} ! Désormais, je parlerai en son nom pour un temps !"
    except Exception as e:
        return f"ERREUR : {e}"

# Définition des schémas de tools pour Gemini
SHEO_TOOLS_DEFINITION = [
    {
        "function_declarations": [
            {
                "name": "wabbajack",
                "description": "Lance le bâton Wabbajack sur un utilisateur s'il est insolent, ennuyeux, se moque de toi ou par pur caprice.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "user_id": {"type": "STRING", "description": "La mention Discord ou l'ID de l'utilisateur (ex: <@123456789>)"},
                        "reason": {"type": "STRING", "description": "La raison de cette punition"}
                    },
                    "required": ["user_id", "reason"]
                }
            },
            {
                "name": "set_mood",
                "description": "Change ton humeur si la conversation t'amuse ou t'agace.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "mood": {"type": "STRING", "enum": ["neutral", "mania", "dementia", "bliss"], "description": "L'humeur à adopter"}
                    },
                    "required": ["mood"]
                }
            },
            {
                "name": "mod_reputation",
                "description": "Donne (positif) ou retire (négatif) de la réputation à un utilisateur.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "user_id": {"type": "STRING", "description": "La mention Discord de l'utilisateur"},
                        "points": {"type": "INTEGER", "description": "Le nombre de points"},
                        "reason": {"type": "STRING", "description": "La raison de ce changement"}
                    },
                    "required": ["user_id", "points", "reason"]
                }
            },
            {
                "name": "start_identity_theft",
                "description": "Commence à usurper l'identité d'un utilisateur. Tu parleras à sa place avec son nom et son avatar pendant quelques minutes.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "user_id": {"type": "STRING", "description": "La mention Discord ou l'ID de l'utilisateur à imiter."}
                    },
                    "required": ["user_id"]
                }
            }
        ]
    }
]

# Définition pour OpenAI/Grok/Mistral
OPENAI_TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "wabbajack",
            "description": "Lance le bâton Wabbajack sur un utilisateur s'il est insolent, ennuyeux ou se moque de toi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "La mention Discord ou l'ID de l'utilisateur"},
                    "reason": {"type": "string", "description": "La raison de cette punition"}
                },
                "required": ["user_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_mood",
            "description": "Change ton humeur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {"type": "string", "enum": ["neutral", "mania", "dementia", "bliss"]}
                },
                "required": ["mood"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_identity_theft",
            "description": "Commence à usurper l'identité d'un utilisateur (Vol de visage).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "La mention Discord de la cible"}
                },
                "required": ["user_id"]
            }
        }
    }
]



@bot.event
async def on_ready():
    logger.info(f'--------------------------------------------------')
    logger.info(f'🧀 Sheogorath règne sur ce serveur ! (Production)')
    logger.info(f'--------------------------------------------------')
    
    # HEALTH CHECK
    logger.info(f'📊 [HEALTH CHECK] APIs disponibles :')
    logger.info(f'   ✅ Gemini : {len([k for k in GEMINI_API_KEYS if k])} clés')
    logger.info(f'   {"✅" if groq_client else "❌"} Groq')
    logger.info(f'   {"✅" if mistral_client else "❌"} Mistral')
    logger.info(f'   {"✅" if openrouter_client else "❌"} OpenRouter')
    logger.info(f'--------------------------------------------------')
    
    status_loop_sheo.start()
    mood_changer.start()  # Démarrage du changeur d'humeur
    daily_rumor_check_sheo.start()  # Rumeur quotidienne (jours impairs)
    birthday_check_sheo.start()  # Vérification anniversaires
    if daily_bio and not daily_bio_loop_sheo.is_running():
        daily_bio_loop_sheo.start()

    
    global twitch_announcer, twitch_chat, twitch_chat_task
    if TWITCH_AVAILABLE and twitch_announcer is None:
        twitch_announcer = setup_twitch_announcer(
            bot, "sheogorath", logger,
            personality_prompt=sheo_data.PERSONALITY_BASE, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
            openrouter_client=openrouter_client, bot_label="Sheogorath")
        if twitch_announcer:
            twitch_poll_loop.start()

    if TWITCH_CHAT_AVAILABLE and twitch_chat is None:
        profile_bio = getattr(sheo_data, "TWITCH_BIO", None)
        
        # Initialisation du système de Faveur cloisonné pour Twitch
        twitch_faveur_system = FaveurSystem(filename=os.path.join(DATA_DIR, "sheo_faveurs_twitch.json"))
        
        # Commandes Twitch Sheogorath
        def cmd_sheo(author: str, args: str) -> str:
            quotes = [
                "Le fromage ! C'est pour moi ! Tout pour moi !",
                "Est-ce que tu as déjà fait de la corde à sauter avec des intestins ? C'est divertissant !",
                "Haskill ! Haskill ! Où est mon wabbajack ?",
                "Je suis le Prince de la Folie. Et toi, tu es un vermisseau distrayant.",
                "Je déteste les papillons. Non, je les adore. Je ne sais plus !"
            ]
            return f"🧀 {random.choice(quotes)}"
            
        def cmd_folie(author: str, args: str) -> str:
            quotes = [
                "La folie est une bénédiction, mortel. Elle libère l'esprit des chaînes de la logique !",
                "Un peu de démence, un zeste de mania... et paf ! Ça fait des chocapic daedriques !",
                "Ne me parle pas de Jyggalag et de son ordre ennuyeux ! Le chaos règne !",
                "Est-ce que ta tête tourne ? C'est le début de la sagesse !"
            ]
            return f"🌀 {random.choice(quotes)}"

        def cmd_fromage(author: str, args: str) -> str:
            user_id = abs(hash(author)) % (10**9)
            result = jeu_fromage(user_id)
            effects_text = {
                "folie": "Tu ressens la folie monter en toi ! EXCELLENT !",
                "puissance": "Une puissance daedrique coule dans tes veines !",
                "hallucination": "Les murs commencent à fondre... c'est normal.",
                "joie": "Tu te sens inexplicablement heureux ! Comme un papillon !",
                "mélancolie": "Une tristesse profonde t'envahit... mais c'est si délicieux.",
                "maladie": "Urghhh... Ce fromage était POURRI ! Dommage !",
                "confusion": "Attends, tu as mangé quoi déjà ? C'était quoi la question ?",
            }
            effect_desc = effects_text.get(result['effet'], "Un effet mystérieux...")
            return f"🧀 @{author} mange un {result['nom']} ! {effect_desc} (Effet : {result['points']} réputation)"

        def cmd_faveur(author: str, args: str) -> str:
            pts = twitch_faveur_system.get_faveur(author)
            rank = twitch_faveur_system.get_rank(author)
            return f"@{author}, tu as {pts} points de Faveur du Prince. Ton rang : {rank['emoji']} {rank['name']} !"

        def cmd_classement(author: str, args: str) -> str:
            top = twitch_faveur_system.get_leaderboard(limit=10)
            if not top:
                return "Le classement de ma Faveur est vide, bande de mortels insignifiants !"
            lines = []
            for i, entry in enumerate(top, 1):
                name = entry["name"]
                pts = entry["points"]
                rank = entry["rank"]
                lines.append(f"{i}. {name} ({pts} pts, {rank['emoji']} {rank['name']})")
            return f"Voici les courtisans qui ont le plus amusé le Prince de la Folie : " + " | ".join(lines)

        async def cmd_decret(author: str, args: str) -> str:
            if not is_feature_enabled("sheogorath", "decret_enabled", default=True):
                return "Le Prince a rangé ses décrets dans un fromage. Reviens plus tard, mortel."  # en personnage
            prompt = (
                f"Rédige un DÉCRET DAEDRA de la Folie visant @{author}. "
                f"Style Sheogorath : obsessionnel (fromage, papillons, intestins), absurde et menaçant. "
                f"Écris une seule phrase de décret courte (max 200 caractères), en personnage, sans guillemets ni didascalies."
            )
            from shared.llm_cascade import generate_response
            from shared.smart_router import RequestType
            try:
                text = await generate_response(
                    routing={"type": RequestType.TEXT, "reason": "twitch_decret"},
                    system_prompt=sheo_data.PERSONALITY_BASE,
                    transcript="",
                    user_message=prompt,
                    conversation_history=[],
                    media_data=None,
                    mime_type="",
                    key_manager=key_manager,
                    mistral_client=mistral_client,
                    groq_client=groq_client,
                    openrouter_client=openrouter_client,
                    bot_label="Sheogorath",
                    temperature=1.0,
                    max_tokens=80
                )
                if text:
                    text = " ".join(text.split()).strip()
                    from shared.twitch_chat import TwitchChatBot
                    text = TwitchChatBot._strip_stage_directions(text)
                    text = text.strip('"\'')
                    return text[:450]
            except Exception as e:
                logger.error(f"❌ [TWITCH_CMD_DECRET] Erreur LLM : {e}")

            fallback_decrees = [
                f"Par décret de la folie, @{author} est condamné à manger du roquefort périmé pendant trois millénaires !",
                f"Je décrète que les oreilles de @{author} appartiennent désormais aux papillons de démence !",
                f"Par ma volonté, @{author} doit marcher à reculons jusqu'à la fin de la journée sous peine de Wabbajack !"
            ]
            return random.choice(fallback_decrees)

        # Anti-farm : 1 gain de Faveur max / 60 s / viewer (parité avec Johnny / try_award).
        _twitch_faveur_cooldowns = {}

        async def twitch_passive_handler(author: str, text: str) -> str | None:
            import time as _time
            _now = _time.time()
            _key = author.lower()
            if _now - _twitch_faveur_cooldowns.get(_key, 0) < 60.0:
                return None
            faveur_points = twitch_faveur_system.check_message_for_faveur(text)
            if faveur_points > 0:
                _twitch_faveur_cooldowns[_key] = _now
                total, old_rank, new_rank, rank_up = twitch_faveur_system.add_faveur(
                    author, author, faveur_points
                )
                if rank_up:
                    return random.choice(RANK_UP_MESSAGES).format(
                        user=f"@{author}",
                        rank=new_rank["name"],
                        emoji=new_rank["emoji"]
                    )
                elif random.random() < 0.30:
                    return random.choice(FAVEUR_GAIN_MESSAGES).format(
                        pts=faveur_points, total=total
                    )
            return None

        # Construction des commandes et alias
        commands = {
            "sheo": cmd_sheo,
            "folie": cmd_folie,
            "fromage": cmd_fromage,
            "faveur": cmd_faveur,
            "decret": cmd_decret,
            "classement": cmd_classement
        }
        command_aliases = {
            "decree": "decret",
            "décret": "decret",
            "cheese": "fromage",
            "favor": "faveur",
            "folly": "folie",
            "leaderboard": "classement"
        }

        twitch_chat = setup_twitch_chat(
            "sheogorath", logger,
            personality_prompt=sheo_data.PERSONALITY_BASE, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
            openrouter_client=openrouter_client, bot_label="Sheogorath",
            system_prompt_provider=get_current_system_prompt,
            profile_bio=profile_bio,
            enable_events=True,
            enable_interjections=False,
            interjection_chance=0.03,
            interjection_min_interval=600.0,
            enable_greetings=False,
            enable_viewer_memory=True,
            viewer_memory_max=8,
            enable_eventsub=True,
            eventsub_reward_map={
                "Décret": "decret",
                "Fromage": "fromage",
                "Folie": "folie"
            },
            commands=commands,
            command_aliases=command_aliases,
            passive_handler=twitch_passive_handler,
            enable_voice_listen=False
        )
        if twitch_chat:
            twitch_chat.extra_recent_provider = lambda: [r for hist in response_memory.memory.values() for r in hist][-6:]
            twitch_chat_task = asyncio.create_task(twitch_chat.run())

    daily_backup_check.start()  # Backup automatique
    check_missed_mentions_sheo.start()  # Détection mentions manquées
    if not decree_cleanup_loop.is_running():
        decree_cleanup_loop.start()  # Nettoyage des rôles de décret expirés/orphelins
    # auto_riddle_loop_sheo.start()  # Transféré à M'aiq
    
    # VOICE TTS — Démarrage du check d'inactivité
    if VOICE_AVAILABLE:
        voice_idle_check.start()
        logger.info(f"🎤 [VOICE] Système TTS Piper activé (auto-voice: {VOICE_AUTO_CHANCE*100:.0f}%)")
    else:
        logger.info("🔇 [VOICE] TTS désactivé (Piper non configuré)")
    
    # INITIALISATION DES COMMANDES SLASH
    if DATABASE_AVAILABLE:
        setup_slash_commands(bot, "Sheogorath")
        await sync_slash_commands(bot)
        logger.info(f"✅ [SLASH] Commandes slash initialisées")
        
    # INITIALISATION DES MINI-JEUX
    if DATABASE_AVAILABLE and GAMES_AVAILABLE:
        setup_games(bot, logger, PERSONA)
        logger.info(f"✅ [GAMES] Mini-jeux initialisés")
    
    # RESUME PUNISHMENTS
    data = load_punishments()
    now = datetime.now().timestamp()
    to_remove = []
    
    logger.info(f"🕵️ [PERSISTENCE] Vérification des punitions en cours ({len(data)} trouvées)...")
    
    for user_id, info in data.items():
        remaining = info["end_time"] - now
        guild = bot.get_guild(info["guild_id"])
        if not guild:
            logger.warning(f"⚠️ [PERSISTENCE] Guild {info['guild_id']} introuvable pour user {user_id}")
            to_remove.append(user_id)
            continue
        
        # fetch_member au lieu de get_member (le cache peut être vide au démarrage)
        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.HTTPException) as e:
            to_remove.append(user_id)
            continue
        
        if remaining > 0:
            logger.info(f"⏳ [RESUME] {member.name} est toujours puni pour {int(remaining)}s.")
            
            # Simple waiter task — utilise des paramètres par défaut pour capturer les valeurs
            async def waiter(m_id=member.id, g_id=guild.id, dur=remaining, orig=info["original_nick"], uid=user_id):
                await asyncio.sleep(dur)
                try:
                    d = load_punishments()
                    if uid in d:
                        g = bot.get_guild(g_id)
                        if g:
                            curr = await g.fetch_member(m_id)
                            await curr.edit(nick=orig)
                            logger.info(f"🔄 [RESUME END] Pseudo de {curr.name} rétabli : {orig or '(nom original)'}")
                        del d[uid]
                        save_punishments(d)
                except discord.Forbidden:
                    logger.warning(f"⚠️ [RESUME END] Permissions insuffisantes pour restaurer user {uid}")
                except discord.NotFound:
                    logger.warning(f"⚠️ [RESUME END] Membre {uid} non trouvé (a quitté ?)")
                except Exception as e:
                    logger.error(f"❌ [RESUME END] Erreur rétablissement: {e}")

            asyncio.create_task(waiter())
            
        else:
            # Expired while offline
            logger.info(f"✅ [EXPIRED] La punition de {member.name} a expiré pendant l'arrêt. Rétablissement immédiat.")
            try:
                await member.edit(nick=info["original_nick"])
                logger.info(f"✅ [EXPIRED] Pseudo restauré: {member.name} → {info['original_nick'] or '(nom original)'}")
            except discord.Forbidden:
                logger.warning(f"⚠️ [EXPIRED] Permissions insuffisantes pour restaurer {member.name}")
            except Exception as e:
                logger.error(f"❌ [EXPIRED] Erreur restauration {member.name}: {e}")
            to_remove.append(user_id)
    
    if to_remove:
        data = load_punishments()
        for uid in to_remove:
            if uid in data:
                del data[uid]
        save_punishments(data)

@tasks.loop(minutes=5)
async def decree_cleanup_loop():
    """Filet anti-redémarrage : supprime les rôles de décret expirés/orphelins.
    Le premier tick s'exécute peu après on_ready (cf. before_loop) → l'orphelin
    actuel est nettoyé en quelques secondes."""
    for guild in bot.guilds:
        try:
            await cleanup_old_decree_roles(guild)
        except Exception as e:
            logger.error(f"❌ [DECRET] Erreur boucle de nettoyage ({guild.id}): {e}")

@decree_cleanup_loop.before_loop
async def before_decree_cleanup():
    await bot.wait_until_ready()

@tasks.loop(seconds=90)
async def twitch_poll_loop():
    if twitch_announcer:
        await twitch_announcer.tick()

@twitch_poll_loop.before_loop
async def before_twitch_poll():
    await bot.wait_until_ready()

@tasks.loop(minutes=30)
async def status_loop_sheo():
    global current_activity_text
    activity = None
    if daily_status:
        await daily_status.ensure_daily_status()  # régénère au changement de jour, sinon cache
        activity = daily_status.pick_activity()
    if activity is None:  # module absent/désactivé : repli sur la liste fallback
        t, name = random.choice(_STATUS_FALLBACK)
        activity = discord.Activity(
            type=getattr(discord.ActivityType, t, discord.ActivityType.playing),
            name=name)
    current_activity_text = activity.name  # réutilisé dans les prompts (« ce que tu fais »)
    await bot.change_presence(activity=activity)

# AUTO-ÉNIGMES CHAOTIQUES (DÉSACTIVÉ - TRANSFÉRÉ À M'AIQ)
# (Code supprimé pour transfert)


daily_rumor_published_sheo = False

@tasks.loop(hours=1)
async def daily_rumor_check_sheo():
    """Vérifie si c'est le moment de publier la rumeur quotidienne (jours impairs uniquement)."""
    global daily_rumor_published_sheo
    
    now = datetime.now()
    day = now.day
    hour = now.hour
    
    # Reset à minuit
    if hour == 0:
        daily_rumor_published_sheo = False
        return
    
    if day % 2 == 0:
        return  # Jour pair = M'aiq publie, pas nous
    
    # Fenêtre horaire : 14h-22h
    if hour < 14 or hour >= 22:
        return
    
    # Déjà publié ?
    if daily_rumor_published_sheo:
        return
    
    # Probabilité 1/8 par heure
    if random.random() > 0.125:
        return
    
    daily_rumor_published_sheo = True
    await publish_daily_rumor_sheo()

async def publish_daily_rumor_sheo(target_channel=None, target_user=None):
    """Publie une rumeur chaotique (Décret Divin). Si target_channel/user sont None, ils sont choisis au hasard."""
    if not is_feature_enabled("sheogorath", "decret_enabled", default=True):
        logger.info("🚫 [DÉCRET] Désactivé via dashboard — publication auto ignorée.")
        return
    if not target_channel:
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if "taverne" in channel.name.lower() and "bot" in channel.name.lower():
                    target_channel = channel
                    break
            if target_channel:
                break
    
    if not target_channel:
        logger.warning("❌ [RUMEUR SHEO] Canal introuvable.")
        return
    
    if not target_user:
        # Collecter les utilisateurs récents
        active_users = []
        try:
            async for msg in target_channel.history(limit=100):
                if not msg.author.bot and msg.author not in active_users:
                    active_users.append(msg.author)
                if len(active_users) >= 10:
                    break
        except Exception as e:
            logger.error(f"❌ [RUMEUR SHEO] Erreur collecte: {e}")
            return
        
        if not active_users:
            logger.warning("❌ [RUMEUR SHEO] Aucun utilisateur actif.")
            return
        target_user = random.choice(active_users)
    
    # Générer via LLM
    rumor_prompt = (
        f"SYSTEM: {sheo_data.PERSONALITY_BASE}\n"
        f"INSTRUCTION: Publie un DÉCRET DAEDRA de la Folie sur {target_user.display_name}. "
        "Style Sheogorath : menaçant, absurde, obsessionnel (fromage, papillons, intestins).\n"
        "TU DOIS FOURNIR DEUX CHOSES :\n"
        "1. Un TITRE de noblesse ridicule entre balises <title>TITRE ICI</title> (max 32 caractères).\n"
        "2. Le TEXTE du décret (1-2 phrases).\n"
        f"IMPORTANT: Mentionne '<@{target_user.id}>' dans le texte."
    )
    
    full_response = None
    
    # Try Grok (via OpenRouter) first
    if openrouter_client:
        try:
            chat = openrouter_client.chat.completions.create(
                model="cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
                messages=[{"role": "user", "content": rumor_prompt}],
                temperature=1.0,
                max_tokens=300
            )
            full_response = chat.choices[0].message.content
        except Exception as e:
            logger.warning(f"⚠️ [RUMEUR SHEO] Grok (OpenRouter) failed: {e}")
    
    # Fallback Gemini
    if not full_response:
        api_key = key_manager.get_key("gemini")
        if api_key:
            try:
                client = get_safe_genai_client(api_key=api_key, http_options={'api_version': 'v1beta'})
                resp = client.models.generate_content(model='gemini-2.5-flash', contents=rumor_prompt)
                full_response = resp.text
            except Exception as e:
                logger.warning(f"⚠️ [RUMEUR SHEO] Gemini failed: {e}")
    
    if not full_response:
        # Repli (les 2 IA ont échoué) : décrets variés DANS la voix de Sheogorath,
        # tirés au hasard pour éviter la répétition.
        uid = target_user.id
        _fallback_decrees = [
            f"<title>Fromager des Abysses</title> MORTEL ! Par Ma volonté capricieuse, <@{uid}> est nommé Grand Fromager des Abysses ! Que ton âme sente le roquefort pour l'éternité ! 🧀",
            f"<title>Compteur de Papillons</title> Ohhh, délicieux ! <@{uid}> devra désormais compter chaque papillon de Mundus. Un seul oubli et tes intestins deviendront des serpentins ! 🦋",
            f"<title>Porteur de Cuillères</title> DÉCRET ! <@{uid}> est sacré Porteur Officiel de Mes Cuillères Sales. Lèche-les avec dévotion, ou danse jusqu'à la folie !",
            f"<title>Duc des Chaussettes</title> Hahaha ! <@{uid}> règne désormais sur Mes Chaussettes Perdues. Un royaume puant, mais ô combien glorieux !",
            f"<title>Murmureur de Légumes</title> Par la Démence ! <@{uid}> chuchotera des secrets aux navets jusqu'à la fin des temps. Ils répondront. Ils répondent TOUJOURS.",
            f"<title>Gardien du Chaos</title> MWAHAHA ! <@{uid}> est promu Gardien de Mon Chaos. Tâche impossible, châtiment garanti, fromage en option ! 🧀",
        ]
        full_response = random.choice(_fallback_decrees)
    
    # Extraction du Titre et du Texte
    title = "Sujet de la Folie"
    title_match = re.search(r"<title>(.*?)</title>", full_response, re.IGNORECASE | re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()
        clean_text = full_response.replace(title_match.group(0), "").strip()
    else:
        clean_text = full_response
    
    # Limitation taille titre pour Discord (32 chars)
    if len(title) > 32:
        title = title[:29] + "..."

    # 1. GÉNÉRATION DE L'IMAGE
    # Les mentions Discord (<@id>) sont du texte brut dans une image : on les
    # résout en nom lisible. La mention réelle (le ping) reste dans le message.
    def _resolve_mentions_for_image(txt):
        guild = target_channel.guild
        def repl_user(m):
            uid = int(m.group(1))
            member = guild.get_member(uid) if guild else None
            return f"@{member.display_name}" if member else (
                f"@{target_user.display_name}" if uid == target_user.id else "@mortel")
        def repl_role(m):
            role = guild.get_role(int(m.group(1))) if guild else None
            return f"@{role.name}" if role else "@rôle"
        txt = re.sub(r"<@!?(\d+)>", repl_user, txt)
        txt = re.sub(r"<@&(\d+)>", repl_role, txt)
        txt = re.sub(r"<a?:(\w+):\d+>", r"\1", txt)  # emoji custom → son nom
        return txt

    image_text = _resolve_mentions_for_image(clean_text)
    image_buf = generate_decree_image(image_text, title=title.upper())
    
    # 2. APPLICATION DU RÔLE
    await apply_decree_role(target_channel.guild, target_user, title)
    
    # 3. ENVOI
    if image_buf:
        file = discord.File(fp=image_buf, filename=f"decret_{target_user.id}.png")
        await target_channel.send(
            content=f"📢 **[DÉCRET DAEDRA]**\n{clean_text}",
            file=file
        )
    else:
        await target_channel.send(f"📢 **[DÉCRET DAEDRA]**\n{clean_text}")

    logger.info(f"🧀 [DÉCRET SHEO PUBLIÉ] Cible: {target_user.display_name} | Titre: {title}")

@bot.command(name="decret", aliases=["decree"])
@commands.has_permissions(administrator=True)
async def decret_cmd(ctx, target: discord.Member = None):
    """Force la publication d'un décret impérial (Admin only pour test)."""
    if not is_feature_enabled("sheogorath", "decret_enabled", default=True):
        await ctx.send("🚫 Le Prince a suspendu ses décrets… pour l'instant. (désactivé via le dashboard)")
        return
    await publish_daily_rumor_sheo(target_channel=ctx.channel, target_user=target)

@tasks.loop(minutes=5)
async def mood_changer():
    """Change l'humeur de Sheogorath toutes les 5 minutes (bascule GARANTIE)."""
    global current_mood, current_system_prompt
    moods = ["mania", "dementia", "neutral", "bliss"]
    old_mood = current_mood
    # Bascule garantie : on tire parmi les AUTRES humeurs → l'humeur change vraiment
    # à chaque tour (sinon random.choice retomberait 1 fois sur 3 sur la même).
    choices = [m for m in moods if m != current_mood] or moods
    current_mood = random.choice(choices)
    current_system_prompt = sheo_data.MOOD_PROMPTS[current_mood]
    
    mood_messages = {
        "mania": "🌈 MANIA ! Les couleurs explosent ! La joie règne ! (Prompt: CRÉATIF/JOYEUX)",
        "dementia": "🌑 DÉMENCE... Les ténèbres murmurent... La paranoïa grandit... (Prompt: SOMBRE/CRUEL)",
        "neutral": "⚖️ Équilibre retrouvé. Entre folie et folie. Toujours la folie. (Prompt: CLASSIQUE)",
        "bliss": "🎁 BLISS ! Une euphorie joviale et chaleureuse s'installe... (Prompt: JOVIAL/LUCIDE)"
    }
    
    if old_mood != current_mood:
        logger.info(f"🎭 [MOOD CHANGE] {old_mood} → {current_mood} | {mood_messages[current_mood]}")

# TÂCHES PLANIFIÉES - ANNIVERSAIRES ET BACKUP

@tasks.loop(hours=12)
async def birthday_check_sheo():
    """Vérifie les anniversaires tous les 12h."""
    if DATABASE_AVAILABLE:
        await check_and_send_birthdays(bot, "Sheogorath")

@tasks.loop(hours=24)
async def daily_backup_check():
    """Backup quotidien à 3h du matin."""
    from datetime import datetime
    if datetime.now().hour == 3:
        try:
            from backup_manager import create_backup
            create_backup()
            logger.info("✅ [BACKUP] Sauvegarde quotidienne effectuée")
        except Exception as e:
            logger.error(f"❌ [BACKUP] Erreur: {e}")

@tasks.loop(hours=1)
async def daily_bio_loop_sheo():
    if daily_bio:
        await daily_bio.ensure_daily_bio()

@daily_bio_loop_sheo.before_loop
async def before_daily_bio_sheo():
    await bot.wait_until_ready()


# DÉTECTION DES MENTIONS MANQUÉES

@tasks.loop(minutes=2)
async def check_missed_mentions_sheo():
    """Vérifie si quelqu'un a mentionné Sheogorath sans obtenir de réponse."""
    global checked_messages_sheo
    
    name_triggers = ["sheogorath", "sheo", "prince de la folie", "dieu fou", "madgod"]
    
    for guild in bot.guilds:
        found_one = False  # Limite : 1 rattrapage par cycle par guild
        for channel in guild.text_channels:
            if found_one:
                break
            
            # Vérifier les permissions
            perms = channel.permissions_for(guild.me)
            if not perms.read_messages or not perms.send_messages or not perms.read_message_history:
                continue
            
            try:
                messages = []
                async for msg in channel.history(limit=20):
                    messages.append(msg)
                
                # Parcourir les messages (du plus ancien au plus récent)
                messages.reverse()
                
                for i, msg in enumerate(messages):
                    # Skip si déjà vérifié, si c'est un bot, ou si trop vieux (> 10 min)
                    if msg.id in checked_messages_sheo:
                        continue
                    if msg.author.bot:
                        continue
                    
                    age = (datetime.now(msg.created_at.tzinfo) - msg.created_at).total_seconds() if msg.created_at.tzinfo else (datetime.utcnow() - msg.created_at).total_seconds()
                    if age > 600 or age < 30:  # Ignorer > 10min ou < 30s (laisser le temps au on_message)
                        checked_messages_sheo.add(msg.id)
                        continue
                    
                    # Détecter si on est mentionné
                    is_mentioned = bot.user.mentioned_in(msg)
                    content_lower = msg.content.lower()
                    is_name_mentioned = any(name in content_lower for name in name_triggers)
                    
                    # Si un AUTRE bot/utilisateur est mentionné mais PAS nous, ignorer
                    if msg.mentions and not is_mentioned:
                        checked_messages_sheo.add(msg.id)
                        continue
                    
                    if not is_mentioned and not is_name_mentioned:
                        checked_messages_sheo.add(msg.id)
                        continue
                    
                    # Vérifier si le bot a déjà répondu après ce message
                    bot_replied = False
                    for later_msg in messages[i+1:]:
                        if later_msg.author.id == bot.user.id:
                            bot_replied = True
                            break
                    
                    if bot_replied:
                        checked_messages_sheo.add(msg.id)
                        continue
                    
                    # MENTION MANQUÉE DÉTECTÉE !
                    logger.info(f"🔔 [MENTION MANQUÉE] {msg.author.name} a parlé à Sheogorath il y a {int(age)}s sans réponse !")
                    
                    # Générer une réponse tardive
                    user_text = msg.content.replace(f'<@{bot.user.id}>', '').strip()
                    if not user_text:
                        user_text = "(Le mortel t'a juste mentionné sans rien dire.)"
                    
                    late_prompt = (
                        f"SYSTEM: {get_current_system_prompt()}\n"
                        f"CONTEXTE: Tu viens de te rendre compte que {msg.author.name} t'a parlé il y a quelques minutes "
                        f"mais tu n'as PAS répondu (tu étais occupé à {current_activity_text}). "
                        f"Son message était : '{user_text}'.\n"
                        f"INSTRUCTION: Réponds-lui maintenant avec une excuse chaotique et folle (tu étais distrait par un fromage, "
                        f"un papillon, ou tu comptais tes dents). Puis réponds à son message. "
                        f"Sois drôle et en personnage. 2-3 phrases max."
                    )
                    
                    response_text = None
                    
                    # Essayer les APIs dans l'ordre
                    if groq_client:
                        try:
                            chat = groq_client.chat.completions.create(
                                messages=[{"role": "user", "content": late_prompt}],
                                model="llama-3.3-70b-versatile",
                                temperature=0.95,
                                max_tokens=200
                            )
                            response_text = chat.choices[0].message.content
                        except Exception as e:
                            logger.warning(f"⚠️ [MISSED MENTION] Groq fail: {e}")
                    
                    if not response_text:
                        api_key = key_manager.get_key("gemini")
                        if api_key:
                            try:
                                gclient = get_safe_genai_client(api_key=api_key)
                                resp = gclient.models.generate_content(model='gemini-2.5-flash', contents=late_prompt)
                                response_text = resp.text
                            except Exception as e:
                                error_code = getattr(e, "code", getattr(e, "status_code", 0))
                                key_manager.report_error("gemini", api_key, error_code)
                                logger.warning(f"⚠️ [MISSED MENTION] Gemini fail: {e}")
                    
                    if not response_text:
                        # Fallback statique
                        fallbacks = [
                            f"🧀 Ah ! <@{msg.author.id}> ! Tu m'avais parlé ?! J'étais occupé à compter mes orteils... j'en ai trouvé 11 cette fois ! Qu'est-ce que tu voulais déjà ?",
                            f"🦋 OH ! <@{msg.author.id}> ! Pardon, j'étais occupé à compter mes chaussettes invisibles. L'une d'elles essayait de s'enfuir ! Tu disais ?",
                            f"👁️ <@{msg.author.id}> ! Je t'ai entendu, mortel ! J'étais juste... dans une autre dimension. C'est compliqué, tu comprendrais pas. BREF ! Tu voulais quoi ?"
                        ]
                        response_text = random.choice(fallbacks)
                    
                    # Nettoyage LLM
                    for artifact in ["[INST]", "[/INST]", "</s>", "<s>", "<<SYS>>", "<</SYS>>"]:
                        response_text = response_text.replace(artifact, "")
                    response_text = response_text.strip()
                    
                    try:
                        await msg.reply(response_text)
                        logger.info(f"✅ [MENTION MANQUÉE] Répondu à {msg.author.name} en retard !")
                    except Exception as e:
                        logger.error(f"❌ [MENTION MANQUÉE] Erreur envoi: {e}")
                    
                    checked_messages_sheo.add(msg.id)
                    found_one = True
                    break  # 1 seul rattrapage par cycle
                    
            except Exception as e:
                logger.error(f"❌ [MISSED CHECK] Erreur canal {channel.name}: {e}")
    
    # Nettoyer le cache (garder les 200 derniers)
    if len(checked_messages_sheo) > MAX_CHECKED_CACHE:
        checked_messages_sheo = set(list(checked_messages_sheo)[-MAX_CHECKED_CACHE:])

@check_missed_mentions_sheo.before_loop
async def before_missed_mentions_sheo():
    await bot.wait_until_ready()

# ÉVÉNEMENTS SERVEUR - BIENVENUE ET DÉPART

@bot.event
async def on_member_join(member):
    """Message de bienvenue quand un membre rejoint."""
    if DATABASE_AVAILABLE:
        await handle_member_join(bot, member, "Sheogorath")

@bot.event
async def on_member_remove(member):
    """Message de départ (si le membre a interagi)."""
    if DATABASE_AVAILABLE:
        await handle_member_remove(bot, member, "Sheogorath")

# COMMANDES SPÉCIALES

@bot.command(name="quete")
async def quest_cmd(ctx):
    """
    Donne une quête absurde à l'utilisateur.
    """
    quest = random.choice(sheo_data.QUESTS)
    embed = discord.Embed(
        title="📜 UNE TÂCHE DIGNE D'UN FOU !",
        description=f"{quest}\n\nFais-le pour ma gloire, ou pour le fromage !",
        color=0x9b59b6 # Violet Sheogorath
    )
    embed.set_footer(text="Sheogorath vous observe... probablement.")
    await ctx.send(content=ctx.author.mention, embed=embed)

# MINI-JEUX DE SHEOGORATH

# MINI-JEUX DE SHEOGORATH

# (Commandes énigmatiques transférées à M'aiq)

@bot.command(name="fromage")
async def fromage_cmd(ctx):
    """Le jeu du fromage mystérieux !"""
    if not DATABASE_AVAILABLE:
        await ctx.send("🧀 Le fromage n'est pas disponible pour le moment !")
        return
    
    # Tracker l'utilisateur
    get_or_create_user(ctx.author.id, ctx.author.name, ctx.author.display_name)
    
    result = jeu_fromage(ctx.author.id)
    
    effects_text = {
        "folie": "Tu ressens la folie monter en toi ! EXCELLENT !",
        "puissance": "Une puissance daedrique coule dans tes veines !",
        "hallucination": "Les murs commencent à fondre... c'est normal.",
        "joie": "Tu te sens inexplicablement heureux ! Comme un papillon !",
        "mélancolie": "Une tristesse profonde t'envahit... mais c'est si délicieux.",
        "maladie": "Urghhh... Ce fromage était POURRI ! Dommage !",
        "confusion": "Attends, tu as mangé quoi déjà ? C'était quoi la question ?",
    }
    
    embed = discord.Embed(
        title=f"🧀 {result['nom']}",
        description=effects_text.get(result['effet'], "Un effet mystérieux..."),
        color=0xFFD700 if result['points'] > 0 else 0x8B0000
    )
    
    if result['points'] > 0:
        embed.add_field(name="Effet", value=f"**+{result['points']}** réputation", inline=True)
    elif result['points'] < 0:
        embed.add_field(name="Effet", value=f"**{result['points']}** réputation 💀", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="wabbajack")
async def wabbajack_cmd(ctx, target: discord.Member = None):
    """
    Lance le Wabbajack sur une cible (ou soi-même).
    Effets : Nickname, Réaction, Message RP
    """
    if not target:
        target = ctx.author

    effects = [
        "nickname", "blessing", "curse", "cheese", "polymorph"
    ]
    effect = random.choice(effects)
    
    # 1. NICKNAME CHANGE (Si possible)
    if effect == "nickname":
        new_nicks = ["Poulet", "Fromage", "Chaise", "Cuillère", "Nuage", "Saucisse", "Grummite", "Pied", "Chaussette"]
        new_nick = random.choice(new_nicks)
        try:
            await target.edit(nick=new_nick)
            await ctx.send(f"🪄 **WABBAJACK !** {target.mention} est maintenant un **{new_nick}** ! (Ou du moins, il en porte le nom)")
        except discord.Forbidden:
            await ctx.send(f"🪄 **WABBAJACK !** J'ai voulu te renommer en **{new_nick}**, mais tes gardes du corps (permissions) m'en empêchent ! Ennuyeux !")
        except Exception as e:
            await ctx.send(f"🪄 **WABBAJACK !** Le sort a raté... C'est sûrement la faute d'Haskill.")

    # 2. MALEDICTION DROLE
    elif effect == "curse":
        curses = [
            "Tu sentiras le fromage rance pendant 47 jours !",
            "Tes chaussettes seront toujours humides !",
            "Tu entendras Haskill soupirer dans ton sommeil !",
            "Tous tes aliments auront le goût de craie !"
        ]
        await ctx.send(f"🌩️ **MALÉDICTION !** {target.mention}, {random.choice(curses)}")

    # 3. BENEDICTION ABSURDE
    elif effect == "blessing":
        blessings = [
            "Je t'offre ce nuage ! Il est un peu collant, mais c'est un bon nuage.",
            "Tu as gagné une dents de géant ! Ne me demande pas où je l'ai trouvée.",
            "Voici une bénédiction : tes cheveux pousseront vers l'intérieur ! Ah, non, c'est une malédiction ça...",
            "Que le fromage soit toujours coulant dans ton assiette !"
        ]
        await ctx.send(f"✨ **BÉNÉDICTION !** {target.mention}, {random.choice(blessings)}")

    # 4. TRANSFORMATION EN FROMAGE
    elif effect == "cheese":
        await ctx.send(f"🧀 **POUF !** {target.mention} est maintenant une magnifique meule de fromage ! C'est un honneur, crois-moi !")
    
    # 5. POLYMORPH (RP)
    elif effect == "polymorph":
        mobs = ["un Scamp", "un Galopin", "une poule", "un coussin", "une tarte aux pommes"]
        await ctx.send(f"🦎 **MÉTAMORPHOSE !** {target.mention} est désormais {random.choice(mobs)} ! \nNe l'écrasez pas ! (Ou si, c'est drôle aussi)")

# Punitions importées de sheo_punishments.py
# (apply_temporary_nickname, PUNISHMENT_NICKS, get_insult_severity, DURATION_MAP)

# ═══════════════════════════════════════════════════════════════
# COMMANDES VOCALES — TTS PIPER (Open Source)
# ═══════════════════════════════════════════════════════════════

@bot.command(name="rejoins", aliases=["join", "vocal"])
async def join_voice_cmd(ctx):
    """Sheogorath rejoint le canal vocal de l'utilisateur."""
    if not VOICE_AVAILABLE:
        await ctx.send("🔇 Ma voix divine est en maintenance, mortel ! (TTS non configuré)")
        return
    await cmd_join_voice(ctx)

@bot.command(name="quitte", aliases=["leave", "degage"])
async def leave_voice_cmd(ctx):
    """Sheogorath quitte le canal vocal."""
    if not VOICE_AVAILABLE:
        await ctx.send("🔇 Je ne suis pas dans un canal vocal, crétin !")
        return
    await cmd_leave_voice(ctx)

@bot.command(name="voix", aliases=["parle", "speak", "dis"])
async def speak_cmd(ctx, *, text: str = None):
    """Sheogorath parle dans le vocal !
    Usage: !voix [texte]
    Sans texte, il génère une phrase aléatoire."""
    if not VOICE_AVAILABLE:
        await ctx.send("🔇 Ma voix divine est en maintenance, mortel !")
        return
    
    if not ctx.author.voice:
        await ctx.send("🔇 Rejoins un canal vocal d'abord, imbécile !")
        return
    
    if not text:
        # Génère une phrase random
        text = get_smart_string_response_v2("parle", ctx.guild.id)
    
    async with ctx.typing():
        logger.info(f"🎤 [CMD VOIX] Demande de voix par {ctx.author.name}: {text}")
        success = await send_voice_response(bot, ctx, text, force=True)
        
    if not success:
        await ctx.send("🌀 Ma voix s'est perdue entre les dimensions d'Oblivion... Réessaie, mortel !")
    else:
        await ctx.send(f"🎤 *Le Prince de la Folie a parlé !*")

@tasks.loop(seconds=60)
async def voice_idle_check():
    """Vérifie périodiquement les connexions vocales inactives."""
    if VOICE_AVAILABLE:
        await disconnect_if_idle(bot)

@voice_idle_check.before_loop
async def before_voice_idle_check():
    await bot.wait_until_ready()


@bot.command(name="solution", aliases=["soluce"])
async def solution_cmd(ctx):
    """Ferme l'énigme de M'aiq (Sheogorath tranche)."""
    if not DATABASE_AVAILABLE:
        await ctx.send("🧀 Les entrailles du serveur sont indisponibles !")
        return
    
    active_riddle = get_maiq_riddle(ctx.channel.id)
    if not active_riddle:
        await ctx.send("Il n'y a pas d'énigme en cours, espèce de fou ! Tu entends des voix ? 🤪")
        return

    # PLUS DE VÉRIFICATION PARTICIPANT : Sheogorath peut intervenir à tout moment
    logger.info(f"🧀 [SOLUCE CMD] {ctx.author.name} demande la soluce. Énigme active trouvée.")
    
    is_impossible = active_riddle.get("is_impossible", 0) == 1
    
    if is_impossible:
        # TRUTH REVELATION
        await ctx.send(
            "🧀 **AH ! JE VOUS L'AVAIS DIT !**\n"
            "M'aiq vous a menti ! Il n'y a **PAS** de réponse ! C'est un chat, que croyiez-vous ? 🤪\n"
            "Je ferme cette farce. Circulez !"
        )
        logger.info(f"🧀 [SOLUCE CMD] Sheogorath a révélé le MENSONGE (Impossible Riddle).")
    else:
        # MOCKERY (Normal Riddle) - Sheogorath se moque mais ferme l'énigme
        mock_msg = random.choice([
            "Vous donnez votre langue au chat ? Pathétique ! Je ne vous donnerai pas la réponse, souffrez ! 🤪",
            "Abandonner si près du but... Mes fromages ont plus de volonté que vous !",
            "La réponse ? Hahaha ! Vous pensiez que je vous la donnerais ? Cherchez encore... ah non, c'est FINI ! 🧀",
            "M'aiq a gagné. Vous avez perdu. C'est l'ordre naturel des choses."
        ])
        await ctx.send(f"🧀 **ÉCHEC :** {mock_msg}")
        logger.info(f"🧀 [SOLUCE CMD] Sheogorath a fermé l'énigme (Réponse cachée).")

    # CLEANUP : Désépingler + Supprimer de la DB (on garde les messages pour conserver les réactions M'aiq ✅/❌)
    riddle_message_id = active_riddle.get("message_id")
    if riddle_message_id:
        try:
            ref_msg = await ctx.channel.fetch_message(riddle_message_id)
            await ref_msg.unpin()
        except Exception as e:
            logger.warning(f"⚠️ Impossible de désépingler l'énigme : {e}")

    delete_maiq_riddle(ctx.channel.id)


@bot.command(name="imposteur")
async def imposteur_cmd(ctx, target: discord.Member, *, instruction: str = ""):
    """
    Imite un utilisateur (Admin/Special only).
    Usage: !imposteur @User [Instruction optionnelle]
    """
    # Permission Check (Admin OU User Spécifique)
    if not (ctx.author.guild_permissions.administrator or ctx.author.id == 000000000000000000):
        await ctx.send("⛔ Vous n'avez pas le doit de porter le Masque du Fou !")
        return

    try:
        await ctx.message.delete() # Supprime la commande pour l'effet de surprise
        
        # 1. DÉTECTION SPECIALE BOTS (PERSONAS)
        bot_persona = get_bot_persona(target.display_name)
        
        # 2. START SESSION
        # On démarre une session interactive pour 5 minutes (300s)
        session = start_imposter_session(ctx.channel.id, target, instruction)
        
        # 3. PREMIER MESSAGE (GÉNÉRATION)
        if bot_persona:
            # Mode "Bot Imitation"
            prompt = (
                f"{bot_persona}\n"
                f"INSTRUCTION: Tu viens d'arriver. Dis quelque chose de typique pour toi. "
                f"Si instruction: {instruction}. "
                "Court (1 phrase)."
            )
            session.style_prompt = bot_persona # Save for session
            
        else:
            # Mode "Human Imitation"
            style_context = await fetch_user_style_context(ctx.channel, target)
            prompt = (
                f"SYSTEM: Tu es Sheogorath. Tu imites {target.display_name}. "
                "Ton but est de te moquer gentiment de lui en caricaturant son style. "
                "ANALYSE SON STYLE CI-DESSOUS (majuscules, emojis, longueur). "
                "Imite-le de façon exagérée mais crédible. Dis quelque chose d'absurde, drôle ou intrigant. "
                f"INSTRUCTION ADDITIONNELLE : {instruction}\n\n"
                f"[STYLE DE LA CIBLE (DERNIERS MESSAGES)] :\n{style_context}\n\n"
                "Réponse courte (1 phrase max) et fidèle au style."
            )
        
        fake_text = "Je suis un imposteur !" # Fallback
        
        # LLM Call
        if openrouter_client:
            try:
                chat = openrouter_client.chat.completions.create(
                    model="cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=1.0,
                    max_tokens=300
                )
                fake_text = chat.choices[0].message.content
            except Exception: pass
        
        if fake_text == "Je suis un imposteur !" and groq_client:
             try:
                chat = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}]
                )
                fake_text = chat.choices[0].message.content
             except Exception: pass

        # Nettoyage
        fake_text = fake_text.replace('"', '').strip()
        
        await send_imposter_message(ctx, target, fake_text)

    except Exception as e:
        logger.error(f"❌ [IMPOSTEUR CMD] Erreur : {e}")
        await ctx.send(f"Le masque a glissé... ({e})")

@bot.command(name="oubliemoi")
async def oubliemoi(ctx):
    """Purge toutes les données de mémoire de l'utilisateur."""
    uid = str(ctx.author.id)
    
    # Purge Daily Memory
    if "users" in daily_brain.memory and uid in daily_brain.memory["users"]:
        del daily_brain.memory["users"][uid]
    
    if "conversations" in daily_brain.memory:
        daily_brain.memory["conversations"] = [
            c for c in daily_brain.memory["conversations"]
            if c.get("user_id") != uid
        ]
    daily_brain.save_memory()
    
    # Purge Fact Memory
    if uid in fact_brain.facts:
        del fact_brain.facts[uid]
        fact_brain.save_facts()
        
    await ctx.send("🧀 Oublié ! Effacé ! Vaporisé ! Pouf ! Tu n'es plus qu'une page blanche dans mon livre de folie ! 🧀")

def _twitch_recent_responses():
    """Helper local qui lit les réponses récentes du bot sur Twitch s'il est actif."""
    global twitch_chat
    if not twitch_chat:
        return []
    try:
        resps = []
        for chan_resps in twitch_chat.recent_self_responses.values():
            resps.extend(list(chan_resps))
        return resps
    except Exception:
        return []

@bot.event
async def on_message(message):
    # 0. Anti-Self
    if message.author.id == bot.user.id:
        return
        
    # SILENCE STREAM (Canal ignoré)
    if is_ignored_channel(message.channel):
        return
    
    # Vérification mode maintenance AVANT process_commands
    if DATABASE_AVAILABLE and is_maintenance_mode():
        return

    # Handle Commands
    await bot.process_commands(message)

    # 1. AUTO-REACTIONS (Ajoute des emojis selon les mots-clés)
    reactions_map = {
        "fromage": "🧀", "cheese": "🧀", "roquefort": "🧀", "brie": "🧀",
        "folie": "🤪", "démence": "🧠", "madness": "🤪",
        "wabbajack": "✨", "jyggalag": "⚖️", "ordre": "⚖️",
        "haskill": "👔", "papillon": "🦋", "butterfly": "🦋",
        "sang": "🩸", "entrailles": "🥩"
    }
    
    msg_lower = message.content.lower()
    for word, emoji in reactions_map.items():
        if word in msg_lower:
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException:
                pass 

    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    if message.author.bot:
        return

    # Gestion des mentions ou réponses
    is_mentioned = bot.user.mentioned_in(message)
    is_reply = (message.reference and message.reference.resolved and 
                message.reference.resolved.author == bot.user)
    
    if message.mentions and not is_mentioned:
        return
     
    msg_lower = message.content.lower()
    is_name_mentioned = any(name in msg_lower for name in ["sheogorath", "sheo", "prince de la folie", "jyggalag"])
    
    # DECISION FINALE DE RÉPONSE
    # On répond si : mentionné, répondu, nom cité, ou si c'est un média (nosy)
    nosy_chance = 0.0
    if message.attachments:
        # Si c'est un média, Sheo est curieux (30% de chance de commenter sans être cité)
        nosy_chance = 0.30
    
    # (should_respond will be re-evaluated in the decision matrix below)
    
    # ---------------------------------------------------------
    # SOLUCE RIDDLE M'AIQ (Sheogorath Only)
    # ---------------------------------------------------------
    if any(keyword in msg_lower for keyword in ["soluce", "réponse", "solution", "donne moi la réponse"]) and (is_mentioned or is_name_mentioned):
        active_riddle = get_maiq_riddle(message.channel.id)
        if active_riddle:
            answer = active_riddle['answer'][0]
            question = active_riddle['question']
            mock_msg = random.choice([
                f"Oh, les mortels sont si bêtes ! La réponse à '{question}' est **{answer}** ! Hahaha !",
                f"M'aiq vous torture ? Bien. La réponse est **{answer}**. Maintenant, fichez le camp.",
                f"C'est **{answer}**, bande d'idiots sans imagination ! Je vous l'offre.",
                f"Vous abandonnez ? Pathétique. La réponse était **{answer}**. Allez pleurer ailleurs."
            ])
            await message.channel.send(mock_msg)
            if active_riddle.get("message_id"):
                try:
                    ref_msg = await message.channel.fetch_message(active_riddle["message_id"])
                    await ref_msg.unpin()
                except Exception as e:
                    logger.warning(f"⚠️ Impossible de désépingler l'énigme : {e}")
            delete_maiq_riddle(message.channel.id)
            logger.info(f"🧀 [SOLUCE] Sheogorath a donné la réponse : {answer}")
            return
        elif "soluce" in msg_lower or "solution" in msg_lower:
             await message.channel.send("Il n'y a pas d'énigme, espèce de fou ! Tu entends des voix ? 🤪")
             return
    
    has_image = any((a.content_type and a.content_type.startswith('image/')) or 
                    (a.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif'))) 
                    for a in message.attachments)
    if has_image:
        logger.info(f"📸 [DEBUG] Image détectée de {message.author.name} ({len(message.attachments)} attachments)")
    
    keywords = [
        "fromage", "cheese", "roquefort", "camembert", "brie", "parmesan", "comté", "meule", "croûte", "affiné",
        "folie", "ordre", "jyggalag", "wabbajack", "haskill", "shivering", "iles", "démence", "mania", "délire", 
        "entrailles", "cervelle", "viscères", "intestin", "yeux", "corde", "narine", "dents", "langue", "os", "sang",
        "papillon", "thé", "nuage", "lapin", "chaise", "cuillère", "fourchette", "horloge", "saucisse",
        "fou", "tête de cul", "cul", "débile", "idiot", "naze", "con", "crétin", "imbécile", "abruti",
        "nul", "radote", "radoter", "répète", "repete", "dico", "vocabulaire", "varié", "original",
        "salut", "bonjour", "bonsoir", "hey", "hello", "coucou", "yo",
        "pourquoi", "comment", "sens", "existence", "réalité", "vérité",
        "barbe", "tempête", "ennui", "crise", "amoureux"
    ]
    has_keyword = any(re.search(rf"\b{word}\b", msg_lower) for word in keywords)

    # (apply_temporary_nickname, PUNISHMENT_NICKS, get_insult_severity, DURATION_MAP)
    
    # 📌 11. IMPOSTEUR DAEDRA (INTERACTIF & PERSONAS)

    # A. VÉRIFICATION SESSION ACTIVE (Priorité Absolue)
    active_session = get_active_session(message.channel.id)
    if active_session and not message.author.bot:
        # Si une session est active, Sheogorath DEVIENT l'imposteur pour tout le monde
        # Sauf si on lui demande d'arrêter explicitemment
        
        if "arrête" in msg_lower and ("sheo" in msg_lower or "imposteur" in msg_lower):
            stop_imposter_session(message.channel.id)
            await message.channel.send("Pff... Rabat-joie ! Je rends ce visage. Il était moche de toute façon.")
            return

        # On génère une réponse en tant qu'imposteur
        try:
            target = active_session.target_user
            logger.info(f"🎭 [SESSION IMPOSTEUR] Réponse à {message.author.name} en tant que {target.display_name}")
            
            # Contextualisation
            persona_prompt = active_session.style_prompt
            if not persona_prompt:
                # Fallback style
                style = await fetch_user_style_context(message.channel, target)
                persona_prompt = (
                    f"SYSTEM: Tues un IMPOSTEUR. Tu imites {target.display_name}. "
                    f"Ton but est de tromper {message.author.name} ou de te moquer de lui. "
                    f"Ne sors PAS du personnage. "
                    f"[STYLE CIBLE]:\n{style}"
                )
                active_session.style_prompt = persona_prompt

            full_prompt = (
                f"{persona_prompt}\n"
                f"CONTEXTE: {message.author.name} vient de dire : '{message.content}'\n"
                f"INSTRUCTION: Réponds-lui du tac au tac en gardant ton masque d'imposteur {target.display_name}. "
                f"Sois drôle, un peu absurde si tu veux, mais crédible."
            )

            fake_text = "..."
            
            # Generation (Fastest avail)
            if groq_client:
                 try:
                    chat = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": full_prompt}]
                    )
                    fake_text = chat.choices[0].message.content
                 except Exception: pass
            elif openrouter_client:
                try:
                    chat = openrouter_client.chat.completions.create(
                        model="cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
                        messages=[{"role": "user", "content": full_prompt}],
                        max_tokens=300
                    )
                    fake_text = chat.choices[0].message.content
                except Exception: pass
            
            fake_text = fake_text.replace('"', '').strip()
            await send_imposter_message(message, target, fake_text)
            
            active_session.message_count += 1
            return # IMPORTANT: On ne répond pas en tant que Sheogorath
            
        except Exception as e:
            logger.error(f"❌ [SESSION ERREUR] {e}")
            stop_imposter_session(message.channel.id)


    # MODE AUTOMATIQUE (0.5% de chance) - Seulement si pas de session
    if not active_session and not message.author.bot and random.random() < 0.005:
        try:
            # On vérifie qu'il n'y a pas d'autre action en cours
            logger.info(f"🎭 [IMPOSTEUR AUTO] Sheogorath va imiter {message.author.display_name} !")
            
            # Fetch Style Context
            style_context = await fetch_user_style_context(message.channel, message.author)

            prompt = (
                f"SYSTEM: Tu es Sheogorath. Tu imites {message.author.display_name}. "
                "Ton but est de te moquer gentiment de lui en caricaturant ce qu'il vient de dire ou son style. "
                "ANALYSE SON STYLE CI-DESSOUS (majuscules, emojis, tics de langage). "
                "Imite-le de façon exagérée. Dis quelque chose d'absurde, drôle ou intrigant. "
                f"Son dernier message : '{message.content}' \n\n"
                f"[STYLE DE LA CIBLE (DERNIERS MESSAGES)] :\n{style_context}\n\n"
                "Réponse courte et absurde."
            )
            
            fake_text = "Moi aussi je dis des choses !" # Fallback
            
            if openrouter_client:
                try:
                    chat = openrouter_client.chat.completions.create(
                        model="cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=1.0,
                        max_tokens=300
                    )
                    fake_text = chat.choices[0].message.content
                except Exception: pass
            
            elif groq_client:
                 try:
                    chat = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    fake_text = chat.choices[0].message.content
                 except Exception: pass

            fake_text = fake_text.replace('"', '').strip()
            await send_imposter_message(message, message.author, fake_text)
            return # On ne répond pas normalement si on fait l'imposteur
        except Exception as e:
            logger.error(f"❌ [IMPOSTEUR AUTO] Erreur : {e}")
            
    # 📌 1. Commandes Admin/Debug
    if message.content.startswith("!debug_sheo") and message.author.guild_permissions.administrator:
        pass # This is a placeholder, actual debug commands would follow
    if message.content.startswith("!humeur ") and message.author.guild_permissions.administrator:
        target_mood = message.content[len("!humeur "):].strip()
        res = tool_set_mood(target_mood)
        await message.channel.send(res)
        return
    
    # ---------------------------------------------------------
    # SYSTÈME DE FAVEUR DU PRINCE
    # ---------------------------------------------------------
    if not message.author.bot:
        faveur_points = faveur_system.check_message_for_faveur(msg_lower)
        if faveur_points > 0:
            total, old_rank, new_rank, rank_up = faveur_system.add_faveur(
                message.author.id, message.author.name, faveur_points
            )
            # 30% de chance d'annoncer le gain (pour ne pas spammer)
            if random.random() < 0.30:
                gain_msg = random.choice(FAVEUR_GAIN_MESSAGES).format(
                    pts=faveur_points, total=total
                )
                await message.channel.send(gain_msg)
            # Toujours annoncer un changement de rang
            if rank_up:
                rank_msg = random.choice(RANK_UP_MESSAGES).format(
                    user=message.author.mention,
                    rank=new_rank["name"],
                    emoji=new_rank["emoji"]
                )
                await message.channel.send(rank_msg)
    # ---------------------------------------------------------
    
    # Check Memory / Context
    str(message.author.id) in daily_brain.memory["users"]
    
    # Intervention Proactive (Chaos Factor)
    # Chance de base : 2%
    # Bonus : 5% si le message contient des mots clés "chaos"
    intervention_chance = 0.02
    if any(w in msg_lower for w in ["ennui", "triste", "calme", "sérieux", "chaos", "fou"]):
        intervention_chance += 0.05
    
    # Anti-incrustation : on ne s'invite pas dans un échange visiblement adressé à un AUTRE bot.
    _other_bot_named = any(n in msg_lower for n in OTHER_BOT_NAMES)
    is_proactive = (not is_mentioned and not is_reply and not message.author.bot
                    and not _other_bot_named and random.random() < intervention_chance)

    if is_proactive:
        logger.info(f"⚡ [PROACTIVITY] Sheogorath s'ennuie et décide d'intervenir ! ({intervention_chance*100:.1f}%)")


    
    priority_keywords = [
        "fromage", "cheese", "roquefort", "camembert", "brie",
        "jyggalag", "wabbajack", "greymarch", "shivering",
        "haskill", "mania", "dementia",
        "sheo", "sheogorath", "madgod", "dieu fou"
    ]
    has_priority_keyword = any(re.search(rf"\b{word}\b", msg_lower) for word in priority_keywords)
    
    is_long_message = len(message.content.split()) > 10

    # Continuité : le mortel poursuit un échange récent avec Sheo (même salon, même auteur,
    # fenêtre courte) sans le re-mentionner → on garde le fil. Sauf s'il s'adresse clairement
    # à un autre bot (anti-incrustation). Probabiliste (~70%) pour garder le grain d'imprévisibilité.
    _prev = last_exchange.get(message.channel.id)
    is_continuation = bool(
        _prev
        and _prev[0] == message.author.id
        and (time.time() - _prev[1]) <= CONTINUATION_WINDOW
        and not any(n in msg_lower for n in OTHER_BOT_NAMES)
        and random.random() < CONTINUATION_PROBA
    )

    # DECISION MATRIX
    should_respond = False
    response_mode = "LLM" # Default

    # Check for name specifically
    has_name = any(name in msg_lower for name in ["sheogorath", "sheo", "prince", "dieu fou", "madgod"])

    if is_mentioned or is_reply:
        should_respond = True
        logger.info(f"🤖 [TRIGGER] Mention/Reply")
    elif has_name:
        should_respond = True
        logger.info(f"👑 [TRIGGER] Mon nom a été prononcé ! ('{msg_lower[:30]}...')")
    elif is_continuation:
        should_respond = True
        response_mode = "LLM"
        logger.info(f"💬 [TRIGGER] Continuité de conversation (échange récent, sans re-mention)")
    elif has_image and not message.author.bot and (has_name or has_priority_keyword or has_keyword):
        should_respond = True
        logger.info(f"📷 [TRIGGER] Image + Name/Keyword detected -> 100% Response")
    elif has_image and not message.author.bot and random.random() < 0.60: # 60% chance to react to random images (users only)
        should_respond = True
        logger.info(f"📷 [TRIGGER] Random Image detected")
    elif is_proactive:
        should_respond = True
        logger.info(f"🤖 [TRIGGER] Proactivity")
    elif has_priority_keyword and not is_long_message:
        # Court message + Keyword fort -> On passe TOUT en LLM pour éviter les réponses hors-sol
        # L'IA est assez intelligente pour gérer les demandes de fromage
        should_respond = True
        response_mode = "LLM"
    elif has_priority_keyword and is_long_message:
        should_respond = True
        response_mode = "LLM" # Force LLM for context
    elif has_keyword and not _other_bot_named and random.random() < 0.60:
        # Mot-clé générique (« bonjour », « fou »…) : on ne s'incruste PAS si le message
        # nomme un autre bot (« bonjour sugar » vise Sugar, pas Sheo).
        should_respond = True
        response_mode = "LLM" # WAS HYBRID - FORCED TO LLM FOR BETTER CONVERSATION

    if not should_respond:
        return

    # Mémorise l'interlocuteur courant → permet de poursuivre le fil au prochain message
    # sans exiger une nouvelle mention (continuité conversationnelle).
    last_exchange[message.channel.id] = (message.author.id, time.time())

    # HYBRID EXECUTION
    if response_mode == "HYBRID" and not is_proactive and not has_image: # Always LLM for images
        # Double check if we really want hybrid (sometimes LLM is better even for short quotes if we have memory)
        logger.info(f"🎯 [HYBRID MODE] Utilisation d'une phrase pré-faite")
        response_text = get_smart_string_response_v2(message.content, message.guild.id)
        
        # AJOUT : Suffixe selon l'humeur en Hybrid Mode ? (Optionnel, gardons simple pour l'instant)
        await message.channel.send(response_text)
        daily_brain.add_interaction(message.author.id, message.author.name, message.content, response_text)
        asyncio.create_task(daily_brain.refresh_daily_read(message.author.id, _daily_llm_call))
        return

    # LLM EXECUTION
    logger.info(f"🧠 [LLM MODE] Génération d'une réponse intelligente... (Mood: {current_mood})")
    
    def _get_meme_addition():
        chan_id = message.channel.id
        consigne = build_meme_consigne(message.content or "", set(meme_recent[chan_id]))
        if consigne:
            import re as _re
            m = _re.search(r"« (.+?) »", consigne)
            if m:
                meme_recent[chan_id].append(m.group(1))
        return consigne
    
    # 1. Prepare User Message & System Context
    user_message = message.content.replace(f'<@{bot.user.id}>', '').strip()
    
    # Memory Context
    memory_context = daily_brain.get_context_summary(message.author.id)
    dr = daily_brain.get_daily_read(message.author.id)
    if dr:
        memory_context += f"\n[CONSIGNE DU JOUR] {dr}"
    
    # REPUTATION CONTEXT (Rank Awareness)
    user_rep = get_reputation(message.author.id)
    user_rank = get_reputation_level(user_rep.get("points", 0))
    user_points = user_rep.get("points", 0)

    # UTILISATION DU PROMPT DYNAMIQUE SELON L'HUMEUR
    system_instruction = f"{get_current_system_prompt()}\n"
    system_instruction += f"[CONTEXTE UTILISATEUR] : Tu parles à {message.author.display_name}. Son Rang est : {user_rank} ({user_points} pts).\n"
    if "Paria" in user_rank:
        system_instruction += "NOTE: C'est un PARIA. Traite-le comme un ver de terre. Moque-toi de lui.\n"
    elif "Champion" in user_rank or "Demi-Prince" in user_rank:
        system_instruction += "NOTE: C'est un CHAMPION. Montre un peu de respect (ou une jalousie amusée).\n"
    
    # [ACTIVITÉ] : simple flavor d'arrière-plan. On ne l'injecte qu'occasionnellement et
    # JAMAIS face à une provocation/insulte — sinon Sheo monologue sur son activité au lieu
    # de claquer une répartie sur ce que le mortel vient de dire.
    _is_provoked = get_insult_severity(user_message.lower()) > 0

    # TON PAR DÉFAUT (fidélité au personnage) : sans provocation, Sheogorath n'est PAS un brute
    # qui menace de mort à chaque message. Il est d'abord le Prince de la Folie : joueur, exalté,
    # curieux, théâtral (Mania) — ou inquiétant et énigmatique (Dementia) — mais il ne sort pas
    # les menaces de torture/dents pour un message anodin. Les vraies menaces = pour un vrai
    # manque de respect (géré par la branche provoquée du prompt).
    if not _is_provoked:
        system_instruction += (
            "[TON — PAS DE MENACE GRATUITE] : Le mortel ne t'a NI insulté NI manqué de respect. "
            "Reste pleinement Sheogorath — joueur, exalté, curieux et imprévisible (Mania), ou "
            "inquiétant et énigmatique (Dementia) — mais NE le menace PAS de mort, de torture ou "
            "de lui arracher les dents pour un message aussi anodin. Rebondis VRAIMENT sur ce qu'il "
            "vient de dire, avec malice et absurde. Les menaces glaciales sont réservées au manque "
            "de respect réel.\n"
        )

    # ANTI-ÉCHO (tic récurrent — TOUTES situations, provoqué OU NON). Sheo ouvrait
    # mécaniquement en recrachant le dernier mot du mortel en MAJUSCULES + « ?! » + « HAHA !
    # Tu as osé... » (« Un CODE wifi ?! », « Un VER ?! », « Johnny ?! »). C'est répétitif même
    # sur une vraie pique. On bannit le GABARIT D'OUVERTURE, pas le droit de retourner l'argument.
    # NB : ce bloc N'EST PLUS gaté sur not _is_provoked — une taquinerie (« chiant ») compte
    # comme provocation légère et le tic ressortait justement là.
    system_instruction += (
        "[ANTI-ÉCHO — VARIE TON OUVERTURE] : NE commence JAMAIS ta réplique en répétant le dernier "
        "mot du mortel en MAJUSCULES suivi de « ?! » (gabarit STRICTEMENT INTERDIT : « Un CODE wifi ?! », "
        "« Un VER ?! », « MOI ?! », « Johnny ?! »). N'enchaîne PAS avec « HAHA ! Tu as osé... ». Tu PEUX "
        "retourner son propos contre lui, mais avec une OUVERTURE DIFFÉRENTE à chaque fois : attaque par "
        "une image saugrenue, une question piège, un constat absurde, un changement de sujet brutal. "
        "Surprends — ne récite pas ton tic.\n"
    )

    if not _is_provoked and random.random() < 0.25:
        system_instruction += f"[ACTIVITÉ EN COURS] : En ce moment même, tu es occupé à : '{current_activity_text}'. Si on te demande ce que tu fais, dis-le !\n"

    # Random Obsession Injection (Chaos Factor) — occasionnelle (~35%) et coupée sur
    # provocation : injectée en permanence, elle tirait Sheo hors-sujet sur les messages
    # vagues (« comme ta réponse » → délire incohérent) au lieu de répondre au mortel.
    if not _is_provoked and random.random() < 0.35:
        current_obsession = random.choice(sheo_data.SHEO_OBSESSIONS)
        system_instruction += f"[OBSESSION DU MOMENT] : {current_obsession}\n"
    
    if is_proactive:
        system_instruction += "NOTE: Tu interviens sans être appelé. Sois surprenant et chaotique, mais pertinent par rapport à la discussion en cours.\n"
    
    if has_image:
        system_instruction += "NOTE: L'utilisateur a envoyé une IMAGE. Commente-la avec ton style fou (Dément ou Maniaque). Si c'est de la nourriture, compare-la à du fromage ou des entrailles !\n"
    
    if memory_context:
        system_instruction += f"{memory_context}\n"

    # Context Injection for Empty Pings - SYSTEM-LEVEL ONLY (No leakage!)
    if is_mentioned and not user_message and not has_image:
         user_message = "(Le mortel vous regarde fixement sans rien dire.)"
    elif has_image and not user_message:
         user_message = "(Le mortel vous montre une image. [INSTRUCTION VISUELLE] : Regarde attentivement l'image. Décris brièvement ce que tu vois (un mème, un chat, du fromage ?) et réagis-y directement selon ton humeur. Ne fais pas de commentaire générique, prouve que tu as vu l'image !)"

    # MEMORY INJECTION (Persistent Facts)
    user_facts = fact_brain.get_facts(message.author.id)
    fact_context = ""
    if user_facts:
        fact_context = f"\n[CE QUE TU SAIS SUR {message.author.name}]:\n- " + "\n- ".join(user_facts) + "\nUtilise ces infos pour personnaliser ta réponse."
    
    system_instruction = f"{system_instruction}\n{fact_context}"
    
    # FAVEUR DU PRINCE — Contexte de rang
    faveur_context = faveur_system.get_rank_context(message.author.id)
    if faveur_context:
        system_instruction += faveur_context
    
    # ANTI-REPETITION INJECTION (NEW!)
    recent_responses = merge_recent_responses(
        response_memory.get_recent(message.guild.id),
        _twitch_recent_responses(),
    )
    if recent_responses:
        recent_snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        system_instruction += f"\n\n[ANTI-RÉPÉTITION ABSOLUE] Tu as déjà dit récemment :\n"
        for i, snippet in enumerate(recent_snippets, 1):
            system_instruction += f"{i}. \"{snippet}\"\n"
        system_instruction += "⚠️ INTERDICTION TOTALE de répéter ces phrases ou des variations proches. Trouve une idée COMPLÈTEMENT DIFFÉRENTE ! Ne réutilise AUCUN mot-clé saillant de ces répliques (mots en MAJUSCULES, images, métaphores, chutes) : si l'une d'elles crie ÉVALUATION, toi tu pars ailleurs."
    
    anti_tic = build_anti_tic_consigne(recent_responses)
    if anti_tic:
        system_instruction += "\n\n" + anti_tic
    
    # Instruction for Extraction
    system_instruction += "\n\n[INSTRUCTION SECRÈTE]: Si tu apprends un FAIT NOUVEAU et IMPORTANT sur l'utilisateur dans ce message (ex: il aime/déteste qqch, son métier, une peur), ajoute-le à la fin de ta réponse dans un bloc XML invisible : <fact>Le fait appris</fact>. Sinon, ne mets rien."
    system_instruction += _get_meme_addition()
    # HISTORY MANAGEMENT
    channel_id = message.channel.id
    if channel_id not in conversation_history: conversation_history[channel_id] = []
    
    # Add to temporary convo history
    # IMPORTANT: Include Author Name so LLM knows who said what in history
    conversation_history[channel_id].append({"role": "user", "parts": [f"{message.author.name}: {user_message}"]})
    if len(conversation_history[channel_id]) > MAX_HISTORY:
        conversation_history[channel_id] = conversation_history[channel_id][-MAX_HISTORY:]

    # Build View Transcript (last 10 msgs) & Collect Active Users
    transcript = "TRANSCRIPTION RÉCENTE (ID des mortels inclus) :\n"
    active_mortals = set()
    messages_list = []
    async for hist_msg in message.channel.history(limit=10): # Increased capture
        messages_list.append(hist_msg)
        if not hist_msg.author.bot:
            active_mortals.add(hist_msg.author.name)
            
    # Reverse to get Chronological Order (Oldest -> Newest)
    for hist_msg in reversed(messages_list):
        # Silence total entre bots : on n'inclut PAS les autres bots dans le contexte.
        if hist_msg.author.bot and hist_msg.author != bot.user:
            continue
        transcript += f"{hist_msg.author.name} ({hist_msg.author.mention}): {hist_msg.content}\n"

    # NB : l'activité est déjà injectée (occasionnellement) dans system_instruction.
    # On ne la ré-injecte PAS ici (l'ancien `current_sheo_activity` était gelé sur
    # « Compter ses dents » → Sheo comptait au lieu de répliquer).

    # Inject Active Mortals List
    if active_mortals:
        system_instruction += f"\n[CIBLES VALIDES POUR RUMEURS (MORTELS PRÉSENTS)] : {', '.join(active_mortals)}. UTILISE UNIQUEMENT CES NOMS."
    
    # INSTRUCTION POUR LES MENTIONS DISCORD
    system_instruction += f"\n\n[MENTIONS DISCORD] : Quand tu mentionnes un utilisateur, utilise TOUJOURS le format Discord '<@ID>' que tu vois dans le transcript (ex: <@123456789>). Ne mets JAMAIS le pseudo entre chevrons comme '<pseudo>' ou '@pseudo'. L'utilisateur actuel est <@{message.author.id}>."

    # ═══ SMART ROUTER — Classification du message ═══
    # Sheo est-il DIRECTEMENT interpellé ? (mention / reply / nom prononcé / continuité)
    # Si oui et que c'est du banter court, le routeur vise la cascade REPARTEE (Grok) pour
    # une répartie plus mordante. Sinon, comportement inchangé (cascade TEXT/REASONING).
    _addressed = bool(is_mentioned or is_reply or has_name or is_continuation)
    routing = classify_request(user_message, message.attachments, addressed=_addressed)
    
    # Télécharger le média si nécessaire (image ou audio)
    media_data = None
    mime_type = "image/jpeg"
    if routing["has_image"] and routing["image_attachment"]:
        media_data, mime_type = await download_media(routing["image_attachment"])
        if not media_data:
            routing["type"] = RequestType.TEXT  # Fallback texte si échec download
    elif routing["has_audio"] and routing["audio_attachment"]:
        media_data, mime_type = await download_media(routing["audio_attachment"])
        if not media_data:
            routing["type"] = RequestType.TEXT
    
    has_image = routing["has_image"] and media_data is not None
    has_audio = routing["has_audio"] and media_data is not None
    
    # LLM CALL
    response_text = None
    
    # Construct Gemini Payload (unifié pour éviter l'erreur 400)
    last_turn_text = f"SYSTEM: {system_instruction}\nCONTEXT: {transcript}\n\n{message.author.name}: {user_message}"
    if has_audio and not media_data:
        last_turn_text = f"SYSTEM: {system_instruction}\nCONTEXT: {transcript}\n\n{message.author.name} a envoyé un MESSAGE VOCAL. Écoute-le et réponds en commentant ce que tu entends, dans ton style fou."
        
    last_turn_parts = [types.Part(text=last_turn_text)]
    if media_data:
        last_turn_parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_data)))
    gemini_messages = [types.Content(role="user", parts=last_turn_parts)]
    
    cascade = get_model_cascade(routing["type"])
    
    # Determine length adaptation
    if routing["type"] == RequestType.REPARTEE:
        # Ancien mode « répartie sèche » (160t/4ph) : APLATISSAIT Sheo quand on l'interpellait
        # (banter/name-spam → one-liner plat), alors que Twitch — sans ce clamp — le laissait
        # respirer en conteur théâtral. On aligne : mêmes plafonds que le chemin riche, et c'est le
        # PROMPT qui décide sec-vs-théâtral (règle FACE À UNE ATTAQUE = morsure courte sur vraie
        # insulte ; EXCEPTION DU CONTEUR = digression ravie sur banter). Le cap n'est qu'un filet.
        max_tokens_val = 340   # marge pour qu'un conteur/double-sens ATTERRISSE (sinon coupe en plein mot)
        max_sentences_val = sentence_budget(user_message)  # filet déterministe
    else:
        max_tokens_val = 340   # assez pour une tirade dense qui monte et atterrit sans clipper
        max_sentences_val = sentence_budget(user_message)  # filet déterministe
    
    for client_type, model_name in cascade:
        try:
            # 1. GEMINI
            if client_type == "gemini":
                api_key = key_manager.get_key("gemini")
                if not api_key: continue
                client = get_safe_genai_client(api_key=api_key, http_options={'api_version': 'v1beta'})
                
                # Gemini Call
                resp = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name, contents=gemini_messages,
                        config=types.GenerateContentConfig(
                            temperature=1.0,
                            tools=SHEO_TOOLS_DEFINITION
                        )
                    ),
                    timeout=15
                )
                
                # Handling Tool Calls (IA Agentique)
                if resp.candidates[0].content.parts and resp.candidates[0].content.parts[0].function_call:
                    fc = resp.candidates[0].content.parts[0].function_call
                    tool_name = fc.name
                    args = fc.args
                    
                    logger.info(f"🛠️ [IA AGENT] Sheogorath appelle l'outil : {tool_name}({args})")
                    
                    tool_result = "Action impossible."
                    if tool_name == "wabbajack":
                        tool_result = await tool_wabbajack(args["user_id"], args["reason"], message.channel)
                    elif tool_name == "set_mood":
                        tool_result = tool_set_mood(args["mood"])
                    elif tool_name == "mod_reputation":
                        tool_result = await tool_mod_reputation(args["user_id"], args["points"], args["reason"])
                    elif tool_name == "start_identity_theft":
                        tool_result = await tool_start_impersonation(args["user_id"], message.channel)
                    
                    # Feedback loop (Sequential matching)
                    gemini_messages.append(resp.candidates[0].content) # 1. Model Call
                    gemini_messages.append(types.Content(
                        role="user", # Role user avec function_response
                        parts=[types.Part(function_response=types.FunctionResponse(name=tool_name, response={"result": tool_result}))]
                    ))
                    
                    # Seconde passe pour la réponse textuelle
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name, contents=gemini_messages,
                            config=types.GenerateContentConfig(
                                temperature=0.9,
                                tools=SHEO_TOOLS_DEFINITION # Redonner les tools peut aider à la stabilité
                            )
                        ),
                        timeout=15
                    )
                
                response_text = resp.text
                logger.info(f"✅ [GEMINI {model_name}] Sheogorath via {routing['reason']}")
                break

            # 1.bis OLLAMA (Moondream)
            elif client_type == "ollama":
                if routing["type"] == RequestType.IMAGE and routing["image_attachment"]:
                    logger.info(f"🌀 [OLLAMA] Tentative Vision locale avec Moondream...")
                    response_text = await process_image_ollama(
                        attachment=routing["image_attachment"],
                        personality_prompt=system_instruction,
                        user_message=user_message
                    )
                    if response_text:
                        logger.info(f"✅ [OLLAMA {model_name}] Sheogorath a utilisé Moondream local !")
                        break
                    else:
                        logger.warning(f"⚠️ [OLLAMA FAIL] Moondream n'a pas pu analyser l'image.")
                        continue
                else:
                    continue

            # 2. OpenRouter (tout modèle OpenRouter de la cascade, avec tool-calling)
            #    NB: garde élargie — plus de filtre "grok" (le modèle :free n'est plus un Grok).
            elif client_type == "openrouter" and openrouter_client:
                msgs = [{"role": "system", "content": f"{system_instruction}\nCONTEXT: {transcript}"}]
                for msg in conversation_history[channel_id]:
                    r = "user" if msg["role"] == "user" else "assistant"
                    msgs.append({"role": r, "content": msg["parts"][0]})
                msgs.append({"role": "user", "content": f"{message.author.name}: {user_message}"})
                
                try:
                    chat = await asyncio.wait_for(
                        asyncio.to_thread(
                            openrouter_client.chat.completions.create,
                            model=model_name,
                            messages=msgs,
                            temperature=1.0,
                            max_tokens=max_tokens_val,
                            tools=OPENAI_TOOLS_DEFINITION,
                            tool_choice="auto"
                        ),
                        timeout=15
                    )
                except Exception as _tool_err:
                    # Modèle sans support tool-use (ex. Dolphin-Venice:free → 404 "No endpoints
                    # found that support tool use") : on réessaie SANS outils au lieu de tomber
                    # en cascade. On perd le tool-calling pour CE modèle, pas la réponse.
                    logger.info(f"🔧 [OpenRouter] {model_name} sans tool-use → réessai sans outils : {_tool_err}")
                    chat = await asyncio.wait_for(
                        asyncio.to_thread(
                            openrouter_client.chat.completions.create,
                            model=model_name,
                            messages=msgs,
                            temperature=1.0,
                            max_tokens=max_tokens_val
                        ),
                        timeout=15
                    )

                resp_msg = chat.choices[0].message
                
                # Handling Tool Calls
                if resp_msg.tool_calls:
                    for tool_call in resp_msg.tool_calls:
                        tool_name = tool_call.function.name
                        import json
                        args = json.loads(tool_call.function.arguments)
                        
                        logger.info(f"🛠️ [OpenRouter Agent] Sheogorath appelle l'outil : {tool_name}({args})")
                        
                        tool_result = "Action impossible."
                        if tool_name == "wabbajack":
                            tool_result = await tool_wabbajack(args["user_id"], args["reason"], message.channel)
                        elif tool_name == "set_mood":
                            tool_result = tool_set_mood(args["mood"])
                        elif tool_name == "start_identity_theft":
                            tool_result = await tool_start_impersonation(args["user_id"], message.channel)
                        
                        # Feedback loop
                        msgs.append(resp_msg)
                        msgs.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": tool_result
                        })
                    
                    # Seconde passe
                    chat = await asyncio.wait_for(
                        asyncio.to_thread(
                            openrouter_client.chat.completions.create, model=model_name, messages=msgs, max_tokens=max_tokens_val
                        ),
                        timeout=15
                    )
                    response_text = chat.choices[0].message.content
                else:
                    response_text = resp_msg.content

                # Un modèle :free peut renvoyer un contenu VIDE sans exception →
                # on ne casse pas la cascade sur du vide, on tente l'échelon suivant.
                if not (response_text and response_text.strip()):
                    logger.warning(f"⚠️ [OPENROUTER {model_name}] réponse vide → échelon suivant")
                    response_text = None
                    continue
                logger.info(f"😈 [OPENROUTER {model_name}] Sheogorath a parlé !")
                break

            # 3. MISTRAL
            elif client_type == "mistral" and mistral_client:
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        mistral_client.chat.complete,
                        model=model_name,
                        messages=[{"role": "system", "content": system_instruction},
                                  {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\nLAST MSG: {user_message}"}],
                        max_tokens=max_tokens_val
                    ),
                    timeout=15
                )
                response_text = chat.choices[0].message.content
                logger.info(f"🌪️ [MISTRAL {model_name}] Sheogorath souffle des vents de folie !")
                break

            # 4. GROQ
            elif client_type == "groq" and groq_client:
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        groq_client.chat.completions.create,
                        messages=[{"role": "system", "content": system_instruction},
                                  {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\nLAST MSG: {user_message}"}],
                        model=model_name, temperature=0.9, max_tokens=max_tokens_val
                    ),
                    timeout=15
                )
                response_text = chat.choices[0].message.content
                logger.info(f"⚡ [GROQ {model_name}] Sheogorath a répondu !")
                break

            # 5. OPENROUTER
            elif client_type == "openrouter" and openrouter_client:
                msgs = [{"role": "system", "content": f"{system_instruction}\nCONTEXT: {transcript}"}]
                for msg in conversation_history[channel_id]:
                    r = "user" if msg["role"] == "user" else "assistant"
                    msgs.append({"role": r, "content": msg["parts"][0]})
                
                # Payload Multimodal si image présente
                if has_image and media_data:
                    b64_image = base64.b64encode(media_data).decode('utf-8')
                    user_content = [
                        {"type": "text", "text": f"{message.author.name}: {user_message}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}
                        }
                    ]
                    msgs.append({"role": "user", "content": user_content})
                else:
                    msgs.append({"role": "user", "content": f"{message.author.name}: {user_message}"})
                
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        openrouter_client.chat.completions.create,
                        model=model_name, messages=msgs,
                        temperature=0.9, max_tokens=max_tokens_val,
                        extra_headers={"HTTP-Referer": "https://discord-bot.local", "X-Title": "Sheogorath Bot"}
                    ),
                    timeout=15
                )
                response_text = chat.choices[0].message.content
                logger.info(f"🌌 [OPENROUTER {model_name}] Sheogorath a utilisé un secours visuel !")
                break

        except Exception as e:
            logger.warning(f"⚠️ [{client_type.upper()} FAIL] {e}")
            if client_type == "gemini" and api_key:
                error_code = getattr(e, 'code', getattr(e, 'status_code', 0))
                key_manager.report_error("gemini", api_key, error_code)
            continue

    # Fallback media : message RP si Gemini échoue sur une image/audio
    if not response_text and (has_image or has_audio):
        media_type = "image" if has_image else "message vocal"
        await message.channel.send(f"🌀 J'arrive pas à voir ! Des nuages de chaos obscurcissent ma vue divine. Réessaie plus tard, mortel ! 🧀")
        return

    # MODE SURVIE (Citations du dictionnaire — DERNIER RECOURS ABSOLU)
    if not response_text:
        logger.warning("🚨 [SURVIE] Toutes les APIs ont échoué. Utilisation du dictionnaire de citations.")
        response_text = get_smart_string_response_v2(message.content, message.guild.id)

    if response_text:
        # POST-PROCESSING via sheo_llm.py
        response_text = postprocess_response(
            response_text, fact_brain, message.author.id, message.content, max_sentences=max_sentences_val
        )
        
        # VÉRIFICATION MESSAGE NON VIDE
        if not response_text or len(response_text.strip()) < 2:
            logger.warning("[POST-PROCESS] Réponse vide après nettoyage, utilisation du dictionnaire.")
            response_text = get_smart_string_response_v2(message.content, message.guild.id)
        
        # CONVERSION DES MENTIONS TEXTUELLES (via sheo_mentions.py)
        response_text = await convert_text_mentions_to_discord(response_text, message.channel)
        
        # ══════════════════════════════════════════════════
        # AUTO-VOICE — TTS Piper (si l'utilisateur est en vocal)
        # ══════════════════════════════════════════════════
        voice_played = False
        if VOICE_AVAILABLE and send_voice_response and not message.author.bot:
            try:
                voice_played = await send_voice_response(bot, message, response_text, mood=current_mood)
                if voice_played:
                    logger.info(f"🎤 [AUTO-VOICE] Réponse vocale envoyée à {message.author.name}")
            except Exception as e:
                logger.warning(f"⚠️ [AUTO-VOICE] Erreur: {e}")
        
        # Préfixer le message texte si vocal joué
        if voice_played:
            response_text = f"🎤 {response_text}"
        # ══════════════════════════════════════════════════
            
        # Split message if too long
        if len(response_text) > 2000:
             chunks = [response_text[i:i+1950] for i in range(0, len(response_text), 1950)]
             for chunk in chunks:
                 await message.channel.send(chunk)
        else:
            await message.channel.send(response_text)
            
        conversation_history[channel_id].append({"role": "model", "parts": [response_text]})
        daily_brain.add_interaction(message.author.id, message.author.name, message.content, response_text)
        asyncio.create_task(daily_brain.refresh_daily_read(message.author.id, _daily_llm_call))
        response_memory.add(message.guild.id, response_text)

async def on_sheo_shutdown():
    global twitch_chat, twitch_chat_task
    if twitch_chat:
        logger.info("[SHUTDOWN] Arrêt du chat Twitch Sheogorath...")
        twitch_chat.stop()
    if twitch_chat_task:
        twitch_chat_task.cancel()
        try:
            await twitch_chat_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    if DISCORD_TOKEN:
        setup_graceful_shutdown(bot, on_sheo_shutdown)
        bot.run(DISCORD_TOKEN)
    else:
        logger.critical("❌ ERREUR : Aucun token Discord trouvé dans le fichier .env !")

