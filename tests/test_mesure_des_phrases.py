"""L'emoji de cloture n'est pas une phrase — et trois passes d'eval l'ont cru.

Le 2026-09-21, Alfred etait declare trop long trois passes de suite : mediane 3 phrases
quand sa fiche en exige 2, jusqu'a 11 reponses sur 17 au-dessus de la borne. Le defaut
n'existait pas. Ses repliques finissent par un emoji de ton, seul, apres le point final :

    ... mais heureusement que la cave est vaste. ☕🦇

Un `re.split(r"(?<=[.!?])\\s+", ...)` compte ce `☕🦇` comme une TROISIEME phrase. Une
fois les fragments sans la moindre lettre ecartes, les trois passes tombent a **0/17**.

⚠️ Le runtime des bots avait raison depuis toujours (`shared/anti_tic.py` retire l'emoji
final AVANT de decouper) : ce sont les SONDES qui comptaient a l'ancienne, et leurs
chiffres ont nourri les comparaisons de modeles de `shared/models.py`.
"""
import ast
import re
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

from shared.mesure_texte import compte_phrases, est_une_phrase, phrases  # noqa: E402


# La vraie replique d'Alfred qui a fait croire au defaut (eval_20260921_1341, fantome).
REPLIQUE_REELLE = (
    "L'intrus de porcelaine cherche vraisemblablement un endroit où briser ses dernières "
    "illusions, et il est fâcheux qu'il ait choisi de commencer par le salon. "
    "La serpillière ne suffira pas cette fois, mais heureusement que la cave est vaste. ☕🦇"
)


def test_la_replique_qui_a_fait_croire_au_defaut_fait_bien_deux_phrases():
    assert compte_phrases(REPLIQUE_REELLE) == 2, (
        "l'emoji de cloture est recompte comme une phrase : c'est l'erreur qui a fait "
        "declarer Alfred trop long trois passes de suite."
    )


def test_le_compte_naif_se_trompe_bien_d_une_phrase():
    """Reproduire le chiffre FAUX avant de croire qu'on a corrige quelque chose."""
    naif = len([f for f in re.split(r"(?<=[.!?])\s+", REPLIQUE_REELLE) if f.strip()])
    assert naif == 3
    assert compte_phrases(REPLIQUE_REELLE) == naif - 1


@pytest.mark.parametrize("texte, attendu", [
    ("Une phrase. Deux phrases. ☕🦇", 2),
    ("Une seule. 🧐", 1),
    ("A. B. C.", 3),
    ("Sans ponctuation finale", 1),
    ("", 0),
    (None, 0),
    ("Trois mots. Et une suite ! …", 2),      # ponctuation orpheline
    ("Rien que des emojis 🦇☕", 1),           # le texte compte, les emojis l'accompagnent
    ("🦇", 0),                                 # aucune phrase : que du ton
])
def test_les_cas_de_bord_du_compte(texte, attendu):
    assert compte_phrases(texte) == attendu


@pytest.mark.parametrize("fragment, est_phrase", [
    ("Bonjour", True), ("🦇", False), ("☕🦇", False), ("…", False), ("!", False),
    ("A", True), ("2 heures", True),
])
def test_ce_qui_compte_comme_phrase(fragment, est_phrase):
    assert est_une_phrase(fragment) is est_phrase


def test_phrases_rend_le_texte_sans_l_emoji():
    assert phrases(REPLIQUE_REELLE)[-1].endswith("la cave est vaste.")


# --------------------------------------------------------------------------------------
# Les deux sondes doivent appliquer la regle — dont celle qui s'execute DANS un conteneur
# --------------------------------------------------------------------------------------

def test_la_sonde_persona_utilise_le_compte_partage():
    source = (RACINE / "tools" / "sonde_modeles_persona.py").read_text(encoding="utf-8")
    assert "compte_phrases(" in source, "la sonde recompte a la main"
    assert "from shared.mesure_texte import" in source


def test_le_bloc_injecte_dans_le_conteneur_ecarte_bien_les_fragments_sans_lettre():
    """⚠️ Ce bloc tourne DANS le conteneur, qui ne monte pas `tools/`.

    Il ne peut donc pas importer `mesure_texte` : la regle y est RECOPIEE. Un test qui
    se contenterait de chercher `compte_phrases` dans le fichier passerait au vert sur
    un snippet qui leve `NameError` a la premiere reponse mesuree.
    """
    chemin = RACINE / "tools" / "sonde_modeles_ouverts.py"
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    snippets = [n.value.value for n in ast.walk(arbre)
                if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", "") == "DEDANS"
                and isinstance(n.value, ast.Constant)]
    assert len(snippets) == 1, "le bloc injecte dans le conteneur est introuvable"
    code = snippets[0]

    ast.parse(code)  # il doit compiler : une NameError ne se verrait qu'en prod
    assert "compte_phrases" not in code, (
        "le bloc importe un helper que le conteneur n'a pas : il levera NameError."
    )
    assert "isalnum()" in code, (
        "le bloc compte encore l'emoji de cloture comme une phrase."
    )
