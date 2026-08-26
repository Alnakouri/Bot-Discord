# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Bot Discord : Malena (La Gitana Marseillaise)
Version : 1.0.0
"""

import os
import discord
import asyncio
import random
from openai import OpenAI
from datetime import datetime
import base64
from core.smart_router import classify_request, RequestType, download_media, get_model_cascade, resolve_media_attachments
from core.media_handler import process_image_ollama
from google.genai import types
from core.safe_client import get_client as get_safe_genai_client
from groq import Groq
from mistralai import Mistral
from pathlib import Path

try:
    from shared.memes_fr import build_meme_consigne
    MEMES_AVAILABLE = True
except ImportError:
    MEMES_AVAILABLE = False
    def build_meme_consigne(*a, **k): return ""

import collections
meme_recent = collections.defaultdict(lambda: collections.deque(maxlen=8))  # {channel_id: deque[ref]}
from core.secure_env import load_secure_env
load_secure_env(Path(__file__).parent)

# Import modules partagés
from core.bot_logger import setup_logger
# shared/ = etat commun entre bots (reputation, anniversaires). Optionnel : le bot doit
# demarrer et repondre sans, chaque appel est garde par DATABASE_AVAILABLE.
try:
    from shared.shared_database import get_or_create_user, log_interaction, is_ignored_channel
    from shared.server_events import check_and_send_birthdays, handle_member_join, handle_member_remove
    DATABASE_AVAILABLE = True
    _DB_IMPORT_ERROR = None
except ImportError as _e:
    DATABASE_AVAILABLE = False
    _DB_IMPORT_ERROR = _e
try:
    from shared.games import setup_games
    from games_persona import PERSONA
    GAMES_AVAILABLE = True
except ImportError:
    GAMES_AVAILABLE = False

# Import données spécifiques
import malena_data as data
from malena_memory import MalenaMemory
from core.graceful_shutdown import setup_graceful_shutdown

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



# Configuration du Logger
logger = setup_logger("malena", "logs")
if not DATABASE_AVAILABLE:
    logger.warning(
        f"⚠️ [CORE] shared/ absent ({_DB_IMPORT_ERROR}) : reputation, salons ignores, "
        "anniversaires et messages d'accueil/depart desactives."
    )

# MISSED MENTIONS TRACKING
checked_messages_malena = set()
MAX_CHECKED_CACHE = 200

# MALENA MEMORY
malena_brain = MalenaMemory()

# CREDENTIALS
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY_1")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not DISCORD_TOKEN:
    logger.critical("❌ DISCORD_TOKEN introuvable dans .env !")
    exit(1)

# INITIALISATION CLIENTS IA
gemini_client = None
if GEMINI_API_KEY:
    try: gemini_client = get_safe_genai_client(api_key=GEMINI_API_KEY)
    except Exception as e: logger.error(f"❌ Erreur Init Gemini : {e}")

groq_client = None
if GROQ_API_KEY:
    try: groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e: logger.error(f"❌ Erreur Init Groq : {e}")

mistral_client = None
if MISTRAL_API_KEY:
    try: mistral_client = Mistral(api_key=MISTRAL_API_KEY)
    except Exception as e: logger.error(f"❌ Erreur Init Mistral : {e}")

openrouter_client = None
if OPENROUTER_API_KEY:
    try: openrouter_client = OpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
    except Exception as e: logger.warning(f"⚠️ OpenRouter indisponible : {e}")

# KEY MANAGER (Standardisé)
from core.api_manager import MultiAPIKeyManager
key_manager = MultiAPIKeyManager()
key_manager.register_api("gemini", [GEMINI_API_KEY] if GEMINI_API_KEY else [])
key_manager.register_api("groq", [GROQ_API_KEY] if GROQ_API_KEY else [])
key_manager.register_api("mistral", [MISTRAL_API_KEY] if MISTRAL_API_KEY else [])
key_manager.register_api("openrouter", [OPENROUTER_API_KEY] if OPENROUTER_API_KEY else [])

async def _daily_llm_call(system_prompt, user_message):
    from core.llm_cascade import generate_response
    return await generate_response(
        routing={"type": RequestType.TEXT, "reason": "daily_read"},
        system_prompt=system_prompt, transcript="", user_message=user_message,
        conversation_history=[], media_data=None, mime_type="",
        key_manager=key_manager, mistral_client=mistral_client,
        groq_client=groq_client, openrouter_client=openrouter_client,
        bot_label="Malena", temperature=0.5, max_tokens=60)

# CONSTRUCTION DYNAMIQUE DU HINT D'EXPRESSIONS
def build_expression_hint(mood):
    """Retourne les expressions adaptées à l'humeur détectée."""
    mood_data = data.MOODS.get(mood, data.MOODS["NEUTRE"])
    categories = mood_data.get("expressions", [])
    
    relevant = []
    for cat in categories:
        if cat in data.EXPRESSIONS:
            relevant.extend(data.EXPRESSIONS[cat])
    
    if not relevant:
        return ""
    
    
    # Sélectionner 2-4 expressions aléatoires parmi celles pertinentes
    sample = random.sample(relevant, min(4, len(relevant)))
    expr_list = ", ".join(f"'{e}'" for e in sample)
    
    return (
        f"\n\nEXPRESSIONS DISPONIBLES POUR CETTE RÉPONSE (choisis-en 1 ou 2 MAX, "
        f"seulement si ça colle au contexte) : {expr_list}"
    )

def _est_vide(txt):
    """Un modèle peut répondre 200 OK avec un contenu VIDE, sans lever d'exception.

    Vu en prod le 2026-08-26 : Groq rend un contenu vide, Malena tente un envoi Discord
    vide -> 400 « Cannot send an empty message », donc muette. Le vide n'est pas une
    réponse : on descend la cascade au lieu de la casser.
    """
    return not (txt and txt.strip())


async def generate_response_hybrid(prompt, mood="NEUTRE", routing=None, media_data=None, mime_type=None, meme_consigne=""):
    """Essaie selon le Smart Router : Gemini (Image/Audio) -> Groq (Texte) -> Mistral (Fallback)."""
    
    # SYSTEM PROMPT COMMUN + HUMEUR + EXPRESSIONS CIBLÉES
    mood_instruction = data.MOODS[mood]["prompt"]
    expression_hint = build_expression_hint(mood)
    sys_prompt = data.PERSONALITY_PROMPT + f"\n\n{mood_instruction}{expression_hint}\n\nET SURTOUT : FAIS COURT (Max 3-4 phrases).{meme_consigne}"

    cascade = get_model_cascade(routing["type"] if routing else RequestType.TEXT)
    
    for client_type, model_name in cascade:
        try:
            # 1. GEMINI
            if client_type == "gemini" and gemini_client:
                logger.info(f"🧠 Tentative Gemini ({model_name})...")
                # Construire le payload Gemini
                last_turn_parts = [types.Part(text=f"SYSTEM: {sys_prompt}\n\nUSER: {prompt}")]
                if media_data:
                    last_turn_parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_data)))
                gemini_messages = [types.Content(role="user", parts=last_turn_parts)]

                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        gemini_client.models.generate_content,
                        model=model_name,
                        contents=gemini_messages,
                        config=types.GenerateContentConfig(
                            temperature=1.1,
                            max_output_tokens=300,
                            thinking_config=types.ThinkingConfig(thinking_level="minimal")
                        )
                    ),
                    timeout=15
                )
                if _est_vide(response.text):
                    logger.warning(f"⚠️ [GEMINI {model_name}] réponse vide → échelon suivant")
                    continue
                return response.text
 
            # 1.bis OLLAMA (Moondream)
            elif client_type == "ollama":
                if routing and routing["type"] == RequestType.IMAGE and routing["image_attachment"]:
                    response_text = await process_image_ollama(
                        attachment=routing["image_attachment"],
                        personality_prompt=sys_prompt,
                        user_message=prompt
                    )
                    if response_text:
                        logger.info(f"✅ [OLLAMA {model_name}] Malena a utilisé Moondream local !")
                        return response_text
                    continue
                else:
                    continue

            # 2. MISTRAL
            elif client_type == "mistral" and mistral_client:
                logger.info(f"🥖 Tentative Mistral ({model_name})...")
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        mistral_client.chat.complete,
                        model=model_name,
                        messages=[{"role": "system", "content": sys_prompt},
                                  {"role": "user", "content": prompt}],
                        temperature=0.9,
                        max_tokens=300
                    ),
                    timeout=15
                )
                texte = response.choices[0].message.content
                if _est_vide(texte):
                    logger.warning(f"⚠️ [MISTRAL {model_name}] réponse vide → échelon suivant")
                    continue
                return texte

            # 4. GROQ
            elif client_type == "groq" and groq_client:
                logger.info(f"🚀 Tentative Groq ({model_name})...")
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        groq_client.chat.completions.create,
                        messages=[{"role": "system", "content": sys_prompt},
                                  {"role": "user", "content": prompt}],
                        model=model_name,
                        temperature=1.1,
                        max_tokens=300
                    ),
                    timeout=15
                )
                texte = chat.choices[0].message.content
                if _est_vide(texte):
                    logger.warning(f"⚠️ [{client_type.upper()} {model_name}] réponse vide → échelon suivant")
                    continue
                return texte

            # 5. OPENROUTER
            elif client_type == "openrouter" and openrouter_client:
                logger.info(f"🌌 Tentative OpenRouter ({model_name})...")
                
                user_content = prompt
                # Support Multimodal Secours
                if media_data:
                    b64_image = base64.b64encode(media_data).decode('utf-8')
                    user_content = [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}
                        }
                    ]
                
                chat = await asyncio.wait_for(
                    asyncio.to_thread(
                        openrouter_client.chat.completions.create,
                        model=model_name,
                        messages=[{"role": "system", "content": sys_prompt},
                                  {"role": "user", "content": user_content}],
                        temperature=1.1,
                        max_tokens=300,
                        extra_headers={"HTTP-Referer": "https://discord-bot.local", "X-Title": "Malena Bot"}
                    ),
                    timeout=15
                )
                texte = chat.choices[0].message.content
                if _est_vide(texte):
                    logger.warning(f"⚠️ [{client_type.upper()} {model_name}] réponse vide → échelon suivant")
                    continue
                return texte

        except Exception as e:
            logger.error(f"❌ Erreur {client_type.upper()} ({model_name}) : {type(e).__name__}: {e}")
            continue

    return "Ay caramba ! J'ai mal au crâne, plus personne ne marche là-dedans ! (Erreur API Totale)"

# INITIALISATION DU BOT
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Nécessaire pour les événements de bienvenue/départ
from discord.ext import commands, tasks
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

ENABLE_DAILY_BIO = os.getenv("ENABLE_DAILY_BIO", "1") != "0"
daily_bio = DiscordDailyBio(
    bot=bot, bot_id="malena", bot_label="Malena",
    personality_prompt=data.PERSONALITY_PROMPT,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, openrouter_client=openrouter_client,
    logger=logger, enabled=ENABLE_DAILY_BIO,
) if DiscordDailyBio else None

# Statut Discord auto-piloté par la personnalité (jumeau de la bio).
# La liste ci-dessous n'est plus qu'un FALLBACK si le LLM est indisponible.
_STATUS_FALLBACK = [
    ("listening", "le flamenco gronder 💃"),
    ("listening", "les esprits murmurer"),
    ("listening", "ton destin chuchoter"),
    ("listening", "une guitare gitane 🎸"),
    ("listening", "le vent de l'Andalousie"),
    ("listening", "les cartes parler 🔮"),
    ("listening", "la lune se lever"),
    ("listening", "une vieille complainte rom"),
    ("listening", "le feu crépiter au campement"),
    ("listening", "les secrets du voyage"),
]
ENABLE_DAILY_STATUS = os.getenv("ENABLE_DAILY_STATUS", "1") != "0"
daily_status = DiscordDailyStatus(
    bot=bot, bot_id="malena", bot_label="Malena",
    personality_prompt=data.PERSONALITY_PROMPT, fallback_activities=_STATUS_FALLBACK,
    key_manager=key_manager, mistral_client=mistral_client,
    groq_client=groq_client, openrouter_client=openrouter_client,
    logger=logger, enabled=ENABLE_DAILY_STATUS,
) if DiscordDailyStatus else None


@bot.command(name="oubliemoi")
async def oubliemoi(ctx):
    """Purge toutes les données de mémoire de l'utilisateur."""
    uid = str(ctx.author.id)
    username = ctx.author.name
    
    if "users" in malena_brain.memory and uid in malena_brain.memory["users"]:
        del malena_brain.memory["users"][uid]
        
    if "conversations" in malena_brain.memory:
        malena_brain.memory["conversations"] = [
            c for c in malena_brain.memory["conversations"]
            if c.get("user") != username
        ]
    malena_brain.save_memory()
    
    await ctx.send("💅 T'inquiète pas, mon minot. J'ai tout effacé, j'sais même plus qui tu es. Allez, trace ta route !")

@bot.event
async def on_ready():
    logger.info(f'✅ Connectée en tant que {bot.user} (Gitana Mode)')
    logger.info(f'✅ {bot.user} est là ! (Gemini + Groq Hybrid)')
    # Lancer les tâches périodiques
    if not check_missed_mentions_malena.is_running():
        check_missed_mentions_malena.start()
    if DATABASE_AVAILABLE and not birthday_loop_malena.is_running():
        birthday_loop_malena.start()
    if daily_bio and not daily_bio_loop_malena.is_running():
        daily_bio_loop_malena.start()
    if not status_loop_malena.is_running():
        status_loop_malena.start()
        
    # Setup Mini-Games
    if GAMES_AVAILABLE:
        try:
            setup_games(bot, logger, PERSONA)
            logger.info("💅 [GAMES] Mini-jeux initialisés pour Malena")
        except Exception as e:
            logger.error(f"[GAMES] Erreur d'initialisation des mini-jeux: {e}")

        
    global twitch_announcer
    if TWITCH_AVAILABLE and twitch_announcer is None:
        twitch_announcer = setup_twitch_announcer(
            bot, "malena", logger,
            personality_prompt=data.PERSONALITY_PROMPT, key_manager=key_manager,
            mistral_client=mistral_client, groq_client=groq_client,
            openrouter_client=openrouter_client, bot_label="Malena")
        if twitch_announcer:
            twitch_poll_loop.start()

# Noms des AUTRES bots du serveur : si l'échange leur est visiblement adressé, on ne s'incruste
# PAS lors d'une intervention ALÉATOIRE (les mentions/nom direct du bot restent prioritaires).
OTHER_BOT_NAMES = ["sheo", "sheogorath", "johnny", "silverhand", "samurai", "silverbot", "alfred", "pennyworth", "m'aiq", "maiq", "sugar", "sugar bot"]

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
    if message.author == bot.user:
        return
        
    # SILENCE STREAM (Canal ignoré)
    if DATABASE_AVAILABLE and is_ignored_channel(message.channel):
        return
        
    await bot.process_commands(message)

    # SILENCE TOTAL ENTRE BOTS — un bot ne répond JAMAIS à un autre bot.
    if message.author.bot:
        return

    # Gestion des mentions ou réponses
    is_mentioned = bot.user.mentioned_in(message)
    is_reply = (message.reference and message.reference.resolved and 
                message.reference.resolved.author == bot.user)
    
    # 🚫 RESPECT DES MENTIONS : Si d'autres sont mentionnés et PAS moi, je me tais.
    if message.mentions and not is_mentioned:
        return

    # 1. DÉTECTION DU NOM OU MOTS DÉCLENCHEURS (Priority High)
    # --------------------------------------------------------
    content_lower = message.content.lower()
    
    # ✨ RÉACTIONS ÉMOJI CONTEXTUELLES (même sans répondre)
    # --------------------------------------------------------
    if not message.author.bot:
        for cat_name, cat_data in data.EMOJI_REACTIONS.items():
            if any(kw in content_lower for kw in cat_data["keywords"]):
                if random.random() < cat_data["proba"]:
                    emoji = random.choice(cat_data["emojis"])
                    try:
                        await message.add_reaction(emoji)
                        logger.info(f"✨ [REACTION] {emoji} sur message de {message.author.name} (cat: {cat_name})")
                    except discord.HTTPException:
                        pass
                break  # 1 seule catégorie de réaction par message
    
    # Mots qui forcent la réponse (ex: cuivre, caravane...)
    has_trigger_word = any(word in content_lower for word in data.TRIGGER_WORDS)
    
    # Noms du bot
    is_name_mentioned = any(name in content_lower for name in ["malena", "gitana", "gitane", "la gitane"])

    should_respond = is_mentioned or is_reply or is_name_mentioned or has_trigger_word

    # 2. INTERACTIONS SPÉCIALES (Utilisateurs VIP)
    # --------------------------------------------------------
    if not should_respond and message.author.name in data.SPECIAL_INTERACTIONS:
        user_config = data.SPECIAL_INTERACTIONS[message.author.name]
        
        # Tirage au sort basé sur la config
        if random.random() < user_config["proba"]:
            if await _other_bot_in_focus(message):
                logger.info("[ANTI-INCRUSTATION] Échange adressé à un autre bot → Malena s'abstient.")
            else:
                logger.info(f"🎲 [SPECIAL INTERACTION] Malena a envie de parler à {message.author.name} ({user_config['proba']*100}%)")
                should_respond = True


    # Si on doit répondre (Humain uniquement — les bots sont filtrés en amont)
    if should_respond:
        atts = await resolve_media_attachments(message)
        async with message.channel.typing():
            try:
                # Construction du prompt
                user_msg = message.content.replace(f'<@{bot.user.id}>', '').strip()
                
                # 1. DÉTECTION DE L'HUMEUR (du plus spécifique au plus général)
                current_mood = "NEUTRE"
                msg_lower = user_msg.lower()
                
                # Priorité 1 : VÉNÈRE (insultes)
                if any(word in msg_lower for word in data.MOODS["VENER"]["keywords"]):
                    current_mood = "VENER"
                # Priorité 2 : CHOQUÉE (stupeur)
                elif any(word in msg_lower for word in data.MOODS["CHOQUEE"]["keywords"]):
                    current_mood = "CHOQUEE"
                # Priorité 3 : MOQUEUSE (se moque)
                elif any(word in msg_lower for word in data.MOODS["MOQUEUSE"]["keywords"]):
                    current_mood = "MOQUEUSE"
                # Priorité 4 : LOVE (compliments)
                elif any(word in msg_lower for word in data.MOODS["LOVE"]["keywords"]):
                    current_mood = "LOVE"
                # Priorité 5 : FIÈRE (identité)
                elif any(word in msg_lower for word in data.MOODS["FIERE"]["keywords"]):
                    current_mood = "FIERE"
                
                if current_mood != "NEUTRE":
                    logger.info(f"\U0001f3ad Humeur détectée : {current_mood} (Msg: {user_msg})")
                
                # 2. GESTION DES SURNOMS
                target_nickname = data.NICKNAMES.get(message.author.name)
                nickname_instruction = ""
                if target_nickname:
                     nickname_instruction = f" (IMPORTANT : Appelle cet utilisateur '{target_nickname}' et pas autrement !)"
                     logger.info(f"🏷️ Surnom appliqué : {message.author.name} -> {target_nickname}")

                # CONTEXTE MÉMOIRE
                memory_context = malena_brain.get_context_summary(message.author.id)
                dr = malena_brain.get_daily_read(message.author.id)
                if dr:
                    memory_context += f"\n[CONSIGNE DU JOUR] {dr}"
                

                # SMART ROUTER (Media & Intention)
                _addressed = bool(is_mentioned or is_reply or is_name_mentioned or has_trigger_word)
                routing = classify_request(user_msg, atts, addressed=_addressed)
                
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
                
                if has_image and not user_msg.strip():
                    user_msg = "(L'utilisateur te montre une image sans rien dire.)"
                if has_image:
                    user_msg += "\n[VISION] Regarde l'image et commente-la avec ton style de marseillaise. Décris ce que tu vois !"
                if has_audio:
                    user_msg += "\n[🎤 VOCAL] L'utilisateur a envoyé un message vocal. Écoute-le et réponds avec ton franc-parler de gitane !"
                
                prompt = f"L'utilisateur {message.author.name} te dit : '{user_msg}'. Réponds-lui.{nickname_instruction}{memory_context}"
                
                # GÉNÉRATION ROUTÉE
                def _get_meme_addition():
                    chan_id = message.channel.id
                    consigne = build_meme_consigne(message.content or "", set(meme_recent[chan_id]))
                    if consigne:
                        import re as _re
                        m = _re.search(r"« (.+?) »", consigne)
                        if m:
                            meme_recent[chan_id].append(m.group(1))
                    return consigne

                reply_text = await generate_response_hybrid(prompt, current_mood, routing, media_data, mime_type, meme_consigne=_get_meme_addition())
                
                if not reply_text and (has_image or has_audio):
                    media_type_str = "l'image" if has_image else "le message vocal"
                    reply_text = f"Ay <@{message.author.id}> ! J'arrive pas à ouvrir {media_type_str}... Mon téléphone a encore buggé ! 🙄"

                # Dernier rempart : Discord refuse un message vide (400 / code 50006), et
                # l'exception remontait jusqu'au repli « (Erreur API) » visible par l'user.
                if _est_vide(reply_text):
                    logger.warning("⚠️ [MALENA] cascade sans texte exploitable → repli en personnage")
                    reply_text = "Ay caramba ! J'ai la tête ailleurs là, redemande-moi ça ma vie ! 💅"

                # Logging DB
                if DATABASE_AVAILABLE:
                    try:
                        user_data = get_or_create_user(message.author.id, message.author.name, message.author.display_name)
                        log_interaction(user_data['user_id'], "Malena", "message")
                    except Exception as db_err:
                        logger.error(f"DB Error: {db_err}")

                await message.reply(reply_text)
                logger.info(f"✅ Répondu à {message.author.name}")
                
                # ENREGISTRER L'INTERACTION DANS LA MÉMOIRE
                malena_brain.add_interaction(message.author.id, message.author.name, user_msg, reply_text)
                asyncio.create_task(malena_brain.refresh_daily_read(message.author.id, _daily_llm_call))

            except Exception as e:
                logger.error(f"❌ Erreur de génération : {e}")
                logger.error(f"❌ [API ERROR] : {e}")
                await message.reply("Ay caramba ! J'ai mal à la tête, laissez-moi tranquille ! (Erreur API)")

# DÉTECTION DES MENTIONS MANQUÉES

@tasks.loop(minutes=2)
async def check_missed_mentions_malena():
    """Vérifie si quelqu'un a mentionné Malena sans obtenir de réponse."""
    global checked_messages_malena
    
    name_triggers = ["malena", "gitana", "gitane", "la gitane"]
    
    for guild in bot.guilds:
        found_one = False  # Limite : 1 rattrapage par cycle par guild
        for channel in guild.text_channels:
            if found_one:
                break
            
            # Vérifier les permissions
            perms = channel.permissions_for(guild.me)
            if not perms.read_messages or not perms.send_messages or not perms.read_message_history:
                continue

            if DATABASE_AVAILABLE and is_ignored_channel(channel): continue
            
            try:
                messages = []
                async for msg in channel.history(limit=20):
                    messages.append(msg)
                
                # Parcourir les messages (du plus ancien au plus récent)
                messages.reverse()
                
                for i, msg in enumerate(messages):
                    # Skip si déjà vérifié, si c'est un bot, ou si trop vieux
                    if msg.id in checked_messages_malena:
                        continue
                    if msg.author.bot:
                        continue
                    
                    age = (datetime.now(msg.created_at.tzinfo) - msg.created_at).total_seconds() if msg.created_at.tzinfo else (datetime.utcnow() - msg.created_at).total_seconds()
                    if age > 600 or age < 30:  # Ignorer > 10min ou < 30s
                        checked_messages_malena.add(msg.id)
                        continue
                    
                    # Détecter si on est mentionnée
                    is_mentioned = bot.user.mentioned_in(msg)
                    content_lower = msg.content.lower()
                    is_name_mentioned = any(name in content_lower for name in name_triggers)
                    
                    # Si un AUTRE est mentionné mais PAS nous, ignorer
                    if msg.mentions and not is_mentioned:
                        checked_messages_malena.add(msg.id)
                        continue
                    
                    if not is_mentioned and not is_name_mentioned:
                        checked_messages_malena.add(msg.id)
                        continue
                    
                    # Vérifier si le bot a déjà répondu après ce message
                    bot_replied = False
                    for later_msg in messages[i+1:]:
                        if later_msg.author.id == bot.user.id:
                            bot_replied = True
                            break
                    
                    if bot_replied:
                        checked_messages_malena.add(msg.id)
                        continue
                    
                    # MENTION MANQUÉE DÉTECTÉE !
                    logger.info(f"🔔 [MENTION MANQUÉE] {msg.author.name} a parlé à Malena il y a {int(age)}s sans réponse !")
                    
                    # Générer une réponse tardive
                    user_text = msg.content.replace(f'<@{bot.user.id}>', '').strip()
                    if not user_text:
                        user_text = "(L'utilisateur t'a juste mentionnée sans rien dire.)"
                    
                    late_prompt = (
                        f"{data.PERSONALITY_PROMPT}\n\n"
                        f"CONTEXTE: Tu viens de te rendre compte que {msg.author.name} t'a parlé il y a quelques minutes "
                        f"mais tu n'as PAS répondu (tu étais occupée à autre chose). "
                        f"Son message était : '{user_text}'.\n"
                        f"INSTRUCTION: Réponds-lui maintenant avec ton style marseillais. Excuse-toi à ta façon "
                        f"(tu étais au téléphone, tu regardais les étoiles, tu faisais la sieste...). "
                        f"Puis réponds à son message. Sois naturelle et en personnage. 2-3 phrases max."
                    )
                    
                    # Détection de l'humeur pour la réponse tardive
                    current_mood = "NEUTRE"
                    msg_lower = user_text.lower()
                    if any(word in msg_lower for word in data.MOODS["VENER"]["keywords"]):
                        current_mood = "VENER"
                    elif any(word in msg_lower for word in data.MOODS["LOVE"]["keywords"]):
                        current_mood = "LOVE"
                    
                    response_text = await generate_response_hybrid(late_prompt, current_mood)
                    
                    if not response_text or "Erreur API" in response_text:
                        # Fallback statique
                        fallbacks = [
                            f"Eh oh <@{msg.author.id}> ! Tu m'as parlé et j'ai pas répondu ?! Excuse-moi j'étais au téléphone avec ma cousine, tu sais comment c'est ! Tu disais quoi ?",
                            f"Ay <@{msg.author.id}> ! Pardon pardon, j'étais dans la lune ! Non mais attends, t'es sérieux tu m'as parlé et j'ai pas capté ? Allez dis-moi !",
                            f"Oh la la <@{msg.author.id}> ! J'ai vu que tu m'avais parlé ! Pardonne-moi j'étais occupée à regarder les oiseaux sur le balcon. Bénissou bénissou, qu'est-ce que tu voulais ?"
                        ]
                        response_text = random.choice(fallbacks)
                    
                    try:
                        await msg.reply(response_text)
                        logger.info(f"✅ [MENTION MANQUÉE] Répondu à {msg.author.name} en retard !")
                    except Exception as e:
                        logger.error(f"❌ [MENTION MANQUÉE] Erreur envoi: {e}")
                    
                    checked_messages_malena.add(msg.id)
                    found_one = True
                    break  # 1 seul rattrapage par cycle
                    
            except Exception as e:
                logger.error(f"❌ [MISSED CHECK] Erreur canal {channel.name}: {e}")
    
    # Nettoyer le cache
    if len(checked_messages_malena) > MAX_CHECKED_CACHE:
        checked_messages_malena = set(list(checked_messages_malena)[-MAX_CHECKED_CACHE:])

@check_missed_mentions_malena.before_loop
async def before_missed_mentions():
    await bot.wait_until_ready()

# ANNIVERSAIRES MALENA

@tasks.loop(hours=12)
async def birthday_loop_malena():
    """Vérifie les anniversaires toutes les 12 heures."""
    if not DATABASE_AVAILABLE:
        return
    try:
        await check_and_send_birthdays(bot, "Malena")
        logger.info("🎂 [ANNIVERSAIRE] Vérification des anniversaires effectuée.")
    except Exception as e:
        logger.error(f"❌ [ANNIVERSAIRE] Erreur : {e}")

@birthday_loop_malena.before_loop
async def before_birthday_malena():
    await bot.wait_until_ready()

@tasks.loop(seconds=90)
async def twitch_poll_loop():
    if twitch_announcer:
        await twitch_announcer.tick()

@twitch_poll_loop.before_loop
async def before_twitch_poll():
    await bot.wait_until_ready()

@tasks.loop(hours=1)
async def daily_bio_loop_malena():
    if daily_bio:
        await daily_bio.ensure_daily_bio()

@daily_bio_loop_malena.before_loop
async def before_daily_bio_malena():
    await bot.wait_until_ready()

# STATUT TOURNANT (présence Discord)
@tasks.loop(minutes=30)
async def status_loop_malena():
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

@status_loop_malena.before_loop
async def before_status_malena():
    await bot.wait_until_ready()

# ÉVÉNEMENTS SERVEUR — BIENVENUE ET DÉPART


@bot.event
async def on_member_join(member):
    """Message de bienvenue quand un membre rejoint."""
    if not DATABASE_AVAILABLE:
        return
    await handle_member_join(bot, member, "Malena")

@bot.event
async def on_member_remove(member):
    """Message de départ quand un membre quitte."""
    if not DATABASE_AVAILABLE:
        return
    await handle_member_remove(bot, member, "Malena")

if __name__ == "__main__":
    setup_graceful_shutdown(bot)
    bot.run(DISCORD_TOKEN)
