# -*- coding: utf-8 -*-
"""Sonde : quel modele recite son raisonnement, et quel parametre l'en empeche ?

Un modele a raisonnement peut recopier sa pensee dans `content` au lieu de la garder a
part. Ca s'est deja vu en production : Malena a recite son raisonnement en plein Discord
(cf. gotcha-modeles-raisonnement-groq-openrouter). Le prompt n'y peut RIEN — mesure du
2026-09-04 : Sheogorath interdit les asterisques en tete de son prompt et en produit 9/9.

Ce qui marche, c'est le parametre du fournisseur. Mais il ne porte pas le meme nom
partout, et un parametre qui marche chez l'un ne marche pas chez l'autre :

    Groq     reasoning_effort="low" + reasoning_format="hidden"
    NVIDIA   reasoning_effort="none"
    Gemini   thinking_level="minimal"
    OpenRouter  `reasoning:{exclude:true}` -> ne corrige RIEN (mesure 2026-08-30)

Cette sonde envoie le VRAI prompt d'une persona, avec et sans le parametre, et compare.

    python tools/sonde_fuite_raisonnement.py
    python tools/sonde_fuite_raisonnement.py --fournisseur nvidia
    python tools/sonde_fuite_raisonnement.py --json rapport.json

⚠️ Elle fait de VRAIS appels et consomme du quota. Un bot par fournisseur suffit.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# Marqueurs de meta-discours : le modele PARLE DE la conversation au lieu d'y participer.
# ⚠️ Un detecteur naif sur « thinking process » rate tout : la fuite sort aussi en
# francais (« L'utilisateur me donne un transcript... »). Mesure du 2026-09-04 : trois
# variantes ont ete classees « propres » a tort avec un detecteur anglophone.
MARQUEURS_FUITE = [
    r"\bl'utilisateur\b", r"\bthe user\b", r"\bl'usager\b",
    r"\bje dois r[ée]pondre\b", r"\bi need to respond\b", r"\bi should respond\b",
    r"\bthinking process\b", r"\blet me think\b", r"\bfirst,? i\b",
    r"\bsystem prompt\b", r"\ble prompt\b", r"\brappel des consignes\b",
    r"\ben tant que .{0,30}, je dois\b", r"\bmon r[ôo]le est de\b",
    r"\bd'apr[èe]s le transcript\b", r"\bthe assistant\b",
    r"^<think>", r"\bokay,? so\b",
]
_FUITE = re.compile("|".join(MARQUEURS_FUITE), re.I | re.M)


def fuite(texte):
    """Rend le marqueur trouve, ou None. On rend le MOTIF pour pouvoir le verifier a l'oeil."""
    if not texte:
        return None
    m = _FUITE.search(texte)
    return m.group(0) if m else None


def charger_persona(bot_dossier, module, attribut):
    sys.path.insert(0, str(RACINE / bot_dossier))
    try:
        mod = __import__(module)
        return getattr(mod, attribut)
    finally:
        sys.path.pop(0)
        sys.modules.pop(module, None)


def cle(bot, nom):
    from shared.secure_env import load_secure_env
    os.environ.pop(nom, None)
    load_secure_env(RACINE / bot)
    return os.getenv(nom)


MESSAGE = ("TRANSCRIPT:\nledev: t'es qu'un tas de ferraille\n"
           "LAST MSG: t'es qu'un tas de ferraille")

# (fournisseur, bot dont on emprunte la cle, modele, variantes {nom: kwargs})
BANCS = {
    "groq": {
        "bot": "JohnnyBot", "var": "GROQ_API_KEY",
        "modeles": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"],
        "variantes": {
            # ⚠️ `reasoning_format` n'est pas un parametre du client OpenAI : il faut
            # passer par `extra_body`, sinon l'appel leve avant meme de partir.
            "sans rien": {},
            "effort=low": {"extra_body": {"reasoning_effort": "low"}},
            "low + format=hidden (production)": {
                "extra_body": {"reasoning_effort": "low", "reasoning_format": "hidden"}},
        },
    },
    "nvidia": {
        "bot": "JohnnyBot", "var": "NVIDIA_API_KEY",
        "modeles": ["nvidia/nemotron-3.5-lightning-30b-a3b",
                    "nvidia/nemotron-3-super-120b-a12b",
                    "nvidia/nemotron-nano-3-30b-a3b",
                    "mistralai/mistral-nemotron"],
        "variantes": {
            "sans rien": {},
            "effort=none": {"extra_body": {"reasoning_effort": "none"}},
            "thinking=False": {"extra_body": {"chat_template_kwargs": {"thinking": False}}},
        },
    },
}


def appeler(base_url, api_key, modele, systeme, kwargs):
    from openai import OpenAI
    cl = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
    depart = time.perf_counter()
    r = cl.chat.completions.create(
        model=modele,
        messages=[{"role": "system", "content": systeme},
                  {"role": "user", "content": MESSAGE}],
        max_tokens=250, temperature=0.9, **kwargs)
    ms = int((time.perf_counter() - depart) * 1000)
    msg = r.choices[0].message
    return (msg.content or ""), ms, bool(getattr(msg, "reasoning_content", None))


URLS = {"groq": "https://api.groq.com/openai/v1",
        "nvidia": "https://integrate.api.nvidia.com/v1"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fournisseur", action="append", choices=sorted(BANCS))
    ap.add_argument("--json", help="ecrire le rapport complet dans ce fichier")
    args = ap.parse_args()
    fournisseurs = args.fournisseur or sorted(BANCS)

    persona = charger_persona("JohnnyBot", "johnny_data", "PERSONALITY_PROMPT")
    rapport = []

    for f in fournisseurs:
        banc = BANCS[f]
        api_key = cle(banc["bot"], banc["var"])
        if not api_key:
            print(f"\n=== {f.upper()} : {banc['var']} absente, banc saute")
            continue
        print(f"\n{'=' * 78}\n{f.upper()}")
        for modele in banc["modeles"]:
            print(f"\n  {modele}")
            for nom, kw in banc["variantes"].items():
                try:
                    texte, ms, champ = appeler(URLS[f], api_key, modele, persona, kw)
                    marqueur = fuite(texte)
                    etat = f"FUITE ({marqueur!r})" if marqueur else "propre"
                    print(f"    {nom:<34} {ms:>6} ms  {etat}")
                    if marqueur:
                        print(f"        -> {texte[:110].strip()!r}")
                    rapport.append({"fournisseur": f, "modele": modele, "variante": nom,
                                    "ms": ms, "fuite": marqueur, "champ_reasoning": champ,
                                    "texte": texte})
                except Exception as e:
                    court = str(e)
                    code = ("404" if "404" in court else "429" if "429" in court
                            else "400" if "400" in court else court[:60])
                    print(f"    {nom:<34} {'':>6}     ECHEC {code}")
                    rapport.append({"fournisseur": f, "modele": modele, "variante": nom,
                                    "erreur": code})
                time.sleep(1.2)

    if args.json:
        Path(args.json).write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"\nRapport : {args.json}")

    # ⚠️ Prouver que la sonde a trouve sa matiere : sans cette borne, une sonde qui
    # n'appelle plus rien sortirait « aucune fuite » et rassurerait a tort.
    reussis = [r for r in rapport if "erreur" not in r]
    if not reussis:
        print("\nAUCUN appel n'a abouti : la sonde n'a rien mesure.")
        return 1
    fuites = [r for r in reussis if r["fuite"]]
    print(f"\n{len(reussis)} appels aboutis, {len(fuites)} avec fuite de raisonnement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
