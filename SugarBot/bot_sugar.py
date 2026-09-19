
# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import asyncio
import discord
from discord.ext import commands, tasks
from google import genai
from groq import Groq 
from mistralai import Mistral
from openai import OpenAI
import aiohttp
import random
import re
import json
import os
from core.response_memory import ResponseMemory, merge_recent_responses
from core.anti_tic import build_anti_tic_consigne
from core.boucles import installer_anti_rattrapage
import logging
from datetime import datetime
from core.smart_router import classify_request, RequestType, download_media, resolve_media_attachments
from core.profil_interlocuteur import construire_profil_discord


try:
    from shared.memes_fr import build_meme_consigne
    MEMES_AVAILABLE = True
except ImportError:
    MEMES_AVAILABLE = False
    def build_meme_consigne(*a, **k): return ""

import collections
meme_recent = collections.defaultdict(lambda: collections.deque(maxlen=8))  # {channel_id: deque[ref]}

# LOGGING STRUCTURÉ
from core.bot_logger import setup_logger, enregistrer_reaction
logger = setup_logger("sugar")

# FILE PATHS
DATA_DIR = os.getenv("DATA_DIR", ".")
DATA_FILE = os.path.join(DATA_DIR, "sugar_data.json")

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                # Migration d'anciennes clés (ère pirate/GTO) vers le compteur d'exploits
                if "legends_told" in data:
                    data["tales_told"] = data.pop("legends_told")
                return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"⚠️ Lecture {DATA_FILE} impossible ({e}) — valeurs par défaut.")
    return {"tales_told": 0}

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning(f"⚠️ Sauvegarde {DATA_FILE} impossible ({e}) — état non persisté.")

# ── FILTRES DE SORTIE ─────────────────────────────────────────────────────────
# La logique vit dans `sugar_filtres.py` : `bot_sugar.py` importe `discord`, donc le
# harnais d'evaluation ne pouvait pas l'atteindre et notait la sortie BRUTE du modele.
try:
    from sugar_filtres import (_strip_lead_vocative, _SWEET_NAMES,
                               _LEAD_VOCATIVE, filtre_sortie)
except ImportError:
    from SugarBot.sugar_filtres import (_strip_lead_vocative, _SWEET_NAMES,
                                        _LEAD_VOCATIVE, filtre_sortie)

# --- Cadence des petits noms sucrés (anti-« un bonbon à chaque message ») ---
# Le petit nom sucré doit rester une touche OCCASIONNELLE, pas un tic à chaque
# réplique (« mon nougat / mon caramel / mon berlingot » en boucle). On sait le
# repérer où qu'il soit — en tête, en début de phrase, en apposition — pour le
# retirer quand la réplique PRÉCÉDENTE en portait déjà un.
_SWEET_PHRASE = (
    r"(?:mon|ma|mes)\s+"
    r"(?:(?:petit|petite|gros|grosse|tendre|doux|douce|cher|chère|chere)\s+){0,2}"
    r"(?:" + _SWEET_NAMES + r")"
    r"(?:\s+(?:d['’]|de\s+|au\s+|à\s+la\s+)?[\wàâäéèêëïîôöùûüç'’-]+){0,2}"
)
# Vocatif en début de phrase : « … ? Mon berlingot, tu… »
_VOCATIVE_SENTENCE = re.compile(
    r"([.!?…]\s+)"
    r"(?:oh|eh|ah|hé|he|hey|coucou|alors)?[,\s]*"
    + _SWEET_PHRASE +
    r"\s*[,–—-]+\s*"
    r"([A-Za-zÀ-ÿ])",
    re.IGNORECASE)
# Vocatif en apposition : « … politesse, mon caramel — dommage… »
_VOCATIVE_APPOS = re.compile(
    r"\s*,\s*" + _SWEET_PHRASE + r"(?=\s*[,–—.!?…-]|\s*$)",
    re.IGNORECASE)

def _has_sweet_vocative(text):
    """True si la réplique porte un petit nom sucré (tête, début de phrase ou apposition)."""
    if not text:
        return False
    return bool(_LEAD_VOCATIVE.match(text)
                or _VOCATIVE_SENTENCE.search(text)
                or _VOCATIVE_APPOS.search(text))

def _strip_sweet_vocatives(text):
    """Retire les petits noms sucrés où qu'ils soient, puis renormalise la ponctuation.
    Appelé quand la réplique précédente en portait déjà un (cadence : pas deux d'affilée)."""
    if not text:
        return text
    text = _strip_lead_vocative(text)
    text = _VOCATIVE_SENTENCE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    text = _VOCATIVE_APPOS.sub(" ", text)
    text = re.sub(r"\s+([,.])", r"\1", text)         # espace parasite avant virgule/point (typo FR : on garde l'espace avant ? ! ; :)
    text = re.sub(r"([,;:])\s*\1", r"\1", text)      # ponctuation doublée après coupe
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()

# Cadence : mémorise si la DERNIÈRE réponse envoyée dans un salon portait un vocatif sucré.
_last_reply_had_vocative = {}

# Bot Sugar Bot (ardoise neutre)

# IMPORT SECURE ENV LOADER
from pathlib import Path
from core.secure_env import load_secure_env
load_secure_env(Path(__file__).parent)

# IMPORT LLM CASCADE
from core.llm_cascade import generate_response
from core.models import GEMINI_FLASH, NVIDIA_BASE_URL
from core.transcript import ligne_de_contexte
from core.chrono import Chrono

# IMPORT DES SYSTÈMES (locaux pour Discloud)

try:
    from shared.shared_database import (
        get_or_create_user, add_reputation, log_interaction,
        is_maintenance_mode, is_ignored_channel,
        get_reputation, get_daily_quests
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
    logger.warning(f"⚠️ [SUGAR] Modules optionnels non disponibles: {e}")
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

try:
    from shared.twitch_chat import setup_twitch_chat
    TWITCH_CHAT_AVAILABLE = True
except ImportError:
    TWITCH_CHAT_AVAILABLE = False
    def setup_twitch_chat(*a, **k): return None

twitch_chat = None
twitch_chat_task = None

def _twitch_recent_responses():
    """Helper local qui lit les réponses récentes du bot sur Twitch s'il est actif.
    Pont anti-doublon Discord↔Twitch (même câblage que le pilote Sheo)."""
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

# Garde one-shot : on_ready peut refire (reconnexion / RESUME) et le setup des
# commandes (slash + jeux) n'est PAS idempotent → on ne l'exécute qu'une fois.
_ready_setup_done = False

try:
    from shared.discord_profile import DiscordDailyBio
except ImportError:
    DiscordDailyBio = None

try:
    from shared.discord_status import DiscordDailyStatus
except ImportError:
    DiscordDailyStatus = None


try:
    from sugar_data import PERSONALITY_PROMPT, PUNCHLINES, EXPLOITS, GREETINGS
except ImportError:
    from SugarBot.sugar_data import PERSONALITY_PROMPT, PUNCHLINES, EXPLOITS, GREETINGS

# CREDENTIALS
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
sugar_stats = load_data()

# API KEYS ROTATION
GEMINI_API_KEYS = [
    os.getenv("GEMINI_KEY_1"), 
    os.getenv("GEMINI_KEY_2"), 
    os.getenv("GEMINI_KEY_3"),
    os.getenv("GEMINI_KEY_4"),
]
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]

# FALLBACK API KEYS
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# MEMORY SETTINGS
try:
    from sugar_memory import FactMemory, DailyMemory
    from sugar_grudge import GrudgeBook, classify_tone, tone_directive
except ImportError:
    from SugarBot.sugar_memory import FactMemory, DailyMemory
    from SugarBot.sugar_grudge import GrudgeBook, classify_tone, tone_directive
sugar_facts_file = os.path.join(DATA_DIR, "sugar_facts.json")
sugar_memory_file = os.path.join(DATA_DIR, "sugar_memory.json")
fact_memory = FactMemory(sugar_facts_file)
daily_memory = DailyMemory(sugar_memory_file)
# Carnet de rancunes : rancune/rédemption par user, implicite (seul le ton la trahit)
ENABLE_GRUDGE_LLM = os.getenv("ENABLE_GRUDGE_LLM", "1") != "0"
grudge_book = GrudgeBook(os.path.join(DATA_DIR, "sugar_grudge.json"),
                         llm_enabled=ENABLE_GRUDGE_LLM)

async def _daily_llm_call(system_prompt, user_message):
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "daily_read"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client,  nvidia_client=nvidia_client,
        bot_label="Sugar Bot", temperature=0.5, max_tokens=60)

async def _grudge_llm_call(system_prompt, user_message):
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "grudge_classify"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client,  nvidia_client=nvidia_client,
        bot_label="Sugar Bot", temperature=0.0, max_tokens=6)

conversation_history = {}
MAX_HISTORY = 30

# MULTI-API KEY MANAGER
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

# ANTI-REPETITION MEMORY

response_memory = ResponseMemory()

# INITIALISATION DU BOT
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

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
        await ctx.send(f"💎 Chéri... Tu veux quoi exactement ? La commande c'est : `{ctx.command.name} {ctx.command.signature}`. 💅")
        return
    logger.error(f"❌ [COMMANDE] {ctx.command} : {error}", exc_info=error)


# Clients IA

groq_client = None
if GROQ_API_KEY:
    try: groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0)
    except Exception as e: logger.warning(f"[INIT] Groq indisponible : {e}")

mistral_client = None
if MISTRAL_API_KEY:
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
    bot=bot, bot_id="sugar", bot_label="Sugar Bot",
    personality_prompt=PERSONALITY_PROMPT,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client,  nvidia_client=nvidia_client,
    logger=logger, enabled=ENABLE_DAILY_BIO,
) if DiscordDailyBio else None

# Statut Discord auto-piloté par la personnalité (jumeau de la bio).
# La liste ci-dessous ne sert plus que de FALLBACK si le LLM est indisponible :
# le statut du jour est régénéré depuis PERSONALITY_PROMPT (cache, 0 LLM le même jour).
_STATUS_FALLBACK = [
    ("watching", "les péteurs se ridiculiser"),
    ("watching", "le caramel dorer"),
    ("watching", "fondre les cœurs"),
    ("watching", "mijoter ses répliques acidulées"),
    ("watching", "les grincheux se changer en pralines"),
    ("watching", "ses bonbons empoisonnés opérer"),
    ("playing", "à la marchande de bonbons"),
    ("playing", "à empoisonner ses caramels"),
    ("playing", "à distribuer sucre et piques"),
    ("playing", "à tremper ses vannes dans le miel"),
    ("playing", "à saupoudrer du sucre partout"),
    ("playing", "à la reine du caramel"),
    ("listening", "vos jérémiades sucrées"),
    ("listening", "craquer le sucre d'orge"),
    ("listening", "fondre la guimauve"),
    ("listening", "le glaçage craqueler"),
]
ENABLE_DAILY_STATUS = os.getenv("ENABLE_DAILY_STATUS", "1") != "0"
daily_status = DiscordDailyStatus(
    bot=bot, bot_id="sugar", bot_label="Sugar Bot",
    personality_prompt=PERSONALITY_PROMPT, fallback_activities=_STATUS_FALLBACK,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client,  nvidia_client=nvidia_client,
    logger=logger, enabled=ENABLE_DAILY_STATUS,
) if DiscordDailyStatus else None


@bot.event
async def on_ready():
    # MODE TEST (dashboard) — garde de publication + remontee des serveurs pour le
    # menu deroulant. Optionnel : sans shared/, le bot publie normalement.
    try:
        from shared.test_mode import installer_garde_publication, enregistrer_serveurs, etat_lisible
        installer_garde_publication("sugar", logger)
        enregistrer_serveurs("sugar", bot, logger)
        logger.info(f"🧪 [MODE TEST:sugar] {etat_lisible('sugar')}")
    except ImportError:
        pass  # shared/ est optionnel, le bot doit tourner sans

    # FILET ANTI-MENTION INVENTEE. Meme point de passage que la garde ci-dessus.
    # Le 2026-09-07, `!rumeur` a publie `<@123456789>` : un identifiant que le modele
    # a fabrique faute d'en avoir un vrai. Un `try` separe — ces deux filets ne
    # dependent pas l'un de l'autre.
    try:
        from shared.mentions import installer_filtre_mentions
        installer_filtre_mentions("sugar", logger)
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

    logger.info("=" * 60)
    logger.info("Sugar Bot est en ligne.")
    logger.info("=" * 60)
    logger.info(f'Connecté en tant que: {bot.user.name} ({bot.user.id})')
    
    ensure_data_writable("sugar", DATA_DIR, logger)
    logger.info(f'🏫 Serveurs: {len(bot.guilds)}')
    logger.info(f'👥 Utilisateurs visibles: {len(bot.users)}')
    
    # Enregistrement des commandes : une seule fois (on_ready peut refire au RESUME)
    global _ready_setup_done
    run_command_setup = not _ready_setup_done
    _ready_setup_done = True

    # Setup Slash Commands
    if run_command_setup and DATABASE_AVAILABLE:
        try:
            setup_slash_commands(bot, "Sugar Bot")
            await sync_slash_commands(bot)
        except Exception as e:
            logger.error(f"[SLASH] Erreur: {e}")

    # Setup Mini-Games
    if run_command_setup and DATABASE_AVAILABLE and GAMES_AVAILABLE:
        try:
            setup_games(bot, logger, PERSONA)
            logger.info("[GAMES] Mini-jeux initialisés pour Sugar Bot")
        except Exception as e:
            logger.error(f"[GAMES] Erreur d'initialisation des mini-jeux: {e}")
    
    # Stats
    logger.info("📊 ARSENAL D'APIs:")
    logger.info(f'   ✅ Gemini : {len([k for k in GEMINI_API_KEYS if k])} clés')
    logger.info(f'   ✅ Groq : {"Oui" if GROQ_API_KEY else "Non"}')
    logger.info(f'   ✅ Mistral : {"Oui" if MISTRAL_API_KEY else "Non"}')
    logger.info(f'   ✅ NVIDIA : {"Oui" if NVIDIA_API_KEY else "Non"}')
    
    logger.info("📊 STATISTIQUES SUGAR BOT:")
    logger.info(f'   📖 Exploits racontés : {sugar_stats.get("tales_told", 0)}')
    
    logger.info("Sugar Bot est prêt.")
    logger.info("=" * 60)
    
    # Statut tournant (1er tick immédiat, puis toutes les 30 min)
    if not status_loop_sugar.is_running():
        status_loop_sugar.start()

    # Tâches périodiques
    if DATABASE_AVAILABLE and not daily_birthday_check.is_running():
        daily_birthday_check.start()
    if daily_bio and not daily_bio_loop_sugar.is_running():
        daily_bio_loop_sugar.start()

        
    global twitch_announcer
    if TWITCH_AVAILABLE and twitch_announcer is None:
        twitch_announcer = setup_twitch_announcer(
            bot, "sugar", logger,
            personality_prompt=PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
             nvidia_client=nvidia_client, bot_label="Sugar Bot")
        if twitch_announcer:
            if not twitch_poll_loop.is_running():
                twitch_poll_loop.start()

    # Présence permanente dans le chat Twitch (persona identique à Discord).
    # Idempotent (on_ready peut refire au RESUME → garde twitch_chat is None).
    # « Silence sauf si nommé » : interjections + accueils OFF (cf. PLAN PARTIE A).
    global twitch_chat, twitch_chat_task
    if TWITCH_CHAT_AVAILABLE and twitch_chat is None:
        twitch_chat = setup_twitch_chat(
            "sugar", logger,
            personality_prompt=PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
             nvidia_client=nvidia_client, bot_label="Sugar Bot",
            tone_directive_provider=lambda author, message: tone_directive(message),
            enable_events=True,
            enable_interjections=False,   # décision « silence sauf si nommé »
            enable_greetings=False,       # idem
            enable_viewer_memory=True,
            enable_eventsub=False,        # pas de token broadcaster Sugar → évite les 403
            enable_voice_listen=False,
        )
        if twitch_chat:
            twitch_chat.extra_recent_provider = lambda: [r for hist in response_memory.memory.values() for r in hist][-6:]
            twitch_chat_task = asyncio.create_task(twitch_chat.run())

@bot.event
async def on_member_join(member):
    """Accueil des nouveaux arrivants (délégué au module partagé, en voix de Sugar)."""
    if DATABASE_AVAILABLE:
        await handle_member_join(bot, member, bot_name="Sugar Bot")

@bot.event
async def on_member_remove(member):
    """Au revoir élève"""
    if DATABASE_AVAILABLE:
        await handle_member_remove(bot, member, bot_name="Sugar Bot")

@bot.event
async def on_raw_reaction_add(payload):
    """Enregistre les réactions des utilisateurs sur les répliques du bot."""
    if not bot.user or payload.user_id == bot.user.id:
        return
    message_author_id = getattr(payload, "message_author_id", None)
    if message_author_id is None:
        try:
            channel = bot.get_channel(payload.channel_id)
            if channel:
                msg = await channel.fetch_message(payload.message_id)
                message_author_id = msg.author.id
        except Exception:
            # Silence VOULU : impossible de recuperer le message pour verifier l'auteur
            return
    if message_author_id != bot.user.id:
        return
    enregistrer_reaction(
        bot_name="sugar",
        message_id=payload.message_id,
        channel_id=payload.channel_id,
        user_id=payload.user_id,
        emoji=str(payload.emoji),
        retiree=0
    )

# Tâche quotidienne : anniversaires
@tasks.loop(hours=24)
async def daily_birthday_check():
    if DATABASE_AVAILABLE:
        for guild in bot.guilds:
            await check_and_send_birthdays(bot, bot_name="Sugar Bot")

@daily_birthday_check.before_loop
async def before_birthday_check():
    await bot.wait_until_ready()

@tasks.loop(seconds=90)
async def twitch_poll_loop():
    if twitch_announcer:
        await twitch_announcer.tick()

@twitch_poll_loop.before_loop
async def before_twitch_poll():
    await bot.wait_until_ready()

@tasks.loop(hours=1)
async def daily_bio_loop_sugar():
    if daily_bio:
        await daily_bio.ensure_daily_bio()

@daily_bio_loop_sugar.before_loop
async def before_daily_bio_sugar():
    await bot.wait_until_ready()

# STATUT TOURNANT (présence Discord) — auto-piloté par la personnalité (cf. daily_status).
@tasks.loop(minutes=30)
async def status_loop_sugar():
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
    await bot.change_presence(activity=activity)

@status_loop_sugar.before_loop
async def before_status_sugar():
    await bot.wait_until_ready()

# COMMANDES SPÉCIALES SUGAR BOT


@bot.command(name="exploit", aliases=["histoire", "legende"])
async def exploit_cmd(ctx):
    """Raconte un exploit de Sugar Bot"""
    tale = random.choice(EXPLOITS)
    sugar_stats["tales_told"] = sugar_stats.get("tales_told", 0) + 1
    save_data(sugar_stats)
    
    embed = discord.Embed(
        title="Exploit de Sugar Bot",
        description=tale,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Total : {sugar_stats['tales_told']}")
    await ctx.send(embed=embed)

@bot.command(name="chanson", aliases=["frime", "chante"])
async def chanson_cmd(ctx):
    """Sort une phrase de Sugar Bot"""
    shanty = random.choice(PUNCHLINES)
    await ctx.send(shanty)

@bot.command(name="equipage", aliases=["crew", "classe"])
async def equipage_cmd(ctx):
    """Affiche le classement de la classe"""
    if not DATABASE_AVAILABLE:
        await ctx.send("⚠️ Base de données non disponible !")
        return
    
    from shared.shared_database import get_reputation_leaderboard
    leaderboard = get_reputation_leaderboard(10)
    
    embed = discord.Embed(
        title="Classe de Sugar Bot",
        description="Les membres les plus actifs de la classe.",
        color=discord.Color.red()
    )
    
    for i, entry in enumerate(leaderboard):
        name = entry.get('display_name') or entry.get('username', 'Inconnu')
        points = entry['points']
        level = entry['level']
        
        # Déterminer le rang
        if points < 50:
            rank = "Niveau 1"
        elif points < 150:
            rank = "Niveau 2"
        elif points < 300:
            rank = "Niveau 3"
        elif points < 500:
            rank = "Niveau 4"
        else:
            rank = "Niveau 5"
        
        embed.add_field(
            name=f"{i+1}. {name}",
            value=f"{rank} • {points} pts (Niv. {level})",
            inline=False
        )
    
    embed.set_footer(text="Gagnez du respect en parlant avec Sugar Bot.")
    await ctx.send(embed=embed)

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
        
    await ctx.send("C'est fait, tes données ont été effacées.")

# LOGIQUE CONVERSATIONNELLE

# Noms des AUTRES bots du serveur : si l'échange leur est visiblement adressé, Sugar Bot
# ne s'incruste PAS lors d'une intervention ALÉATOIRE (les mentions/noms directs de Sugar Bot
# restent toujours prioritaires et passent avant cette garde).
OTHER_BOT_NAMES = [
    "sheo", "sheogorath", "johnny", "silverhand", "samurai",
    "alfred", "pennyworth", "m'aiq", "maiq", "malena", "malèna",
]


async def _other_bot_in_focus(message):
    """True si la conversation est manifestement tournée vers un AUTRE bot (on ne barge pas).
    N'est consulté QUE pour une intervention aléatoire (rare) → coût historique négligeable."""
    if any(n in message.content.lower() for n in OTHER_BOT_NAMES):
        return True
    try:
        async for prev in message.channel.history(limit=4, before=message):
            if prev.author == bot.user:
                return False  # Sugar Bot était déjà dans la boucle → ok d'enchaîner
            if prev.author.bot:
                return True   # un autre bot vient de parler → c'est SON échange
            if any(n in prev.content.lower() for n in OTHER_BOT_NAMES):
                return True   # un humain vient de nommer un autre bot
    except Exception:
        return False
    return False


@bot.event
async def on_message(message):
    # Ignorer les messages du bot lui-même
    if message.author == bot.user:
        return

    # IGNORER SES PROPRES IMPOSTEURS (Webhooks nommés Sugar)
    if message.webhook_id and "sugar" in message.author.display_name.lower():
        return
        
    # SILENCE STREAM (Canal ignoré) — is_ignored_channel provient de shared (optionnel)
    if DATABASE_AVAILABLE and is_ignored_channel(message.channel):
        return
    
    # Vérification mode maintenance AVANT process_commands
    if DATABASE_AVAILABLE and is_maintenance_mode():
        return
    
    # Traiter les commandes
    await bot.process_commands(message)

    # Un message qui est une commande de CE bot a deja produit sa reponse :
    # il ne doit pas repartir dans le chemin LLM (bavardage aleatoire compris).
    ctx = await bot.get_context(message)
    if ctx.valid:
        return

    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    if message.author.bot:
        return

    # Conditions de réponse
    is_mentioned = bot.user in message.mentions
    is_reply = message.reference and message.reference.resolved and message.reference.resolved.author == bot.user
    is_dm = isinstance(message.channel, discord.DMChannel)
    
    # Noms alternatifs pour Sugar Bot (détection dans le message)
    SUGAR_NAMES = ["sugar", "sugar bot"]
    content_lower = message.content.lower()
    is_name_mentioned = any(name in content_lower for name in SUGAR_NAMES)
    
    # Les autres bots sont filtrés en amont (silence total entre bots).
    is_bot_talking = False

    # Détection image très tôt (pour priorité)
    has_image_early = classify_request(message.content, message.attachments, silent=True)["has_image"]
    
    should_respond = False
    keyword_boost = ""
    
    # A. Message direct (mention, reply, DM, ou nom alternatif)
    if is_mentioned or is_reply or is_dm or (is_name_mentioned and not is_bot_talking):
        should_respond = True

        # Log si invoqué par nom alternatif
        if is_name_mentioned and not is_mentioned:
            logger.info(f"[NOM ALTERNATIF] Sugar Bot invoqué par nom dans le message de {message.author.name}")

        # Database
        if DATABASE_AVAILABLE and not is_dm:
            get_or_create_user(message.author.id, message.author.name, message.author.display_name)
            log_interaction(message.author.id, "Sugar Bot", "mention")

    # L'image d'un message cité n'est récupérée que si on s'adresse à Sugar ;
    # sinon on garde les attachments du message courant (comportement d'origine).
    atts = await resolve_media_attachments(message) if should_respond else message.attachments
    
    
    # ══════════════════════════════════════════════════
    # LTM SYSTEM - MEMORY INJECTION (paresseux)
    # On ne calcule la mémoire (recherche embeddings, etc.) QUE si un chemin qui
    # répond la consomme réellement → pas de coût sur les messages ignorés.
    # ══════════════════════════════════════════════════
    user_id = message.author.id
    user_name = message.author.name
    _memory_cache = {}
    
    def _get_memory_addition():
        if "val" not in _memory_cache:
            user_message_temp = message.content.replace(f'<@{bot.user.id}>', '').strip()
            relevant_facts = fact_memory.get_relevant_facts(user_id, user_message_temp, k=3)
            daily_summary = daily_memory.get_context_summary(user_id)
            dr = daily_memory.get_daily_read(user_id)
            daily_read_addition = f"\n[CONSIGNE DU JOUR] {dr}" if dr else ""

            # Carnet de rancunes : les événements de ton ne comptent que si le
            # message est ADRESSÉ à Sugar (sinon on lit juste le score courant).
            _grudge_addressed = bool(is_mentioned or is_reply or is_dm or is_name_mentioned)
            grudge_addition = grudge_book.update(
                user_id, user_message_temp, addressed=_grudge_addressed)
            # Raffinement LLM en tâche de fond (jamais dans le chemin de réponse)
            if _grudge_addressed and grudge_book.should_refine(
                    user_id, user_message_temp, classify_tone(user_message_temp)):
                import asyncio as _asyncio
                _asyncio.create_task(grudge_book.refine_async(
                    user_id, user_message_temp, _grudge_llm_call))

            fact_context = ""
            if relevant_facts:
                fact_context = f"\n[CE QUE TU SAIS SUR CET INTERLOCUTEUR (MÉMOIRE LONG TERME)]:\n- " + "\n- ".join(relevant_facts)

            profile_context = ""
            rep = get_reputation(user_id) if DATABASE_AVAILABLE else None
            quests = get_daily_quests(user_id) if DATABASE_AVAILABLE else None
            profile = construire_profil_discord(message.author, reputation_data=rep, quests_data=quests)
            if profile:
                profile_context = f"\n\n{profile}"

            _memory_cache["val"] = (
                f"\n\n[CONTEXTE DE MÉMOIRE]"
                f"{fact_context}"
                f"{profile_context}"
                f"\n{daily_summary}"
                f"{daily_read_addition}"
                f"{grudge_addition}"
                f"\n\n[INSTRUCTION MÉMOIRE CONCOMITANTE]: Si tu apprends un fait durable, important et nouveau sur cet élève — ses préférences, son métier, ses projets, mais AUSSI sa façon d'argumenter, ce qui le pique, ses habitudes (le connaître sert à mieux le contrer) — ajoute-le discrètement à la fin de ta réponse entouré de balises XML : <fact>Le fait appris</fact>.\n"
                f"⚠️ RÈGLE ABSOLUE : un fait ne peut s'appuyer que sur ce qui vient DE LUI — SES messages, son profil public, sa bio, ses actes. Ne lui attribue JAMAIS un thème, un mot ou une image que c'est TOI qui as introduit — tes propres réponses font partie de la conversation et ne t'apprennent rien sur lui. Si rien de neuf n'est venu de LUI, ne mets rien."
            )
        return _memory_cache["val"]

    def _get_meme_addition():
        chan_id = message.channel.id
        consigne = build_meme_consigne(message.content or "", set(meme_recent[chan_id]))
        # mémorise la ref proposée pour ne pas la re-proposer en boucle dans ce salon
        if consigne:
            import re as _re
            m = _re.search(r"« (.+?) »", consigne)
            if m:
                meme_recent[chan_id].append(m.group(1))
        return consigne


    # C. Intervention aléatoire (10%) — sauf si l'échange vise un AUTRE bot
    if not is_bot_talking and not should_respond and not has_image_early and random.random() < 0.10:
        if await _other_bot_in_focus(message):
            logger.info("[ANTI-INCRUSTATION] Échange adressé à un autre bot → Sugar Bot se tait.")
        else:
            should_respond = True
            logger.info(f"[INTERVENTION] Sugar Bot intervient dans {message.channel.name}")
    
    if not should_respond:
        return
    
    # PREPARATION DU MESSAGE
    user_message = message.content.replace(f'<@{bot.user.id}>', '').strip()

    user_msg_content = user_message
    content_lower = user_message.lower()
    keyword_boost = ""

    # HISTORIQUE
    channel_id = message.channel.id
    if channel_id not in conversation_history:
        conversation_history[channel_id] = []
    
    conversation_history[channel_id].append({
        "role": "user",
        "parts": [f"{message.author.name}: {user_message}"]
    })
    
    if len(conversation_history[channel_id]) > MAX_HISTORY:
        conversation_history[channel_id] = conversation_history[channel_id][-MAX_HISTORY:]
    
    # TRANSCRIPT
    transcript = "CONTEXTE DU SALON (Chronologique) :\n"
    _chrono = Chrono("sugar", message.channel.id)
    messages_list = []
    async for hist_msg in message.channel.history(limit=10):
        messages_list.append(hist_msg)
    
    for hist_msg in reversed(messages_list):
        ligne = ligne_de_contexte(hist_msg, bot.user, avec_mention=False)
        if ligne:
            transcript += ligne
    
    # ANTI-RÉPÉTITION (fusion Discord + Twitch : pont anti-doublon inter-canaux)
    recent_responses = merge_recent_responses(
        response_memory.get_recent(message.guild.id if message.guild else 0),
        _twitch_recent_responses(),
    )
    anti_repeat_prompt = ""
    if recent_responses:
        snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        anti_repeat_prompt = "\n\n[ANTI-RÉPÉTITION] Tu as déjà dit récemment :\n"
        for i, snippet in enumerate(snippets, 1):
            anti_repeat_prompt += f"{i}. \"{snippet}\"\n"
        anti_repeat_prompt += ("Ne réutilise NI ces phrases NI leur OSSATURE : change d'ouverture "
            "(surtout PAS de vocatif « Oh, mon… » si tu viens de l'employer) et ne finis PAS "
            "encore par une question. Prends un angle, un rythme et une chute différents. "
            "Ne réutilise AUCUN mot-clé saillant de ces répliques (mots en MAJUSCULES, images, "
            "métaphores, chutes) : si l'une d'elles crie ÉVALUATION, toi tu pars ailleurs.")

    # ANTI-TICS : les amorces/clôtures/mots récurrents des dernières répliques, interdits
    # nommément. L'anti-répétition ci-dessus cite des phrases ; celui-ci vise le MOULE.
    # ⚠️ TOUT ce que les mortels ont dit, pas seulement le dernier message : sinon
    # le filet interdit le SUJET de la conversation des qu'on cesse de le renommer.
    _mots_des_mortels = [m.content for m in messages_list if not m.author.bot and m.content]
    _consigne_anti_tic = build_anti_tic_consigne(recent_responses, message_utilisateur=_mots_des_mortels)
    anti_tic = f"\n\n{_consigne_anti_tic}" if _consigne_anti_tic else ""

    try:
        from core.repartee_lessons import detect_defeat_signal, reflect_on_defeat, format_for_prompt
        from core.safe_client import get_client as get_safe_genai_client
        
        bloc_lecons = format_for_prompt("Sugar")
        if bloc_lecons:
            anti_tic += bloc_lecons
            
        motif_defaite = detect_defeat_signal(user_message)
        if motif_defaite and recent_responses:
            asyncio.create_task(
                reflect_on_defeat(
                    bot_id="Sugar",
                    guild_id=str(message.guild.id) if message.guild else "DM",
                    categorie=motif_defaite,
                    repliques=recent_responses,
                    fournisseur="gemini",
                    key_manager=key_manager,
                    bot_label="Sugar Bot",
                    modele=GEMINI_FLASH,
                    timeout=15,
                    fabrique=lambda cle: get_safe_genai_client(api_key=cle),
                    methode="models.generate_content",
                    model=GEMINI_FLASH,
                )
            )
    except ImportError as e:
        logger.warning(f"carnet de repartie indisponible : {e}")
    
    # ═══ SMART ROUTER — Classification du message ═══
    _addressed = bool(is_mentioned or is_reply or is_dm or is_name_mentioned)
    routing = classify_request(user_message, atts, addressed=_addressed)
    
    # Téléchargement Média
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
        user_message = "(L'utilisateur montre une image sans rien dire.)"
    if has_image:
        user_message += "\n[VISION] Regarde l'image et commente-la comme Sugar le ferait ! Décris ce que tu vois avec ton exubérance !"
    if has_audio:
        user_message += "\n[🎤 VOCAL] L'utilisateur a envoyé un message vocal. Écoute-le et réponds avec ton style exubérant !"
    

    # GÉNÉRATION (Smart Router)
    
    response_text = None
    system_prompt = f"SYSTEM: {PERSONALITY_PROMPT}{_get_memory_addition()}{_get_meme_addition()}\n{transcript}{keyword_boost}{anti_repeat_prompt}{anti_tic}"
    
    async with message.channel.typing():
        
        _chrono.etape("contexte")
        response_text = await generate_response(
            routing=routing,
            system_prompt=system_prompt,
            transcript=transcript,
            user_message=user_message,
            conversation_history=conversation_history.get(channel_id, []),
            media_data=media_data,
            mime_type=mime_type,
            key_manager=key_manager,
            mistral_client=mistral_client,
            groq_client=groq_client,
             nvidia_client=nvidia_client,
            bot_label="Sugar Bot",
            max_tokens=150,
            gemini_max_tokens=150,
        )

        # Cas d'échec multimodal (Image/Audio)
        if not response_text and (has_image or has_audio):
            media_type = "image" if has_image else "message vocal"
            item_name = "l'image" if has_image else "le message vocal"
            await message.channel.send(f"Désolé, je n'ai pas pu lire {item_name}.")
            return
        
        # FALLBACK FINAL
        if not response_text:
            if is_bot_talking:
                logger.info("[SILENCE] Echec API vs Bot - Stop boucle.")
                return
            response_text = random.choice(GREETINGS)
    
    # NETTOYAGE
    if response_text:
        import re
        matches = re.findall(r"<fact>(.*?)</fact>", response_text, re.DOTALL | re.IGNORECASE)
        for f in matches:
            fact_text = f.strip()
            if fact_text:
                fact_memory.add_fact(user_id, fact_text)
                
        # Un SEUL chemin de nettoyage, partage mot pour mot avec le harnais d'evaluation :
        # deux enchainements paralleles finissent toujours par diverger, et c'est alors le
        # score qui ment. Cf. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].
        # ⚠️ `user_msg_content` et NON `user_message` : ce dernier a pu recevoir le
        # texte de substitution des images (« L'utilisateur montre une image... »). Le
        # budget de mots doit lire ce que l'interlocuteur a REELLEMENT ecrit.
        response_text = filtre_sortie(response_text, user_msg_content)

    response_text = response_text.strip()

    # Cadence des petits noms sucrés : pas deux répliques d'affilée qui en portent un
    # (sinon « mon nougat / mon caramel / mon berlingot » à chaque message). Si la
    # réponse précédente dans ce salon en avait un, on retire le sucre de celle-ci.
    if _last_reply_had_vocative.get(channel_id):
        response_text = _strip_sweet_vocatives(response_text)
    _last_reply_had_vocative[channel_id] = _has_sweet_vocative(response_text)

    # Sauvegarde anti-répétition
    if message.guild:
        response_memory.add(message.guild.id, response_text)
    
    # Sauvegarde historique
    conversation_history[channel_id].append({
        "role": "assistant",
        "parts": [response_text]
    })

    # LTM - Daily interaction logging
    daily_memory.add_interaction(user_id, user_name, user_msg_content, response_text)
    asyncio.create_task(daily_memory.refresh_daily_read(user_id, _daily_llm_call))
    
    # Récompense réputation
    if DATABASE_AVAILABLE and not is_dm and not is_bot_talking:
        add_reputation(message.author.id, points=2, reason="Conversation avec Sugar Bot")
    
    _chrono.etape("llm")

    # ENVOI
    await message.reply(response_text)
    _chrono.fin(envoye=True)

# LANCEMENT

async def on_sugar_shutdown():
    global twitch_chat, twitch_chat_task
    if twitch_chat:
        logger.info("[SHUTDOWN] Arrêt du chat Twitch Sugar...")
        twitch_chat.stop()
    if twitch_chat_task:
        twitch_chat_task.cancel()
        try:
            await twitch_chat_task
        except asyncio.CancelledError:
            pass  # annulation attendue : c'est nous qui venons d'appeler cancel()

if __name__ == "__main__":
    if DISCORD_TOKEN:
        # Un `tasks.loop` rejoue TOUTES les iterations manquees quand l'horloge saute
        # (veille de l'hote) : 40 `MOOD CHANGE` en deux secondes le 2026-09-04.
        installer_anti_rattrapage(logger)
        setup_graceful_shutdown(bot, on_sugar_shutdown, journal=logger)
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ ERREUR : Aucun token Discord trouvé dans le fichier .env !")
