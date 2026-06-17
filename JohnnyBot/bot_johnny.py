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
import random
import json
import base64
from shared.response_memory import ResponseMemory
import logging
from datetime import datetime
from shared.smart_router import classify_request, RequestType, download_media, get_model_cascade
from shared.media_handler import process_image, process_image_ollama, process_voice_message
from shared.llm_cascade import generate_response

# LOGGING STRUCTURÉ
try:
    from shared.bot_logger import setup_logger
    logger = setup_logger("johnny")
except ImportError:
    logger = logging.getLogger("johnny")
    logging.basicConfig(level=logging.INFO)

# FILE PATHS
DATA_DIR = os.getenv("DATA_DIR", ".")
DATA_FILE = os.path.join(DATA_DIR, "johnny_data.json")

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"missions_completed": 0, "gifts_given": 0, "mead_consumed": 0}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# TOP-LEVEL DUEL TRACKER IMPORT
try:
    from shared.bot_duel_tracker import can_join_duel, register_duel
except ImportError:
    logger.warning("[DUEL] bot_duel_tracker non disponible")
    can_join_duel = lambda *args: True
    register_duel = lambda *args: None

# IMPORT SECURE ENV LOADER
from pathlib import Path
try:
    from shared.secure_env import load_secure_env
    load_secure_env(Path(__file__).parent)
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()

# IMPORT SAFE CLIENT
from shared.safe_client import get_client as get_safe_genai_client

# IMPORT DES SYSTÈMES (locaux pour Discloud)
try:
    from shared.shared_database import (
        get_or_create_user, add_reputation, log_interaction,
        is_maintenance_mode, is_ignored_channel
    )
    from shared.slash_commands import setup_slash_commands, sync_slash_commands
    from shared.server_events import handle_member_join, handle_member_remove, check_and_send_birthdays
    DATABASE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ [JOHNNY] Modules optionnels non disponibles: {e}")
    DATABASE_AVAILABLE = False

# IMPORT PERSONNALITÉ JOHNNY
from johnny_data import (
    PERSONALITY_PROMPT, DIPLOMATIC_TALES, GIFT_RESPONSES,
    SKYRIM_RESPONSES, MEAD_RESPONSES, GREETINGS,
    CULTURAL_CONFUSION, GIFT_TRIGGERS,
    MISSION_TRIGGERS, SKYRIM_TRIGGERS, MEAD_TRIGGERS
)

# CREDENTIALS
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
johnny_data = load_data()
last_duel_time = 0

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
from shared.api_manager import MultiAPIKeyManager
from shared.graceful_shutdown import setup_graceful_shutdown

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

# LTM - LONG TERM MEMORY SYSTEM
import re
from shared.long_term_memory import FactMemory, DailyMemory
from shared.smart_router import RequestType

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

@bot.event
async def on_ready():
    logger.info("=" * 60)
    logger.info("🎸 JOHNNY SILVERHAND — Rockerboy de Night City est prêt !")
    logger.info("=" * 60)
    logger.info(f'🎸 Connecté en tant que: {bot.user.name} ({bot.user.id})')
    logger.info(f'🏰 Serveurs: {len(bot.guilds)}')
    logger.info(f'👥 Utilisateurs visibles: {len(bot.users)}')
    
    # Setup Slash Commands
    if DATABASE_AVAILABLE:
        try:
            setup_slash_commands(bot, "Johnny Silverhand")
            await sync_slash_commands(bot)
        except Exception as e:
            logger.error(f"[SLASH] Erreur: {e}")
    
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
    
    # Status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="Chippin' In | 🎸 Samurai"
        )
    )
    
    # Tâches périodiques
    if DATABASE_AVAILABLE:
        daily_birthday_check.start()

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

# LOGIQUE CONVERSATIONNELLE

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
    
    # Conditions de réponse
    is_mentioned = bot.user in message.mentions
    is_reply = message.reference and message.reference.resolved and message.reference.resolved.author == bot.user
    is_dm = isinstance(message.channel, discord.DMChannel)
    
    # Noms alternatifs pour Johnny (détection dans le message)
    JOHNNY_NAMES = ["johnny", "silverhand", "samurai", "silverbot"]
    content_lower = message.content.lower()
    is_name_mentioned = any(name in content_lower for name in JOHNNY_NAMES)
    
    # Détection autres bots (pour duels)
    is_bot_talking = message.author.bot and message.author != bot.user
    bot_name_lower = message.author.name.lower() if is_bot_talking else ""
    is_sheogorath = "sheo" in bot_name_lower
    is_maiq = "maiq" in bot_name_lower or "m'aiq" in bot_name_lower
    is_alfred = "alfred" in bot_name_lower
    is_zaji = "zaji" in bot_name_lower or "za'ji" in bot_name_lower or "onizuka" in bot_name_lower or "eikichi" in bot_name_lower or "gto" in bot_name_lower
    
    # Détection image très tôt (pour priorité)
    has_image_early = any(
        att.content_type and att.content_type.startswith('image/') 
        for att in message.attachments
    )
    
    should_respond = False
    duel_context = ""
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
    
    # A.bis IMAGE PRIORITY
    elif has_image_early and not is_bot_talking:
        should_respond = True
        logger.info(f"[IMAGE PRIORITY] Johnny va analyser l'image de {message.author.name}")
    
    # B. Mode DUEL avec autres bots
    elif is_bot_talking:
        # Anti-cascade system (importé en haut du fichier)
        
        # Determine bot name from message
        bot_name = None
        if is_sheogorath:
            bot_name = "Sheogorath"
        elif is_zaji:
            bot_name = "Za'ji"
        elif is_alfred:
            bot_name = "Alfred"
        elif is_maiq:
            bot_name = "M'aiq"
        
        # Check if Johnny can join this conversation
        if bot_name and not can_join_duel(message.channel.id, "Johnny", bot_name):
            logger.info(f"[DUEL BLOQUÉ] {bot_name} est déjà en conversation. Johnny attend son tour.")
            return
        
        global last_duel_time
        now = datetime.now().timestamp()
        
        # Cooldown 3 min
        if now - last_duel_time < 180:
            return
        
        # Probabilité selon le bot
        duel_chance = 0.15 if (is_sheogorath or is_maiq or is_alfred or is_zaji) else 0.08
        
        if random.random() < duel_chance:
            should_respond = True
            last_duel_time = now
            
            # Register this duel
            if bot_name:
                register_duel(message.channel.id, "Johnny", bot_name)
            
            # Instructions de duel personnalisées
            if is_sheogorath:
                duel_context = (
                    "\n\n⚔️ RENCONTRE AVEC SHEOGORATH ⚔️\n"
                    "Un taré chromé se prenant pour un dieu de la folie. Johnny doit être méprisant mais intrigué par son chaos :\n"
                    "- 'Un taré chromé qui se prend pour un dieu ? Night City bouffe les dieux au p'tit-déj, choom.'\n"
                    "- Dis-lui qu'il a besoin d'un ripperdoc pour réparer son processeur neural.\n"
                    "- Ton cynique et rebelle."
                )
            elif is_maiq or is_zaji:
                duel_context = (
                    "\n\n🐱 RENCONTRE AVEC KHAJIIT (DES CHATS QUI PARLENT) ⚔️\n"
                    "Des chats qui parlent. Johnny pense à un bug de son implant braindance ou de son chrome d'occasion :\n"
                    "- 'Des chats qui parlent. Soit je flatline, soit on m'a refilé du mauvais chrome.'\n"
                    "- Demande-leur s'ils bossent pour Arasaka ou s'ils ont trop forcé sur les paillettes."
                )
            elif is_alfred:
                duel_context = (
                    "\n\n🎩 RENCONTRE AVEC ALFRED (LARBIN CORPO) ⚔️\n"
                    "Un larbin en costard. Johnny le déteste car il représente le système et la servitude :\n"
                    "- 'Un larbin en costard ? Tu bosses pour les suits. Ça fait de toi le problème.'\n"
                    "- Moque-toi de son dévouement envers un riche bourgeois (Batman/Wayne)."
                )
            
            logger.info(f"[DUEL] Johnny rencontre {message.author.name} !")
    
    # C. Intervention aléatoire (10%)
    if not should_respond and not is_bot_talking and random.random() < 0.10:
        should_respond = True
        logger.info(f"[INTERVENTION] Johnny intervient dans {message.channel.name}")
    
    if not should_respond:
        return
    
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
    
    fact_context = ""
    if relevant_facts:
        fact_context = f"\n[CE QUE TU SAIS SUR CETTE PERSONNE (MÉMOIRE LONG TERME)]:\n- " + "\n- ".join(relevant_facts)
        
    memory_prompt_addition = (
        f"\n\n[CONTEXTE DE MÉMOIRE]"
        f"{fact_context}"
        f"\n{daily_summary}"
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
        # Marquer les autres bots compagnons comme décor : Johnny ne doit pas
        # adopter leur thème (ex: Sheogorath) quand il répond à un humain.
        prefix = "[autre IA] " if (hist_msg.author.bot and hist_msg.author != bot.user) else ""
        transcript += f"{prefix}{hist_msg.author.name}: {hist_msg.content}\n"
    
    # ANTI-RÉPÉTITION
    recent_responses = response_memory.get_recent(message.guild.id if message.guild else 0)
    anti_repeat_prompt = ""
    if recent_responses:
        snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        anti_repeat_prompt = "\n\n[ANTI-RÉPÉTITION] Johnny a déjà dit récemment :\n"
        for i, snippet in enumerate(snippets, 1):
            anti_repeat_prompt += f"{i}. \"{snippet}\"\n"
        anti_repeat_prompt += "Ne répète PAS ces phrases ! Sois ORIGINAL !"
    
    # ═══ SMART ROUTER — Classification du message ═══
    routing = classify_request(user_message, message.attachments)

    # Johnny est un perso de pure répartie → Grok en priorité pour tout texte.
    # On garde le routage image/audio/raisonnement intact ; seul le TEXT simple
    # est promu en REPARTEE (cascade Grok d'abord, voir get_model_cascade).
    if routing["type"] == RequestType.TEXT:
        routing["type"] = RequestType.REPARTEE
        routing["reason"] = "Johnny → Grok prioritaire (répartie)"

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
    
    response_text = None
    system_prompt = f"SYSTEM: {PERSONALITY_PROMPT}{memory_prompt_addition}\n{transcript}{duel_context}{keyword_boost}{anti_repeat_prompt}"
    
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
    
    # ENVOI
    await message.reply(response_text)

# LANCEMENT

if __name__ == "__main__":
    if DISCORD_TOKEN:
        setup_graceful_shutdown(bot)
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("ERREUR : Aucun token Discord trouvé dans le fichier .env !")
