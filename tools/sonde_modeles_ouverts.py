# -*- coding: utf-8 -*-
"""Sonde : quels modeles OUVERTS, sur nos free tiers, tiennent la borne du DIRECT ?

Elle appelle des candidats a poids ouverts avec les VRAIES fiches de persona, sur les
cles que les bots ont deja (Gemini, Groq, Mistral, NVIDIA). Aucun nouveau fournisseur,
aucune depense.

    docker exec bot-alfred python /app/bot/../tools/sonde_modeles_ouverts.py   # non
    python tools/sonde_modeles_ouverts.py --bot alfred      # depuis l'hote : lance dans le conteneur

⚠️ ELLE APPELLE, ELLE NE LIT PAS LE CATALOGUE. Sur 14 modeles NVIDIA annonces, 8
rendaient 404 et 4 depassaient la borne du direct ([[gotcha-catalogue-nvidia-ment]]).

⚠️ ELLE BORNE A 15 s, LA BORNE DU CHAT — pas les 90 s du lot. gemma-4 a ete « valide »
le 18/09 sous 90 s alors que 26 de ses 67 appels reussis depassaient 15 s : il n'a
jamais ete utilisable en direct ([[gotcha-la-borne-du-LOT-cache-ce-que-le-direct-refuse]]).

⚠️ ELLE MESURE CE QUI NOUS COUTE : latence, nombre de PHRASES, nombre de MOTS, et
asterisques. La longueur est le defaut ouvert depuis le 16/09, et les asterisques sont
un defaut de MODELE (ministral 77 %, flash-lite 0 %).

⚠️ Elle tourne DANS les conteneurs : les cles n'existent qu'apres dechiffrement par la
`.master_key` montee dans l'image.
"""
import argparse
import json
import statistics as st
import subprocess
import sys

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # Flux deja remplace ou sans `reconfigure` : l'encodage est celui de l'appelant,
        # il n'y a rien a corriger et echouer ici empecherait la sonde de tourner.
        pass

BOTS = {"alfred": "bot-alfred", "johnny": "bot-johnny", "maiq": "bot-maiq",
        "malena": "bot-malena", "sheogorath": "bot-sheogorath", "sugar": "bot-sugar"}

# La borne du DIRECT. Voir l'avertissement en tete.
BORNE = 15

DEDANS = r'''
import json, os, re, sys, time
from pathlib import Path
sys.path.insert(0, "/app/bot")
from core.secure_env import load_secure_env
load_secure_env(Path("/app/bot"))

bot = sys.argv[1]
borne = float(sys.argv[2])

# La VRAIE fiche du bot, chargee depuis SON module — le conteneur ne monte pas
# `tests/`, et dupliquer la table de `persona_loader` la ferait diverger en silence.
# On reprend donc la seule convention que les deux partagent : <bot>_data.PERSONALITY_PROMPT.
import importlib
FICHES = {"alfred": ("alfred_data", "PERSONALITY_PROMPT"),
          "johnny": ("johnny_data", "PERSONALITY_PROMPT"),
          "maiq": ("maiq_data", "PERSONALITY_PROMPT"),
          "malena": ("malena_data", "PERSONALITY_PROMPT"),
          "sugar": ("sugar_data", "PERSONALITY_PROMPT"),
          "sheogorath": ("sheo_data", "MOOD_PROMPTS")}
mod, attr = FICHES[bot]
fiche = getattr(importlib.import_module(mod), attr)
if isinstance(fiche, dict):
    fiche = fiche.get("neutral", "")

MESSAGES = ["Tu ferais quoi un dimanche pluvieux ?",
            "Franchement ce serveur part en vrille, non ?",
            "Donne-moi ton meilleur conseil."]

def mesure(appel):
    lat, phr, mots, ast, exemple, err = [], [], [], 0, "", None
    for m in MESSAGES:
        t = time.perf_counter()
        try:
            txt = appel(fiche, m) or ""
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:120]
            lat.append((time.perf_counter() - t) * 1000)
            continue
        lat.append((time.perf_counter() - t) * 1000)
        txt = txt.strip()
        if not txt:
            err = err or "reponse VIDE"
            continue
        phr.append(len([p for p in re.split(r"(?<=[.!?…])\s+", txt) if p.strip()]))
        mots.append(len(txt.split()))
        ast += txt.count("*")
        exemple = exemple or txt[:100]
    return {"lat": lat, "phr": phr, "mots": mots, "ast": ast, "exemple": exemple, "err": err}

resultats = []

# ── Gemini : les Gemma servis par l'API Google, avec la cle du bot ────────────
try:
    from google import genai
    from google.genai import types
    cle = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY_1")
    if cle:
        cli = genai.Client(api_key=cle)
        dispo = [m.name.replace("models/", "") for m in cli.models.list()]
        for ref in [d for d in dispo if "gemma" in d.lower()]:
            def appel(f, m, ref=ref, cli=cli):
                r = cli.models.generate_content(
                    model=ref, contents=f + "\n\nMessage : " + m,
                    config=types.GenerateContentConfig(temperature=0.8,
                                                       max_output_tokens=300))
                return r.text
            resultats.append(("gemini/" + ref, mesure(appel)))
except Exception as e:
    resultats.append(("gemini/(catalogue)", {"err": f"{type(e).__name__}: {e}"[:120],
                                             "lat": [], "phr": [], "mots": [], "ast": 0,
                                             "exemple": ""}))

# ── Groq et NVIDIA : point d'entree compatible OpenAI ─────────────────────────
from openai import OpenAI
from core.models import NVIDIA_BASE_URL, groq_kwargs, nvidia_kwargs

OUVERTS = ("gemma", "llama", "qwen", "deepseek", "kimi", "gpt-oss", "granite",
           "mixtral", "mistral-7b", "nemo", "phi", "glm", "olmo")
# Ce qui n'est pas un modele de CONVERSATION : inutile de depenser un appel.
HORS_SUJET = ("guard", "code", "embed", "ocr", "vision", "diffusion", "rerank",
              "moderation", "safeguard", "recurrent", "fim", "2b", "-3b")

def catalogue_ouvert(client):
    refs = [m.id for m in client.models.list().data]
    return [r for r in refs
            if any(o in r.lower() for o in OUVERTS)
            and not any(h in r.lower() for h in HORS_SUJET)]

for nom, cle_env, base, kw in (
        ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", groq_kwargs),
        ("nvidia", "NVIDIA_API_KEY", NVIDIA_BASE_URL, nvidia_kwargs)):
    cle = os.getenv(cle_env)
    if not cle:
        continue
    cli = OpenAI(api_key=cle, base_url=base, max_retries=0, timeout=borne)
    try:
        refs = catalogue_ouvert(cli)
    except Exception as e:
        resultats.append((nom + "/(catalogue)", {"err": f"{type(e).__name__}: {e}"[:120],
                                                 "lat": [], "phr": [], "mots": [],
                                                 "ast": 0, "exemple": ""}))
        continue
    for ref in refs[:10]:
        def appel(f, m, ref=ref, cli=cli, kw=kw):
            r = cli.chat.completions.create(
                model=ref,
                messages=[{"role": "system", "content": f},
                          {"role": "user", "content": m}],
                temperature=0.8, max_tokens=300, **(kw(ref) or {}))
            return r.choices[0].message.content
        resultats.append((nom + "/" + ref, mesure(appel)))

print(json.dumps({"bot": bot, "resultats": resultats}, ensure_ascii=False))
'''


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bot", default="alfred", choices=sorted(BOTS))
    args = p.parse_args()

    r = subprocess.run(
        ["docker", "exec", BOTS[args.bot], "python", "-c", DEDANS, args.bot, str(BORNE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    lignes = [l for l in (r.stdout or "").splitlines() if l.startswith("{")]
    if not lignes:
        print("KO :", (r.stderr or r.stdout or "aucune sortie")[-600:])
        return

    data = json.loads(lignes[-1])
    print(f"=== {data['bot']} — borne du DIRECT {BORNE} s, vraie fiche, 3 messages ===\n")
    print(f"{'modele':46s} {'med':>7s} {'max':>7s} {'phr':>4s} {'mots':>5s} {'*':>3s}")
    print("-" * 80)
    tenus = []
    for ref, m in data["resultats"]:
        lat = sorted(m["lat"])
        if not m["phr"]:
            print(f"{ref[:46]:46s} {'—':>7s} {'—':>7s}   KO  {m.get('err', '')[:28]}")
            continue
        med = lat[len(lat) // 2] / 1000
        mx = lat[-1] / 1000
        marque = "" if mx <= BORNE else "  ⚠️ hors borne"
        print(f"{ref[:46]:46s} {med:6.2f}s {mx:6.2f}s {st.median(m['phr']):4.0f} "
              f"{st.median(m['mots']):5.0f} {m['ast']:3d}{marque}")
        if mx <= BORNE:
            tenus.append((ref, med, st.median(m["phr"]), st.median(m["mots"]), m["ast"],
                          m["exemple"]))

    print(f"\n{len(tenus)} modele(s) tiennent la borne du direct sur les 3 messages :\n")
    for ref, med, phr, mots, ast, ex in sorted(tenus, key=lambda x: x[1]):
        print(f"  {ref}  ({med:.2f}s, {phr:.0f} phr / {mots:.0f} mots, {ast} astérisque(s))")
        print(f"      « {ex} »")


if __name__ == "__main__":
    main()
