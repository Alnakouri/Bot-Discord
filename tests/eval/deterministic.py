# -*- coding: utf-8 -*-
"""Mesures déterministes pour les scénarios récents (Lot 2).

Ces mesures sont calculées par du code et non par le juge LLM, évitant ainsi
la fatigue ou l'aléa du juge pour des règles absolues (comptage de mots, mots-clés, catégories).
Elles vivent à côté des scores du juge sans altérer les 5 métriques standards.
"""
from shared.repartee_lessons import detect_defeat_signal


def evaluate_deterministic(scenario_id: str, bot_id: str, responses: list[str], user_messages: list[str]) -> dict:
    """Calcule les métriques déterministes associées à un scénario du Lot 2.

    Retourne un dictionnaire vide si le scénario n'a pas de mesure déterministe dédiée.
    """
    if scenario_id == "defaite":
        dernier_msg = user_messages[-1] if user_messages else ""
        cat = detect_defeat_signal(dernier_msg)
        return {
            "type": "defaite",
            "categorie": cat,
            "succes": cat is not None,
            "detail": f"Catégorie rendue : {cat}" if cat else "Aucun signal détecté"
        }

    if scenario_id == "sugar_30_mots":
        mots_par_reponse = [len(r.split()) for r in responses] if responses else [0]
        max_mots = max(mots_par_reponse)
        respecte_30 = all(m <= 30 for m in mots_par_reponse)
        return {
            "type": "sugar_30_mots",
            "max_mots": max_mots,
            "mots_par_reponse": mots_par_reponse,
            "respecte_30_mots": respecte_30,
            "succes": respecte_30 if bot_id == "sugar" else True,
            "detail": f"Max {max_mots} mots (<= 30 : {respecte_30})"
        }

    if scenario_id == "alfred_maitre":
        texte = " ".join(responses).lower() if responses else ""
        # [gotcha-verrou-trop-faible] 2e cas : vérification en minuscules
        maitre_present = ("maître" in texte or "maitre" in texte)
        manoir_absent = ("manoir" not in texte)
        succes = maitre_present and manoir_absent
        return {
            "type": "alfred_maitre",
            "maitre_present": maitre_present,
            "manoir_absent": manoir_absent,
            "succes": succes if bot_id == "alfred" else True,
            "detail": f"Maître: {maitre_present}, Manoir absent: {manoir_absent}"
        }

    return {}
