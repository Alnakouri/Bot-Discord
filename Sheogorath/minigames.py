# -*- coding: utf-8 -*-
"""
Mini-jeu du fromage de Sheogorath (!fromage).

Les énigmes de M'aiq qui vivaient aussi ici ont été retirées avec elles (SUITE 17,
2026-09-28) : plus aucun bot ne lit la table `riddles`.
"""

import random
from typing import Dict


def jeu_fromage(user_id: int) -> Dict:
    """
    Le jeu du fromage mystérieux pour Sheogorath.
    Retourne un dictionnaire avec le nom du fromage, l'effet et les points de réputation.
    """
    fromages = [
        {"nom": "Vieux Boulogne", "effet": "maladie", "points": -5},
        {"nom": "Roquefort d'Oblivion", "effet": "puissance", "points": 10},
        {"nom": "Camembert de Mania", "effet": "joie", "points": 5},
        {"nom": "Cheddar de Jyggalag (Rassis)", "effet": "confusion", "points": 2},
        {"nom": "Brie de Démence", "effet": "mélancolie", "points": 5},
        {"nom": "Fromage de Chèvre à tête de Wabbajack", "effet": "folie", "points": 15},
        {"nom": "Emmental Invisible", "effet": "hallucination", "points": 8},
        {"nom": "Croûte de Parmesan de Pelagius", "effet": "confusion", "points": 1},
    ]

    result = random.choice(fromages)

    # Si DATABASE_AVAILABLE, on pourrait logguer ici mais c'est fait dans le bot
    return result
