# -*- coding: utf-8 -*-
"""
Helper d'autorisation OAuth Twitch (User Access Token) — réutilisable par bot.

Ouvre le flux "Authorization Code" de Twitch dans le navigateur, récupère le code
via un petit serveur local, l'échange contre un access_token + refresh_token avec
TOUS les scopes utilisés par les bots (chat, profil, EventSub), puis écrit
data/twitch_chat_auth_<bot>.json (lu en priorité par shared/twitch_chat.py).

⚠️ Connecte-toi avec le COMPTE DU BOT (ex: le compte Johnny), pas avec ton compte
   principal ni celui d'un autre bot. force_verify=true force le ré-affichage du
   choix de compte pour éviter de réutiliser une session Sheo déjà ouverte.

Usage :
    python twitch_authorize.py --bot johnny \
        --client-id <CLIENT_ID_JOHNNY> --client-secret <CLIENT_SECRET_JOHNNY>

EventSub (channel points, subs, hype, polls, follow) — token du BROADCASTER :
    Ces events exigent le token du PROPRIÉTAIRE de la chaîne, pas celui du bot. Lance le
    helper avec le suffixe _broadcaster et CONNECTE-TOI AVEC TON COMPTE DE STREAMER :
        python twitch_authorize.py --bot johnny_broadcaster \
            --client-id <CLIENT_ID_JOHNNY> --client-secret <CLIENT_SECRET_JOHNNY>
    (même app que le bot ; écrit data/twitch_chat_auth_johnny_broadcaster.json, repéré
    automatiquement par setup_twitch_chat pour EventSub).

Optionnel :
    --redirect-port 3000   (doit correspondre à une OAuth Redirect URL de l'app)
    --no-write             (n'écrit pas le JSON, affiche juste les tokens)

Prérequis côté console dev.twitch.tv (app du bot) :
    - OAuth Redirect URLs doit contenir EXACTEMENT : http://localhost:3000
      (ou le port passé en --redirect-port).
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Scopes couvrant chat + profil + EventSub (Phase 4). Voir PLAN.md (P.2).
SCOPES = [
    "chat:read",                       # lire le chat (IRC)
    "chat:edit",                       # écrire dans le chat (IRC)
    "user:edit",                       # mettre à jour la bio (Update User)
    "user:manage:chat_color",          # changer la couleur du pseudo
    "channel:read:redemptions",        # channel points (redemptions)
    "moderator:read:followers",        # channel.follow v2
    "bits:read",                       # bits / cheers
    "channel:read:subscriptions",      # subs
    "channel:read:hype_train",         # hype train
    "channel:read:polls",              # sondages
]

AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
DATA_DIR = Path(__file__).parent / "data"

_received = {"code": None, "error": None}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (signature imposée par http.server)
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

    def log_message(self, *args):  # silence le logging HTTP par défaut
        return


NL = "\n"  # saut de ligne, pour les blocs multi-lignes ci-dessous


def est_broadcaster(bot_id: str) -> bool:
    """Le suffixe `_broadcaster` change QUEL COMPTE doit se connecter.

    ⚠️ C'est le seul echec probable de la manip EventSub : se connecter avec le compte
    du BOT rend un token qui n'est proprietaire d'aucune chaine → tous les abonnements
    « channel.… » repondent 403. Le message affiche doit donc suivre le suffixe, sinon
    l'outil dicte lui-meme la faute qu'il est cense eviter.
    """
    return bot_id.endswith("_broadcaster")


def consigne_compte(bot_id: str) -> str:
    """La phrase affichee juste avant d'ouvrir le navigateur."""
    if est_broadcaster(bot_id):
        return (">>> Connecte-toi avec le COMPTE DU STREAMER (le proprietaire de la "
                "chaine), PAS avec le compte du bot, puis autorise l'application.")
    return ">>> Connecte-toi avec le COMPTE DU BOT puis autorise l'application."


def lignes_env(bot_id: str, access_token: str, refresh_token: str) -> str:
    """Ce qu'on recopie dans le .env — ou surtout, ce qu'on n'y recopie PAS.

    ⚠️ Un token broadcaster colle dans TWITCH_OAUTH_TOKEN ferait parler le bot SOUS
    L'IDENTITE DU STREAMER dans son propre chat. Le fichier d'auth dedie suffit :
    setup_twitch_chat le repere tout seul.
    """
    if est_broadcaster(bot_id):
        return (NL + "ATTENTION : NE recopie PAS ces tokens dans le .env du bot : ils sont ceux du"
                + NL + "   STREAMER, et TWITCH_OAUTH_TOKEN ferait parler le bot sous son identite."
                + NL + "   Le fichier d'auth ci-dessus suffit, EventSub le trouve seul.")
    return (NL + "--- A ajouter dans le .env du bot (puis re-chiffrer) ---"
            + NL + "TWITCH_OAUTH_TOKEN=" + access_token
            + NL + "TWITCH_REFRESH_TOKEN=" + refresh_token
            + NL + "--------------------------------------------------------")


def main():
    parser = argparse.ArgumentParser(description="Autorisation OAuth Twitch par bot.")
    parser.add_argument("--bot", required=True, help="bot_id (ex: johnny, sheogorath)")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--redirect-port", type=int, default=3000)
    parser.add_argument("--no-write", action="store_true",
                        help="N'écrit pas le JSON, affiche seulement les tokens.")
    args = parser.parse_args()

    redirect_uri = f"http://localhost:{args.redirect_port}"

    # 1. Construire l'URL d'autorisation et l'ouvrir dans le navigateur
    qs = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
        "force_verify": "true",  # force le choix du compte (évite la session Sheo)
    })
    url = f"{AUTHORIZE_URL}?{qs}"
    print("\n" + consigne_compte(args.bot) + "\n")
    print(f"Si le navigateur ne s'ouvre pas, ouvre ce lien manuellement :\n{url}\n")
    webbrowser.open(url)

    # 2. Attendre le code sur le serveur local
    print(f"En attente du retour OAuth sur {redirect_uri} ...")
    server = HTTPServer(("localhost", args.redirect_port), _CallbackHandler)
    while _received["code"] is None and _received["error"] is None:
        server.handle_request()
    server.server_close()

    if _received["error"]:
        print(f"\n❌ Autorisation refusée : {_received['error']}")
        sys.exit(1)

    code = _received["code"]
    print("✅ Code reçu, échange contre les tokens...")

    # 3. Échanger le code contre access_token + refresh_token
    data = urllib.parse.urlencode({
        "client_id": args.client_id,
        "client_secret": args.client_secret,
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

    # 4. Écrire le JSON d'auth (lu en priorité au démarrage du bot)
    if not args.no_write:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        auth_path = DATA_DIR / f"twitch_chat_auth_{args.bot}.json"
        tmp_path = str(auth_path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
            }, f, indent=2)
        os.replace(tmp_path, auth_path)
        print(f"\n✅ Tokens écrits dans : {auth_path}")

    # 5. Afficher les lignes .env à intégrer (TWITCH_OAUTH_TOKEN est REQUIS au boot)
    print(lignes_env(args.bot, access_token, refresh_token))
    print(f"\nScopes accordés : {', '.join(SCOPES)}")
    print("Token valide ~", int(expires_in), "s ; le bot le rafraîchira automatiquement via le refresh_token.")


if __name__ == "__main__":
    main()
