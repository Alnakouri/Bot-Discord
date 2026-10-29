# -*- coding: utf-8 -*-
"""Sonde : NVIDIA repond-il vraiment, dans les six conteneurs ?

NVIDIA est le **dernier echelon** de la cascade des six personas. C'est ce qui le rend
impossible a valider en observant les logs : tant que Gemini, Groq et Mistral repondent,
il ne sert jamais. Mesure du 2026-09-05 sur `data/api_usage.db` : **zero appel NVIDIA**
depuis son ajout le 04/09 — non pas parce qu'il est casse, mais parce que la cascade
n'est jamais descendue jusqu'a lui.

Le 2026-09-05, ce silence a cache un vrai bug pendant 24 h : les quatre cascades INLINE
n'avaient aucune branche `nvidia`, et Johnny/Sugar levaient un `NameError` avale par leur
propre `except`. Rien dans les logs, et le health check du demarrage annoncait
« NVIDIA : Oui » parce qu'il regarde la CLE, jamais le cablage.

    python tools/sonde_nvidia.py               # ping direct du client, dans les 6
    python tools/sonde_nvidia.py --cascade     # + la cascade du noyau, forcee sur nvidia
    python tools/sonde_nvidia.py --essais 10   # 10 pings par bot : la fuite est rare
    python tools/sonde_nvidia.py --strict      # code de sortie 1 au moindre KO

Ce que chaque mode prouve, et ce qu'il ne prouve pas :

* **ping** : la cle, le modele, l'URL et `nvidia_kwargs()` sont bons DANS le conteneur,
  avec la cle de CE bot. Ne prouve rien du cablage de la cascade.
* **--cascade** : `generate_response()` du noyau descend jusqu'a l'echelon `nvidia` et en
  rend du texte. Couvre Johnny et Sugar, qui passent par le noyau. ⚠️ Ne couvre PAS les
  quatre cascades recopiees dans `on_message` (Alfred, M'aiq, Malena, Sheogorath) : leur
  code n'est pas appelable hors d'un vrai message Discord. Pour celles-la, l'autorite
  reste `tests/test_nvidia_cable_partout.py`, qui en lit la structure.

⚠️ Ce que la sonde a trouve le 2026-09-05, et qui reste ouvert : nemotron laisse fuir du
meta-discours dans `content` environ **une fois sur vingt**, malgre
`reasoning_effort=none` (`'p? The user wants exactly: pong'`,
`'p deepellsellsellsellsellsellsworth, pong'`). Le filet du noyau,
`_fuite_de_raisonnement()`, ne peut PAS l'attraper : il compare `content` a `reasoning`,
et NVIDIA ne remplit jamais `reasoning`. Le commentaire « filet malgre tout » de la
branche nvidia de `llm_cascade.py` promet donc une protection qui n'existe pas. Decision
a poser, cf. docs/plans/PLAN.md.

⚠️ La sonde n'affiche jamais une cle entiere, seulement ses 6 derniers caracteres —
assez pour verifier a l'oeil que les six bots ont bien six cles DIFFERENTES
([[regle-une-cle-api-par-bot]]).

⚠️ Elle s'execute DANS les conteneurs (`docker exec`), parce que les cles ne vivent que
la : elles sont chiffrees, et `load_secure_env()` ne les dechiffre qu'avec la
`.master_key` montee dans l'image. La lancer depuis l'hote ne dirait rien.

Elle n'est pas dans la suite de tests a dessein : elle exige Docker allume, six
conteneurs debout et un vrai appel reseau. La CI ne peut rien en faire.
"""
import argparse
import os
os.environ.setdefault("SUIVI_ORIGINE", "sonde")
import subprocess
import sys

CONTENEURS = [
    "bot-alfred",
    "bot-johnny",
    "bot-maiq",
    "bot-malena",
    "bot-sheogorath",
    "bot-sugar",
]

# Les quatre bots dont la cascade est recopiee dans `on_message` : --cascade sonde le
# noyau, qui n'est PAS le code qu'ils executent. On le dit plutot que de le laisser croire.
CASCADES_INLINE = {"bot-alfred", "bot-maiq", "bot-malena", "bot-sheogorath"}

# La sonde demande un mot, et juge sur la LONGUEUR de ce qui revient — pas sur une liste
# de marqueurs, et pas sur l'obeissance.
#
# Pourquoi pas les marqueurs : mesure du 2026-09-05, une reponse de Malena est revenue en
# `'p? The user wants exactly: pong'`. Aucun `<think`, aucun « Okay, the user » : trois
# marqueurs bien choisis l'auraient ratee. La longueur, elle, la voit.
#
# Pourquoi pas le mot exact : sugar a repondu `'Ping'` au lieu de `'pong'`. C'est un
# modele qui repond de travers, pas un fournisseur casse. Un verdict qui compte ca pour
# un echec est un verdict qu'on apprend a ignorer. Un mot pour un mot : c'est bon.
#
# Le seuil est a UN mot parce qu'un seuil a trois a deja laisse passer une fuite :
# `'p deepellsellsellsellsellsellsworth, pong'` (M'aiq, 2026-09-05) en fait exactement
# trois. On a demande un mot, on juge sur un mot.
#
# ⚠️ Ne PAS importer `_fuite_de_raisonnement()` du noyau pour en faire le verdict : il
# exige un champ `reasoning` separe, que l'endpoint NVIDIA ne remplit JAMAIS (mesure du
# 2026-09-05, 16 appels, `reasoning` vide a chaque fois). Il rendrait toujours False.
MOTS_MAX = 1

_PROLOGUE = '''
import os, sys, time
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/bot")
from pathlib import Path
from core.secure_env import load_secure_env
load_secure_env(Path("/app/bot"))
from core.models import NVIDIA_FAST, NVIDIA_BASE_URL, nvidia_kwargs

MOTS_MAX = {mots_max!r}
cle = os.getenv("NVIDIA_API_KEY")
if not cle:
    print("KO   NVIDIA_API_KEY absente du conteneur")
    sys.exit(0)
empreinte = "..." + cle[-6:]

def verdict(texte, ms):
    if not texte:
        return "KO", "reponse vide (la cascade serait tombee dans le vide)"
    # On a demande UN mot. Une phrase entiere en retour, c'est le modele qui pense tout
    # haut : c'est exactement ce qui serait parti dans Discord.
    mots = len(texte.split())
    if mots > MOTS_MAX:
        return "KO", "%d ms  fuite (%d mots pour UN mot demande) : %r" % (ms, mots, texte[:120])
    return "OK", "%d ms  cle=%s  %r" % (ms, empreinte, texte[:60])
'''

# ESSAIS repetitions : la fuite est INTERMITTENTE (3 sur ~20 appels le 2026-09-05). Un
# seul ping vert ne prouve pas qu'elle a disparu, il prouve qu'on ne l'a pas croisee.
_PING = '''
from openai import OpenAI
client = OpenAI(api_key=cle, base_url=NVIDIA_BASE_URL, max_retries=0)
ESSAIS = {essais!r}
for _essai in range(ESSAIS):
    depart = time.time()
    try:
        reponse = client.chat.completions.create(
            model=NVIDIA_FAST,
            messages=[{{"role": "user", "content": "Reponds exactement : pong"}}],
            max_tokens=30,
            temperature=0.2,
            **nvidia_kwargs(NVIDIA_FAST),
        )
        texte = (reponse.choices[0].message.content or "").strip()
        etat, detail = verdict(texte, int((time.time() - depart) * 1000))
        print("%s   ping     %s" % (etat, detail))
    except Exception as e:
        print("KO   ping     %s: %s" % (type(e).__name__, str(e)[:160]))
'''

# `cascade=` force l'echelon au lieu de celui de la persona : sans ca, les trois premiers
# fournisseurs repondraient et NVIDIA ne serait toujours pas exerce. `key_manager` n'est
# touche que par la branche gemini, absente ici.
_CASCADE = '''
import asyncio
import os
os.environ.setdefault("SUIVI_ORIGINE", "sonde")
from openai import OpenAI
from core.llm_cascade import generate_response
from core.smart_router import RequestType

class _SansCles:
    """key_manager muet : la branche qui s'en sert (gemini) n'est pas dans la cascade."""
    apis = {}
    def get_key(self, _nom): return None
    def report_error(self, *a, **k): pass

async def _principal():
    depart = time.time()
    texte = await generate_response(
        routing={"type": RequestType.TEXT},
        system_prompt="Tu reponds en un seul mot, sans ponctuation.",
        transcript="",
        user_message="Reponds exactement : pong",
        conversation_history=[],
        media_data=None,
        mime_type="text/plain",
        key_manager=_SansCles(),
        nvidia_client=OpenAI(api_key=cle, base_url=NVIDIA_BASE_URL, max_retries=0),
        bot_label="sonde_nvidia",
        max_tokens=30,
        cascade=[("nvidia", NVIDIA_FAST)],
    )
    return texte, int((time.time() - depart) * 1000)

try:
    texte, ms = asyncio.run(_principal())
    etat, detail = verdict(texte, ms)
    print("%s   cascade  %s" % (etat, detail))
except Exception as e:
    print("KO   cascade  %s: %s" % (type(e).__name__, str(e)[:160]))
'''


def _script(avec_cascade, essais):
    # ⚠️ Seuls _PROLOGUE et _PING passent par `.format()`. _CASCADE contient un `{}`
    # litteral (`apis = {}`) : le formater le casserait.
    script = _PROLOGUE.format(mots_max=MOTS_MAX) + _PING.format(essais=essais)
    if avec_cascade:
        script += _CASCADE
    return script


def _sonder(conteneur, script):
    """Rend la liste des lignes de verdict, ou une ligne KO si l'exec a echoue."""
    try:
        acheve = subprocess.run(
            ["docker", "exec", "-i", conteneur, "python", "-"],
            input=script,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        return ["KO   docker introuvable — Docker Desktop est-il allume ?"]
    except subprocess.TimeoutExpired:
        return ["KO   pas de reponse en 180 s"]
    lignes = [l for l in acheve.stdout.splitlines() if l.startswith(("OK ", "KO "))]
    if not lignes:
        detail = (acheve.stderr or acheve.stdout).strip().splitlines()
        return ["KO   " + (detail[-1][:160] if detail else "aucune sortie")]
    return lignes


def principal():
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument(
        "--cascade",
        action="store_true",
        help="exercer aussi generate_response() du noyau, forcee sur l'echelon nvidia",
    )
    analyseur.add_argument(
        "--essais",
        type=int,
        default=1,
        metavar="N",
        help="repeter le ping N fois par bot : la fuite est intermittente (defaut 1)",
    )
    analyseur.add_argument(
        "--strict", action="store_true", help="code de sortie 1 au moindre KO"
    )
    analyseur.add_argument(
        "--bot",
        action="append",
        metavar="CONTENEUR",
        help="ne sonder que ce conteneur (repetable)",
    )
    args = analyseur.parse_args()

    cibles = args.bot or CONTENEURS
    script = _script(args.cascade, args.essais)
    echecs = 0

    print("Sonde NVIDIA — le 4e fournisseur, celui qu'aucun log ne montre jamais\n")
    for conteneur in cibles:
        for ligne in _sonder(conteneur, script):
            print("  %-16s %s" % (conteneur, ligne))
            if ligne.startswith("KO"):
                echecs += 1

    print()
    if echecs:
        print("  %d verdict(s) KO." % echecs)
    else:
        print("  Tout est vert.")

    if args.cascade:
        inline = sorted(c for c in cibles if c in CASCADES_INLINE)
        if inline:
            print(
                "\n  /!\\ --cascade a exerce le NOYAU. %s portent leur cascade dans\n"
                "      `on_message` : ce vert ne dit rien de leur cablage. Pour eux,\n"
                "      l'autorite est tests/test_nvidia_cable_partout.py."
                % ", ".join(inline)
            )

    return 1 if (echecs and args.strict) else 0


if __name__ == "__main__":
    sys.exit(principal())
