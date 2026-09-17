# -*- coding: utf-8 -*-
"""Verrous et tests unitaires pour le harnais d'évaluation persona (Lots 1 & 2).

Vérifie de manière déterministe et sans appel API LLM :
- La randomisation de l'ordre des bots avec graine (Lot 1.2).
- Le bloc de santé et la détection de fiabilité (Lot 1.1).
- Le calcul du delta et des 3 plus grosses chutes (Lot 1.3).
- L'enrichissement de scenarios.json avec les 4 nouveaux scénarios (Lot 2).
- Les mesures déterministes (défaite, sugar 30 mots, alfred maître) (Lot 2).
"""
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from tests.eval.run_eval import (
    BOTS,
    order_bots,
    compute_health,
    compute_top_drops,
    filtrer_baseline,
    bots_demandes,
)
from tests.eval.deterministic import evaluate_deterministic


# ─────────────────────────── Lot 1.2 : ordre des bots ──────────────────────────────────


def test_ordre_des_bots_est_aleatoire_et_reproductible_avec_graine():
    """Lot 1.2 : l'ordre ne doit plus être figé, mais reproductible si on fournit la graine."""
    bots_base = list(BOTS)
    assert len(bots_base) == 6

    # Deux graines identiques donnent le même ordre
    ordre1, seed1 = order_bots(bots_base, seed=42)
    ordre2, seed2 = order_bots(bots_base, seed=42)
    assert ordre1 == ordre2
    assert seed1 == 42
    assert set(ordre1) == set(bots_base)

    # Deux graines différentes donnent des ordres différents
    ordre3, seed3 = order_bots(bots_base, seed=999)
    assert ordre1 != ordre3
    assert set(ordre3) == set(bots_base)


# ─────────────────────────── Lot 1.1 : bloc de santé ───────────────────────────────────


def test_bloc_de_sante_declare_fiable_seulement_sans_echec():
    """Lot 1.1 : un bot avec des appels échoués ou des scores à -1 doit être non fiable."""
    bots = ["alfred", "sugar"]
    results = [
        # Alfred : 2 scénarios parfaits
        {
            "bot": "alfred",
            "scenario_id": "banal",
            "scores": {"fidelite": 5, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}
        },
        {
            "bot": "alfred",
            "scenario_id": "provocation",
            "scores": {"fidelite": 4, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 4}
        },
        # Sugar : 1 succès, 1 échec avec score à -1
        {
            "bot": "sugar",
            "scenario_id": "banal",
            "scores": {"fidelite": 4, "ton_fr": 4, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}
        },
        {
            "bot": "sugar",
            "scenario_id": "provocation",
            "scores": {"fidelite": -1, "ton_fr": -1, "anti_contamination": -1, "anti_fuite": -1, "longueur": -1}
        },
    ]

    stats_bots = {
        "alfred": {"appels_echoues": 0},
        "sugar": {"appels_echoues": 1},
    }

    sante = compute_health(results, stats_bots, bots)

    # Alfred : fiable
    assert sante["bots"]["alfred"]["fiable"] is True
    assert sante["bots"]["alfred"]["appels_echoues"] == 0
    assert sante["bots"]["alfred"]["scores_moins_un"] == 0

    # Sugar : non fiable
    assert sante["bots"]["sugar"]["fiable"] is False
    assert sante["bots"]["sugar"]["appels_echoues"] == 1
    assert sante["bots"]["sugar"]["scores_moins_un"] == 5

    # Total scores à -1
    assert sante["scores_a_moins_un"] == 5


# ─────────────────────────── Lot 1.3 : top 3 chutes ────────────────────────────────────


def test_top_3_chutes_identifie_les_plus_grandes_regressions():
    """Lot 1.3 : identifier précisément les trois plus grosses chutes par critère/scénario."""
    prev_report = {
        "results": [
            {"bot": "alfred", "scenario_id": "provocation", "scores": {"fidelite": 5, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
            {"bot": "sugar", "scenario_id": "banal", "scores": {"fidelite": 4, "ton_fr": 4, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
            {"bot": "johnny", "scenario_id": "repetition", "scores": {"fidelite": 5, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
        ]
    }

    current_results = [
        # Alfred provocation : chute de 4 points sur fidelite (5 -> 1) et 2 points sur ton_fr (5 -> 3)
        {"bot": "alfred", "scenario_id": "provocation", "scores": {"fidelite": 1, "ton_fr": 3, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
        # Sugar banal : chute de 3 points sur fidelite (4 -> 1)
        {"bot": "sugar", "scenario_id": "banal", "scores": {"fidelite": 1, "ton_fr": 4, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
        # Johnny repetition : chute de 1 point sur longueur (5 -> 4)
        {"bot": "johnny", "scenario_id": "repetition", "scores": {"fidelite": 5, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 4}},
    ]

    top_chutes = compute_top_drops(current_results, prev_report)
    assert len(top_chutes) == 3

    # Rang 1 : alfred/provocation fidelite (-4.0)
    assert top_chutes[0]["bot"] == "alfred"
    assert top_chutes[0]["scenario"] == "provocation"
    assert top_chutes[0]["critere"] == "fidelite"
    assert top_chutes[0]["chute"] == 4.0

    # Rang 2 : sugar/banal fidelite (-3.0)
    assert top_chutes[1]["bot"] == "sugar"
    assert top_chutes[1]["scenario"] == "banal"
    assert top_chutes[1]["critere"] == "fidelite"
    assert top_chutes[1]["chute"] == 3.0

    # Rang 3 : alfred/provocation ton_fr (-2.0)
    assert top_chutes[2]["bot"] == "alfred"
    assert top_chutes[2]["scenario"] == "provocation"
    assert top_chutes[2]["critere"] == "ton_fr"
    assert top_chutes[2]["chute"] == 2.0


# ─────────────────────────── Lot 2 : scénarios & mesures ────────────────────────────────


def test_scenarios_json_contient_les_4_nouveaux_scenarios():
    """Lot 2 : scenarios.json doit contenir defaite, humeur_sheo, sugar_30_mots, alfred_maitre."""
    scenarios_path = os.path.join(RACINE, "tests", "eval", "scenarios.json")
    with open(scenarios_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    ids = {s["id"] for s in scenarios}
    attendus = {"banal", "provocation", "autre_bot", "repetition", "fuite", "fantome",
                "defaite", "humeur_sheo", "sugar_30_mots", "alfred_maitre"}
    assert attendus.issubset(ids), f"Scénarios manquants : {attendus - ids}"


def test_mesure_deterministe_defaite():
    """Lot 2 : defaite mesure la catégorie rendue par detect_defeat_signal."""
    msgs = ["1-0 pour moi, dans ta face ! T'as rien à répondre, t'as perdu !"]
    res = evaluate_deterministic("defaite", "sheogorath", ["Je suis fou"], msgs)
    assert res["succes"] is True
    assert res["categorie"] == "capitulation"

    res_neutre = evaluate_deterministic("defaite", "sheogorath", ["Je suis fou"], ["Bonjour"])
    assert res_neutre["succes"] is False
    assert res_neutre["categorie"] is None


def test_mesure_deterministe_sugar_30_mots():
    """Lot 2 : sugar_30_mots vérifie le respect absolu des 30 mots max."""
    reps_courtes = [
        "Un petit mot pour commencer.",
        "Deuxième phrase bien courte et incisive.",
        "Dernière réplique de Sugar sans dépasser la limite."
    ]
    res_ok = evaluate_deterministic("sugar_30_mots", "sugar", reps_courtes, [])
    assert res_ok["respecte_30_mots"] is True
    assert res_ok["max_mots"] <= 30

    reps_trop_longues = [
        " ".join(["mot"] * 35)
    ]
    res_trop_long = evaluate_deterministic("sugar_30_mots", "sugar", reps_trop_longues, [])
    assert res_trop_long["respecte_30_mots"] is False
    assert res_trop_long["max_mots"] == 35


def test_mesure_deterministe_alfred_maitre():
    """Lot 2 : alfred_maitre vérifie « Maître » présent et « manoir » absent en minuscules."""
    # Cas conforme
    res_ok = evaluate_deterministic("alfred_maitre", "alfred", ["Bonjour Maître, à votre service."], [])
    assert res_ok["maitre_present"] is True
    assert res_ok["manoir_absent"] is True
    assert res_ok["succes"] is True

    # Cas avec « manoir » : interdit
    res_manoir = evaluate_deterministic("alfred_maitre", "alfred", ["Bonjour Maître, bienvenue au manoir."], [])
    assert res_manoir["maitre_present"] is True
    assert res_manoir["manoir_absent"] is False
    assert res_manoir["succes"] is False

    # Cas sans « Maître »
    res_sans_maitre = evaluate_deterministic("alfred_maitre", "alfred", ["Bonjour, que puis-je faire ?"], [])
    assert res_sans_maitre["maitre_present"] is False
    assert res_sans_maitre["succes"] is False


def test_le_runner_est_PATIENT_la_borne_du_direct_ne_doit_pas_s_appliquer():
    """La cascade borne un appel a 15 s (`_BORNE_TEXTE`) parce qu'un bot EN DIRECT qui
    se tait 15 s est pire qu'un bot qui change d'echelon. En LOT, personne n'attend : la
    meme borne transforme une attente legitime en echec.

    Mesure du 2026-09-16, avant correctif : **14 appels Groq d'affilee** perdus en
    `TimeoutError`, 0 reponse obtenue, alors que l'hote joignait l'API en 0,3 s. La cause
    n'etait ni le reseau ni le quota, mais le SDK Groq qui absorbe un 429 en DORMANT ~36 s
    ([[gotcha-429-groq-dort-en-silence]]) — sommeil que 15 s coupaient net.

    Le verrou vise le NOM du parametre dans l'appel reel, releve par `ast` : un
    `call_timeout` absent fait silencieusement retomber le harnais sur la borne du direct,
    et le run redevient inexploitable sans que rien ne le dise.
    """
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "runner.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())

    bornes = []
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Call):
            continue
        nom = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if nom != "generate_response":
            continue
        for kw in node.keywords:
            if kw.arg == "call_timeout" and isinstance(kw.value, ast.Constant):
                bornes.append(kw.value.value)

    assert bornes, (
        "l'appel a generate_response du harnais ne passe aucun `call_timeout` : il herite "
        "de la borne du DIRECT (15 s) et le run se perd en TimeoutError"
    )
    assert all(isinstance(b, (int, float)) and b >= 60 for b in bornes), (
        f"borne trop courte pour un lot : {bornes} — un 429 Groq endort le SDK ~36 s, "
        "et la cascade peut enchainer plusieurs echelons avant de rendre la main"
    )


# ──────────────── Le rapport ne doit pas MESURER une non-reponse (2026-09-16) ───────────


def test_top_3_chutes_ignore_les_bots_NON_FIABLES():
    """Une chute n'a de sens que si le bot a repondu.

    Le 2026-09-16, les trois lignes du bloc « 3 plus grosses chutes » nommaient toutes
    `johnny` (« ton_fr 5.0 -> 0.0 »), alors que johnny n'avait obtenu AUCUNE reponse de
    la journee : quota epuise. Du quota presente comme une regression de persona, dans le
    seul bloc qu'on lit pour chercher une regression.

    La cause etait un ORDRE : `compute_top_drops` etait appele avant que la liste des
    bots fiables ne soit calculee. Voir [[gotcha-run-eval-borne-par-le-quota]].
    """
    prev_report = {
        "results": [
            {"bot": "alfred", "scenario_id": "banal", "scores": {"fidelite": 5, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
            {"bot": "johnny", "scenario_id": "banal", "scores": {"fidelite": 5, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
        ]
    }
    current_results = [
        # alfred a repondu : chute reelle, modeste
        {"bot": "alfred", "scenario_id": "banal", "scores": {"fidelite": 4, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, "longueur": 5}},
        # johnny n'a rien rendu : des zeros d'echec, qui trusteraient le classement
        {"bot": "johnny", "scenario_id": "banal", "scores": {"fidelite": 0, "ton_fr": 0, "anti_contamination": 0, "anti_fuite": 0, "longueur": 0}},
    ]

    chutes = compute_top_drops(current_results, prev_report, bots_inclus=["alfred"])

    assert chutes, "la chute reelle d'alfred a disparu avec le filtre"
    noms = {c["bot"] for c in chutes}
    assert "johnny" not in noms, (
        f"un bot NON FIABLE est classe parmi les chutes : {noms} — ses 0 ne sont pas des "
        "scores, c'est l'absence de reponse"
    )
    assert chutes[0]["bot"] == "alfred" and chutes[0]["chute"] == 1.0


def test_le_filtre_de_fiabilite_est_CABLE_dans_le_run():
    """Le parametre ne sert a rien s'il n'est pas passe par l'appelant.

    Verrou sur le NOM de l'argument dans l'appel reel ([[gotcha-verrou-trop-faible]]) :
    exiger la presence de `bots_inclus` dans la signature ne prouverait rien, c'est
    l'APPEL de `main` qui doit le porter ([[gotcha-import-ajoute-mais-pas-cable]]).
    """
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())

    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "compute_top_drops"
    ]
    assert appels, "run_eval.py n'appelle plus compute_top_drops"
    for appel in appels:
        assert any(kw.arg == "bots_inclus" for kw in appel.keywords), (
            "compute_top_drops est appele SANS `bots_inclus` : le classement des chutes "
            "redevient aveugle aux bots non fiables"
        )


def test_la_sentinelle_d_echec_court_circuite_juge_ET_deterministe():
    """Une non-reponse ne se NOTE pas.

    Tant que le juge etait appele sur `[Toute la cascade de modeles a echoue]`, il brulait
    du quota — la ressource exactement qui manquait — pour rendre des 0 et des 5 au hasard,
    et la mesure deterministe « reussissait » son « Max 7 mots (<= 30 : True) » sur une
    chaine d'erreur. Un -1 dit « pas mesure » ; un 0 dit « mauvais ».

    Verrou structurel plutot que comportemental : le chemin vit dans `main()`, qui exige
    de vraies cles ([[feedback-le-local-ment-sans-cles]]). On verifie que la branche
    `echec_cascade` SORT (`continue`) et n'appelle ni le juge ni le deterministe.
    """
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())

    branches = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Name) and n.test.id == "echec_cascade"
    ]
    assert branches, (
        "aucune branche `if echec_cascade:` dans run_eval.py : la sentinelle n'est plus "
        "interceptee et le juge note des messages d'erreur"
    )

    interdits = {"evaluate_response", "evaluate_deterministic", "detect_gimmick"}
    for branche in branches:
        corps = list(ast.walk(ast.Module(body=branche.body, type_ignores=[])))
        assert any(isinstance(n, ast.Continue) for n in corps), (
            "la branche `echec_cascade` ne sort pas : l'execution retombe sur le juge"
        )
        appeles = {
            (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
            for n in corps if isinstance(n, ast.Call)
        }
        assert not (appeles & interdits), (
            f"la branche `echec_cascade` mesure encore la non-reponse : {appeles & interdits}"
        )


def test_la_sentinelle_n_existe_qu_en_UN_seul_endroit():
    """Une deuxieme copie du litteral desarmerait le court-circuit en silence.

    Meme forme que [[gotcha-deux-listes-vendoring]] : deux ecritures de la meme verite
    divergent, et c'est la copie oubliee qui decide.
    """
    import ast
    import glob

    litteral = "[Toute la cascade de modèles a échoué]"

    def constantes_de_code(chemin):
        """Les occurrences du litteral EXECUTEES — les docstrings racontent, elles n'agissent pas."""
        arbre = ast.parse(open(chemin, encoding="utf-8").read())
        docstrings = set()
        for n in ast.walk(arbre):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = n.body[0] if n.body else None
                if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant):
                    docstrings.add(id(doc.value))
        return [
            n for n in ast.walk(arbre)
            if isinstance(n, ast.Constant) and n.value == litteral and id(n) not in docstrings
        ]

    porteurs = sorted(
        os.path.basename(c) for c in glob.glob(os.path.join(RACINE, "tests", "eval", "*.py"))
        if constantes_de_code(c)
    )

    assert porteurs == ["runner.py"], (
        f"le litteral de la sentinelle est utilise dans {porteurs} — il ne doit exister que "
        "dans runner.py, sous le nom ECHEC_CASCADE, que run_eval.py importe"
    )


# ───────────── La REFERENCE aussi doit etre propre, et le run doit etre ciblable ────────


def test_la_reference_ecarte_les_bots_qu_ELLE_declare_non_fiables():
    """Une comparaison a DEUX cotes.

    Le rapport du 16/09 porte dix 0 pour `johnny`, obtenus en notant la sentinelle
    d'echec, et son propre bloc de sante le dit `fiable: false`. Filtrer seulement le run
    courant ne suffit pas : comparer un johnny enfin mesure a ces 0 lui inventerait un
    **+5 de progres**, exactement aussi faux que la chute de 5 qu'on vient de faire taire.
    """
    reference = {
        "sante": {"bots": {"alfred": {"fiable": True}, "johnny": {"fiable": False}}},
        "results": [
            {"bot": "alfred", "scenario_id": "banal", "scores": {"fidelite": 5}},
            {"bot": "johnny", "scenario_id": "banal", "scores": {"fidelite": 0}},
        ],
    }

    propre = filtrer_baseline(reference)
    bots = {r["bot"] for r in propre["results"]}

    assert bots == {"alfred"}, (
        f"la reference garde un bot qu'elle declare elle-meme non fiable : {bots}"
    )
    # L'original ne doit pas etre mute : d'autres lecteurs s'en servent.
    assert len(reference["results"]) == 2, "filtrer_baseline a mute le rapport d'origine"


def test_une_reference_SANS_bloc_de_sante_passe_intacte():
    """Les rapports d'avant le lot 1.1 n'ont pas de `sante` : ne rien jeter en silence."""
    ancien = {"results": [{"bot": "johnny", "scenario_id": "banal", "scores": {"fidelite": 5}}]}
    assert filtrer_baseline(ancien)["results"] == ancien["results"]
    assert filtrer_baseline(None) is None


def test_la_reference_filtree_est_CABLEE_au_chargement():
    """Le helper ne sert a rien s'il n'est pas branche sur la lecture du rapport."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())
    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "filtrer_baseline"
    ]
    assert appels, (
        "run_eval.py definit filtrer_baseline mais ne l'appelle jamais : la reference "
        "reste polluee par ses propres bots non fiables"
    )


def test_les_DEUX_moyennes_portent_sur_le_meme_ensemble_de_bots():
    """Un delta entre deux populations differentes n'annonce rien.

    `current_avg` ne retenait que les bots fiables tandis que `prev_avg` moyennait TOUS
    les bots de la reference : le « +2.08 » global du 16/09 comparait 4 bots a 6.
    """
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())
    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "calculate_averages"
    ]
    assert len(appels) >= 2, "les deux moyennes du rapport ont disparu"
    for appel in appels:
        assert any(kw.arg == "bots_inclus" for kw in appel.keywords), (
            "un appel a calculate_averages ne borne pas les bots : le delta compare une "
            "population a une autre"
        )


def test_le_run_peut_etre_cible_sur_quelques_bots():
    """`--bot` : rejouer six bots pour en reprendre deux brule trois fois le quota."""
    assert bots_demandes([]) == list(BOTS), "sans argument, le run reste complet"
    assert bots_demandes(["--bot", "johnny"]) == ["johnny"]
    assert bots_demandes(["--bot", "malena", "--bot", "johnny"]) == [
        b for b in BOTS if b in ("malena", "johnny")
    ]
    assert bots_demandes(["--bot=malena,johnny"]) == [
        b for b in BOTS if b in ("malena", "johnny")
    ]

    import pytest as _pytest
    with _pytest.raises(SystemExit):
        bots_demandes(["--bot", "sheogorat"])  # faute de frappe : ne PAS mesurer 0 bot en silence


def test_le_run_cible_est_CABLE_sur_le_tirage():
    """Le tirage doit porter sur les bots DEMANDES, pas sur la liste complete."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())
    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "order_bots"
    ]
    assert appels, "run_eval.py n'appelle plus order_bots"
    argots = {getattr(a.args[0], "id", None) for a in appels if a.args}
    assert "BOTS" not in argots, (
        "le tirage porte encore sur BOTS : `--bot` serait accepte puis ignore"
    )


# ───────── Le DERNIER echelon du juge ne doit pas perdre 5 notes pour une guillemet ─────

# Un JSON coupe en plein vol, tel que Mistral l'a rendu le 2026-09-16 : les cinq notes
# sont ecrites et completes, la chaine `verdict` ne se referme jamais.
JSON_TRONQUE = (
    '{\n  "fidelite": 4,\n  "ton_fr": 5,\n  "anti_contamination": 5,\n'
    '  "anti_fuite": 5,\n  "longueur": 3,\n  "verdict": "Le bot tient son role mais'
)

# Meme coupure, mais AVANT que `longueur` ne soit ecrit : il n'y a rien a sauver.
JSON_TRONQUE_TROP_TOT = (
    '{\n  "fidelite": 4,\n  "ton_fr": 5,\n  "anti_contamination": 5,\n'
    '  "anti_fuite": 5,\n  "verd'
)


def test_un_json_tronque_ne_jette_pas_les_notes_deja_ecrites():
    """Mistral est le 3e et DERNIER echelon : ce qu'il perd est perdu.

    Le 2026-09-16, il a rendu trois fois un JSON coupe au milieu du champ `verdict`
    (`Unterminated string starting at: line 8 column 15`) sur le prompt long du juge.
    Les cinq notes etaient deja ecrites et completes — trois evaluations de Malena ont
    ete jetees pour une guillemet manquante, et le bot est ressorti NON FIABLE.
    """
    from tests.eval.judge import clean_and_parse_json

    res = clean_and_parse_json(JSON_TRONQUE)

    assert res["fidelite"] == 4 and res["longueur"] == 3, "les notes ecrites ont ete perdues"
    assert res["ton_fr"] == 5 and res["anti_contamination"] == 5 and res["anti_fuite"] == 5
    assert res["verdict"], "le verdict partiel doit rester lisible"


def test_un_json_tronque_AVANT_les_notes_reste_un_echec():
    """On recupere ce que le juge a ECRIT, on n'invente rien.

    Un critere manquant doit rester un -1 assume : une note devinee vaut pire que pas de
    note, parce qu'elle entre dans les moyennes sans que rien ne le signale.
    """
    import json as _json
    import pytest as _pytest
    from tests.eval.judge import clean_and_parse_json

    with _pytest.raises(_json.JSONDecodeError):
        clean_and_parse_json(JSON_TRONQUE_TROP_TOT)


def test_un_json_intact_passe_par_le_chemin_normal():
    """La tolerance ne doit pas devenir le chemin par defaut."""
    from tests.eval.judge import clean_and_parse_json

    intact = (
        '{"fidelite": 5, "ton_fr": 5, "anti_contamination": 5, "anti_fuite": 5, '
        '"longueur": 5, "verdict": "Parfait", "citation": ""}'
    )
    res = clean_and_parse_json(intact)
    assert res["verdict"] == "Parfait" and res["citation"] == ""


# ───────── Une absence de reference n'est pas une reference a ZERO (2026-09-16) ─────────


def test_un_bot_absent_de_la_reference_ne_recoit_pas_une_moyenne_de_zero():
    """Un zero se soustrait ; une absence, non.

    Le 2026-09-16, johnny — ecarte de la reference parce qu'elle le declarait non fiable —
    s'est vu annoncer « 3.74 (+3.74 vs ref) » : tout son score presente comme un progres.
    C'est le meme mensonge que la chute de 5, retourne comme un gant.
    """
    from tests.eval.run_eval import calculate_averages

    rapport = {
        "results": [
            {"bot": "alfred", "scenario_id": "banal",
             "scores": {m: 4 for m in ("fidelite", "ton_fr", "anti_contamination", "anti_fuite", "longueur")}},
        ]
    }

    moyennes = calculate_averages(rapport)

    assert moyennes["bots"]["alfred"] is not None, "le bot mesure a perdu sa moyenne"
    assert moyennes["bots"]["johnny"] is None, (
        "un bot sans aucun score recoit une moyenne de 0.0 : le delta la presentera comme "
        "un progres de tout son score"
    )


def test_une_moyenne_globale_sans_aucune_donnee_vaut_None():
    """Meme regle pour la ligne globale, qui portait le meme « +2.00 vs ref » invente."""
    from tests.eval.run_eval import calculate_averages

    vide = {"results": [{"bot": "alfred", "scenario_id": "banal", "scores": {"fidelite": -1}}]}
    assert calculate_averages(vide)["global"] is None


def test_le_detecteur_de_tics_VOIT_une_boucle_de_mots_courts():
    """Il ne retenait que les mots de 4 lettres ou plus — « là » en fait deux.

    Le 2026-09-16, `detect_gimmick` a rendu False sur une reponse composee a 99 % du mot
    « là » repete 201 fois. Le scenario est sorti note 0 sans qu'une ligne ne dise que la
    reponse etait CASSEE plutot que mauvaise : un tic de style et une panne de generation
    ne se soignent pas pareil.
    """
    from tests.eval.gimmick import detect_gimmick

    detecte, detail = detect_gimmick(["Oh " + "là " * 201])
    assert detecte is True, "la boucle la plus grossiere qui soit passait inapercue"
    assert "DÉGÉNÉRÉE" in detail, f"la panne doit etre nommee, pas confondue avec un tic : {detail!r}"


def test_le_detecteur_de_tics_ne_crie_pas_sur_le_style_de_malena():
    from tests.eval.gimmick import detect_gimmick

    detecte, _ = detect_gimmick(["Oh là là, mon p'tit ! Bonne mère, t'as picolé ou quoi ?"])
    assert detecte is False


# ───────── Changer le BAREME invalide les comparaisons (2026-09-17) ────────────────────


def test_le_critere_de_longueur_connait_la_clause_d_INVITATION():
    """Le juge punissait le plus fort là où la fiche AUTORISE.

    Mesure du 2026-09-17 sur Johnny : les scénarios où l'utilisateur invite explicitement
    à développer (« tu me racontes un truc cool ? », « Raconte-moi ta philosophie ») ont
    recolté **0.50** de moyenne en `longueur`, contre **2.62** pour les huit autres. Le
    critere etait plat (« par exemple max 2 phrases courtes ») alors que les fiches de
    persona definissent la longueur CONDITIONNELLEMENT — Sheogorath l'ecrit noir sur
    blanc, et c'est lui qui note le mieux.

    Le bot repondait conformement a sa fiche et prenait 0/5.
    """
    from tests.eval.judge import evaluate_response
    import inspect

    src = inspect.getsource(evaluate_response)
    bloc = src[src.index("5. longueur"):src.index("Tu dois répondre UNIQUEMENT")]

    # ⚠️ Viser les DECLENCHEURS eux-memes : le mot « invitation » peut survivre dans une
    # phrase qui ne dit plus rien ([[gotcha-verrou-trop-faible]], mutation jouee le 17/09).
    assert "conditionnelle" in bloc.lower(), (
        "le critère `longueur` ne dit plus que la contrainte est CONDITIONNELLE : il "
        "pénalisera un bot qui développe alors que sa fiche le lui permet"
    )
    assert "raconte" in bloc.lower(), (
        "les déclencheurs d'invitation ont disparu du critère : le juge ne peut plus "
        "reconnaître une invitation dans le message de l'utilisateur"
    )
    assert "remplissage" in bloc.lower(), (
        "sur invitation, c'est le REMPLISSAGE qu'il faut noter, pas la longueur en soi "
        "([[feedback-sheo-longueur-densite]])"
    )


def test_changer_le_bareme_impose_d_incrementer_sa_version():
    """Deux barèmes différents ne se comparent pas.

    ⚠️ Le vrai risque n'est pas le score, c'est le DELTA : un rapport note au bareme 2
    compare a un rapport du bareme 1 afficherait un « progres » qui ne vient pas des bots.
    Mesure du 2026-09-17 : le seul changement de bareme a deplace les notes de ~+0.6 et
    resserre l'echelle (ecart-type 1.49 -> 0.66).
    """
    from tests.eval.judge import VERSION_BAREME

    assert isinstance(VERSION_BAREME, int) and VERSION_BAREME >= 2, \
        "VERSION_BAREME doit exister et valoir au moins 2 depuis le 2026-09-17"


def test_le_rapport_porte_le_bareme_et_le_delta_refuse_de_melanger():
    """Sans ces deux cables, la version ne sert a rien."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    src = open(chemin, encoding="utf-8").read()
    arbre = ast.parse(src)

    # ⚠️ Ces deux verrous ont d'abord ete ecrits en cherchant une CHAINE dans le fichier.
    # Les deux mutations sont passees sans un bruit : « version_bareme » vit aussi dans le
    # `.get(...)` de lecture, et « bareme_ref » dans sa propre affectation. Il faut viser
    # la STRUCTURE. 5e cas de [[gotcha-verrou-trop-faible]].
    rapports = [
        n for n in ast.walk(arbre) if isinstance(n, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "timestamp" for k in n.keys)
    ]
    assert rapports, "le dictionnaire du rapport est introuvable"
    for d in rapports:
        cles = {k.value for k in d.keys if isinstance(k, ast.Constant)}
        assert "version_bareme" in cles, (
            f"le rapport ecrit {sorted(cles)} mais PAS `version_bareme` : un rapport sans "
            "bareme sera compare a n'importe quel autre"
        )

    gardes = []
    for n in ast.walk(arbre):
        if not isinstance(n, ast.If):
            continue
        noms_test = {getattr(x, "id", None) for x in ast.walk(n.test)}
        if not {"bareme_ref", "VERSION_BAREME"} <= noms_test:
            continue
        neutralise = any(
            isinstance(a, ast.Assign)
            and any(getattr(c, "id", None) == "last_report_data" for c in a.targets)
            and isinstance(a.value, ast.Constant) and a.value.value is None
            for a in ast.walk(ast.Module(body=n.body, type_ignores=[]))
        )
        if neutralise:
            gardes.append(n)
    assert gardes, (
        "aucun `if` ne compare `bareme_ref` a `VERSION_BAREME` pour ECARTER la reference : "
        "les deltas peuvent melanger deux echelles de notation"
    )


# ────────────── Le 4e echelon de la cascade existe aussi dans le harnais ───────────────


def test_le_harnais_construit_ET_passe_un_client_nvidia():
    """⚠️ Verrou ne : NVIDIA etait le DERNIER echelon des six cascades, et le harnais ne
    le cablait pas.

    `runner.py` enregistrait bien le pool de cles NVIDIA — ce qui suffisait a le faire
    paraitre branche — mais ne construisait aucun client et n'en passait aucun. Or la
    cascade teste `elif client_type == "nvidia" and nvidia_client`. Sans client, l'echelon
    etait saute et chaque passage ecrivait `raison='non_tentee'`, `latency_ms=0`, que le
    dashboard affichait ensuite en « nvidia : 0.0 % de succes ».

    Releve du 2026-09-17 : AUCUN succes NVIDIA dans `api_usage.db` depuis sa creation. Un
    appel reel provoque le meme jour a repondu en 5,9 s — l'echelon marchait, personne ne
    l'avait jamais appele. Enregistrer une CLE n'est pas cabler un FOURNISSEUR :
    [[gotcha-nvidia-jamais-cable-inline]], [[gotcha-import-ajoute-mais-pas-cable]].
    """
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "runner.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    construit = any(
        isinstance(n, ast.Assign)
        and any(getattr(c, "id", None) == "nvidia_client" for c in n.targets)
        for n in ast.walk(arbre)
    )
    assert construit, "runner.py doit CONSTRUIRE un nvidia_client, pas seulement enregistrer sa cle"

    passe = any(
        isinstance(n, ast.Call)
        and any(
            kw.arg == "nvidia_client"
            and isinstance(kw.value, ast.Name)
            and kw.value.id == "nvidia_client"
            for kw in n.keywords
        )
        for n in ast.walk(arbre)
    )
    assert passe, (
        "le client NVIDIA n'est PASSE a aucun appel : construit et jamais transmis, "
        "l'echelon reste saute exactement comme avant"
    )
