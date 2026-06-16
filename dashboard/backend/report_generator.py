import os
import json
from datetime import datetime

class ReportGenerator:
    def __init__(self, db_path):
        self.db_path = db_path
        # Assurer l'existence du dossier rapports
        self.reports_dir = os.path.join(os.path.dirname(os.path.dirname(db_path)), "dashboard", "reports")
        os.makedirs(self.reports_dir, exist_ok=True)
        
    def generate_single_error_report(self, bot_name, error_type, error_message, traceback, context_event):
        """Généré automatiquement par le hook on_error."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"CRASH_{bot_name}_{timestamp}.md"
        filepath = os.path.join(self.reports_dir, filename)
        
        content = f"""# 🚨 CRASH REPORT - {bot_name.upper()}
## Informations Générales
- **Date** : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **Bot** : {bot_name}
- **Type d'Erreur** : {error_type}
- **Événement** : {context_event}

## Message d'Erreur
```
{error_message}
```

## Traceback Complet
```python
{traceback}
```

## Instruction pour IA
Veuillez analyser ce traceback et me fournir la cause racine et une suggestion de correction détaillée.
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        return filepath

    def generate(self, format="md", scope="all", hours=24):
        """Génération manuelle via API."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"report_{scope}_{timestamp}.{format}"
        filepath = os.path.join(self.reports_dir, filename)
        
        # Pour le moment, génération de stub. Brancher aux autres modules en prod.
        if format == "md":
            content = f"# Rapport Système ({hours}h)\n\nCeci est un rapport généré automatiquement...\n"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            content = json.dumps({"scope": scope, "hours": hours, "status": "ok"})
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
                
        return {"filename": filename, "path": filepath, "content": content}
