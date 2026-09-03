# INJECTION SHARED FOLDER
import sys
import os
import asyncio
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
import random
import json
import base64
from core.response_memory import ResponseMemory, merge_recent_responses
import logging
from datetime import datetime
from core.smart_router import classify_request, RequestType, download_media, resolve_media_attachments
from core.media_handler import process_image_ollama
from core.llm_cascade import generate_response

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
logger = setup_logger("johnny")

# FILE PATHS
DATA_DIR = os.getenv("DATA_DIR", ".")
DATA_FILE = os.path.join(DATA_DIR, "johnny_data.json")

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"⚠️ Lecture {DATA_FILE} impossible ({e}) — valeurs par défaut.")
    return {"missions_completed": 0, "gifts_given": 0, "mead_consumed": 0}

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        logger.warning(f"⚠️ Sauvegarde {DATA_FILE} impossible ({e}) — état non persisté.")

# IMPORT SECURE ENV LOADER
from pathlib import Path
from core.secure_env import load_secure_env
load_secure_env(Path(__file__).parent)

# IMPORT SAFE CLIENT
from core.safe_client import get_client as get_safe_genai_client

# IMPORT DES SYSTÈMES (locaux pour Discloud)
try:
    from shared.shared_database import (
        get_or_create_user, add_reputation, log_interaction,
        is_maintenance_mode, is_ignored_channel
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
    logger.warning(f"⚠️ [JOHNNY] Modules optionnels non disponibles: {e}")
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

try:
    from shared.twitch_economy import PointsEconomy
    TWITCH_ECONOMY_AVAILABLE = True
except ImportError:
    TWITCH_ECONOMY_AVAILABLE = False
    class PointsEconomy:
        def __init__(self, *a, **k): pass

johnny_cred = None

try:
    from shared.ensure_writable import ensure_data_writable
except ImportError:
    def ensure_data_writable(*args, **kwargs): pass

try:
    from shared.discord_profile import DiscordDailyBio
except ImportError:
    DiscordDailyBio = None

try:
    from shared.discord_status import DiscordDailyStatus
except ImportError:
    DiscordDailyStatus = None


# IMPORT PERSONNALITÉ JOHNNY
from johnny_data import (
    PERSONALITY_PROMPT, DIPLOMATIC_TALES, GIFT_RESPONSES,
    SKYRIM_RESPONSES, MEAD_RESPONSES, GREETINGS,
    CULTURAL_CONFUSION, GIFT_TRIGGERS,
    MISSION_TRIGGERS, SKYRIM_TRIGGERS, MEAD_TRIGGERS,
    TWITCH_BIO, JOHNNY_TWITCH_RANKS, JOHNNY_TWITCH_KEYWORDS, TWITCH_GREETINGS
)

# CREDENTIALS
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
johnny_data = load_data()

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
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# MEMORY SETTINGS
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
key_manager.register_api("openrouter", [OPENROUTER_API_KEY] if OPENROUTER_API_KEY else [])

# ANTI-REPETITION MEMORY
response_memory = ResponseMemory()

# Configuration du Bot (Johnny)
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
        await ctx.send(f"🎸 Eh choomba, t'as oublié la moitié de ta phrase : `{ctx.command.name} {ctx.command.signature}`. 🦾")
        return
    logger.error(f"❌ [COMMANDE] {ctx.command} : {error}", exc_info=error)


# Clients IA

groq_client = None
if GROQ_API_KEY:
    try: groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e: logger.warning(f"[INIT] Groq indisponible : {e}")

mistral_client = None
if MISTRAL_API_KEY:
    try: mistral_client = Mistral(api_key=MISTRAL_API_KEY)
    except Exception as e: logger.warning(f"[INIT] Mistral indisponible : {e}")

openrouter_client = None
if OPENROUTER_API_KEY:
    try: openrouter_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    except Exception as e: logger.warning(f"[INIT] OpenRouter indisponible : {e}")

ENABLE_DAILY_BIO = os.getenv("ENABLE_DAILY_BIO", "1") != "0"
daily_bio = DiscordDailyBio(
    bot=bot, bot_id="johnny", bot_label="Johnny Silverhand",
    personality_prompt=PERSONALITY_PROMPT,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, openrouter_client=openrouter_client,
    logger=logger, enabled=ENABLE_DAILY_BIO,
) if DiscordDailyBio else None

# Statut Discord auto-piloté par la personnalité (jumeau de la bio).
# La liste ci-dessous n'est plus qu'un FALLBACK si le LLM est indisponible.
_STATUS_FALLBACK = [
    ("listening", "Chippin' In | 🎸 Samurai"),
    ("listening", "Never Fade Away | 🎸 Samurai"),
    ("listening", "A Like Supreme | 🎸 Samurai"),
    ("listening", "The Ballad of Buck Ravers | 🎸 Samurai"),
    ("listening", "Black Dog | 🎸 Samurai"),
    ("listening", "Archangel | 🎸 Samurai"),
    ("listening", "Night City cramer 🔥"),
    ("listening", "les corpos crever"),
    ("listening", "Arasaka tomber"),
    ("listening", "un vieux vinyle dans l'AV"),
    ("listening", "la révolution gronder"),
    ("listening", "le silence avant l'émeute"),
]
ENABLE_DAILY_STATUS = os.getenv("ENABLE_DAILY_STATUS", "1") != "0"
daily_status = DiscordDailyStatus(
    bot=bot, bot_id="johnny", bot_label="Johnny Silverhand",
    personality_prompt=PERSONALITY_PROMPT, fallback_activities=_STATUS_FALLBACK,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, openrouter_client=openrouter_client,
    logger=logger, enabled=ENABLE_DAILY_STATUS,
) if DiscordDailyStatus else None


# LTM - LONG TERM MEMORY SYSTEM
import re
try:
    from johnny_memory import FactMemory, DailyMemory
except ImportError:
    from JohnnyBot.johnny_memory import FactMemory, DailyMemory
from core.smart_router import RequestType

johnny_facts_file = os.path.join(DATA_DIR, "johnny_facts.json")
johnny_memory_file = os.path.join(DATA_DIR, "johnny_memory.json")
fact_memory = FactMemory(johnny_facts_file)

async def consolidate_daily_memory(memory_dict):
    """
    Callback asynchrone pour consolider les conversations quotidiennes
    de Johnny en faits persistants dans fact_memory.
    """
    conversations = memory_dict.get("conversations", [])
    if not conversations:
        return
        
    logger.info("🧠 [LTM] Début de la consolidation quotidienne pour Johnny...")
    
    # Grouper par utilisateur
    user_conversations = {}
    for conv in conversations:
        uid = conv.get("user_id")
        if not uid:
            continue
        if uid not in user_conversations:
            user_conversations[uid] = []
        user_conversations[uid].append(conv)
        
    for uid, chats in user_conversations.items():
        user_name = chats[0].get("user", "le voyageur")
        
        # Formater l'historique
        chat_text = ""
        for c in chats:
            chat_text += f"{c['user']}: {c['content']}\nJohnny: {c['response']}\n"
            
        prompt = f"""
        Tu es Johnny Silverhand, rockerboy charismatique et cynique. Tu dois résumer les conversations de la journée avec {user_name} sous forme de faits durables, clairs et concis sur lui (ses préférences, ses opinions, ses modifications corporelles, son comportement, etc.).
        Fais des phrases courtes, directes et cyniques à la troisième personne (ex: "Il déteste les corpos" ou "Elle traîne beaucoup au bar de Kabuki").
        
        Historique de la journée :
        {chat_text}
        
        Génère uniquement une liste de nouveaux faits, chacun entouré de balises <fact>Le fait appris</fact>. Si tu n'apprends rien de durable ou de nouveau sur lui, ne renvoie rien.
        """
        
        routing = {"type": RequestType.TEXT, "reason": f"Consolidation quotidienne user {uid}"}
        try:
            resp_text = await generate_response(
                routing=routing,
                system_prompt="Tu es Johnny Silverhand, rockerboy anarchiste et observateur cynique de Night City.",
                transcript="",
                user_message=prompt,
                conversation_history=[],
                media_data=None,
                mime_type="",
                key_manager=key_manager,
                mistral_client=mistral_client,
                groq_client=groq_client,
                openrouter_client=openrouter_client,
                bot_label="Johnny",
                temperature=0.4
            )
            
            if resp_text:
                matches = re.findall(r"<fact>(.*?)</fact>", resp_text, re.DOTALL | re.IGNORECASE)
                for f in matches:
                    fact_text = f.strip()
                    if fact_text:
                        fact_memory.add_fact(uid, fact_text)
                        
        except Exception as e:
            logger.error(f"Erreur lors de la consolidation LTM pour {user_name} ({uid}) : {e}")

daily_memory = DailyMemory(johnny_memory_file, on_reset=consolidate_daily_memory)

async def _daily_llm_call(system_prompt, user_message):
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "daily_read"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client, openrouter_client=openrouter_client,
        bot_label="Johnny", temperature=0.5, max_tokens=60)

@bot.event
async def on_ready():
    logger.info("=" * 60)
    logger.info("🎸 JOHNNY SILVERHAND — Rockerboy de Night City est prêt !")
    logger.info("=" * 60)
    logger.info(f'🎸 Connecté en tant que: {bot.user.name} ({bot.user.id})')

    # MODE TEST (dashboard) — garde de publication + remontee des serveurs pour le
    # menu deroulant. Optionnel : sans shared/, le bot publie normalement.
    try:
        from shared.test_mode import installer_garde_publication, enregistrer_serveurs, etat_lisible
        installer_garde_publication("johnny", logger)
        enregistrer_serveurs("johnny", bot, logger)
        logger.info(f"🧪 [MODE TEST:johnny] {etat_lisible('johnny')}")
    except ImportError:
        pass
    
    ensure_data_writable("johnny", DATA_DIR, logger)
    
    logger.info(f'🏰 Serveurs: {len(bot.guilds)}')
    logger.info(f'👥 Utilisateurs visibles: {len(bot.users)}')
    
    # Setup Slash Commands
    if DATABASE_AVAILABLE:
        try:
            setup_slash_commands(bot, "Johnny Silverhand")
            await sync_slash_commands(bot)
        except Exception as e:
            logger.error(f"[SLASH] Erreur: {e}")
            
    # Setup Mini-Games
    if DATABASE_AVAILABLE and GAMES_AVAILABLE:
        try:
            setup_games(bot, logger, PERSONA)
            logger.info("🎸 [GAMES] Mini-jeux initialisés pour Johnny")
        except Exception as e:
            logger.error(f"[GAMES] Erreur d'initialisation des mini-jeux: {e}")
    
    # Stats
    logger.info("📊 ARSENAL D'APIs:")
    logger.info(f'   ✅ Gemini : {len([k for k in GEMINI_API_KEYS if k])} clés')
    logger.info(f'   ✅ Groq : {"Oui" if GROQ_API_KEY else "Non"}')
    logger.info(f'   ✅ Mistral : {"Oui" if MISTRAL_API_KEY else "Non"}')
    logger.info(f'   ✅ OpenRouter : {"Oui" if OPENROUTER_API_KEY else "Non"}')
    
    logger.info("🎖️ STATISTIQUES DE JOHNNY:")
    logger.info(f'   🎸 Gigs terminés : {johnny_data.get("missions_completed", 0)}')
    logger.info(f'   🔫 Loot récupéré : {johnny_data.get("gifts_given", 0)}')
    logger.info(f'   🥃 Verres sifflés : {johnny_data.get("mead_consumed", 0)}')
    
    logger.info("🎯 Johnny est prêt à faire cramer la ville !")
    logger.info("=" * 60)
    
    # Statut tournant (1er tick immédiat, puis toutes les 30 min)
    if not status_loop_johnny.is_running():
        status_loop_johnny.start()

    # Tâches périodiques
    if DATABASE_AVAILABLE:
        daily_birthday_check.start()
    if daily_bio and not daily_bio_loop_johnny.is_running():
        daily_bio_loop_johnny.start()

        
    global twitch_announcer, twitch_chat, twitch_chat_task, johnny_cred
    if TWITCH_AVAILABLE and twitch_announcer is None:
        twitch_announcer = setup_twitch_announcer(
            bot, "johnny", logger,
            personality_prompt=PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
            openrouter_client=openrouter_client, bot_label="Johnny")
        if twitch_announcer:
            twitch_poll_loop.start()

    if TWITCH_CHAT_AVAILABLE and twitch_chat is None:
        # Initialisation du système de Street Cred cloisonné pour Twitch
        if TWITCH_ECONOMY_AVAILABLE:
            johnny_cred = PointsEconomy(
                filename=os.path.join(DATA_DIR, "johnny_cred_twitch.json"),
                ranks=JOHNNY_TWITCH_RANKS,
                keywords=JOHNNY_TWITCH_KEYWORDS
            )

        # Commandes Twitch Johnny
        def cmd_johnny(author: str, args: str) -> str:
            quotes = [
                "Réveille-toi, Samurai. On a une ville à faire cramer. 🎸",
                "Le système est corrompu jusqu'à la moelle, choom. 🚬",
                "Arasaka a besoin d'une bonne ogive nucléaire. À nouveau. 🔥",
                "Je ne suis qu'un engramme dans ta tête de gonk.",
                "Fais cracher le plomb sur le premier corpo venu. 🤘"
            ]
            return f"🎸 {random.choice(quotes)}"

        def cmd_chrome(author: str, args: str) -> str:
            quotes = [
                "Mon bras argenté ? Le meilleur chrome que j'aie jamais eu. 🤘",
                "Soit tu te fais poser du chrome de combat, soit tu finis à la morgue de Kabuki.",
                "Kiroshi, Kerenzikov... peu importe, tant que ça t'aide à flinguer du costume.",
                "Les rippers de rue te vendraient leur mère pour deux eddies. Fais gaffe.",
                "Du chrome d'occasion ? Autant se faire sauter la cervelle tout de suite."
            ]
            return f"🤘 {random.choice(quotes)}"

        async def cmd_punchline(author: str, args: str) -> str:
            prompt = f"Balance une punchline cyberpunk cynique et arrogante à @{author}. Reste dans la peau de Johnny Silverhand. Pas de blabla inutile, juste la punchline directe, courte (max 150 caractères), sans guillemets ni astérisques."
            try:
                text = await generate_response(
                    routing={"type": RequestType.TEXT, "reason": "twitch_punchline"},
                    system_prompt=PERSONALITY_PROMPT,
                    transcript="",
                    user_message=prompt,
                    conversation_history=[],
                    media_data=None,
                    mime_type="",
                    key_manager=key_manager,
                    mistral_client=mistral_client,
                    groq_client=groq_client,
                    openrouter_client=openrouter_client,
                    bot_label="Johnny",
                    temperature=0.9,
                    max_tokens=60
                )
                if text:
                    text = " ".join(text.split()).strip()
                    from shared.twitch_chat import TwitchChatBot
                    text = TwitchChatBot._strip_stage_directions(text)
                    text = text.strip('"\'')
                    return text[:450]
            except Exception as e:
                logger.error(f"❌ [TWITCH_CMD_PUNCHLINE] Erreur LLM : {e}")

            fallback_punchlines = [
                f"Hé @{author}, t'as l'air d'un costard-cravate qui s'est perdu dans les Badlands. Minable. 🚬",
                f"@{author}, t'es juste un autre gonk qui attend que le NCPD vienne lui torcher le cul.",
                f"Dis-moi @{author}, ton chrome vient d'une benne à ordures de Kabuki ?"
            ]
            return random.choice(fallback_punchlines)

        def cmd_cred(author: str, args: str) -> str:
            if not TWITCH_ECONOMY_AVAILABLE or johnny_cred is None:
                return "Système de Street Cred non disponible. 🚬"
            pts = johnny_cred.get_points(author)
            rank = johnny_cred.get_rank(author)
            return f"@{author}, tu as {pts} points de Street Cred. Rang actuel : {rank['emoji']} {rank['name']} !"

        def cmd_classement(author: str, args: str) -> str:
            if not TWITCH_ECONOMY_AVAILABLE or johnny_cred is None:
                return "Système de Street Cred non disponible. 🚬"
            top = johnny_cred.leaderboard(n=10)
            if not top:
                return "Personne n'a encore de Street Cred dans cette décharge !"
            lines = []
            for i, (name, pts) in enumerate(top, 1):
                rank = johnny_cred.get_rank(name)
                lines.append(f"{i}. {name} ({pts} pts, {rank['emoji']} {rank['name']})")
            return "Les mercenaires les plus respectés de Night City : " + " | ".join(lines)

        async def twitch_passive_handler(author: str, text: str) -> str | None:
            if not TWITCH_ECONOMY_AVAILABLE or johnny_cred is None:
                return None
            # try_award applique l'anti-farm (cooldown par viewer) avant de créditer.
            awarded = johnny_cred.try_award(author, text)
            if awarded:
                cred_points, total, old_rank, new_rank, rank_up = awarded
                if rank_up:
                    rank_up_msgs = [
                        "🎉 **STREET CRED UP !** {user} passe au rang de **{rank}** {emoji} ! Tu commences à te faire un nom dans cette putain de ville !",
                        "⚡ **NOUVEAU RANG !** {user} → **{rank}** {emoji} ! Continue comme ça et Rogue te confiera peut-être un vrai gig !",
                        "🔥 **ASCENSION !** {user} est maintenant **{rank}** {emoji} ! Même Smasher ferait bien de surveiller ses arrières !"
                    ]
                    return random.choice(rank_up_msgs).format(
                        user=f"@{author}",
                        rank=new_rank["name"],
                        emoji=new_rank["emoji"]
                    )
                elif random.random() < 0.20:
                    gain_msgs = [
                        "🤘 +{pts} Street Cred ! Respect, choom. (Total: {total})",
                        "🚬 {user} gagne +{pts} Street Cred. Ne crache pas dessus. ({total})",
                        "⚡ +{pts} Street Cred ! Tu montes en puissance, Samurai ! ({total})"
                    ]
                    return random.choice(gain_msgs).format(
                        user=f"@{author}",
                        pts=cred_points,
                        total=total
                    )
            return None

        commands = {
            "johnny": cmd_johnny,
            "chrome": cmd_chrome,
            "punchline": cmd_punchline,
            "cred": cmd_cred,
            "classement": cmd_classement
        }
        command_aliases = {
            "punch": "punchline",
            "leaderboard": "classement",
            "rep": "cred"
        }

        twitch_chat = setup_twitch_chat(
            "johnny", logger,
            personality_prompt=PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
            openrouter_client=openrouter_client, bot_label="Johnny Silverhand",
            system_prompt_provider=lambda: PERSONALITY_PROMPT,
            profile_bio=TWITCH_BIO,
            enable_events=True,
            enable_interjections=False,
            interjection_chance=0.03,
            interjection_min_interval=600.0,
            enable_greetings=False,
            greeting_templates=TWITCH_GREETINGS,
            enable_viewer_memory=True,
            viewer_memory_max=8,
            enable_eventsub=True,
            eventsub_reward_map={
                "Punchline": "punchline",
                "Chrome": "chrome"
            },
            commands=commands,
            command_aliases=command_aliases,
            passive_handler=twitch_passive_handler,
            enable_voice_listen=False
        )
        if twitch_chat:
            twitch_chat.extra_recent_provider = lambda: [r for hist in response_memory.memory.values() for r in hist][-6:]
            twitch_chat_task = asyncio.create_task(twitch_chat.run())

@bot.event
async def on_member_join(member):
    """Accueil de Johnny"""
    if DATABASE_AVAILABLE:
        await handle_member_join(bot, member, bot_name="Johnny")
        # Message personnalisé
        if member.guild.system_channel:
            await member.guild.system_channel.send(
                f"Bienvenue à Night City, {member.mention}. Essaie de pas finir en cyberpsycho avant vendredi. 🚬"
            )

@bot.event
async def on_member_remove(member):
    """Au revoir de Johnny"""
    if DATABASE_AVAILABLE:
        await handle_member_remove(bot, member, bot_name="Johnny")

# Tâche quotidienne : anniversaires
@tasks.loop(hours=24)
async def daily_birthday_check():
    if DATABASE_AVAILABLE:
        await check_and_send_birthdays(bot, "Johnny")

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
async def daily_bio_loop_johnny():
    if daily_bio:
        await daily_bio.ensure_daily_bio()

@daily_bio_loop_johnny.before_loop
async def before_daily_bio_johnny():
    await bot.wait_until_ready()


# STATUT TOURNANT (présence Discord)
@tasks.loop(minutes=30)
async def status_loop_johnny():
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

@status_loop_johnny.before_loop
async def before_status_johnny():
    await bot.wait_until_ready()


# COMMANDES SPÉCIALES JOHNNY SILVERHAND

@bot.command(name="gig", aliases=["job", "mission", "run", "contrat"])
async def gig_cmd(ctx):
    """Johnny raconte un de ses braquages ou concerts légendaires"""
    tale = random.choice(DIPLOMATIC_TALES)
    johnny_data["missions_completed"] = johnny_data.get("missions_completed", 0) + 1
    save_data(johnny_data)
    
    embed = discord.Embed(
        title="🎸 GIG DE JOHNNY SILVERHAND",
        description=tale,
        color=discord.Color.red()
    )
    embed.set_footer(text=f"Gigs accomplis : {johnny_data['missions_completed']}")
    await ctx.send(embed=embed)

@bot.command(name="loot", aliases=["gift", "chrome", "eddies"])
async def loot_cmd(ctx):
    """Johnny offre du loot de rue ou du chrome"""
    response = random.choice(GIFT_RESPONSES)
    johnny_data["gifts_given"] = johnny_data.get("gifts_given", 0) + 1
    save_data(johnny_data)
    await ctx.send(f"{response}\n🔫 Loots récupérés : {johnny_data['gifts_given']}")

@bot.command(name="nightcity", aliases=["samurai", "anti-corpo"])
async def nightcity_cmd(ctx):
    """Johnny exprime sa fierté de Night City et sa haine des corpos"""
    response = random.choice(SKYRIM_RESPONSES)
    await ctx.send(response)

@bot.command(name="whisky", aliases=["clope", "drink"])
async def whisky_cmd(ctx):
    """Johnny siffle un verre de whisky ou allume une clope"""
    response = random.choice(MEAD_RESPONSES)
    johnny_data["mead_consumed"] = johnny_data.get("mead_consumed", 0) + 1
    save_data(johnny_data)
    await ctx.send(f"{response}\n🥃 Verres bus : {johnny_data['mead_consumed']}")

@bot.command(name="rant", aliases=["corpo", "systeme"])
async def rant_cmd(ctx):
    """Johnny part dans un rant anti-corpo sauvage"""
    response = random.choice(CULTURAL_CONFUSION)
    await ctx.send(response)

@bot.command(name="legends", aliases=["leaderboard"])
async def legends_cmd(ctx):
    """Liste les meilleurs chooms (leaderboard)"""
    if not DATABASE_AVAILABLE:
        await ctx.send("⚠️ Base de données non disponible !")
        return
    
    from shared.shared_database import get_reputation_leaderboard
    leaderboard = get_reputation_leaderboard(10)
    
    embed = discord.Embed(
        title="🎸 LÉGENDES DE NIGHT CITY",
        description="Les chooms les plus fiables de Johnny !",
        color=discord.Color.red()
    )
    
    for i, entry in enumerate(leaderboard):
        name = entry.get('display_name') or entry.get('username', 'Inconnu')
        points = entry['points']
        level = entry['level']
        
        # Déterminer le rang
        if points < 50:
            rank = "🎖️ Nobody"
        elif points < 150:
            rank = "🏙️ Tireur de rue"
        elif points < 300:
            rank = "⚔️ Solo"
        elif points < 500:
            rank = "👑 Merc de l'Afterlife"
        else:
            rank = "💎 Légende de Night City"
        
        embed.add_field(
            name=f"{i+1}. {name}",
            value=f"{rank} • {points} pts (Niv. {level})",
            inline=False
        )
    
    embed.set_footer(text="Gagnez du respect en aidant Johnny dans ses gigs !")
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
        
    await ctx.send("🎸 C'est fait, choom. J'ai effacé tes traces de mes puces de mémoire. T'as jamais existé pour moi.")

# LOGIQUE CONVERSATIONNELLE

# Noms des AUTRES bots du serveur : si l'échange leur est visiblement adressé, on ne s'incruste
# PAS lors d'une intervention ALÉATOIRE (les mentions/nom direct du bot restent prioritaires).
OTHER_BOT_NAMES = ["sheo", "sheogorath", "sugar", "sugar bot", "alfred", "pennyworth", "m'aiq", "maiq", "malena", "malèna"]

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
    # Ignorer les messages du bot lui-même
    if message.author == bot.user:
        return

    # IGNORER SES PROPRES IMPOSTEURS (Webhooks nommés Johnny ou Silverhand)
    if message.webhook_id and any(n in message.author.display_name.lower() for n in ["johnny", "silverhand"]):
        return
        
    # SILENCE STREAM (Canal ignoré)
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
    
    # Noms alternatifs pour Johnny (détection dans le message)
    JOHNNY_NAMES = ["johnny", "silverhand", "samurai", "silverbot"]
    content_lower = message.content.lower()
    is_name_mentioned = any(name in content_lower for name in JOHNNY_NAMES)
    
    # Les autres bots sont filtrés en amont (silence total entre bots).
    is_bot_talking = False

    # Détection image très tôt (pour priorité)
    has_image_early = classify_request(message.content, message.attachments)["has_image"]
    
    should_respond = False
    keyword_boost = ""
    
    # A. Message direct (mention, reply, DM, ou nom alternatif)
    if is_mentioned or is_reply or is_dm or (is_name_mentioned and not is_bot_talking):
        should_respond = True
        
        # Log si invoqué par nom alternatif
        if is_name_mentioned and not is_mentioned:
            logger.info(f"[NOM ALTERNATIF] Johnny invoqué par nom dans le message de {message.author.name}")
        
        # Database
        if DATABASE_AVAILABLE and not is_dm:
            get_or_create_user(message.author.id, message.author.name, message.author.display_name)
            log_interaction(message.author.id, "Johnny", "mention")
    
    # C. Intervention aléatoire (10%) — sauf si l'échange vise un AUTRE bot
    if not should_respond and not is_bot_talking and not has_image_early and random.random() < 0.10:
        if await _other_bot_in_focus(message):
            logger.info("[ANTI-INCRUSTATION] Échange adressé à un autre bot → Johnny se tait.")
        else:
            should_respond = True
            logger.info(f"[INTERVENTION] Johnny intervient dans {message.channel.name}")
    
    if not should_respond:
        return
    
    # L'image d'un message cité n'est récupérée que si on s'adresse à Johnny
    # (pas via l'intervention aléatoire) ; sinon attachments du message courant.
    atts = (await resolve_media_attachments(message)
            if (is_mentioned or is_reply or is_dm or is_name_mentioned)
            else message.attachments)

    # PREPARATION DU MESSAGE
    user_message = message.content.replace(f'<@{bot.user.id}>', '').strip()
    
    # ══════════════════════════════════════════════════
    # LTM SYSTEM - MEMORY INJECTION
    # ══════════════════════════════════════════════════
    user_id = message.author.id
    user_name = message.author.name
    user_msg_content = user_message
    
    relevant_facts = fact_memory.get_relevant_facts(user_id, user_msg_content, k=3)
    daily_summary = daily_memory.get_context_summary(user_id)
    dr = daily_memory.get_daily_read(user_id)
    daily_read_addition = f"\n[CONSIGNE DU JOUR] {dr}" if dr else ""
    
    fact_context = ""
    if relevant_facts:
        fact_context = f"\n[CE QUE TU SAIS SUR CETTE PERSONNE (MÉMOIRE LONG TERME)]:\n- " + "\n- ".join(relevant_facts)
        
    memory_prompt_addition = (
        f"\n\n[CONTEXTE DE MÉMOIRE]"
        f"{fact_context}"
        f"\n{daily_summary}"
        f"{daily_read_addition}"
        f"\n\n[INSTRUCTION MÉMOIRE CONCOMITANTE]: Si tu apprends un fait durable, important et nouveau sur cette personne dans cette interaction (ex: ses préférences, ses opinions, sa localisation, son métier, etc.), ajoute-le discrètement à la fin de ta réponse entouré de balises XML : <fact>Le fait appris</fact>. Sinon, ne mets rien."
    )

    # Détection mots-clés
    content_lower = user_message.lower()
    keyword_boost = ""
    
    if any(kw in content_lower for kw in SKYRIM_TRIGGERS):
        keyword_boost = "\n\n🎸 [DÉTECTION NIGHT CITY] L'utilisateur parle de Night City / d'un sujet cyber ! Sois fier, cynique et arrogant !"
    
    if any(kw in content_lower for kw in GIFT_TRIGGERS):
        keyword_boost += "\n\n🔫 [DÉTECTION LOOT] Parle de ton flingue / ton chrome avec arrogance !"
    
    if any(kw in content_lower for kw in MEAD_TRIGGERS):
        keyword_boost += "\n\n🥃 [DÉTECTION VERRE] Propose un whisky / une clope, ton détaché et cynique !"
    
    if any(kw in content_lower for kw in MISSION_TRIGGERS):
        keyword_boost += "\n\n🎸 [DÉTECTION GIG] Parle de tes gigs de mercenaire ou de rockstar !"
    
    # HISTORIQUE
    channel_id = message.channel.id
    if channel_id not in conversation_history:
        conversation_history[channel_id] = []
        MAX_CHANNELS = 200
        if len(conversation_history) > MAX_CHANNELS:
            oldest = next(iter(conversation_history))
            conversation_history.pop(oldest, None)
    
    conversation_history[channel_id].append({
        "role": "user",
        "parts": [f"{message.author.name}: {user_message}"]
    })
    
    if len(conversation_history[channel_id]) > MAX_HISTORY:
        conversation_history[channel_id] = conversation_history[channel_id][-MAX_HISTORY:]
    
    # TRANSCRIPT
    transcript = "CONTEXTE DU SALON (Chronologique) :\n"
    messages_list = []
    async for hist_msg in message.channel.history(limit=10):
        messages_list.append(hist_msg)
    
    for hist_msg in reversed(messages_list):
        # Silence total entre bots : on n'inclut PAS les autres bots dans le contexte.
        if hist_msg.author.bot and hist_msg.author != bot.user:
            continue
        transcript += f"{hist_msg.author.name}: {hist_msg.content}\n"
    
    # ANTI-RÉPÉTITION (fusion Discord + Twitch : pont anti-doublon inter-canaux)
    recent_responses = merge_recent_responses(
        response_memory.get_recent(message.guild.id if message.guild else 0),
        _twitch_recent_responses(),
    )
    anti_repeat_prompt = ""
    if recent_responses:
        snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        anti_repeat_prompt = "\n\n[ANTI-RÉPÉTITION] Johnny a déjà dit récemment :\n"
        for i, snippet in enumerate(snippets, 1):
            anti_repeat_prompt += f"{i}. \"{snippet}\"\n"
        anti_repeat_prompt += ("Ne répète PAS ces phrases ! Sois ORIGINAL ! "
            "Ne réutilise AUCUN mot-clé saillant de ces répliques (mots en MAJUSCULES, images, "
            "métaphores, chutes) : si l'une d'elles crie ÉVALUATION, toi tu pars ailleurs.")
    
    # ═══ SMART ROUTER — Classification du message ═══
    _addressed = bool(is_mentioned or is_reply or is_dm or is_name_mentioned)
    routing = classify_request(user_message, atts, addressed=_addressed)

    # ⚠️ Il y avait ici une promotion TEXT → REPARTEE, « pour mettre Grok en priorité ».
    # Elle ne changeait plus aucun modèle : Grok a disparu du code, et get_model_cascade
    # rend la MÊME cascade de persona pour TEXT et pour REPARTEE. Son seul effet restant
    # était d'écrire dans `routing["reason"]` — journalisé par llm_cascade — une phrase
    # qui annonçait un modèle inexistant à chaque réponse de Johnny. Supprimée : le log
    # porte désormais la raison réelle du routeur.

    # Télécharger le média si nécessaire
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
        user_message = "(L'choom montre une image à Johnny sans rien dire.)"
    if has_image:
        user_message += "\n[VISION] Regarde l'image et commente-la comme Johnny le ferait ! Décris ce que tu vois avec ton détachement cynique !"
    if has_audio:
        user_message += "\n[🎤 VOCAL] L'choom a envoyé un message vocal. Écoute-le et réponds avec ton franc-parler !"
    
    # GÉNÉRATION (Smart Router)
    
    def _get_meme_addition():
        chan_id = message.channel.id
        consigne = build_meme_consigne(message.content or "", set(meme_recent[chan_id]))
        if consigne:
            import re as _re
            m = _re.search(r"« (.+?) »", consigne)
            if m:
                meme_recent[chan_id].append(m.group(1))
        return consigne

    response_text = None
    system_prompt = f"SYSTEM: {PERSONALITY_PROMPT}{memory_prompt_addition}{_get_meme_addition()}\n{transcript}{keyword_boost}{anti_repeat_prompt}"
    
    async with message.channel.typing():
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
            openrouter_client=openrouter_client,
            bot_label="Johnny",
            call_timeout=15,   # si un provider traîne (~47s), bascule vers l'échelon suivant (comme Sheo)
        )

        # Cas d'échec multimodal (Image/Audio)
        if not response_text and (has_image or has_audio):
            item_name = "l'image" if has_image else "le message vocal"
            await message.channel.send(f"🚬 J'ai pas le chrome pour capter {item_name} là, choom. On verra ça plus tard.")
            return
        
        # FALLBACK FINAL
        if not response_text:
            if is_bot_talking:
                logger.info("[SILENCE] Echec API vs Bot - Stop boucle.")
                return
            response_text = random.choice(GREETINGS)
    
    # NETTOYAGE
    response_text = response_text.strip()
    
    # LTM - EXTRACTION AND CLEANING OF FACTS
    matches = re.findall(r"<fact>(.*?)</fact>", response_text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        fact_text = match.strip()
        if fact_text:
            fact_memory.add_fact(user_id, fact_text)
            
    response_text = re.sub(r"<fact>.*?</fact>", "", response_text, flags=re.DOTALL | re.IGNORECASE).strip()
    response_text = re.sub(r"<[a-z_-]+>", "", response_text, flags=re.IGNORECASE)
    response_text = re.sub(r"</[a-z_-]+>", "", response_text, flags=re.IGNORECASE).strip()

    # Sauvegarde anti-répétition
    if message.guild:
        response_memory.add(message.guild.id, response_text)
    
    # Sauvegarde historique
    conversation_history[channel_id].append({
        "role": "assistant",
        "parts": [response_text]
    })
    
    # Récompense réputation
    if DATABASE_AVAILABLE and not is_dm and not is_bot_talking:
        add_reputation(message.author.id, points=2, reason="Conversation avec Johnny")
        
    # LTM - Daily interaction logging
    daily_memory.add_interaction(user_id, user_name, user_msg_content, response_text)
    asyncio.create_task(daily_memory.refresh_daily_read(user_id, _daily_llm_call))
    
    # ENVOI
    await message.reply(response_text)

# LANCEMENT

async def on_johnny_shutdown():
    global twitch_chat, twitch_chat_task
    if twitch_chat:
        logger.info("[SHUTDOWN] Arrêt du chat Twitch Johnny...")
        twitch_chat.stop()
    if twitch_chat_task:
        twitch_chat_task.cancel()
        try:
            await twitch_chat_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    if DISCORD_TOKEN:
        setup_graceful_shutdown(bot, on_johnny_shutdown)
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("ERREUR : Aucun token Discord trouvé dans le fichier .env !")
