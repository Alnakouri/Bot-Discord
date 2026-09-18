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

    async def get_channel_info(self, login: str) -> dict | None:
        """Titre et jeu d'une chaine, MEME HORS LIGNE (deux appels Helix).

        `/streams` ne rend rien quand la chaine est eteinte : une simulation d'annonce
        devrait alors inventer un titre et un jeu, et ne testerait plus rien de reel.
        `/users` donne l'identifiant, `/channels` donne le dernier titre et le dernier
        jeu declares — les vraies valeurs, celles qu'une annonce afficherait.
        """
        try:
            await self.ensure_token()
        except Exception:
            return None

        headers = {"Client-ID": self.client_id, "Authorization": f"Bearer {self.token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.twitch.tv/helix/users",
                                       headers=headers, params={"login": login.lower()},
                                       timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    users = (await resp.json()).get("data", [])
                if not users:
                    return None
                user = users[0]

                async with session.get("https://api.twitch.tv/helix/channels",
                                       headers=headers,
                                       params={"broadcaster_id": user["id"]},
                                       timeout=10) as resp:
                    chaine = {}
                    if resp.status == 200:
                        donnees = (await resp.json()).get("data", [])
                        chaine = donnees[0] if donnees else {}
        except Exception:
            return None

        return {
            "user_id": user["id"],
            "user_login": user["login"],
            "user_name": user.get("display_name") or user["login"],
            "title": chaine.get("title", ""),
            "game_name": chaine.get("game_name", ""),
            "profile_image_url": user.get("profile_image_url", ""),
        }


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
                 mistral_client=None, groq_client=None,  nvidia_client=None,
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
        self.nvidia_client = nvidia_client
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

    async def simuler_annonce(self, canal, login: str | None = None) -> dict:
        """Joue une annonce complete dans `canal`, a la demande, sans attendre un live.

        Le chemin est le VRAI : meme resolution du streamer, meme embed, meme accroche
        ecrite par le modele, meme repli statique. Trois differences, toutes voulues :

        1. **Le salon est celui d'ou la commande part**, jamais celui de la config. Un
           test n'a rien a faire dans le salon de la communaute.
        2. **L'anti-doublon est saute.** `_recent_announcement_exists` regarde
           l'historique du salon et fait taire le 2e bot qui parle du meme streamer
           dans les 30 minutes : sur six bots lances ensemble, un seul parlerait et
           les cinq autres auraient l'air casses. Ici on veut justement les six voix.
        3. **Ce qui est FAUX est signale.** Si la chaine n'est pas en direct, le titre
           et le jeu restent les vrais (`/channels` les rend hors ligne), mais le
           nombre de spectateurs et la vignette n'existent pas : l'embed le dit dans son
           pied. Une annonce de test indistinguable d'une vraie ferait croire a un live.

        Rend un petit compte rendu — pour le JOURNAL, pas pour le salon
        ([[gotcha-un-bot-ne-parle-jamais-de-sa-mecanique]]).
        """
        cfg = self.load_config()
        abonnements = cfg.get("subscriptions", []) or []

        if not login:
            for sub in abonnements:
                if sub.get("twitch_login"):
                    login = sub["twitch_login"]
                    break
        if not login:
            return {"ok": False, "raison": "aucun streamer : ni argument, ni abonnement configure"}

        login = login.strip().lstrip("@").lower()

        # 1. En direct ? Si oui, les donnees sont reelles de bout en bout.
        stream = None
        try:
            stream = (await self.client.get_streams([login])).get(login)
        except Exception as e:
            self.logger.warning(f"⚠️ [TWITCH] Simulation : /streams indisponible ({e})")

        simulee = stream is None
        if simulee:
            infos = await self.client.get_channel_info(login)
            if not infos:
                return {"ok": False, "raison": f"chaine Twitch introuvable : {login}"}
            stream = {
                "id": f"simulation-{int(time.time())}",
                "user_id": infos["user_id"],
                "user_login": infos["user_login"],
                "user_name": infos["user_name"],
                "title": infos["title"] or "(aucun titre declare)",
                "game_name": infos["game_name"] or "Inconnu",
                "viewer_count": 0,
                "thumbnail_url": "",
            }

        # 2. Le meme embed que l'annonce reelle, et le pied qui dit ce qui est faux.
        embed = build_embed(stream, stream["user_login"])
        if simulee:
            embed.set_footer(text="Twitch · simulation — la chaine n'est pas en direct")

        # 3. Le meme contenu : message custom s'il existe, sinon l'accroche du modele.
        url_twitch = f"https://twitch.tv/{stream['user_login']}"
        sub = next((s for s in abonnements
                    if (s.get("twitch_login") or "").lower() == login), {})
        custom = sub.get("custom_message")
        origine = "custom"
        if custom:
            try:
                contenu = custom.format(streamer=stream["user_name"], title=stream.get("title", ""),
                                        game=stream.get("game_name", "Inconnu"), url=url_twitch)
            except Exception:
                contenu = custom
        else:
            accroche = await self._generate_hype(stream)
            if accroche:
                contenu, origine = f"{accroche}\n{url_twitch}", "modele"
            else:
                contenu = random.choice(GENERIC_HYPE).format(
                    streamer=stream["user_name"], title=stream.get("title", ""),
                    game=stream.get("game_name", "Inconnu"), url=url_twitch)
                origine = "repli statique"

        await canal.send(content=contenu, embed=embed)
        self.logger.info(
            f"🧪 [TWITCH] Simulation d'annonce pour {stream['user_name']} dans "
            f"#{getattr(canal, 'name', canal.id)} — "
            f"{'chaine HORS LIGNE (donnees partielles)' if simulee else 'chaine EN DIRECT (donnees reelles)'}, "
            f"accroche : {origine}"
        )
        return {"ok": True, "simulee": simulee, "origine": origine,
                "streamer": stream["user_name"]}

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
            from shared.models import CASCADE_ANNONCE
        except Exception:
            return None

        streamer = stream.get("user_name", "")
        title = stream.get("title", "") or "inconnu"
        game = stream.get("game_name", "") or "inconnu"

        # ⚠️ « Donne envie de regarder » rendait des annonces correctes et plates. On
        # demande maintenant une INVITATION adressée au salon — « venez », pas « il est
        # en live » — et l'emoji est explicitement autorisé : rien ne le retire sur ce
        # chemin, mais tant qu'on ne le demandait pas, l'accroche sortait sèche.
        # La borne d'honnêteté ne bouge PAS : c'est précisément une accroche enthousiaste
        # qui invente un fait sur le jeu, et le salon y croit.
        #
        # ⚠️ 2026-09-18, EN LIVE (johnny, 12:12, #les-coupains-en-stream) : « Cinq ans de
        # stream et un premier pas dans Elden Ring AVEC streameuse_amie ». streameuse_amie EST la
        # streameuse, et elle jouait seule. Deux faits inventés dans une phrase : son
        # ancienneté, et une coéquipière.
        #
        # La borne d'honnêteté ne voyait NI l'un NI l'autre : elle énumérait le JEU (« pas
        # de qualité, note, histoire ou détail inventés ») et le LIVE (« tu ne l'as pas
        # regardé »). La PERSONNE n'y figurait pas — alors que la ligne juste au-dessus
        # demande de « mettre en valeur le streamer », à température 0.95. Le prompt
        # autorisait donc à broder sur quelqu'un et ne bornait que le décor :
        # [[gotcha-une-permission-bat-une-demonstration]].
        #
        # Le rôle du nom mérite sa propre phrase : le modèle ne reçoit qu'un NOM, et rien
        # ne lui dit que ce nom est CELUI QUI JOUE. « Ne mens pas » ne protège de rien
        # quand le modèle ignore de qui on parle.
        #
        # ⚠️ Et cette phrase DÉCRIT le défaut, elle ne le montre pas. Écrire ici la tournure
        # fautive avec le vrai nom du streamer dedans la placerait mot pour mot dans le
        # contexte, à deux lignes de l'endroit où le modèle rédige : c'est le piège
        # [[gotcha-le-prompt-enseigne-le-tic-interdit]], déjà payé deux fois ici, et la
        # raison pour laquelle la fiche d'Alfred a été dé-citée (`3e3c91e`).
        #
        # Le GENRE est le même trou, pas encore mordu : le français accorde, l'API ne rend
        # aucun genre, et deviner se trompe une fois sur deux sur une personne réelle. On
        # demande donc une tournure qui n'ait pas à choisir.
        system_prompt = (
            f"SYSTEM: {self.personality_prompt}\n"
            "INSTRUCTION: Annonce, DANS TA VOIX et avec TA personnalité, qu'un streamer vient "
            "de lancer un live Twitch. Écris UNE accroche très courte (1 à 2 phrases), "
            "TOUJOURS positive et enthousiaste, qui met en valeur le streamer et le jeu et "
            "DONNE ENVIE DE REJOINDRE le live : parle au salon, invite-le franchement à venir "
            "regarder, ne te contente pas de constater que le live existe. "
            "Tu PEUX utiliser un ou deux emoji, s'ils collent à ton personnage. "
            "Tu peux enjoliver le TON, mais reste HONNÊTE : n'invente AUCUN fait "
            "sur le jeu (pas de superlatif présenté comme vrai type « le meilleur jeu de l'année », "
            "pas de qualité, note, histoire ou détail inventés), et n'invente rien non plus sur ce "
            "qui se passe en ce moment dans le live : tu ne l'as pas regardé. "
            "N'invente RIEN non plus sur LA PERSONNE qui stream : ni son ancienneté ou son "
            "nombre d'années de stream, ni son niveau, ni son passé, ni sa communauté. "
            "Le nom donné ci-dessous est celui de LA PERSONNE QUI JOUE et qui tient ce "
            "live : ce n'est ni un jeu, ni un personnage, ni quelqu'un qui l'accompagne. "
            "Ta phrase ne doit donc jamais le présenter comme la personne EN COMPAGNIE de "
            "qui on joue, et tu ne dois pas supposer que le live se joue à plusieurs — sauf "
            "si le titre ci-dessous le dit explicitement. "
            "Tu ne connais pas non plus son genre : tourne ta phrase pour n'avoir pas à le "
            "deviner, plutôt que de choisir au hasard. "
            "Appuie-toi UNIQUEMENT sur le titre "
            "du live et le nom du jeu ci-dessous ; si tu ne connais pas le jeu, reste enthousiaste "
            "sans affirmer quoi que ce soit de faux. N'écris PAS le lien (il est ajouté séparément). "
            f"Streamer : {streamer}. Titre du live : {title}. Jeu : {game}."
        )
        try:
            text = await generate_response(
                routing={"type": RequestType.TEXT, "reason": "twitch_announce"},
                system_prompt=system_prompt, transcript="",
                user_message="Annonce ce live à ta communauté.",
                conversation_history=[], media_data=None, mime_type="",
                key_manager=self.key_manager, mistral_client=self.mistral_client,
                groq_client=self.groq_client,  nvidia_client=getattr(self, "nvidia_client", None),
                bot_label=self.bot_label, temperature=0.95,
                # 120 tokens coupaient l'annonce en plein mot (mesuré : mistral-large
                # tronqué sur 2 tirages sur 4). Une accroche fait 1 à 2 phrases, la
                # consigne s'en charge ; ce plafond n'est qu'un filet.
                max_tokens=200,
                cascade=CASCADE_ANNONCE,
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
            except Exception as e:
                self.logger.debug(f"[TWITCH] date de debut de live illisible, fenetre par defaut : {e}")

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

# Qui repond quand on ecrit `!annonce johnny`. La cle est le `bot_id` passe a
# `setup_twitch_announcer` ; les valeurs sont ce qu'un humain tape vraiment.
# ⚠️ Les six bots lisent la MEME table : un bot absent d'ici ne serait jamais appelable
# par son nom, et personne ne le verrait — c'est la moitie des ennuis de ce projet
# ([[gotcha-un-bot-sur-six-manque-toujours]]). Un verrou la compare aux six dossiers.
ALIAS_BOTS = {
    "alfred":     ("alfred", "majordome"),
    "johnny":     ("johnny", "johnnybot", "silverbot", "silverhand"),
    "maiq":       ("maiq", "maiqbot", "khajiit"),
    "malena":     ("malena", "gitane"),
    "sugar":      ("sugar", "sugarbot"),
    "sheogorath": ("sheogorath", "sheo"),
}


def _normaliser(mot: str) -> str:
    """« M'aiq » et « maïq » doivent designer le meme bot qu'un `maiq` tape a la va-vite."""
    import unicodedata
    sans_accent = unicodedata.normalize("NFD", (mot or "").strip().lower())
    sans_accent = "".join(c for c in sans_accent if unicodedata.category(c) != "Mn")
    return sans_accent.replace("'", "").replace("-", "").replace("_", "")


def bot_vise(mot: str) -> str | None:
    """Rend le `bot_id` designe par `mot`, ou None si ce mot ne nomme aucun bot."""
    cible = _normaliser(mot)
    if not cible:
        return None
    for bot_id, alias in ALIAS_BOTS.items():
        if cible == _normaliser(bot_id) or cible in {_normaliser(a) for a in alias}:
            return bot_id
    return None


def lire_arguments_annonce(args) -> tuple[str | None, str | None]:
    """Separe « a qui je parle » de « de quelle chaine on parle ».

    `!annonce`                  -> (None, None)        les six repondent, streamer configure
    `!annonce johnny`           -> ("johnny", None)    Johnny seul
    `!annonce streameuse_amie`        -> (None, "streameuse_amie") les six, sur cette chaine
    `!annonce johnny streameuse_amie` -> ("johnny", "streameuse_amie")

    Un mot qui ne nomme aucun bot est donc lu comme un login Twitch. C'est le bon defaut :
    les noms de bots forment une liste fermee et connue, les logins non.
    ⚠️ Un streamer qui s'appellerait « sugar » serait pris pour le bot. Cas assume : il
    reste `!annonce sugar sugar`.
    """
    mots = [m for m in (args or ()) if m and m.strip()]
    if not mots:
        return None, None
    cible = bot_vise(mots[0])
    if cible:
        return cible, (mots[1] if len(mots) > 1 else None)
    return None, mots[0]


async def effacer_la_commande(ctx, logger) -> bool:
    """Retire le message `!annonce…` pour ne laisser que l'annonce.

    ⚠️ A six bots, cinq echouent FORCEMENT : le premier arrive supprime, les autres
    tombent sur un `NotFound`. C'est le cas nominal, pas une panne — il ne doit donc ni
    crier dans le journal ni empecher l'annonce de partir
    ([[gotcha-une-alerte-qui-crie-pour-du-nominal]]).

    Sans la permission « Gerer les messages », on le dit une fois au journal et on
    continue : une annonce vaut mieux qu'un abandon parce qu'un menage a echoue.
    """
    try:
        await ctx.message.delete()
        return True
    except discord.NotFound:
        return False        # un autre bot a ete plus rapide : nominal
    except discord.Forbidden:
        logger.info("🧪 [TWITCH] !annonce : message non supprime, permission "
                    "« Gerer les messages » absente")
        return False
    except Exception as e:
        logger.warning(f"⚠️ [TWITCH] !annonce : suppression du message impossible : {e}")
        return False


def enregistrer_commande_annonce(bot, announcer, logger) -> bool:
    """Ajoute `!annonce [login]` : rejoue une annonce a la demande, pour la voir.

    Elle est enregistree ICI et pas dans les six fichiers de bots : un envoi ecrit en dur
    dans un bot echappe au module partage, a ses garde-fous et a son journal — Johnny
    accueillait ainsi 100 % des arrivants hors du tirage commun
    ([[gotcha-un-envoi-en-dur-contourne-le-partage]]). Un seul point d'ajout, et les six
    l'ont parce qu'ils appellent tous `setup_twitch_announcer`
    ([[gotcha-un-bot-sur-six-manque-toujours]]).

    ⚠️ Les six bots repondent donc a la MEME commande, dans le meme salon : c'est voulu,
    c'est meme l'interet — six accroches cote a cote, ecrites par six personas (et, en ce
    moment, par des modeles differents selon le quota disponible).

    Rend True si la commande a ete ajoutee. `on_ready` rejoue a chaque reconnexion
    ([[bug-on-ready-taches-relancees]]) : sans ce garde, discord.py leverait
    `CommandRegistrationError` et la reconnexion echouerait.
    """
    if bot.get_command("annonce") is not None:
        return False

    @bot.command(name="annonce")
    async def annonce(ctx, *args):
        """Rejoue une annonce de live dans CE salon (reserve aux gerants du serveur).

            !annonce                     les six bots repondent
            !annonce johnny              Johnny seul
            !annonce streameuse_amie           les six, sur cette chaine
            !annonce johnny streameuse_amie    Johnny seul, sur cette chaine
        """
        cible, login = lire_arguments_annonce(args)

        # Un bot qui n'est pas vise se tait AVANT toute verification : le nom sert a
        # n'en faire parler qu'un, et six refus de permission pour un seul appel
        # rempliraient le salon.
        if cible and cible != announcer.bot_id:
            return

        if ctx.guild is None:
            logger.info("🧪 [TWITCH] !annonce ignoree : hors serveur, aucune permission a verifier")
            return

        droits = getattr(ctx.author, "guild_permissions", None)
        if not (droits and (droits.manage_guild or droits.administrator)):
            # Silence volontaire : six bots qui refusent en choeur feraient six messages
            # pour un refus. Le refus va au journal, qui est fait pour ca.
            logger.info(f"🧪 [TWITCH] !annonce refusee a {ctx.author} (droits insuffisants)")
            return

        # Le menage AVANT l'annonce : la commande disparait, l'annonce prend sa place.
        # Si la generation echoue ensuite, le repli statique parle quand meme — la
        # commande ne peut donc pas s'evaporer sans rien laisser.
        await effacer_la_commande(ctx, logger)

        try:
            resultat = await announcer.simuler_annonce(ctx.channel, login)
        except Exception as e:
            logger.error(f"❌ [TWITCH] !annonce a echoue : {e}", exc_info=True)
            return

        if not resultat.get("ok"):
            logger.warning(f"⚠️ [TWITCH] !annonce sans effet : {resultat.get('raison')}")

    logger.info("🧪 [TWITCH] Commande !annonce disponible (gerants du serveur)")
    return True


def setup_twitch_announcer(bot, bot_id: str, logger, *, personality_prompt: str | None = None,
                           key_manager=None, mistral_client=None, groq_client=None,
                            nvidia_client=None, bot_label: str | None = None) -> TwitchAnnouncer | None:
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

    announcer = TwitchAnnouncer(
        bot, bot_id, logger, client_id, client_secret,
        personality_prompt=personality_prompt, key_manager=key_manager,
        mistral_client=mistral_client, groq_client=groq_client,
         nvidia_client=nvidia_client, bot_label=bot_label,
    )
    enregistrer_commande_annonce(bot, announcer, logger)
    return announcer
