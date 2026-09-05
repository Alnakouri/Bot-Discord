import os
import json
import asyncio
from datetime import datetime
import glob
import re

class LogCollector:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.logs_dirs = [
            os.path.join(root_dir, "logs"),
            os.path.join(root_dir, "data", "logs")
        ]
        
    def _parse_text_log_line(self, line: str, bot_name: str) -> dict:
        """Parse une ligne de log texte en dict structuré."""
        pattern = r"(\d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*(.*)"
        match = re.search(pattern, line)
        if match:
            # Reconstruire une date ISO approximative à partir de l'heure
            now = datetime.now()
            time_str = match.group(1)
            # Hypothèse: c'est la date d'aujourd'hui (on filtre après)
            iso_timestamp = f"{now.strftime('%Y-%m-%d')}T{time_str}"
            
            return {
                "timestamp": iso_timestamp,
                "level": match.group(2).strip(),
                "message": match.group(3).strip(),
                "bot": bot_name,
                "source": "file_txt"
            }
        return None

    def get_logs(self, bot=None, level=None, search=None, date_from=None, date_to=None, page=1, per_page=100):
        all_logs = []
        
        # 1. Parcourir les fichiers strutturés JSONL
        for log_dir in self.logs_dirs:
            if not os.path.exists(log_dir): continue
            
            # JSONL logs
            pattern = os.path.join(log_dir, "*_structured.jsonl")
            if bot:
                pattern = os.path.join(log_dir, f"{bot}_structured.jsonl")
                
            for filepath in glob.glob(pattern):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip(): continue
                            try:
                                log_entry = json.loads(line)
                                log_entry["source"] = "file_jsonl"
                                all_logs.append(log_entry)
                            except json.JSONDecodeError:
                                pass  # ligne de journal illisible : on passe a la suivante
                except Exception:
                    pass  # le collecteur de journaux ne peut pas se plaindre dans les journaux

        # 2. S'il n'y a pas beaucoup de logs, fallback sur les .log (simplifié pour perfs)
        # On pourrait ajouter le parsing des .log ici si nécessaire
        
        # 3. Filtrer
        filtered = []
        for entry in all_logs:
            if level and entry.get("level") != level: continue
            if bot and entry.get("bot") != bot: continue
            if search and search.lower() not in entry.get("message", "").lower(): continue
            if date_from and entry.get("timestamp") < date_from: continue
            if date_to and entry.get("timestamp") > date_to: continue
            filtered.append(entry)
            
        # 4. Trier (plus récent d'abord)
        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Pagination
        start = (page - 1) * per_page
        end = start + per_page
        
        return {
            "total": len(filtered),
            "page": page,
            "per_page": per_page,
            "data": filtered[start:end]
        }

    async def watch(self, bot=None):
        """Générateur async pour streamer les nouvelles entrées de logs."""
        last_positions = {}
        
        while True:
            # Identifier les fichiers à surveiller
            log_files = []
            for log_dir in self.logs_dirs:
                if not os.path.exists(log_dir): continue
                pattern = f"{bot}_structured.jsonl" if bot else "*_structured.jsonl"
                import glob
                log_files.extend(glob.glob(os.path.join(log_dir, pattern)))
            
            for filepath in log_files:
                if not os.path.exists(filepath): continue
                
                # Si nouveau fichier, commencer à la fin
                if filepath not in last_positions:
                    last_positions[filepath] = os.path.getsize(filepath)
                    continue
                
                current_size = os.path.getsize(filepath)
                if current_size > last_positions[filepath]:
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            f.seek(last_positions[filepath])
                            for line in f:
                                if line.strip():
                                    try:
                                        log_entry = json.loads(line)
                                        log_entry["source"] = "stream"
                                        yield log_entry
                                    except json.JSONDecodeError:
                                        pass  # ligne de journal illisible : on passe a la suivante
                            last_positions[filepath] = f.tell()
                    except Exception as e:
                        print(f"Error watching {filepath}: {e}")
                elif current_size < last_positions[filepath]:
                    # Fichier tronqué (rotation ?)
                    last_positions[filepath] = 0
            
            await asyncio.sleep(1) # Vérifier chaque seconde
