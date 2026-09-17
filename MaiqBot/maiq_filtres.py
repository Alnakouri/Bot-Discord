# -*- coding: utf-8 -*-
"""Filtres de sortie de M'aiq — ce qui est retire du texte du LLM avant l'envoi.

Sorti de `bot_maiq.py` le 2026-09-17, SANS dependance a `discord` ni a `shared/` :
le bot reste deployable seul et le harnais d'evaluation peut l'importer directement.
Cf. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].
"""
import re

# ── STRIP DIDASCALIES (inline, 0 dépendance partagée) ─────────────────────────
# La persona de M'aiq interdit les didascalies (actions narrées), mais le LLM en
# glisse parfois. Logique curée : ne retire QUE la narration d'action, jamais un
# impératif de dialogue (« souris ! ») et préserve les mots lors d'une simple emphase
# (« *The Times* » -> « The Times »).
_META_NARRATION_LEAD = re.compile(
    r"^\s*(?:l['’]utilisateur|l['’]user|l['’]interlocuteur|l['’]individu|"
    r"le joueur|le membre|le sujet|the user)\b[^.!?…\n]*[.!?…\n]+\s*", re.IGNORECASE)
_RP_REFLEXIVE = (r"penche|redresse|rapproche|approche|recule|avance|retourne|incline|pivote|"
    r"l[eè]ve|baisse|fige|d[eé]tourne|esclaffe|gratte|frotte|[eé]tire|cambre|love|"
    r"tortille|fend|dresse|raidit|crispe|tend|gonfle|tasse|balance")
_RP_PLAIN = (r"claqu\w*|rican\w*|[eé]clat\w*|soupir\w*|grogn\w*|grond\w*|jongl\w*|gesticul\w*|"
    r"tourbillonn\w*|virevolt\w*|applaudi\w*|brandi\w*|sourit|sourire|souriant|"
    r"hurl\w*|riant|sifflot\w*|ronronn\w*|pouffant?|pouffe")
_STAGE_TAIL = r"(?:[\s,]+(?-i:[a-zà-ÿ])[\w'’-]*)*"
_BARE_STAGE = re.compile(
    r"(?:(?<=^)|(?<=[.!?…—])|(?<=\n))\s*"
    r"(?:(?:s['’]|se\s+)(?:" + _RP_REFLEXIVE + r")\w*|(?:" + _RP_PLAIN + r")"
    r"|(?:un|une|le|la|d['’]un)\s+(?:soupir|rire|ricanement|chuchotement|silence|sourire|grognement|souffle|gloussement)\w*)"
    + _STAGE_TAIL, re.IGNORECASE)


def _strip_didascalies(text):
    """Retire les didascalies de roleplay (nues ou entre *astérisques*) sans jamais
    entamer le dialogue. Renvoie le texte nettoyé."""
    import re as _re
    if not text:
        return text
    text = _META_NARRATION_LEAD.sub("", text).strip()
    text = _re.sub(r"<[^>]*\s[^>]*>", "", text)          # didascalies en <chevrons>
    prev = None
    while prev != text:                                   # didascalies nues, en boucle
        prev = text
        text = _BARE_STAGE.sub("", text)
    text = _re.sub(r"^\s*\*[^*]+\*\s*", "", text)          # didascalie en tête *...*
    text = _re.sub(r"(?<=[.!?…])\s*\*[^*]+\s[^*]+\*\s*", " ", text)  # après ponctuation
    text = _re.sub(r"\*([^*]+)\*", r"\1", text)            # reste = simple emphase
    return _re.sub(r"\s{2,}", " ", text).strip()


def filtre_sortie(texte, message_utilisateur=None):
    """Ce que M'aiq retire de TOUTE reponse, sans rien savoir du salon ni de l'historique.

    `message_utilisateur` est facultatif : il existe pour que les six bots exposent
    la MEME porte, appelable par le harnais sans savoir lequel il tient.
    """
    if not texte:
        return texte
    if texte.startswith("M'aiq:"):
        texte = texte.replace("M'aiq:", "", 1).strip()
    texte = re.sub(r"<fact>.*?</fact>", "", texte, flags=re.DOTALL | re.IGNORECASE).strip()
    texte = re.sub(r"<[a-z_-]+>", "", texte, flags=re.IGNORECASE)
    texte = re.sub(r"</[a-z_-]+>", "", texte, flags=re.IGNORECASE).strip()
    texte = _strip_didascalies(texte)
    return texte.strip()
