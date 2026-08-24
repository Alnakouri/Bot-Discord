"""
Smart Router — Routage intelligent des modèles IA.
Économise le quota Gemini en ne l'utilisant que pour vision, audio et raisonnement.
Tout le texte courant est routé vers Groq/OpenRouter/Mistral (gratuits ou pas chers).
"""

import re
import logging
import aiohttp

try:
    from shared.models import GEMINI_FLASH, GEMINI_FLASH_LITE, GROQ_FAST, MISTRAL_MAIN, OPENROUTER_FREE
except ImportError:  # bot déployé seul, sans shared/
    GEMINI_FLASH      = "gemini-3.5-flash"
    GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"
    GROQ_FAST         = "openai/gpt-oss-120b"
    MISTRAL_MAIN      = "mistral-large-latest"
    OPENROUTER_FREE   = "nvidia/nemotron-3-super-120b-a12b:free"

logger = logging.getLogger("smart_router")

# ═══════════════════════════════════════════
# DÉTECTION DU RAISONNEMENT COMPLEXE
# ═══════════════════════════════════════════

REASONING_KEYWORDS_FR = [
    r"\bexplique\b", r"\banalyse\b", r"\bcompare\b", r"\bpourquoi\b",
    r"\bcomment\s+fonctionne\b", r"\bdémontre\b", r"\braisonne\b",
    r"\bcalcule\b", r"\bstratégie\b", r"\boptimise\b", r"\ben\s+détail\b",
    r"\bthéorie\b", r"\bproblème\b", r"\bdébat\b", r"\bdifférence\s+entre\b",
    r"\bavantages?\s+et\s+inconvénients?\b", r"\bpour\s+et\s+contre\b",
]
REASONING_KEYWORDS_EN = [
    r"\bexplain\b", r"\banalyze\b", r"\bcompare\b", r"\bwhy\b",
    r"\bhow\s+does\b", r"\bcalculate\b", r"\bstrategy\b", r"\boptimize\b",
    r"\bin\s+detail\b", r"\btheory\b", r"\bdebate\b", r"\bpros?\s+and\s+cons?\b",
]
ALL_REASONING_PATTERNS = REASONING_KEYWORDS_FR + REASONING_KEYWORDS_EN

# Types MIME supportés
AUDIO_MIME_TYPES = [
    "audio/ogg", "audio/mpeg", "audio/mp3", "audio/wav",
    "audio/webm", "audio/aac", "audio/flac", "audio/x-wav",
]
IMAGE_MIME_TYPES = [
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp",
]

# Taille max des médias (sécurité)
MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10 MB


# ═══════════════════════════════════════════
# TYPES DE REQUÊTES
# ═══════════════════════════════════════════

class RequestType:
    TEXT = "text"           # → Cascade économique (Mistral/Groq/OpenRouter)
    REPARTEE = "repartee"   # → Grok (Humor/Personality)
    IMAGE = "image"         # → Gemini 2.0 Flash (Vision)
    AUDIO = "audio"         # → Gemini 2.0 Flash (Audio)
    REASONING = "reasoning" # → Gemini 2.0 Pro (Thinking)


# ═══════════════════════════════════════════
# CLASSIFICATION
# ═══════════════════════════════════════════


def _is_voice_message(attachment) -> bool:
    """True si l'attachment est un message vocal Discord.

    `discord.Attachment.is_voice_message` est une **méthode** (discord.py 2.x) : il
    faut l'appeler. On tolère aussi un simple booléen (mocks, versions anciennes).
    """
    flag = getattr(attachment, "is_voice_message", None)
    if flag is None:
        return False
    try:
        return bool(flag() if callable(flag) else flag)
    except Exception:
        return False


def classify_request(message_text, attachments=None, *, addressed: bool = False):
    """
    Classifie un message Discord pour déterminer le modèle optimal.

    Args:
        message_text: Le texte du message
        attachments: Liste des pièces jointes Discord (message.attachments)
        addressed: True si le bot est DIRECTEMENT interpellé (mention / reply / nom
            prononcé / continuité de conversation). Défaut False → comportement d'origine
            inchangé pour tout appelant qui ne passe pas ce signal (rétro-compatible).
            Quand True et que le message est du banter court (ni raisonnement, ni demande
            d'info), on vise la cascade REPARTEE (Grok) pour une répartie plus mordante.

    Returns:
        dict avec type, model, reason, has_image, has_audio, 
        image_attachment, audio_attachment
    """
    result = {
        "type": RequestType.TEXT,
        "model": None,
        "reason": "Texte simple → cascade économique",
        "has_image": False,
        "has_audio": False,
        "image_attachment": None,
        "audio_attachment": None,
    }
    
    # 1. Vérifier les pièces jointes (PRIORITÉ ABSOLUE)
    if attachments:
        for att in attachments:
            ct = (att.content_type or "").lower()
            filename = (att.filename or "").lower()
            
            # DETECTION MESSAGE VOCAL (OGG Discord)
            # ⚠️ discord.py expose is_voice_message comme une METHODE, pas un attribut :
            # un `getattr(att, 'is_voice_message', False)` nu renvoie la méthode liée,
            # toujours vraie → TOUTE pièce jointe (images comprises) passait en vocal.
            is_voice = _is_voice_message(att) or (filename.endswith('.ogg') and "audio" in ct)
            if is_voice:
                result["type"] = RequestType.AUDIO
                result["model"] = GEMINI_FLASH
                result["reason"] = "🎤 Message vocal Discord → Gemini Audio"
                result["has_audio"] = True
                result["audio_attachment"] = att
                logger.info(f"[ROUTER] {result['reason']}")
                return result

            # Image détectée
            if any(ct.startswith(mime) for mime in IMAGE_MIME_TYPES):
                result["type"] = RequestType.IMAGE
                result["model"] = GEMINI_FLASH
                result["reason"] = f"🖼️ Image ({ct}) → Gemini Vision"
                result["has_image"] = True
                result["image_attachment"] = att
                logger.info(f"[ROUTER] {result['reason']}")
                return result  # Image est prioritaire
            
            # Audio standard détecté
            if any(ct.startswith(mime) for mime in AUDIO_MIME_TYPES):
                result["type"] = RequestType.AUDIO
                result["model"] = GEMINI_FLASH
                result["reason"] = f"🎵 Fichier Audio ({ct}) → Gemini Audio"
                result["has_audio"] = True
                result["audio_attachment"] = att
                logger.info(f"[ROUTER] {result['reason']}")
                return result
    
    # 2. Vérifier si raisonnement complexe requis
    if _needs_reasoning(message_text):
        result["type"] = RequestType.REASONING
        result["model"] = GEMINI_FLASH
        result["reason"] = "🧠 Raisonnement complexe → Gemini Pro"
        logger.info(f"[ROUTER] {result['reason']}")
        return result

    # 3. Vérifier si humour / répartie requis (Priorité Grok)
    if _needs_humor(message_text):
        result["type"] = RequestType.REPARTEE
        result["reason"] = "🎭 Humour / Répartie → Grok (xAI)"
        logger.info(f"[ROUTER] {result['reason']}")
        return result

    # 3b. Banter ADRESSÉ : le bot est directement interpellé (mention/reply/nom/continuité)
    # et ce n'est ni du raisonnement ni une demande d'info → on vise le meilleur modèle
    # d'humour (cascade REPARTEE / Grok). Gardé sur `addressed` pour MAÎTRISER LE COÛT :
    # Grok est payant, on ne l'engage que sur les vrais moments de répartie, pas sur tout.
    if addressed and _is_banter(message_text):
        result["type"] = RequestType.REPARTEE
        result["reason"] = "🎭 Banter adressé → Grok (xAI)"
        logger.info(f"[ROUTER] {result['reason']}")
        return result

    # 4. Texte simple → cascade économique
    logger.debug(f"[ROUTER] 💬 Texte simple → cascade Mistral/Groq/OpenRouter")
    return result


def get_model_cascade(routing_type):
    """
    Retourne la liste ordonnée (client_type, model_name) pour un type donné.
    """
    if routing_type == RequestType.REASONING:
        return [
            ("gemini",  GEMINI_FLASH),
            ("mistral", MISTRAL_MAIN),
            ("groq",    GROQ_FAST),
        ]

    if routing_type in (RequestType.IMAGE, RequestType.AUDIO):
        # Vision/audio via Gemini direct (clé propre).
        # Ancien échelon OpenRouter google/gemini-2.0-flash-lite-001 retiré
        # (payant → 402 sur compte vide, et Gemini direct couvre déjà gratis).
        return [
            ("gemini", GEMINI_FLASH),
            ("gemini", GEMINI_FLASH_LITE),
        ]
    
    if routing_type == RequestType.REPARTEE:
        # Cascade FREE-TIER optimisée répartie/humour, 3 fournisseurs distincts
        # (pools de rate-limit indépendants → si l'un throttle, l'autre prend le relais) :
        return [
            # Ordre pour un rendu FR PROPRE et fidèle à la persona (1er qui répond gagne) :
            # Mistral Large (modèle FR, français le plus propre, obéit bien → moins de tics) en
            # tête, puis gpt-oss-120b (Groq, rapide) en secours, et enfin nemotron-3-super-120b
            # tout en bas pour la variété quand les deux propres tombent.
            # NB : plus aucun Grok gratuit sur OpenRouter (x-ai/grok-4-fast:free déprécié → 404, 2026-07).
            ("mistral", MISTRAL_MAIN),
            ("groq", GROQ_FAST),
            ("openrouter", OPENROUTER_FREE),
        ]
    
    # TEXT par défaut — 3 fournisseurs à clé propre (Mistral/Groq/Gemini),
    # aucune dépendance au crédit OpenRouter. (Ancien échelon gemma retiré
    # car il provoque actuellement des erreurs 429).
    return [
        ("mistral", MISTRAL_MAIN),
        ("groq", GROQ_FAST),
        ("gemini", GEMINI_FLASH_LITE),
    ]


def _needs_humor(text):
    """Détecte les signaux d'humour, sarcasme ou répartie."""
    if not text:
        return False
    text_lower = text.lower()

    # Mots-clés de répartie
    humor_triggers = [
        r"\bblague\b", r"\bhumour\b", r"\bdrôle\b", r"\binsulte\b",
        r"\bidiot\b", r"\bimbécile\b", r"\bt'es\s+qui\b",
        r"\braconte\b", r"\btaquine\b",
        r"\bsarcasme\b", r"\bcynique\b"
    ]

    # Ponctuation expressive (???, !!!)
    is_expressive = text.count("!") >= 3 or text.count("?") >= 3

    # Détection par mots-clés
    has_keywords = any(re.search(pattern, text_lower) for pattern in humor_triggers)

    # Grok est réservé aux cas explicites de répartie/humour
    return has_keywords or is_expressive


# Marqueurs d'une VRAIE demande d'info/aide → ce n'est PAS du banter, on laisse la
# cascade TEXT/REASONING répondre sérieusement (et on évite de payer Grok pour ça).
_INFO_REQUEST_PATTERNS = [
    r"\bc'?est\s+quoi\b", r"\bc'?est\s+qui\b", r"\bqu'?est-?ce\b",
    r"\baide(?:-moi)?\b", r"\btuto\b", r"\btutoriel\b", r"\bdonne-?moi\b",
    r"\bliste\b", r"\bsource\b", r"\bdéfinis?\b", r"\bdéfinition\b",
    r"\bhttps?://", r"\bwww\.",
    # Interrogatifs d'une vraie question (réponse sérieuse attendue, pas une vanne).
    r"\bcomment\b", r"\bcombien\b", r"\bquand\b", r"\bquels?\b", r"\bquelles?\b",
]


def _is_banter(text):
    """
    True si le message (adressé au bot) est un échange de RÉPARTIE court → on vise Grok.
    False quand mieux vaut une réponse sérieuse (raisonnement / demande d'info / message long).

    Conservateur par dessein : on ne bascule en répartie/Grok (payant) que pour le banter
    court. Tout ce qui ressemble à une vraie question reste sur la cascade TEXT/REASONING.
    """
    if not text:
        # Ping nu / "(le mortel te regarde fixement)" : c'est un moment d'interaction
        # persona pure → répartie bienvenue.
        return True

    text_lower = text.lower()

    # Demande de raisonnement : ici on est PLUS strict que _needs_reasoning (qui exige 2
    # mots-clés) — un SEUL marqueur (« explique », « pourquoi », « comment fonctionne »…)
    # suffit à dire « ce n'est pas une vanne » et à laisser une réponse sérieuse.
    if any(re.search(p, text_lower) for p in ALL_REASONING_PATTERNS):
        return False

    # Demande d'info explicite (incl. interrogatifs) → réponse sérieuse, pas Grok.
    if any(re.search(p, text_lower) for p in _INFO_REQUEST_PATTERNS):
        return False

    # Message long = probablement une vraie requête, pas une vanne.
    if len(text) > 200:
        return False

    # Sinon : banter court adressé → répartie.
    return True


def _needs_reasoning(text):
    """Détermine si un message nécessite du raisonnement profond."""
    if not text:
        return False
    text_lower = text.lower()
    
    # Compter les mots-clés de raisonnement trouvés
    keyword_count = sum(
        1 for pattern in ALL_REASONING_PATTERNS
        if re.search(pattern, text_lower)
    )
    
    # Message long + question = signe de requête complexe
    is_long_question = len(text) > 200 and "?" in text
    
    # Décision conservatrice : 2 mots-clés OU (1 mot-clé + message long)
    return keyword_count >= 2 or (keyword_count >= 1 and is_long_question)


# ═══════════════════════════════════════════
# TÉLÉCHARGEMENT DES MÉDIAS
# ═══════════════════════════════════════════

async def download_media(attachment):
    """
    Télécharge un fichier média depuis Discord de manière sécurisée.
    
    Returns:
        tuple: (data_bytes, mime_type) ou (None, None) si échec
    """
    if not attachment:
        return None, None
    
    mime_type = attachment.content_type or "application/octet-stream"
    
    # Vérification taille avant téléchargement
    if attachment.size and attachment.size > MAX_MEDIA_SIZE:
        logger.warning(f"⚠️ [ROUTER] Média trop grand rejeté: {attachment.size / 1024 / 1024:.1f} MB")
        return None, None
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    logger.warning(f"⚠️ [ROUTER] Échec téléchargement média: HTTP {resp.status}")
                    return None, None
                
                content_length = int(resp.headers.get('content-length', 0))
                if content_length > MAX_MEDIA_SIZE:
                    logger.warning(f"⚠️ [ROUTER] Média content-length trop grand: {content_length / 1024 / 1024:.1f} MB")
                    return None, None
                
                data = await resp.read()
                logger.info(f"✅ [ROUTER] Média téléchargé: {len(data)} bytes ({mime_type})")
                return data, mime_type
    except Exception as e:
        logger.error(f"❌ [ROUTER] Erreur téléchargement: {e}")
        return None, None


async def resolve_media_attachments(message):
    """Renvoie les attachments à router : ceux du message courant s'il y en a,
    sinon ceux du message CITÉ (reply) — permet « @bot t'en penses quoi ? » sous une image.
    Jamais d'exception : en cas d'échec, renvoie message.attachments tel quel."""
    try:
        if message.attachments:
            return message.attachments
        
        ref = message.reference
        if ref and ref.message_id:
            resolved = ref.resolved
            if resolved is not None and hasattr(resolved, "attachments"):
                # Déjà résolu (cache gateway) : ses attachments font foi,
                # pas de fetch HTTP même s'ils sont vides.
                if resolved.attachments:
                    return resolved.attachments
            elif hasattr(message.channel, "fetch_message"):
                msg = await message.channel.fetch_message(ref.message_id)
                if msg and msg.attachments:
                    return msg.attachments
    except Exception:
        pass
    return getattr(message, "attachments", [])
