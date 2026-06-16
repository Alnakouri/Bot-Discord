
# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import discord
from discord.ext import commands, tasks
from google import genai
from groq import Groq 
from mistralai import Mistral
from openai import OpenAI
import aiohttp
import random
import json
import os
from shared.response_memory import ResponseMemory
import logging
from datetime import datetime
from shared.smart_router import classify_request, RequestType, download_media
from shared.media_handler import process_image, process_voice_message

# LOGGING STRUCTURÉ
try:
    from shared.bot_logger import setup_logger
    logger = setup_logger("zaji")
except ImportError:
    logger = logging.getLogger("zaji")
    logging.basicConfig(level=logging.INFO)

# TOP-LEVEL DUEL TRACKER IMPORT
try:
    from shared.bot_duel_tracker import can_join_duel, register_duel
except ImportError:
    logger.warning("[DUEL] bot_duel_tracker non disponible")
    can_join_duel = lambda *args: True
    register_duel = lambda *args: None

# FILE PATHS
DATA_DIR = os.getenv("DATA_DIR", ".")
DATA_FILE = os.path.join(DATA_DIR, "zaji_data.json")

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"rum_count": 0, "treasures_found": 0, "tales_told": 0}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# ZA'JI LE CAPITAINE CORSAIRE

# IMPORT SECURE ENV LOADER
from pathlib import Path
try:
    from shared.secure_env import load_secure_env
    load_secure_env(Path(__file__).parent)
except ImportError:
    from dotenv import load_dotenv
    load_dotenv()

# IMPORT LLM CASCADE
from shared.llm_cascade import generate_response

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
    logger.warning(f"⚠️ [ZA'JI] Modules optionnels non disponibles: {e}")
    DATABASE_AVAILABLE = False

try:
    from zaji_data import (
        PERSONALITY_PROMPT, SEA_SHANTIES, TALL_TALES,
        RUM_RESPONSES, TREASURE_RESPONSES, SHIP_RESPONSES,
        GREETINGS, SHANTY_TRIGGERS, TALE_TRIGGERS
    )
except ImportError:
    from ZajiBot.zaji_data import (
        PERSONALITY_PROMPT, SEA_SHANTIES, TALL_TALES,
        RUM_RESPONSES, TREASURE_RESPONSES, SHIP_RESPONSES,
        GREETINGS, SHANTY_TRIGGERS, TALE_TRIGGERS
    )

# CREDENTIALS
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
zaji_data = load_data()
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

# INITIALISATION DU BOT
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

@bot.event
async def on_ready():
    logger.info("=" * 60)
    logger.info("⚓ ZA'JI LE CAPITAINE - Le Rugissement Parfait a pris la mer!")
    logger.info("=" * 60)
    logger.info(f'🏴‍☠️ Connecté en tant que: {bot.user.name} ({bot.user.id})')
    logger.info(f'⛵ Serveurs: {len(bot.guilds)}')
    logger.info(f'👥 Utilisateurs visibles: {len(bot.users)}')
    
    # Setup Slash Commands
    if DATABASE_AVAILABLE:
        try:
            setup_slash_commands(bot, "Za'ji")
            await sync_slash_commands(bot)
        except Exception as e:
            logger.error(f"[SLASH] Erreur: {e}")
    
    # Stats
    logger.info("📊 ARSENAL D'APIs:")
    logger.info(f'   ✅ Gemini : {len([k for k in GEMINI_API_KEYS if k])} clés')
    logger.info(f'   ✅ Groq : {"Oui" if GROQ_API_KEY else "Non"}')
    logger.info(f'   ✅ Mistral : {"Oui" if MISTRAL_API_KEY else "Non"}')
    logger.info(f'   ✅ OpenRouter : {"Oui" if OPENROUTER_API_KEY else "Non"}')
    
    logger.info("💰 STATISTIQUES CAPITAINE:")
    logger.info(f'   🍺 Rhum bu : {zaji_data.get("rum_count", 0)}')
    logger.info(f'   💰 Trésors trouvés : {zaji_data.get("treasures_found", 0)}')
    logger.info(f'   📖 Histoires racontées : {zaji_data.get("tales_told", 0)}')
    
    logger.info("🎯 Za'ji est prêt à naviguer !")
    logger.info("=" * 60)
    
    # Status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="les mers de Discord | ⚓ Le Rugissement Parfait"
        )
    )
    
    # Tâches périodiques
    if DATABASE_AVAILABLE:
        daily_birthday_check.start()

@bot.event
async def on_member_join(member):
    """Accueil pirates"""
    if DATABASE_AVAILABLE:
        await handle_member_join(bot, member, bot_name="Za'ji")
        # Message personnalisé
        if member.guild.system_channel:
            await member.guild.system_channel.send(
                f"🏴‍☠️ **Bienvenue à bord, {member.mention} !**\n"
                f"Za'ji, le plus grand capitaine de Tamriel, te souhaite la bienvenue sur le Rugissement Parfait ! ⚓\n"
                f"Prépare-toi à l'aventure, moussaillon !"
            )

@bot.event
async def on_member_remove(member):
    """Au revoir matelot"""
    if DATABASE_AVAILABLE:
        await handle_member_remove(bot, member, bot_name="Za'ji")

# Tâche quotidienne : anniversaires
@tasks.loop(hours=24)
async def daily_birthday_check():
    if DATABASE_AVAILABLE:
        for guild in bot.guilds:
            await check_and_send_birthdays(bot, bot_name="Za'ji")

@daily_birthday_check.before_loop
async def before_birthday_check():
    await bot.wait_until_ready()

# COMMANDES SPÉCIALES ZA'JI

@bot.command(name="exploit")
async def exploit_cmd(ctx):
    """Za'ji raconte un de ses exploits légendaires"""
    tale = random.choice(TALL_TALES)
    zaji_data["tales_told"] = zaji_data.get("tales_told", 0) + 1
    save_data(zaji_data)
    
    embed = discord.Embed(
        title="⚓ L'EXPLOIT LÉGENDAIRE DE ZA'JI",
        description=tale,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Histoires racontées : {zaji_data['tales_told']}")
    await ctx.send(embed=embed)

@bot.command(name="chanson", aliases=["shanty", "chante"])
async def chanson_cmd(ctx):
    """Za'ji chante une chanson de marin"""
    shanty = random.choice(SEA_SHANTIES)
    await ctx.send(shanty)

@bot.command(name="rhum", aliases=["rum"])
async def rhum_cmd(ctx):
    """Za'ji parle de sa passion pour le rhum"""
    response = random.choice(RUM_RESPONSES)
    zaji_data["rum_count"] = zaji_data.get("rum_count", 0) + 1
    save_data(zaji_data)
    await ctx.send(response)

@bot.command(name="tresor", aliases=["treasure"])
async def tresor_cmd(ctx):
    """Za'ji parle de ses trésors"""
    response = random.choice(TREASURE_RESPONSES)
    zaji_data["treasures_found"] = zaji_data.get("treasures_found", 0) + 1
    save_data(zaji_data)
    await ctx.send(f"{response}\n💰 Trésors découverts par Za'ji : {zaji_data['treasures_found']}")

@bot.command(name="navire", aliases=["ship", "bateau"])
async def navire_cmd(ctx):
    """Za'ji vante son navire"""
    response = random.choice(SHIP_RESPONSES)
    await ctx.send(response)

@bot.command(name="equipage", aliases=["crew"])
async def equipage_cmd(ctx):
    """Liste l'équipage actif"""
    if not DATABASE_AVAILABLE:
        await ctx.send("⚠️ Base de données non disponible !")
        return
    
    from shared.shared_database import get_reputation_leaderboard
    leaderboard = get_reputation_leaderboard(10)
    
    embed = discord.Embed(
        title="🏴‍☠️ ÉQUIPAGE DU RUGISSEMENT PARFAIT",
        description="Les meilleurs matelots de Za'ji !",
        color=discord.Color.blue()
    )
    
    
    for i, entry in enumerate(leaderboard):
        name = entry.get('display_name') or entry.get('username', 'Inconnu')
        points = entry['points']
        level = entry['level']
        
        # Déterminer le rang
        if points < 50:
            rank = "⚓ Cadet"
        elif points < 150:
            rank = "⛵ Matelot"
        elif points < 300:
            rank = "🏴‍☠️ Maître"
        elif points <500:
            rank = "👑 Quartier-Maître"
        else:
            rank = "💎 Capitaine"
        
        embed.add_field(
            name=f"{i+1}. {name}",
            value=f"{rank} • {points} pts (Niv. {level})",
            inline=False
        )
    
    embed.set_footer(text="Gagnez de la réputation en interagissant avec Za'ji !")
    await ctx.send(embed=embed)

# LOGIQUE CONVERSATIONNELLE

@bot.event
async def on_message(message):
    # Ignorer les messages du bot lui-même
    if message.author == bot.user:
        return

    # IGNORER SES PROPRES IMPOSTEURS (Webhooks nommés Za'ji)
    if message.webhook_id and any(n in message.author.display_name.lower() for n in ["zaji", "za'ji"]):
        return
        
    # SILENCE STREAM (Canal ignoré)
    if is_ignored_channel(message.channel):
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
    
    # Noms alternatifs pour Za'ji (détection dans le message)
    ZAJI_NAMES = ["zaji", "za'ji", "za ji", "capitaine", "rugissement", "corsaire"]
    content_lower = message.content.lower()
    is_name_mentioned = any(name in content_lower for name in ZAJI_NAMES)
    
    # Détection autres bots (pour duels)
    is_bot_talking = message.author.bot and message.author != bot.user
    bot_name_lower = message.author.name.lower() if is_bot_talking else ""
    is_sheogorath = "sheo" in bot_name_lower
    is_maiq = "maiq" in bot_name_lower or "m'aiq" in bot_name_lower
    is_alfred = "alfred" in bot_name_lower
    is_johnny = "johnny" in bot_name_lower or "silverbot" in bot_name_lower
    
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
            logger.info(f"[NOM ALTERNATIF] Za'ji invoqué par nom dans le message de {message.author.name}")
        
        # Database
        if DATABASE_AVAILABLE and not is_dm:
            get_or_create_user(message.author.id, message.author.name, message.author.display_name)
            log_interaction(message.author.id, "Za'ji", "mention")
    
    # A.bis IMAGE PRIORITY
    elif has_image_early and not is_bot_talking:
        should_respond = True
        logger.info(f"[IMAGE PRIORITY] Za'ji va analyser l'image de {message.author.name}")
    
    # B. Mode DUEL avec autres bots
    elif is_bot_talking:
        # Anti-cascade system (importé en haut du fichier)
        
        # Determine bot name from message
        bot_name = None
        if is_sheogorath:
            bot_name = "Sheogorath"
        elif is_johnny:
            bot_name = "Johnny"
        elif is_alfred:
            bot_name = "Alfred"
        elif is_maiq:
            bot_name = "M'aiq"
        
        # Check if Za'ji can join this conversation
        if bot_name and not can_join_duel(message.channel.id, "Za'ji", bot_name):
            logger.info(f"[DUEL BLOQUÉ] {bot_name} est déjà en conversation. Za'ji reste en retrait.")
            return
        
        global last_duel_time
        now = datetime.now().timestamp()
        
        # Cooldown 3 min
        if now - last_duel_time < 180:
            return
        
        # Probabilité selon le bot
        duel_chance = 0.25 if (is_sheogorath or is_maiq or is_alfred) else 0.10
        
        if random.random() < duel_chance:
            should_respond = True
            last_duel_time = now
            
            # Register this duel
            if bot_name:
                register_duel(message.channel.id, "Za'ji", bot_name)
            
            # Instructions de duel personnalisées
            if is_sheogorath:
                duel_context = (
                    "\n\n⚔️ DUEL CONTRE SHEOGORATH ⚔️\n"
                    "Un Prince Daedra fou te défie ! Reste CONFIANT et moque sa folie :\n"
                    "- 'Za'ji a navigué avec des Daedra ! Ils avaient tous le mal de mer !'\n"
                    "- Compare sa folie à une tempête : impressionnante mais Za'ji l'a déjà vaincue\n"
                    "- Reste VANTARD et ne te laisse PAS impressionner"
                )
            elif is_maiq:
                duel_context = (
                    "\n\n🤝 RENCONTRE AVEC M'AIQ (FRATERNITÉ KHAJIIT) !\n"
                    "Un autre Khajiit ! Sois AMICAL mais COMPÉTITIF :\n"
                    "- 'M'aiq devrait rejoindre l'équipage de Za'ji ! Les meilleurs marins sont Khajiit !'\n"
                    "- Montre du respect mais reste le MEILLEUR capitaine\n"
                    "- Propose-lui du rhum ou une aventure"
                )
            elif is_alfred:
                duel_context = (
                    "\n\n🎩 RENCONTRE AVEC ALFRED (LE MAJORDOME) !\n"
                    "Un majordome coincé ! Taquine-le gentiment :\n"
                    "- 'Un majordome ? Za'ji préfère un quartier-maître ! Plus utile en mer !'\n"
                    "- Essaie de le détendre et de le faire rire\n"
                    "- Invite-le à boire du rhum"
                )
            
            logger.info(f"[DUEL] Za'ji affronte {message.author.name} !")
    
    # ══════════════════════════════════════════════════
    # TRAITEMENT MULTIMODAL (Vision + Audio Vocal)
    # ══════════════════════════════════════════════════
    if message.attachments:
        routing = classify_request(message.content, message.attachments)
        
        # --- IMAGE ---
        if routing["has_image"] and routing["image_attachment"]:
            api_key = key_manager.get_key("gemini")
            if api_key:
                async with message.channel.typing():
                    # Préparation du prompt consolidé
                    full_personality = f"{PERSONALITY_PROMPT}\n{duel_context}{keyword_boost}"
                    response = await process_image(
                        attachment=routing["image_attachment"],
                        api_key=api_key,
                        personality_prompt=full_personality,
                        user_message=message.content or ""
                    )
                if response:
                    await message.reply(response)
                    if message.channel.id not in conversation_history:
                        conversation_history[message.channel.id] = []
                    conversation_history[message.channel.id].append({"role": "model", "parts": [response]})
                    return
            else:
                await message.reply("🏝️ Trop de soleil sur le pont, je ne vois rien, moussaillon ! C'est éblouissant ! 🏴‍☠️")
                return
        
        # --- MESSAGE VOCAL ---
        if routing["has_audio"] and routing["audio_attachment"]:
            api_key = key_manager.get_key("gemini")
            if api_key:
                async with message.channel.typing():
                    full_personality = f"{PERSONALITY_PROMPT}\n{duel_context}{keyword_boost}"
                    response = await process_voice_message(
                        attachment=routing["audio_attachment"],
                        api_key=api_key,
                        personality_prompt=full_personality
                    )
                if response:
                    await message.reply(response)
                    if message.channel.id not in conversation_history:
                        conversation_history[message.channel.id] = []
                    conversation_history[message.channel.id].append({"role": "model", "parts": [response]})
                    return
            else:
                await message.reply("👂 Trop de vagues et de vent dans les voiles ! Je n'entends rien à ce que tu racontes ! 🏴‍☠️")
                return
    # ══════════════════════════════════════════════════
    
    # C. Intervention aléatoire (10%)
    elif not is_bot_talking and random.random() < 0.10:
        should_respond = True
        logger.info(f"[INTERVENTION] Za'ji intervient dans {message.channel.name}")
    
    if not should_respond:
        return
    
    # PREPARATION DU MESSAGE
    user_message = message.content.replace(f'<@{bot.user.id}>', '').strip()
    
    # Détection mots-clés (rhum, trésor, etc.)
    content_lower = user_message.lower()
    keyword_boost = ""
    
    if any(kw in content_lower for kw in ["rhum", "rum"]):
        keyword_boost = "\n\n🍺 [DÉTECTION RHUM] L'utilisateur parle de RHUM ! Sois TRÈS enthousiaste !"
        zaji_data["rum_count"] = zaji_data.get("rum_count", 0) + 1
        save_data(zaji_data)
    
    if any(kw in content_lower for kw in ["trésor", "treasure", "or", "gold"]):
        keyword_boost += "\n\n💰 [DÉTECTION TRÉSOR] Parle de tes découvertes légendaires !"
    
    if any(kw in content_lower for kw in ["navire", "bateau", "ship"]):
        keyword_boost += "\n\n⛵ [DÉTECTION NAVIRE] Vante Le Rugissement Parfait !"
    
    if any(kw in SHANTY_TRIGGERS for kw in content_lower.split()):
        keyword_boost += "\n\n🎵 [DEMANDE DE CHANSON] Chante une chanson de marin !"
    
    if any(kw in TALE_TRIGGERS for kw in content_lower.split()):
        keyword_boost += "\n\n📖 [DEMANDE D'HISTOIRE] Raconte un exploit !"
    
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
    messages_list = []
    async for hist_msg in message.channel.history(limit=10):
        messages_list.append(hist_msg)
    
    for hist_msg in reversed(messages_list):
        prefix = "[autre IA] " if (hist_msg.author.bot and hist_msg.author != bot.user) else ""
        transcript += f"{prefix}{hist_msg.author.name}: {hist_msg.content}\n"
    transcript += "\n[RÈGLE] Les lignes préfixées '[autre IA]' sont d'autres bots compagnons (décor). Reste toi-même et n'adopte JAMAIS leurs thèmes/personnages quand tu réponds à un humain.\n"
    
    # ANTI-RÉPÉTITION
    recent_responses = response_memory.get_recent(message.guild.id if message.guild else 0)
    anti_repeat_prompt = ""
    if recent_responses:
        snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        anti_repeat_prompt = "\n\n[ANTI-RÉPÉTITION] Za'ji a déjà dit récemment :\n"
        for i, snippet in enumerate(snippets, 1):
            anti_repeat_prompt += f"{i}. \"{snippet}\"\n"
        anti_repeat_prompt += "Ne répète PAS ces phrases ! Sois ORIGINAL !"
    
    # ═══ SMART ROUTER — Classification du message ═══
    routing = classify_request(user_message, message.attachments)
    
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
        user_message = "(Le matelot montre une image à Za'ji sans rien dire.)"
    if has_image:
        user_message += "\n[VISION] Regarde l'image et commente-la comme Za'ji le ferait ! Décris ce que tu vois avec enthousiasme !"
    if has_audio:
        user_message += "\n[🎤 VOCAL] Le matelot a envoyé un message vocal. Écoute-le et réponds en conséquence avec ton accent Khajiit."
    

    # GÉNÉRATION (Smart Router)
    
    response_text = None
    system_prompt = f"SYSTEM: {PERSONALITY_PROMPT}\n{transcript}{duel_context}{keyword_boost}{anti_repeat_prompt}"
    
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
            bot_label="Za'ji",
            gemini_max_tokens=500,
        )

        # Cas d'échec multimodal (Image/Audio)
        if not response_text and (has_image or has_audio):
            media_type = "image" if has_image else "message vocal"
            item_name = "l'image" if has_image else "le message vocal"
            await message.channel.send(f"🏝️ Les courants sont trop forts et ma vue est trouble. Le capitaine ne comprend pas {item_name} aujourd'hui ! ⚓")
            return
        
        # FALLBACK FINAL
        if not response_text:
            if is_bot_talking:
                logger.info("[SILENCE] Echec API vs Bot - Stop boucle.")
                return
            response_text = random.choice(GREETINGS)
    
    # NETTOYAGE
    response_text = response_text.strip()
    
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
        add_reputation(message.author.id, points=2, reason="Conversation avec Za'ji")
    
    # ENVOI
    await message.reply(response_text)

# LANCEMENT

if __name__ == "__main__":
    if DISCORD_TOKEN:
        setup_graceful_shutdown(bot)
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ ERREUR : Aucun token Discord trouvé dans le fichier .env !")
