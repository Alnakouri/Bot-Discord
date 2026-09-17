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
import unicodedata

logger = logging.getLogger("sheogorath")

# Strip méta-narration + didascalies nues (source partagée, optionnelle cf. bots indépendants)
try:
    from shared.twitch.sanitize import strip_meta_narration, strip_bare_stage_directions
except Exception:  # pragma: no cover - fallback no-op si shared/ absent
    def strip_meta_narration(text):
        return text

    def strip_bare_stage_directions(text):
        return text


# Filet anti-tics : mutualisé dans le noyau (vendorisé sous <Bot>/core/), donc présent
# même déployé sans `shared/`. Le repli no-op garde la génération vivante en dernier
# recours plutôt que de la faire échouer sur un helper de confort.
try:
    from core.anti_tic import build_anti_tic_consigne as _anti_tic_noyau
except ImportError:  # pragma: no cover
    try:
        from shared.anti_tic import build_anti_tic_consigne as _anti_tic_noyau
    except ImportError:
        def _anti_tic_noyau(*_a, **_kw):
            return ""


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
    """Extrait les faits (<fact>...</fact>) de la réponse et les stocke.

    Gère aussi une balise <fact> TRONQUÉE (ouvrante sans </fact> fermante, coupée par le plafond
    de tokens) : dans ce cas le contenu interne du fait FUYAIT en clair dans le message (bug observé
    en live : « ...L'utilisateur semble particulièrement attaché aux... »). On retire alors tout
    depuis <fact> jusqu'à la fin. On n'enregistre PAS ce fait tronqué (incomplet = non fiable)."""
    match = re.search(r"<fact>(.*?)</fact>", response_text, re.DOTALL)
    if match:
        new_fact = match.group(1).strip()
        if new_fact:
            fact_brain.add_fact(user_id, new_fact)
        response_text = response_text.replace(match.group(0), "").strip()
        return response_text
    # Balise ouvrante SANS fermante (réponse tronquée) → couper depuis <fact> jusqu'à la fin.
    if "<fact>" in response_text:
        response_text = re.sub(r"<fact>.*$", "", response_text, flags=re.DOTALL).strip()
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

    # ⚠️ Les enveloppes VIDES laissees par tout ce qui precede.
    # Chaque nettoyeur ci-dessus retire un CONTENU entre delimiteurs, aucun ne ramasse le
    # delimiteur devenu vide : `([laugh])` -> `()`, `(*rire*)` -> `()`,
    # `(<fact>...</fact>)` -> `()`. Constate en live le 2026-09-06, message `!neutre` :
    # la reponse de Sheo se terminait par « ...crise de rage ? 🎩 () ».
    response_text = _retirer_enveloppes_vides(response_text)

    # ⚠️ Et la ponctuation qui RATTACHAIT le morceau retire. Meme mecanisme, une couche
    # plus loin : une enveloppe vide se voit (`()`), une virgule orpheline non.
    response_text = _retirer_ponctuation_orpheline(response_text)

    # Espaces multiples
    response_text = re.sub(r"\s+", " ", response_text).strip()
    return response_text


# Paires de delimiteurs qu'un nettoyage peut laisser vides. Le `*` et le `_` du markdown
# sont deja traites par strip_markdown_emphasis ; ceux-ci lui survivent.
_ENVELOPPES_VIDES = re.compile(
    r"[ 	]*(?:\(\s*\)|\[\s*\]|\{\s*\}|«\s*»|\"\s*\"|“\s*”|<\s*>)"
)


def _retirer_enveloppes_vides(texte):
    """Supprime les `()`, `[]`, `«»`... devenus vides apres le retrait de leur contenu.

    ⚠️ Repete jusqu'a stabilite : `(( ))` demande deux passes, et un modele en produit.
    On ne touche JAMAIS a une enveloppe qui contient encore quelque chose — `(oui)` reste.
    """
    if not texte:
        return texte
    for _ in range(5):
        nouveau = _ENVELOPPES_VIDES.sub("", texte)
        if nouveau == texte:
            break
        texte = nouveau
    return texte


# Une amorce qui ne peut jamais etre voulue. `…` et `...` en sont exclus : une reponse
# qui commence par des points de suspension est LEGITIME (reprise a mi-pensee), et
# `—` aussi (auto-interruption, cf. _trim_incomplete_tail).
_AMORCE_ORPHELINE = re.compile(r"^[\s]*(?!\.\.\.|…)[,;:.!?]+[\s]*")

# Deux separateurs colles par le retrait de ce qui les separait.
_SEPARATEURS_COLLES = re.compile(r",\s*(?=[,.;:!?])")

# Un espace laisse DEVANT une virgule. ⚠️ Uniquement la virgule : en typographie
# francaise, l'espace avant `;` `:` `!` `?` est CORRECT et doit survivre.
_ESPACE_AVANT_VIRGULE = re.compile(r"\s+,")


def _retirer_ponctuation_orpheline(texte):
    """Retire la ponctuation qui rattachait un morceau supprime par les nettoyeurs.

    ⚠️ Constate en live le 2026-09-07, 18:37. Sheogorath a repondu :

        « , @LeDev. Tu penses vraiment dompter le vent... »

    Meme mecanisme que les enveloppes vides ([[_retirer_enveloppes_vides]]), une couche
    plus loin : `clean_internal_tags` retire `[whisper]`, `<note>...</note>`, `[INST]`
    — et laisse la virgule qui les accrochait a la phrase. Une parenthese vide se voit ;
    une virgule en tete de replique passe pour une faute du modele.

    Trois formes, et rien d'autre :
      * l'amorce  : `, @LeDev.`  ->  `@LeDev.`
      * le collage : `Ah, , mortel`   ->  `Ah, mortel`
      * l'espace  : `Ah , mortel`     ->  `Ah, mortel`

    ⚠️ Ce qui NE doit PAS bouger : une replique ouverte par `...` ou `—` (voulue), et
    l'espace typographique francais devant `;` `:` `!` `?`.
    """
    if not texte:
        return texte
    for _ in range(5):
        nouveau = _SEPARATEURS_COLLES.sub("", texte)
        nouveau = _ESPACE_AVANT_VIRGULE.sub(",", nouveau)
        nouveau = _AMORCE_ORPHELINE.sub("", nouveau)
        if nouveau == texte:
            break
        texte = nouveau
    return texte


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


INVITATION_PATTERN = re.compile(
    r"\b(raconte|racontes?-moi|explique|développe|developpe|continue|détaille|detaille|"
    r"histoire|conte|poème|poeme|chante|décris|decris)\b", re.IGNORECASE)


def sentence_budget(user_message, short_cap=4, long_cap=10):
    """Filet déterministe : 4 phrases par défaut, 10 si le mortel invite à développer."""
    if user_message and INVITATION_PATTERN.search(user_message):
        return long_cap
    return short_cap


def force_short_response(response_text, max_sentences=10):
    """FILET anti-déraillage (pas un outil de mise en forme) : ne tronque QUE si la réponse
    dépasse largement max_sentences vraies phrases. La longueur est gouvernée par le PROMPT
    (LONGUEUR = PERTINENCE) et le budget de tokens ; ce filet n'attrape que l'emballement réel.
    Préserve l'emoji de ton final.

    ⚠️ Les « ... » / « … » ne comptent PAS comme fin de phrase : Sheo en abuse (fragments
    théâtraux « Non, une pelle. », « ... Attends. ») et les compter gonflait le compteur, ce qui
    guillotinait la vraie chute (le double-sens, la morsure finale)."""
    trailing_emoji = ""
    m = _TRAILING_EMOJI_RE.search(response_text)
    if m:
        trailing_emoji = " " + m.group(1).strip()
        response_text = response_text[:m.start()].rstrip()

    # Protéger les points de suspension avant le découpage en phrases.
    _ELLIPSIS = "\x00"
    protected = re.sub(r'\.\.\.+|…', _ELLIPSIS, response_text)
    # \s+ (pas ' +') : une frontière de phrase = ponctuation + N'IMPORTE QUEL blanc.
    # Mistral sépare souvent ses phrases par un SAUT DE LIGNE sur Discord ; avec ' +' (espace
    # seul) ces phrases n'étaient pas comptées → le filet ne se déclenchait jamais et Sheo
    # débordait (bug live 2026-07-15). Twitch (mono-ligne IRC) échappait au défaut.
    sentences = re.split(r'(?<=[.!?])\s+', protected)
    if len(sentences) > max_sentences:
        protected = " ".join(sentences[:max_sentences])
    response_text = protected.replace(_ELLIPSIS, "...")
    return (response_text + trailing_emoji).strip()


# Interjections / mots vides qui ne comptent pas comme "écho" en ouverture.
_ECHO_STOPWORDS = {
    "oh", "ah", "eh", "ha", "haha", "hého", "tiens", "alors", "ainsi", "donc",
    "quelle", "quel", "quels", "quelles", "les", "des", "une", "mon", "mes",
    "cette", "cet", "ces", "vraiment", "encore",
}


def _norm(s: str) -> str:
    """Minuscules + accents retirés, pour comparer « tête » à « tete »."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def strip_markdown_emphasis(reply):
    """Retire les `*...*` et `_..._` : le prompt de Sheogorath les INTERDIT.

    ⚠️ Mesure du 2026-09-04 (sonde des 6 personas, 3 modeles Mistral) : Sheogorath est le
    SEUL bot dont le prompt interdit explicitement les asterisques — « PAS DE NARRATION :
    jamais d'actions... ni parentheses, ni asterisques », en tete, en majuscules, avec un
    emoji d'interdiction — et c'est le SEUL a 9/9 reponses qui en contiennent. Le taux le
    plus eleve des six.

    Une regle de prompt oriente ; elle ne garantit rien. Seul un filet deterministe
    garantit. Les mots sont conserves, seuls les marqueurs tombent."""
    if not reply:
        return reply
    # `**gras**` puis `*italique*` ; `_..._` seulement entre limites de mots, pour ne pas
    # amputer un pseudo comme `le_dev`.
    # ⚠️ `**gras**` d'abord, sinon `**x**` laisse un asterisque orphelin.
    nettoye = re.sub(r'\*\*(\S(?:[^*]*\S)?)\*\*', r'\1', reply)
    nettoye = re.sub(r'\*(\S(?:[^*]*\S)?)\*', r'\1', nettoye)
    nettoye = re.sub(r'(?<![\w])_([^_]+?)_(?![\w])', r'\1', nettoye)
    return nettoye


def _strip_echo_opening(reply, user_message, max_strips=2):
    """Coupe une ouverture qui HURLE l'insulte du mortel en écho (« Oh, "FACE DE PET" ! »,
    « NUL ?! ») et garde la vraie vanne derrière. Ne touche PAS :
    - un écho en casse NORMALE (« Des pâtes ? » = réflexion voulue, canon) ;
    - une réponse ENTIÈREMENT en majuscules (easter egg ALL CAPS / cri de mania) ;
    - une ouverture qui apporte du neuf.
    Ne coupe jamais si le reste devient un moignon."""
    if not reply or not user_message:
        return reply

    # Ne jamais toucher un cri intégral (easter egg ALL CAPS).
    letters = [c for c in reply if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return reply

    user_words = {w for w in re.findall(r"\w+", _norm(user_message)) if len(w) >= 3}
    user_words -= _ECHO_STOPWORDS
    if not user_words:
        return reply

    current = reply.strip()
    for _ in range(max_strips):
        m = re.match(r"\s*(.+?[.!?…]+)\s+(\S.*)", current, re.DOTALL)
        if not m:
            break
        head, rest = m.group(1), m.group(2).strip()
        # Tête = pure interjection (« Ah... ») ?
        head_sig = {w for w in re.findall(r"\w+", _norm(head)) if len(w) >= 3} - _ECHO_STOPWORDS
        is_interjection = not head_sig
        # Tête = HURLE un mot du mortel (token EN MAJUSCULES ≥ 3 lettres qui échote) ?
        caps_tokens = re.findall(r"[A-ZÀ-ÖØ-Þ]{3,}", head)
        is_shouted_echo = bool({_norm(t) for t in caps_tokens} & user_words)
        # Tête = contient une citation en écho du mortel ?
        # ⚠️ Le markdown `*mot*` compte comme une citation. Sonde du 2026-09-04 : un
        # modele a ouvert par `*Nul* ?!` — l'echo interdit — et il est passe, parce que
        # ce motif n'etait ni un cri (pas de MAJUSCULES) ni une citation reconnue.
        head_demarque = re.sub(r'\*{1,2}([^*]+?)\*{1,2}', r'"\1"', head)
        raw_matches = re.findall(r'"([^"]+?)"|«([^»]+?)»|“([^”]+?)”|‘([^’]+?)’|\'([^\']+?)\'', head_demarque)
        quoted_segments = [seg for tup in raw_matches for seg in tup if seg]
        is_quoted_echo = any(
            (sig := {w for w in re.findall(r"\w+", _norm(seg)) if len(w) >= 3} - _ECHO_STOPWORDS)
            and all(any(w.startswith(uw) or uw.startswith(w) for uw in user_words) for w in sig)
            for seg in quoted_segments
        )
        if not (is_interjection or is_shouted_echo or is_quoted_echo):
            break
        if len(rest) < 15:
            break
        current = rest

    if current and current != reply.strip():
        return current[0].upper() + current[1:]
    return reply


def _trim_incomplete_tail(text):
    """Si le plafond de tokens a coupé la réponse EN PLEIN MOT (elle ne finit ni par une
    ponctuation de fin, ni par un tiret d'auto-interruption, ni par un emoji de ton), on revient
    à la dernière fin de phrase propre. Évite les « ...Un from » / « ...bas corpor » disgracieux.
    Ne touche JAMAIS une réponse déjà propre (préserve « — » d'auto-interruption voulue)."""
    if not text:
        return text
    stripped = text.rstrip()
    # Isoler un éventuel emoji de ton final : une fin sur emoji est PROPRE.
    if _TRAILING_EMOJI_RE.search(stripped):
        return text
    # Fin déjà propre : ponctuation terminale, guillemet/parenthèse fermante, ou tiret voulu.
    if re.search(r"[.!?…—»\"')\]]$", stripped):
        return text
    # Sinon (coupe en plein mot) : revenir à la dernière ponctuation de fin de phrase.
    cuts = list(re.finditer(r"[.!?…]", stripped))
    if cuts:
        return stripped[:cuts[-1].end()].rstrip()
    return text  # aucune phrase complète : ne rien casser


def filtre_sortie(texte, message_utilisateur=None):
    """Tout ce que Sheogorath RETIRE d'une réponse, et rien de ce qu'il y ajoute.

    Sorti de `postprocess_response` le 2026-09-17 pour que le harnais d'évaluation
    puisse enchaîner EXACTEMENT les mêmes étapes que le bot. Il notait jusque-là la
    sortie brute du modèle : Sheo était puni pour 17/17 astérisques que personne ne voit
    jamais, puisqu'il les retire avant l'envoi.
    Cf. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].

    Ne contient QUE les étapes qui n'exigent pas d'état de conversation. Restent dehors,
    donc à la charge de `postprocess_response` : l'extraction de faits (il lui faut le
    cerveau), les easter eggs (ils AJOUTENT du texte), et le plafond de phrases (il se
    calcule sur le message et doit tomber APRÈS les easter eggs).

    `message_utilisateur` est facultatif : sans lui, l'écho-perroquet n'est pas coupé.
    """
    if not texte:
        return texte

    # Les blocs <fact>…</fact> : `extract_facts` les retire après les avoir enregistrés ;
    # ici on n'a pas le cerveau, on retire seulement le texte pour voir la même réplique.
    texte = re.sub(r"<fact>.*?</fact>", "", texte, flags=re.DOTALL | re.IGNORECASE)

    # Nettoyage des balises
    texte = clean_internal_tags(texte)

    # Méta-narration hors-personnage ("L'utilisateur semble...")
    texte = strip_meta_narration(texte)

    # Didascalies nues sans astérisques ("... ?! hurle UNE CUILLÈRE")
    texte = strip_bare_stage_directions(texte)

    # Ouverture-perroquet qui HURLE l'insulte en écho ("Oh, FACE DE PET !")
    texte = _strip_echo_opening(texte, message_utilisateur or "")

    # ── Les asterisques, a DEUX etages — et l'ordre porte toute la mesure ──────────
    #
    # ⚠️ Tout ce bloc passe APRES _strip_echo_opening : c'est le marqueur `*...*` qui
    # lui permet de reconnaitre l'echo. Nettoyer avant lui reviendrait a lui crever un oeil.
    #
    # Etage 1 — une didascalie entre asterisques : le SEGMENT ENTIER tombe.
    # Mesure du 2026-09-17, avec le seul strip_markdown_emphasis :
    #   « *Soupir imperceptible, mais audible…* Le the est servi. »
    #   -> « Soupir imperceptible, mais audible… Le the est servi. »
    # Sheogorath ne cessait pas de se decrire : il cessait de le mettre en italique, ce
    # qui est PIRE pour qui lit. `strip_bare_stage_directions` n'y voyait rien, puisque la
    # didascalie n'etait justement pas « nue ». Les cinq autres bots n'ont pas ce trou :
    # leur filtre traite `*...*` comme une didascalie d'emblee (logique curee de Sugar).
    # ⚠️ En tete : tout segment. Apres une ponctuation : seulement s'il fait au moins deux
    # mots — un `*mot*` isole au milieu d'une phrase reste de l'emphase, pas une action.
    # ⚠️ BORNE de longueur : sans elle, `[^*]+` court jusqu'à l'astérisque suivante, où
    # qu'elle soit. Cas réel du run du 2026-09-17 (chez Alfred, même règle) : le modèle
    # ouvre par `*` et referme 200 caractères plus loin, et la règle emporte TOUTE la
    # réplique. Une didascalie est courte ; au-delà, c'est de la prose mise en italique,
    # et on ne retire alors que les marqueurs.
    texte = re.sub(r"^\s*\*[^*\n]{1,120}\*\s*", "", texte)
    texte = re.sub(r"(?<=[.!?…])\s*\*[^*\n]{1,120}\s[^*\n]{1,120}\*\s*", " ", texte)

    # Etage 2 — le reste n'etait que de l'emphase : les marqueurs tombent, les mots restent.
    texte = strip_markdown_emphasis(texte)

    # Seconde passe sur les didascalies NUES : ce que les asterisques masquaient au
    # premier passage devient visible une fois les marqueurs tombes.
    texte = strip_bare_stage_directions(texte)

    # Et la ponctuation qui RATTACHAIT le morceau supprime
    # ([[gotcha-nettoyeur-laisse-ce-qui-rattachait]]).
    texte = _retirer_ponctuation_orpheline(texte)

    return re.sub(r"\s{2,}", " ", texte).strip()


def postprocess_response(response_text, fact_brain, user_id, original_message, max_sentences=4):
    """Pipeline complet de post-processing de la réponse LLM."""
    # 1. Extraction de faits
    response_text = extract_facts(response_text, fact_brain, user_id)

    # 2. Tout le nettoyage, dans un SEUL endroit, partagé avec le harnais d'évaluation :
    # deux enchaînements parallèles finissent toujours par diverger, et c'est alors le
    # score qui ment.
    response_text = filtre_sortie(response_text, original_message)

    # 3. Easter eggs
    response_text = apply_easter_eggs(response_text, original_message)

    # 4. Forcer réponse courte
    response_text = force_short_response(response_text, max_sentences=max_sentences)

    # 5. Coupe propre si le plafond de tokens a tronqué en plein mot.
    response_text = _trim_incomplete_tail(response_text)

    return response_text


def merge_recent_responses(*sources, limit=8):
    """Fusionne des listes de réponses récentes (None-safe), dédoublonne en gardant l'ordre."""
    seen, out = set(), []
    for src in sources:
        for r in (src or []):
            if r and r not in seen:
                seen.add(r)
                out.append(r)
    return out[-limit:]


# Mots-outils : ils reviennent forcement d'une phrase a l'autre et ne disent rien d'un
# tic. Ecrits SANS accent, parce que `_norm` les retire avant la comparaison.
_MOTS_OUTILS = {
    "dans", "pour", "avec", "sans", "mais", "donc", "plus", "tout", "tous", "toute",
    "toutes", "cette", "leur", "leurs", "elle", "elles", "nous", "vous", "etre", "avoir",
    "fait", "faire", "peut", "peux", "veux", "veut", "comme", "quand", "alors", "encore",
    "aussi", "meme", "bien", "trop", "chaque", "quelque", "quelques", "quel", "quelle",
    "quels", "quelles", "celui", "celle", "ceux", "cela", "juste", "deja", "puis",
    "ensuite", "parce", "pendant", "toujours", "jamais", "rien", "personne", "autre",
    "autres", "entre", "sous", "vers", "chez", "depuis", "apres", "avant", "moins",
    "beaucoup", "peut-etre", "voila", "voici", "ainsi", "surtout", "petit", "petite",
    "grand", "grande", "prochaine", "prochain",
}


def _radical(mot):
    """Pluriel francais rabattu sur le singulier, pour comparer « cornichon » a
    « cornichons ».

    ⚠️ Sans ca, l'exclusion du sujet ne mordait pas : le mortel ecrit « ta tete de
    cornichon ? » au singulier, Sheo repond « cornichons » au pluriel, et l'interdiction
    s'appliquait quand meme — on lui coupait le sujet de la conversation.
    """
    if len(mot) > 4 and mot[-1] in ("s", "x"):
        return mot[:-1]
    return mot


def _motifs_recurrents(reponses, message_utilisateur=None, seuil=2, maxi=6):
    """Les mots de CONTENU presents dans au moins `seuil` des dernieres repliques.

    ⚠️ Mesure du 2026-09-06, sur les 8 vraies reponses de Sheo a LeDev : le moule
    « Haskill, <ordre> » tenait **7 repliques sur 8**, et aucun filet ne le voyait.
    L'amorce (5 premiers mots) l'attrapait 2 fois sur 7, la cloture (5 derniers) **0 sur
    7** : « Haskill » etait aux positions 103, 117, 126, 175, 220. Un tic ne vit ni au
    debut ni a la fin, il vit au MILIEU — et rien ne regardait le milieu.

    ⚠️ Les mots du message de l'utilisateur sont EXCLUS. S'il ecrit « ta tete de
    cornichon ? », Sheo doit pouvoir lui repondre cornichon : on interdit la rengaine,
    jamais le sujet de la conversation.

    ⚠️ Rien n'est ajoute au prompt cote entree : `recent_responses` porte deja le texte
    COMPLET des repliques, seul son affichage etait tronque a 60 caracteres ailleurs.
    Ce filet coute quelques mots, pas quelques centaines de tokens — le quota Groq est
    en tokens par minute et le prompt de Sheo en mange deja 56 %.
    """
    if not reponses:
        return []

    interdits_du_sujet = set()
    if message_utilisateur:
        interdits_du_sujet = {_radical(w) for w in re.findall(r"[a-z]+", _norm(message_utilisateur))}

    compte = {}
    for resp in reponses:
        if not resp or not isinstance(resp, str):
            continue
        mots = {w for w in re.findall(r"[a-z]+", _norm(resp))
                if len(w) >= 4 and w not in _MOTS_OUTILS
                and _radical(w) not in interdits_du_sujet}
        for mot in mots:
            compte[mot] = compte.get(mot, 0) + 1

    recurrents = [(n_vu, mot) for mot, n_vu in compte.items() if n_vu >= seuil]
    # Le plus repete d'abord ; a egalite, ordre alphabetique pour rester deterministe.
    recurrents.sort(key=lambda x: (-x[0], x[1]))
    return [mot for _, mot in recurrents[:maxi]]


# Registre d'ecriture propre a chaque humeur. ⚠️ UNE seule entree par humeur, jamais un
# « ou » : voir `consigne_de_ton`.
_REGISTRE_PAR_HUMEUR = {
    "dementia": ("inquietant, enigmatique et paranoiaque — tu insinues plus que tu n'affirmes, "
                 "les tenebres murmurent, le doute s'installe"),
    "mania":    "joueur, exalte, curieux et imprevisible — les couleurs explosent",
    "bliss":    "chaleureux, jovial et etrangement lucide — une euphorie qui met mal a l'aise",
    "neutral":  "joueur et theatral, entre malice et menace voilee",
}


def consigne_de_ton(mood, provoque=False):
    """Le bloc [TON] envoye au modele quand le mortel n'a NI insulte NI manque de respect.

    ⚠️ Ce bloc REOUVRAIT l'humeur que le systeme venait de trancher. Il disait :
    « joueur, exalte, curieux et imprevisible (Mania), OU inquietant et enigmatique
    (Dementia) » — un choix, propose APRES le prompt d'humeur, donc plus proche de la
    fin et plus lourd. Le modele prenait le premier terme a chaque fois.

    Constate en live le 2026-09-06 : quatre repliques d'affilee generees en humeur
    `dementia` (journal : 20:31:36, 20:32:04, 20:32:49, 20:33:30), quatre repliques
    joyeuses — papillons qui fredonnent du jazz, bulles de confiture, cornichons
    chantants. Aucune tenebre. La seule replique vraiment sombre de la session est
    arrivee quand le mortel avait lui-meme ecrit le mot « dementia » : le modele reprenait
    le theme de son TEXTE, jamais celui de son humeur.

    La garde anti-menace-gratuite reste entiere — elle existe pour une raison : Sheogorath
    n'est pas une brute qui menace de torture a chaque message anodin. Mais elle ne doit
    pas coûter l'humeur. Dementia n'est PAS une menace de torture, c'est un malaise.
    """
    if provoque:
        return ""
    registre = _REGISTRE_PAR_HUMEUR.get(mood, _REGISTRE_PAR_HUMEUR["neutral"])
    return (
        "[TON — PAS DE MENACE GRATUITE] : Le mortel ne t'a NI insulte NI manque de respect. "
        f"Ton humeur du moment est {str(mood).upper()} et elle est DEJA choisie : reste {registre}. "
        "NE le menace PAS de mort, de torture ou de lui arracher les dents pour un message aussi "
        "anodin — mais ne change PAS d'humeur pour autant. Rebondis VRAIMENT sur ce qu'il vient "
        "de dire, avec malice et absurde. Les menaces glaciales sont reservees au manque de "
        "respect reel.\n"
    )


def build_anti_tic_consigne(recent_responses, n=5, message_utilisateur=None):
    """Enveloppe : le filet est mutualisé dans le noyau, le tic NOMMÉ reste à Sheo.

    « Haskill, note ça » est SA clôture réflexe (7 répliques sur 8 le 07/09) : c'est ici,
    et nulle part dans le helper partagé, qu'on a le droit de la citer."""
    return _anti_tic_noyau(
        recent_responses,
        n=n,
        message_utilisateur=message_utilisateur,
        exemple_cloture="Haskill, note ça",
    )

