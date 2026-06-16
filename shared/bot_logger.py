# SHARED LOGGING MODULE FOR DISCORD BOTS

import logging
import os
from datetime import datetime
import json
from logging.handlers import RotatingFileHandler

class JSONLHandler(logging.Handler):
    """Handler qui écrit les logs en JSON Lines pour le dashboard."""
    
    def __init__(self, log_dir, bot_name):
        super().__init__()
        self.filepath = os.path.join(log_dir, f"{bot_name}_structured.jsonl")
    
    def emit(self, record):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "bot": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno
        }
        # Ajouter des champs extra si présents (permet un tracking avancé depuis d'autres modules sans changer la signature de base)
        for key in ["api_name", "api_key_index", "error_code", "user_id", "channel_id", "latency_ms"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Ne jamais crasher le bot pour un log

def setup_logger(bot_name: str, log_dir: str = "logs"):
    """
    Configure un logger avec sortie fichier, console et JSONL (Dashboard).
    
    Args:
        bot_name: Nom du bot (ex: "sheogorath", "maiq", "alfred")
        log_dir: Dossier des logs (défaut: "logs")
    
    Returns:
        Logger configuré
    """
    # Créer le dossier logs si nécessaire
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Nom du fichier avec date
    log_filename = os.path.join(log_dir, f"{bot_name}_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    # Configuration du logger
    logger = logging.getLogger(bot_name)
    logger.setLevel(logging.INFO)
    
    # Éviter les doublons si déjà configuré
    if logger.handlers:
        return logger
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-7s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Handler fichier (rotation : 5 MB max, 3 backups)
    file_handler = RotatingFileHandler(
        log_filename, encoding='utf-8',
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Handler console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Handler JSON Lines pour le dashboard
    jsonl_handler = JSONLHandler(log_dir, bot_name)
    jsonl_handler.setLevel(logging.INFO)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(jsonl_handler)
    
    logger.info(f"=== {bot_name.upper()} STARTED ===")
    
    return logger


# logger.info("Message de log")
# logger.warning("Avertissement")
# logger.error("Erreur")
