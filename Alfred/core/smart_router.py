# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/smart_router.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

"""
Smart Router — Routage intelligent des modèles IA.
Économise le quota Gemini en ne l'utilisant que pour vision, audio et raisonnement.
Tout le texte courant est routé vers Groq/OpenRouter/Mistral (gratuits ou pas chers).
"""

import re
import logging
import aiohttp

try:
    from core.models import GEMINI_FLASH, GEMINI_FLASH_LITE, GROQ_FAST, MISTRAL_MAIN, cascade_persona
except ImportError:  # bot déployé seul, sans shared/
    GEMINI_FLASH      = "gemini-3.5-flash"
    GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"
    GROQ_FAST         = "openai/gpt-oss-120b"
    # mistral-large est hors abonnement (403 tier_not_allowed, 2026-08-30) : ce repli
    # le ressuscitait des qu'un bot tournait sans shared/. Cf. MISTRAL_HORS_TIER.
    MISTRAL_MAIN      = "mistral-small-latest"

    def cascade_persona(_bot_id_ou_label):
        """Repli : sans models.py, pas de cascade par persona — on garde la generique.

        Sans ce repli, la branche except laisserait `cascade_persona` INDEFINI et
        get_model_cascade() leverait un NameError a la premiere reponse : le mode de
        panne « bot vivant mais muet » deja vu deux fois.
        """
        return None

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
    "image/heic", "image/heif", "image/avif",
]

IMAGE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
    ".heic", ".heif", ".avif",
)

# Taille max des médias (sécurité)
MAX_MEDIA_SIZE = 10 * 1024 * 1024  # 10 MB


# ═══════════════════════════════════════════
# TYPES DE REQUÊTES
# ═══════════════════════════════════════════

class RequestType:
    """Ce qu'EST le message — pas le modèle qui le traitera.

    ⚠️ La correspondance type → modèles vit dans `get_model_cascade`, seule autorité.
    Ne recopier aucun identifiant de modèle ici : ces commentaires ont nommé « Grok »
    et « Gemini 2.0 » des mois après leur retrait du code, et rien ne le signalait.
    """
    TEXT = "text"           # conversation ordinaire → cascade de la persona
    REPARTEE = "repartee"   # banter adressé → MÊME cascade que TEXT (voir get_model_cascade)
    IMAGE = "image"         # pièce jointe image → cascade vision
    AUDIO = "audio"         # pièce jointe audio → cascade vision/audio
    REASONING = "reasoning" # demande qui exige du raisonnement → cascade dédiée


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


def classify_request(message_text, attachments=None, *, addressed: bool = False, silent: bool = False):
    """
    Classifie un message Discord pour déterminer le modèle optimal.

    Args:
        message_text: Le texte du message
        attachments: Liste des pièces jointes Discord (message.attachments)
        addressed: True si le bot est DIRECTEMENT interpellé (mention / reply / nom
            prononcé / continuité de conversation). Défaut False → comportement d'origine
            inchangé pour tout appelant qui ne passe pas ce signal (rétro-compatible).
            Quand True et que le message est du banter court (ni raisonnement, ni demande
            d'info), le message est classé REPARTEE.
            ⚠️ Depuis la cascade par persona, REPARTEE et TEXT servent les MÊMES modèles :
            l'étiquette ne change plus le routage. Elle reste un signal de classification
            que l'appelant peut exploiter (ton, longueur), rien de plus.
        silent: N'émet aucun log. Réservé à la détection PRÉCOCE des bots, qui appelle
            `classify_request` uniquement pour savoir s'il faut répondre : sans lui, une
            ligne `[ROUTER]` apparaît DEUX fois par message et laisse croire à deux
            routages. Le routage réel, lui, doit rester bruyant.

    Returns:
        dict avec type, model, reason, has_image, has_audio, 
        image_attachment, audio_attachment
    """
    result = {
        "type": RequestType.TEXT,
        "model": None,
        "reason": "Texte simple",
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
                if not silent: logger.info(f"[ROUTER] {result['reason']}")
                return result

            # Image détectée
            if ct.startswith("image/") or any(ct.startswith(mime) for mime in IMAGE_MIME_TYPES) or filename.endswith(IMAGE_EXTENSIONS):
                result["type"] = RequestType.IMAGE
                result["model"] = GEMINI_FLASH
                result["reason"] = f"🖼️ Image ({ct}) → Gemini Vision"
                result["has_image"] = True
                result["image_attachment"] = att
                if not silent: logger.info(f"[ROUTER] {result['reason']}")
                return result  # Image est prioritaire
            
            # Audio standard détecté
            if any(ct.startswith(mime) for mime in AUDIO_MIME_TYPES):
                result["type"] = RequestType.AUDIO
                result["model"] = GEMINI_FLASH
                result["reason"] = f"🎵 Fichier Audio ({ct}) → Gemini Audio"
                result["has_audio"] = True
                result["audio_attachment"] = att
                if not silent: logger.info(f"[ROUTER] {result['reason']}")
                return result
    
    # 2. Vérifier si raisonnement complexe requis
    if _needs_reasoning(message_text):
        result["type"] = RequestType.REASONING
        result["model"] = GEMINI_FLASH
        result["reason"] = "🧠 Raisonnement complexe"
        if not silent: logger.info(f"[ROUTER] {result['reason']}")
        return result

    # 3. Vérifier si humour / répartie requis (mots-clés explicites)
    if _needs_humor(message_text):
        result["type"] = RequestType.REPARTEE
        result["reason"] = "🎭 Humour / Répartie détecté"
        if not silent: logger.info(f"[ROUTER] {result['reason']}")
        return result

    # 3b. Banter ADRESSÉ : le bot est directement interpellé (mention/reply/nom/continuité)
    # et ce n'est ni du raisonnement ni une demande d'info.
    # ⚠️ Cette branche visait à l'origine un modèle d'humour PAYANT, d'où le garde sur
    # `addressed` (maîtrise du coût). Ce modèle n'existe plus et REPARTEE mène désormais
    # à la cascade de la persona, comme TEXT : il n'y a plus de coût à maîtriser ici.
    # Le garde est conservé pour la PRÉCISION du classement, pas pour la dépense.
    if addressed and _is_banter(message_text):
        result["type"] = RequestType.REPARTEE
        result["reason"] = "🎭 Banter adressé"
        if not silent: logger.info(f"[ROUTER] {result['reason']}")
        return result

    # 4. Texte simple → cascade de la persona (voir get_model_cascade)
    if not silent: logger.debug("[ROUTER] 💬 Texte simple")
    return result


def get_model_cascade(routing_type, bot_id=None):
    """
    Retourne la liste ordonnée (client_type, model_name) pour un type donné.

    `bot_id` (ou son étiquette d'affichage) sélectionne la cascade PROPRE À LA PERSONA
    pour le texte et la répartie — voir CASCADES_PERSONA dans models.py, dont le choix
    vient d'une sonde réelle. Sans lui, on retombe sur la cascade générique historique.

    Vision et raisonnement ne sont PAS personnalisés : là c'est la capacité du modèle
    qui commande, pas le ton.
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
    
    # Texte et répartie : c'est là que la « voix » du bot se joue.
    if routing_type in (RequestType.TEXT, RequestType.REPARTEE) or routing_type not in (
            RequestType.REASONING, RequestType.IMAGE, RequestType.AUDIO):
        propre = cascade_persona(bot_id)
        if propre:
            return propre

    # ⚠️ Il y avait ici une cascade RÉPARTIE distincte, dont le dernier échelon était
    # nemotron:free. Elle est supprimée, pour deux raisons qui tiennent chacune seule :
    #   — nemotron est ÉCARTÉ (fuite de raisonnement : il recopie sa pensée dans
    #     `content`, cf. `_fuite_de_raisonnement` dans llm_cascade) ;
    #   — son commentaire vantait « Mistral Large en tête », modèle hors abonnement
    #     depuis le 2026-08-30 : la cascade décrivait un monde qui n'existait plus.
    # La répartie tombe donc sur la cascade TEXT ci-dessous, qui mélange déjà trois
    # fournisseurs à quotas indépendants et n'utilise que des modèles admis.
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

    # On ne classe en répartie que sur des marqueurs explicites.
    return has_keywords or is_expressive


# Marqueurs d'une VRAIE demande d'info/aide → ce n'est PAS du banter, on laisse la
# cascade TEXT/REASONING répondre sérieusement.
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
    True si le message (adressé au bot) est un échange de RÉPARTIE court.
    False quand mieux vaut une réponse sérieuse (raisonnement / demande d'info / message long).

    Conservateur par dessein : on ne bascule en répartie que pour le banter court.
    Tout ce qui ressemble à une vraie question reste classé TEXT/REASONING.
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

    # Demande d'info explicite (incl. interrogatifs) → réponse sérieuse, pas du banter.
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
