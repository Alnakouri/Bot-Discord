# -*- coding: utf-8 -*-
"""Verrou : le harnais d'évaluation note ce que l'UTILISATEUR lit, pas la sortie du modèle.

Le 2026-09-17, `tests/eval/runner.py` rendait la réponse brute de la cascade, sans aucun
post-traitement de bot. Deux effets, en sens inverse, tous deux faux :

  - Sheogorath était noté sur 17 réponses sur 17 contenant des astérisques qu'il retire
    lui-même avant l'envoi : son score de `fidelite` était un plancher, pas une mesure.
  - Un filet ajouté à un bot nu n'aurait bougé AUCUN score, et on aurait conclu à l'échec
    d'un correctif que le harnais ne regardait simplement pas.

Ces tests visent les NOMS dans le fichier réel (AST), jamais une reconstitution de la
logique : un verrou qui retape le traitement reste vert quand le vrai chemin le perd.
"""
import ast
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from tests.eval.persona_loader import FILTRES, load_filtre


def _arbre(chemin_relatif):
    chemin = os.path.join(RACINE, chemin_relatif)
    with open(chemin, encoding="utf-8") as f:
        return ast.parse(f.read(), filename=chemin)


def _noms_appeles(noeud):
    """Tous les noms de fonctions appelées sous ce nœud (`f(...)` et `o.f(...)`)."""
    noms = set()
    for n in ast.walk(noeud):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                noms.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                noms.add(n.func.attr)
    return noms


def _fonction(arbre, nom):
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    return None


# ───────────────────────── Le harnais applique bien le filtre ──────────────────────────


def test_runner_importe_et_appelle_load_filtre():
    """L'import ne suffit pas : [[gotcha-import-ajoute-mais-pas-cable]]."""
    arbre = _arbre("tests/eval/runner.py")

    importe = any(
        isinstance(n, ast.ImportFrom) and any(a.name == "load_filtre" for a in n.names)
        for n in ast.walk(arbre)
    )
    assert importe, "runner.py doit importer load_filtre depuis persona_loader"

    fonction = _fonction(arbre, "run_scenario_for_bot")
    assert fonction is not None, "run_scenario_for_bot a disparu de runner.py"
    assert "load_filtre" in _noms_appeles(fonction), (
        "run_scenario_for_bot doit APPELER load_filtre : sans l'appel, le harnais note "
        "de nouveau la sortie brute du modele"
    )


def test_runner_applique_le_filtre_a_la_reponse_avec_le_message():
    """Le filtre doit recevoir la RÉPONSE et le MESSAGE — pas être appelé à vide.

    Le message n'est pas décoratif : chez Sheogorath, c'est lui qui permet de couper
    l'ouverture-perroquet qui hurle l'insulte en écho.
    """
    arbre = _arbre("tests/eval/runner.py")
    fonction = _fonction(arbre, "run_scenario_for_bot")

    appels = [
        n for n in ast.walk(fonction)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "filtre_sortie"
    ]
    assert appels, "le filtre chargé n'est jamais appliqué à la réponse"
    assert any(
        len(a.args) == 2
        and isinstance(a.args[0], ast.Name) and a.args[0].id == "response"
        and isinstance(a.args[1], ast.Name) and a.args[1].id == "user_msg"
        for a in appels
    ), "filtre_sortie doit être appelé avec (response, user_msg)"


def test_un_bot_sans_filtre_declare_rend_son_texte_inchange():
    """Jamais d'exception : quatre bots sur six n'ont aucun filet, il faut les mesurer
    quand même — sinon le harnais cesse de mesurer au lieu de mesurer moins."""
    identite = load_filtre("bot-qui-n-existe-pas")
    texte = "*Soupir imperceptible* Le the est servi, Monsieur."
    assert identite(texte) == texte
    assert identite(texte, "un message") == texte


# ─────────────── Les bots exposent la même porte, et passent par elle ──────────────────


def test_les_filtres_declares_partagent_la_meme_signature():
    """Le harnais appelle `filtre(texte, message)` sans savoir quel bot il tient."""
    for bot_id in FILTRES:
        filtre = load_filtre(bot_id)
        assert filtre("Bonjour.", "salut") is not None, f"{bot_id} : signature incompatible"
        assert filtre("") == "", f"{bot_id} : un texte vide doit rester vide"


def test_les_filtres_declares_retirent_les_asterisques():
    """Le comportement qui justifie tout le reste, mesuré sur les deux bots équipés."""
    for bot_id in FILTRES:
        filtre = load_filtre(bot_id)
        sortie = filtre("Le fromage est *tres* important, mortel !", "et le fromage ?")
        assert "*" not in sortie, f"{bot_id} laisse passer des asterisques : {sortie!r}"


def test_sugar_passe_par_son_module_de_filtres_et_plus_par_du_code_inline():
    """Un second enchaînement, parallèle, finirait par diverger de celui que l'on mesure."""
    arbre = _arbre("SugarBot/bot_sugar.py")
    appels = _noms_appeles(arbre)
    assert "filtre_sortie" in appels, "bot_sugar.py doit passer par filtre_sortie"
    assert "_strip_didascalies" not in appels, (
        "bot_sugar.py rappelle _strip_didascalies directement : le chemin du bot et celui "
        "du harnais ont recommence a diverger"
    )


def test_sheogorath_passe_par_son_filtre_partage():
    arbre = _arbre("Sheogorath/sheo_llm.py")
    postprocess = _fonction(arbre, "postprocess_response")
    assert postprocess is not None, "postprocess_response a disparu de sheo_llm.py"

    appels = _noms_appeles(postprocess)
    assert "filtre_sortie" in appels, "postprocess_response doit passer par filtre_sortie"
    for perdu in ("strip_meta_narration", "strip_bare_stage_directions",
                  "strip_markdown_emphasis"):
        assert perdu not in appels, (
            f"postprocess_response rappelle {perdu} en direct : le nettoyage vit a deux "
            "endroits, et c'est le score qui mentira"
        )
