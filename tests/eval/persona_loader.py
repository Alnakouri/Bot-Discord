import importlib
import sys
import os

# S'assurer que le répertoire racine est dans sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

def load_persona(bot_id):
    """
    Charge le prompt système et le label du bot de manière isolée sans exécuter le client Discord.
    """
    mapping = {
        "johnny": ("JohnnyBot.johnny_data", "PERSONALITY_PROMPT", "Johnny"),
        "maiq": ("MaiqBot.maiq_data", "PERSONALITY_PROMPT", "M'aiq"),
        "alfred": ("Alfred.alfred_data", "PERSONALITY_PROMPT", "Alfred"),
        "malena": ("MalenaBot.malena_data", "PERSONALITY_PROMPT", "Malena"),
        "sugar": ("SugarBot.sugar_data", "PERSONALITY_PROMPT", "Sugar Bot"),
        "sheogorath": ("Sheogorath.sheo_data", "MOOD_PROMPTS", "Sheogorath")
    }
    
    if bot_id not in mapping:
        raise ValueError(f"Bot ID inconnu : {bot_id}")
        
    module_path, attr_name, bot_label = mapping[bot_id]
    
    try:
        mod = importlib.import_module(module_path)
        val = getattr(mod, attr_name)
        if isinstance(val, dict):
            # Cas spécial pour Sheogorath (dictionnaire d'humeurs)
            system_prompt = val.get("neutral", "")
        else:
            system_prompt = val
        return {
            "system_prompt": system_prompt,
            "bot_label": bot_label
        }
    except Exception as e:
        print(f"Erreur de chargement pour {bot_id} ({module_path}) : {e}")
        raise e


# Le filtre de sortie de chaque bot : ce qu'il RETIRE du texte du LLM avant de l'envoyer
# dans Discord. Sans lui, le harnais note la sortie BRUTE du modèle — donc un texte que
# personne ne lit : Sheogorath était puni pour 17/17 astérisques qu'il retire lui-même,
# et un filet ajouté à un bot nu n'aurait bougé aucun score.
# Cf. [[gotcha-le-harnais-mesure-le-modele-pas-le-bot]].
#
# ⚠️ Le module visé ne doit PAS importer `discord` : le harnais tourne sans client.
# C'est la raison d'être de `SugarBot/sugar_filtres.py`.
# Un bot absent de cette table n'a pas (encore) de filtre : son texte passe inchangé.
FILTRES = {
    "sugar": ("SugarBot.sugar_filtres", "filtre_sortie"),
    "sheogorath": ("Sheogorath.sheo_llm", "filtre_sortie"),
}


def load_filtre(bot_id):
    """Rend le filtre de sortie du bot, ou l'identité s'il n'en a pas.

    L'identité, jamais une exception : quatre bots sur six n'ont aucun filet au
    2026-09-17 (LOT 1 du plan), et un harnais qui refuserait de les mesurer ne
    mesurerait plus rien.
    """
    entree = FILTRES.get(bot_id)
    if not entree:
        return lambda texte, message_utilisateur=None: texte

    module_path, attr_name = entree
    mod = importlib.import_module(module_path)
    return getattr(mod, attr_name)
