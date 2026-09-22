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

    ⚠️ 2026-09-18 : la borne est devenue CHOISISSABLE (`--borne-du-direct`), donc l'appel
    porte une conditionnelle et non plus une constante. Ce que le verrou protege n'a pas
    change d'un pouce — c'est le DEFAUT qui doit rester patient. Il relit donc la branche
    `else` de la conditionnelle, celle qui s'applique quand personne ne demande rien. Une
    borne courte glissee la reviendrait a reintroduire le defaut de 2026-09-16 en laissant
    un drapeau pour alibi.
    """
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "runner.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())

    def _valeurs_par_defaut(noeud):
        """La ou les valeurs que prend `call_timeout` quand aucun drapeau n'est passe.

        Une constante vaut pour elle-meme ; une conditionnelle ne vaut que par sa branche
        `else`, la seule qu'un run ordinaire emprunte.
        """
        if isinstance(noeud, ast.Constant):
            return [noeud.value]
        if isinstance(noeud, ast.IfExp):
            return _valeurs_par_defaut(noeud.orelse)
        return []

    bornes = []
    conditionnelles = []
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Call):
            continue
        nom = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if nom != "generate_response":
            continue
        for kw in node.keywords:
            if kw.arg != "call_timeout":
                continue
            bornes.extend(_valeurs_par_defaut(kw.value))
            if isinstance(kw.value, ast.IfExp):
                conditionnelles.append(kw.value)

    assert bornes, (
        "l'appel a generate_response du harnais ne passe aucun `call_timeout` exploitable : "
        "il herite de la borne du DIRECT (15 s) et le run se perd en TimeoutError"
    )
    assert all(isinstance(b, (int, float)) and b >= 60 for b in bornes), (
        f"borne trop courte pour un lot : {bornes} — un 429 Groq endort le SDK ~36 s, "
        "et la cascade peut enchainer plusieurs echelons avant de rendre la main"
    )

    # Si la borne est conditionnelle, elle ne peut l'etre que sur le drapeau prevu pour ca.
    # Sans ce point, n'importe quelle variable de portee pourrait raccourcir le lot en
    # laissant la branche `else` presentable.
    for cond in conditionnelles:
        noms = {n.id for n in ast.walk(cond.test) if isinstance(n, ast.Name)}
        assert "borne_du_direct" in noms, (
            f"la borne du lot depend de {noms or 'une expression opaque'} et non de "
            "`borne_du_direct` : le lot peut devenir presse sans que personne l'ait demande"
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
        source = f.read()
    arbre = ast.parse(source, filename=chemin)

    # 2026-09-19 : le client n'est plus une variable de module mais un element de
    # l'attelage rendu par `attelage_du_bot`, donc lie par DEPAQUETAGE. Le verrou accepte
    # les deux formes ; ce qu'il protege est inchange — un client NVIDIA doit etre
    # CONSTRUIT quelque part, pas seulement voir sa cle enregistree.
    def _noms_affectes(noeud):
        for cible in noeud.targets:
            for sous in ast.walk(cible):
                if isinstance(sous, ast.Name):
                    yield sous.id

    construit = any(
        isinstance(n, ast.Assign) and "nvidia_client" in set(_noms_affectes(n))
        for n in ast.walk(arbre)
    ) or "OpenAI(api_key=nvidia_key" in source
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


# ────────── La réponse BRUTE est gardée à côté de la filtrée (2026-09-17) ──────────────


def test_le_runner_rend_la_filtree_ET_la_brute():
    """⚠️ Sans la brute, on ne peut pas dire QUI a agi.

    Le 2026-09-17, après avoir posé un filet déterministe (LOT 1) ET réécrit les fiches
    (LOT 2), la question « c'est le filet ou la fiche ? » est restée sans réponse : le
    rapport ne gardait que le texte filtré, où il n'y a plus une astérisque par
    construction. Trancher aurait coûté un run entier avec le filtre désarmé.
    """
    import asyncio
    import tests.eval.runner as runner

    async def _faux_appel(**kwargs):
        return "**Gras** et *pose son torchon* une didascalie."

    vrai = runner.generate_response
    runner.generate_response = _faux_appel
    try:
        scenario = {"id": "sonde", "user_messages": ["salut"], "transcript": ""}
        filtrees, brutes, _echelons = asyncio.run(
            runner.run_scenario_for_bot("alfred", scenario)
        )
    finally:
        runner.generate_response = vrai

    assert len(filtrees) == len(brutes) == 1, "les deux listes doivent aller de pair"
    assert "*" in brutes[0], "la BRUTE doit garder les astérisques du modèle"
    assert "*" not in filtrees[0], "la FILTRÉE doit être ce que l'utilisateur lit"


def test_chaque_resultat_stocke_la_brute_a_cote_de_la_filtree():
    """Un dict de résultat qui porte `responses` sans `responses_brutes` reperd l'info."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    dicts_de_resultat = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "responses" for k in n.keys)
    ]
    assert dicts_de_resultat, "aucun dict de résultat trouvé dans run_eval.py"
    for d in dicts_de_resultat:
        cles = {k.value for k in d.keys if isinstance(k, ast.Constant)}
        assert "responses_brutes" in cles, (
            "un résultat porte `responses` sans `responses_brutes` : la mesure qui sépare "
            "le FILET de la FICHE est perdue pour ce cas"
        )


def test_le_compte_d_asterisques_separe_avant_et_apres():
    from tests.eval.run_eval import compte_asterisques

    results = [
        {"bot": "alfred",
         "responses": ["Le the est servi."],
         "responses_brutes": ["*pose son torchon* Le the est servi."]},
        {"bot": "sugar",
         "responses": ["Rien a signaler."],
         "responses_brutes": ["Rien a signaler."]},
    ]
    compte = compte_asterisques(results)
    assert compte["alfred"] == {"avant": 1, "apres": 0, "total": 1, "echelons": {}}, (
        "alfred : le modèle en produit, le filet les retire — c'est le FILET qui agit"
    )
    assert compte["sugar"] == {"avant": 0, "apres": 0, "total": 1, "echelons": {}}, (
        "sugar : rien à retirer — c'est la FICHE qui tient"
    )


# ───────── L'échelon qui a répondu, à côté du compte (2026-09-18) ──────────────────────


def _scenario(*messages):
    return {"id": "sonde", "user_messages": list(messages), "transcript": ""}


def _sans_tracage():
    """Remplace le vrai traceur par un muet : un test n'écrit pas dans `api_usage.db`.

    [[gotcha-pytest-pollue-data]] — et l'espion du runner DÉLÈGUE au traceur qu'il
    trouve, donc c'est bien ici qu'il faut couper.
    """
    import shared.llm_cascade as llm_cascade

    vrai = llm_cascade.tracer_appel
    llm_cascade.tracer_appel = lambda *a, **k: None
    return llm_cascade, vrai


def test_le_runner_nomme_l_echelon_qui_a_repondu():
    """⚠️ Le compte d'astérisques AVANT filtrage appartient au MODÈLE autant qu'à la fiche.

    Sugar est passée de 0/17 le 17/09 à 11/17 le 18/09 sans qu'un mot de sa fiche ne
    bouge : Gemini était à sec, ministral-14b avait répondu à sa place. Lu sans son
    échelon, le tableau accusait la fiche.
    [[gotcha-le-compte-brut-est-fausse-par-l-echelon-qui-a-repondu]]
    """
    import asyncio
    import tests.eval.runner as runner

    llm_cascade, vrai_traceur = _sans_tracage()

    async def _faux_appel(**kwargs):
        # Comme la vraie cascade : l'échelon raté, puis celui qui répond.
        llm_cascade.tracer_appel(bot="alfred", api="gemini", modele="un-modele-gemini",
                                 index_cle=0, succes=False, raison="429")
        llm_cascade.tracer_appel(bot="alfred", api="mistral", modele="ministral-14b",
                                 index_cle=0, succes=True)
        return "Le the est servi, Monsieur."

    vrai_appel = runner.generate_response
    runner.generate_response = _faux_appel
    try:
        _f, _b, echelons = asyncio.run(runner.run_scenario_for_bot("alfred", _scenario("salut")))
    finally:
        runner.generate_response = vrai_appel
        llm_cascade.tracer_appel = vrai_traceur

    assert echelons == ["mistral/ministral-14b"], (
        f"l'echelon qui a REPONDU doit etre nomme, pas celui qui a echoue : {echelons}"
    )


def test_une_cascade_MUETTE_ne_nomme_aucun_echelon():
    """⚠️ Le trou qu'une mutation a ouvert : sans le filtre sur `succes`, l'espion garde
    le DERNIER échelon tracé — et quand toute la cascade a échoué, c'est un échelon qui
    n'a rien produit. Le rapport nommerait alors nemotron comme auteur d'une réponse qui
    n'existe pas, et le compte d'astérisques la lui attribuerait.

    Tant que la cascade répond, le dernier tracé EST le bon (elle s'arrête là) : c'est
    exactement le cas où un verrou trop faible reste vert.
    [[gotcha-verrou-trop-faible]]
    """
    import asyncio
    import tests.eval.runner as runner

    llm_cascade, vrai_traceur = _sans_tracage()

    async def _cascade_muette(**kwargs):
        for api, modele in (("gemini", "flash-lite"), ("mistral", "ministral-14b"),
                            ("nvidia", "nemotron")):
            llm_cascade.tracer_appel(bot="alfred", api=api, modele=modele,
                                     index_cle=0, succes=False, raison="429")
        return None

    vrai_appel = runner.generate_response
    runner.generate_response = _cascade_muette
    try:
        filtrees, brutes, echelons = asyncio.run(
            runner.run_scenario_for_bot("alfred", _scenario("salut"))
        )
    finally:
        runner.generate_response = vrai_appel
        llm_cascade.tracer_appel = vrai_traceur

    assert echelons == [None], (
        f"aucun echelon n'a repondu : le rapport doit le dire, pas nommer le dernier "
        f"essai rate — {echelons}"
    )
    assert filtrees == [runner.ECHEC_CASCADE] and brutes == [runner.ECHEC_CASCADE], (
        "la sentinelle d'echec doit rester intacte des deux cotes"
    )


def test_l_espion_rend_le_traceur_intact_et_ne_lui_mange_rien():
    """L'observation ne doit RIEN retirer à la base : l'espion délègue, il ne remplace pas.

    Et il se retire de lui-même — un traceur laissé en place fuirait sur tout le reste
    de la suite.
    """
    import shared.llm_cascade as llm_cascade

    vus_par_la_base = []
    vrai = llm_cascade.tracer_appel
    llm_cascade.tracer_appel = lambda **k: vus_par_la_base.append(k["modele"])
    muet = llm_cascade.tracer_appel
    try:
        with runner_echelon() as vus:
            llm_cascade.tracer_appel(bot="b", api="mistral", modele="ministral-14b",
                                     index_cle=0, succes=True)
        assert vus == ["mistral/ministral-14b"]
        assert vus_par_la_base == ["ministral-14b"], (
            "l'espion a avale l'appel : la base perdrait cette ligne pendant les runs"
        )
        assert llm_cascade.tracer_appel is muet, "l'espion ne s'est pas retire"
    finally:
        llm_cascade.tracer_appel = vrai


def runner_echelon():
    import tests.eval.runner as runner
    return runner._echelon_qui_repond()


def test_l_historique_rend_le_texte_FILTRE_par_defaut():
    """⚠️ Sur Discord, le tour suivant relit le message ENVOYÉ — donc filtré.

    Un harnais qui renvoie la sortie brute au modèle mesure une conversation qui n'a
    jamais eu lieu. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]]
    """
    import asyncio
    import tests.eval.runner as runner

    llm_cascade, vrai_traceur = _sans_tracage()
    histoires = []

    async def _faux_appel(**kwargs):
        histoires.append([m["parts"][0] for m in kwargs["conversation_history"]])
        return "*pose son torchon* Le the est servi."

    vrai_appel = runner.generate_response
    runner.generate_response = _faux_appel
    try:
        asyncio.run(runner.run_scenario_for_bot("alfred", _scenario("salut", "et encore ?")))
    finally:
        runner.generate_response = vrai_appel
        llm_cascade.tracer_appel = vrai_traceur

    assert len(histoires) == 2, "les deux tours doivent avoir eu lieu"
    memoire = histoires[1][-1]
    assert "*" not in memoire, f"l'historique doit porter le texte FILTRE : {memoire!r}"
    assert "pose son torchon" not in memoire, "la didascalie devait tomber avec le filtre"


def test_l_historique_brut_remet_le_texte_NON_filtre():
    """Le drapeau qui isole la variable restée ouverte le 2026-09-17.

    Depuis que l'historique est assaini, le modèle s'imite lui-même sans astérisques : la
    baisse de production peut venir de la fiche, de cet historique, ou des deux. Sans ce
    drapeau, trancher coûte un run entier filtre désarmé — et ce run-là ne mesurerait plus
    ce que l'utilisateur lit.
    """
    import asyncio
    import tests.eval.runner as runner

    llm_cascade, vrai_traceur = _sans_tracage()
    histoires = []

    async def _faux_appel(**kwargs):
        histoires.append([m["parts"][0] for m in kwargs["conversation_history"]])
        return "*pose son torchon* Le the est servi."

    vrai_appel = runner.generate_response
    runner.generate_response = _faux_appel
    try:
        filtrees, _b, _e = asyncio.run(runner.run_scenario_for_bot(
            "alfred", _scenario("salut", "et encore ?"), historique_brut=True
        ))
    finally:
        runner.generate_response = vrai_appel
        llm_cascade.tracer_appel = vrai_traceur

    memoire = histoires[1][-1]
    assert "*pose son torchon*" in memoire, (
        f"avec --historique-brut, le modele doit relire sa sortie BRUTE : {memoire!r}"
    )
    assert "*" not in filtrees[0], (
        "le drapeau ne touche QUE l'historique : ce qui est NOTE reste le texte filtre"
    )


def test_le_compte_d_asterisques_nomme_l_echelon_de_chaque_bot():
    from tests.eval.run_eval import compte_asterisques

    results = [
        {"bot": "sugar",
         "responses": ["Rien.", "Rien non plus."],
         "responses_brutes": ["*hausse un sourcil* Rien.", "Rien non plus."],
         "echelons": ["mistral/ministral-14b", "gemini/un-modele-gemini"]},
    ]
    compte = compte_asterisques(results)["sugar"]
    assert compte["avant"] == 1 and compte["total"] == 2
    assert compte["echelons"] == {
        "mistral/ministral-14b": 1,
        "gemini/un-modele-gemini": 1,
    }, "chaque reponse doit etre rattachee a l'echelon qui l'a produite"


def test_le_resume_d_echelons_classe_du_plus_servi_au_moins():
    from tests.eval.run_eval import _resume_echelons

    resume = _resume_echelons({"gemini/flash-lite": 2, "mistral/ministral-14b": 15})
    assert resume.startswith("mistral/ministral-14b x15"), resume
    assert "gemini/flash-lite x2" in resume
    assert _resume_echelons({}) == "echelon inconnu", (
        "un compte sans echelon doit le DIRE, pas afficher une case vide"
    )


def test_le_drapeau_historique_brut_est_lu_et_cable():
    """[[gotcha-import-ajoute-mais-pas-cable]] : la fonction doit aussi être APPELÉE,
    et son résultat passé à `run_scenario_for_bot`."""
    import ast
    from tests.eval.run_eval import historique_brut_demande

    assert historique_brut_demande([]) is False
    assert historique_brut_demande(["--bot", "alfred"]) is False
    assert historique_brut_demande(["--historique-brut"]) is True
    assert historique_brut_demande(["--bot", "alfred", "--historique-brut"]) is True

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "run_scenario_for_bot"
    ]
    assert appels, "run_scenario_for_bot n'est plus appele dans run_eval.py"
    assert all(
        any(kw.arg == "historique_brut" for kw in a.keywords) for a in appels
    ), (
        "un appel a run_scenario_for_bot ne passe pas `historique_brut` : le drapeau "
        "serait lu, annonce en console, et sans le moindre effet"
    )


def test_le_rapport_ecrit_le_mode_d_historique():
    """Un rapport qui ne dit pas comment il a ete mene se compare a n'importe quoi."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    rapports = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "version_bareme" for k in n.keys)
    ]
    assert rapports, "le dict de rapport a disparu de run_eval.py"
    for d in rapports:
        cles = {k.value for k in d.keys if isinstance(k, ast.Constant)}
        assert "historique_brut" in cles, (
            "le rapport doit porter `historique_brut` : sans lui, un run experimental "
            "devient en silence la reference du run normal suivant"
        )


def test_chaque_resultat_stocke_l_echelon_a_cote_des_reponses():
    """Même leçon que pour la brute : un résultat sans son échelon se lit à l'envers."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    dicts_de_resultat = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "responses" for k in n.keys)
    ]
    assert dicts_de_resultat, "aucun dict de résultat trouvé dans run_eval.py"
    for d in dicts_de_resultat:
        cles = {k.value for k in d.keys if isinstance(k, ast.Constant)}
        assert "echelons" in cles, (
            "un resultat porte `responses` sans `echelons` : impossible de dire quel "
            "modele a produit ces asterisques"
        )



# ───────── La console cp1252 ne doit pas TUER le run avant le 1er appel (2026-09-18) ────
#
# Vu en vrai le 18/09 : `run_eval.py --historique-brut` est tombe sur un
# `UnicodeEncodeError` a la banniere, AVANT d'avoir appele un seul modele. Le coupable
# n'est pas le `⚠️` — c'est la console Windows, qui rend du cp1252. Appauvrir les
# messages un par un ne tient pas : il en reste six autres dans le fichier, et le
# prochain qu'on ecrira retombera dans le trou.


def test_le_harnais_force_UTF_8_sur_sa_sortie():
    """Verrou sur le NOM : `sys.stdout`/`sys.stderr` doivent etre reconfigures en UTF-8."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    flux_vus = set()
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)):
            continue
        if noeud.func.attr != "reconfigure":
            continue
        encodage = next(
            (kw.value.value for kw in noeud.keywords
             if kw.arg == "encoding" and isinstance(kw.value, ast.Constant)),
            None,
        )
        if encodage is None or encodage.lower().replace("-", "") != "utf8":
            continue
        # La cible est soit `sys.stdout.reconfigure(...)`, soit une variable de boucle
        # qui parcourt `(sys.stdout, sys.stderr)` : on lit les noms du fichier entier.
        flux_vus.add(ast.unparse(noeud.func.value))

    assert flux_vus, (
        "aucun `reconfigure(encoding=\"utf-8\")` dans run_eval.py : un seul caractere "
        "hors cp1252 dans un message fera tomber le run sur une console Windows"
    )

    source = open(chemin, encoding="utf-8").read()
    for flux in ("sys.stdout", "sys.stderr"):
        assert flux in source, f"{flux} n'est pas reconfigure"


def test_un_message_hors_cp1252_SURVIT_a_l_import_du_harnais():
    """Le verrou structurel ne prouve rien : on le VERIFIE sur une vraie console cp1252."""
    import subprocess

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"       # la console Windows de l'utilisateur
    env["PYTHONPATH"] = RACINE

    # Sans la reconfiguration, ce `print` leve `UnicodeEncodeError` et le code sort a 1.
    code = "import tests.eval.run_eval; print('⚠️ ok')"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, env=env, cwd=RACINE, timeout=120,
    )

    assert proc.returncode == 0, (
        "importer le harnais ne repare pas la sortie : "
        + proc.stderr.decode("utf-8", "replace")[-600:]
    )
    assert b"ok" in proc.stdout


def test_un_argument_inconnu_ne_lance_PAS_un_run_complet():
    """`run_eval.py --help` depensait le quota du jour en croyant afficher une aide.

    Le harnais lit ses drapeaux a la main, sans `argparse` : tout le reste etait ignore en
    SILENCE et le run partait sur les six bots (~60 appels de bot, autant de juge). Vu le
    2026-09-18. Une faute de frappe (`--bots alfred`) faisait pire : elle mesurait les six
    alors que l'utilisateur en demandait un.
    """
    import pytest as _pytest
    from tests.eval.run_eval import verifie_arguments

    # Ce qui est reconnu passe sans bruit.
    verifie_arguments([])
    verifie_arguments(["--bot", "alfred"])
    verifie_arguments(["--bot=malena,johnny", "--historique-brut"])

    # `--help` sort a 0, et sans avoir rien appele.
    with _pytest.raises(SystemExit) as sortie:
        verifie_arguments(["--help"])
    assert sortie.value.code == 0
    with _pytest.raises(SystemExit) as sortie:
        verifie_arguments(["-h"])
    assert sortie.value.code == 0

    # Tout le reste est refuse plutot que joue.
    for argv in (
        ["--bots", "alfred"],                  # faute de frappe : mesurait les SIX
        ["--bot-alfred"],
        ["--historique_brut"],                 # tiret bas : le drapeau etait sans effet
        ["--bot"],                             # valeur manquante : retombait sur les six
        ["--bot="],                            # idem, en silence
        ["alfred"],                            # le nom nu, sans son drapeau
    ):
        with _pytest.raises(SystemExit) as sortie:
            verifie_arguments(argv)
        assert sortie.value.code != 0, f"{argv} est passe : le run complet serait parti"


def test_la_verification_des_arguments_passe_AVANT_le_premier_appel():
    """Un garde place apres le premier appel payant ne garde plus rien."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    mains = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "main"
    ]
    assert mains, "run_eval.py n'a plus de `main`"

    corps = mains[0].body
    appels = [
        i for i, stmt in enumerate(corps)
        if isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Name)
        and stmt.value.func.id == "verifie_arguments"
    ]
    assert appels, "`main` n'appelle plus `verifie_arguments` : un typo relance les six bots"
    assert appels[0] == 0, (
        "`verifie_arguments()` n'est plus la PREMIERE instruction de `main` : "
        "ce qui la precede s'execute pour un argument qui sera refuse"
    )


def test_la_recitation_de_la_fiche_est_MESUREE():
    """Un modele tres obeissant ressort les EXEMPLES de sa fiche mot pour mot.

    Vu le 2026-09-18 chez Alfred : « Mieux avant cette question, helas. » est une ligne
    de demonstration du prompt, rendue telle quelle par gemma-4. Le juge ne peut pas le
    voir — il trouve la reponse parfaitement fidele, et elle l'est. L'anti-tic non plus :
    il compare les reponses ENTRE elles, jamais a la fiche.
    """
    from tests.eval.run_eval import plus_longue_citation, compte_recitation, _RECITATION_MIN

    fiche = ("Tu es Alfred, majordome. Exemples : 'Comment ca va ?' -> "
             "'Mieux avant cette question, helas.' ; 'T'es nul' -> 'Fort possible.'")

    taille, fragment = plus_longue_citation("Bonjour. Mieux avant cette question, hélas. ☕", fiche)
    assert taille >= _RECITATION_MIN, f"recitation manquee ({taille} car.)"
    assert "mieux avant cette question" in fragment

    # Les accents et la casse ne doivent pas faire rater la citation.
    assert plus_longue_citation("MIEUX AVANT CETTE QUESTION, HELAS", fiche)[0] >= _RECITATION_MIN

    # Une reponse originale qui partage juste du vocabulaire ne doit PAS etre comptee.
    petite, _ = plus_longue_citation(
        "Monsieur confond un majordome avec une encyclopedie.", fiche)
    assert petite < _RECITATION_MIN, f"faux positif : {petite} caracteres"

    # Cablage sur la VRAIE fiche : on lui rend un morceau d'elle-meme, pris a l'execution.
    # ⚠️ Ne PAS coder en dur une phrase de la fiche ici : elle a justement ete reecrite le
    # 2026-09-18 pour en retirer les repliques, et ce test serait tombe avec elle alors que
    # la mesure, elle, marchait.
    from tests.eval.persona_loader import load_persona

    vraie = load_persona("alfred")["system_prompt"]
    morceau = vraie[400:400 + 60]
    compte = compte_recitation([{"bot": "alfred", "responses_brutes": [morceau]}])
    assert compte["alfred"]["citations"] == 1, compte

    # Et une reponse qui ne vient pas de la fiche ne doit rien declencher.
    propre = compte_recitation([
        {"bot": "alfred", "responses_brutes": ["Le chat du voisin a encore mange la pizza."]},
    ])
    assert propre["alfred"]["citations"] == 0, propre


def test_la_recitation_est_ECRITE_dans_le_rapport():
    """Recalculee plus tard, elle dependrait de la fiche du jour, pas de celle du run."""
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    rapports = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "version_bareme" for k in n.keys)
    ]
    assert rapports, "le dictionnaire du rapport a disparu"
    assert any(
        any(isinstance(k, ast.Constant) and k.value == "recitation" for k in r.keys)
        for r in rapports
    ), "le rapport n'ecrit pas `recitation` : la mesure ne survivrait pas au run"


# ──────── La borne du direct est CHOISISSABLE, et cablee jusqu'a la cascade (18/09) ────────


def test_la_borne_du_direct_est_CABLEE_du_drapeau_jusqu_a_la_cascade():
    """`--borne-du-direct` doit atteindre `generate_response`, pas seulement etre lu.

    Ce drapeau existe parce que la borne patiente du lot (90 s) CACHE ce que le direct
    refuserait. Mesure du 2026-09-18 sur les 67 appels `google/gemma-4-31b-it` de la passe
    qui l'a valide en tete de cascade : mediane 12,4 s, et 26 au-dela de 15 s — comptes en
    succes par le harnais, refuses en production. Le rapport annoncait « gemma x17 » sur
    dix-sept tours quand le chat n'en voit que six sur dix.

    Un drapeau lu mais non transmis rendrait exactement les memes chiffres qu'un run
    ordinaire, en affichant son avertissement : le pire des cas, une mesure fausse qui se
    croit corrigee. Le verrou suit donc la chaine entiere, maillon par maillon
    ([[gotcha-import-ajoute-mais-pas-cable]]).
    """
    import ast

    # 1. run_eval : le drapeau est lu, puis PASSE au runner sous son nom.
    chemin_run = os.path.join(RACINE, "tests", "eval", "run_eval.py")
    arbre_run = ast.parse(open(chemin_run, encoding="utf-8").read())

    passages = [
        kw
        for node in ast.walk(arbre_run)
        if isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None)) == "run_scenario_for_bot"
        for kw in node.keywords
        if kw.arg == "borne_du_direct"
    ]
    assert passages, (
        "run_eval lit `--borne-du-direct` mais ne le passe pas a run_scenario_for_bot : "
        "le run resterait patient en annoncant le contraire"
    )
    assert all(isinstance(kw.value, ast.Name) and kw.value.id == "borne_du_direct" for kw in passages), (
        "le harnais passe autre chose que la valeur lue sur la ligne de commande"
    )

    # 2. runner : le parametre existe, il est FAUX par defaut, et c'est lui qui commande
    #    la borne de l'appel (verifie par le test de patience, juste au-dessus).
    chemin_runner = os.path.join(RACINE, "tests", "eval", "runner.py")
    source_runner = open(chemin_runner, encoding="utf-8").read()
    arbre_runner = ast.parse(source_runner)

    fonctions = [
        n for n in ast.walk(arbre_runner)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_scenario_for_bot"
    ]
    assert fonctions, "run_scenario_for_bot a disparu du runner"
    signature = fonctions[0].args
    noms = [a.arg for a in signature.args]
    assert "borne_du_direct" in noms, (
        "run_scenario_for_bot n'accepte pas `borne_du_direct` : le drapeau s'arrete au CLI"
    )
    rang = noms.index("borne_du_direct") - (len(noms) - len(signature.defaults))
    defaut = signature.defaults[rang]
    assert isinstance(defaut, ast.Constant) and defaut.value is False, (
        "le defaut de `borne_du_direct` n'est pas False : tous les runs deviendraient "
        "presses, et un 429 Groq endormi redeviendrait un echec"
    )

    # 3. La borne demandee est bien celle du DIRECT, pas un nombre recopie a la main.
    #    Un litteral divergerait le jour ou `_BORNE_TEXTE` bouge.
    assert "_BORNE_TEXTE if borne_du_direct" in source_runner, (
        "la borne du mode direct doit etre `_BORNE_TEXTE` lui-meme, pas une copie : "
        "sinon le harnais mesure une borne que la production n'applique plus"
    )


def test_deux_bornes_differentes_MASQUENT_les_deltas():
    """Un run borne au direct ne se compare pas a un run patient.

    Les deux ne font pas repondre les memes ECHELONS : borne au direct, une tete de
    cascade lente est refusee et c'est le suivant qui sert. Comparer les deux attribuerait
    aux fiches de persona un ecart qui vient du chronometre — l'erreur exacte, dans sa
    version modele, du 2026-09-17 au soir.
    """
    source = open(os.path.join(RACINE, "tests", "eval", "run_eval.py"), encoding="utf-8").read()
    assert '"borne_du_direct": borne_du_direct' in source, (
        "le rapport ne note pas sous quelle borne il a ete mene : plus aucun run posterieur "
        "ne pourra savoir s'il est comparable"
    )
    assert 'get("borne_du_direct", False)) != borne_du_direct' in source, (
        "rien ne masque les deltas entre deux bornes differentes"
    )


# ────── Le harnais mesure chaque bot avec SES cles, pas celles de Johnny (19/09) ──────


def test_chaque_bot_est_mesure_avec_SES_PROPRES_cles():
    """Jusqu'au 2026-09-19, `runner.py` chargeait le `.env` de JohnnyBot et faisait tourner
    les SIX personas dessus.

    Une passe complete — ~102 appels de bot, autant de juge — tapait donc six fois sur le
    seul projet Google de Johnny, quand la production en a six separes. D'ou le « plancher
    de bruit » qu'on documentait comme une fatalite : deux passes identiques bougeaient de
    jusqu'a 6/17 sur la colonne AVANT « parce que le tirage de l'ORDRE decide qui a le
    quota frais ». Il n'y avait pas de loterie — le premier bot tire vidait la reserve de
    Johnny, les suivants retombaient sur ministral, qui produit une didascalie 3 fois sur 4.

    En PRODUCTION les epuisements ne sont pas simultanes : sur 41 minutes ou au moins un
    bot est ecarte (api_usage.db, 17-18/09), **37 ne concernent qu'un seul bot**. Les
    quotas sont bien separes ; ils ne l'etaient que dans le harnais.

    ⚠️ Verrou en STRUCTURE : les cles n'existent pas en CI, et un `MagicMock` rendrait une
    fausse cle non-None ([[feedback-le-local-ment-sans-cles]]).
    """
    import ast

    chemin = os.path.join(RACINE, "tests", "eval", "runner.py")
    source = open(chemin, encoding="utf-8").read()
    arbre = ast.parse(source)

    fonctions = [
        n for n in ast.walk(arbre)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_scenario_for_bot"
    ]
    assert fonctions, "run_scenario_for_bot a disparu"
    corps = fonctions[0]

    # 1. l'attelage est demande POUR CE BOT, avec l'identifiant recu en argument.
    appels = [
        n for n in ast.walk(corps)
        if isinstance(n, ast.Call)
        and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "attelage_du_bot"
    ]
    assert appels, (
        "run_scenario_for_bot ne demande pas les cles du bot mesure : il retombe sur un "
        "pool global, c'est-a-dire les cles d'un seul bot pour les six"
    )
    assert any(
        a.args and isinstance(a.args[0], ast.Name) and a.args[0].id == "bot_id"
        for a in appels
    ), "l'attelage est demande pour autre chose que le bot en cours de mesure"

    # 2. le code remplace ne doit plus exister : un pool construit au niveau du MODULE
    #    reprendrait la main en silence, puisqu'il porterait le meme nom.
    #    ([[gotcha-import-ajoute-mais-pas-cable]] : exiger aussi l'ABSENCE du remplace.)
    for noeud in arbre.body:
        if isinstance(noeud, ast.Assign):
            cibles = {t.id for t in noeud.targets if isinstance(t, ast.Name)}
            assert not (cibles & {"key_manager", "groq_client", "mistral_client", "nvidia_client"}), (
                f"{cibles} est reconstruit au niveau du MODULE : les six bots repartageraient "
                "les memes cles, et le correctif serait annule sans qu'un test ne bouge"
            )


def test_le_dossier_du_bot_est_DEDUIT_de_la_table_des_personas():
    """Une seconde liste ecrite a la main divergerait en silence.

    C'est exactement ce que les deux listes de vendoring ont fait
    ([[gotcha-deux-listes-vendoring]]), et le harnais a deja paye une liste ecrite a la
    main qui excluait un bot sur six ([[gotcha-un-bot-sur-six-manque-toujours]]).

    Ce test-ci ne demande AUCUNE cle : il verifie que les six identifiants mappent vers un
    dossier de bot qui existe reellement sur le disque.
    """
    from tests.eval.persona_loader import PERSONAS
    from tests.eval.runner import _dossier_du_bot

    assert len(PERSONAS) == 6, f"la table des personas n'a plus six bots : {sorted(PERSONAS)}"

    for bot_id in PERSONAS:
        dossier = _dossier_du_bot(bot_id)
        assert dossier.is_dir(), f"{bot_id} pointe vers {dossier}, qui n'existe pas"

    dossiers = {str(_dossier_du_bot(b)) for b in PERSONAS}
    assert len(dossiers) == 6, (
        f"deux bots partagent un dossier de cles : {sorted(dossiers)} — ils partageraient "
        "alors un quota, ce que ce correctif existe precisement pour eviter"
    )


def test_le_harnais_REFUSE_un_bot_sans_cles(tmp_path, monkeypatch):
    """Sans cles lisibles, le harnais mesurait avec celles du bot charge AVANT, en silence.

    `load_secure_env` ne leve jamais : il rend False. Le refus doit donc lire ce RETOUR.
    Ce test ne demande aucune cle : il le verifie sur un dossier vide, ici comme en CI.
    """
    import pytest as _pytest          # style du fichier : pytest est importe localement
    from tests.eval import runner

    monkeypatch.setattr(runner, "_ATTELAGES", {})
    monkeypatch.setattr(runner, "_dossier_du_bot", lambda bot_id: tmp_path)
    with _pytest.raises(RuntimeError, match="aucune cle lisible"):
        runner.attelage_du_bot("alfred")

