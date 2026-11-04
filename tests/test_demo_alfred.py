# -*- coding: utf-8 -*-
"""La demo web d'Alfred ne doit pas deriver du vrai Alfred.

Sa persona est generee depuis `Alfred/alfred_data.py` et son filtre porte en JavaScript
depuis `Alfred/alfred_filtres.py` : sans ces tests, le bot et sa vitrine divergeraient
sans bruit.
"""
import importlib.util
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DEMO = RACINE / "demo-alfred"


def _charge(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generateur = _charge("generer_persona_demo", DEMO / "generer_persona.py")
filtres = _charge("alfred_filtres_demo", RACINE / "Alfred" / "alfred_filtres.py")

CAS_FIXES = [
    "",
    "Le thé est servi, Monsieur.",
    "*Soupir imperceptible* Le thé est servi.",
    "*pose son torchon* Quelle audace.",
    "Bien entendu. *The Times* vous attend.",
    "**gras** et *italique* dans la même phrase",
    "**a *b* c** et **d *e* f**",
    "Il est parti pour **l'emotion",
    "Elle m'a dit : *\"C'est",
    "L'utilisateur demande un café. Le voici, Monsieur.",
    "l'interlocuteur s'impatiente\nVoici le thé.",
    "Le joueur a perdu. Tant pis.",
    "Soupir. Encore vous.",
    "Quelle audace. Soupire longuement dans le couloir. Voici.",
    "Monsieur. Un soupir résigné traverse la pièce. Voici.",
    "S'esclaffe doucement. Non.",
    "Se penche vers vous lentement. Voici.",
    "Souris ! La photo est prête.",
    "Bien. RICANEMENT Non.",
    "<fact>Il aime le thé</fact>Voici le thé.",
    "<reponse>Voici</reponse>",
    "<soupire longuement>Voici.",
    "Un `*` seul et *un autre",
    "*" * 5,
    "Texte\n\n   avec    espaces",
    "*" + "x" * 200 + "* suite",
    "Parfait. *regard appuyé vers la fenêtre* Voici.",
    "Sourire aux lèvres, il répond.",
    "Éclat de rire dans la salle. Voici.",
    "éclate de rire puis repart. Voici.",
]

FRAGMENTS = [
    "Voici le thé, Monsieur.", "*soupir*", "**gras**", "*italique bref*", "Soupir", "se penche doucement",
    "Un soupir", "le silence", "L'utilisateur insiste.", "<fact>note</fact>", "<b>", "</b>", "<tag avec espace>",
    "\n", "  ", "...", "!", "—", "*", "**", "sourit", "ricane encore", "Éclat", "d'un rire", "s'avance",
    "À", "é", "Voilà", "🧐", "☕",
]


def _corpus_aleatoire(n=600):
    tirage = random.Random(20261101)
    return ["".join(tirage.choice(FRAGMENTS) + tirage.choice(["", " "]) for _ in range(tirage.randint(1, 8)))
            for _ in range(n)]


def test_persona_generee_a_jour():
    actuel = (DEMO / "src" / "persona.generated.js").read_text(encoding="utf-8")
    assert actuel == generateur.contenu_genere(), "relancer python demo-alfred/generer_persona.py"


def test_persona_sans_duels_ni_mentions():
    persona = generateur.persona_demo(generateur._charge_persona())
    assert "Alfred Pennyworth" in persona
    assert "Sheogorath" not in persona and "M'AIQ" not in persona and "<@ID>" not in persona
    assert persona.endswith(generateur.CADRE_DEMO)
    assert persona.count("Utilise UNIQUEMENT des emojis") == 1


def test_coupe_introuvable_arrete_la_generation():
    with pytest.raises(ValueError):
        generateur.persona_demo("une fiche sans aucun des reperes attendus")


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_filtre_js_identique_au_filtre_python():
    corpus = CAS_FIXES + _corpus_aleatoire()
    sortie = subprocess.run(
        ["node", str(DEMO / "tests" / "filtre_cli.mjs")],
        input=json.dumps(corpus), capture_output=True, text=True, encoding="utf-8", check=True,
    )
    obtenu = json.loads(sortie.stdout)
    ecarts = [(t, filtres.filtre_sortie(t), j) for t, j in zip(corpus, obtenu)
              if filtres.filtre_sortie(t) != j]
    assert not ecarts, f"{len(ecarts)} ecarts, premiers : {ecarts[:5]}"
