# -*- coding: utf-8 -*-
"""Sonde : deux bots partagent-ils une cle API ?

CHAQUE BOT A SA PROPRE CLE. PAS DE PARTAGE. C'est une regle d'architecture, pas une
preference : deux bots sur la meme cle partagent le meme quota, donc l'un peut rendre
l'autre muet, et une cle revoquee en abat deux au lieu d'un.

La regle etait ecrite dans API_KEYS_SETUP.md depuis toujours, et elle etait violee sans
que personne ne le voie : mesure du 2026-08-30, JohnnyBot et MalenaBot tournaient sur la
MEME cle Gemini. Une regle qu'aucun outil ne verifie n'est pas une regle, c'est un voeu.

    python tools/sonde_cles_partagees.py            # partage seul (hors ligne)
    python tools/sonde_cles_partagees.py --vitalite # + chaque cle repond-elle encore ?
    python tools/sonde_cles_partagees.py --strict   # code de sortie 1 si probleme

⚠️ Cette sonde n'affiche JAMAIS une cle : seulement une empreinte SHA-256 tronquee,
suffisante pour dire « c'est la meme » sans jamais dire laquelle.

Avec --vitalite, elle demande en plus a chaque fournisseur si la cle repond encore.
Une cle morte ne se voit pas : le bot bascule sur l'echelon suivant de la cascade et
personne ne remarque rien, jusqu'au jour ou l'on compte dessus. Mesure du 2026-08-30 :
ELEVENLABS (Alfred) et HF_TOKEN (Sheo) rendaient 401 depuis que les features voix/GPU
sont parquees.

⚠️ Le token Twitch du .env n'est qu'une AMORCE. `shared/twitch/auth.py` charge en
priorite `data/twitch_chat_auth_<bot>.json`, qui se rafraichit tout seul. Un 401 sur le
.env est donc normal et sans effet — c'est le fichier de data/ qui dit la verite. La
sonde teste les deux et le distingue, sinon elle crie au feu tous les jours.

Elle n'est pas dans la suite de tests a dessein : les cles ne sont pas dans le depot,
donc la CI ne peut pas la jouer. Elle se lance a la main, ou apres avoir touche a un
.env.
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]

# Tout ce qui identifie le bot aupres d'un tiers. Les cles Gemini sont numerotees :
# le code fait tourner GEMINI_KEY_1..4 pour repartir le quota.
CLES_SURVEILLEES = [
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "GEMINI_KEY_1", "GEMINI_KEY_2", "GEMINI_KEY_3", "GEMINI_KEY_4",
    "DISCORD_TOKEN",
]


def _lire_env_du_bot(dossier):
    """Rend {nom: valeur} pour UN bot, sans toucher a os.environ.

    `shared.secure_env.load_secure_env` ecrit dans l'environnement du processus : le
    charger pour six bots d'affilee ecraserait chaque bot par le suivant, et la sonde
    ne verrait plus que le dernier. On dechiffre donc a cote.
    """
    chemin = RACINE / dossier
    brut = None

    clair = chemin / ".env"
    if clair.exists():
        brut = clair.read_text(encoding="utf-8", errors="replace")
    else:
        chiffre = chemin / ".env.encrypted"
        maitre = chemin / ".master_key"
        if not (chiffre.exists() and maitre.exists()):
            return None
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            print("cryptography manquant : impossible de dechiffrer.")
            return None
        try:
            fernet = Fernet(maitre.read_bytes().strip())
            brut = fernet.decrypt(chiffre.read_bytes()).decode("utf-8")
        except Exception as e:
            print(f"  [!] {dossier} : dechiffrement impossible ({type(e).__name__})")
            return None

    valeurs = {}
    for ligne in brut.splitlines():
        ligne = ligne.strip()
        if "=" in ligne and not ligne.startswith("#"):
            nom, valeur = ligne.split("=", 1)
            valeurs[nom.strip()] = valeur.strip()
    return valeurs


def empreinte(valeur):
    return hashlib.sha256(valeur.encode("utf-8")).hexdigest()[:10]



# ---------------------------------------------------------------------------
# Vitalite : la cle repond-elle encore ? (--vitalite)
# ---------------------------------------------------------------------------
#
# Toutes les requetes sont en LECTURE SEULE : on demande « qui suis-je » ou « liste les
# modeles », jamais de generation, jamais d'ecriture.
#
# ⚠️ Pas de TWITCH_REFRESH_TOKEN ici. Twitch fait TOURNER le refresh token a l'usage :
# le tester le consommerait, et la valeur du .env deviendrait perimee — la sonde
# casserait ce qu'elle est censee verifier.

# En-tete navigateur obligatoire : Cloudflare renvoie « error code: 1010 » a l'agent par
# defaut d'urllib devant Groq. Un 403 sans corps JSON vient de la, pas de la cle.
_UA = "Mozilla/5.0"

# Dossier du bot -> identifiant utilise par shared/twitch/auth.py pour son fichier.
_ID_TWITCH = {"JohnnyBot": "johnny", "Sheogorath": "sheogorath", "SugarBot": "sugar"}


def _http(url, entetes=None, corps=None):
    en = {"User-Agent": _UA}
    en.update(entetes or {})
    t0 = time.time()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, data=corps, headers=en), timeout=25) as r:
            return r.status, r.read(), int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), int((time.time() - t0) * 1000)
    except Exception as e:
        return type(e).__name__, str(e).encode("utf-8", "replace"), int((time.time() - t0) * 1000)


def _sondes(valeurs):
    """Rend [(nom, url, entetes, corps)] pour les cles presentes chez ce bot."""
    v = valeurs.get
    liste = []
    if v("DISCORD_TOKEN"):
        liste.append(("DISCORD_TOKEN", "https://discord.com/api/v10/users/@me",
                      {"Authorization": "Bot " + v("DISCORD_TOKEN")}, None))
    for n in ("GEMINI_KEY_1", "GEMINI_KEY_2", "GEMINI_KEY_3", "GEMINI_KEY_4"):
        if v(n):
            liste.append((n, "https://generativelanguage.googleapis.com/v1beta/models?key="
                          + urllib.parse.quote(v(n)), {}, None))
    for n, url in (("MISTRAL_API_KEY", "https://api.mistral.ai/v1/models"),
                   ("GROQ_API_KEY", "https://api.groq.com/openai/v1/models"),
                   ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/key")):
        if v(n):
            liste.append((n, url, {"Authorization": "Bearer " + v(n)}, None))
    if v("ELEVENLABS_API_KEY"):
        liste.append(("ELEVENLABS_API_KEY", "https://api.elevenlabs.io/v1/user",
                      {"xi-api-key": v("ELEVENLABS_API_KEY")}, None))
    if v("HF_TOKEN"):
        liste.append(("HF_TOKEN", "https://huggingface.co/api/whoami-v2",
                      {"Authorization": "Bearer " + v("HF_TOKEN")}, None))
    if v("TWITCH_CLIENT_ID") and v("TWITCH_CLIENT_SECRET"):
        liste.append(("TWITCH_CLIENT_*", "https://id.twitch.tv/oauth2/token",
                      {"Content-Type": "application/x-www-form-urlencoded"},
                      urllib.parse.urlencode({
                          "client_id": v("TWITCH_CLIENT_ID"),
                          "client_secret": v("TWITCH_CLIENT_SECRET"),
                          "grant_type": "client_credentials"}).encode()))
    return liste


def _valider_twitch(jeton):
    return _http("https://id.twitch.tv/oauth2/validate",
                 {"Authorization": "OAuth " + (jeton or "").replace("oauth:", "")})


def token_twitch_vivant(bot):
    """Le token REELLEMENT utilise vit dans data/, pas dans le .env.

    Rend (etat, detail), etat parmi 'ok', 'mort', 'absent'. Sans cette distinction la
    sonde signalerait une panne Twitch tous les jours, alors que le rafraichissement
    automatique fait son travail : mesure du 2026-08-30, les trois .env rendaient 401
    pendant que les trois bots parlaient normalement sur le chat.
    """
    bot_id = _ID_TWITCH.get(bot)
    if not bot_id:
        return "absent", "ce bot ne va pas sur Twitch"
    chemin = RACINE / "data" / ("twitch_chat_auth_" + bot_id + ".json")
    if not chemin.exists():
        return "absent", chemin.name + " absent — le bot repartira de l'amorce du .env"
    try:
        jeton = json.loads(chemin.read_text(encoding="utf-8")).get("access_token")
    except Exception as e:
        return "mort", chemin.name + " illisible (" + type(e).__name__ + ")"
    code, corps, _ = _valider_twitch(jeton)
    if code == 200:
        d = json.loads(corps)
        return "ok", str(d.get("login")) + ", expire dans " + str(d.get("expires_in")) + " s"
    return "mort", chemin.name + " : " + str(code)


def _detail(nom, code, corps):
    if code != 200:
        return corps.decode("utf-8", "replace").replace("\n", " ")[:80]
    try:
        d = json.loads(corps)
    except Exception:
        return "ok"
    if nom == "DISCORD_TOKEN":
        return d.get("username", "ok")
    if nom.startswith("GEMINI"):
        return str(len(d.get("models", []))) + " modeles"
    return "ok"


def vitalite():
    """Interroge chaque fournisseur. Rend le nombre de cles mortes."""
    morts = 0
    print("\n=== Vitalite (lecture seule) ===")
    for bot in BOTS:
        valeurs = _lire_env_du_bot(bot)
        if valeurs is None:
            continue
        print("\n  " + bot)
        for nom, url, entetes, corps in _sondes(valeurs):
            code, rep, ms = _http(url, entetes, corps)
            vivant = code == 200
            morts += 0 if vivant else 1
            print("    {:22} {} {:>5} {:>6} ms  {}".format(
                nom, "OK  " if vivant else "MORT", str(code), ms, _detail(nom, code, rep)))

        if valeurs.get("TWITCH_OAUTH_TOKEN"):
            etat, detail = token_twitch_vivant(bot)
            if etat == "ok":
                print("    {:22} OK    live            {}".format("TWITCH (data/)", detail))
            else:
                morts += 1
                print("    {:22} MORT                  {}".format("TWITCH (data/)", detail))
            # L'amorce du .env : informatif seulement. Un 401 ici est SANS EFFET tant
            # que le fichier de data/ repond — mais il ne reste plus de secours.
            code, _, ms = _valider_twitch(valeurs["TWITCH_OAUTH_TOKEN"])
            if code != 200:
                print("    {:22} perimee {:>6} ms  sans effet aujourd'hui, mais plus "
                      "de secours si data/ est perdu".format("  .env (amorce)", ms))
    return morts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="code de sortie 1 si une cle est partagee ou morte")
    ap.add_argument("--vitalite", action="store_true",
                    help="interroge chaque fournisseur (lecture seule, ~25 appels)")
    args = ap.parse_args()

    par_cle = defaultdict(lambda: defaultdict(list))   # nom -> empreinte -> [bots]
    manquants = defaultdict(list)

    for bot in BOTS:
        valeurs = _lire_env_du_bot(bot)
        if valeurs is None:
            print(f"  [!] {bot} : aucun .env lisible — bot ignore")
            continue
        for nom in CLES_SURVEILLEES:
            valeur = valeurs.get(nom)
            if valeur:
                par_cle[nom][empreinte(valeur)].append(bot)
            elif nom in ("MISTRAL_API_KEY", "GROQ_API_KEY", "GEMINI_KEY_1", "DISCORD_TOKEN"):
                manquants[bot].append(nom)

    partages = []
    print("\n=== Empreintes par fournisseur (jamais la cle) ===")
    for nom in CLES_SURVEILLEES:
        if nom not in par_cle:
            continue
        print(f"\n  {nom}")
        for emp, bots in sorted(par_cle[nom].items(), key=lambda kv: -len(kv[1])):
            marque = "  <<< PARTAGEE" if len(bots) > 1 else ""
            print(f"    {emp}  {', '.join(bots)}{marque}")
            if len(bots) > 1:
                partages.append((nom, bots))

    if manquants:
        print("\n=== Cles attendues et absentes ===")
        for bot, noms in manquants.items():
            print(f"  {bot} : {', '.join(noms)}")

    morts = vitalite() if args.vitalite else 0

    print()
    if morts:
        print(str(morts) + " cle(s) ne repondent plus. Une cle morte ne se voit pas :")
        print("  la cascade bascule d'un echelon, et personne ne remarque rien.")
    if partages:
        print("VIOLATION DE LA REGLE : une cle par bot, pas de partage.")
        for nom, bots in partages:
            print(f"  {nom} est partagee par {' et '.join(bots)}"
                  f" -> quota commun, et une revocation en abat {len(bots)}.")
        print("\n  Correctif : creer une cle NEUVE chez le fournisseur pour tous les bots")
        print("  sauf un, puis la poser dans le .env du bot concerne. Aucun code a changer.")
        return 1 if args.strict else 0

    if not morts:
        print("OK : aucune cle partagee entre bots.")
    return 1 if (args.strict and morts) else 0


if __name__ == "__main__":
    sys.exit(main())
