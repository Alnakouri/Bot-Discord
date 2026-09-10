import json
import glob
import os
import shutil
from datetime import datetime
import argparse
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

def _is_register_fact(fact):
    # Regex to detect facts that describe the conversation tone/register rather than the user
    pattern = re.compile(
        r"(semble obsédé|semble particulièrement|métaphore|comparaison|provocation|provoquer|insulte|expression|ton de|registre|rhétorique)",
        re.IGNORECASE
    )
    return bool(pattern.search(fact))

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Purge les faits auto-générés sur le registre")
    parser.add_argument("--appliquer", action="store_true", help="Appliquer les modifications")
    args = parser.parse_args()

    files = glob.glob(str(RACINE / "data" / "*facts*.json"))
    
    if not files:
        print("Aucun fichier *facts*.json trouvé.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = RACINE / "data" / "backups_faits"
    
    if args.appliquer and not backup_dir.exists():
        backup_dir.mkdir(parents=True)

    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Erreur de lecture de {file_path}: {e}")
            continue
            
        modified = False
        new_data = {}
        
        filename = os.path.basename(file_path)
        print(f"\n[{filename}]")
        
        for user_id, facts in data.items():
            new_facts = []
            for fact_item in facts:
                # Gérer les différences de format (string vs dict)
                fact_text = fact_item["fact"] if isinstance(fact_item, dict) else fact_item
                
                if _is_register_fact(fact_text):
                    print(f"  [À RETIRER] (User {user_id}) : {fact_text}")
                    modified = True
                else:
                    print(f"  [GARDÉ]     (User {user_id}) : {fact_text}")
                    new_facts.append(fact_item)
                    
            if new_facts:
                new_data[user_id] = new_facts
                
        if args.appliquer and modified:
            backup_path = backup_dir / f"{filename}.{timestamp}.bak"
            shutil.copy2(file_path, backup_path)
            print(f"  -> Sauvegarde créée : {backup_path.name}")
            
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)
            print(f"  -> Fichier {filename} mis à jour.")

if __name__ == "__main__":
    main()
