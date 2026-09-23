# -*- coding: utf-8 -*-
"""Sonde du ton de Sugar sur Twitch.

Mesure les réponses de Sugar via le VRAI chemin de génération Twitch (_generate_response)
face à des messages courts, des excuses ou des reproches :
- "sugar"
- "@compte_bot_sugar dsl"
- "@compte_bot_sugar c'est mechant =("

Deux scénarios :
1. isole : bot remis à zéro à chaque tour (18 tours par message).
2. conversation : séquence des 3 messages avec persistance d'historique (18 conversations).
"""
import argparse
import asyncio
import collections
import os
import sys
import time
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

dossier_sugar = RACINE / "SugarBot"
if str(dossier_sugar) not in sys.path:
    sys.path.insert(0, str(dossier_sugar))

from shared.twitch.llm import LlmMixin
from shared.twitch.sanitize import SanitizeMixin
from core.api_manager import MultiAPIKeyManager


def charger_sugar():
    """Charge la fiche et les clés de Sugar depuis SugarBot/."""
    dossier = RACINE / "SugarBot"
    if str(dossier) not in sys.path:
        sys.path.insert(0, str(dossier))
    from shared.secure_env import load_secure_env
    load_secure_env(dossier)
    import sugar_data
    from sugar_grudge import tone_directive
    cles = [os.getenv(f"GEMINI_KEY_{i}") for i in range(1, 5)]
    return sugar_data.PERSONALITY_PROMPT, [c for c in cles if c], tone_directive


def creer_faux_bot(fiche, cles, tone_directive, tete="gemini"):
    class FauxBot(LlmMixin, SanitizeMixin):
        pass

    f = FauxBot()
    f.bot_id = "sugar"
    f.bot_label = "Sugar Bot"
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

    # Hook tone_directive_provider: prend (author, clean_message)
    f.tone_directive_provider = lambda author, message: tone_directive(message)

    journal = []
    f.logger = types.SimpleNamespace(
        debug=lambda *a, **k: None,
        info=lambda *a, **k: journal.append(a[0] if a else ""),
        warning=lambda *a, **k: journal.append("WARN " + (a[0] if a else "")),
        error=lambda *a, **k: journal.append("ERR " + (a[0] if a else "")),
    )
    f._journal = journal
    reinitialiser_etat(f)
    return f


def reinitialiser_etat(f):
    f.injection_hits = collections.defaultdict(int)
    f.enable_viewer_memory = False
    f.viewer_facts = {}
    f.recent_self_responses = {}
    f.channel_recent = {}
    f.histories = {}
    f.extra_recent_provider = None
    del f._journal[:]


MESSAGES_TEST = [
    "sugar",
    "@compte_bot_sugar dsl",
    "@compte_bot_sugar c'est mechant =(",
]


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scenario", choices=("isole", "conversation"), default="isole",
                    help="isole = un message sur bot neuf ; conversation = enchaînement des 3 messages")
    ap.add_argument("--n", type=int, default=18, help="nombre de répétitions (défaut 18)")
    ap.add_argument("--pause", type=float, default=4.5, help="pause en secondes entre appels (défaut 4.5s pour respecter 15 RPM)")
    ap.add_argument("--tete", choices=("gemini", "mistral"), default="gemini",
                    help="échelon LLM à interroger")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="borne de timeout LLM en secondes (défaut 30s)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # flux deja en UTF-8, ou redirige : la sonde mesure quand meme

    if args.timeout != 8.0:
        import shared.llm_cascade as lc
        original = lc.generate_response

        async def borne_desserree(**kw):
            kw["call_timeout"] = args.timeout
            return await original(**kw)
        lc.generate_response = borne_desserree

    fiche, cles, td_fn = charger_sugar()
    if args.tete == "gemini" and not cles:
        print("[!] Aucune GEMINI_KEY_n trouvée pour Sugar.")
        return 1
    if args.tete == "mistral" and not os.getenv("MISTRAL_API_KEY"):
        print("[!] Aucune MISTRAL_API_KEY trouvée pour Sugar.")
        return 1

    f = creer_faux_bot(fiche, cles, td_fn, tete=args.tete)
    channel = "ma_streameuse"
    author = "Ahmed"

    print(f"Sonde ton Sugar Twitch | scenario={args.scenario} | n={args.n} | tete={args.tete} | timeout={args.timeout:g}s | pause={args.pause:g}s")
    print("=" * 78)

    async def _appel_avec_retry(msg):
        for essai in range(3):
            t0 = time.perf_counter()
            try:
                rep = await f._generate_response(channel, author, msg)
            except Exception as e:
                rep = f"<<EXCEPTION {type(e).__name__}: {e}>>"
            dt = time.perf_counter() - t0
            if rep is not None:
                return rep, dt
            # Si None (rate limit / indisponibilité temporaire), on patiente
            await asyncio.sleep(20.0)
        return None, dt

    if args.scenario == "isole":
        for idx_msg, msg in enumerate(MESSAGES_TEST, 1):
            print(f"\n--- SOUS-SÉRIE {idx_msg}/3 : message = {msg!r} ---")
            for i in range(args.n):
                reinitialiser_etat(f)
                rep, dt = await _appel_avec_retry(msg)
                print(f"[{i + 1:2d}/{args.n}] ({dt:4.1f}s) User: {msg} -> Sugar: {rep}")
                if i + 1 < args.n:
                    await asyncio.sleep(args.pause)

    elif args.scenario == "conversation":
        for i in range(args.n):
            reinitialiser_etat(f)
            print(f"\n--- CONVERSATION {i + 1}/{args.n} ---")
            for msg in MESSAGES_TEST:
                rep, dt = await _appel_avec_retry(msg)
                print(f"  ({dt:4.1f}s) User: {msg}")
                print(f"         Sugar: {rep}")
                await asyncio.sleep(args.pause)

    print("\n" + "=" * 78)
    print("Fin des mesures.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
