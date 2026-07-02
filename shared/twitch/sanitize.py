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
    return re.sub(r"\s{2,}", " ", text).strip()

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
