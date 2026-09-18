# -*- coding: utf-8 -*-
"""Sonde : deux cles Gemini puisent-elles dans le MEME quota ?

Le quota gratuit de l'API Gemini est attache au PROJET Google, pas a la cle. Deux cles
nees dans le meme projet — ou, selon les regles de Google, dans le meme COMPTE — partagent
donc un seul seau, et les multiplier n'apporte rien.

⚠️ C'est exactement le piege dans lequel ce depot est tombe : les six bots ont six cles
DIFFERENTES (verifie par tools/sonde_cles_partagees.py) et se disputaient pourtant le meme
quota. Mesure des 17-18/09 : malena 53 appels servis contre 86 ecartes, maiq 32 contre 58,
sugar 44 contre 45, johnny 20 moments sans aucune cle saine, sheo zero appel servi. Et le
plancher de bruit du harnais d'eval (±6/17 entre deux passes identiques) n'avait pas
d'autre cause que la course au seau commun.

Aucun catalogue ne repond a la question : la page de quotas parle de « projet » sans dire
ce que Google compte vraiment, et le nom d'une metrique n'est pas une mesure. Seul un
appel reel tranche — meme lecon que le catalogue NVIDIA qui ment.

    python tools/sonde_quota_gemini_partage.py --cle-a <cle> --cle-b <cle>
    python tools/sonde_quota_gemini_partage.py --cle-a <cle> --cle-b <cle> --modele ...

METHODE : on epuise la cle A en l'appelant jusqu'au 429, puis on appelle B AUSSITOT.
  - B repond          -> seaux SEPARES. Multiplier les cles/projets paye.
  - B rend 429 aussi  -> seau COMMUN. Il faut un autre compte, ou un palier payant.

⚠️ La sonde DEPENSE le quota de A : c'est le prix de la reponse, et il se reconstitue tout
seul. Ne pas la lancer juste avant une passe d'eval.
"""
import argparse
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from shared.models import GEMINI_FLASH_LITE

# Court exprès : on cherche le refus, pas une réponse. Moins de tokens par appel = le
# quota par MINUTE se déclenche sur le nombre de requêtes, pas sur leur taille.
MESSAGE = "Dis juste: ok"


def _appel(cle, modele):
    """Rend (ok, code, detail). `code` vaut 429 quand le quota est atteint."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=cle, http_options={"api_version": "v1beta"})
    try:
        r = client.models.generate_content(
            model=modele,
            contents=MESSAGE,
            config=types.GenerateContentConfig(max_output_tokens=8),
        )
        return True, 200, (getattr(r, "text", "") or "")[:40]
    except Exception as e:
        code = getattr(e, "code", None) or getattr(getattr(e, "response", None), "status_code", None)
        # ⚠️ Le corps complet vit dans `details`, et le vrai delai de reprise est au 3e
        # niveau ([[gotcha-apierror-details-json-complet]]). On le rend brut : un
        # extracteur borne retomberait en silence sur le mauvais champ.
        return False, code, str(getattr(e, "details", None) or e)[:400]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cle-a", required=True, help="cle a EPUISER")
    ap.add_argument("--cle-b", required=True, help="cle a tester une fois A epuisee")
    ap.add_argument("--modele", default=GEMINI_FLASH_LITE)
    ap.add_argument("--max-appels", type=int, default=40,
                    help="borne de securite si A ne s'epuise jamais (defaut 40)")
    args = ap.parse_args()

    if args.cle_a == args.cle_b:
        raise SystemExit("[ERREUR] --cle-a et --cle-b sont la MEME cle : rien a comparer.")

    print(f"Modele : {args.modele}")
    print("1. J'epuise la cle A...")
    epuisee = False
    for i in range(1, args.max_appels + 1):
        ok, code, detail = _appel(args.cle_a, args.modele)
        print(f"   A[{i:2d}] {'ok' if ok else f'ECHEC {code}'} {'' if ok else detail[:120]}")
        if not ok and code == 429:
            epuisee = True
            break
        if not ok:
            raise SystemExit(f"[ERREUR] la cle A echoue sans 429 ({code}) : rien ne prouve "
                             f"que le quota soit en cause.\n{detail}")
        time.sleep(0.3)

    if not epuisee:
        print(f"\n>>> INDETERMINE : la cle A n'a pas atteint son quota en {args.max_appels} "
              f"appels. Relancer avec --max-appels plus grand, ou a un moment plus charge.")
        return

    print("\n2. J'appelle la cle B IMMEDIATEMENT...")
    ok, code, detail = _appel(args.cle_b, args.modele)
    print(f"   B    {'ok' if ok else f'ECHEC {code}'} {detail[:200]}")

    print()
    if ok:
        print(">>> SEAUX SEPARES : B repond alors que A est a sec.")
        print("    Multiplier les cles (un projet/compte par bot) multiplie le quota.")
    elif code == 429:
        print(">>> SEAU COMMUN : B est refusee elle aussi, dans la seconde.")
        print("    Ajouter des cles au meme endroit n'apportera RIEN. Il faut un autre")
        print("    compte Google, ou un palier payant.")
    else:
        print(f">>> INDETERMINE : B echoue en {code}, qui ne parle pas de quota.")


if __name__ == "__main__":
    main()
