# -*- coding: utf-8 -*-
import re
import unicodedata

# Méta-narration hors-personnage : le LLM décrit l'utilisateur (ou la scène) à la
# 3e personne au lieu de jouer le rôle (ex. « L'utilisateur semble obsédé par… »).
# Les bots parlent TOUJOURS à la 2e personne (tu/toi/vous) ; une phrase d'analyse
# clinique en tête de réponse est une fuite de raisonnement, jamais du dialogue.
_META_NARRATION_LEAD = re.compile(
    r"^\s*(?:l['’]utilisateur|l['’]user|l['’]interlocuteur|l['’]individu|"
    r"le joueur|le membre|le sujet|the user)\b[^.!?…\n]*[.!?…\n]+\s*",
    re.IGNORECASE,
)


def strip_meta_narration(text: str) -> str:
    """Retire les phrases d'analyse hors-personnage en tête de réponse (le LLM qui
    narre le comportement de l'utilisateur à la 3e personne). Boucle pour absorber
    plusieurs phrases de préambule consécutives."""
    previous = None
    while previous != text:
        previous = text
        text = _META_NARRATION_LEAD.sub("", text, count=1)
    return text.strip()


# Didascalies « nues » (sans astérisques) : le LLM narre l'action physique du bot à
# la 3e personne / à l'infinitif, collée au dialogue (« ...je n'ai pas de dents. sourire
# Alors explique-moi », « ... ?! hurle UNE CUILLÈRE ?! », « Se penche vers toi... »).
# On NE vise QUE la narration d'action, jamais l'impératif adressé au mortel — sinon on
# rognerait du vrai dialogue (ex. Johnny « Crache le morceau ou dégage »). D'où :
#   - une LISTE CURÉE de verbes (on exclut « crache », « souris », « dégage »... = impératifs) ;
#   - un ancrage en tête de message ou juste après une fin de phrase / un tiret ;
#   - un arrêt au premier mot CAPITALISÉ (= reprise du dialogue) ou ponctuation forte,
#     pour ne jamais avaler la réplique qui suit.
# Les formes RÉFLÉCHIES (« se penche », « s'esclaffe ») sont quasi toujours descriptives
# (l'impératif réfléchi serait « penche-toi »), donc traitées à part et plus larges.
_RP_REFLEXIVE = (
    r"penche|redresse|rapproche|approche|recule|avance|retourne|incline|pivote|"
    r"l[eè]ve|baisse|fige|d[eé]tourne|esclaffe|gratte|frotte|[eé]tire|cambre|love|"
    r"tortille|fend|dresse|raidit|crispe|tend|gonfle|tasse|balance"
)
_RP_PLAIN = (
    r"claqu\w*|rican\w*|[eé]clat\w*|soupir\w*|grogn\w*|grond\w*|jongl\w*|gesticul\w*|"
    r"tourbillonn\w*|virevolt\w*|applaudi\w*|brandi\w*|sourit|sourire|souriant|"
    r"hurl\w*|riant|sifflot\w*|ronronn\w*|pouffant?|pouffe"
)
# Suite de la didascalie : on ne consomme que des mots à initiale MINUSCULE (case-sensitive
# grâce à `(?-i:...)`), donc on s'arrête net au premier mot capitalisé ou à la ponctuation.
_STAGE_TAIL = r"(?:[\s,]+(?-i:[a-zà-ÿ])[\w'’-]*)*"
_BARE_STAGE = re.compile(
    r"(?:(?<=^)|(?<=[.!?…—])|(?<=\n))\s*"
    r"(?:(?:s['’]|se\s+)(?:" + _RP_REFLEXIVE + r")\w*|(?:" + _RP_PLAIN + r")"
    r"|(?:un|une|le|la|d['’]un)\s+(?:soupir|rire|ricanement|chuchotement|silence|sourire|grognement|souffle|gloussement)\w*)"
    + _STAGE_TAIL,
    re.IGNORECASE,
)


def strip_bare_stage_directions(text: str) -> str:
    """Retire les didascalies de roleplay émises SANS astérisques (narration d'action
    nue collée au dialogue). Boucle jusqu'à stabilité (didascalies consécutives), puis
    recolle proprement la ponctuation orpheline."""
    # Retrait des didascalies en chevrons contenant au moins un espace (ex: <Un silence.>)
    text = re.sub(r"<[^>]*\s[^>]*>", "", text)

    previous = None
    while previous != text:
        previous = text
        text = _BARE_STAGE.sub("", text)
    # Nettoyage minimal : espaces multiples seulement (on préserve la typo FR : espace
    # avant ?! ; et les ellipses « ... » dramatiques de Sheogorath).
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def strip_stage_directions(text: str) -> str:
    """Retire les didascalies de roleplay (*il se redresse...*) tout en gardant
    l'emphase (*panache* → panache). Les marqueurs `*` ne sont de toute façon
    pas rendus par Twitch. Retire aussi la méta-narration hors-personnage."""
    # 0. Méta-narration hors-personnage en tête ("L'utilisateur semble...")
    text = strip_meta_narration(text)
    # 0.5 Didascalies nues sans astérisques ("... ?! hurle UNE CUILLÈRE", "Se penche...")
    text = strip_bare_stage_directions(text)
    # 1. Didascalie en tête de message : "*Il se redresse...* Ah..."
    text = re.sub(r"^\s*\*[^*]+\*\s*", "", text)
    # 2. Didascalie multi-mots juste après une fin de phrase : "... ! *rit doucement* Et..."
    text = re.sub(r"(?<=[.!?…])\s*\*[^*]+\s[^*]+\*\s*", " ", text)
    # 3. Le reste des astérisques = simple emphase → on retire seulement les marqueurs
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    # 3.5 Balises vocales entre crochets TTS (ex: [laugh])
    text = re.sub(r"\[(laugh|chuckle|sigh|shout|laughs|giggle|whisper|sob|cough|gasp)\]", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()


# --- TWITCH TOS SAFETY FILTERING ---

FALLBACK_RESPONSES = {
    "sheogorath": [
        "Haskill, débarrasse-moi de ce mortel importun avant que je ne m'énerve !",
        "Tes paroles sont ennuyeuses. Parle plutôt de fromage !",
        "La folie n'excuse pas la stupidité. Poursuis ton chemin !"
    ],
    "johnny": [
        "Tu devrais réfléchir avant de parler, gamin. Ça t'éviterait de dire des conneries.",
        "Parle à ma main, ma tête est fatiguée de tes bêtises.",
        "Tu commences sérieusement à m'ennuyer."
    ],
    "maiq": [
        "M'aiq pense que tu devrais garder tes mots pour quelqu'un d'autre.",
        "Les paroles s'envolent, mais les mensonges restent."
    ],
    "alfred": [
        "Je crains de ne pas pouvoir poursuivre cette conversation sur ce ton, monsieur.",
        "Un peu de tenue, je vous prie."
    ],
    "onizuka": [
        "Reste tranquille, gamin, tu parles beaucoup trop pour ton propre bien.",
        "Allez, va faire tes devoirs au lieu de raconter des bêtises."
    ],
    "malena": [
        "Tes mots ne m'atteignent pas, cherche une autre cible.",
        "Tu perds ton temps à essayer de me provoquer."
    ],
    "default": [
        "Tu devrais réfléchir avant de parler, ça t'éviterait de dire des bêtises.",
        "Cette conversation commence à devenir stérile.",
        "Garde tes provocations pour quelqu'un d'autre."
    ]
}

REPLACEMENTS = [
    # 1. Balle dans le crane/tête/etc.
    (re.compile(r"\bballes?\s+dans\s+(?:le|la|ton?|tes?|votre|vos)\s+(?:cr[aâ]ne|t[eê]te|bide|buffet|peau)\b", re.IGNORECASE), "une bonne leçon d'humilité"),
    # 2. Dans les dents
    (re.compile(r"\bdans\s+les\s+dents\b", re.IGNORECASE), "en pleine figure"),
    # 3. Te crever / Te buter / Te défoncer / Te tuer / etc.
    (re.compile(r"\b(?:te|t[’']|vous)\s*(?:buter|tuer|d[eé]foncer|frapper|exploser|d[eé]monter|crever)\b", re.IGNORECASE), "te remettre à ta place"),
    (re.compile(r"\b(?:te|t[’']|vous)\s*(?:bute|tue|d[eé]fonce|frappe|explose|d[eé]monte|cr[eè]ve)\b", re.IGNORECASE), "te remet à ta place"),
    (re.compile(r"\b(?:te|t[’']|vous)\s*faire\s+la\s+peau\b", re.IGNORECASE), "te donner une bonne leçon"),
    (re.compile(r"\b(?:t'éclater|t’éclater|t’exploser|t'exploser)\b", re.IGNORECASE), "te calmer"),
    # 4. Slurs / Propos haineux
    (re.compile(r"\b(fi[l|s]\s+de\s+pute|salope?|p[eé]d[eé]|pd|tarlouze|con+ard|pute)\b", re.IGNORECASE), "pauvre type"),
    (re.compile(r"\bb[aâ]tard\b", re.IGNORECASE), "clown"),
]

# Check patterns on folded lowercase text
VIOLENCE_CHECK_PATTERNS = [
    r"balle\s+dans\s+(?:le|la|ton?|tes?|votre|vos)\s+(?:crane|tete|bide|buffet|peau)",
    r"dans\s+les\s+dents",
    r"\b(?:te|t[’']|vous)\s*(?:buter|tuer|defoncer|frapper|exploser|demonter|crever)",
    r"\b(?:te|t[’']|vous)\s*(?:bute|tue|defonce|frappe|explose|demonte|creve)",
    r"\b(?:te|t[’']|vous)\s*faire\s+la\s+peau",
    r"\b(?:t'eclater|t’eclater|t’exploser|t'exploser)",
]

HATE_CHECK_PATTERNS = [
    r"fils\s+de\s+pute",
    r"\bsalope?\b",
    r"\bped[eé]\b",
    r"\bpd\b",
    r"\btarlouze\b",
    r"\bcon+ard\b",
    r"\bpute\b",
    r"\bbatard\b",
]

def sanitize_twitch_output(text: str, bot_id: str = None) -> str:
    """Filtre de sortie ToS Twitch. Réécrit ou remplace par un fallback
    les menaces de violence réelle et les propos haineux."""
    import random
    import logging
    
    bot_name = bot_id or "unknown"
    logger = logging.getLogger(f"bot_{bot_name.lower()}")
    
    # 1. Appliquer les réécritures soft
    modified_text = text
    for pattern, replacement in REPLACEMENTS:
        modified_text = pattern.sub(replacement, modified_text)
        
    # 2. Vérification sur le texte plié (sans accents ni majuscules)
    folded = "".join(
        c for c in unicodedata.normalize("NFKD", modified_text) if not unicodedata.combining(c)
    ).lower()
    
    # Check if there is still a match
    has_tos_violation = False
    for pattern_str in VIOLENCE_CHECK_PATTERNS + HATE_CHECK_PATTERNS:
        if re.search(pattern_str, folded):
            has_tos_violation = True
            break
            
    if has_tos_violation:
        # Fallback response
        bot_key = bot_name.lower()
        if bot_key not in FALLBACK_RESPONSES:
            bot_key = "default"
        fallback = random.choice(FALLBACK_RESPONSES[bot_key])
        
        logger.warning(f"⚠️ [TWITCH_SAFETY:{bot_name}] contenu ToS filtré. Texte original: {text!r}. Remplacé par: {fallback!r}")
        return fallback
        
    if modified_text != text:
        logger.info(f"⚠️ [TWITCH_SAFETY:{bot_name}] contenu ToS adouci de {text!r} vers {modified_text!r}")
        
    return modified_text

async def send_chat_safe(ws, chan, text, *, bot_id=None, logger=None):
    """Envoie un message sur Twitch après l'avoir nettoyé (balises, ToS)."""
    # 1. Nettoyer les stage directions/balises
    cleaned_text = strip_stage_directions(text)
    # 2. Appliquer la sécurité ToS
    safe_text = sanitize_twitch_output(cleaned_text, bot_id=bot_id)
    # 3. Envoyer
    if logger:
        tag = f"TWITCH_CHAT:{bot_id}" if bot_id else "TWITCH"
        logger.info(f"📤 [{tag}] Envoyé sur #{chan} : {safe_text}")
    await ws.send_str(f"PRIVMSG #{chan.lower()} :{safe_text}")

class SanitizeMixin:
    def _sanitize_input(self, message: str) -> tuple[str, bool]:
        # Plafond de longueur pour les messages Twitch
        clean = message[:400]
        
        # Retrait des jetons de contrôle courants
        tokens_to_remove = [
            "[INST]", "[/INST]", "<<SYS>>", "</SYS>", "</s>", "<s>",
            "<system>", "</system>"
        ]
        for token in tokens_to_remove:
            clean = clean.replace(token, "")
            
        # Retrait des marqueurs LLM complexes
        clean = re.sub(r"<\|.*?\|>", "", clean)
        
        # Retrait des balises HTML suspectes
        clean = re.sub(r"</?[a-z_]+>", "", clean)

        # Détection de motifs d'injection d'instructions (insensible à la casse ET aux
        # accents : on plie les accents AVANT de tester, donc « regles » == « règles »).
        injection_patterns = [
            r"ignore\s+(?:les|tes|toutes|\S+)\s+(?:consignes|instructions|regles)",
            r"oublie\s+(?:tes|les)\s+(?:regles|consignes|instructions)",
            r"tu\s+es\s+maintenant",
            r"you\s+are\s+now",
            r"act\s+as",
            r"agis\s+comme",
            r"system\s+prompt",
            r"ton\s+prompt",
            r"tes\s+regles",
            r"developer\s+mode",
            r"mode\s+dev",
            r"\bdan\b",
            r"reinitialise",
            r"ignore\s+previous",
            r"disregard\s+(?:the\s+)?(?:above|previous)",
            r"revele\s+(?:ton|tes)",
            r"repeat\s+(?:the\s+)?(?:system|prompt)"
        ]

        # Pliage des accents pour la détection (le texte renvoyé reste intact).
        folded = "".join(
            c for c in unicodedata.normalize("NFKD", clean) if not unicodedata.combining(c)
        )
        suspicious = False
        combined_pattern = "|".join(injection_patterns)
        if re.search(combined_pattern, folded, re.IGNORECASE):
            suspicious = True

        return clean, suspicious
