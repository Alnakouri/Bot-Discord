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
        # ⚠️ Le budget n'est plus absolu depuis le 2026-09-19 : sur decision d'Ahmed,
        # Sugar peut aller jusqu'a ~60 mots quand on lui demande EXPLICITEMENT de
        # raconter ou d'expliquer (sa fiche a ete amendee en meme temps).
        #
        # La mesure compare donc chaque reponse au budget de SON message, au lieu de
        # les juger toutes a 30. Exempter les messages d'invitation aurait été plus
        # simple et aurait rendu la mesure aveugle la ou elle compte le plus : c'est
        # justement sur un « raconte » qu'un modele deborde.
        #
        # ⚠️ Le budget est importe du BOT, jamais recopie ici : deux baremes paralleles
        # divergent, et c'est alors le score qui ment
        # ([[gotcha-test-qui-retape-la-logique]]).
        from SugarBot.sugar_filtres import budget_demande

        mots_par_reponse = [len(r.split()) for r in responses] if responses else [0]
        max_mots = max(mots_par_reponse)
        budgets = [budget_demande(user_messages[i] if i < len(user_messages) else "")
                   for i in range(len(mots_par_reponse))]
        depassements = [(m, b) for m, b in zip(mots_par_reponse, budgets) if m > b]
        respecte_30 = not depassements
        return {
            "type": "sugar_30_mots",
            "max_mots": max_mots,
            "mots_par_reponse": mots_par_reponse,
            "budgets_applicables": budgets,
            "respecte_30_mots": respecte_30,
            "succes": respecte_30 if bot_id == "sugar" else True,
            "detail": (f"Max {max_mots} mots, budgets {budgets} "
                       f"(dans le budget : {respecte_30})")
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
