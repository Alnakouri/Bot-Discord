# -*- coding: utf-8 -*-
"""
Utilitaire de chiffrement des clés API pour les bots Discord.
Ce script chiffre les fichiers .env pour les protéger.

Usage:
    python crypto_utils.py encrypt   # Chiffre tous les .env
    python crypto_utils.py decrypt   # Déchiffre tous les .env
    python crypto_utils.py generate  # Génère une nouvelle clé maître
"""
import os
import sys
import base64
import shutil
import time
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    print("Installation de cryptography...")
    import subprocess
    try:
        subprocess.run(
            ["pip", "install", "cryptography"],
            check=True,
            capture_output=True,
            timeout=60
        )
        print("✅ cryptography installé avec succès")
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    except subprocess.CalledProcessError as e:
        print(f"❌ Échec de l'installation: {e}")
        print("Veuillez installer manuellement: pip install cryptography")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("❌ Timeout lors de l'installation")
        sys.exit(1)

# Configuration
MASTER_KEY_FILE = ".master_key"
BOT_DIRS = ["Sheogorath", "MaiqBot", "Alfred", "SugarBot", "JohnnyBot", "MalenaBot"]
BASE_DIR = Path(__file__).parent


def get_bot_key(bot_dir: Path, create=False) -> bytes | None:
    """Lit la clé maître propre du bot ou la génère si nécessaire."""
    key_path = bot_dir / MASTER_KEY_FILE
    if key_path.exists():
        with open(key_path, "rb") as f:
            return f.read().strip()
    
    if create:
        key = Fernet.generate_key()
        bot_dir.mkdir(parents=True, exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(key)
        print(f"[OK] Clé générée pour {bot_dir.name}: {key_path}")
        return key
    else:
        print(f"[!] Clé propre (.master_key) introuvable pour {bot_dir.name}")
        return None


def generate_all_bot_keys(force=False):
    """Génère une clé propre pour chaque bot avec sauvegarde si elle existe déjà."""
    for bot_dir in BOT_DIRS:
        bot_path = BASE_DIR / bot_dir
        key_path = bot_path / MASTER_KEY_FILE
        
        if key_path.exists() and not force:
            print(f"\n[🚨 SÉCURITÉ] Une clé propre existe DEJA pour {bot_dir} ! Action bloquée.")
            print("Générer une nouvelle clé rendrait le fichier .env.encrypted actuel INLISIBLE.")
            print(" -> Si vous savez ce que vous faites, utilisez: python crypto_utils.py generate --force")
            continue

        if key_path.exists() and force:
            backup_path = key_path.with_name(f".master_key.bak_{int(time.time())}")
            shutil.copy2(key_path, backup_path)
            print(f"[*] [BACKUP] L'ancienne clé de {bot_dir} a été sauvegardée dans: {backup_path.name}")

        key = Fernet.generate_key()
        bot_path.mkdir(parents=True, exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(key)
        print(f"[OK] Nouvelle clé générée pour {bot_dir}: {key_path}")


def encrypt_file(filepath: Path, fernet: Fernet):
    """Chiffre un fichier .env de façon hautement sécurisée."""
    if not filepath.exists():
        return False
    
    encrypted_path = filepath.parent / ".env.encrypted"
    
    # [BACKUP] SAUVEGARDE DE L'ANCIEN CHIFFREMENT (Empêche l'écrasement)
    if encrypted_path.exists():
        backup_path = filepath.parent / f".env.encrypted.bak_{int(time.time())}"
        shutil.copy2(encrypted_path, backup_path)
        print(f"[*] Sauvegarde de sécurité créée pour {filepath.parent.name}: {backup_path.name}")
    
    with open(filepath, "rb") as f:
        data = f.read()
    
    encrypted = fernet.encrypt(data)
    
    with open(encrypted_path, "wb") as f:
        f.write(encrypted)
    
    filepath.unlink()  # On supprime le texte en clair pour éviter toute fuite
    print(f"[OK] [LOCK] Chiffré et verrouillé: {filepath.parent.name} (.env -> .env.encrypted)")
    return True


def decrypt_file(filepath: Path, fernet: Fernet):
    """Déchiffre un fichier .env.encrypted."""
    encrypted_path = filepath.parent / ".env.encrypted"
    if not encrypted_path.exists():
        return False
    
    with open(encrypted_path, "rb") as f:
        encrypted = f.read()
    
    try:
        decrypted = fernet.decrypt(encrypted)
    except Exception as e:
        print(f"[ERREUR] Échec déchiffrement {encrypted_path}: {e}")
        return False
        
    # --- SAUVEGARDE AUTOMATIQUE ---
    if filepath.exists():
        backup_path = filepath.with_suffix(f".env.bak_{int(time.time())}")
        shutil.copy2(filepath, backup_path)
        print(f"[*] Sauvegarde de sécurité créée: {backup_path.name}")
    
    with open(filepath, "wb") as f:
        f.write(decrypted)
    
    print(f"[OK] Déchiffré: {encrypted_path} -> {filepath}")
    return True


def encrypt_all():
    """Chiffre tous les fichiers .env des bots avec leurs clés propres."""
    for bot_dir in BOT_DIRS:
        env_path = BASE_DIR / bot_dir / ".env"
        if not env_path.exists():
            continue
        key = get_bot_key(BASE_DIR / bot_dir, create=True)
        if key:
            fernet = Fernet(key)
            encrypt_file(env_path, fernet)
    
    print("\n[OK] Tous les fichiers .env présents ont été chiffrés avec leurs clés propres!")


def decrypt_all():
    """Déchiffre tous les fichiers .env.encrypted des bots."""
    for bot_dir in BOT_DIRS:
        env_path = BASE_DIR / bot_dir / ".env"
        key = get_bot_key(BASE_DIR / bot_dir, create=False)
        if key is None:
            print(f"[!] Warning: Pas de clé trouvée pour {bot_dir}")
            continue
        fernet = Fernet(key)
        decrypt_file(env_path, fernet)
    
    print("\n[OK] Tous les fichiers .env ont été déchiffrés!")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    cmd = sys.argv[1].lower()
    force = "--force" in sys.argv
    
    if cmd == "encrypt":
        encrypt_all()
    elif cmd == "decrypt":
        decrypt_all()
    elif cmd == "generate":
        generate_all_bot_keys(force=force)
    else:
        print(f"Commande inconnue: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
