import os
import json
from datetime import datetime

class ReportGenerator:
    def __init__(self, db_path, bot_manager=None, error_analyzer=None, api_tracker=None, conversation_analyzer=None):
        self.db_path = db_path
        self.bot_manager = bot_manager
        self.error_analyzer = error_analyzer
        self.api_tracker = api_tracker
        self.conversation_analyzer = conversation_analyzer
        
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
        
        if format == "md":
            lines = []
            lines.append(f"# 📋 RAPPORT DE DIAGNOSTIC SYSTÈME ({hours}h)")
            lines.append(f"- **Généré le** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"- **Périmètre** : {scope.upper()}")
            lines.append("")
            
            # 1. Statut des bots
            if scope in ("all", "status") and self.bot_manager:
                lines.append("## 🤖 Statut de l'Écosystème des Bots")
                bots = self.bot_manager.get_all_status()
                for bot in bots:
                    status_emoji = "🟢" if bot["status"] == "running" else "🔴"
                    uptime_str = f"{bot['uptime'] // 3600}h {((bot['uptime'] % 3600) // 60)}m" if bot["status"] == "running" else "Hors ligne"
                    lines.append(f"### {status_emoji} {bot['display']} ({bot['id']})")
                    lines.append(f"- **Statut** : {bot['status'].upper()}")
                    lines.append(f"- **Uptime** : {uptime_str}")
                    if bot["status"] == "running":
                        lines.append(f"- **CPU** : {bot.get('cpu', '0%')} | **RAM** : {bot.get('ram', '0MiB')}")
                    lines.append("")
                lines.append("")
                
            # 2. Analyse des erreurs
            if scope in ("all", "errors") and self.error_analyzer:
                lines.append("## 🚨 Erreurs et Pannes Récentes")
                errors = self.error_analyzer.get_errors(resolved=False)
                if not errors:
                    lines.append("Aucune erreur non résolue détectée sur la période.")
                else:
                    lines.append(f"Il y a actuellement **{len(errors)}** erreur(s) active(s) non résolue(s) :")
                    lines.append("")
                    for err in errors[:10]:
                        lines.append(f"### [{err['bot_name']}] {err['error_type']} ({err['severity']})")
                        lines.append(f"- **Date** : {err['timestamp']}")
                        lines.append(f"- **Message** : `{err['error_message']}`")
                        if err.get('error_traceback'):
                            lines.append("- **Traceback** :")
                            lines.append("```python")
                            lines.append(err['error_traceback'][:500] + ("..." if len(err['error_traceback']) > 500 else ""))
                            lines.append("```")
                        lines.append("")
                lines.append("")
                
            # 3. Usage et clés API
            if scope in ("all", "api") and self.api_tracker:
                lines.append("## 🔑 État des clés et usage API (Cascade)")
                usage = self.api_tracker.get_usage(hours=hours)
                lines.append(f"**Total appels API** : {usage.get('total_calls', 0)}")
                lines.append("")
                
                by_api = usage.get("by_api", {})
                if by_api:
                    lines.append("| Provider API | Appels | Erreurs | Taux de Succès |")
                    lines.append("|---|---|---|---|")
                    for api_name, data in by_api.items():
                        lines.append(f"| {api_name} | {data['calls']} | {data['errors']} | {data['success_rate']}% |")
                    lines.append("")
                
                keys = self.api_tracker.get_keys_status()
                if keys:
                    lines.append("### Santé des Clés du Pool")
                    lines.append("| Clé | Statut | Appels | Erreurs | Dernière utilisation |")
                    lines.append("|---|---|---|---|---|")
                    for k in keys:
                        status_emoji = "🟢 ACTIVE" if k["status"] == "active" else ("🟡 COOLDOWN" if k["status"] == "cooldown" else "🔴 DESACTIVEE")
                        lines.append(f"| {k['api_key_display']} | {status_emoji} | {k['total_calls']} | {k['error_count']} | {k['last_used']} |")
                    lines.append("")
                lines.append("")
                
            # 4. Conversations
            if scope in ("all", "conversations") and self.conversation_analyzer:
                lines.append("## 💬 Volume de Conversations (7 jours)")
                stats = self.conversation_analyzer.get_stats(days=7)
                lines.append(f"- **Total interactions** : {stats.get('total_interactions', 0)}")
                lines.append(f"- **Utilisateurs uniques** : {stats.get('unique_users', 0)}")
                lines.append("")
                
                by_bot = stats.get("by_bot", {})
                if by_bot:
                    lines.append("| Bot | Messages | Utilisateurs Uniques |")
                    lines.append("|---|---|---|")
                    for bot_name, data in by_bot.items():
                        lines.append(f"| {bot_name} | {data.get('messages', 0)} | {data.get('unique_users', 0)} |")
                    lines.append("")
                lines.append("")
                
            # 5. Instructions pour IA
            lines.append("## 🧠 Consigne d'Analyse pour l'Assistant IA")
            lines.append("> Veuillez analyser ce rapport de diagnostic système. Identifiez s'il y a des goulots d'étranglement ou des clés API en panne, et proposez des mesures d'optimisation ou des corrections concrètes si des erreurs de crash sont présentes.")
            lines.append("")
            
            content = "\n".join(lines)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            content = json.dumps({"scope": scope, "hours": hours, "status": "ok"})
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
                
        return {"filename": filename, "path": filepath, "content": content}
