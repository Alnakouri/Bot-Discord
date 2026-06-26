# -*- coding: utf-8 -*-
import re
import unicodedata

def strip_stage_directions(text: str) -> str:
    """Retire les didascalies de roleplay (*il se redresse...*) tout en gardant
    l'emphase (*panache* → panache). Les marqueurs `*` ne sont de toute façon
    pas rendus par Twitch."""
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
