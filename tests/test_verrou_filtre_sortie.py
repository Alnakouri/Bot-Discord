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


# ─────────────── LOT 1 : Filet déterministe sur les bots équipés ──────────────────────


def test_filtres_contient_les_six_bots():
    """FILTRES doit contenir les 6 bots : pas cinq ([[gotcha-un-bot-sur-six-manque-toujours]])."""
    bots_attendus = {"alfred", "johnny", "maiq", "malena", "sheogorath", "sugar"}
    assert set(FILTRES.keys()) == bots_attendus, f"FILTRES incomplet : {set(FILTRES.keys())} != {bots_attendus}"


def test_filtres_retirent_didascalie_entiere_et_gardent_emphase():
    """Pour LES SIX : retire la didascalie entière et garde l'emphase simple.

    ⚠️ Ce test a d'abord été écrit sur CINQ bots, sheogorath retiré de la liste sans un
    mot. L'exclusion était fondée — son filtre ne retirait que les MARQUEURS, donc
    « *Soupir imperceptible…* » ressortait « Soupir imperceptible… », une didascalie en
    clair — mais un bot muet dans une liste ne signale rien : `FILTRES` contenait bien
    les six, le compte semblait complet, et un bot sur six ne faisait pas le travail.
    Le filtre de Sheo a été aligné (deux étages) le 2026-09-17 ; la liste reste donc
    `FILTRES` lui-même, jamais une liste écrite à la main.
    [[gotcha-un-bot-sur-six-manque-toujours]]
    """
    for bot_id in FILTRES:
        filtre = load_filtre(bot_id)

        # 1. Didascalie en tête : tout le segment tombe, aucun astérisque
        t1 = filtre("*Soupir imperceptible, mais audible…* Le thé est servi, Monsieur.")
        assert t1 == "Le thé est servi, Monsieur.", f"{bot_id} n'a pas retiré la didascalie en tête : {t1!r}"

        # 2. Didascalie après ponctuation : tout le segment tombe
        t2 = filtre("*Souffle sur ma clope imaginaire* Qu'est-ce que tu veux ?")
        assert t2 == "Qu'est-ce que tu veux ?", f"{bot_id} n'a pas retiré la didascalie : {t2!r}"

        t3 = filtre("*soupir dramatique* C'est ridicule.")
        assert t3 == "C'est ridicule.", f"{bot_id} n'a pas retiré la didascalie : {t3!r}"

        # 3. Emphase : marqueurs retirés, mots gardés
        t4 = filtre("J'ai lu *The Times* ce matin.")
        assert t4 == "J'ai lu The Times ce matin.", f"{bot_id} n'a pas préservé l'emphase : {t4!r}"


def test_filtres_ne_coupent_pas_imperatifs_ni_pseudos():
    """Ne coupe pas « Souris ! », ne touche pas `le_dev`."""
    for bot_id in FILTRES:
        filtre = load_filtre(bot_id)
        t1 = filtre("Souris ! Le monde n'est pas si sombre.")
        assert t1.startswith("Souris !"), f"{bot_id} a coupé un impératif de dialogue : {t1!r}"

        t2 = filtre("Bonjour @le_dev !")
        assert "le_dev" in t2, f"{bot_id} a touché un pseudo contenant des underscores : {t2!r}"


def _a_re_sub_fact(arbre):
    """Vérifie si re.sub(r'<fact>...') est appelé dans l'arbre."""
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call):
            is_sub = (isinstance(n.func, ast.Attribute) and n.func.attr == "sub") or (
                isinstance(n.func, ast.Name) and n.func.id == "sub"
            )
            if is_sub and n.args and "<fact>" in str(getattr(n.args[0], "value", "")):
                return True
    return False


def test_alfred_passe_par_filtre_sortie_sans_re_sub_fact():
    arbre = _arbre("Alfred/bot_alfred.py")
    assert "filtre_sortie" in _noms_appeles(arbre), "bot_alfred.py doit appeler filtre_sortie"
    assert not _a_re_sub_fact(arbre), "Les re.sub(<fact>...) doivent avoir disparu de bot_alfred.py"


def test_johnny_passe_par_filtre_sortie_sans_re_sub_fact():
    arbre = _arbre("JohnnyBot/bot_johnny.py")
    assert "filtre_sortie" in _noms_appeles(arbre), "bot_johnny.py doit appeler filtre_sortie"
    assert not _a_re_sub_fact(arbre), "Les re.sub(<fact>...) doivent avoir disparu de bot_johnny.py"


def test_maiq_passe_par_filtre_sortie_sans_re_sub_fact():
    arbre = _arbre("MaiqBot/bot_maiq.py")
    assert "filtre_sortie" in _noms_appeles(arbre), "bot_maiq.py doit appeler filtre_sortie"
    assert not _a_re_sub_fact(arbre), "Les re.sub(<fact>...) doivent avoir disparu de bot_maiq.py"


def test_malena_generate_response_hybrid_passe_par_filtre():
    arbre = _arbre("MalenaBot/bot_malena.py")
    f_pub = _fonction(arbre, "generate_response_hybrid")
    assert f_pub is not None, "generate_response_hybrid a disparu de bot_malena.py"
    assert "filtre_sortie" in _noms_appeles(f_pub), "generate_response_hybrid doit appeler filtre_sortie"
    assert "_generate_response_hybrid_brut" in _noms_appeles(f_pub), (
        "generate_response_hybrid doit envelopper _generate_response_hybrid_brut"
    )

    # Vérifier qu'aucun return _texte_branche ne subsiste hors de _generate_response_hybrid_brut
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name != "_generate_response_hybrid_brut":
            for r in ast.walk(n):
                if isinstance(r, ast.Return) and isinstance(r.value, ast.Name):
                    assert r.value.id != "_texte_branche", (
                        f"return _texte_branche trouvé dans {n.name} hors de _generate_response_hybrid_brut"
                    )
