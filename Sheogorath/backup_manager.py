import os
DATA_DIR = os.getenv("DATA_DIR", ".")
# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Système de backup automatique pour les bots Discord.
Sauvegarde quotidienne des fichiers importants.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
import json

# Configuration
BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "backups"
MAX_BACKUPS = 7  # Conserver 7 jours de backups

# Fichiers à sauvegarder
FILES_TO_BACKUP = [
    "bots_database.db",
    "Sheogorath/sheogorath_memory.json",
    "Sheogorath/sheo_facts.json",
    "Sheogorath/sheo_punishments.json",
    "MaiqBot/maiq_data.json",
    "Alfred/alfred_memory.json",
]


def create_backup():
    """Crée une sauvegarde de tous les fichiers importants."""
    # Créer le dossier de backup si nécessaire
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Nom du backup avec date
    backup_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / backup_name
    backup_path.mkdir(exist_ok=True)
    
    backed_up = []
    errors = []
    
    for file_path in FILES_TO_BACKUP:
        src = BASE_DIR / file_path
        if src.exists():
            try:
                # Créer les sous-dossiers si nécessaire
                dst = backup_path / file_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                
                shutil.copy2(src, dst)
                backed_up.append(file_path)
            except Exception as e:
                errors.append(f"{file_path}: {e}")
        else:
            errors.append(f"{file_path}: Fichier non trouvé")
    
    # Créer un fichier de métadonnées
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "files_backed_up": backed_up,
        "errors": errors
    }
    
    with open(backup_path / os.path.join(DATA_DIR, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"✅ [BACKUP] Sauvegarde créée: {backup_path}")
    print(f"   Fichiers: {len(backed_up)} | Erreurs: {len(errors)}")
    
    # Nettoyer les anciens backups
    cleanup_old_backups()
    
    return backup_path


def cleanup_old_backups():
    """Supprime les backups de plus de MAX_BACKUPS jours."""
    if not BACKUP_DIR.exists():
        return
    
    # Lister tous les backups
    backups = sorted([d for d in BACKUP_DIR.iterdir() if d.is_dir()])
    
    # Supprimer les plus anciens si on dépasse la limite
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        try:
            shutil.rmtree(oldest)
            print(f"🗑️ [BACKUP] Ancien backup supprimé: {oldest.name}")
        except Exception as e:
            print(f"❌ [BACKUP] Erreur suppression {oldest.name}: {e}")


def restore_backup(backup_name: str) -> bool:
    """Restaure un backup spécifique."""
    backup_path = BACKUP_DIR / backup_name
    
    if not backup_path.exists():
        print(f"❌ [BACKUP] Backup non trouvé: {backup_name}")
        return False
    
    restored = []
    errors = []
    
    for file_path in FILES_TO_BACKUP:
        src = backup_path / file_path
        dst = BASE_DIR / file_path
        
        if src.exists():
            try:
                # Créer une sauvegarde du fichier actuel avant restauration
                if dst.exists():
                    shutil.copy2(dst, str(dst) + ".pre_restore")
                
                shutil.copy2(src, dst)
                restored.append(file_path)
            except Exception as e:
                errors.append(f"{file_path}: {e}")
    
    print(f"✅ [BACKUP] Restauration terminée: {len(restored)} fichiers")
    if errors:
        print(f"⚠️ Erreurs: {errors}")
    
    return len(errors) == 0


def list_backups() -> list:
    """Liste tous les backups disponibles."""
    if not BACKUP_DIR.exists():
        return []
    
    backups = []
    for d in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if d.is_dir():
            metadata_file = d / os.path.join(DATA_DIR, "metadata.json")
            if metadata_file.exists():
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                backups.append({
                    "name": d.name,
                    "timestamp": metadata.get("timestamp"),
                    "files": len(metadata.get("files_backed_up", []))
                })
            else:
                backups.append({
                    "name": d.name,
                    "timestamp": None,
                    "files": 0
                })
    
    return backups


# Fonction pour être appelée par les tâches planifiées
async def scheduled_backup():
    """Fonction async pour backup planifié."""
    create_backup()


if __name__ == "__main__":
    # Test manuel
    print("Création d'un backup...")
    create_backup()
    print("\nBackups disponibles:")
    for b in list_backups():
        print(f"  - {b['name']} ({b['files']} fichiers)")
