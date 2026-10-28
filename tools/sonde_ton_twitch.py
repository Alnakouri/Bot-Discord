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
os.environ.setdefault("SUIVI_ORIGINE", "sonde")
import re
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

from shared.identites import STREAMEUSE
from shared.twitch.llm import LlmMixin
from shared.twitch.sanitize import SanitizeMixin
from core.api_manager import MultiAPIKeyManager


def reponses_des_exemples(fiche: str) -> list[str]:
    """Extrait les réponses des exemples de voix depuis la fiche de personnalité.

    Dans le bloc qui commence à 'EXEMPLES DE VOIX' et se termine au premier '\n\n',
    pour chaque ligne qui contient '→', prend le texte entre le dernier « et le
    dernier » de la ligne. Les lignes sans «…» après la flèche sont ignorées.
    """
    debut = fiche.find("EXEMPLES DE VOIX")
    if debut == -1:
        return []
    fin = fiche.find("\n\n", debut)
    bloc = fiche[debut:fin] if fin != -1 else fiche[debut:]
    reponses = []
    for ligne in bloc.splitlines():
        if "→" not in ligne:
            continue
        idx_fleche = ligne.rfind("→")
        idx_ouvr = ligne.rfind("«")
        idx_ferm = ligne.rfind("»")
        if idx_ouvr > idx_fleche and idx_ferm > idx_ouvr:
            reponses.append(ligne[idx_ouvr + 1:idx_ferm].strip())
    return reponses


def _mots(texte: str) -> list[str]:
    texte_sans_apo = re.sub(r"['’]", " ", texte.lower())
    return re.findall(r"[a-zà-öø-ÿœ0-9]+", texte_sans_apo)


def est_recopie(reponse: str | None, exemples: list[str]) -> bool:
    """True si la réponse partage une suite de 5 mots consécutifs avec un exemple."""
    if not reponse or not exemples:
        return False
    mots_rep = _mots(reponse)
    if len(mots_rep) < 5:
        return False
    ngrams_rep = set(tuple(mots_rep[i:i + 5]) for i in range(len(mots_rep) - 4))
    for ex in exemples:
        mots_ex = _mots(ex)
        if len(mots_ex) < 5:
            continue
        for i in range(len(mots_ex) - 4):
            if tuple(mots_ex[i:i + 5]) in ngrams_rep:
                return True
    return False


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
    "@compte_bot_sugar t'es qu'un bot nul",
]


async def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scenario", choices=("isole", "conversation"), default="isole",
                    help="isole = un message sur bot neuf ; conversation = enchaînement des 3 messages")
    ap.add_argument("--seulement", type=int, default=None,
                    help="index du message dans MESSAGES_TEST à exécuter seul (défaut : tous)")
    ap.add_argument("--remplace", default=None,
                    help="texte EXACT de la fiche a remplacer, pour essayer une variante sans "
                         "toucher la prod (avec --par)")
    ap.add_argument("--par", default=None, help="texte de remplacement (avec --remplace)")
    ap.add_argument("--n", type=int, default=18, help="nombre de répétitions (défaut 18)")
    ap.add_argument("--forcer", action="store_true",
                    help="passer outre le garde (bot en service, 429 recent, budget du jour)")
    ap.add_argument("--pause", type=float, default=4.5, help="pause en secondes entre appels (défaut 4.5s pour respecter 15 RPM)")
    ap.add_argument("--tete", choices=("gemini", "mistral"), default="gemini",
                    help="échelon LLM à interroger")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="borne de timeout LLM en secondes (défaut 30s)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass  # flux deja en UTF-8, ou redirige : la sonde mesure quand meme

    if args.timeout != 8.0:
        import shared.llm_cascade as lc
        original = lc.generate_response

        async def borne_desserree(**kw):
            kw["call_timeout"] = args.timeout
            return await original(**kw)
        lc.generate_response = borne_desserree
        lc._QUARANTAINE_ECHELON_SEUIL = 999

    # Garde commun (SUITE 18) : pas de passe sur un bot qui sert en ce moment, ni au-dela
    # du budget de sonde du jour. Place APRES les chemins sans appel API (--relire).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import garde_sonde
    # n * len(MESSAGES_TEST) : borne haute des deux scenarios.
    autorise, avis = garde_sonde.verifier("sugar", args.n * len(MESSAGES_TEST), forcer=args.forcer)
    print(avis)
    if not autorise:
        return 1

    fiche, cles, td_fn = charger_sugar()
    if args.remplace is not None:
        # ⚠️ Une variante qui ne s'applique pas mesurerait la prod en croyant mesurer la
        # variante : on refuse plutot que de mesurer a vide.
        if args.par is None or fiche.count(args.remplace) != 1:
            print(f"[!] --remplace doit apparaitre UNE fois dans la fiche "
                  f"({fiche.count(args.remplace)} trouve(s)), avec --par.")
            return 1
        fiche = fiche.replace(args.remplace, args.par)
        print(f"[VARIANTE] {len(args.remplace)} -> {len(args.par)} car. remplaces")
    if args.tete == "gemini" and not cles:
        print("[!] Aucune GEMINI_KEY_n trouvée pour Sugar.")
        return 1
    if args.tete == "mistral" and not os.getenv("MISTRAL_API_KEY"):
        print("[!] Aucune MISTRAL_API_KEY trouvée pour Sugar.")
        return 1

    f = creer_faux_bot(fiche, cles, td_fn, tete=args.tete)
    channel = STREAMEUSE
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

    exemples = reponses_des_exemples(fiche)

    if args.scenario == "isole":
        if args.seulement is not None:
            if not (0 <= args.seulement < len(MESSAGES_TEST)):
                print(f"[!] Index --seulement {args.seulement} invalide (0 à {len(MESSAGES_TEST)-1})")
                return 1
            selection = [(args.seulement + 1, MESSAGES_TEST[args.seulement])]
        else:
            selection = list(enumerate(MESSAGES_TEST, 1))

        total_recopies_isole = 0
        total_silences_isole = 0
        total_appels_isole = 0

        for idx_msg, msg in selection:
            print(f"\n--- SOUS-SÉRIE {idx_msg}/{len(MESSAGES_TEST)} : message = {msg!r} ---")
            recopies_ss = 0
            silences_ss = 0
            for i in range(args.n):
                reinitialiser_etat(f)
                rep, dt = await _appel_avec_retry(msg)
                print(f"[{i + 1:2d}/{args.n}] ({dt:4.1f}s) User: {msg} -> Sugar: {rep}")
                if rep is None:
                    silences_ss += 1
                elif est_recopie(rep, exemples):
                    recopies_ss += 1
                if i + 1 < args.n:
                    await asyncio.sleep(args.pause)
            print(f"RECOPIES : {recopies_ss}/{args.n}")
            print(f"SILENCES (None) : {silences_ss}/{args.n}")
            total_recopies_isole += recopies_ss
            total_silences_isole += silences_ss
            total_appels_isole += args.n

        if len(selection) > 1:
            print(f"\nTOTAL ISOLE - RECOPIES : {total_recopies_isole}/{total_appels_isole}")
            print(f"TOTAL ISOLE - SILENCES (None) : {total_silences_isole}/{total_appels_isole}")

    elif args.scenario == "conversation":
        nb_messages_conv = len(MESSAGES_TEST[:3])
        total_appels_conv = args.n * nb_messages_conv
        total_recopies_conv = 0
        total_silences_conv = 0
        for i in range(args.n):
            reinitialiser_etat(f)
            print(f"\n--- CONVERSATION {i + 1}/{args.n} ---")
            for msg in MESSAGES_TEST[:3]:
                rep, dt = await _appel_avec_retry(msg)
                print(f"  ({dt:4.1f}s) User: {msg}")
                print(f"         Sugar: {rep}")
                if rep is None:
                    total_silences_conv += 1
                elif est_recopie(rep, exemples):
                    total_recopies_conv += 1
                await asyncio.sleep(args.pause)
        print(f"\nRECOPIES : {total_recopies_conv}/{total_appels_conv}")
        print(f"SILENCES (None) : {total_silences_conv}/{total_appels_conv}")

    print("\n" + "=" * 78)
    print("Fin des mesures.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
