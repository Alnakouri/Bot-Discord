# -*- coding: utf-8 -*-
"""N invitations `!discord`, par le VRAI chemin de code, sur l'echelon qu'on choisit.

⚠️ POURQUOI CETTE SONDE EXISTE. Toutes les mesures de la phrase de lien du 19 au 22/09
ont ete faites avec des scripts jetables, refaits a chaque fois — et la moitie des
conclusions de ces trois jours ont ete CORRIGEES par une mesure suivante. Le cout de
refaire l'outil a chaque question est ce qui a rendu ces corrections si tardives.

CE QU'ELLE MESURE, ET CE QU'ELLE NE MESURE PAS
----------------------------------------------
Elle n'ecrit AUCUNE instruction : elle appelle `_generate_link_line`, celui de la prod,
qui batit son texte comme en salon. Un script qui reconstruirait le prompt mesurerait sa
propre copie ([[gotcha-test-qui-retape-la-logique]]). Le cache de phrases est vide a
chaque tour, et le jeu diffuse est injecte par un faux HelixClient.

Ce qu'elle IMPRIME est generique : longueur, ouvertures, repli sur le gabarit fixe. Le
comptage des defauts de PERSONA — un the chez Alfred, un fromage chez Sheogorath — se
fait en LISANT les phrases : aucune regex ecrite d'avance ne les aurait attrapes, et
celle qu'on ecrit apres coup penche du cote de ce qu'on espere trouver.

    python tools/sonde_phrase_de_lien.py --bot alfred --n 18
    python tools/sonde_phrase_de_lien.py --bot sheogorath --n 18 --tete mistral --sans-jeu
    python tools/sonde_phrase_de_lien.py --bot maiq --n 18 --clause "<une clause a essayer>"

CE QUE LES OPTIONS ONT SERVI A TRANCHER
---------------------------------------
`--tete mistral` — mesurer un bot que sa tete refuse de servir. Sheogorath n'avait
JAMAIS pu etre mesure depuis le 21/09 (Groq le rate-limite a 3-4 appels) ; ministral,
son 2e echelon, l'a rendu mesurable le 22/09 en 18 generations. Meme sortie pendant la
panne Gemini du 22/09 (503 toute l'apres-midi).
⚠️ Ce qu'on etablit ainsi vaut POUR CET ECHELON. Alfred : 1/22 objets inventes sous
flash-lite, **12/17 sous ministral, fiche identique**.
Cf. [[gotcha-la-fiche-n-agit-que-sur-un-modele-qui-ecoute]].

`--clause` et `--force-accroche` — repondre a « faut-il l'ajouter a la table ? » SANS
toucher au code de prod. Sheogorath, 18 generations par bras : l'accroche au jeu reparait
ses objets mieux que tout (12/18 -> 1/18) mais faisait **disparaitre l'invitation une
fois sur deux** (18/18 -> 9/18). ▶ Toujours verifier que la sortie fait encore CE POUR
QUOI elle existe, pas seulement qu'elle evite ses defauts connus.

`--timeout` — mesurer la PROSE quand le fournisseur est lent. La qualite d'un texte ne
depend pas de sa latence ; laisser la borne de prod a 8 s pendant la panne du 22/09 ne
mesurait plus que des `TimeoutError`. Seule la borne de l'APPEL bouge, jamais
l'instruction.
"""
import argparse
import asyncio
import os
import sys
import time
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

# (dossier, module, attribut) — la fiche REELLE, celle que le bot envoie.
# ⚠️ Sheogorath n'entre pas dans le moule : sa cle n'est pas son dossier, et son prompt
# s'appelle `PERSONALITY_BASE`. Une sonde qui suppose l'uniformite le laisse dehors, et
# c'est justement le bot qu'on n'arrivait pas a mesurer.
BOTS = {
    "alfred":     ("Alfred",     "alfred_data", "PERSONALITY_PROMPT"),
    "johnny":     ("JohnnyBot",  "johnny_data", "PERSONALITY_PROMPT"),
    "maiq":       ("MaiqBot",    "maiq_data",   "PERSONALITY_PROMPT"),
    "malena":     ("MalenaBot",  "malena_data", "PERSONALITY_PROMPT"),
    "sugar":      ("SugarBot",   "sugar_data",  "PERSONALITY_PROMPT"),
    "sheogorath": ("Sheogorath", "sheo_data",   "PERSONALITY_BASE"),
}

PLAFOND_DEMANDE = 120      # ce que l'instruction reclame, en caracteres


def charger(bot_id):
    """La fiche ET les cles de CE bot, depuis son propre dossier.

    ⚠️ Jamais les six .env a la suite : le dernier charge gagnerait, et on mesurerait un
    bot avec la cle d'un autre ([[gotcha-six-cles-un-seul-quota]]).
    """
    dossier, module, attribut = BOTS[bot_id]
    chemin = str(RACINE / dossier)
    if chemin not in sys.path:
        sys.path.insert(0, chemin)
    from shared.secure_env import load_secure_env
    load_secure_env(RACINE / dossier)
    mod = __import__(module)
    # Les bots tiennent un POOL `GEMINI_KEY_1..4`, pas une `GEMINI_API_KEY`.
    cles = [os.getenv(f"GEMINI_KEY_{i}") for i in range(1, 5)]
    return getattr(mod, attribut), [c for c in cles if c]


def faux_bot(bot_id, fiche, cles, jeu, tete):
    """Le minimum pour que `_generate_link_line` tourne — et RIEN de plus.

    Un seul echelon est servi : on veut la tete CONSTANTE d'un bout a l'autre de la
    mesure, sinon un changement d'echelon en cours de route se lit comme un effet de la
    fiche ([[gotcha-le-compte-brut-est-fausse-par-l-echelon-qui-a-repondu]]).
    """
    from shared.twitch.dispatch import DispatchMixin
    from core.api_manager import MultiAPIKeyManager

    class Faux(DispatchMixin):
        pass

    f = Faux()
    f.bot_id = bot_id
    f.bot_label = bot_id
    f.channels = ["un_canal"]
    f.client_id, f.client_secret = "id", "secret"
    f.personality_prompt = fiche
    f.system_prompt_provider = None
    f.mistral_client = f.groq_client = f.nvidia_client = None

    km = MultiAPIKeyManager()
    km.register_api("gemini", [] if tete == "mistral" else cles)
    if tete == "mistral":
        from mistralai import Mistral
        cle = os.getenv("MISTRAL_API_KEY")
        km.register_api("mistral", [cle])
        f.mistral_client = Mistral(api_key=cle)
    f.key_manager = km

    journal = []
    f.logger = types.SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: journal.append(a[0] if a else ""),
        warning=lambda *a, **k: journal.append("WARN " + (a[0] if a else "")),
        error=lambda *a, **k: journal.append("ERR " + (a[0] if a else "")))
    f._journal = journal

    class Helix:
        async def get_current_game(self, chan, live_only=False):
            return (jeu, "42") if jeu else None
    f._helix_client = Helix()
    return f


def resumer(phrases, replis, n):
    """Les seuls chiffres qui se comptent sans lire. Le reste se LIT."""
    print("=" * 78)
    if not phrases:
        print(f"  aucune phrase exploitable sur {n} : le repli a tout pris.")
        return
    longueurs = sorted(len(p) for p in phrases)
    ouvertures = {}
    for p in phrases:
        cle = " ".join(p.split()[:3]).lower().strip(",'\"")
        ouvertures[cle] = ouvertures.get(cle, 0) + 1
    tete = max(ouvertures.items(), key=lambda kv: kv[1])
    print(f"  exploitables      : {len(phrases)}/{n}"
          + (f"   ({replis} tombees sur le gabarit fixe)" if replis else ""))
    print(f"  longueur mediane  : {longueurs[len(longueurs) // 2]} car."
          f"   (plafond demande : {PLAFOND_DEMANDE})")
    print(f"  au-dela du plafond: {sum(1 for l in longueurs if l > PLAFOND_DEMANDE)}"
          f"/{len(phrases)}")
    print(f"  ouvertures        : {len(ouvertures)} distinctes ; la plus frequente "
          f"{tete[1]}x « {tete[0]} »")
    print()
    print("  ⚠️ Les defauts de PERSONA — objet promis, lieu invente, invitation qui "
          "n'invite plus — ne se")
    print("     comptent PAS ici : ils se LISENT. Une regex ecrite apres coup trouve ce "
          "qu'on espere.")


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bot", default="alfred", choices=sorted(BOTS))
    ap.add_argument("--n", type=int, default=18,
                    help="nombre de generations. 18 est le plancher utile : a 6, un "
                         "ecart de 1 a 3 n'est pas distinguable du tirage.")
    ap.add_argument("--jeu", default="Elden Ring", help="le jeu que le faux Helix annonce")
    ap.add_argument("--sans-jeu", action="store_true",
                    help="stream eteint : l'accroche au jeu ne part pas")
    ap.add_argument("--pause", type=float, default=2.0, help="secondes entre deux appels")
    ap.add_argument("--tete", default="gemini", choices=("gemini", "mistral"),
                    help="quel echelon doit repondre. `mistral` n'enregistre AUCUNE cle "
                         "gemini : la cascade va droit a ministral, echelon constant, "
                         "sans payer un refus a chaque tour.")
    ap.add_argument("--timeout", type=float, default=8.0,
                    help="borne de l'appel. 8 s = la prod. Plus haut pour mesurer la "
                         "PROSE quand le fournisseur est lent.")
    ap.add_argument("--clause", default=None,
                    help="clause par-bot a ESSAYER, sans toucher au code de prod")
    ap.add_argument("--force-accroche", action="store_true",
                    help="ajoute ce bot a ACCROCHE_AU_JEU le temps de la mesure")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # flux deja en UTF-8, ou redirige : la sonde mesure quand meme

    if args.timeout != 8.0:
        # On ne retape pas la construction de l'instruction : le VRAI
        # `_generate_link_line` la batit, et on ne desserre QUE la borne de l'appel.
        import shared.llm_cascade as lc
        original = lc.generate_response

        async def borne_desserree(**kw):
            kw["call_timeout"] = args.timeout
            return await original(**kw)
        lc.generate_response = borne_desserree

    from shared.twitch.dispatch import DispatchMixin
    if args.force_accroche:
        DispatchMixin.ACCROCHE_AU_JEU = set(DispatchMixin.ACCROCHE_AU_JEU) | {args.bot}
    if args.clause is not None:
        DispatchMixin.CLAUSES_PAR_BOT = dict(DispatchMixin.CLAUSES_PAR_BOT)
        DispatchMixin.CLAUSES_PAR_BOT[args.bot] = args.clause

    fiche, cles = charger(args.bot)
    if args.tete == "gemini" and not cles:
        print(f"[!] aucune GEMINI_KEY_n pour {args.bot} : rien a mesurer.")
        return 1
    if args.tete == "mistral" and not os.getenv("MISTRAL_API_KEY"):
        print(f"[!] aucune MISTRAL_API_KEY pour {args.bot} : rien a mesurer.")
        return 1

    jeu = None if args.sans_jeu else args.jeu
    f = faux_bot(args.bot, fiche, cles, jeu, args.tete)
    print(f"{args.bot} | tete={args.tete} | fiche {len(fiche)} car. | jeu={jeu!r} | "
          f"n={args.n} | borne {args.timeout:g}s"
          + ("  | CLAUSE INJECTEE" if args.clause else "")
          + ("  | ACCROCHE FORCEE" if args.force_accroche else ""))
    print("=" * 78)

    phrases, replis = [], 0
    for i in range(args.n):
        f._link_lines_cache = {}      # sinon la 2e generation rend la 1re
        del f._journal[:]
        debut = time.perf_counter()
        try:
            rendu = await f._generate_link_line("discord", "discord", "https://X")
        except Exception as e:
            rendu = f"<<EXCEPTION {type(e).__name__}: {e}>>"
        duree = time.perf_counter() - debut

        if rendu:
            phrase = rendu.replace(" https://X", "")
            phrases.append(phrase)
        else:
            phrase = "<<repli sur le gabarit fixe>>"
            replis += 1
        print(f"{i + 1:3}. [{duree:5.2f}s] {phrase}")
        for ligne in f._journal:
            if "rejetee" in ligne or ligne.startswith(("ERR", "WARN")):
                print(f"      ↳ {ligne[:150]}")
        if i + 1 < args.n:
            await asyncio.sleep(args.pause)

    resumer(phrases, replis, args.n)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
