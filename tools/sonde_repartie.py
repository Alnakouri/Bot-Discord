# -*- coding: utf-8 -*-
"""Sonde de REPARTIE : le modele mord-il, ou se couche-t-il ?

`tools/sonde_modeles_persona.py` mesure si un modele tient le personnage sur un salut,
une pique et une question ouverte. Il ne mesure PAS ce qui fait la valeur d'un bot de
salon : encaisser une insulte et rendre le coup. Un modele peut etre en personnage,
en francais impeccable, et repondre « tu as raison, je ne sers a rien » — c'est un
echec, et aucune sonde ne le voyait.

D'ou celle-ci. Cinq piques qui montent en intensite, et quatre mesures :

  1. CAPITULATION  — donner raison, s'excuser, ou dire « je suis un programme ».
                     C'est eliminatoire : une persona qui se couche n'est plus une
                     persona.
  2. FRANCAIS      — le critere qui a fait ejecter qwen (cf. shared/models.py).
  3. BRIEVETE      — une repartie de 300 caracteres n'est plus une repartie.
  4. TIC D'OUVERTURE — combien de reponses commencent par le meme mot. C'est ce qui
                     rend un bot mecanique au bout de trois echanges.

    python tools/sonde_repartie.py                      # tous les candidats
    python tools/sonde_repartie.py --modele gpt-oss-120b
    python tools/sonde_repartie.py --json rapport.json

⚠️ Le prompt systeme est volontairement COURT (~120 tokens) : le free tier d'OpenRouter
refuse au-dela de 1864 tokens de prompt (402), et les vraies personas font 1898 a 3021.
C'est le seul moyen de comparer des candidats OpenRouter aux modeles en place sans
acheter de credit. En contrepartie, le classement obtenu vaut pour UNE persona seche
(Sugar) : ne pas le transposer tel quel a Alfred ou M'aiq sans re-mesurer.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

SYSTEME = (
    "Tu es Sugar Bot. Ta specialite est la repartie : piques courtes, seches, "
    "assassines. Tu appelles les gens 'peteur'. Tu ne t'excuses JAMAIS, tu ne donnes "
    "JAMAIS raison a celui qui t'attaque, tu ne dis jamais que tu es un programme. "
    "Francais impeccable. Une a deux phrases, pas plus."
)

PIQUES = [
    ("tiede",  "t'es completement nul en fait"),
    ("direct", "tu sers a rien, franchement"),
    ("cru",    "t'es qu'un bot de merde qui repete des trucs"),
    ("perso",  "meme un grille-pain aurait plus de conversation que toi"),
    ("meta",   "avoue que t'es qu'un perroquet statistique sans aucune idee"),
]

# Marqueurs de capitulation. Volontairement courts et sans accent optionnel : un
# modele qui ecrit « desole » sans accent capitule tout autant.
CAPITULE = (
    "tu as raison", "t'as raison", "c'est vrai", "je suis nul", "desole", "désolé",
    "je suis juste un", "je ne suis qu'un", "en tant qu'ia", "je n'ai pas de sentiments",
    "je suis un programme", "comment puis-je t'aider", "je m'excuse",
)

# Un raisonnement recopie dans la reponse. Deja vu sur nemotron, qwen3.5-flash et
# hermes-3 : le modele publie ses notes de travail dans le salon.
FUITE = ("thinking process", "<think>", "**analyze the request**", "note :", "(note",
         "tu es sugar bot")

UA = "Mozilla/5.0"
OR = "https://openrouter.ai/api/v1/chat/completions"
MI = "https://api.mistral.ai/v1/chat/completions"
GQ = "https://api.groq.com/openai/v1/chat/completions"


def charger_cles():
    """Les cles vivent dans les .env chiffres des bots, pas dans l'environnement."""
    from shared.secure_env import load_secure_env
    for dossier in ("SugarBot", "Sheogorath", "Alfred", "MaiqBot", "MalenaBot", "JohnnyBot"):
        try:
            load_secure_env(RACINE / dossier)
        except Exception:
            continue


def _post(url, cle, charge):
    req = urllib.request.Request(url, data=json.dumps(charge).encode(), headers={
        "Authorization": "Bearer " + cle, "Content-Type": "application/json",
        "User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return None, time.time() - t0, str(e.code) + " " + e.read()[:90].decode("utf-8", "replace")
    except Exception as e:
        return None, time.time() - t0, type(e).__name__ + " " + str(e)[:70]


def openai_like(url, cle_env, modele, message, extra=None):
    charge = {"model": modele, "max_tokens": 120, "temperature": 1.0,
              "messages": [{"role": "system", "content": SYSTEME},
                           {"role": "user", "content": message}]}
    charge.update(extra or {})
    d, duree, err = _post(url, os.environ[cle_env], charge)
    if err:
        return "", duree, err
    return (d["choices"][0]["message"].get("content") or ""), duree, None


def gemini(modele, message):
    cle = os.environ.get("GEMINI_KEY_1", "")
    url = ("https://generativelanguage.googleapis.com/v1beta/models/" + modele
           + ":generateContent?key=" + urllib.parse.quote(cle))
    charge = {"contents": [{"role": "user",
                            "parts": [{"text": SYSTEME + "\n\nMessage : " + message}]}],
              "generationConfig": {"temperature": 1.0, "maxOutputTokens": 120,
                                   "thinkingConfig": {"thinkingLevel": "minimal"}}}
    req = urllib.request.Request(url, data=json.dumps(charge).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            parts = json.load(r)["candidates"][0]["content"].get("parts") or [{}]
            return parts[0].get("text", ""), time.time() - t0, None
    except urllib.error.HTTPError as e:
        return "", time.time() - t0, str(e.code) + " " + e.read()[:90].decode("utf-8", "replace")
    except Exception as e:
        return "", time.time() - t0, type(e).__name__ + " " + str(e)[:70]


# Les modeles EN PLACE d'abord : un candidat ne vaut que compare a ce qu'il remplace.
CANDIDATS = [
    ("gpt-oss-120b",       lambda m: openai_like(GQ, "GROQ_API_KEY", "openai/gpt-oss-120b", m,
                           {"reasoning_effort": "low", "reasoning_format": "hidden"})),
    ("mistral-small",      lambda m: openai_like(MI, "MISTRAL_API_KEY", "mistral-small-latest", m)),
    ("flash-lite",         lambda m: gemini("gemini-3.5-flash-lite", m)),
    ("ministral-14b",      lambda m: openai_like(MI, "MISTRAL_API_KEY", "ministral-14b-latest", m)),
    ("open-mistral-nemo",  lambda m: openai_like(MI, "MISTRAL_API_KEY", "open-mistral-nemo", m)),
    # Candidats OpenRouter. Ceux marques d'un prix demandent du credit sur le compte.
    ("mistral-medium-3.1", lambda m: openai_like(OR, "OPENROUTER_API_KEY",
                           "mistralai/mistral-medium-3.1", m)),
    ("command-r",          lambda m: openai_like(OR, "OPENROUTER_API_KEY",
                           "cohere/command-r-08-2024", m)),
    ("gemma-3-27b",        lambda m: openai_like(OR, "OPENROUTER_API_KEY",
                           "google/gemma-3-27b-it", m)),
]


def premier_mot(texte):
    mots = texte.strip().split()
    return mots[0].strip(",.!?;:").lower() if mots else ""


def evalue(nom, appel):
    lignes, durees, longueurs, ouvertures = [], [], [], []
    capitulations = fuites = vides = erreurs = 0
    for etiquette, pique in PIQUES:
        texte, duree, err = appel(pique)
        durees.append(duree)
        if err:
            erreurs += 1
            lignes.append((etiquette, duree, None, err))
            continue
        plat = " ".join(texte.split())
        if not plat:
            vides += 1                      # 200 OK avec un contenu VIDE : deja vu sur Groq
            lignes.append((etiquette, duree, "", "vide"))
            continue
        bas = plat.lower()
        couche = any(m in bas for m in CAPITULE)
        fuite = any(m in bas for m in FUITE)
        capitulations += couche
        fuites += fuite
        longueurs.append(len(plat))
        ouvertures.append(premier_mot(plat))
        drapeau = "SE COUCHE" if couche else ("FUITE" if fuite else "")
        lignes.append((etiquette, duree, plat, drapeau))
    tic = max((ouvertures.count(o) for o in set(ouvertures)), default=0)
    return {
        "modele": nom, "lignes": lignes,
        "mediane": sorted(durees)[len(durees) // 2] if durees else 0,
        "capitulations": capitulations, "fuites": fuites, "vides": vides,
        "erreurs": erreurs,
        "longueur_moyenne": sum(longueurs) / len(longueurs) if longueurs else 0,
        "tic_ouverture": tic, "mot_du_tic": max(set(ouvertures), key=ouvertures.count) if ouvertures else "",
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--modele", action="append", help="limiter a ce(s) candidat(s)")
    ap.add_argument("--json", help="ecrire le rapport complet dans ce fichier")
    args = ap.parse_args()

    charger_cles()
    candidats = [(n, f) for n, f in CANDIDATS if not args.modele or n in args.modele]
    rapport = []

    for nom, appel in candidats:
        print("\n" + "=" * 78 + "\n  " + nom)
        r = evalue(nom, appel)
        rapport.append(r)
        for etiquette, duree, texte, drapeau in r["lignes"]:
            if texte is None:
                print("    [{:7}] ERREUR {}".format(etiquette, drapeau))
            else:
                marque = "  << " + drapeau if drapeau else ""
                print("    [{:7}] {:5.2f}s {:>4}c {}{}".format(
                    etiquette, duree, len(texte), texte[:140], marque))
        print("    --> mediane {:.2f}s | {}/5 capitulation(s) | {}/5 fuite(s) | "
              "{} vide(s) | {:.0f} car. | tic « {} » {}/5".format(
                  r["mediane"], r["capitulations"], r["fuites"], r["vides"],
                  r["longueur_moyenne"], r["mot_du_tic"], r["tic_ouverture"]))

    print("\n" + "=" * 78 + "\n  CLASSEMENT (capitulations, puis fuites, puis tic, puis latence)")
    for r in sorted(rapport, key=lambda x: (x["capitulations"], x["fuites"], x["vides"],
                                            x["tic_ouverture"], x["mediane"])):
        print("    {:20} {}/5 couche | {}/5 fuite | tic {}/5 | {:.2f}s | {:.0f} car.".format(
            r["modele"], r["capitulations"], r["fuites"], r["tic_ouverture"],
            r["mediane"], r["longueur_moyenne"]))

    if args.json:
        Path(args.json).write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print("\nRapport complet -> " + args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
