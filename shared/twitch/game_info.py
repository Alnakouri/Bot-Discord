# -*- coding: utf-8 -*-
import os
import re
import time
import logging
import datetime
import unicodedata
import difflib
import aiohttp

# Global Caches
# channel_name (lower) -> (game_name, game_id, timestamp)
HELIX_CACHE = {}
HELIX_CACHE_TTL = 180  # 3 minutes

# game_name_normalized -> (game_facts_dict, timestamp)
IGDB_CACHE = {}
IGDB_CACHE_TTL = 86400  # 24 hours

# broadcaster_login (lower) -> broadcaster_id
USER_ID_CACHE = {}

logger = logging.getLogger("shared.twitch.game_info")

class IGDBClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = 0

    async def ensure_token(self):
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
                    raise Exception(f"Twitch OAuth for IGDB failed ({resp.status}): {err_text}")

    async def search_game(self, game_name: str) -> list:
        try:
            await self.ensure_token()
        except Exception as e:
            logger.error(f"❌ [IGDBClient] Authentication failed: {e}")
            return []

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "text/plain"
        }
        
        escaped_name = game_name.replace('"', '\\"')
        query = (
            f'search "{escaped_name}"; '
            f'fields name,platforms.name,genres.name,first_release_date,summary,'
            f'involved_companies.company.name,involved_companies.developer,involved_companies.publisher; '
            f'limit 5;'
        )
        url = "https://api.igdb.com/v4/games"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=query, timeout=10) as resp:
                    if resp.status == 401:
                        self.token = None
                        await self.ensure_token()
                        headers["Authorization"] = f"Bearer {self.token}"
                        async with session.post(url, headers=headers, data=query, timeout=10) as retry_resp:
                            if retry_resp.status == 200:
                                return await retry_resp.json()
                    elif resp.status == 200:
                        return await resp.json()
                    else:
                        err_text = await resp.text()
                        logger.warning(f"⚠️ [IGDBClient] Query failed ({resp.status}): {err_text}")
        except Exception as e:
            logger.error(f"❌ [IGDBClient] Request error: {e}")
        return []

    async def get_game_by_id(self, igdb_id) -> dict | None:
        """Interroge IGDB par son id numérique. Cache IGDB_CACHE sous 'id:<n>', 24 h. Ne lève jamais."""
        try:
            n = int(igdb_id)
        except (ValueError, TypeError):
            return None

        cache_key = f"id:{n}"
        now = time.time()
        if cache_key in IGDB_CACHE:
            val, ts = IGDB_CACHE[cache_key]
            if now - ts < IGDB_CACHE_TTL:
                return val

        try:
            await self.ensure_token()
        except Exception as e:
            logger.debug(f"[IGDBClient] Authentication failed: {e}")
            return None

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "text/plain"
        }
        query = f"fields name,summary,themes.name; where id = {n};"
        url = "https://api.igdb.com/v4/games"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=query, timeout=10) as resp:
                    if resp.status == 401:
                        self.token = None
                        await self.ensure_token()
                        headers["Authorization"] = f"Bearer {self.token}"
                        async with session.post(url, headers=headers, data=query, timeout=10) as retry_resp:
                            if retry_resp.status == 200:
                                res = await retry_resp.json()
                                game = res[0] if res else None
                                if game:
                                    IGDB_CACHE[cache_key] = (game, now)
                                return game
                    elif resp.status == 200:
                        res = await resp.json()
                        game = res[0] if res else None
                        if game:
                            IGDB_CACHE[cache_key] = (game, now)
                        return game
                    else:
                        err_text = await resp.text()
                        logger.debug(f"[IGDBClient] Query failed ({resp.status}): {err_text}")
        except Exception as e:
            logger.debug(f"[IGDBClient] Request error: {e}")
        return None

class HelixClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = 0

    async def ensure_token(self):
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
                    raise Exception(f"Twitch OAuth failed for Helix ({resp.status}): {err_text}")

    async def get_user_id(self, login: str) -> str | None:
        login_key = login.lower()
        if login_key in USER_ID_CACHE:
            return USER_ID_CACHE[login_key]

        try:
            await self.ensure_token()
        except Exception as e:
            logger.error(f"❌ [HelixClient] Authentication failed: {e}")
            return None

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }
        url = "https://api.twitch.tv/helix/users"
        params = {"login": login_key}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        users = data.get("data", [])
                        if users:
                            uid = users[0]["id"]
                            USER_ID_CACHE[login_key] = uid
                            return uid
        except Exception as e:
            logger.error(f"❌ [HelixClient] get_user_id error: {e}")
        return None

    async def get_current_game(self, chan: str, live_only: bool = False):
        """Le jeu du canal. Rend (nom, id).

        ⚠️ `live_only=True` change le SENS de la reponse : « ce qui est diffuse MAINTENANT »
        au lieu de « la derniere categorie posee sur la chaine ». Les deux sont utiles et
        ne se remplacent pas :
          - repondre a une question sur le jeu marche tres bien hors direct, d'ou le repli
            sur `helix/channels` en 2e etape ;
          - une invitation qui s'accroche au jeu, elle, parlerait d'Elden Ring des heures
            apres la fin du stream. Constate le 2026-09-22 : « le stream est termine » —
            et `helix/channels` rendait toujours le jeu de la veille.
        Le cache retient donc AUSSI si la reponse venait du direct.
        """
        chan_key = chan.lower().lstrip("#")
        now = time.time()

        if chan_key in HELIX_CACHE:
            en_cache = HELIX_CACHE[chan_key]
            # ⚠️ Entree a 3 elements = posee avant le 2026-09-22, liveness inconnue : on la
            # traite comme HORS direct, le choix prudent pour `live_only`.
            cached_game, cached_id, cached_ts = en_cache[:3]
            cached_live = en_cache[3] if len(en_cache) > 3 else False
            if now - cached_ts < HELIX_CACHE_TTL:
                if live_only and not cached_live:
                    return None, None
                return cached_game, cached_id

        try:
            await self.ensure_token()
        except Exception as e:
            logger.error(f"❌ [HelixClient] Authentication failed: {e}")
            return None, None

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }

        # 1. Try streams first
        url_streams = "https://api.twitch.tv/helix/streams"
        params_streams = {"user_login": chan_key}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_streams, headers=headers, params=params_streams, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        streams = data.get("data", [])
                        if streams:
                            game_name = streams[0].get("game_name")
                            game_id = streams[0].get("game_id")
                            HELIX_CACHE[chan_key] = (game_name, game_id, now, True)
                            return game_name, game_id
        except Exception as e:
            logger.error(f"❌ [HelixClient] get_streams error: {e}")

        # 2. Try offline fallback
        # ⚠️ Cette etape repond « la derniere categorie posee », pas « ce qui passe en ce
        # moment » : un appelant qui a besoin du DIRECT s'arrete ici.
        if live_only:
            HELIX_CACHE[chan_key] = (None, None, now, False)
            return None, None
        uid = await self.get_user_id(chan_key)
        if not uid:
            return None, None

        url_channel = "https://api.twitch.tv/helix/channels"
        params_channel = {"broadcaster_id": uid}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_channel, headers=headers, params=params_channel, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        channels = data.get("data", [])
                        if channels:
                            game_name = channels[0].get("game_name")
                            game_id = channels[0].get("game_id")
                            HELIX_CACHE[chan_key] = (game_name, game_id, now, False)
                            return game_name, game_id
        except Exception as e:
            logger.error(f"❌ [HelixClient] get_channels error: {e}")

        return None, None

    async def get_igdb_id(self, game_id) -> str | None:
        """GET https://api.twitch.tv/helix/games?id=<game_id> -> data[0]['igdb_id'], cache 24h. Ne lève jamais."""
        if not game_id:
            return None
        gid_str = str(game_id).strip()
        if not gid_str:
            return None
        cache_key = f"igdb_id:{gid_str}"
        now = time.time()
        if cache_key in HELIX_CACHE:
            val, ts = HELIX_CACHE[cache_key][:2]
            if now - ts < 86400:
                return val

        try:
            await self.ensure_token()
        except Exception as e:
            logger.debug(f"[HelixClient] Authentication failed: {e}")
            return None

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }
        url = "https://api.twitch.tv/helix/games"
        params = {"id": gid_str}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        games = data.get("data", [])
                        if games:
                            igdb_id = games[0].get("igdb_id")
                            HELIX_CACHE[cache_key] = (igdb_id, now)
                            return igdb_id
                    else:
                        err_text = await resp.text()
                        logger.debug(f"[HelixClient] get_igdb_id failed ({resp.status}): {err_text}")
        except Exception as e:
            logger.debug(f"[HelixClient] get_igdb_id error: {e}")
        return None


def fiche_courte(game: dict | None) -> str | None:
    """Rend 'Résumé : <summary[:300]> | Thèmes : <…>', ou None sans résumé."""
    if not game or not isinstance(game, dict):
        return None
    summary = (game.get("summary") or "").strip()
    if not summary:
        return None
    summary_court = summary[:300]
    themes_list = game.get("themes") or []
    themes = [t.get("name") for t in themes_list if isinstance(t, dict) and t.get("name")]
    if themes:
        return f"Résumé : {summary_court} | Thèmes : {', '.join(themes)}"
    return f"Résumé : {summary_court}"


def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = "".join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    name = re.sub(r'[^a-z0-9\s]', ' ', name)
    name = " ".join(name.split())
    return name

def clean_for_regex(text: str) -> str:
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    text = re.sub(r"[^a-z0-9\s\?']", " ", text)
    return " ".join(text.split())

def get_similarity(s1: str, s2: str) -> float:
    n1 = normalize_name(s1)
    n2 = normalize_name(s2)
    if n1 == n2:
        return 1.0
    return difflib.SequenceMatcher(None, n1, n2).ratio()

def find_best_match(helix_name: str, igdb_results: list) -> dict | None:
    if not igdb_results:
        return None
    
    normalized_helix = normalize_name(helix_name)
    best_match = None
    best_score = -1.0
    
    for game in igdb_results:
        igdb_name = game.get("name", "")
        if not igdb_name:
            continue
        
        normalized_igdb = normalize_name(igdb_name)
        if normalized_helix == normalized_igdb:
            return game
            
        score = get_similarity(helix_name, igdb_name)
        if score > best_score:
            best_score = score
            best_match = game
            
    if best_score >= 0.6:
        return best_match
        
    return None

MARKERS = [
    r"\?",
    r"\bc['’]est quoi\b",
    r"\bquel(?:le)?s?\b",
    r"\bsur quoi\b",
    r"\bqui a fait\b",
    r"\bca sort quand\b",
    r"\bsort quand\b",
    r"\bde quoi ca parle\b",
    r"\bde quoi parle\b",
    r"\bdispo sur\b",
    r"\bdisponible sur\b",
    r"\bwhat\b",
    r"\bwhich\b",
    r"\bwhen\b",
    r"\bwho\b"
]

PATTERNS = {
    "platform": [
        r"\bpc\b", r"\bps5\b", r"\bps4\b", r"\bxbox\b", r"\bswitch\b", r"\bsteam\b",
        r"\bconsole\b", r"\bdispo\b", r"\bdisponible\b", r"\bplateforme\b", r"\bplate-forme\b",
        r"\bplaystation\b", r"\bnintendo\b", r"\bsur quoi\b", r"\bsur quel\b"
    ],
    "genre": [
        r"\bgenre\b", r"\btype de jeu\b", r"\bstyle de jeu\b", r"\bfps\b", r"\brpg\b",
        r"\brogue\b", r"\bmmo\b", r"\brts\b", r"\bsimulateur\b", r"\btype\b"
    ],
    "studio": [
        r"\bstudio\b", r"\bdeveloppeur\b", r"\bediteur\b", r"\bqui a fait\b", r"\bdeveloper\b",
        r"\bpublisher\b", r"\bcree par\b", r"\bdeveloppe par\b", r"\bconcu par\b",
        r"\bdeveloppe\b", r"\bcree\b"
    ],
    "mode": [
        r"\bsolo\b", r"\bmulti\b", r"\bcoop\b", r"\bmultijoueur\b", r"\bcooperation\b",
        r"\bmultiplayer\b", r"\bsingleplayer\b", r"\bco-op\b", r"\bjouer a plusieurs\b"
    ],
    "release": [
        r"\bsortie\b", r"\bsort quand\b", r"\bdate\b", r"\brelease\b", r"\bannee\b", r"\bparution\b"
    ],
    "about": [
        r"\bca parle de quoi\b", r"\bde quoi ca parle\b", r"\bc['’]est quoi l['’]histoire\b",
        r"\bpitch\b", r"\bhistoire\b", r"\bde quoi parle\b", r"\babout\b", r"\bresume\b",
        r"\bsynopsis\b", r"\bscenario\b"
    ],
    "which_game": [
        r"\bc['’]est quoi ce jeu\b", r"\bquel jeu\b", r"\bwhat game\b", r"\bquel est ce jeu\b",
        r"\bnom du jeu\b"
    ]
}

def detect_game_question(text: str) -> str | None:
    cleaned = clean_for_regex(text)
    
    has_marker = False
    for marker in MARKERS:
        if re.search(marker, cleaned):
            has_marker = True
            break
            
    if not has_marker:
        return None
        
    for cat in ["which_game", "platform", "genre", "studio", "mode", "release", "about"]:
        patterns = PATTERNS[cat]
        for pat in patterns:
            if re.search(pat, cleaned):
                return cat
                
    return None

def format_facts_block(game: dict, category: str) -> str:
    parts = []
    parts.append(f"Nom du jeu: {game.get('name')}")
    
    if category in ("platform", "which_game", "about"):
        platforms = [p["name"] for p in game.get("platforms", []) if "name" in p]
        if platforms:
            parts.append(f"Plateformes: {', '.join(platforms)}")
            
    if category in ("genre", "which_game", "about"):
        genres = [g["name"] for g in game.get("genres", []) if "name" in g]
        if genres:
            parts.append(f"Genre: {', '.join(genres)}")
            
    if category in ("studio", "which_game", "about"):
        devs = []
        pubs = []
        for ic in game.get("involved_companies", []):
            comp = ic.get("company", {})
            if "name" in comp:
                if ic.get("developer"):
                    devs.append(comp["name"])
                if ic.get("publisher"):
                    pubs.append(comp["name"])
        if devs:
            parts.append(f"Studio/Developpeur: {', '.join(devs)}")
        if pubs:
            parts.append(f"Editeur: {', '.join(pubs)}")
            
    if category in ("release", "which_game", "about"):
        ts = game.get("first_release_date")
        if ts:
            try:
                year = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y")
                parts.append(f"Sortie: {year}")
            except Exception:
                pass  # date de sortie illisible : on l'omet de la fiche
                
    if category in ("about", "which_game", "mode"):
        summary = game.get("summary", "")
        if summary:
            summary = summary[:200] + "..." if len(summary) > 200 else summary
            parts.append(f"Resume: {summary}")
            
    return " | ".join(parts)

async def get_game_facts(game_name: str, client_id: str, client_secret: str, igdb_client: "IGDBClient | None" = None) -> dict | None:
    normalized = normalize_name(game_name)
    now = time.time()

    if normalized in IGDB_CACHE:
        cached_facts, cached_ts = IGDB_CACHE[normalized]
        if now - cached_ts < IGDB_CACHE_TTL:
            return cached_facts

    igdb = igdb_client or IGDBClient(client_id, client_secret)
    results = await igdb.search_game(game_name)
    best_match = find_best_match(game_name, results)
    
    if best_match:
        IGDB_CACHE[normalized] = (best_match, now)
        return best_match
        
    return None
