"""Compter les phrases d'une replique, sans se faire avoir par l'emoji final.

⚠️ POURQUOI CE MODULE EXISTE. Le 2026-09-21, Alfred etait declare « trop long » sur
trois passes d'eval de suite : mediane 3 phrases quand sa fiche en exige 2, et jusqu'a
11 reponses sur 17 au-dessus de la borne. C'etait FAUX. Ses repliques finissent par un
emoji de ton, seul, apres le point final :

    L'intrus de porcelaine cherche un endroit ou briser ses illusions. La serpilliere
    ne suffira pas cette fois, mais heureusement que la cave est vaste. ☕🦇

Un `re.split(r"(?<=[.!?])\\s+", ...)` compte ce `☕🦇` comme une TROISIEME phrase. Une
fois les fragments sans la moindre lettre ecartes, les trois passes tombent a **0/17**
au-dessus de la borne : le defaut n'existait pas, seule la mesure existait.

⚠️ Ce module n'est PAS vendorise (il n'est pas dans `tools/vendor_core.py`) : il sert au
harnais et aux sondes, pas au runtime des bots. Le bloc que `sonde_modeles_ouverts.py`
injecte DANS un conteneur en recopie la regle, faute de pouvoir l'importer.

Le runtime des bots, lui, avait raison depuis toujours — `shared/anti_tic.py` retire
l'emoji final AVANT de decouper. Ce sont les SONDES qui comptaient a l'ancienne, et
leurs chiffres ont nourri les commentaires de `shared/models.py` : chaque comparaison
« N phrases » entre deux modeles y est biaisee par la frequence a laquelle chacun
termine par un emoji.
"""
import re

# Fin de phrase reelle. Les « ... » sont volontairement exclus : ils gonflent le compte
# et ont deja coute une punchline ([[feedback-sheo-longueur-densite]]).
PONCTUATION_FIN = r"(?<=[.!?])\s+"


def est_une_phrase(fragment: str) -> bool:
    """Un fragment sans AUCUNE lettre ni chiffre n'est pas une phrase.

    Volontairement plus large qu'un motif d'emoji : ca couvre aussi un « ! » orphelin,
    des points de suspension isoles, ou n'importe quel signe que le modele laisse
    trainer apres sa derniere ponctuation.
    """
    return any(c.isalnum() for c in fragment)


def phrases(texte: str) -> list:
    """Les phrases reelles de ce texte, emoji de cloture exclu."""
    if not texte:
        return []
    fragments = [f.strip() for f in re.split(PONCTUATION_FIN, texte.strip())]
    return [f for f in fragments if f.strip() and est_une_phrase(f)]


def compte_phrases(texte: str) -> int:
    return len(phrases(texte))
