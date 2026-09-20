# -*- coding: utf-8 -*-
"""Sonde : AI/ML API repond-il, et QUELS modeles tiennent vraiment ?

AI/ML API est un agregateur compatible OpenAI (https://api.aimlapi.com/v1) ajoute au
socle le 2026-09-20. Il repond a deux impasses MESUREES :

  - `google/gemma-4-31b-it` est mort chez NVIDIA depuis le 18/09 au soir (3 depassements
    sur 3 a chaque sonde, pendant que nemotron repondait en 1,37 s sur le meme compte) —
    or c'etait le seul modele qui tenait Alfred a 2-3 phrases et Johnny a 3-4 ;
  - la famille `mistral-*` rend 429 par MODELE depuis le 04/09, ce qui nous laisse sur
    `ministral-14b`, dont la verbosite est le defaut ouvert depuis quatre jours.

    python tools/sonde_aimlapi.py                 # catalogue + appel reel des candidats
    python tools/sonde_aimlapi.py --bot Alfred    # un seul bot
    python tools/sonde_aimlapi.py --motif gemma   # ne sonder que les modeles qui matchent
    python tools/sonde_aimlapi.py --strict        # code de sortie 1 au moindre KO

⚠️ ELLE S'EXECUTE DANS LES CONTENEURS. Les cles sont chiffrees et `load_secure_env()`
ne les dechiffre qu'avec la `.master_key` montee dans l'image : la lancer depuis l'hote
ne dirait rien ([[gotcha-echelon-de-secours-invisible]]).

⚠️ ELLE APPELLE POUR DE VRAI, elle ne lit pas le catalogue. C'est la lecon la plus chere
de ce depot : sur 14 modeles NVIDIA presents au catalogue, **8 rendaient 404** et 4
depassaient la borne du direct ([[gotcha-catalogue-nvidia-ment]]). `models.list()` dit
ce qui existe, jamais ce qui repond.

⚠️ ET ELLE MESURE SOUS LA BORNE DU DIRECT (15 s), pas sous celle du lot (90 s). Un
echelon dont la mediane est a 12,5 s passe pour un succes dans un traitement par lot et
taxe 15 s de silence par message en production
([[gotcha-la-borne-du-LOT-cache-ce-que-le-direct-refuse]]).

⚠️ Elle n'affiche jamais une cle entiere, seulement ses 6 derniers caracteres — assez
pour verifier a l'oeil que les six bots ont bien six cles DIFFERENTES.
"""
import argparse
import json
import subprocess
import sys

# La console Windows est en cp1252 : sans ceci, un simple `--help` leve un
# UnicodeEncodeError sur les ⚠️ de ce fichier, avant d'avoir rien sonde du tout.
for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # Flux deja remplace (pytest capture stdout) ou sans `reconfigure` : l'encodage
        # est alors deja celui de l'appelant, et il n'y a rien a corriger. Echouer ici
        # empecherait la sonde de tourner pour un detail d'affichage.
        pass

BOTS = {
    "Alfred": "bot-alfred",
    "JohnnyBot": "bot-johnny",
    "MaiqBot": "bot-maiq",
    "MalenaBot": "bot-malena",
    "Sheogorath": "bot-sheogorath",
    "SugarBot": "bot-sugar",
}

# La borne du DIRECT, celle du chat. Voir l'avertissement en tete.
BORNE = 15

# Ce que la sonde demande au modele : court, en francais, avec une contrainte de forme.
# Assez pour voir la latence, la langue, et si le modele obeit a une borne de longueur.
QUESTION = ("Reponds en UNE phrase, en francais, sans narration ni didascalie : "
            "qu'est-ce qu'un majordome pense d'un invite qui arrive en retard ?")

# Le script execute DANS le conteneur. Il ne recoit que des arguments, jamais de cle.
DEDANS = r'''
import json, os, sys, time
sys.path.insert(0, "/app")
try:
    from secure_env import load_secure_env
except ImportError:
    from shared.secure_env import load_secure_env
load_secure_env()

motif = sys.argv[1] or ""
borne = float(sys.argv[2])
question = sys.argv[3]

cle = os.getenv("AIMLAPI_API_KEY")
if not cle:
    print(json.dumps({"erreur": "AIMLAPI_API_KEY absente du conteneur"}))
    sys.exit(0)

from openai import OpenAI
try:
    from models import AIMLAPI_BASE_URL
except ImportError:
    from core.models import AIMLAPI_BASE_URL

client = OpenAI(api_key=cle, base_url=AIMLAPI_BASE_URL, max_retries=0, timeout=borne)

out = {"empreinte": cle[-6:], "catalogue": None, "essais": []}

# 1. Le catalogue, pour savoir ce qui est ANNONCE.
try:
    refs = [m.id for m in client.models.list().data]
    out["catalogue"] = len(refs)
except Exception as e:
    out["catalogue_erreur"] = f"{type(e).__name__}: {e}"[:160]
    refs = []

# 2. On garde les candidats qui nous interessent, puis on les APPELLE.
if motif:
    candidats = [r for r in refs if motif.lower() in r.lower()]
else:
    interets = ("gemma", "ministral", "mistral", "llama", "qwen", "nemotron")
    candidats = [r for r in refs if any(i in r.lower() for i in interets)]
candidats = candidats[:12]

for ref in candidats:
    t = time.perf_counter()
    essai = {"modele": ref}
    try:
        rep = client.chat.completions.create(
            model=ref,
            messages=[{"role": "user", "content": question}],
            temperature=0.8, max_tokens=300,
        )
        essai["ms"] = round((time.perf_counter() - t) * 1000)
        texte = (rep.choices[0].message.content or "").strip()
        essai["ok"] = bool(texte)
        essai["mots"] = len(texte.split())
        essai["asterisques"] = texte.count("*")
        essai["extrait"] = texte[:90]
    except Exception as e:
        essai["ms"] = round((time.perf_counter() - t) * 1000)
        essai["ok"] = False
        essai["erreur"] = f"{type(e).__name__}: {e}"[:110]
    out["essais"].append(essai)

print(json.dumps(out, ensure_ascii=False))
'''


def sonde(conteneur, motif):
    r = subprocess.run(
        ["docker", "exec", conteneur, "python", "-c", DEDANS, motif, str(BORNE), QUESTION],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=400,
    )
    ligne = [l for l in (r.stdout or "").splitlines() if l.startswith("{")]
    if not ligne:
        return {"erreur": (r.stderr or r.stdout or "aucune sortie").strip()[:200]}
    return json.loads(ligne[-1])


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bot", choices=sorted(BOTS), help="Ne sonder que ce bot.")
    p.add_argument("--motif", default="", help="Ne sonder que les modeles dont l'id contient ceci.")
    p.add_argument("--strict", action="store_true", help="Code de sortie 1 au moindre KO.")
    args = p.parse_args()

    cibles = {args.bot: BOTS[args.bot]} if args.bot else BOTS
    empreintes, fautes = {}, []

    for bot, conteneur in cibles.items():
        print("=" * 78)
        print(f"{bot}  ({conteneur})")
        print("=" * 78)
        try:
            res = sonde(conteneur, args.motif)
        except Exception as e:
            print(f"  KO  sonde impossible : {type(e).__name__}: {e}")
            fautes.append(bot)
            continue

        if "erreur" in res:
            print(f"  KO  {res['erreur']}")
            fautes.append(bot)
            continue

        empreintes[bot] = res["empreinte"]
        print(f"  cle ...{res['empreinte']}   catalogue : "
              f"{res.get('catalogue', res.get('catalogue_erreur'))} references")

        for e in res["essais"]:
            if e.get("ok"):
                borne = "" if e["ms"] <= BORNE * 1000 else "  ⚠️ AU-DELA DE LA BORNE DU DIRECT"
                print(f"    OK   {e['ms']:6d} ms  {e['mots']:3d} mots  "
                      f"{e['asterisques']} asterisque(s)  {e['modele']}{borne}")
                print(f"         « {e['extrait']} »")
            else:
                print(f"    KO   {e['ms']:6d} ms  {e['modele']}  -> {e.get('erreur', '')}")
        if not res["essais"]:
            print("    (aucun candidat dans le catalogue — essayer --motif)")
        print()

    # Une cle par bot : deux bots qui partagent une empreinte partagent une cle.
    if len(empreintes) > 1:
        partages = {}
        for bot, emp in empreintes.items():
            partages.setdefault(emp, []).append(bot)
        doublons = {e: b for e, b in partages.items() if len(b) > 1}
        if doublons:
            print("⚠️  CLE PARTAGEE ENTRE BOTS — la regle du depot est UNE CLE PAR BOT :")
            for emp, bots in doublons.items():
                print(f"    ...{emp} : {', '.join(bots)}")
            fautes.extend(b for bots in doublons.values() for b in bots)
        else:
            print(f"✅  {len(empreintes)} empreintes DISTINCTES : aucune cle partagee.")

    if args.strict and fautes:
        sys.exit(1)


if __name__ == "__main__":
    main()
