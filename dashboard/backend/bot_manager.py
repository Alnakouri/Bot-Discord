import subprocess
import os
import time
from datetime import datetime, timezone

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
    "sugar": {
        "name": "sugar",
        "display": "Sugar Bot",
        "dir": "SugarBot",
        "script": "bot_sugar.py",
        "bat": "start_sugar.bat",
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
        
    def _fetch_all_docker_info(self):
        """Récupère d'un coup les statuts, uptimes et ressources de tous les bots."""
        info_map = {}
        for bot_id in BOT_REGISTRY:
            info_map[bot_id] = {
                "status": "stopped",
                "uptime": 0,
                "cpu": "0%",
                "ram": "0MiB"
            }
            
        # 1. Inspecter le statut et StartedAt
        container_names = [f"bot-{bot_id}" for bot_id in BOT_REGISTRY]
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.Name}} {{.State.Status}} {{.State.StartedAt}}"] + container_names,
                capture_output=True, text=True
            )
            # NB : `docker inspect` retourne un code != 0 dès qu'UN conteneur
            # est absent (bot jamais démarré), mais produit quand même les
            # lignes des conteneurs trouvés sur stdout. On parse donc stdout
            # sans gater sur le code retour, sinon un seul bot manquant ferait
            # afficher « stopped » pour TOUTE la grille.
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        name = parts[0].lstrip("/")
                        status = parts[1]
                        started_at = parts[2]
                        
                        bot_id = name.replace("bot-", "")
                        if bot_id in info_map:
                            info_map[bot_id]["status"] = status
                            if status == "running":
                                try:
                                    t_str = started_at[:19]
                                    dt_start = datetime.fromisoformat(t_str).replace(tzinfo=timezone.utc)
                                    dt_now = datetime.now(timezone.utc)
                                    uptime_seconds = int((dt_now - dt_start).total_seconds())
                                    info_map[bot_id]["uptime"] = max(0, uptime_seconds)
                                except Exception as ex:
                                    print(f"Error parsing StartedAt for {bot_id}: {ex}")
        except Exception as e:
            print(f"Docker inspect error: {e}")
            
        # 2. Récupérer les stats CPU/RAM via docker stats --no-stream
        try:
            stats_result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}} {{.MemUsage}}"],
                capture_output=True, text=True
            )
            if stats_result.returncode == 0:
                for line in stats_result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        name = parts[0].lstrip("/")
                        cpu = parts[1]
                        ram_usage = parts[2]
                        
                        bot_id = name.replace("bot-", "")
                        if bot_id in info_map:
                            info_map[bot_id]["cpu"] = cpu
                            info_map[bot_id]["ram"] = ram_usage
        except Exception as e:
            print(f"Docker stats error: {e}")
            
        return info_map

    def _get_docker_status(self, bot_id):
        """Vérifie si le conteneur Docker du bot tourne (check léger 1 conteneur).

        On n'appelle pas `get_status` (qui scanne les 6 bots + `docker stats`,
        ~1-2 s) : un simple `docker inspect` sur le seul conteneur ciblé suffit
        pour les gardes de start/stop/restart.
        """
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", f"bot-{bot_id}"],
                capture_output=True, text=True
            )
            return result.stdout.strip() == "running"
        except Exception as e:
            print(f"Docker inspect (status léger) error for {bot_id}: {e}")
            return False

    def get_status(self, bot_id):
        bot_info = BOT_REGISTRY.get(bot_id)
        if not bot_info:
            return None
        
        docker_info = self._fetch_all_docker_info()
        info = docker_info.get(bot_id, {
            "status": "stopped",
            "uptime": 0,
            "cpu": "0%",
            "ram": "0MiB"
        })
        
        return {
            "id": bot_id,
            "display": bot_info["display"],
            "status": info["status"],
            "uptime": info["uptime"],
            "cpu": info["cpu"],
            "ram": info["ram"],
            "pid": None,
            "color": bot_info["color"]
        }

    def get_all_status(self):
        docker_info = self._fetch_all_docker_info()
        
        status_list = []
        for bot_id, bot_info in BOT_REGISTRY.items():
            info = docker_info.get(bot_id, {
                "status": "stopped",
                "uptime": 0,
                "cpu": "0%",
                "ram": "0MiB"
            })
            
            status_list.append({
                "id": bot_id,
                "display": bot_info["display"],
                "status": info["status"],
                "uptime": info["uptime"],
                "cpu": info["cpu"],
                "ram": info["ram"],
                "pid": None,
                "color": bot_info["color"]
            })
        return status_list

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
