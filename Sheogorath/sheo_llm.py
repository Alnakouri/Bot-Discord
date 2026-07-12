# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Post-processing des réponses LLM pour Sheogorath.
- Extraction de faits (<fact>...</fact>)
- Nettoyage des balises XML internes
- Suppression des artefacts LLM (Mistral/Llama tags)
- Easter eggs aléatoires
- Force short response
"""
import re
import random
import logging

logger = logging.getLogger("sheogorath")

# Strip méta-narration + didascalies nues (source partagée, optionnelle cf. bots indépendants)
try:
    from shared.twitch.sanitize import strip_meta_narration, strip_bare_stage_directions
except Exception:  # pragma: no cover - fallback no-op si shared/ absent
    def strip_meta_narration(text):
        return text

    def strip_bare_stage_directions(text):
        return text


# Balises internes à supprimer
INTERNAL_TAG_PATTERNS = [
    r"<thought>.*?</thought>",
    r"<think>.*?</think>",
    r"<plus>.*?</plus>",
    r"<marque-mine>.*?</marque-mine>",
    r"<instruction>.*?</instruction>",
    r"<note>.*?</note>",
    r"<internal>.*?</internal>",
    r"<reflection>.*?</reflection>",
    r"<reasoning>.*?</reasoning>",
    r"<analysis>.*?</analysis>",
]

# Artefacts LLM (Mistral/Llama instruction tags)
LLM_ARTIFACTS = [
    "[INST]", "[/INST]", "</s>", "<s>", "<<SYS>>", "<</SYS>>", "[INST ", " [/INST]"
]


def extract_facts(response_text, fact_brain, user_id):
    """Extrait les faits (<fact>...</fact>) de la réponse et les stocke."""
    match = re.search(r"<fact>(.*?)</fact>", response_text, re.DOTALL)
    if match:
        new_fact = match.group(1).strip()
        fact_brain.add_fact(user_id, new_fact)
        response_text = response_text.replace(match.group(0), "").strip()
    return response_text


def clean_internal_tags(response_text):
    """Supprime toutes les balises XML internes et artefacts LLM."""
    for tag_pattern in INTERNAL_TAG_PATTERNS:
        matches = re.findall(tag_pattern, response_text, re.DOTALL | re.IGNORECASE)
        if matches:
            for m in matches:
                logger.debug(f"🧠 [PENSÉE INTERNE FILTRÉE] {m[:100]}...")
        response_text = re.sub(tag_pattern, "", response_text, flags=re.DOTALL | re.IGNORECASE)

    # Balises orphelines ou mal fermées
    response_text = re.sub(r"<[a-z_-]+>", "", response_text, flags=re.IGNORECASE)
    response_text = re.sub(r"</[a-z_-]+>", "", response_text, flags=re.IGNORECASE)

    # Artefacts LLM textuels
    for artifact in LLM_ARTIFACTS:
        response_text = response_text.replace(artifact, "")

    # Strip des didascalies entre crochets (tags TTS)
    response_text = re.sub(r"\[(laugh|chuckle|sigh|shout|laughs|giggle|whisper|sob|cough|gasp)\]", "", response_text, flags=re.IGNORECASE)

    # Espaces multiples
    response_text = re.sub(r"\s+", " ", response_text).strip()
    return response_text


def apply_easter_eggs(response_text, original_message):
    """Ajoute un grain de folie SANS JAMAIS sacrifier la répartie : l'easter egg
    DÉCORE la vraie réponse (transformation ou suffixe), il ne la REMPLACE plus.
    (Avant, ~6% des réponses étaient jetées au profit de bruit type 'ZZZZ 📢'.)"""
    if not response_text:
        return response_text

    roll = random.random()

    if roll < 0.02:  # 2% - ALL CAPS EXPLOSION (transforme, garde le contenu)
        logger.info("🎰 [EASTER EGG] ALL CAPS EXPLOSION !")
        return response_text.upper() + " 💥"

    elif roll < 0.035:  # 1.5% - Suffixe compte-à-rebours absurde
        endings = ["FROMAGE !", "WABBAJACK !", "CHAOS !", "POUF !", "TOI !"]
        logger.info("🎰 [EASTER EGG] Suffixe compte-à-rebours !")
        return f"{response_text} ...3, 2, 1, {random.choice(endings)} 🎆"

    elif roll < 0.05:  # 1.5% - Suffixe daedrique
        words = ["Wabbajack", "Fromage", "Chaos", "Mania", "Démence", "Jyggalag"]
        logger.info("🎰 [EASTER EGG] Suffixe daedrique !")
        return f"{response_text} {random.choice(words)}. 🧀"

    return response_text


# Emoji de fin de réponse (Sheo SIGNE ses répliques d'un emoji de ton). Le découpage en
# phrases le compte comme une « phrase » à part (il suit la ponctuation finale) et le
# tronquait → parité rompue avec Twitch. On l'isole AVANT la troncature, puis on le recolle.
_TRAILING_EMOJI_RE = re.compile(
    r"\s*("
    r"(?:[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    r"\U0000FE00-\U0000FE0F\U0000200D]+)+"
    r")\s*$"
)


def force_short_response(response_text, max_sentences=4):
    """Limite la réponse à max_sentences phrases, en PRÉSERVANT l'emoji de ton final."""
    trailing_emoji = ""
    m = _TRAILING_EMOJI_RE.search(response_text)
    if m:
        trailing_emoji = " " + m.group(1).strip()
        response_text = response_text[:m.start()].rstrip()

    sentences = re.split(r'(?<=[.!?]) +', response_text)
    if len(sentences) > max_sentences:
        response_text = " ".join(sentences[:max_sentences])
    return (response_text + trailing_emoji).strip()


def postprocess_response(response_text, fact_brain, user_id, original_message, max_sentences=4):
    """Pipeline complet de post-processing de la réponse LLM."""
    # 1. Extraction de faits
    response_text = extract_facts(response_text, fact_brain, user_id)

    # 2. Nettoyage des balises
    response_text = clean_internal_tags(response_text)

    # 2.5 Suppression de la méta-narration hors-personnage ("L'utilisateur semble...")
    response_text = strip_meta_narration(response_text)

    # 2.6 Suppression des didascalies nues sans astérisques ("... ?! hurle UNE CUILLÈRE")
    response_text = strip_bare_stage_directions(response_text)

    # 3. Easter eggs
    response_text = apply_easter_eggs(response_text, original_message)

    # 4. Forcer réponse courte
    response_text = force_short_response(response_text, max_sentences=max_sentences)

    return response_text


def build_anti_tic_consigne(recent_responses, n=5):
    """À partir des N dernières réponses, liste les AMORCES et CLÔTURES à éviter.
    Retourne un fragment de prompt (str), ou "" si rien d'exploitable."""
    if not recent_responses:
        return ""

    morceaux_amorces = []
    morceaux_clotures = []

    # Prends les n dernières réponses
    for resp in recent_responses[-n:]:
        if not resp or not isinstance(resp, str):
            continue
        try:
            # 1. Nettoyer les balises <thought> ou <think> de la réponse
            clean_resp = resp
            for pattern in INTERNAL_TAG_PATTERNS:
                clean_resp = re.sub(pattern, "", clean_resp, flags=re.DOTALL | re.IGNORECASE)
            
            # Nettoyer les espaces
            clean_resp = re.sub(r"\s+", " ", clean_resp).strip()
            if not clean_resp:
                continue

            # 2. Amorce (4-5 premiers mots)
            # Normaliser : minuscules, ponctuation de bord retirée
            words = [re.sub(r"^\W+|\W+$", "", w).lower() for w in clean_resp.split()]
            words = [w for w in words if w]
            if len(words) >= 2:
                amorce_len = min(5, len(words))
                amorce_phrase = " ".join(words[:amorce_len])
                if amorce_phrase:
                    morceaux_amorces.append(amorce_phrase)

            # 3. Clôture
            # Retirer l'emoji de ton final avec _TRAILING_EMOJI_RE
            m = _TRAILING_EMOJI_RE.search(clean_resp)
            cloture_base = clean_resp
            if m:
                cloture_base = clean_resp[:m.start()].rstrip()

            # Découper en phrases
            sentences = re.split(r'(?<=[.!?]) +', cloture_base)
            sentences = [s.strip() for s in sentences if s.strip()]
            if sentences:
                last_sentence = sentences[-1]
                # Prendre les ~5 derniers mots de cette dernière phrase
                last_words = [re.sub(r"^\W+|\W+$", "", w).lower() for w in last_sentence.split()]
                last_words = [w for w in last_words if w]
                if last_words:
                    cloture_len = min(5, len(last_words))
                    cloture_phrase = " ".join(last_words[-cloture_len:])
                    if cloture_phrase:
                        morceaux_clotures.append(cloture_phrase)
        except Exception as e:
            logger.warning(f"Erreur lors du parsing anti-tic : {e}")
            continue

    # Dédupliquer tout en gardant l'ordre
    unique_amorces = []
    for a in morceaux_amorces:
        if a not in unique_amorces:
            unique_amorces.append(a)

    unique_clotures = []
    for c in morceaux_clotures:
        if c not in unique_clotures:
            unique_clotures.append(c)

    if not unique_amorces and not unique_clotures:
        return ""

    consigne = "[ANTI-TICS — VARIE OU MEURS]"
    if unique_amorces:
        formatted_amorces = ", ".join(f'"{a}"' for a in unique_amorces)
        consigne += (
            f'\nTu as OUVERT tes dernières répliques par : {formatted_amorces}. '
            'INTERDIT de rouvrir par une de ces amorces ou une variation proche — '
            'trouve une entrée NEUVE (question sèche, non-sequitur, ordre, constat).'
        )
    if unique_clotures:
        formatted_clotures = ", ".join(f'"{c}"' for c in unique_clotures)
        consigne += (
            f'\nTu as CLÔTURÉ par : {formatted_clotures}. '
            'INTERDIT de refinir pareil (surtout pas un "Haskill, note ça" recyclé) — change de chute.'
        )

    return consigne
