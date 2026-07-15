# -*- coding: utf-8 -*-
"""
sheo_voice.py — Module TTS pour Sheogorath (100% Open Source).

Moteur : Piper TTS (serveur Docker via Wyoming protocol ou HTTP)
Voix : fr_FR-gilles-low (voix masculine française mature)
Architecture : Le bot reste connecté au vocal tant qu'il y a des auditeurs.

FLUX :
1. Le texte de réponse du bot est envoyé à Piper TTS (conteneur Docker)
2. Piper génère un WAV en ~200ms (CPU only, ultra-rapide)
3. Le WAV est joué dans le voice channel via discord.FFmpegPCMAudio
4. Le bot reste dans le canal vocal (persistant)
"""

import os
import io
import asyncio
import logging
import tempfile
import random
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("sheogorath")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION TTS
# ═══════════════════════════════════════════════════════════════

# URL du serveur Piper TTS (Docker)
PIPER_TTS_URL = os.getenv("PIPER_TTS_URL", "http://piper-tts:5000")

# Voix Piper par défaut (masculin français mature — "gilles")
PIPER_VOICE = os.getenv("PIPER_VOICE", "fr_FR-gilles-low")

# Paramètres de synthèse
PIPER_SETTINGS = {
    "length_scale": 0.95,     # Légèrement plus rapide que la normale (théâtral)
    "noise_scale": 0.8,       # Haute variation (folie, imprévisibilité)
    "noise_w": 0.9,           # Variation de prononciation (expressivité)
    "sentence_silence": 0.3,  # Pause entre phrases
}

# Auto-Voice settings
VOICE_AUTO_CHANCE = 0.15      # 15% de chance de répondre en vocal
VOICE_SHORT_MAX_LEN = 250     # Max caractères pour auto-voice
VOICE_IDLE_TIMEOUT = 300      # 5 minutes d'inactivité → déconnexion
VOICE_ALWAYS_IF_IN_VC = True  # Toujours répondre en vocal si le user est dans le VC du bot

# Tracking de la dernière activité vocale par guild
_voice_last_activity = {}  # {guild_id: datetime}

# Cache de disponibilité Piper
_piper_available = None
_piper_check_time = 0
_PIPER_CHECK_INTERVAL = 60  # Revérifier toutes les 60 secondes

# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════

async def check_piper_available() -> bool:
    """Vérifie si le serveur TTS (Chatterbox ou Piper) est disponible."""
    global _piper_available, _piper_check_time
    import time
    now = time.time()
    
    # Cache
    if _piper_available is not None and (now - _piper_check_time) < _PIPER_CHECK_INTERVAL:
        return _piper_available
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Tenter /health (Chatterbox FastAPI)
            try:
                async with session.get(f"{PIPER_TTS_URL}/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        _piper_available = True
                        _piper_check_time = now
                        logger.info(
                            f"✅ [TTS] Chatterbox disponible "
                            f"(model={data.get('model','?')}, device={data.get('device','?')}, "
                            f"voice_ref={data.get('voice_ref_found', '?')})"
                        )
                        return True
            except Exception:
                pass
            
            # Fallback : GET /?text=test (Piper compatible)
            async with session.get(f"{PIPER_TTS_URL}/?text=test") as resp:
                _piper_available = resp.status == 200
    except Exception:
        _piper_available = False
    
    _piper_check_time = now
    if _piper_available:
        logger.info("✅ [TTS] TTS disponible (mode Piper)")
    else:
        logger.debug("[TTS] TTS indisponible")
    return _piper_available


def is_tts_enabled() -> bool:
    """Vérifie si le TTS est activable (synchrone, pour le startup)."""
    return bool(PIPER_TTS_URL)

# ═══════════════════════════════════════════════════════════════
# TEXT PREPROCESSING — Performance Sheogorath
# ═══════════════════════════════════════════════════════════════

# Patterns de rire et d'émotions pour injection automatique
_LAUGH_TRIGGERS = [
    "haha", "HAHA", "hihi", "HIHI", "héhé", "HÉHÉ",
    "muahahaha", "MUAHAHAHA", "hahaha", "😂", "🤣", "😈"
]

_CHUCKLE_TRIGGERS = [
    "héhé", "hé hé", "heh", "hehe", "😏", "😼"
]

def prepare_text_for_tts(text: str, mood: str = "neutral") -> str:
    """
    Prépare le texte pour capturer le jeu d'acteur de Philippe Bozo.
    
    Transformations appliquées :
    1. Suppression emojis/markdown (incompatibles TTS)
    2. Injection de tags paralinguistiques [laugh]/[chuckle] (natifs Chatterbox Turbo)
    3. Pauses dramatiques (... → silences réels)
    4. Gestion des MAJUSCULES d'emphase
    5. Auto-interruptions (— → pause)
    6. Découpage adaptatif selon l'humeur (mania=rapide, dementia=lent)
    """
    import re

    # ── 1. Nettoyage de base ──
    
    # Supprimer les emojis (Chatterbox ne les gère pas)
    text = re.sub(
        r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F'
        r'\U0000200D\U00002600-\U000026FF\U00002700-\U000027BF]+',
        '', text
    )
    
    # Supprimer les mentions Discord <@123456>
    text = re.sub(r'<@!?\d+>', '', text)
    
    # Supprimer le markdown Discord (**bold**, *italic*, etc.)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'~~([^~]+)~~', r'\1', text)
    
    # ── 2. Injection de tags paralinguistiques (NATIFS Chatterbox Turbo) ──
    
    # Convertir les onomatopées de rire en tags [laugh]
    for trigger in _LAUGH_TRIGGERS:
        if trigger in text:
            text = text.replace(trigger, '[laugh]', 1)  # Un seul remplacement
            break  # Un seul rire par message
    
    # Convertir les petits rires en [chuckle]
    for trigger in _CHUCKLE_TRIGGERS:
        if trigger in text:
            text = text.replace(trigger, '[chuckle]', 1)
            break
    
    # ── 3. Pauses dramatiques de Philippe Bozo ──
    
    # Les "..." deviennent de vrais silences (Chatterbox les respecte)
    text = re.sub(r'\.{3,}', '... ', text)
    
    # Les tirets longs (auto-interruptions) → pause + reprise
    text = text.replace('—', '... ')
    text = text.replace(' - ', '... ')
    
    # Les "!" multiples → un seul (plus naturel vocalement)
    text = re.sub(r'!{2,}', '!', text)
    
    # Les "?" multiples → un seul
    text = re.sub(r'\?{2,}', '?', text)
    
    # ── 4. Nettoyage final ──
    
    text = re.sub(r'\s+', ' ', text).strip()
    
    # ── 5. Découpage adaptatif selon l'humeur ──
    
    max_len = _get_max_length(mood)
    if len(text) > max_len:
        sentences = re.split(r'(?<=[.!?])\s+', text[:max_len])
        text = ' '.join(sentences[:-1]) if len(sentences) > 1 else sentences[0]
    
    return text


def _get_max_length(mood: str) -> int:
    """
    Longueur max du texte selon l'humeur.
    Philippe Bozo alterne entre tirades rapides (Mania) et phrases glaciales (Dementia).
    """
    return {
        "mania": 600,      # Mania : tirades rapides, plus de texte
        "dementia": 300,   # Dementia : phrases courtes, glaciales, menaçantes
        "neutral": 450,    # Neutre : équilibré
        "bliss": 550,      # Bliss : jovial, anecdotes (exception du conteur)
    }.get(mood, 450)

# ═══════════════════════════════════════════════════════════════
# TTS GENERATION — Piper HTTP API
# ═══════════════════════════════════════════════════════════════

# Paramètres Chatterbox par humeur (capture le jeu d'acteur de Philippe Bozo)
VOICE_MOOD_PARAMS = {
    "mania": {
        "exaggeration": 1.0,    # MAX expressif (sauts d'octave, excitation)
        "cfg_weight": 0.15,     # Rythme très rapide, imprévisible
    },
    "dementia": {
        "exaggeration": 0.8,    # Menace froide très marquée
        "cfg_weight": 0.5,      # Rythme très lent, pesant
    },
    "neutral": {
        "exaggeration": 0.95,   # Théâtral intense
        "cfg_weight": 0.25,     # Rythme dramatique marqué
    },
    "bliss": {
        "exaggeration": 1.0,    # Très expressif (chaleureux et jovial)
        "cfg_weight": 0.2,      # Rythme rapide, dynamique mais fluide (anecdotes)
    },
}

async def generate_tts(text: str, voice: str = None, mood: str = "neutral") -> bytes | None:
    """
    Génère l'audio TTS via Chatterbox avec voice cloning de Philippe Bozo.
    
    Adapte automatiquement l'expressivité selon l'humeur du bot :
    - Mania : exaggeration haute, rythme rapide (folie joyeuse)
    - Dementia : exaggeration basse, rythme lent (menace glaciale)
    - Neutral : théâtral standard
    
    Args:
        text: Texte à synthétiser
        voice: Non utilisé (voix de référence configurée au niveau Docker)
        mood: Humeur actuelle du bot ("mania", "dementia", "neutral")
    
    Returns:
        bytes WAV ou None si échec
    """
    if not await check_piper_available():
        return None
    
    text = prepare_text_for_tts(text, mood)
    
    if not text or len(text.strip()) < 2:
        return None
    
    # Récupérer les paramètres vocaux selon l'humeur
    params = VOICE_MOOD_PARAMS.get(mood, VOICE_MOOD_PARAMS["neutral"])
    
    # Stratégie de timeout : 15s pour le mode Turbo (POST), 10s pour le mode Standard (GET)
    # On utilise des timeouts par requête plutôt que par session globale
    async with aiohttp.ClientSession() as session:
        # --- TENTATIVE 1 : POST /tts (Mode Turbo Expressif) ---
        try:
            timeout_turbo = aiohttp.ClientTimeout(total=15)
            async with session.post(
                f"{PIPER_TTS_URL}/tts",
                json={
                    "text": text,
                    "exaggeration": params["exaggeration"],
                    "cfg_weight": params["cfg_weight"],
                    "language_id": "fr"
                },
                timeout=timeout_turbo
            ) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    logger.info(
                        f"🔊 [TTS] Audio généré (Mode Turbo) : {len(audio_data)} bytes, "
                        f"{len(text)} chars, mood={mood}"
                    )
                    return audio_data
                else:
                    logger.warning(f"⚠️ [TTS] Mode Turbo échoué (Status {resp.status})")
        except asyncio.TimeoutError:
            logger.warning("⏱️ [TTS] Timeout Mode Turbo (15s), passage au mode Standard...")
        except Exception as e:
            logger.debug(f"[TTS] Erreur Mode Turbo (silencieuse) : {e}")

        # --- TENTATIVE 2 : GET / (Mode Standard / Fallback) ---
        try:
            timeout_std = aiohttp.ClientTimeout(total=10)
            async with session.get(
                f"{PIPER_TTS_URL}/",
                params={"text": text},
                timeout=timeout_std
            ) as resp:
                if resp.status == 200:
                    audio_data = await resp.read()
                    logger.info(f"🔊 [TTS] Audio généré (Mode Standard) : {len(audio_data)} bytes")
                    return audio_data
                else:
                    body = await resp.text()
                    logger.error(f"❌ [TTS] Échec total (Status {resp.status}) : {body[:100]}")
        except asyncio.TimeoutError:
            logger.error("⏱️ [TTS] Timeout total (Mode Standard 10s)")
        except Exception as e:
            logger.error(f"❌ [TTS] Erreur fatale génération : {e}")
            global _piper_available
            _piper_available = None
    
    return None

# ═══════════════════════════════════════════════════════════════
# VOICE CHANNEL MANAGEMENT — Persistant
# ═══════════════════════════════════════════════════════════════

async def ensure_voice_connection(bot, guild, target_channel=None):
    """
    S'assure que le bot est connecté au voice channel.
    Si déjà connecté, retourne le voice_client existant.
    Si pas connecté, se connecte au channel cible ou au plus peuplé.
    
    Returns:
        discord.VoiceClient ou None
    """
    import discord
    
    voice_client = guild.voice_client
    
    # Déjà connecté
    if voice_client and voice_client.is_connected():
        return voice_client
    
    # Chercher le channel cible
    if not target_channel:
        # Trouver le canal vocal avec le plus de membres humains
        best_channel = None
        max_members = 0
        for vc in guild.voice_channels:
            member_count = len([m for m in vc.members if not m.bot])
            if member_count > max_members:
                max_members = member_count
                best_channel = vc
        target_channel = best_channel
    
    if not target_channel:
        logger.debug("🔇 [VOICE] Aucun canal vocal avec des membres")
        return None
    
    # Vérifier les permissions
    perms = target_channel.permissions_for(guild.me)
    if not perms.connect or not perms.speak:
        logger.warning(f"🔇 [VOICE] Permissions insuffisantes pour {target_channel.name}")
        return None
    
    try:
        logger.debug(f"📡 [VOICE] Tentative de connexion à #{target_channel.name}...")
        voice_client = await target_channel.connect(self_deaf=True, timeout=20.0)
        logger.info(f"🔊 [VOICE] Connecté à #{target_channel.name} ({guild.name})")
        _voice_last_activity[guild.id] = datetime.now()
        return voice_client
    except Exception as e:
        logger.error(f"❌ [VOICE] Impossible de se connecter à #{target_channel.name}: {e}")
        return None


async def play_audio(voice_client, audio_bytes: bytes) -> bool:
    """
    Joue des bytes audio WAV dans le voice channel.
    Attend la fin de la lecture avant de retourner.
    
    Args:
        voice_client: discord.VoiceClient connecté
        audio_bytes: Données WAV
    
    Returns:
        True si joué avec succès
    """
    import discord
    
    if not voice_client or not voice_client.is_connected():
        return False
    
    # Si déjà en train de jouer, attendre
    if voice_client.is_playing():
        voice_client.stop()
        await asyncio.sleep(0.2)
    
    # Sauvegarder temporairement
    tmp_dir = Path(tempfile.gettempdir())
    tmp_path = tmp_dir / f"sheo_tts_{random.randint(1000, 9999)}.wav"
    
    try:
        tmp_path.write_bytes(audio_bytes)
        
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(str(tmp_path)), volume=4.0)
        
        # Event pour attendre la fin
        play_done = asyncio.Event()
        
        def after_play(error):
            if error:
                logger.error(f"❌ [VOICE] Erreur lecture: {error}")
            play_done.set()
        
        voice_client.play(source, after=after_play)
        
        # Attendre la fin (max 30s)
        try:
            await asyncio.wait_for(play_done.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("⏱️ [VOICE] Timeout lecture audio (30s)")
            voice_client.stop()
        
        # Mettre à jour l'activité
        guild_id = voice_client.guild.id
        _voice_last_activity[guild_id] = datetime.now()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ [VOICE] Erreur play: {e}")
        return False
    finally:
        # Cleanup du fichier temporaire
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


async def disconnect_if_idle(bot):
    """
    Déconnecte le bot des voice channels inactifs.
    À appeler périodiquement (ex: toutes les 60s via @tasks.loop).
    """
    now = datetime.now()
    
    for guild in bot.guilds:
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            continue
        
        # Vérifier si le canal est vide (aucun humain)
        channel = vc.channel
        human_count = len([m for m in channel.members if not m.bot])
        
        if human_count == 0:
            logger.info(f"🔇 [VOICE] Canal vide, déconnexion de #{channel.name}")
            await vc.disconnect()
            _voice_last_activity.pop(guild.id, None)
            continue
        
        # Vérifier le timeout d'inactivité
        last_activity = _voice_last_activity.get(guild.id)
        if last_activity and (now - last_activity).total_seconds() > VOICE_IDLE_TIMEOUT:
            logger.info(f"🔇 [VOICE] Inactivité {VOICE_IDLE_TIMEOUT}s, déconnexion de #{channel.name}")
            await vc.disconnect()
            _voice_last_activity.pop(guild.id, None)

# ═══════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL — Auto-Voice
# ═══════════════════════════════════════════════════════════════

async def send_voice_response(bot, message, text: str, force: bool = False, mood: str = "neutral") -> bool:
    """
    Pipeline complet : TTS + envoi dans le voice channel.
    
    Logique de décision :
    1. Si `force=True` → toujours parler en vocal
    2. Si l'utilisateur est dans le VC du bot → toujours parler
    3. Si l'utilisateur est dans un VC → 15% de chance
    4. Sinon → pas de vocal
    
    Args:
        bot: Instance du bot Discord
        message: Le message Discord original
        text: Le texte à synthétiser
        force: Forcer la réponse vocale
        mood: Humeur actuelle du bot
    
    Returns:
        True si l'audio a été joué
    """
    # L'utilisateur doit être dans un voice channel
    if not message.author.voice or not message.author.voice.channel:
        return False
    
    user_vc = message.author.voice.channel
    guild = message.guild
    
    # Décision : parler ou non ?
    if not force:
        bot_vc = guild.voice_client
        
        if bot_vc and bot_vc.is_connected() and bot_vc.channel == user_vc:
            # Bot déjà dans le même VC que l'utilisateur → toujours parler
            pass
        elif VOICE_ALWAYS_IF_IN_VC and bot_vc and bot_vc.is_connected():
            # Bot dans un VC, user dans un autre → ne pas suivre
            return False
        else:
            # Pas encore connecté → chance aléatoire
            if random.random() > VOICE_AUTO_CHANCE:
                return False
    
    # Vérifier la longueur du texte
    if len(text) > VOICE_SHORT_MAX_LEN and not force:
        return False
    
    # Générer le TTS
    audio = await generate_tts(text, mood=mood)
    if not audio:
        return False
    
    # Se connecter / rester connecté
    voice_client = await ensure_voice_connection(bot, guild, target_channel=user_vc)
    if not voice_client:
        return False
    
    # Jouer l'audio
    success = await play_audio(voice_client, audio)
    
    if success:
        logger.info(f"🎤 [AUTO-VOICE] Sheogorath a parlé dans #{user_vc.name} !")
    
    return success

# ═══════════════════════════════════════════════════════════════
# COMMANDES VOCALES — Entrées/Sorties
# ═══════════════════════════════════════════════════════════════

async def cmd_join_voice(ctx):
    """Commande pour rejoindre le voice channel de l'utilisateur."""
    if not ctx.author.voice:
        await ctx.send("🔇 Rejoins un canal vocal d'abord, imbécile ! Je ne parle pas aux murs !")
        return False
    
    vc = await ensure_voice_connection(ctx.bot, ctx.guild, ctx.author.voice.channel)
    if vc:
        phrases = [
            "🎤 Me voilà ! Préparez vos oreilles, mortels !",
            "🎤 Le Prince de la Folie entre en scène ! Applaudissez !",
            "🎤 Silence ! Votre Dieu parle maintenant !",
            "🎤 Qui a invoqué le Dieu Fou dans ce salon minable ?",
        ]
        await ctx.send(random.choice(phrases))
        return True
    else:
        await ctx.send("🌀 Ma voix divine s'est perdue entre les dimensions...")
        return False


async def cmd_leave_voice(ctx):
    """Commande pour quitter le voice channel."""
    vc = ctx.guild.voice_client
    if vc and vc.is_connected():
        await vc.disconnect()
        _voice_last_activity.pop(ctx.guild.id, None)
        phrases = [
            "🔇 Je m'en vais ! Vous ne méritez pas ma voix divine !",
            "🔇 Haskill m'appelle. Il a encore perdu mes chaussettes.",
            "🔇 La folie a besoin de repos. Enfin... NON ! Mais je pars quand même !",
        ]
        await ctx.send(random.choice(phrases))
    else:
        await ctx.send("🔇 Je ne suis même pas dans votre canal, imbécile !")
