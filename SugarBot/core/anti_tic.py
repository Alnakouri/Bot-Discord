# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/anti_tic.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

import re
import unicodedata
import logging

logger = logging.getLogger("anti_tic")

# Balises internes à supprimer (recopié de sheo_llm.py)
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

_TRAILING_EMOJI_RE = re.compile(
    r"\s*("
    r"(?:[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    r"\U0000FE00-\U0000FE0F\U0000200D]+)+"
    r")\s*$"
)

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

def _norm(s: str) -> str:
    """Minuscules + accents retirés, pour comparer « tête » à « tete »."""
    if not s: return ""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")

def _radical(mot):
    """Pluriel francais rabattu sur le singulier, pour comparer « cornichon » a
    « cornichons »."""
    if len(mot) > 4 and mot[-1] in ("s", "x"):
        return mot[:-1]
    return mot

def _motifs_recurrents(reponses, message_utilisateur=None, seuil=2, maxi=6):
    """Les mots de CONTENU presents dans au moins `seuil` des dernieres repliques.

    ⚠️ Les mots du message de l'utilisateur sont EXCLUS.
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

def build_anti_tic_consigne(recent_responses, n=5, message_utilisateur=None,
                            exemple_cloture=None):
    """À partir des N dernières réponses, liste les AMORCES et CLÔTURES à éviter.
    Retourne un fragment de prompt (str), ou "" si rien d'exploitable.

    ⚠️ Ce helper est PARTAGÉ par les 6 bots et par le chemin Twitch : il ne doit citer
    AUCUN nom propre de persona. Le moule « Haskill, <ordre> » était le tic de Sheo ;
    écrit en dur ici, il ordonnait aux cinq autres bots de ne pas imiter un personnage
    dont ils n'ont jamais entendu parler. Un appelant qui a un tic nommé le passe par
    `exemple_cloture`."""
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

            # Découper en phrases (\s+ : saut de ligne compte aussi comme frontière)
            sentences = re.split(r'(?<=[.!?])\s+', cloture_base)
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

    recurrents = _motifs_recurrents(
        [r for r in (recent_responses or [])[-n:] if isinstance(r, str)],
        message_utilisateur=message_utilisateur,
    )

    if not unique_amorces and not unique_clotures and not recurrents:
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
        rappel = f' (surtout pas un "{exemple_cloture}" recyclé)' if exemple_cloture else ""
        consigne += (
            f'\nTu as CLÔTURÉ par : {formatted_clotures}. '
            f'INTERDIT de refinir pareil{rappel} — change de chute.'
        )
    if recurrents:
        formatted_mots = ", ".join(f'"{m}"' for m in recurrents)
        consigne += (
            f'\nCes mots reviennent DANS LE CORPS de tes dernières répliques : {formatted_mots}. '
            'INTERDIT de les reprendre. Change de DÉCOR, pas seulement de phrase : '
            'autre créature, autre objet, autre lubie.'
        )

    return consigne
