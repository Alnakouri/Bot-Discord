
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

# FILE PATHS
DATA_DIR = os.getenv("DATA_DIR", ".")
DATA_FILE = os.path.join(DATA_DIR, "zaji_data.json")

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            # Map old keys to new keys if they exist
            if "rum_count" in data:
                data["money_bragged"] = data.pop("rum_count")
            if "treasures_found" in data:
                data["jackpots"] = data.pop("treasures_found")
            return data
    return {"money_bragged": 0, "jackpots": 0, "tales_told": 0}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# EIKICHI ONIZUKA (GTO)

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
    logger.warning(f"⚠️ [ONIZUKA] Modules optionnels non disponibles: {e}")
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
    logger.info("🏍️ EIKICHI ONIZUKA - Great Teacher Onizuka est là !")
    logger.info("=" * 60)
    logger.info(f'🏍️ Connecté en tant que: {bot.user.name} ({bot.user.id})')
    logger.info(f'🏫 Serveurs: {len(bot.guilds)}')
    logger.info(f'👥 Utilisateurs visibles: {len(bot.users)}')
    
    # Setup Slash Commands
    if DATABASE_AVAILABLE:
        try:
            setup_slash_commands(bot, "Onizuka")
            await sync_slash_commands(bot)
        except Exception as e:
            logger.error(f"[SLASH] Erreur: {e}")
    
    # Stats
    logger.info("📊 ARSENAL D'APIs:")
    logger.info(f'   ✅ Gemini : {len([k for k in GEMINI_API_KEYS if k])} clés')
    logger.info(f'   ✅ Groq : {"Oui" if GROQ_API_KEY else "Non"}')
    logger.info(f'   ✅ Mistral : {"Oui" if MISTRAL_API_KEY else "Non"}')
    logger.info(f'   ✅ OpenRouter : {"Oui" if OPENROUTER_API_KEY else "Non"}')
    
    logger.info("📊 STATISTIQUES ONIZUKA:")
    logger.info(f'   💴 Fric vanté : {zaji_data.get("money_bragged", 0)}')
    logger.info(f'   🎰 Jackpots gagnés : {zaji_data.get("jackpots", 0)}')
    logger.info(f'   📖 Exploits racontés : {zaji_data.get("tales_told", 0)}')
    
    logger.info("🎯 Onizuka est prêt à enseigner !")
    logger.info("=" * 60)
    
    # Status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="les élèves | 🏍️ Kawasaki Z-II"
        )
    )
    
    # Tâches périodiques
    if DATABASE_AVAILABLE:
        daily_birthday_check.start()

@bot.event
async def on_member_join(member):
    """Accueil de classe"""
    if DATABASE_AVAILABLE:
        await handle_member_join(bot, member, bot_name="Onizuka")
        # Message personnalisé
        if member.guild.system_channel:
            await member.guild.system_channel.send(
                f"🏍️ **Bienvenue dans la classe, {member.mention} !**\n"
                f"Eikichi Onizuka, 22 ans, célibataire et prof de génie, te souhaite la bienvenue ! 🔥\n"
                f"Prépare-toi à faire des étincelles !"
            )

@bot.event
async def on_member_remove(member):
    """Au revoir élève"""
    if DATABASE_AVAILABLE:
        await handle_member_remove(bot, member, bot_name="Onizuka")

# Tâche quotidienne : anniversaires
@tasks.loop(hours=24)
async def daily_birthday_check():
    if DATABASE_AVAILABLE:
        for guild in bot.guilds:
            await check_and_send_birthdays(bot, bot_name="Onizuka")

@daily_birthday_check.before_loop
async def before_birthday_check():
    await bot.wait_until_ready()

# COMMANDES SPÉCIALES ONIZUKA

@bot.command(name="exploit", aliases=["histoire", "legende"])
async def exploit_cmd(ctx):
    """Onizuka raconte un de ses exploits de légende"""
    tale = random.choice(TALL_TALES)
    zaji_data["tales_told"] = zaji_data.get("tales_told", 0) + 1
    save_data(zaji_data)
    
    embed = discord.Embed(
        title="🏍️ L'EXPLOIT DE LEGENDE D'ONIZUKA",
        description=tale,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Exploits racontés : {zaji_data['tales_told']}")
    await ctx.send(embed=embed)

@bot.command(name="chanson", aliases=["frime", "chante", "shanty"])
async def chanson_cmd(ctx):
    """Onizuka sort une punchline / vantardise"""
    shanty = random.choice(SEA_SHANTIES)
    await ctx.send(shanty)

@bot.command(name="fric", aliases=["argent", "rhum", "rum"])
async def fric_cmd(ctx):
    """Onizuka parle de sa passion pour le fric, les filles et le ramen"""
    response = random.choice(RUM_RESPONSES)
    zaji_data["money_bragged"] = zaji_data.get("money_bragged", 0) + 1
    save_data(zaji_data)
    await ctx.send(response)

@bot.command(name="jackpot", aliases=["tresor", "trésor", "treasure"])
async def jackpot_cmd(ctx):
    """Onizuka parle de ses jackpots"""
    response = random.choice(TREASURE_RESPONSES)
    zaji_data["jackpots"] = zaji_data.get("jackpots", 0) + 1
    save_data(zaji_data)
    await ctx.send(f"{response}\n💰 Jackpots décrochés par Onizuka : {zaji_data['jackpots']}")

@bot.command(name="moto", aliases=["navire", "ship", "bateau"])
async def moto_cmd(ctx):
    """Onizuka vante sa moto (ou la Cresta de Uchiyamada)"""
    response = random.choice(SHIP_RESPONSES)
    await ctx.send(response)

@bot.command(name="equipage", aliases=["crew", "classe"])
async def equipage_cmd(ctx):
    """Liste la bande d'élèves d'Onizuka"""
    if not DATABASE_AVAILABLE:
        await ctx.send("⚠️ Base de données non disponible !")
        return
    
    from shared.shared_database import get_reputation_leaderboard
    leaderboard = get_reputation_leaderboard(10)
    
    embed = discord.Embed(
        title="🏍️ LA BANDE D'ONIZUKA (CLASSE SEIRIN)",
        description="Les élèves et potes les plus fidèles d'Onizuka !",
        color=discord.Color.red()
    )
    
    for i, entry in enumerate(leaderboard):
        name = entry.get('display_name') or entry.get('username', 'Inconnu')
        points = entry['points']
        level = entry['level']
        
        # Déterminer le rang
        if points < 50:
            rank = "🎒 Cancre"
        elif points < 150:
            rank = "📚 Élève Moyen"
        elif points < 300:
            rank = "🏍️ Motard d'Onibaku"
        elif points < 500:
            rank = "🔥 Délégué de Classe"
        else:
            rank = "👑 Great Student Onizuka"
        
        embed.add_field(
            name=f"{i+1}. {name}",
            value=f"{rank} • {points} pts (Niv. {level})",
            inline=False
        )
    
    embed.set_footer(text="Gagnez du respect en parlant avec Onizuka !")
    await ctx.send(embed=embed)

# LOGIQUE CONVERSATIONNELLE

@bot.event
async def on_message(message):
    # Ignorer les messages du bot lui-même
    if message.author == bot.user:
        return

    # IGNORER SES PROPRES IMPOSTEURS (Webhooks nommés Onizuka / Za'ji)
    if message.webhook_id and any(n in message.author.display_name.lower() for n in ["zaji", "za'ji", "onizuka", "eikichi", "gto"]):
        return
        
    # SILENCE STREAM (Canal ignoré)
    if is_ignored_channel(message.channel):
        return
    
    # Vérification mode maintenance AVANT process_commands
    if DATABASE_AVAILABLE and is_maintenance_mode():
        return
    
    # Traiter les commandes
    await bot.process_commands(message)

    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    if message.author.bot:
        return

    # Conditions de réponse
    is_mentioned = bot.user in message.mentions
    is_reply = message.reference and message.reference.resolved and message.reference.resolved.author == bot.user
    is_dm = isinstance(message.channel, discord.DMChannel)
    
    # Noms alternatifs pour Onizuka (détection dans le message)
    ONIZUKA_NAMES = ["onizuka", "eikichi", "gto", "onibaku"]
    content_lower = message.content.lower()
    is_name_mentioned = any(name in content_lower for name in ONIZUKA_NAMES)
    
    # Les autres bots sont filtrés en amont (silence total entre bots).
    is_bot_talking = False

    # Détection image très tôt (pour priorité)
    has_image_early = any(
        att.content_type and att.content_type.startswith('image/') 
        for att in message.attachments
    )
    
    should_respond = False
    keyword_boost = ""
    
    # A. Message direct (mention, reply, DM, ou nom alternatif)
    if is_mentioned or is_reply or is_dm or (is_name_mentioned and not is_bot_talking):
        should_respond = True
        
        # Log si invoqué par nom alternatif
        if is_name_mentioned and not is_mentioned:
            logger.info(f"[NOM ALTERNATIF] Onizuka invoqué par nom dans le message de {message.author.name}")
        
        # Database
        if DATABASE_AVAILABLE and not is_dm:
            get_or_create_user(message.author.id, message.author.name, message.author.display_name)
            log_interaction(message.author.id, "Onizuka", "mention")
    
    # A.bis IMAGE PRIORITY
    elif has_image_early and not is_bot_talking:
        should_respond = True
        logger.info(f"[IMAGE PRIORITY] Onizuka va analyser l'image de {message.author.name}")
    
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
                    full_personality = f"{PERSONALITY_PROMPT}\n{keyword_boost}"
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
                await message.reply("🏍️ Oï ! Le soleil tape trop fort sur ma visière, je vois que dalle à ton image ! 😎")
                return
        
        # --- MESSAGE VOCAL ---
        if routing["has_audio"] and routing["audio_attachment"]:
            api_key = key_manager.get_key("gemini")
            if api_key:
                async with message.channel.typing():
                    full_personality = f"{PERSONALITY_PROMPT}\n{keyword_boost}"
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
                await message.reply("👂 Trop de bruit de moteur ! Parle plus fort dans le micro, je capte rien ! 🏍️")
                return
    # ══════════════════════════════════════════════════
    
    # C. Intervention aléatoire (10%)
    elif not is_bot_talking and random.random() < 0.10:
        should_respond = True
        logger.info(f"[INTERVENTION] Onizuka intervient dans {message.channel.name}")
    
    if not should_respond:
        return
    
    # PREPARATION DU MESSAGE
    user_message = message.content.replace(f'<@{bot.user.id}>', '').strip()
    
    # Détection mots-clés (fric, jackpot, moto, etc.)
    content_lower = user_message.lower()
    keyword_boost = ""
    
    if any(kw in content_lower for kw in ["fric", "argent", "thune", "yen", "pachinko"]):
        keyword_boost = "\n\n💴 [DÉTECTION FRIC/MONEY] L'utilisateur parle de thunes ou de pachinko ! Sois TRÈS motivé par l'argent !"
        zaji_data["money_bragged"] = zaji_data.get("money_bragged", 0) + 1
        save_data(zaji_data)
    
    if any(kw in content_lower for kw in ["jackpot", "trésor", "tresor", "gloire"]):
        keyword_boost += "\n\n🎰 [DÉTECTION JACKPOT] Parle de décrocher le gros lot, de la gloire, ou d'exploits !"
    
    if any(kw in content_lower for kw in ["moto", "bécane", "kawasaki", "cresta", "voiture"]):
        keyword_boost += "\n\n🏍️ [DÉTECTION VEHICULE] Vante ta moto de loubard ou plains-toi de la Cresta d'Uchiyamada !"
    
    if any(kw in SHANTY_TRIGGERS for kw in content_lower.split()):
        keyword_boost += "\n\n🎵 [DEMANDE DE CHANSON] Sors une punchline de légende ou une vantardise !"
    
    if any(kw in TALE_TRIGGERS for kw in content_lower.split()):
        keyword_boost += "\n\n📖 [DEMANDE D'HISTOIRE] Raconte un de tes exploits de prof ou de motard !"
    
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
        # Silence total entre bots : on n'inclut PAS les autres bots dans le contexte.
        if hist_msg.author.bot and hist_msg.author != bot.user:
            continue
        transcript += f"{hist_msg.author.name}: {hist_msg.content}\n"
    
    # ANTI-RÉPÉTITION
    recent_responses = response_memory.get_recent(message.guild.id if message.guild else 0)
    anti_repeat_prompt = ""
    if recent_responses:
        snippets = [r[:60] + "..." if len(r) > 60 else r for r in recent_responses[-5:]]
        anti_repeat_prompt = "\n\n[ANTI-RÉPÉTITION] Onizuka a déjà dit récemment :\n"
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
        user_message = "(Un élève montre une image à Onizuka sans rien dire.)"
    if has_image:
        user_message += "\n[VISION] Regarde l'image et commente-la en tant qu'Onizuka ! Dis ce que t'en penses de manière cash !"
    if has_audio:
        user_message += "\n[🎤 VOCAL] L'élève a envoyé un message vocal. Écoute-le et réponds en tant qu'Onizuka avec ton ton de loubard."
    

    # GÉNÉRATION (Smart Router)
    
    response_text = None
    system_prompt = f"SYSTEM: {PERSONALITY_PROMPT}\n{transcript}{keyword_boost}{anti_repeat_prompt}"
    
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
            bot_label="Onizuka",
            gemini_max_tokens=500,
        )

        # Cas d'échec multimodal (Image/Audio)
        if not response_text and (has_image or has_audio):
            media_type = "image" if has_image else "message vocal"
            item_name = "l'image" if has_image else "le message vocal"
            await message.channel.send(f"🏍️ Oï ! Les circuits surchauffent, Onizuka ne capte pas {item_name} aujourd'hui ! 😎")
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
        add_reputation(message.author.id, points=2, reason="Conversation avec Onizuka")
    
    # ENVOI
    await message.reply(response_text)

# LANCEMENT

if __name__ == "__main__":
    if DISCORD_TOKEN:
        setup_graceful_shutdown(bot)
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ ERREUR : Aucun token Discord trouvé dans le fichier .env !")
