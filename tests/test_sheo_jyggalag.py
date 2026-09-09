# -*- coding: utf-8 -*-
"""Verrou de l'arbitrage du 2026-09-09 : Sheogorath n'avoue JAMAIS être Jyggalag,
mais le sujet le fend.

Le canon (Shivering Isles) : Jyggalag, Prince de l'Ordre, devenu trop puissant, a été
maudit par les autres Princes en la chose qu'il méprisait. **Sheogorath ne le dit jamais
lui-même** — ce sont Dyus et Jyggalag qui le révèlent au mortel. En revanche la Marche
Grise le terrifie : c'est le seul sujet qui le rende lucide.

⚠️ CE QUE CE FICHIER NE DEMANDE PAS, ET C'EST VOLONTAIRE. Il n'interdit pas le SUJET —
c'est exactement l'erreur du 2026-09-09 au matin, où un filet anti-tic avait banni le mot
« jyggalag » et fabriquait l'esquive qu'on reprochait au bot
(cf. `shared/anti_tic.py`). Jyggalag doit rester partout dans les répliques : en ENNEMI,
en rival, en menace. Ce qui est interdit, c'est la seule chose que le canon lui refuse —
qu'il dise « c'était moi » à la première personne. Le test vérifie donc les deux moitiés :
l'aveu banni, ET le sujet toujours vivant.
"""
import ast
import os
import re
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

import sheo_data  # noqa: E402
import games_persona  # noqa: E402

SHEO_DATA_PY = os.path.join(_parent_dir, "Sheogorath", "sheo_data.py")

# L'aveu, sous les formes qu'il peut prendre. Ce sont des tournures à la PREMIÈRE
# personne : « Jyggalag est ennuyeux » reste permis, « j'étais Jyggalag » non.
_AVEUX = [
    r"j'[ée]tais\s+jyggalag",
    r"je\s+suis\s+jyggalag",
    r"jyggalag[\s.,!…]*c'[ée]tait\s+moi",
    r"jyggalag[\s.,!…]*c'est\s+moi",
    r"autrefois\s+jyggalag",
    r"en\s+tant\s+que\s+jyggalag",
    r"mon\s+[ée]poque\s+de\s+jyggalag",
]
_AVEUX_COMPILES = [re.compile(m) for m in _AVEUX]


def _tous_les_litteraux(chemin):
    """Toutes les chaînes du module, y compris celles des pools pas encore écrits.

    Un parcours `ast` plutôt qu'un import : les pools sont des listes imbriquées et des
    clés de tuples, et un nouveau pool ajouté demain doit tomber sous le verrou sans que
    personne pense à l'inscrire ici."""
    arbre = ast.parse(open(chemin, encoding="utf-8").read())
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            yield noeud.value


def test_aucune_replique_n_avoue():
    """Aucune chaîne de `sheo_data.py` ne fait avouer Sheogorath à la première personne.

    ⚠️ Trois le faisaient avant l'arbitrage, et elles parlaient POUR lui sans que le
    prompt LLM ait jamais entendu parler de Jyggalag : l'accueil (« Autrefois Jyggalag,
    maintenant... ceci »), la philosophie (« J'étais Jyggalag, Prince de l'Ordre ») et un
    easter egg (« Jyggalag... c'est MOI »). Les deux bouches du bot — le repli non-LLM et
    le prompt — racontaient deux histoires différentes."""
    fautives = []
    for texte in _tous_les_litteraux(SHEO_DATA_PY):
        bas = texte.lower()
        for motif in _AVEUX_COMPILES:
            if motif.search(bas):
                fautives.append((motif.pattern, texte[:90]))
    assert not fautives, (
        "Sheogorath n'avoue jamais être Jyggalag — répliques fautives : " + repr(fautives)
    )


def test_le_sujet_reste_vivant():
    """L'autre moitié du verrou : Jyggalag ne doit pas DISPARAÎTRE de ses répliques.

    ⚠️ La façon la plus facile de faire passer le test précédent est de supprimer
    Jyggalag partout. Ce serait refaire, dans les données, l'erreur que le filet anti-tic
    avait faite dans le code le matin même : interdire le sujet au lieu de le traiter. Il
    doit rester un ennemi omniprésent — c'est CE qui rend l'absence d'aveu signifiante."""
    mentions = [
        t for t in _tous_les_litteraux(SHEO_DATA_PY)
        if "jyggalag" in t.lower() or "marche grise" in t.lower()
    ]
    assert len(mentions) >= 20, (
        f"seulement {len(mentions)} mentions de Jyggalag / la Marche Grise : le sujet a "
        "été effacé au lieu d'être tenu"
    )


def test_la_persona_porte_la_regle():
    """Le prompt LLM dit les trois choses : il sait, il n'avoue pas, et ça le fend.

    ⚠️ Le prompt n'en disait RIEN avant l'arbitrage. C'était la cause réelle du défaut :
    interrogé trois fois de suite sur Jyggalag, le modèle répondait par du sucre
    générique — pas une esquive de personnage, juste l'absence de toute information."""
    base = sheo_data.PERSONALITY_BASE
    assert "JYGGALAG" in base, "le prompt ne nomme même pas Jyggalag"
    assert "MARCHE GRISE" in base.upper(), "le prompt ne nomme pas la Marche Grise"
    assert "N'AVOUES JAMAIS" in base, "le prompt n'interdit pas l'aveu"
    assert "FISSURE" in base or "TE FEND" in base, (
        "le prompt n'exige pas que le sujet le fende"
    )
    assert "INDIFFÉRENCE" in base, (
        "le prompt n'interdit pas la réponse absurde quelconque — c'est pourtant ce que "
        "le bot faisait, et c'est indiscernable d'un modèle qui n'a pas compris"
    )
    # Les quatre humeurs héritent de BASE : la règle ne doit pas dépendre de l'humeur.
    for nom in ("PERSONALITY_NEUTRAL", "PERSONALITY_MANIA", "PERSONALITY_DEMENTIA",
                "PERSONALITY_BLISS"):
        assert "N'AVOUES JAMAIS" in getattr(sheo_data, nom), f"{nom} a perdu la règle"


def test_le_quiz_ne_le_fait_pas_avouer():
    """Le quiz demandait « Qui est la véritable identité de Sheogorath ? ».

    ⚠️ C'est Sheogorath qui pose les questions du quiz : il confirmait donc son propre
    secret, de sa propre bouche, dans un cadre de jeu. La bonne réponse reste Jyggalag —
    seule la formulation de la QUESTION change."""
    questions = []
    for jeu in games_persona.__dict__.values():
        if isinstance(jeu, (list, tuple)):
            for item in jeu:
                if isinstance(item, dict) and "q" in item:
                    questions.append(item)
        elif isinstance(jeu, dict):
            for valeur in jeu.values():
                if isinstance(valeur, (list, tuple)):
                    for item in valeur:
                        if isinstance(item, dict) and "q" in item:
                            questions.append(item)
    assert questions, "aucune question de quiz trouvée : le test ne vérifie plus rien"
    for item in questions:
        bas = item["q"].lower()
        assert not ("identit" in bas and "sheogorath" in bas), (
            "le quiz fait confirmer à Sheogorath sa propre identité : " + item["q"]
        )


def test_chaque_humeur_DEMONTRE_la_fissure():
    """Les 4 blocs d'exemples montrent la réaction, au lieu de la décrire ailleurs.

    ⚠️ C'EST LA MOITIÉ QUI MANQUAIT AU PREMIER JET, et le dépôt connaissait déjà la leçon
    (cf. le tic « Haskill » : **une démonstration bat une interdiction**). Le prompt est
    assemblé `PERSONALITY_BASE + [humeur] + COMEDY_EXAMPLES_<humeur>` : la règle vivait
    dans BASE, donc LOIN devant, et la dernière chose que le modèle lisait était une
    dizaine de few-shots d'absurde joyeux. Test live du 09/09 : « prêt pour la Marche
    Grise ? » a rendu un bal masqué de confiture, sans une once d'effroi.

    Le verrou exige donc la DÉMONSTRATION, là où le modèle la lit en dernier."""
    for humeur in ("NEUTRAL", "MANIA", "DEMENTIA", "BLISS"):
        bloc = getattr(sheo_data, "COMEDY_EXAMPLES_" + humeur)
        # ⚠️ Pas « le premier exemple qui cite Jyggalag » : NEUTRAL en contient déjà un où
        # le nom sert de pique jetable (« Utile est un mot de Jyggalag »). C'est permis —
        # Jyggalag reste un ennemi qu'on méprise — mais ce n'est PAS la démonstration.
        # On exige un exemple qui porte les deux : le sujet, ET la fissure.
        exemples = [
            e for e in bloc.split("\nUser: ")[1:]
            if ("jyggalag" in e.lower() or "marche grise" in e.lower())
            and "aucun aveu" in e
        ]
        assert exemples, (
            f"COMEDY_EXAMPLES_{humeur} ne DÉMONTRE pas la réaction à Jyggalag : la règle "
            "de PERSONALITY_BASE reste une interdiction nue, et les few-shots qui la "
            "suivent gagnent"
        )
        demo = exemples[0]
        for motif in _AVEUX_COMPILES:
            assert not motif.search(demo.lower()), (
                f"COMEDY_EXAMPLES_{humeur} : la démonstration elle-même avoue"
            )
