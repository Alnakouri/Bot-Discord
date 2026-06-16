import subprocess
import psutil
import os
import time

BOT_REGISTRY = {
    "sheogorath": {
        "name": "Sheogorath",
        "display": "🧀 Sheogorath",
        "dir": "Sheogorath",
        "script": "bot_sheogorath.py",
        "bat": "start_sheogorath.bat",
        "color": "#d946ef"
    },
    "maiq": {
        "name": "maiq",
        "display": "🐱 M'aiq le Menteur",
        "dir": "MaiqBot",
        "script": "bot_maiq.py",
        "bat": "start_bot.bat",
        "color": "#f97316"
    },
    "alfred": {
        "name": "alfred",
        "display": "☕ Alfred Pennyworth",
        "dir": "Alfred",
        "script": "bot_alfred.py",
        "bat": "start_alfred.bat",
        "color": "#475569"
    },
    "johnny": {
        "name": "johnny",
        "display": "🔫 Johnny Silverbot",
        "dir": "JohnnyBot",
        "script": "bot_johnny.py",
        "bat": "start_johnny.bat",
        "color": "#22c55e"
    },
    "zaji": {
        "name": "zaji",
        "display": "🏍️ Eikichi Onizuka",
        "dir": "ZajiBot",
        "script": "bot_zaji.py",
        "bat": "start_zaji.bat",
        "color": "#0ea5e9"
    },
    "malena": {
        "name": "malena",
        "display": "💃 Malena la Gitana",
        "dir": "MalenaBot",
        "script": "bot_malena.py",
        "bat": "start_malena.bat",
        "color": "#f43f5e"
    }
}

class BotManager:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        
    def _get_docker_status(self, bot_id):
        """Vérifie si le conteneur Docker du bot est en cours d'exécution."""
        container_name = f"bot-{bot_id}"
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
                capture_output=True, text=True, check=True
            )
            status = result.stdout.strip()
            return status == "running"
        except subprocess.CalledProcessError:
            return False

    def get_status(self, bot_id):
        bot_info = BOT_REGISTRY.get(bot_id)
        if not bot_info:
            return None
        
        is_running = self._get_docker_status(bot_id)
        
        if is_running:
            return {
                "id": bot_id,
                "display": bot_info["display"],
                "status": "running",
                "uptime": 0, # Uptime via docker non implémenté pour le moment
                "pid": None,
                "color": bot_info["color"]
            }
        return {
            "id": bot_id,
            "display": bot_info["display"],
            "status": "stopped",
            "uptime": 0,
            "pid": None,
            "color": bot_info["color"]
        }

    def get_all_status(self):
        return [self.get_status(bot_id) for bot_id in BOT_REGISTRY]

    def start_bot(self, bot_id):
        bot_info = BOT_REGISTRY.get(bot_id)
        if not bot_info:
            return {"success": False, "error": "Bot inconnu"}
            
        if self._get_docker_status(bot_id):
            return {"success": False, "error": "Bot déjà en cours d'exécution dans Docker"}
            
        try:
            subprocess.run(
                ["docker", "compose", "up", "-d", bot_id],
                cwd=self.root_dir, check=True
            )
            return {"success": True, "message": f"{bot_info['display']} (Docker) démarré"}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"Erreur Docker: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_bot(self, bot_id):
        bot_info = BOT_REGISTRY.get(bot_id)
        if not bot_info:
            return {"success": False, "error": "Bot inconnu"}
            
        if not self._get_docker_status(bot_id):
            return {"success": False, "error": "Bot non en cours d'exécution dans Docker"}
            
        try:
            subprocess.run(
                ["docker", "compose", "stop", bot_id],
                cwd=self.root_dir, check=True
            )
            return {"success": True, "message": f"{bot_info['display']} (Docker) arrêté"}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"Erreur Docker: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def restart_bot(self, bot_id):
        bot_info = BOT_REGISTRY.get(bot_id)
        if not bot_info:
            return {"success": False, "error": "Bot inconnu"}
            
        try:
            subprocess.run(
                ["docker", "compose", "restart", bot_id],
                cwd=self.root_dir, check=True
            )
            return {"success": True, "message": f"{bot_id} (Docker) redémarré"}
        except subprocess.CalledProcessError as e:
            return {"success": False, "error": f"Erreur Docker: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Erreur au redémarrage: {str(e)}"}

