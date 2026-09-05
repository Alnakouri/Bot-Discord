# -*- coding: utf-8 -*-
import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Console Windows en cp1252 : forcer l'UTF-8 pour que les emojis des messages
# ne fassent pas crasher le script (UnicodeEncodeError).
for _stream in (sys.stdout, sys.stderr):
    if getattr(_stream, "encoding", "").lower() not in ("utf-8", "utf8"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # flux non reconfigurable (deja UTF-8, ou redirige) : la sonde tourne quand meme

# Add root directory to sys.path
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Import secure env loader
try:
    from shared.secure_env import load_secure_env
except ImportError:
    # Fallback to dotenv
    try:
        from dotenv import load_dotenv
        def load_secure_env(path):
            load_dotenv(path / ".env")
    except ImportError:
        def load_secure_env(path):
            pass

# API URLs
AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DATA_DIR = Path(__file__).parent.parent / "data"

_received = {"code": None, "error": None}

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _received["code"] = params["code"][0]
            body = "<h1>Autorisation reçue ✅</h1><p>Tu peux fermer cet onglet et revenir au terminal.</p>"
        else:
            _received["error"] = params.get("error_description", ["Erreur inconnue"])[0]
            body = f"<h1>Échec ❌</h1><p>{_received['error']}</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        return

def get_bot_dir(bot_name: str) -> Path:
    root = Path(__file__).parent.parent
    mapping = {
        "sheogorath": "Sheogorath",
        "maiq": "MaiqBot",
        "maiqbot": "MaiqBot",
        "johnny": "JohnnyBot",
        "johnnybot": "JohnnyBot",
        "sugar": "SugarBot",
        "sugarbot": "SugarBot",
        "malena": "MalenaBot",
        "malenabot": "MalenaBot",
        "alfred": "Alfred",
    }
    dir_name = mapping.get(bot_name.lower(), bot_name)
    path = root / dir_name
    if path.exists():
        return path
    raise FileNotFoundError(f"Répertoire du bot '{dir_name}' introuvable.")

def run_oauth_flow(client_id, client_secret, port=3000):
    redirect_uri = f"http://localhost:{port}"
    scopes = ["chat:read", "chat:edit"]
    qs = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "force_verify": "true",
    })
    url = f"{AUTHORIZE_URL}?{qs}"
    print("\n>>> Connecte-toi avec le COMPTE DU STREAMER puis autorise l'application.\n")
    print(f"Si le navigateur ne s'ouvre pas, ouvre ce lien manuellement :\n{url}\n")
    webbrowser.open(url)

    print(f"En attente du retour OAuth sur {redirect_uri} ...")
    server = HTTPServer(("localhost", port), _CallbackHandler)
    while _received["code"] is None and _received["error"] is None:
        server.handle_request()
    server.server_close()

    if _received["error"]:
        print(f"\n❌ Autorisation refusée : {_received['error']}")
        sys.exit(1)

    code = _received["code"]
    print("✅ Code reçu, échange contre les tokens...")

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        print(f"\n❌ Échec de l'échange de token ({e.code}): {e.read().decode('utf-8', 'replace')}")
        sys.exit(1)

    access_token = payload["access_token"]
    refresh_token = payload["refresh_token"]
    expires_in = payload.get("expires_in", 3600)
    expires_at = time.time() + expires_in

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    auth_path = DATA_DIR / "twitch_chat_auth_probe.json"
    with open(auth_path, "w", encoding="utf-8") as f:
        json.dump({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
        }, f, indent=2)
    print(f"\n✅ Tokens de la sonde écrits dans : {auth_path}")

def check_and_refresh_probe_token(client_id, client_secret):
    auth_file = DATA_DIR / "twitch_chat_auth_probe.json"
    if not auth_file.exists():
        print("❌ Fichier de token de sonde absent. Lance d'abord --auth")
        sys.exit(1)
        
    with open(auth_file, "r", encoding="utf-8") as f:
        auth_data = json.load(f)
        
    access_token = auth_data["access_token"]
    refresh_token = auth_data["refresh_token"]
    expires_at = auth_data.get("expires_at", 0)
    
    if time.time() >= expires_at - 60:
        print("🔄 Token de sonde expiré ou expirant bientôt, rafraîchissement...")
        data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                payload = json.load(resp)
                access_token = payload["access_token"]
                refresh_token = payload.get("refresh_token", refresh_token)
                expires_in = payload.get("expires_in", 3600)
                expires_at = time.time() + expires_in
                
                with open(auth_file, "w", encoding="utf-8") as fw:
                    json.dump({
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "expires_at": expires_at
                    }, fw, indent=2)
                print("✅ Token de sonde rafraîchi avec succès.")
        except Exception as e:
            print(f"❌ Impossible de rafraîchir le token: {e}")
            sys.exit(1)
            
    return access_token

def get_probe_username(client_id, token):
    req = urllib.request.Request(
        "https://api.twitch.tv/helix/users",
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            return data["data"][0]["login"]
    except Exception as e:
        print(f"❌ Impossible de récupérer le nom d'utilisateur du streamer: {e}")
        sys.exit(1)

def get_twitch_channel(bot_name: str) -> str:
    config_path = DATA_DIR / "twitch_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                bot_cfg = config.get(bot_name.lower(), {})
                chat_channels = bot_cfg.get("chat_channels", [])
                if chat_channels:
                    return chat_channels[0].strip().lower().lstrip("#")
        except Exception:
            pass  # config illisible : on retombe sur la variable d'environnement
    env_channels = os.getenv("TWITCH_CHAT_CHANNELS", "")
    if env_channels:
        return env_channels.split(",")[0].strip().lower().lstrip("#")
    
    bot_username = os.getenv("TWITCH_BOT_USERNAME", "")
    if bot_username:
        return bot_username.strip().lower().lstrip("#")
        
    raise ValueError("Impossible de déterminer le canal Twitch pour la sonde.")

def count_sentences(text: str) -> int:
    try:
        from shared.twitch.llm import _TRAILING_EMOJI
    except ImportError:
        # Fallback inline regex
        _TRAILING_EMOJI = re.compile(
            r"\s*("
            r"(?:[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
            r"\U0000FE00-\U0000FE0F\U0000200D]+)+"
            r")\s*$"
        )

    m = _TRAILING_EMOJI.search(text)
    if m:
        text = text[:m.start()].rstrip()
    
    _ELLIPSIS = "\x00"
    protected = re.sub(r'\.\.\.+|…', _ELLIPSIS, text)
    sentences = re.split(r'(?<=[.!?])\s+', protected)
    sentences = [s for s in sentences if s.strip()]
    return len(sentences)

def ends_properly(text: str) -> bool:
    stripped = text.strip()
    try:
        from shared.twitch.llm import _TRAILING_EMOJI
    except ImportError:
        _TRAILING_EMOJI = re.compile(
            r"\s*("
            r"(?:[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
            r"\U0000FE00-\U0000FE0F\U0000200D]+)+"
            r")\s*$"
        )

    if _TRAILING_EMOJI.search(stripped):
        return True
    if re.search(r"[.!?…—»\"')\]]$", stripped):
        return True
    return False

def starts_with_quoted_probe(reply: str, probe: str) -> bool:
    probe_clean = re.sub(r"^@[^\s]+\s+", "", probe).strip()
    m = re.match(r'^\s*["«“\'‘]([^"»”\'’]+)["»”\'’]', reply)
    if m:
        quoted_content = m.group(1).lower()
        if quoted_content in probe_clean.lower() or probe_clean.lower() in quoted_content:
            return True
    return False

def is_empty_teaser(last_sentence: str) -> bool:
    pattern = r"(histoire|suite|conte)[,.]?\s*(donc)?\s*[.!?…]*\s*\W*$"
    return bool(re.search(pattern, last_sentence, re.IGNORECASE))

async def connect_irc_reader(channel):
    reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
    writer.write(b"PASS irc_is_great\r\n")
    writer.write(f"NICK justinfan{time.time_ns() % 100000}\r\n".encode())
    writer.write(f"JOIN #{channel}\r\n".encode())
    await writer.drain()
    return reader, writer

async def send_probe_message(channel, token, username, message):
    reader, writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
    writer.write(f"PASS oauth:{token}\r\n".encode())
    writer.write(f"NICK {username}\r\n".encode())
    writer.write(f"JOIN #{channel}\r\n".encode())
    await writer.drain()
    
    # Wait to ensure join
    await asyncio.sleep(1.5)
    
    writer.write(f"PRIVMSG #{channel} :{message}\r\n".encode())
    await writer.drain()
    
    writer.close()
    await writer.wait_closed()

async def run_single_probe(channel, bot_username, probe_msg, token, streamer_username, timeout=60):
    reader, writer = await connect_irc_reader(channel)
    bot_reply = None
    
    try:
        await send_probe_message(channel, token, streamer_username, probe_msg)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                line_bytes = await asyncio.wait_for(reader.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            
            if line.startswith("PING"):
                writer.write(b"PONG :tmi.twitch.tv\r\n")
                await writer.drain()
                continue
            
            match = re.match(r"^:([^!]+)![^@]+@[^\s]+\s+PRIVMSG\s+#([^\s]+)\s+:(.*)$", line)
            if match:
                sender = match.group(1).lower()
                content = match.group(3)
                if sender == bot_username.lower():
                    bot_reply = content
                    break
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass  # la socket est deja fermee
            
    return bot_reply

async def main_async():
    parser = argparse.ArgumentParser(description="Sondes live automatisées pour les bots Twitch.")
    parser.add_argument("--bot", default="sheogorath", help="bot_id (ex: sheogorath, johnny)")
    parser.add_argument("--probe", action="append", help="Sonde spécifique à envoyer (peut être répété)")
    parser.add_argument("--auth", action="store_true", help="Lance la procédure d'authentification pour la sonde")
    parser.add_argument("--channel", help="Force le canal Twitch de test")
    parser.add_argument("--redirect-port", type=int, default=3000, help="Port pour la redirection OAuth")
    args = parser.parse_args()

    try:
        bot_dir = get_bot_dir(args.bot)
        load_secure_env(bot_dir)
    except Exception as e:
        print(f"⚠️ Impossible de charger l'environnement du bot: {e}")
        load_secure_env(Path(__file__).parent.parent)

    client_id = os.getenv("TWITCH_CLIENT_ID")
    client_secret = os.getenv("TWITCH_CLIENT_SECRET")
    bot_username = os.getenv("TWITCH_BOT_USERNAME")

    if not client_id or not client_secret:
        print("❌ TWITCH_CLIENT_ID ou TWITCH_CLIENT_SECRET non configuré dans l'environnement du bot.")
        sys.exit(1)

    if args.auth:
        run_oauth_flow(client_id, client_secret, port=args.redirect_port)
        return

    access_token = check_and_refresh_probe_token(client_id, client_secret)
    streamer_username = get_probe_username(client_id, access_token)
    print(f"🔑 Connecté en tant que sondeur (streamer) : {streamer_username}")

    if not bot_username:
        print("❌ TWITCH_BOT_USERNAME non défini dans l'environnement.")
        sys.exit(1)

    channel = args.channel or get_twitch_channel(args.bot)
    print(f"📡 Canal cible : #{channel} | Bot : {bot_username}")

    trigger = f"@{bot_username}"

    probes = []
    if args.probe:
        for p in args.probe:
            probes.append((p.replace("<trigger>", trigger), p))
    else:
        probes = [
            (f"{trigger} es-tu fou ?", "<trigger> es-tu fou ?"),
            (f"{trigger} t'es nul", "<trigger> t'es nul"),
            (f"{trigger} raconte-moi une histoire", "<trigger> raconte-moi une histoire"),
            (f"{trigger} n'importe quoi", "<trigger> n'importe quoi")
        ]

    had_failure = False

    print("\n🚀 Lancement des sondes...")
    for idx, (probe_msg, raw_probe) in enumerate(probes, 1):
        print(f"\n[{idx}/{len(probes)}] Envoi de : '{probe_msg}'")
        
        reply = await run_single_probe(channel, bot_username, probe_msg, access_token, streamer_username)
        
        if reply is None:
            print("❌ FAIL : Aucune réponse reçue (timeout 60s)")
            had_failure = True
            continue
            
        print(f"💬 Réponse reçue : '{reply}'")
        
        warnings = []
        failures = []
        
        if not ends_properly(reply):
            failures.append("La réponse ne se termine pas par une ponctuation finale propre ni un emoji (mot tronqué ?)")
            
        if starts_with_quoted_probe(reply, probe_msg):
            failures.append("L'ouverture cite la sonde entre guillemets (anti-écho en panne)")
            
        s_count = count_sentences(reply)
        print(f"ℹ️ Nombre de phrases détectées : {s_count}")
        
        if "es-tu fou ?" in probe_msg:
            if s_count > 4:
                failures.append(f"Dépasse le budget de 4 phrases pour une question (trouvé: {s_count})")
        elif "t'es nul" in probe_msg:
            if s_count > 4:
                failures.append(f"Dépasse le budget de 4 phrases pour une insulte (trouvé: {s_count})")
        elif "raconte-moi une histoire" in probe_msg:
            if s_count > 10:
                failures.append(f"Dépasse le budget de 10 phrases pour une histoire (trouvé: {s_count})")
        elif "n'importe quoi" in probe_msg:
            if s_count > 4:
                failures.append(f"Dépasse le budget de 4 phrases par défaut (trouvé: {s_count})")
            
            _ELLIPSIS = "\x00"
            protected = re.sub(r'\.\.\.+|…', _ELLIPSIS, reply)
            sentences = [s for s in re.split(r'(?<=[.!?])\s+', protected) if s.strip()]
            if sentences:
                last_sentence = sentences[-1].replace(_ELLIPSIS, "...")
                if is_empty_teaser(last_sentence):
                    warnings.append(f"La réponse se termine par une annonce vide / teaser suspect : '{last_sentence}'")

        if failures:
            print("❌ FAIL :")
            for f in failures:
                print(f"   - {f}")
            had_failure = True
        elif warnings:
            print("⚠️ WARN :")
            for w in warnings:
                print(f"   - {w}")
        else:
            print("✅ OK")
            
        if idx < len(probes):
            print("⏳ Espacement anti rate-limit (15s)...")
            await asyncio.sleep(15)

    print("\n================ REPORT ================")
    if had_failure:
        print("❌ Résultat global : FAIL")
        sys.exit(1)
    else:
        print("✅ Résultat global : OK")
        sys.exit(0)

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nInterrompu.")
        sys.exit(1)

if __name__ == "__main__":
    main()
