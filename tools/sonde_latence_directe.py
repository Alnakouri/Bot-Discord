"""Un echelon tient-il la borne du DIRECT, maintenant, au calme ?

⚠️ POURQUOI CETTE SONDE EXISTE. Le 2026-09-21, pendant une passe d'eval a quatre bots,
`gemini-3.5-flash-lite` a depasse 15 s — la borne du chat — sur **7 appels sur 35 (20 %)**,
avec des pointes a 33, 37 et 49 s. Les jours precedents : 4 sur 166, soit 2 %. Et la
MEDIANE n'avait quasiment pas bouge (2,6 -> 3,5 s) : c'est la QUEUE qui explose, et une
mediane ne la voit pas.

Le harnais d'eval ne pouvait pas le signaler : il borne a 90 s, donc ces appels-la
REUSSISSENT chez lui alors qu'en salon ils tombent en `TimeoutError` et coutent 15 s de
silence avant que l'echelon suivant reponde ([[gotcha-borne-du-direct-sabote-le-lot]],
[[gotcha-la-borne-du-LOT-cache-ce-que-le-direct-refuse]]).

⚠️ Et la passe est sa propre suspecte : elle tape la MEME cle que les bots. D'ou cette
sonde, qui mesure au CALME, a une cadence de salon, avec :
  - la vraie fiche du bot (la taille du prompt pese sur la latence) ;
  - sa PROPRE cle, chargee depuis son .env chiffre a lui — jamais les six a la suite,
    qui laissent la derniere gagner ([[gotcha-six-cles-un-seul-quota]]) ;
  - la config de la cascade partagee, `thinking_level="minimal"` compris : sans lui on
    mesure un autre appel que celui des bots ([[gotcha-sonde-ne-reproduit-pas-le-fournisseur]]).

Ce qu'elle rend, et c'est le seul chiffre qui compte : **la part des appels au-dela de la
borne**. La mediane est affichee pour memoire, elle ne decide de rien.

    python tools/sonde_latence_directe.py --bot alfred --n 30

RESULTAT DU 2026-09-21, 20:30, au calme (c'est la reference a battre) :

    alfred   0 / 30 au-dela de 15 s   mediane 1,37 s   max 14,4 s
    sugar    1 / 29 au-dela de 15 s   mediane 1,22 s   max 15,7 s
    cumul    1 / 59 = 1,7 %  — exactement la reference historique (4/166 = 2 %)

Contre **7 / 35 = 20 %** pendant la passe d'eval. Si le taux reel etait celui du calme,
voir sept depassements sur trente-cinq a une probabilite de 1,8e-06 : la difference est
reelle, et c'est la PASSE qui la cause (le juge tape la meme cle, et ses prompts portent
transcript + historique, bien plus gros qu'un message de salon).

▶ **Conclusion pour la prod : aucun defaut permanent.** flash-lite tient la borne du
direct a cadence de salon. ⚠️ **Mais pendant une passe d'eval, l'echelon de tete des bots
se degrade vraiment** : ne pas mesurer la latence de prod pendant une passe, et ne pas
s'etonner qu'un bot reponde mal a ce moment-la.
"""
import argparse
import os
import statistics
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from shared.models import GEMINI_FLASH_LITE  # noqa: E402

# (dossier, module, attribut) — la fiche reelle, celle que le bot envoie.
BOTS = {
    "alfred":  ("Alfred",     "alfred_data",  "PERSONALITY_PROMPT"),
    "johnny":  ("JohnnyBot",  "johnny_data",  "PERSONALITY_PROMPT"),
    "maiq":    ("MaiqBot",    "maiq_data",    "PERSONALITY_PROMPT"),
    "malena":  ("MalenaBot",  "malena_data",  "PERSONALITY_PROMPT"),
    "sheo":    ("Sheogorath", "sheo_data",    "PERSONALITY_BASE"),
    "sugar":   ("SugarBot",   "sugar_data",   "PERSONALITY_PROMPT"),
}

# Des messages de salon, courts, sans piege : on mesure le TRANSPORT, pas la prose.
MESSAGES = [
    "salut, ca va ?",
    "t'as vu ce qui s'est passe hier ?",
    "tu penses quoi de tout ca ?",
    "raconte-moi un truc",
]

BORNE_DU_DIRECT = 15      # ce que le chat accorde
PLAFOND = 60              # au-dela, on parle de mort, plus de lenteur


def charger(bot_id):
    """La fiche ET la cle de CE bot, depuis son propre dossier."""
    dossier, module, attribut = BOTS[bot_id]
    chemin = str(RACINE / dossier)
    if chemin not in sys.path:
        sys.path.insert(0, chemin)
    from shared.secure_env import load_secure_env
    load_secure_env(RACINE / dossier)
    mod = __import__(module)
    # ⚠️ La cle ne s'appelle pas `GEMINI_API_KEY` : les bots tiennent un POOL,
    # `GEMINI_KEY_1..4`, et l'enregistrent via `register_api("gemini", [...])`. Chercher
    # le mauvais nom rendait la sonde muette avec un message parfaitement credible.
    cles = [os.getenv(f"GEMINI_KEY_{i}") for i in range(1, 5)]
    cles = [c for c in cles if c]
    return getattr(mod, attribut), (cles[0] if cles else None)


def appeler(client, modele, fiche, message, borne):
    """Un appel, borne comme en salon. Rend (duree_s, erreur_ou_None)."""
    from google.genai import types
    debut = time.perf_counter()
    try:
        client.models.generate_content(
            model=modele,
            contents=[types.Content(role="user", parts=[
                types.Part(text=f"{fiche}\n\nDernier message : {message}")])],
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=300,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
            ),
        )
        return time.perf_counter() - debut, None
    except Exception as e:
        return time.perf_counter() - debut, f"{type(e).__name__}: {str(e)[:80]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bot", default="alfred", choices=sorted(BOTS))
    ap.add_argument("--modele", default=GEMINI_FLASH_LITE)
    ap.add_argument("--n", type=int, default=30, help="nombre d'appels (defaut 30)")
    ap.add_argument("--pause", type=float, default=6.0,
                    help="secondes entre deux appels. Defaut 6 : cadence de salon, et "
                         "10 appels/min laissent de la marge sous le quota Gemini "
                         "(15/min PAR MODELE).")
    ap.add_argument("--borne", type=float, default=BORNE_DU_DIRECT)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        # Flux deja en UTF-8, ou redirige, ou sans `reconfigure` : il n'y a rien a
        # corriger, et echouer ici empecherait la sonde de mesurer quoi que ce soit.
        pass

    fiche, cle = charger(args.bot)
    if not cle:
        print(f"[!] Aucune cle GEMINI_KEY_n pour {args.bot} : rien a mesurer.")
        return 1
    from shared.safe_client import get_client as get_safe_genai_client
    client = get_safe_genai_client(api_key=cle, http_options={"api_version": "v1beta"})

    print(f"{args.bot} / {args.modele} | fiche {len(fiche)} car. | {args.n} appels, "
          f"1 toutes les {args.pause:g}s | borne {args.borne:g}s")
    durees, erreurs = [], []
    for i in range(args.n):
        d, err = appeler(client, args.modele, fiche, MESSAGES[i % len(MESSAGES)], args.borne)
        if err:
            erreurs.append((d, err))
            marque = f"  ERREUR {err}"
        else:
            durees.append(d)
            marque = "  <<< HORS BORNE DU DIRECT" if d > args.borne else ""
        print(f"  {i + 1:3}/{args.n}  {d:6.2f}s{marque}")
        if i + 1 < args.n:
            time.sleep(args.pause)

    print("\n" + "=" * 72)
    if not durees:
        print(f"Aucun appel abouti sur {args.n}. Erreurs : {erreurs[:3]}")
        return 1

    hors = [d for d in durees if d > args.borne]
    morts = [d for d in durees if d > PLAFOND]
    ordonnees = sorted(durees)
    p90 = ordonnees[min(len(ordonnees) - 1, int(0.9 * len(ordonnees)))]
    print(f"  appels aboutis   : {len(durees)}/{args.n}"
          + (f"  ({len(erreurs)} erreur(s))" if erreurs else ""))
    print(f"  mediane          : {statistics.median(durees):6.2f}s   (pour memoire : "
          f"elle ne voit pas la queue)")
    print(f"  p90 / max        : {p90:6.2f}s / {max(durees):.2f}s")
    print(f"  AU-DELA DE {args.borne:g}s   : {len(hors)}/{len(durees)} "
          f"({len(hors) / len(durees):.0%})"
          + (f"   dont {len(morts)} au-dela de {PLAFOND}s" if morts else ""))
    print()
    # Le seul verdict qui porte : en salon, ces appels-la sont REFUSES.
    part = len(hors) / len(durees)
    if part >= 0.10:
        print(f"  ⚠️ EN SALON, {part:.0%} DES MESSAGES TOMBERAIENT EN TimeoutError sur cet")
        print(f"     echelon, et couteraient {args.borne:g}s de silence avant le suivant.")
    elif hors:
        print(f"  Queue presente mais marginale ({part:.0%}). Comparer a la reference du")
        print("     jour avant d'en conclure quoi que ce soit.")
    else:
        print("  Aucun depassement : cet echelon tient la borne du direct, maintenant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
