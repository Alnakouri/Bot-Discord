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
        "zaji": ("ZajiBot.zaji_data", "PERSONALITY_PROMPT", "Onizuka"),
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
