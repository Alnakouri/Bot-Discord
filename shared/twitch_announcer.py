import os
import re
import time
import random
import datetime
import aiohttp
import discord
from pathlib import Path

# Path configuration
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
CONFIG_PATH = os.path.join(DATA_DIR, "twitch_config.json")

# Repère un login Twitch dans n'importe quel texte/URL (tolère www., m.,
# slash final, query string, casse). Sert à détecter une annonce déjà postée
# quel que soit son format (nos bots, Pingcord, intégration Twitch, etc.).
_TWITCH_LOGIN_RE = re.compile(
    r'(?:https?://)?(?:www\.|m\.)?twitch\.tv/([a-zA-Z0-9_]{3,25})',
    re.IGNORECASE,
)

def _logins_in_text(text) -> set:
    """Retourne l'ensemble des logins Twitch (en minuscules) trouvés dans `text`."""
    if not text:
        return set()
    return {m.group(1).lower() for m in _TWITCH_LOGIN_RE.finditer(str(text))}

# Repli STATIQUE (toujours positif) si la génération IA en personnage échoue ou
# est indisponible. {streamer}/{title}/{game}/{url} sont injectés.
GENERIC_HYPE = [
    "🔴 {streamer} est EN LIVE ! Filez voir ça : {url}",
    "🎉 Ça démarre ! {streamer} vient de lancer son live, venez nombreux : {url}",
    "🔴 En direct maintenant : {streamer} ! Ne ratez pas ça → {url}",
    "✨ {streamer} est en live et ça vaut clairement le coup d'œil : {url}",
    "🚀 C'est parti chez {streamer} ! Rejoignez le live : {url}",
    "💥 {streamer} a allumé le live ! On vous attend : {url}",
]

class TwitchClient:
    """
    Client for interacting with the Twitch Helix API using client_credentials.
    """
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = 0

    async def ensure_token(self):
        """
        Ensures we have a valid access token. Requests a new one if missing or expired.
        """
        if self.token and time.time() + 60 < self.token_expiry:
            return self.token

        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.token = data["access_token"]
                    self.token_expiry = time.time() + data["expires_in"]
                    return self.token
                else:
                    err_text = await resp.text()
                    raise Exception(f"Twitch OAuth failed ({resp.status}): {err_text}")

    async def get_streams(self, logins: list[str]) -> dict[str, dict | None]:
        """
        Polls Helix streams for the provided list of logins.
        Returns a dict mapping lowercase login -> stream dict (or None if offline).
        """
        if not logins:
            return {}

        results = {login.lower(): None for login in logins}
        
        try:
            await self.ensure_token()
        except Exception as e:
            # We can't query if we don't have a token
            raise Exception(f"Authentication failed: {e}")

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }

        # Query Helix in chunks of 100
        for i in range(0, len(logins), 100):
            chunk = logins[i:i+100]
            params = [("user_login", login.lower()) for login in chunk]
            url = "https://api.twitch.tv/helix/streams"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 401:
                        # Expired token, refresh and try once
                        self.token = None
                        await self.ensure_token()
                        headers["Authorization"] = f"Bearer {self.token}"
                        async with session.get(url, headers=headers, params=params, timeout=10) as retry_resp:
                            if retry_resp.status == 200:
                                data = await retry_resp.json()
                                for stream in data.get("data", []):
                                    results[stream["user_login"].lower()] = stream
                    elif resp.status == 429:
                        # Rate limit reached, skip this chunk
                        pass
                    elif resp.status == 200:
                        data = await resp.json()
                        for stream in data.get("data", []):
                            results[stream["user_login"].lower()] = stream
                    else:
                        # Other API errors, skip
                        pass

        return results

def build_embed(stream: dict, twitch_login: str) -> discord.Embed:
    """
    Builds the Discord Embed for a live announcement.
    """
    twitch_url = f"https://twitch.tv/{twitch_login.lower()}"
    
    # Process thumbnail url
    thumbnail_url = stream.get("thumbnail_url", "")
    if thumbnail_url:
        thumbnail_url = thumbnail_url.replace("{width}", "1280").replace("{height}", "720")
        thumbnail_url = f"{thumbnail_url}?t={int(time.time())}"

    embed = discord.Embed(
        title=f"{stream['user_name']} est en live !",
        description=stream.get("title", ""),
        url=twitch_url,
        color=0x9146FF
    )
    
    embed.add_field(name="Jeu", value=stream.get("game_name", "Inconnu"), inline=True)
    embed.add_field(name="Spectateurs", value=str(stream.get("viewer_count", 0)), inline=True)
    
    if thumbnail_url:
        embed.set_image(url=thumbnail_url)
        
    embed.set_author(name=stream["user_name"], url=twitch_url)
    embed.set_footer(text="Twitch")
    
    return embed

class TwitchAnnouncer:
    """
    Manages the polling and announcing loop for a specific Discord Bot.
    """
    def __init__(self, bot, bot_id: str, logger, client_id: str, client_secret: str,
                 personality_prompt: str | None = None, key_manager=None,
                 mistral_client=None, groq_client=None, openrouter_client=None,
                 bot_label: str | None = None):
        self.bot = bot
        self.bot_id = bot_id
        self.logger = logger
        self.client = TwitchClient(client_id, client_secret)
        self._announced = set()  # set of stream_ids currently announced
        # Pour générer un message d'annonce DANS LA VOIX du bot (optionnel).
        self.personality_prompt = personality_prompt
        self.key_manager = key_manager
        self.mistral_client = mistral_client
        self.groq_client = groq_client
        self.openrouter_client = openrouter_client
        self.bot_label = bot_label or bot_id

    def load_config(self) -> dict:
        """
        Reads data/twitch_config.json and returns this bot's configuration.
        """
        import json
        default_cfg = {"enabled": False, "poll_interval_seconds": 90, "subscriptions": []}
        if not os.path.exists(CONFIG_PATH):
            return default_cfg

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(self.bot_id, default_cfg)
        except Exception as e:
            self.logger.error(f"❌ [TWITCH] Erreur lors de la lecture du fichier de config : {e}")
            return default_cfg

    async def tick(self):
        """
        Fires on each polling interval. Loads configuration, polls live streams,
        and posts announcements for new lives.
        """
        try:
            cfg = self.load_config()
            if not cfg or not cfg.get("enabled", False):
                return

            subscriptions = cfg.get("subscriptions", [])
            if not subscriptions:
                return

            # Collect active subscription logins
            logins = list(set(sub["twitch_login"].lower() for sub in subscriptions if sub.get("twitch_login")))
            if not logins:
                return

            # Query current live stream status
            streams = await self.client.get_streams(logins)

            current_live_ids = set()
            for login, stream in streams.items():
                if stream:
                    stream_id = stream["id"]
                    current_live_ids.add(stream_id)

                    # Only announce if we haven't announced this stream ID during this online period
                    if stream_id not in self._announced:
                        # Find all subscriptions for this login and announce
                        for sub in subscriptions:
                            if sub.get("twitch_login", "").lower() == login:
                                await self._announce(stream, sub)
                        self._announced.add(stream_id)

            # Purge offline stream IDs from memory
            self._announced = self._announced.intersection(current_live_ids)

        except Exception as e:
            self.logger.error(f"❌ [TWITCH] Erreur dans la boucle Twitch : {e}", exc_info=True)

    async def _announce(self, stream: dict, sub: dict):
        channel_id = sub.get("discord_channel_id")
        if not channel_id:
            return

        try:
            channel_id = int(channel_id)
        except ValueError:
            self.logger.warning(f"⚠️ [TWITCH] ID de salon invalide : {channel_id}")
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH] Salon Discord introuvable ({channel_id}) : {e}")
                return

        # Check history to prevent multiple bots posting the same live
        twitch_login = stream["user_login"]
        if await self._recent_announcement_exists(channel, stream):
            # Déjà annoncé récemment (par nous, Pingcord, l'intégration Twitch…) → on se tait.
            return

        # Build embed & resolve the message content
        embed = build_embed(stream, twitch_login)
        twitch_url = f"https://twitch.tv/{twitch_login.lower()}"
        custom_msg = sub.get("custom_message")
        content = None

        if custom_msg:
            # 1) Message personnalisé saisi par l'utilisateur : PRIORITAIRE.
            try:
                content = custom_msg.format(
                    streamer=stream["user_name"],
                    title=stream.get("title", ""),
                    game=stream.get("game_name", "Inconnu"),
                    url=twitch_url
                )
            except Exception as e:
                self.logger.error(f"❌ [TWITCH] Échec du formatage du message custom : {e}")
                content = custom_msg
        else:
            # 2) Pas de message : on génère une accroche DANS LA VOIX du bot (IA),
            #    toujours positive ; repli sur une phrase statique si l'IA échoue.
            generated = await self._generate_hype(stream)
            if generated:
                content = f"{generated}\n{twitch_url}"
            else:
                content = random.choice(GENERIC_HYPE).format(
                    streamer=stream["user_name"],
                    title=stream.get("title", ""),
                    game=stream.get("game_name", "Inconnu"),
                    url=twitch_url
                )

        try:
            await channel.send(content=content, embed=embed)
            self.logger.info(f"📢 [TWITCH] Annonce de live envoyée pour {stream['user_name']} dans #{channel.name}")
        except Exception as e:
            self.logger.error(f"❌ [TWITCH] Échec de l'envoi de l'annonce Twitch dans #{channel_id} : {e}")

    async def _generate_hype(self, stream: dict) -> str | None:
        """
        Génère une phrase d'annonce dans la voix/personnalité du bot via la
        cascade LLM partagée. Toujours positive, met en valeur le streamer.
        Retourne None si la personnalité/les clés ne sont pas fournies ou si la
        génération échoue (l'appelant retombe alors sur une phrase statique).
        """
        if not self.personality_prompt or self.key_manager is None:
            return None
        try:
            from shared.llm_cascade import generate_response
            from shared.smart_router import RequestType
        except Exception:
            return None

        streamer = stream.get("user_name", "")
        title = stream.get("title", "") or "inconnu"
        game = stream.get("game_name", "") or "inconnu"

        system_prompt = (
            f"SYSTEM: {self.personality_prompt}\n"
            "INSTRUCTION: Annonce, DANS TA VOIX et avec TA personnalité, qu'un streamer vient "
            "de lancer un live Twitch. Écris UNE accroche très courte (1 à 2 phrases), "
            "TOUJOURS positive et enthousiaste, qui met en valeur le streamer et donne envie de "
            "regarder. N'invente aucun fait. N'écris PAS le lien (il est ajouté séparément). "
            f"Streamer : {streamer}. Titre du live : {title}. Jeu : {game}."
        )
        try:
            text = await generate_response(
                routing={"type": RequestType.TEXT, "reason": "twitch_announce"},
                system_prompt=system_prompt, transcript="",
                user_message="Annonce ce live à ta communauté.",
                conversation_history=[], media_data=None, mime_type="",
                key_manager=self.key_manager, mistral_client=self.mistral_client,
                groq_client=self.groq_client, openrouter_client=self.openrouter_client,
                bot_label=self.bot_label, temperature=0.95, max_tokens=120,
            )
            if text and text.strip():
                return text.strip()
        except Exception as e:
            self.logger.debug(f"ℹ️ [TWITCH] Génération IA de l'annonce échouée, repli statique : {e}")
        return None

    async def _recent_announcement_exists(self, channel, stream: dict, window_min: int = 30) -> bool:
        """
        True s'il existe déjà, dans l'historique récent du salon, une annonce de CE
        live (par un bot/webhook : nos bots, Pingcord, intégration Twitch, etc.).
        La fenêtre est élargie à la durée écoulée depuis le début du live (started_at,
        plafonnée à 12 h) pour aussi attraper une annonce postée tôt sur un long live.
        """
        twitch_login = (stream.get("user_login") or "").lower()
        if not twitch_login:
            return False

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_naive = datetime.datetime.utcnow()

        # Fenêtre = max(30 min, temps écoulé depuis le début du live + 5 min),
        # plafonnée à 12 h pour éviter de remonter trop loin dans l'historique.
        effective_window = float(window_min)
        started_at = stream.get("started_at")
        if started_at:
            try:
                st = datetime.datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
                mins_since_start = (now_utc - st).total_seconds() / 60.0
                effective_window = max(float(window_min), min(mins_since_start + 5.0, 12 * 60.0))
            except Exception:
                pass

        try:
            async for message in channel.history(limit=100):
                # On ne tient compte que des annonces automatisées (bots/webhooks).
                if not (getattr(message.author, "bot", False) or message.webhook_id):
                    continue

                # Hors fenêtre → comme l'historique est du plus récent au plus ancien,
                # tout le reste est plus vieux : on s'arrête.
                msg_time = message.created_at
                if msg_time.tzinfo is not None:
                    diff = now_utc - msg_time
                else:
                    diff = now_naive - msg_time
                if diff.total_seconds() / 60.0 >= effective_window:
                    break

                # Rassembler toutes les sources de texte du message + embeds.
                logins = _logins_in_text(message.content)
                for embed in message.embeds:
                    author = getattr(embed, "author", None)
                    footer = getattr(embed, "footer", None)
                    for piece in (
                        embed.url, embed.title, embed.description,
                        getattr(author, "url", None), getattr(author, "name", None),
                        getattr(footer, "text", None),
                    ):
                        logins |= _logins_in_text(piece)
                    for field in embed.fields:
                        logins |= _logins_in_text(field.name)
                        logins |= _logins_in_text(field.value)

                if twitch_login in logins:
                    return True
        except Exception as e:
            self.logger.debug(f"ℹ️ [TWITCH] Impossible de lire l'historique du salon {channel.id} : {e}")

        return False

def setup_twitch_announcer(bot, bot_id: str, logger, *, personality_prompt: str | None = None,
                           key_manager=None, mistral_client=None, groq_client=None,
                           openrouter_client=None, bot_label: str | None = None) -> TwitchAnnouncer | None:
    """
    Initializes TwitchAnnouncer if environmental credentials are set.
    Les paramètres optionnels (personality_prompt + cascade LLM) permettent de
    générer un message d'annonce dans la voix du bot quand aucun message custom
    n'est configuré. S'ils sont absents, on utilise une phrase statique positive.
    """
    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.info("📡 [TWITCH] Module Twitch non activé (crédentiels manquants)")
        return None

    return TwitchAnnouncer(
        bot, bot_id, logger, client_id, client_secret,
        personality_prompt=personality_prompt, key_manager=key_manager,
        mistral_client=mistral_client, groq_client=groq_client,
        openrouter_client=openrouter_client, bot_label=bot_label,
    )
