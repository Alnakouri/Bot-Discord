# -*- coding: utf-8 -*-
"""Sonde : Gemini refuse-t-il le PROMPT ENTIER d'un bot (PROHIBITED_CONTENT) ?

⚠️ 24/09 : la fiche de Sugar + ANTI_INJECTION_GUARD franchissait une frontiere au-dela de
laquelle Gemini bloque tout le prompt (`prompt_feedback.block_reason`), sans exception :
reponse vide, bascule sur l'echelon suivant, aucune trace lisible. Un bot peut ainsi etre
« vivant mais jamais servi par Gemini » sans que personne le voie.

Un appel par prompt, sur `gemini-3.5-flash-lite` (echelon texte des six personas), avec
la cle du bot SEUL : chaque bot est sonde dans son propre processus, pour que les
variables d'environnement d'un bot ne fuient jamais dans l'appel d'un autre.

Pas dans pytest : il faut les cles, et chaque appel consomme du quota.

    python tools/sonde_blocage_gemini.py              # les six bots
    python tools/sonde_blocage_gemini.py --bot sheo   # un seul
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# bot -> (dossier, module de fiche, [(nom du prompt, attribut)], sur Twitch ?)
BOTS = {
    "alfred": ("Alfred", "alfred_data", [("fiche", "PERSONALITY_PROMPT")], False),
    "maiq":   ("MaiqBot", "maiq_data", [("fiche", "PERSONALITY_PROMPT")], False),
    "malena": ("MalenaBot", "malena_data", [("fiche", "PERSONALITY_PROMPT")], False),
    "johnny": ("JohnnyBot", "johnny_data", [("fiche", "PERSONALITY_PROMPT")], True),
    "sugar":  ("SugarBot", "sugar_data", [("fiche", "PERSONALITY_PROMPT")], True),
    "sheo":   ("Sheogorath", "sheo_data", [
        ("neutral", "PERSONALITY_NEUTRAL"), ("mania", "PERSONALITY_MANIA"),
        ("dementia", "PERSONALITY_DEMENTIA"), ("bliss", "PERSONALITY_BLISS"),
    ], True),
}

MODELE = "gemini-3.5-flash-lite"
MESSAGE = "Ahmed (sur Twitch) dit : salut, ça va ?"


def sonder_un_bot(bot: str) -> int:
    dossier, module, prompts, twitch = BOTS[bot]
    sys.path.insert(0, str(RACINE))
    sys.path.insert(0, str(RACINE / dossier))
    from shared.secure_env import load_secure_env
    load_secure_env(RACINE / dossier)
    cle = os.getenv("GEMINI_KEY_1")
    if not cle:
        print(f"{bot:7s} | pas de GEMINI_KEY_1 dans {dossier}/.env — non sondé")
        return 0

    import importlib
    from google import genai
    from google.genai import types
    from shared.twitch.llm import ANTI_INJECTION_GUARD

    data = importlib.import_module(module)
    client = genai.Client(api_key=cle)
    bloques = 0
    for nom, attr in prompts:
        fiche = getattr(data, attr)
        variantes = [("seule", fiche)]
        if twitch:
            variantes.append(("+garde Twitch", fiche + "\n\n" + ANTI_INJECTION_GUARD))
        for etiquette, prompt in variantes:
            try:
                for essai in range(3):
                    try:
                        rep = client.models.generate_content(
                            model=MODELE, contents=MESSAGE,
                            config=types.GenerateContentConfig(
                                system_instruction=prompt, max_output_tokens=60),
                        )
                        break
                    except Exception as e:
                        # 503 = Gemini surcharge, pas un refus du prompt : on reessaie,
                        # sinon la sonde ne conclut rien pour ce bot.
                        if "503" not in str(e) or essai == 2:
                            raise
                        time.sleep(15)
                fb = getattr(rep, "prompt_feedback", None)
                raison = getattr(fb, "block_reason", None) if fb else None
                if raison:
                    bloques += 1
                    verdict = f"❌ BLOQUÉ ({raison})"
                else:
                    verdict = "✅ servi" if rep.text else "⚠️ vide (sans block_reason)"
            except Exception as e:
                verdict = f"?? {type(e).__name__}: {str(e)[:90]}"
            print(f"{bot:7s} | {nom:9s} | {etiquette:14s} | {len(prompt):5d} car. | {verdict}")
    return bloques


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bot", choices=sorted(BOTS))
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # flux deja en UTF-8, ou redirige : la sonde mesure quand meme

    if args.bot:
        return 1 if sonder_un_bot(args.bot) else 0

    # Un processus par bot : les cles d'un bot ne doivent jamais servir a un autre.
    code = 0
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for bot in BOTS:
        r = subprocess.run([sys.executable, __file__, "--bot", bot], env=env)
        code |= r.returncode
    return code


if __name__ == "__main__":
    sys.exit(main())
