# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/secure_env.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

import os
import sys
from pathlib import Path
try:
    from cryptography.fernet import Fernet
except ImportError:
    # On n'installe pas ici pour éviter les problèmes de droits dans Docker
    # Mais on prévient si c'est manquant
    Fernet = None

def load_secure_env(bot_path: Path):
    """
    Charge les variables d'environnement depuis .env ou .env.encrypted.
    Supporte la clé maître à la racine ou dans le dossier du bot.
    """
    # 1. Tenter de charger .env (clair)
    env_paths = [bot_path / ".env", bot_path.parent / ".env"]
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        os.environ[key] = value
            return True

    # 2. Tenter de charger .env.encrypted
    enc_path = bot_path / ".env.encrypted"
    if enc_path.exists():
        if not Fernet:
            print("❌ [SECURE_ENV] Cryptography manquant pour déchiffrer .env.encrypted")
            return False
            
        # Chercher la master key (dossier bot uniquement)
        master_key_file = ".master_key"
        key_locations = [bot_path / master_key_file]
        
        fernet = None
        for loc in key_locations:
            if loc.exists():
                with open(loc, "rb") as f:
                    key = f.read().strip()
                    try:
                        fernet = Fernet(key)
                        break
                    except Exception:
                        continue
        
        if not fernet:
            print(f"❌ [SECURE_ENV] .master_key introuvable ou invalide pour {bot_path.name}")
            return False

        try:
            with open(enc_path, "rb") as f:
                encrypted_data = f.read()
            decrypted_data = fernet.decrypt(encrypted_data).decode("utf-8")
            
            for line in decrypted_data.splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
            return True
        except Exception as e:
            print(f"❌ [SECURE_ENV] Erreur déchiffrement : {e}")
            return False

    return False
