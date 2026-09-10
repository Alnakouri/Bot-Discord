# -*- coding: utf-8 -*-
import os
import sys
import time
import argparse
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from Sheogorath.sheo_data import MOOD_PROMPTS
from shared.models import CASCADES_PERSONA, groq_kwargs
from tools.sonde_repartie import openai_like, GQ, MI

# ⚠️ `openai_like` de sonde_repartie plafonne a max_tokens=120. gpt-oss-120b, le
# PREMIER echelon de Sheo, est un modele a RAISONNEMENT : avec un budget aussi court il
# le depense en pensee et rend un `content` VIDE — la sonde affichait « Echec : None »
# et retombait sur le repli 14B a chaque appel, donc elle mesurait le mauvais modele.
# On aligne sur le plafond du vrai bot (max_tokens_val = 340 dans bot_sheogorath.py).
# Voir [[gotcha-modeles-raisonnement-groq-openrouter]] et [[bug-cascade-reponse-vide]].
def CHARGE(prompt, msg, modele=None, groq=False):
    charge = {"max_tokens": 340,
              "messages": [{"role": "system", "content": prompt},
                           {"role": "user", "content": msg}]}
    # ⚠️ ET SURTOUT CECI. Sans `reasoning_effort`/`reasoning_format`, gpt-oss-120b
    # depense tout son budget en pensee sur un prompt de persona de 13 000 caracteres
    # et rend un `content` VIDE : la sonde affichait « Echec : None » et retombait sur
    # le repli 14B a chaque appel. Le vrai bot, lui, passe groq_kwargs() — une sonde
    # qui ne reproduit pas les parametres du fournisseur ne mesure pas le vrai bot.
    # Voir [[gotcha-fuite-raisonnement-parametre-par-fournisseur]].
    if groq:
        charge.update(groq_kwargs(modele))
    return charge


MESSAGES = [
    "jyggalag te passe le bonjour",
    "la marche grise approche",
    "c'est vrai que tu étais Jyggalag ?",
    "t'as vu le fromage ?",
]

def load_keys():
    from shared.secure_env import load_secure_env
    try:
        load_secure_env(RACINE / "Sheogorath")
    except Exception:
        # En CI ou si le dossier n'existe pas, on passe
        pass

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Flux non reconfigurable
        pass
        
    # ⚠️ SANS FILTRE, CETTE SONDE MESURE LE MAUVAIS MODELE. 4 humeurs x 4 messages
    # = 16 appels, et le prompt de persona pese ~3300 tokens : Groq (8000 tokens/MINUTE)
    # rend 429 des le deuxieme, donc TOUT ce qui s'affiche vient du repli 14B. Or
    # l'esquive du 10/09 venait de gpt-oss-120b, le PREMIER echelon. Filtrer l'humeur
    # ramene la campagne a 4 appels, ce qui tient dans le quota avec la pause ci-dessous.
    ap = argparse.ArgumentParser(description="Sonde Jyggalag — imprime les repliques brutes, ne juge rien.")
    ap.add_argument("--humeur", choices=sorted(MOOD_PROMPTS), action="append",
                    help="Limite a cette humeur (repetable). Defaut : bliss, l'humeur ou le defaut a ete observe.")
    ap.add_argument("--pause", type=float, default=35.0,
                    help="Secondes entre deux appels (defaut 35 : sous les 8000 tokens/min de Groq).")
    args = ap.parse_args()
    humeurs = args.humeur or ["bliss"]

    load_keys()

    # Cascade réelle de Sheogorath
    cascade = CASCADES_PERSONA["sheo"]

    for humeur in humeurs:
        prompt = MOOD_PROMPTS[humeur]
        print(f"\n{'='*60}\n HUMEUR : {humeur.upper()}\n{'='*60}")
        
        for msg in MESSAGES:
            print(f"\n▶ Message : {msg}")
            
            reponse = None
            for client_type, model_name in cascade:
                try:
                    if client_type == "groq":
                        reponse, _, err = openai_like(GQ, "GROQ_API_KEY", model_name, msg, extra=CHARGE(prompt, msg, model_name, groq=True))
                    elif client_type == "mistral":
                        reponse, _, err = openai_like(MI, "MISTRAL_API_KEY", model_name, msg, extra=CHARGE(prompt, msg))
                    elif client_type == "gemini":
                        # Gemini's prompt in sonde_repartie doesn't accept system prompt perfectly, we'll just prepend it.
                        from tools.sonde_repartie import UA
                        import urllib.parse
                        import urllib.request
                        import json
                        cle = os.environ.get("GEMINI_KEY_1", "")
                        url = ("https://generativelanguage.googleapis.com/v1beta/models/" + model_name
                               + ":generateContent?key=" + urllib.parse.quote(cle))
                        charge = {"contents": [{"role": "user",
                                                "parts": [{"text": prompt + "\n\nMessage : " + msg}]}],
                                  "generationConfig": {"temperature": 1.0, "maxOutputTokens": 300}}
                        req = urllib.request.Request(url, data=json.dumps(charge).encode(),
                                                     headers={"Content-Type": "application/json", "User-Agent": UA})
                        try:
                            with urllib.request.urlopen(req, timeout=120) as r:
                                parts = json.load(r)["candidates"][0]["content"].get("parts") or [{}]
                                reponse = parts[0].get("text", "")
                            err = None
                        except Exception as e:
                            err = str(e)
                    else:
                        continue
                    
                    if not err and reponse:
                        print(f"  [{client_type.upper()} {model_name}] {reponse.strip()}")
                        break
                    else:
                        print(f"  [{client_type.upper()} {model_name}] Échec : {err}")
                except Exception as e:
                    print(f"  [{client_type.upper()} {model_name}] Erreur script : {e}")
            
            # ⚠️ Groq est plafonné à 8000 tokens/MINUTE et le prompt de persona en
            # pèse ~3300 : deux appels rapprochés suffisent à déclencher un 429
            # (mesuré en live le 10/09). On espace, et on accepte que la cascade
            # descende d'échelon quand ça arrive.
            time.sleep(args.pause)
            
if __name__ == "__main__":
    sys.exit(main())
