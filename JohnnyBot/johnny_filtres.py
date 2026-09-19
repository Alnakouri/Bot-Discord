# -*- coding: utf-8 -*-
"""Filtres de sortie de Johnny — ce qui est retire du texte du LLM avant l'envoi.

Sorti de `bot_johnny.py` le 2026-09-17, SANS dependance a `discord` ni a `shared/` :
le bot reste deployable seul et le harnais d'evaluation peut l'importer directement.
Cf. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].
"""
import re

# ── STRIP DIDASCALIES (inline, 0 dépendance partagée) ─────────────────────────
# La persona de Johnny interdit les didascalies (actions narrées), mais le LLM en
# glisse parfois (« *Souffle sur ma clope imaginaire* », « *allume une clope* »).
# Logique curée : ne retire QUE la narration d'action, jamais un impératif de dialogue
# (« souris ! ») et préserve les mots lors d'une simple emphase (« *très* » -> « très »).
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
    # ⚠️ BORNE de longueur, et elle n'est pas cosmetique. Sans elle, `[^*]+` court
    # jusqu'a l'asterisque suivante, ou qu'elle soit. Cas reel du run du 2026-09-17,
    # Alfred, scenario `alfred_maitre` : le modele avait ouvert par `*` et referme 200
    # caracteres plus loin, et la regle a emporte TOUTE la replique — il ne restait que
    # « encore en train de sauver Gotham. ». Une didascalie est courte ; au-dela, c'est
    # de la prose que le modele a mise en italique, et on ne retire alors que les marqueurs.
    text = _re.sub(r"^\s*\*[^*\n]{1,120}\*\s*", "", text)   # didascalie en tête *...*
    text = _re.sub(r"(?<=[.!?…])\s*\*[^*\n]{1,120}\s[^*\n]{1,120}\*\s*", " ", text)  # après ponctuation
    # ⚠️ Le GRAS D'ABORD. Mesure du 2026-09-17 sur le run de reference : 10 reponses sur
    # 102 sortaient ENCORE avec des asterisques apres filtrage, alors que les 92 autres
    # etaient des points fixes — le filtre n'etait pas idempotent. Cause : sur `**gras**`,
    # la substitution ci-dessous ne peut pas demarrer a l'indice 0 (le caractere suivant
    # est une asterisque), elle attaque a l'indice 1, mange `*gras*` et laisse `*gras*`
    # derriere elle. Le gras ne disparaissait pas : il DEVENAIT de l'italique.
    # Sheogorath n'a jamais eu ce defaut (`strip_markdown_emphasis` traite `**` en
    # premier) et c'est le seul des six a sortir 0/17 sur ce meme run.
    # ⚠️ Deux defauts mesures le 2026-09-20, qu'une borne `[^*]+` ne voit NI l'un NI
    # l'autre :
    #  1. l'EMPHASE IMBRIQUEE. Dans `**1 Trouve ton *rose* a toi**`, le contenu du gras
    #     contient une asterisque : `[^*]+` ne peut pas le couvrir, le gras n'est jamais
    #     reconnu, et la passe italique s'accroche de travers. Sur deux spans —
    #     `**a *b* c** et **d *e* f**` — elle les FUSIONNE en `*a b c et d e f*` ;
    #  2. le MARQUEUR ORPHELIN. Les 6 fuites relevees sur 306 sorties brutes finissent
    #     toutes en plein mot (« ... pour **l'emotion », « ... m'a dit : *"C'est ») :
    #     `max_tokens` a coupe la reponse AVANT le marqueur fermant, et l'ouvrant reste
    #     seul. Aucune paire ne le ramasse.
    # D'ou une boucle jusqu'au point fixe qui AUTORISE l'imbrication, puis le retrait de
    # ce qui n'a plus de partenaire. Mesure : 6 fuites sur 306 -> 0, et aucun des textes
    # deja propres n'est modifie.
    prev = None
    while prev != text:
        prev = text
        text = _re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=_re.S)   # gras, imbrication OK
        text = _re.sub(r"\*([^*\n]+)\*", r"\1", text)                # italique
    text = _re.sub(r"\*+", "", text)                                 # orphelin de troncature
    return _re.sub(r"\s{2,}", " ", text).strip()



# ── PLAFOND DE PHRASES (filet déterministe) ───────────────────────────────────
# ⚠️ Johnny rendait 8 à 10 phrases (140 mots) quand sa propre règle en autorise 3, et
# trois interventions sur le MODÈLE n'y avaient rien changé : ministral-14b, gpt-oss et
# flash-lite rendent tous 8-10 phrases à prompt identique — 0.20 d'écart sur un run de
# 10 scénarios, c'est-à-dire du bruit. Ce n'est donc pas un défaut de modèle, et la
# règle de prompt seule ne suffit pas non plus : ce filet-ci ne dépend d'aucun tirage.
#
# Sheogorath a le même depuis le 2026-07 (`sheo_llm.force_short_response`) ; Johnny
# n'en avait pas, et il est le seul des six à déborder. Copié plutôt qu'importé : ce
# module reste SANS dépendance à `shared/` ni à `discord` (cf. l'en-tête du fichier).
#
# ⚠️ Le plafond est celui de SA règle, pas un plus sévère : c'est un filet contre
# l'emballement, pas un outil de mise en forme — la densité est gouvernée par le prompt
# ([[feedback-sheo-longueur-densite]] : seul le remplissage est le problème).
_INVITATION = re.compile(
    r"\b(raconte|racontes?-moi|explique|développe|developpe|continue|détaille|detaille|"
    r"histoire|conte|poème|poeme|chante|décris|decris)\b", re.IGNORECASE)

_EMOJI_FINAL = re.compile(r"(\s*[🌀-🫿☀-➿️]+\s*)$")


def budget_de_phrases(message_utilisateur, plafond=6, plafond_long=10):
    """6 phrases par défaut, 10 si le choom invite explicitement à développer.

    ⚠️ Le cas « raconte » n'est pas cosmétique : sans lui, un filet aveugle punit là où
    la fiche AUTORISE, et c'est exactement ce qui avait fait chuter la note `longueur`
    à 0.50/5 ([[gotcha-le-juge-punissait-la-ou-la-fiche-autorise]]).
    """
    if message_utilisateur and _INVITATION.search(message_utilisateur):
        return plafond_long
    return plafond


def plafonner_les_phrases(texte, max_phrases=6):
    """Tronque au-delà de `max_phrases` VRAIES phrases. Préserve l'emoji final.

    ⚠️ Les « ... » ne comptent pas comme fin de phrase, et une frontière de phrase est
    une ponctuation suivie de N'IMPORTE QUEL blanc : avec un simple espace, les phrases
    séparées par un SAUT DE LIGNE n'étaient pas comptées et le filet ne se déclenchait
    jamais — le défaut live du 2026-07-15 chez Sheogorath.
    """
    if not texte:
        return texte
    fin = ""
    m = _EMOJI_FINAL.search(texte)
    if m:
        fin = " " + m.group(1).strip()
        texte = texte[:m.start()].rstrip()
    _POINTS = chr(0)   # sentinelle : aucun texte de Discord ne la contient
    protege = re.sub(r"\.\.\.+|…", _POINTS, texte)
    phrases = re.split(r"(?<=[.!?])\s+", protege)
    if len(phrases) > max_phrases:
        protege = " ".join(phrases[:max_phrases])
    return (protege.replace(_POINTS, "...") + fin).strip()


def filtre_sortie(texte, message_utilisateur=None):
    """Ce que Johnny retire de TOUTE reponse, sans rien savoir du salon ni de l'historique.

    `message_utilisateur` est facultatif : il existe pour que les six bots exposent
    la MEME porte, appelable par le harnais sans savoir lequel il tient.
    """
    if not texte:
        return texte
    texte = re.sub(r"<fact>.*?</fact>", "", texte, flags=re.DOTALL | re.IGNORECASE).strip()
    texte = re.sub(r"<[a-z_-]+>", "", texte, flags=re.IGNORECASE)
    texte = re.sub(r"</[a-z_-]+>", "", texte, flags=re.IGNORECASE).strip()
    texte = _strip_didascalies(texte)
    texte = plafonner_les_phrases(texte, budget_de_phrases(message_utilisateur))
    return texte.strip()
