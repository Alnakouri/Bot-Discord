# -*- coding: utf-8 -*-
"""Filtres de sortie de Sugar — ce qui est retire du texte du LLM avant l'envoi.

Sorti de `bot_sugar.py` le 2026-09-17, SANS changement de logique. La raison n'est pas
l'esthetique : `bot_sugar.py` importe `discord`, donc le harnais d'evaluation ne pouvait
pas l'importer, donc il notait la sortie BRUTE du modele — un texte que l'utilisateur ne
voit jamais. Cf. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].

Aucune dependance a `shared/` : le bot reste deployable seul.
"""
import re

# ── STRIP DIDASCALIES (inline, 0 dépendance partagée) ─────────────────────────
# La persona de Sugar interdit les didascalies (actions narrées), mais le LLM en
# glisse parfois (« *soupir sucré* », « soupir sucré Les larmes… »). Logique curée
# (reprise de shared/twitch/sanitize.py, copiée ici pour garder le bot autonome) :
# ne retire QUE la narration d'action, jamais un impératif de dialogue
# (« souris ! », « penche-toi ») — le tail ne consomme que des mots à initiale
# minuscule et s'arrête au premier mot capitalisé (= reprise du dialogue).
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
    text = _re.sub(r"\*\*([^*]+)\*\*", r"\1", text)        # gras
    text = _re.sub(r"\*([^*]+)\*", r"\1", text)            # reste = simple emphase
    return _re.sub(r"\s{2,}", " ", text).strip()

# Petits noms sucrés (pour reconnaître un VOCATIF en tête, pas « Mon avis, … »).
_SWEET_NAMES = (
    r"sucre|orge|praline|caramel|chamallow|berlingot|guimauve|nougat|nougatine|dragée|dragee|"
    r"cœur|coeur|fondant|bonbon|sucette|miel|macaron|éclair|eclair|biscuit|gâteau|gateau|"
    r"calisson|loukoum|réglisse|reglisse|marshmallow|cupcake|sirop|sucré|sucree|sucrée|"
    r"friandise|douceur|nonette|pralin|meringue|barbe\s+à\s+papa|petit\s+sucre"
)
# Vocatif sucré en ouverture : « Oh, mon berlingot, … », « Ma praline, … », « Eh, mon petit cœur fondant — … »
_LEAD_VOCATIVE = re.compile(
    r"^\s*(?:oh|eh|ah|hé|he|hey|coucou|alors)?\s*[,!.…\-–—]*\s*"
    r"(?:mon|ma|mes)\s+"
    r"(?:(?:petit|petite|gros|grosse|tendre|doux|douce|cher|chère|chere)\s+){0,2}"
    r"(?:" + _SWEET_NAMES + r")"
    r"(?:\s+(?:d['’]|de\s+|au\s+|à\s+la\s+)?[\wàâäéèêëïîôöùûüç'’-]+){0,2}"
    r"\s*[,–—-]+\s*",
    re.IGNORECASE)

def _strip_lead_vocative(text):
    """Retire un vocatif sucré en TÊTE (« Oh, mon berlingot, … »), tic récurrent de Sugar.
    Ne coupe que si un vrai petit nom sucré suit ET qu'il reste une phrase substantielle
    derrière (sinon la réplique tenait entièrement dans le petit nom → on garde)."""
    if not text:
        return text
    m = _LEAD_VOCATIVE.match(text)
    if not m:
        return text
    rest = text[m.end():].lstrip()
    if len(rest) < 12:
        return text
    return rest[0].upper() + rest[1:]

# ── BUDGET DE MOTS (filet déterministe) ──────────────────────────────────────
# ⚠️ Sa fiche dit « 2 phrases GRAND MAXIMUM, idéalement UNE seule punchline. Vise
# ~30 mots, JAMAIS plus » (`sugar_data.py:30`). Mesure sur les 85 réponses des
# rapports d'éval du 16 au 19/09 : **18 dépassent 30 mots**, jusqu'à 67.
#
# ⚠️ Et un plafond de PHRASES n'y suffit pas — c'est la mesure qui l'a montré, pas une
# intuition. En coupant à 2 phrases (son maximum affiché), seules **5 des 18** repassent
# sous 30 mots, et il en reste une à 47 : ses phrases font 20 à 25 mots chacune, donc
# deux phrases « réglementaires » pèsent déjà 48 mots. Les deux moitiés de sa propre
# règle se contredisent en pratique, et le modèle satisfait celle qui l'arrange.
#
# D'où un budget en MOTS. Il garde des phrases ENTIÈRES tant qu'il tient dans le budget,
# et jamais moins d'une : couper au milieu d'une phrase estropie la chute, et une
# punchline amputée est pire qu'une punchline longue
# ([[gotcha-nettoyeur-laisse-ce-qui-rattachait]]).
#
# Simulation sur ces 85 réponses : 67/85 sous 30 mots aujourd'hui -> **82/85**, et
# SEULES les 19 déjà en faute sont modifiées. Les 3 qui restent au-dessus sont des
# punchlines d'une seule phrase (max 34 mots) : les raccourcir voudrait dire couper
# dedans, et « ~30 » est approximatif dans sa fiche.
#
# ⚠️ Aucune exception « raconte » ici, contrairement au plafond de Johnny : sa fiche
# dit « JAMAIS plus », sans reserve. Le cas `sugar_30_mots` du harnais est absolu lui
# aussi, et c'est bien SA regle qu'il mesure (`deterministic.py:35`).
_BUDGET_MOTS = 30

_EMOJI_FINAL = re.compile(r"(\s*[\U0001F300-\U0001FAFF☀-➿️]+\s*)$")


def budget_de_mots(texte, max_mots=_BUDGET_MOTS):
    """Tronque a des phrases ENTIERES pour tenir dans `max_mots`. Jamais moins d'une.

    L'emoji de ton final est preserve et recolle : il ne compte pas dans le budget.
    Les « ... » ne sont pas des fins de phrase.
    """
    if not texte:
        return texte
    fin = ""
    m = _EMOJI_FINAL.search(texte)
    if m:
        fin = " " + m.group(1).strip()
        texte = texte[:m.start()].rstrip()
    _POINTS = chr(1)   # sentinelle : aucun texte de Discord ne la contient
    protege = re.sub(r"\.\.\.+|…", _POINTS, texte)
    # \s+ et non ' +' : une frontiere de phrase est une ponctuation suivie de N'IMPORTE
    # QUEL blanc. Avec un espace seul, les phrases separees par un SAUT DE LIGNE ne sont
    # pas comptees et le filet ne se declenche jamais.
    phrases = [s for s in re.split(r"(?<=[.!?])\s+", protege.strip()) if s.strip()]
    if not phrases:
        return (texte + fin).strip()
    gardees = [phrases[0]]
    total = len(phrases[0].split())
    for ph in phrases[1:]:
        n = len(ph.split())
        if total + n > max_mots:
            break
        gardees.append(ph)
        total += n
    return (" ".join(gardees).replace(_POINTS, "...") + fin).strip()


def filtre_sortie(texte, message_utilisateur=None):
    """Ce que Sugar retire de TOUTE reponse, sans rien savoir du salon ni de l'historique.

    `message_utilisateur` n'est pas utilise ici : il est la pour que les six bots exposent
    la MEME porte, appelable par le harnais sans savoir lequel il tient.

    Meme enchainement que le chemin Discord (`bot_sugar.py`), amputee des seules etapes
    qui dependent d'un etat : la cadence des petits noms sucres a besoin de la reponse
    PRECEDENTE du salon, elle ne peut pas entrer ici.

    C'est la porte que le harnais d'evaluation appelle pour noter le BOT et non le MODELE.
    """
    if not texte:
        return texte
    texte = re.sub(r"<fact>.*?</fact>", "", texte, flags=re.DOTALL | re.IGNORECASE).strip()
    texte = re.sub(r"<[a-z_-]+>", "", texte, flags=re.IGNORECASE)
    texte = re.sub(r"</[a-z_-]+>", "", texte, flags=re.IGNORECASE).strip()
    texte = _strip_didascalies(texte)
    texte = _strip_lead_vocative(texte)
    # En DERNIER : les etapes ci-dessus retirent du texte, donc comptent des mots qui
    # ne seront pas envoyes. Budgeter avant elles rognerait deux fois.
    texte = budget_de_mots(texte)
    return texte.strip()
