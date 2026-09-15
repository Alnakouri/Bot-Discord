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
