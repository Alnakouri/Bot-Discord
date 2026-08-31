# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import logging
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Système de mini-jeux pour M'aiq le Menteur.
Énigmes et vérités (ou mensonges).
"""

logger = logging.getLogger(__name__)
import random
import re
from typing import Dict, Optional, Tuple

# Import Database Partagée
try:
    from shared.shared_database import set_active_riddle, get_active_riddle
except ImportError:
    # Fallback pour tests locaux si nécessaire
    print("ERREUR IMPORT SHARED_DATABASE dans minigames.py")

# ÉNIGMES DE M'AIQ

ENIGMES = [
    {
        "question": "M'aiq court beaucoup, mais ne bouge pas. Que suis-je ?",
        "answer": ["rivière", "une rivière", "le vent", "vent"],
        "hint": "Cela coule, ou cela souffle. M'aiq ne sait plus.",
        "reward": 15
    },
    {
        "question": "Plus tu en prends, plus tu en laisses derrière toi. Que sont-ils ?",
        "answer": ["pas", "des pas", "empreintes", "traces"],
        "hint": "Regarde le sable derrière toi, voyageur.",
        "reward": 10
    },
    {
        "question": "Je peux voler sans ailes. Je peux pleurer sans yeux. Que suis-je ?",
        "answer": ["nuage", "un nuage", "le nuage"],
        "hint": "Regarde le ciel. Ils te jugent.",
        "reward": 20
    },
    {
        "question": "M'aiq en a beaucoup, mais les autres disent qu'elles sont fausses. Qu'est-ce que c'est ?",
        "answer": ["histoires", "rumeurs", "mensonges", "histoires de m'aiq"],
        "hint": "C'est la vérité... ou pas.",
        "reward": 10
    },
    {
        "question": "Qu'est-ce qui disparait dès que tu dis son nom ?",
        "answer": ["silence", "le silence", "un silence"],
        "hint": "Chut...",
        "reward": 15
    },
    {
        "question": "Qu'est-ce qui appartient à M'aiq, mais que les autres utilisent plus que lui ?",
        "answer": ["nom", "ton nom", "mon nom", "le nom"],
        "hint": "Tout le monde appelle M'aiq, mais M'aiq ne s'appelle pas lui-même.",
        "reward": 20
    },
]

# Note: active_games est supprimé au profit de la DB partagée

def generate_riddle(channel_id: int) -> Optional[Dict]:
    """Génère une énigme (mais ne la sauvegarde pas encore)."""
    # Vérifier si une énigme existe déjà
    current = get_active_riddle(channel_id)
    if current:
        return None

    enigme = random.choice(ENIGMES)
    return enigme

def start_tracking_riddle(channel_id: int, question: str, answers: list, hint: str, reward: int, message_id: int, is_impossible: bool = False):
    """Sauvegarde l'énigme active après son envoi."""
    set_active_riddle(
        channel_id,
        question,
        answers,
        hint,
        reward,
        message_id,
        is_impossible=is_impossible
    )

def start_enigme(channel_id: int) -> Optional[Dict]:
    """OBSOLÈTE: Utiliser generate_riddle + start_tracking_riddle."""
    # Legacy support removed — use generate_riddle() + start_tracking_riddle()
    return None

def start_custom_enigme(channel_id: int, question: str, answers: list, hint: str, reward: int) -> Dict:
    """Démarre une énigme personnalisée (ex: générée par IA)."""
    # Vérifier si une énigme existe déjà
    current = get_active_riddle(channel_id)
    if current:
        return current

    set_active_riddle(
        channel_id,
        question,
        answers,
        hint,
        reward
    )
    return {
        "question": question,
        "answer": answers,
        "hint": hint,
        "reward": reward
    }

def normalize_answer(text: str) -> str:
    """Normalise la réponse pour comparaison floue."""
    if not text: return ""
    text = text.lower().strip()
    
    # Retirer la ponctuation
    text = re.sub(r'[^\w\s]', '', text)
    
    # Retirer les articles définis/indéfinis au début
    articles = ["le ", "la ", "les ", "un ", "une ", "du ", "des ", "l'", "d'", "l ", "d "]
    for art in articles:
        if text.startswith(art):
            text = text[len(art):].strip()
            break
            
    return text.strip()

def check_answer(channel_id: int, user_answer: str) -> Tuple[bool, Optional[int], str]:
    """
    Vérifie une réponse.
    Retourne: (correct, reward, message)
    """
    game = get_active_riddle(channel_id)
    if not game:
        return False, None, "M'aiq ne pose pas d'énigme pour le moment. Le voyageur rêve."
    
    # Vérifier la réponse
    user_answer_norm = normalize_answer(user_answer)
    valid_answers_norm = [normalize_answer(a) for a in game["answer"]]
    
    # ⚠️ C'etait un `print`, donc du bruit permanent qu'aucun niveau de log ne pouvait
    # filtrer : l'enigme est confrontee a CHAQUE message tant qu'une partie est ouverte,
    # y compris aux commandes des autres bots. Six lignes rien que pour un « !decret ».
    logger.debug("[ENIGME] reponse '%s' -> '%s' | attendu : %s",
                 user_answer, user_answer_norm, valid_answers_norm)
    
    # Check if ANY valid answer is IN the user's normalized answer using regex word boundaries
    # (More lenient than exact match but stricter than basic substring)
    is_correct = any(re.search(rf"\\b{re.escape(valid)}\\b", user_answer_norm) for valid in valid_answers_norm)
    
    if is_correct:
        # Bonne réponse !
        reward = game["reward"]
        # ON NE SUPPRIME PLUS L'ÉNIGME ICI (Multi-Gagnants)
        # delete_active_riddle(channel_id) 
        return True, reward, "C'est la vérité ! M'aiq est impressionné."
    
    # Mauvaise réponse
    # M'aiq ne donne JAMAIS la réponse.
    # Il peut donner un indice ou se moquer.
    
    return False, None, f"Ce n'est pas ça. Si vous voulez la réponse, demandez au Prince Fou (Sheogorath).\nM'aiq pense à '{game['hint']}'..."


def get_hint(channel_id: int) -> Optional[str]:
    """Donne un indice pour l'énigme en cours."""
    game = get_active_riddle(channel_id)
    if not game:
        return None
    return game.get("hint")


