# -*- coding: utf-8 -*-
"""
shared/twitch_chat.py — Connexion permanente et chat Twitch pour les bots.
"""

import os
import re
import json
import string
import collections
from pathlib import Path
from typing import Callable


def _link_message_placeholders(template: str) -> set[str]:
    """Retourne les noms de champs utilisés dans un template link_command."""
    names = set()
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is None:
            continue
        base = field_name.split(".")[0].split("[")[0].strip()
        if base:
            names.add(base)
    return names

# Import satellite components
from shared.twitch.auth import TwitchAuth
from shared.twitch.profile import TwitchProfile
from shared.twitch.connection import ConnectionMixin
from shared.twitch.llm import LlmMixin
from shared.twitch.daily_profile import DailyProfileMixin
from shared.twitch.memory import ViewerMemoryMixin
from shared.twitch.events import EventsMixin
from shared.twitch.dispatch import DispatchMixin
from shared.twitch.eventsub_bridge import EventSubMixin
from shared.twitch.voice import VoiceMixin
from shared.twitch.sanitize import SanitizeMixin

# Path configuration
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))

class TwitchChatBot(
    ConnectionMixin,
    LlmMixin,
    DailyProfileMixin,
    ViewerMemoryMixin,
    EventsMixin,
    DispatchMixin,
    EventSubMixin,
    VoiceMixin,
    SanitizeMixin,
):
    """
    Gère la connexion permanente IRC au chat Twitch, écoute les messages et y répond en personnage.
    """
    PRIVMSG_RE = re.compile(r"^(?:@\S+ )?:(?P<user>[^!]+)![^ ]+ PRIVMSG #(?P<chan>[^ ]+) :(?P<msg>.*)$")
    USERNOTICE_RE = re.compile(r"^(?:@\S+ )?:tmi\.twitch\.tv USERNOTICE #(?P<chan>[^ ]+)(?: :(?P<msg>.*))?$")

    @staticmethod
    def _parse_tags(line: str) -> dict[str, str]:
        tags = {}
        if not line.startswith("@"):
            return tags
        space_idx = line.find(" ")
        if space_idx == -1:
            tags_part = line[1:]
        else:
            tags_part = line[1:space_idx]
        for pair in tags_part.split(";"):
            if not pair:
                continue
            if "=" in pair:
                k, v = pair.split("=", 1)
                v = v.replace(r"\s", " ").replace(r"\:", ";").replace(r"\r", "\r").replace(r"\n", "\n").replace(r"\\", "\\")
                tags[k] = v
            else:
                tags[pair] = ""
        return tags

    def __init__(
        self,
        bot_id: str,
        logger,
        username: str,
        channels: list[str],
        client_id: str,
        client_secret: str,
        auth: TwitchAuth,
        personality_prompt: str | None = None,
        key_manager = None,
        mistral_client = None,
        groq_client = None,
        openrouter_client = None,
        nvidia_client = None,
        bot_label: str | None = None,
        system_prompt_provider = None,
        tone_directive_provider = None,
        profile_bio: str | None = None,
        chat_color: str | None = None,
        enable_events: bool = False,
        enable_interjections: bool = False,
        interjection_chance: float = 0.03,
        interjection_min_interval: float = 600.0,
        enable_greetings: bool = False,
        commands: dict[str, Callable] | None = None,
        command_aliases: dict[str, str] | None = None,
        passive_handler: Callable | None = None,
        enable_viewer_memory: bool = False,
        viewer_memory_max: int = 8,
        enable_eventsub: bool = False,
        eventsub_subscriptions: list[str] | None = None,
        eventsub_reward_map: dict | None = None,
        peer_bots: list[str] | None = None,
        greeting_templates: dict | None = None,
        broadcaster_auth=None,
        enable_voice_listen: bool = False,
        voice_min_interval: float = 45.0,
        listen_port: int = 8765,
        listen_host: str = "127.0.0.1",
        enable_game_qa: bool = False,
        cohost_channels: list[str] | None = None
    ):
        self.bot_id = bot_id
        self.logger = logger
        self.username = username
        self.channels = channels
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth = auth
        self.personality_prompt = personality_prompt
        # Optionnel : callable renvoyant le prompt système "vivant" (ex. humeur courante
        # côté Discord). Permet d'utiliser la MÊME config que le bot principal.
        self.system_prompt_provider = system_prompt_provider
        # Optionnel : callable (author, message) -> str renvoyant une consigne de TON
        # à injecter par message (ex. Sugar : chaleureuse si amical, griffes si hostile).
        # Hook GÉNÉRIQUE — aucune logique spécifique-bot ici.
        self.tone_directive_provider = tone_directive_provider
        self.key_manager = key_manager
        self.mistral_client = mistral_client
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.nvidia_client = nvidia_client
        self.bot_label = bot_label

        self.enable_voice_listen = enable_voice_listen
        self.voice_min_interval = voice_min_interval
        self.listen_port = listen_port
        self.listen_host = listen_host
        self._last_voice_ts = 0

        self.profile_helper = TwitchProfile(bot_id, logger, client_id, auth)
        self.profile_bio = profile_bio
        self.chat_color = chat_color
        self._profile_day = None
        self.injection_hits = collections.defaultdict(int)

        # Twitch V2 Configuration
        self.enable_events = enable_events
        self.enable_interjections = enable_interjections
        self.interjection_chance = interjection_chance
        self.interjection_min_interval = interjection_min_interval
        self.enable_greetings = enable_greetings
        self.enable_game_qa = enable_game_qa
        self.cohost_channels = [c.lower().strip() for c in (cohost_channels or []) if c.strip()]
        self.commands = commands or {}
        self.command_aliases = command_aliases or {}
        self.passive_handler = passive_handler
        self.enable_viewer_memory = enable_viewer_memory
        self.viewer_memory_max = viewer_memory_max
        self.enable_eventsub = enable_eventsub
        self.eventsub_subscriptions = eventsub_subscriptions or [
            "channel.channel_points_custom_reward_redemption.add",
            "channel.follow",
            "channel.raid",
            "channel.hype_train.begin",
            "channel.hype_train.end",
            "channel.poll.begin",
            "channel.poll.end"
        ]
        self.eventsub_reward_map = eventsub_reward_map or {}
        self.eventsub_active = False
        self.eventsub_client = None
        # Auth SÉPARÉE pour EventSub : les events « channel » (channel points, subs,
        # hype, polls, follow) exigent le token du BROADCASTER, pas celui du bot. Si
        # fourni, EventSub l'utilise ; sinon il retombe sur self.auth (→ 403 propre si
        # le bot n'est pas le streamer).
        self.broadcaster_auth = broadcaster_auth
        self.ws = None

        # Bots à ignorer (anti-boucle inter-bots). Sur Twitch il n'existe pas de flag
        # `author.bot` (les bots sont des comptes normaux) → on exclut par pseudo.
        # Les pseudos Twitch des AUTRES bots sont CONFIGURÉS par bot (env TWITCH_PEER_BOTS)
        # et JAMAIS codés en dur ici (cloisonnement, cf. [[bots-independants]] /
        # silence-total-bots). On y ajoute son propre pseudo + les bots tiers courants.
        _third_party = {"nightbot", "streamelements", "wizebot", "moobot", "fossabot", "sery_bot"}
        self.known_bots = {b.strip().lower() for b in (peer_bots or []) if b and b.strip()} | _third_party
        self.known_bots.add(username.lower())
        _peers_cfg = sorted(b.strip().lower() for b in (peer_bots or []) if b and b.strip())
        self.logger.info(f"🤖 [TWITCH_CHAT:{self.bot_id}] Bots pairs ignorés (TWITCH_PEER_BOTS) : {_peers_cfg or 'AUCUN'}")

        # Templates d'accueil EN PERSONNAGE, optionnels et fournis par chaque bot :
        # {"new": ["... {author} ..."], "returning": ["... {author} ... {count} ..."]}.
        # Si absent → repli sur _generate_templated_greet (générique / branche Sheo).
        self.greeting_templates = greeting_templates

        self.session_seen = set()
        self.channel_recent = {}
        self.recent_self_responses = {}  # chan -> deque(maxlen=6) des dernières répliques du bot (anti-répétition)
        self.command_cooldowns = {}
        self._last_event_ts = 0
        self._last_greet_ts = 0
        self._last_interjection = 0
        self.viewers_state = self._load_viewers_state()
        self.viewer_facts = self._load_viewer_facts() if enable_viewer_memory else {}

        self._stopped = False
        self.histories = {}  # (channel, user) -> deque(maxlen=6)
        self.user_cooldowns = {}  # user -> float (timestamp)
        self.global_msg_timestamps = collections.deque()  # deque of floats

        # Build triggers
        trigger_terms = [username.lower(), bot_id.lower()]
        if bot_label:
            trigger_terms.append(bot_label.lower())
        
        # Add common short names for bots
        for short in ["sheo", "maiq", "johnny", "sugar", "malena", "alfred"]:
            if short in bot_id.lower():
                trigger_terms.append(short)

        trigger_terms = sorted(list(set(t.strip().lower() for t in trigger_terms if t)), key=len, reverse=True)
        trigger_pattern = r"(?:@?(" + "|".join(re.escape(t) for t in trigger_terms) + r"))\b"
        self.trigger_re = re.compile(trigger_pattern, re.IGNORECASE)
        self.logger.info(f"🎯 [TWITCH_CHAT:{self.bot_id}] Déclencheurs configurés : {trigger_terms}")

    @staticmethod
    def _strip_stage_directions(text: str) -> str:
        from shared.twitch.sanitize import strip_stage_directions
        return strip_stage_directions(text)

    def stop(self):
        self._stopped = True
        # Sauvegarde finale des viewers
        path = os.path.join(DATA_DIR, f"twitch_viewers_{self.bot_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.viewers_state, f, indent=2)
        except Exception as e:
            self.logger.debug(f"[TWITCH] sauvegarde finale des viewers impossible : {e}")
        # Sauvegarde finale des facts
        if hasattr(self, "viewer_facts") and self.viewer_facts:
            facts_path = os.path.join(DATA_DIR, f"twitch_facts_{self.bot_id}.json")
            try:
                with open(facts_path, "w", encoding="utf-8") as f:
                    json.dump(self.viewer_facts, f, indent=2, ensure_ascii=False)
            except Exception as e:
                self.logger.debug(f"[TWITCH] sauvegarde finale des faits viewers impossible : {e}")
        # Arrêt d'EventSub si actif
        if hasattr(self, "eventsub_client") and self.eventsub_client:
            self.eventsub_client.stop()


def _load_dashboard_twitch_config(bot_id: str, logger) -> dict:
    """Lit data/twitch_config.json pour CE bot. Renvoie {} si absent/illisible → le bot
    reste autonome sans le dashboard (cf. [[bots-independants]])."""
    path = os.path.join(DATA_DIR, "twitch_config.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get(bot_id) or {}) if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] Lecture twitch_config.json échouée (ignoré) : {e}")
        return {}


def setup_twitch_chat(bot_id: str, logger, *, personality_prompt: str | None = None,
                      key_manager=None, mistral_client=None, groq_client=None,
                       nvidia_client=None, bot_label: str | None = None,
                      system_prompt_provider=None,
                      tone_directive_provider=None,
                      profile_bio: str | None = None,
                      chat_color: str | None = None,
                      enable_events: bool = False,
                      enable_interjections: bool = False,
                      interjection_chance: float = 0.03,
                      interjection_min_interval: float = 600.0,
                      enable_greetings: bool = False,
                      commands: dict[str, Callable] | None = None,
                      command_aliases: dict[str, str] | None = None,
                      passive_handler: Callable | None = None,
                      enable_viewer_memory: bool = False,
                      viewer_memory_max: int = 8,
                      enable_eventsub: bool = False,
                      eventsub_subscriptions: list[str] | None = None,
                      eventsub_reward_map: dict | None = None,
                      peer_bots: list[str] | None = None,
                      greeting_templates: dict | None = None,
                      enable_voice_listen: bool = False) -> TwitchChatBot | None:
    """
    Initialise TwitchChatBot si les crédentiels d'environnement requis sont définis.
    """
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    username = os.getenv("TWITCH_BOT_USERNAME")
    channels_csv = os.getenv("TWITCH_CHAT_CHANNELS")
    default_token = os.getenv("TWITCH_OAUTH_TOKEN")
    default_refresh = os.getenv("TWITCH_REFRESH_TOKEN")

    # Secrets => env obligatoire. channels_csv N'EST PLUS requis (dashboard peut fournir).
    if not client_id or not client_secret or not username or not default_token:
        logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Module chat non activé (crédentiels manquants)")
        return None

    dash = _load_dashboard_twitch_config(bot_id, logger)   # {} si pas de dashboard

    # Pseudos Twitch des autres bots à ignorer (anti-boucle), fusionnés avec l'éventuel
    # argument explicite. Source de vérité = config par bot (cloisonnement).
    env_peers = os.getenv("TWITCH_PEER_BOTS", "")
    resolved_peers = list(peer_bots or []) + [p.strip() for p in env_peers.split(",") if p.strip()]

    # Chaînes : dashboard prioritaire si non vide, sinon env.
    dash_channels = [str(c).strip().lower().lstrip("#") for c in dash.get("chat_channels", []) if str(c).strip()]
    env_channels  = [c.strip().lower().lstrip("#") for c in (channels_csv or "").split(",") if c.strip()]
    channels = dash_channels or env_channels
    if not channels:
        logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Aucune chaîne (ni dashboard ni TWITCH_CHAT_CHANNELS)")
        return None
    if dash_channels:
        logger.info(f"📡 [TWITCH_CHAT:{bot_id}] Chaînes pilotées par le dashboard : {channels}")

    # Toggles : le dashboard prime SUR LES ARGS quand la clé est présente.
    dash_chat = dash.get("chat") or {}
    if "events" in dash_chat:        enable_events         = bool(dash_chat["events"])
    if "interjections" in dash_chat: enable_interjections  = bool(dash_chat["interjections"])
    if "greetings" in dash_chat:     enable_greetings      = bool(dash_chat["greetings"])
    if "viewer_memory" in dash_chat: enable_viewer_memory  = bool(dash_chat["viewer_memory"])

    if "eventsub" in dash_chat: enable_eventsub      = bool(dash_chat["eventsub"])

    enable_game_qa = False
    if "game_qa" in dash_chat:
        enable_game_qa = bool(dash_chat["game_qa"])

    cohost_channels = dash.get("cohost_channels") or []

    # Configuration listen/voix depuis le dashboard
    dash_listen = dash.get("listen") or {}
    if "enabled" in dash_listen:
        enable_voice_listen = bool(dash_listen["enabled"])
    voice_min_interval = 45.0
    if "min_interval" in dash_listen:
        try:
            voice_min_interval = float(dash_listen["min_interval"])
        except (ValueError, TypeError):
            pass  # valeur illisible dans le dashboard : on garde l'intervalle par defaut
    # Hôte du hub d'écoute : 127.0.0.1 par défaut (IPv4, évite le ::1). En conteneur avec
    # le hub sur la machine hôte, poser TWITCH_LISTEN_HOST=host.docker.internal.
    listen_host = os.getenv("TWITCH_LISTEN_HOST", "127.0.0.1").strip() or "127.0.0.1"

    # reward_map : merge dashboard PAR-DESSUS les défauts du bot (un dashboard vide ne les efface pas).
    dash_rewards = dash.get("reward_map") or {}
    if dash_rewards:
        eventsub_reward_map = {**(eventsub_reward_map or {}), **dash_rewards}

    auth = TwitchAuth(bot_id, logger, client_id, client_secret, default_token, default_refresh)

    # Auth broadcaster (token du STREAMER) pour EventSub. Activée si un token broadcaster
    # est fourni (env TWITCH_BROADCASTER_OAUTH_TOKEN) ou si le fichier d'auth dédié existe
    # (généré par `twitch_authorize.py --bot {bot_id}_broadcaster` connecté au compte du
    # streamer). Stocké séparément → 0 collision avec le token de chat du bot.
    broadcaster_auth = None
    if enable_eventsub:
        b_token = os.getenv("TWITCH_BROADCASTER_OAUTH_TOKEN")
        b_refresh = os.getenv("TWITCH_BROADCASTER_REFRESH_TOKEN")
        b_file = os.path.join(DATA_DIR, f"twitch_chat_auth_{bot_id}_broadcaster.json")
        if b_token or os.path.exists(b_file):
            broadcaster_auth = TwitchAuth(f"{bot_id}_broadcaster", logger, client_id,
                                          client_secret, b_token, b_refresh)
            logger.info(f"📡 [TWITCH_CHAT:{bot_id}] EventSub utilisera le token BROADCASTER (channel points/subs/etc. activables)")
        else:
            logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] EventSub activé mais AUCUN token broadcaster → les events « channel » seront refusés (403). Lance twitch_authorize.py --bot {bot_id}_broadcaster avec ton compte streamer.")

    # Résolution des informations de profil
    env_bio = os.getenv("TWITCH_PROFILE_BIO")
    resolved_bio = profile_bio or env_bio

    env_color = os.getenv("TWITCH_CHAT_COLOR")
    if resolved_bio or env_color or chat_color:
        resolved_color = chat_color or env_color or "blue_violet"
    else:
        resolved_bio = None
        resolved_color = None

    # Espace liens (Feature 1)
    # Les callbacks des liens peuvent avoir besoin du bot lui-meme (pour lui faire
    # ecrire sa phrase), et il n'existe pas encore a cet instant : on le leur passe
    # par ce porte-instance, rempli juste apres la construction.
    bot_ref = {}
    link_cmds = {}
    link_aliases = {}
    link_auto = {}
    reserved_names = {
        "decret", "decree", "fromage", "cheese", "folie", "faveur", "favor",
        "classement", "leaderboard", "humeur", "platform", "platforms",
        "genre", "genres", "studio", "developer", "publisher", "mode",
        "release", "about", "which_game", "game"
    }
    
    for entry in (dash.get("link_commands") or []):
        if not isinstance(entry, dict) or not entry.get("cmd") or not entry.get("url"):
            continue
        cmd = entry["cmd"].strip().lower().lstrip("!")
        if not cmd or " " in cmd:
            continue
        if cmd in reserved_names:
            logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] link_command !{cmd} ignorée (nom réservé)")
            continue
        if commands and cmd in commands:
            logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] link_command !{cmd} ignorée (collision)")
            continue
            
        url = entry["url"].strip()
        label = (entry.get("label") or "").strip()
        msg_tmpl = (entry.get("message") or "").strip()
        # Champ « Message (optionnel) » laissé VIDE = le bot écrit lui-même sa phrase, en
        # personnage, et le code y accole l'URL. Rempli = gabarit fixe, comme avant : qui
        # a pris la peine d'écrire un message ne veut pas qu'on le remplace.
        message_auto = not msg_tmpl
        if not msg_tmpl:
            msg_tmpl = "{label} : {url}" if label else "{url}"

        # Garde template : uniquement {url}/{label}, sinon .format() planterait à l'exécution
        try:
            bad = _link_message_placeholders(msg_tmpl) - {"url", "label"}
        except (ValueError, IndexError):
            logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] link_command !{cmd} ignorée (message mal formé)")
            continue
        if bad:
            logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] link_command !{cmd} ignorée (placeholder inconnu : {bad})")
            continue

        if message_auto:
            async def callback(author, args, u=url, l=label, c=cmd, t=msg_tmpl):
                # ⚠️ Repli sur le gabarit fixe à la moindre défaillance : quota épuisé,
                # cascade muette, phrase vide. Un `!discord` qui ne rend RIEN est pire
                # qu'un `!discord` fade — le viewer, lui, attend une adresse.
                bot = bot_ref.get("bot")
                phrase = None
                if bot is not None:
                    try:
                        phrase = await bot._generate_link_line(c, l, u)
                    except Exception as e:
                        logger.error(f"❌ [TWITCH_CHAT:{bot_id}] phrase de lien !{c} : {e}")
                return phrase or t.format(url=u, label=l)
        else:
            callback = lambda author, args, u=url, l=label, t=msg_tmpl: t.format(url=u, label=l)
        link_cmds[cmd] = callback
        link_auto[cmd] = message_auto
        
        aliases = entry.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [a.strip() for a in aliases.replace(",", " ").split() if a.strip()]
        for alias in aliases:
            alias = alias.strip().lower().lstrip("!")
            if not alias or " " in alias:
                continue
            if alias in reserved_names:
                logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] link_command alias !{alias} ignorée (nom réservé)")
                continue
            if (commands and alias in commands) or (command_aliases and alias in command_aliases):
                logger.warning(f"⚠️ [TWITCH_CHAT:{bot_id}] link_command alias !{alias} ignorée (collision)")
                continue
            link_aliases[alias] = cmd
            
    # Le silence est le pire des cas : un !discord non arme ne laisse AUCUNE trace, qu'il
    # soit absent de la config, en collision ou sur un nom reserve (les deux derniers cas
    # se journalisent deja, le premier non). On dit donc ce qui est arme, et ce qui ne l'est
    # pas. [[gotcha-config-twitch-lue-au-demarrage-seulement]] : lu AU DEMARRAGE seulement.
    if link_cmds:
        resume = []
        for cmd in link_cmds:
            details = []
            n_alias = sum(1 for c in link_aliases.values() if c == cmd)
            if n_alias:
                details.append(f"+{n_alias} alias")
            details.append("phrase du bot" if link_auto.get(cmd) else "gabarit fixe")
            resume.append(f"!{cmd} ({', '.join(details)})")
        logger.info(f"🔗 [TWITCH_CHAT:{bot_id}] Commandes de lien armees : {', '.join(resume)}")
    else:
        logger.info(
            f"🔗 [TWITCH_CHAT:{bot_id}] Aucune commande de lien armee "
            f"(`link_commands` vide dans data/twitch_config.json) — un !discord tape dans "
            f"le chat ne repondra a personne."
        )

    # Fusionner
    final_commands = {**link_cmds, **(commands or {})}
    final_aliases = {**link_aliases, **(command_aliases or {})}

    bot = TwitchChatBot(
        bot_id=bot_id,
        logger=logger,
        username=username,
        channels=channels,
        client_id=client_id,
        client_secret=client_secret,
        auth=auth,
        personality_prompt=personality_prompt,
        key_manager=key_manager,
        mistral_client=mistral_client,
        groq_client=groq_client,
         nvidia_client=nvidia_client,
        bot_label=bot_label,
        system_prompt_provider=system_prompt_provider,
        tone_directive_provider=tone_directive_provider,
        profile_bio=resolved_bio,
        chat_color=resolved_color,
        enable_events=enable_events,
        enable_interjections=enable_interjections,
        interjection_chance=interjection_chance,
        interjection_min_interval=interjection_min_interval,
        enable_greetings=enable_greetings,
        commands=final_commands,
        command_aliases=final_aliases,
        passive_handler=passive_handler,
        enable_viewer_memory=enable_viewer_memory,
        viewer_memory_max=viewer_memory_max,
        enable_eventsub=enable_eventsub,
        eventsub_subscriptions=eventsub_subscriptions,
        eventsub_reward_map=eventsub_reward_map,
        peer_bots=resolved_peers,
        greeting_templates=greeting_templates,
        broadcaster_auth=broadcaster_auth,
        enable_voice_listen=enable_voice_listen,
        voice_min_interval=voice_min_interval,
        listen_host=listen_host,
        enable_game_qa=enable_game_qa,
        cohost_channels=cohost_channels
    )
    # Les callbacks de lien construits plus haut peuvent maintenant atteindre le bot.
    bot_ref["bot"] = bot
    return bot
