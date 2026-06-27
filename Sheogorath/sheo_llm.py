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

    # Espaces multiples
    response_text = re.sub(r"\s+", " ", response_text).strip()
    return response_text


def apply_easter_eggs(response_text, original_message):
    """Applique un easter egg aléatoire (6% chance totale, 1% chacun)."""
    roll = random.random()

    if roll < 0.01:  # 1% - Réponse en miroir
        response_text = f"🪞 {original_message} 🪞"
        logger.info("🎰 [EASTER EGG] Réponse en miroir activée !")

    elif 0.02 <= roll < 0.03:  # 1% - Multilingue absurde
        nonsense_words = ["Wabbajack", "Fromage", "Chaos", "Mania", "Démence", "Jyggalag", "Haskill"]
        languages = ["🇫🇷", "🇬🇧", "🇪🇸", "🇩🇪", "🇮🇹", "🇯🇵", "🇷🇺"]
        response_text = " ".join([random.choice(nonsense_words) for _ in range(5)]) + " " + "".join(random.sample(languages, 3))
        logger.info("🎰 [EASTER EGG] Multilingue absurde activé !")

    elif 0.03 <= roll < 0.04:  # 1% - ALL CAPS EXPLOSION
        response_text = response_text.upper() + " 💥💥💥"
        logger.info("🎰 [EASTER EGG] ALL CAPS EXPLOSION activée !")

    elif 0.04 <= roll < 0.05:  # 1% - Compte-à-rebours absurde
        endings = ["FROMAGE !", "WABBAJACK !", "CHAOS !", "POUF !", "EXPLOSION !", "RIEN !", "TOI !"]
        response_text = f"3... 2... 1... {random.choice(endings)} 🎆"
        logger.info("🎰 [EASTER EGG] Compte-à-rebours absurde activé !")

    elif 0.05 <= roll < 0.06:  # 1% - Une seule lettre répétée
        letters = ["A", "E", "O", "Z", "X", "W", "Q"]
        chosen = random.choice(letters)
        count = random.randint(10, 30)
        response_text = chosen * count + " 📢"
        logger.info(f"🎰 [EASTER EGG] Lettre unique activée ! ({chosen} x{count})")

    return response_text


def force_short_response(response_text, max_sentences=4):
    """Limite la réponse à max_sentences phrases."""
    sentences = re.split(r'(?<=[.!?]) +', response_text)
    if len(sentences) > max_sentences:
        response_text = " ".join(sentences[:max_sentences])
    return response_text


def postprocess_response(response_text, fact_brain, user_id, original_message):
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
    response_text = force_short_response(response_text)

    return response_text
