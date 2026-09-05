import os
import json
import re
import string
from pathlib import Path
from bot_manager import BOT_REGISTRY

class TwitchConfigManager:
    """
    Manages loading, updating, validating, and saving Twitch configurations
    for all registered Discord bots.
    """
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config_path = data_dir / "twitch_config.json"
        
    def _load_raw(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_raw(self, data: dict):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Atomic write
        tmp_path = self.config_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.config_path)
        except Exception as e:
            if tmp_path.exists():
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass  # le temporaire a deja disparu ; l'erreur d'origine est relancee juste apres
            raise e

    def get_all(self) -> dict:
        """
        Returns the entire configuration structure. Initializes missing bots with default options.
        """
        config = self._load_raw()
        updated = False
        for bot_id in BOT_REGISTRY:
            if bot_id not in config:
                config[bot_id] = {
                    "enabled": False,
                    "poll_interval_seconds": 90,
                    "subscriptions": []
                }
                updated = True
            
            # Fill missing keys for Twitch V2 config
            if "chat" not in config[bot_id]:
                config[bot_id]["chat"] = {
                    "events": True,
                    "interjections": True,
                    "greetings": True,
                    "viewer_memory": True,
                    "game_qa": False,
                    "eventsub": False
                }
                updated = True
            else:
                if "game_qa" not in config[bot_id]["chat"]:
                    config[bot_id]["chat"]["game_qa"] = False
                    updated = True
                if "eventsub" not in config[bot_id]["chat"]:
                    config[bot_id]["chat"]["eventsub"] = False
                    updated = True
            if "reward_map" not in config[bot_id]:
                config[bot_id]["reward_map"] = {}
                updated = True
            if "chat_channels" not in config[bot_id]:
                # Chaînes Twitch où le bot chatte. Vide => le bot retombe sur TWITCH_CHAT_CHANNELS (env).
                config[bot_id]["chat_channels"] = []
                updated = True
            if "listen" not in config[bot_id]:
                config[bot_id]["listen"] = {
                    "enabled": False,
                    "mode": "C",
                    "device": "cpu",
                    "chunk_ms": 160,
                    "min_interval": 45
                }
                updated = True
            if "cohost_channels" not in config[bot_id]:
                config[bot_id]["cohost_channels"] = []
                updated = True
            if "link_commands" not in config[bot_id]:
                config[bot_id]["link_commands"] = []
                updated = True

        if updated:
            self._save_raw(config)
        return config

    def get_bot(self, bot_id: str) -> dict:
        """
        Returns config for a single bot.
        """
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        config = self.get_all()
        return config[bot_id]

    def set_bot(self, bot_id: str, enabled: bool, poll_interval_seconds: int):
        """
        Updates a bot's global settings (enabled state, poll interval).
        """
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        if not isinstance(enabled, bool):
            raise ValueError("Le paramètre 'enabled' doit être un booléen.")
        try:
            poll_interval_seconds = int(poll_interval_seconds)
        except (ValueError, TypeError):
            raise ValueError("L'intervalle de polling doit être un entier.")
        if poll_interval_seconds < 60:
            raise ValueError("L'intervalle de polling doit être d'au moins 60 secondes.")
            
        config = self.get_all()
        config[bot_id]["enabled"] = enabled
        config[bot_id]["poll_interval_seconds"] = poll_interval_seconds
        self._save_raw(config)

    def extract_login(self, raw: str) -> str:
        """
        Extracts and normalizes a Twitch login username from either a raw login or a stream URL.
        """
        raw = raw.strip()
        # Match standard URLs like twitch.tv/username or just raw username
        match = re.search(r'(?:https?://)?(?:www\.)?twitch\.tv/([a-zA-Z0-9_]{3,25})(?:[/?].*)?$', raw, re.IGNORECASE)
        if match:
            login = match.group(1).lower()
        else:
            if not re.match(r'^[a-zA-Z0-9_]{3,25}$', raw):
                raise ValueError("Nom d'utilisateur Twitch invalide (3 à 25 caractères alphanumériques ou soulignés).")
            login = raw.lower()
        return login

    def extract_channel_id(self, raw: str) -> int:
        """
        Extracts a Discord channel (or thread) ID from either a raw numeric ID
        or a full Discord URL like https://discord.com/channels/<guild>/<channel>[/<thread>].
        Returns the ID as int. Raises ValueError if none can be found.
        """
        raw = str(raw).strip()
        if raw.isdigit():
            return int(raw)
        # Discord snowflakes are 17-20 digit numbers. In a channel URL the last
        # snowflake is the target (channel, or thread if present).
        snowflakes = re.findall(r'\d{17,20}', raw)
        if snowflakes:
            return int(snowflakes[-1])
        raise ValueError("ID de salon Discord invalide : collez l'ID numérique du salon ou son lien Discord complet.")

    def add_subscription(self, bot_id: str, twitch_login_raw: str, discord_channel_id: str, custom_message: str | None = None) -> dict:
        """
        Adds a new twitch subscription to a bot's config.
        """
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        
        login = self.extract_login(twitch_login_raw)

        # Accepte un ID numérique OU un lien Discord complet (extraction de l'ID).
        channel_id_int = self.extract_channel_id(discord_channel_id)
        discord_channel_id_str = str(channel_id_int)

        # Validate custom message placeholders if present
        if custom_message:
            custom_message = custom_message.strip()
            # Try formatting to detect bad curly brace keys
            try:
                custom_message.format(streamer="test", title="test", game="test", url="test")
            except KeyError as e:
                raise ValueError(f"Clé de message personnalisé invalide : {e}")
            except Exception as e:
                raise ValueError(f"Message personnalisé mal formaté : {e}")
        else:
            custom_message = None

        config = self.get_all()
        subs = config[bot_id]["subscriptions"]
        
        # Prevent exact duplicates (same login and channel for this bot)
        for sub in subs:
            if sub["twitch_login"] == login and str(sub["discord_channel_id"]) == discord_channel_id_str:
                raise ValueError(f"L'abonnement à '{login}' dans ce salon Discord existe déjà pour ce bot.")
                
        new_sub = {
            "twitch_login": login,
            "discord_channel_id": channel_id_int,
            "custom_message": custom_message
        }
        subs.append(new_sub)
        self._save_raw(config)
        return new_sub

    def remove_subscription(self, bot_id: str, index: int):
        """
        Removes subscription at the given index.
        """
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
            
        config = self.get_all()
        subs = config[bot_id]["subscriptions"]
        try:
            index = int(index)
        except (ValueError, TypeError):
            raise ValueError("L'index doit être un entier.")
            
        if index < 0 or index >= len(subs):
            raise ValueError("Index d'abonnement hors limites.")

        subs.pop(index)
        self._save_raw(config)

    # --- ACTIONS GLOBALES (tous les bots en un clic) ---
    def set_enabled_all(self, enabled: bool, poll_interval_seconds=None):
        """Active/désactive la surveillance pour TOUS les bots (intervalle optionnel)."""
        if not isinstance(enabled, bool):
            raise ValueError("Le paramètre 'enabled' doit être un booléen.")
        piv = None
        if poll_interval_seconds is not None:
            try:
                piv = int(poll_interval_seconds)
            except (ValueError, TypeError):
                raise ValueError("L'intervalle de polling doit être un entier.")
            if piv < 60:
                raise ValueError("L'intervalle de polling doit être d'au moins 60 secondes.")
        config = self.get_all()
        for bot_id in BOT_REGISTRY:
            config[bot_id]["enabled"] = enabled
            if piv is not None:
                config[bot_id]["poll_interval_seconds"] = piv
        self._save_raw(config)

    def add_subscription_all(self, twitch_login_raw: str, discord_channel_id: str,
                             custom_message: str | None = None) -> dict:
        """Ajoute le même abonnement à TOUS les bots. Validé une fois ; un bot qui a
        déjà cet abonnement (même chaîne + même salon) est ignoré."""
        login = self.extract_login(twitch_login_raw)
        channel_id_int = self.extract_channel_id(discord_channel_id)
        if custom_message:
            custom_message = custom_message.strip()
            try:
                custom_message.format(streamer="test", title="test", game="test", url="test")
            except KeyError as e:
                raise ValueError(f"Clé de message personnalisé invalide : {e}")
            except Exception as e:
                raise ValueError(f"Message personnalisé mal formaté : {e}")
        else:
            custom_message = None
        config = self.get_all()
        added, skipped = [], []
        for bot_id in BOT_REGISTRY:
            subs = config[bot_id]["subscriptions"]
            if any(s["twitch_login"] == login and str(s["discord_channel_id"]) == str(channel_id_int)
                   for s in subs):
                skipped.append(bot_id)
                continue
            subs.append({"twitch_login": login, "discord_channel_id": channel_id_int,
                         "custom_message": custom_message})
            added.append(bot_id)
        self._save_raw(config)
        return {"added": added, "skipped": skipped}

    def update_chat_config(self, bot_id: str, events: bool, interjections: bool, greetings: bool, viewer_memory: bool, game_qa: bool = False, eventsub: bool = False):
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        config = self.get_all()
        config[bot_id]["chat"] = {
            "events": events,
            "interjections": interjections,
            "greetings": greetings,
            "viewer_memory": viewer_memory,
            "game_qa": game_qa,
            "eventsub": eventsub
        }
        self._save_raw(config)

    def get_link_commands(self, bot_id: str) -> list:
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        config = self.get_all()
        return config[bot_id].get("link_commands", [])

    def update_link_commands(self, bot_id: str, items: list) -> list:
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        if not isinstance(items, list):
            raise ValueError("Les commandes doivent être sous forme de liste.")
        
        reserved_commands = {
            "decret", "decree", "fromage", "cheese", "folie", "faveur", "favor",
            "classement", "leaderboard", "humeur", "platform", "platforms",
            "genre", "genres", "studio", "developer", "publisher", "mode",
            "release", "about", "which_game", "game"
        }
        
        cleaned_items = []
        seen_cmds = set()
        
        for item in items:
            if not isinstance(item, dict):
                continue
            cmd = item.get("cmd", "")
            if not isinstance(cmd, str):
                continue
            cmd = cmd.strip().lower().lstrip("!")
            if not cmd:
                raise ValueError("La commande 'cmd' ne peut pas être vide.")
            if " " in cmd:
                raise ValueError(f"La commande '{cmd}' ne doit pas contenir d'espaces.")
            if cmd in reserved_commands:
                raise ValueError(f"La commande '{cmd}' est un nom réservé et ne peut pas être utilisée.")
                
            url = item.get("url", "")
            if not isinstance(url, str) or not url.strip():
                raise ValueError(f"L'URL pour la commande '{cmd}' ne peut pas être vide.")
            url = url.strip()
            
            # Label
            label = item.get("label", "")
            if isinstance(label, str):
                label = label.strip()
            else:
                label = ""
                
            # Message
            msg = item.get("message", "")
            if isinstance(msg, str):
                msg = msg.strip()
            else:
                msg = ""

            # Le template ne peut utiliser que {url} et {label} (sinon .format() planterait au runtime)
            if msg:
                try:
                    used = {
                        fn.split(".")[0].split("[")[0].strip()
                        for _, fn, _, _ in string.Formatter().parse(msg)
                        if fn is not None
                    }
                except (ValueError, IndexError):
                    raise ValueError(f"Le message de la commande '{cmd}' contient un format invalide.")
                unknown = used - {"url", "label", ""}
                if unknown:
                    raise ValueError(
                        f"Le message de la commande '{cmd}' ne peut utiliser que {{url}} et {{label}} "
                        f"(inconnu : {', '.join(sorted(unknown))})."
                    )
                
            # Aliases
            aliases = item.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [a.strip() for a in aliases.replace(",", " ").split() if a.strip()]
            elif not isinstance(aliases, list):
                aliases = []
            
            cleaned_aliases = []
            for alias in aliases:
                if not isinstance(alias, str):
                    continue
                alias = alias.strip().lower().lstrip("!")
                if not alias:
                    continue
                if " " in alias:
                    raise ValueError(f"L'alias '{alias}' ne doit pas contenir d'espaces.")
                if alias in reserved_commands:
                    raise ValueError(f"L'alias '{alias}' est un nom réservé et ne peut pas être utilisé.")
                if alias == cmd:
                    continue
                if alias not in cleaned_aliases:
                    cleaned_aliases.append(alias)
            
            if cmd in seen_cmds:
                continue
            seen_cmds.add(cmd)
            
            cleaned_items.append({
                "cmd": cmd,
                "url": url,
                "label": label,
                "message": msg,
                "aliases": cleaned_aliases
            })
            
        config = self.get_all()
        config[bot_id]["link_commands"] = cleaned_items
        self._save_raw(config)
        return cleaned_items

    def update_cohost_channels(self, bot_id: str, channels) -> list[str]:
        """Liste des chaînes co-host. Accepte liste ou CSV. Normalise chaque entrée via extract_login."""
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        if isinstance(channels, str):
            channels = channels.split(",")
        if not isinstance(channels, list):
            raise ValueError("Les chaînes co-host doivent être une liste ou une chaîne CSV.")
        cleaned = []
        for raw in channels:
            raw = str(raw).strip()
            if not raw:
                continue
            login = self.extract_login(raw)
            if login not in cleaned:
                cleaned.append(login)
        config = self.get_all()
        config[bot_id]["cohost_channels"] = cleaned
        self._save_raw(config)
        return cleaned

    def update_reward_map(self, bot_id: str, reward_map: dict):
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        config = self.get_all()
        config[bot_id]["reward_map"] = reward_map
        self._save_raw(config)

    def update_chat_channels(self, bot_id: str, channels) -> list[str]:
        """Liste des chaînes où le bot chatte. Accepte liste ou CSV. Normalise chaque entrée
        via extract_login (login ou URL twitch.tv/...). Liste vide => fallback env."""
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        if isinstance(channels, str):
            channels = channels.split(",")
        if not isinstance(channels, list):
            raise ValueError("Les chaînes doivent être une liste ou une chaîne CSV.")
        cleaned = []
        for raw in channels:
            raw = str(raw).strip()
            if not raw:
                continue
            login = self.extract_login(raw)   # réutilise la validation des subscriptions
            if login not in cleaned:
                cleaned.append(login)
        config = self.get_all()
        config[bot_id]["chat_channels"] = cleaned
        self._save_raw(config)
        return cleaned

    def update_listen_config(self, bot_id: str, enabled: bool, mode: str, device: str, chunk_ms: int, min_interval: int):
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        config = self.get_all()
        config[bot_id]["listen"] = {
            "enabled": enabled,
            "mode": mode,
            "device": device,
            "chunk_ms": int(chunk_ms),
            "min_interval": int(min_interval)
        }
        self._save_raw(config)

    def get_leaderboard(self, bot_id: str) -> list:
        if bot_id not in BOT_REGISTRY:
            raise ValueError(f"Bot '{bot_id}' non enregistré.")
        
        if bot_id == "sheogorath":
            path = self.data_dir / "sheo_faveurs_twitch.json"
        elif bot_id == "johnny":
            path = self.data_dir / "johnny_cred_twitch.json"
        else:
            path = self.data_dir / f"{bot_id}_cred_twitch.json"
            
        if not path.exists():
            return []
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            res = []
            for user_key, info in data.items():
                if isinstance(info, dict):
                    res.append({
                        "name": info.get("name", user_key),
                        "points": info.get("points", 0)
                    })
                else:
                    res.append({
                        "name": user_key,
                        "points": int(info)
                    })
            res.sort(key=lambda x: x["points"], reverse=True)
            return res[:20]
        except Exception:
            return []
