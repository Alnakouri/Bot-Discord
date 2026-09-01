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
priorite `data/twitch_chat_auth_<bot>.json`, qui se rafraichit tout seul. Le token
d'ACCES du .env est fait pour expirer toutes les ~4 h : le trouver perime est NORMAL et
ne dit rien. La sonde ne le teste donc pas. Elle teste le fichier de data/ (la verite du
moment) et, pour le secours, COMPARE le refresh token des deux cotes — c'est lui, et lui
seul, qui permet de repartir si data/ est perdu.

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

    Rend (etat, detail), etat parmi 'ok', 'perime', 'mort', 'absent'.

    ⚠️ 'perime' n'est PAS une panne. Un token d'acces Twitch dure ~4 h ; quand les
    conteneurs sont a l'arret (Docker Desktop eteint, par exemple), plus personne ne
    le rafraichit et il expire. `shared/twitch/auth.py::get_valid_token` le rafraichit
    de lui-meme au demarrage suivant. Compter ca comme une cle morte, c'est annoncer
    trois pannes Twitch chaque matin — mesure du 2026-09-01, les trois fichiers
    rendaient 401 pour cette seule raison.

    Un 401 alors que `expires_at` n'est PAS encore atteint, la oui : le token a ete
    revoque cote Twitch. C'est cette distinction qui fait la difference entre une
    alarme utile et une alarme qu'on apprend a ignorer.
    """
    bot_id = _ID_TWITCH.get(bot)
    if not bot_id:
        return "absent", "ce bot ne va pas sur Twitch"
    chemin = RACINE / "data" / ("twitch_chat_auth_" + bot_id + ".json")
    if not chemin.exists():
        return "absent", chemin.name + " absent — le bot repartira de l'amorce du .env"
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except Exception as e:
        return "mort", chemin.name + " illisible (" + type(e).__name__ + ")"
    code, corps, _ = _valider_twitch(donnees.get("access_token"))
    if code == 200:
        d = json.loads(corps)
        return "ok", str(d.get("login")) + ", expire dans " + str(d.get("expires_in")) + " s"

    echeance = donnees.get("expires_at") or 0
    depuis = int(time.time() - echeance)
    if echeance and depuis > 0:
        if donnees.get("refresh_token"):
            return "perime", ("expire depuis " + _duree(depuis) + " (bots a l'arret ?) "
                              "— rafraichi tout seul au prochain demarrage")
        return "mort", ("expire depuis " + _duree(depuis) + " et AUCUN refresh token : "
                        "rejouer twitch_authorize.py")
    return "mort", (chemin.name + " : " + str(code) + " alors que le token n'a pas "
                    "encore expire — revoque cote Twitch ?")


def _duree(secondes):
    if secondes < 3600:
        return str(secondes // 60) + " min"
    if secondes < 86400:
        return str(secondes // 3600) + " h"
    return str(secondes // 86400) + " j"


def amorce_env_reutilisable(bot, valeurs):
    """L'amorce du `.env` pourrait-elle relancer le bot si `data/` etait perdu ?

    Rend (etat, detail), etat parmi 'ok', 'perimee', 'absente', 'sans objet'.

    ⚠️ Ce qui relance un bot n'est PAS le token d'ACCES du `.env`. Celui-la est fait
    pour expirer toutes les ~4 h : le trouver perime est NORMAL et ne dit rien de
    l'etat du secours. C'est le REFRESH token qui redonne un acces. La bonne question
    est donc : le refresh du `.env` est-il encore celui que `data/` utilise ?

    Twitch fait TOURNER le refresh token a l'usage : on ne le teste jamais en ligne
    (cf. `test_aucune_sonde_ne_consomme_le_refresh_token_twitch`), on le COMPARE par
    empreinte. Mesure du 2026-08-31 : les trois bots Twitch ont le meme refresh des
    deux cotes — le secours est intact, et la version precedente de cette sonde
    annoncait le contraire tous les jours.
    """
    bot_id = _ID_TWITCH.get(bot)
    if not bot_id:
        return "sans objet", "ce bot ne va pas sur Twitch"
    amorce = (valeurs or {}).get("TWITCH_REFRESH_TOKEN")
    if not amorce:
        return "absente", ("aucun TWITCH_REFRESH_TOKEN dans le .env — si data/ est "
                          "perdu, il faudra rejouer twitch_authorize.py")
    chemin = RACINE / "data" / ("twitch_chat_auth_" + bot_id + ".json")
    if not chemin.exists():
        return "ok", "le .env porte un refresh token, et data/ n'existe pas encore"
    try:
        vivant = json.loads(chemin.read_text(encoding="utf-8")).get("refresh_token")
    except Exception as e:
        return "absente", chemin.name + " illisible (" + type(e).__name__ + ")"
    if not vivant:
        return "ok", "seul le .env porte un refresh token"
    if empreinte(vivant) == empreinte(amorce):
        return "ok", "refresh identique des deux cotes (" + empreinte(amorce) + ")"
    return "perimee", ("le refresh a tourne : data/ " + empreinte(vivant) + " != .env "
                       + empreinte(amorce) + " — recopier celui de data/ dans le .env")


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
            # Seul 'mort' compte : 'perime' est le fonctionnement normal d'un token de
            # 4 h que le bot rafraichira lui-meme (cf. token_twitch_vivant).
            morts += 1 if etat == "mort" else 0
            print("    {:22} {:9} {:11} {}".format(
                "TWITCH (data/)",
                {"ok": "OK  ", "perime": "perime", "mort": "MORT", "absent": "-"}[etat],
                "live" if etat == "ok" else "", detail))
            # Le secours, c'est le REFRESH token du .env, pas son token d'acces.
            # On ne teste donc PAS TWITCH_OAUTH_TOKEN : perime toutes les ~4 h, il
            # ferait crier au feu pour un fonctionnement nominal.
            etat_a, detail_a = amorce_env_reutilisable(bot, valeurs)
            marque = {"ok": "OK  ", "perimee": "A REFAIRE", "absente": "ABSENTE"}
            if etat_a != "sans objet":
                print("    {:22} {:9} secours      {}".format(
                    "  .env (amorce)", marque[etat_a], detail_a))
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
