import os
import glob
import logging

def ensure_data_writable(bot_name: str, data_dir: str, logger: logging.Logger = None):
    """
    Vérifie que le dossier de données et les fichiers JSON du bot sont inscriptibles.
    Logge un WARNING si ce n'est pas le cas.
    """
    if logger is None:
        logger = logging.getLogger(bot_name)
    
    if not os.path.exists(data_dir):
        return

    # Check directory
    if not os.access(data_dir, os.W_OK):
        logger.warning(f"⚠️ [Perms] Le dossier {data_dir} n'est pas inscriptible (W_OK=False).")

    # Check bot JSON files
    pattern = os.path.join(data_dir, f"{bot_name}_*.json*")
    files = glob.glob(pattern)
    for file in files:
        if not os.access(file, os.W_OK):
            logger.warning(f"⚠️ [Perms] Le fichier {file} n'est pas inscriptible (W_OK=False). Les sauvegardes d'état vont échouer.")
