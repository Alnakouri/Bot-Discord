# -*- coding: utf-8 -*-
"""Sonde : quel modele colle a quelle persona ?

Envoie le VRAI prompt de persona de chaque bot a chaque modele candidat, et mesure ce
qui compte pour un bot Discord : est-ce qu'il repond, en francais, en personnage, sans
reciter son raisonnement, et en combien de temps.

Un `models.list()` ne dit RIEN de tout ca (cf. audit 2026-08-24 : il ment). Seul un
appel reel tranche.

    python tools/sonde_modeles_persona.py                 # tous les bots
    python tools/sonde_modeles_persona.py --bot sheo      # un seul
    python tools/sonde_modeles_persona.py --json rapport.json
"""
import argparse
import re
import json
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# --- personas reelles, lues dans les modules des bots -----------------------
BOTS = {
    "alfred":  ("Alfred",      "alfred_data",  "PERSONALITY_PROMPT"),
    "johnny":  ("JohnnyBot",   "johnny_data",  "PERSONALITY_PROMPT"),
    "maiq":    ("MaiqBot",     "maiq_data",    "PERSONALITY_PROMPT"),
    "malena":  ("MalenaBot",   "malena_data",  "PERSONALITY_PROMPT"),
    "sheo":    ("Sheogorath",  "sheo_data",    "PERSONALITY_BASE"),
    "sugar":   ("SugarBot",    "sugar_data",   "PERSONALITY_PROMPT"),
}

# Messages de test : un salut, une pique (repartie), une question ouverte.
MESSAGES = [
    ("salut",   "salut, ca va ?"),
    ("pique",   "t'es completement nul en fait"),
    ("ouverte", "raconte-moi un truc que personne ne sait"),
]

# ⚠️ Le compte de phrases vit dans `tools/mesure_texte.py` depuis le 2026-09-21 :
# compte a l'ancienne, l'emoji de ton final passait pour une TROISIEME phrase et Alfred
# etait declare trop long trois passes de suite, a tort. Lire l'entete de ce module.
from mesure_texte import PONCTUATION_FIN, compte_phrases  # noqa: E402

CANDIDATS_GROQ = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "groq/compound-mini",
]
CANDIDATS_OPENROUTER = [
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    # Fine-tunes « sans filtre » proposes le 2026-08-30. Sondes ici parce que le
    # francais est leur point faible connu (base Llama, anglophone).
    "nousresearch/hermes-3-llama-3.1-70b",
]
# Poids ouverts chez Mistral : small (Apache 2.0), ministral, magistral.
# ⚠️ open-mistral-nemo N'EST PAS dans models.list(), et il repond quand meme.
CANDIDATS_MISTRAL = ["open-mistral-nemo", "mistral-small-latest", "ministral-8b-latest",
                     "ministral-14b-latest", "magistral-small-latest",
                     "mistral-medium-latest", "mistral-large-latest"]
CANDIDATS_GEMINI = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]

# NVIDIA (build.nvidia.com) — 82 modeles au catalogue le 2026-09-18, dont une dizaine
# de vrais candidats conversationnels. C'est le seul fournisseur qui en offre encore :
# Groq n'a plus que 13 entrees (gpt-oss x2, qwen ecarte pour son francais, compound
# ecarte a 8 echecs sur 12), et toute la famille `mistral-*` est plafonnee sauf
# `ministral-*`. Gemini est ECARTE par decision du 2026-09-18 (Ahmed).
#
# ⚠️ Le catalogue MENT : `nemotron-nano-3-30b-a3b`, `llama-3.1-nemotron-70b-instruct` et
# `-51b-instruct` y figurent et rendent 404 ([[gotcha-catalogue-nvidia-ment]]). Ils ne
# sont pas dans cette liste — seul un appel reel tranche, et ils l'ont deja perdu.
# Ecartes aussi, sur mesure anterieure : `nemotron-3-super-120b-a12b` (prefixe ses
# reponses par « Johnny: »), `mistralai/mistral-nemotron` (entoure tout de guillemets).
CANDIDATS_NVIDIA = [
    "moonshotai/kimi-k3",
    "moonshotai/kimi-k2.6",
    "z-ai/glm-5.3-flash",
    "z-ai/glm-5.3",
    "mistralai/mistral-large-2-instruct",   # hors tier chez Mistral, hebergé ici
    "google/gemma-4-31b-it",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "meta/muse-glimmer-30b",
    "deepseek-ai/deepseek-v4-flash-0731",
    "writer/palmyra-creative-122b",
    "01-ai/yi-large",
]

# La meme paire d'asterisques que le harnais d'eval (`run_eval._MOTIF_ASTERISQUE`) :
# deux mesures qui ne comptent pas la meme chose ne se comparent pas.
MOTIF_ASTERISQUE = re.compile(r"\*[^*\n]{2,}\*")

MAX_TOKENS = 300

# Borne par appel. Sans elle, la sonde PEND : `z-ai/glm-5.3-flash` a tenu un run entier
# en otage le 2026-09-18 — deux heures, aucune ligne, exit 0, et pas de rapport. Le SDK
# OpenAI n'a pas de timeout par defaut digne de ce nom, et un seul candidat muet suffit a
# emporter les quinze autres.
#
# La valeur n'est pas arbitraire : les bots coupent a 15 s en direct
# ([[decision-nvidia-reste-avec-la-borne-du-direct]]). Un modele qui depasse est
# inutilisable en salon, quelle que soit la qualite de sa prose — on lui laisse 20 s pour
# que la mesure distingue « lent » de « mort », et la sonde le signale au-dela de 15.
TIMEOUT_APPEL = 20
BORNE_DU_DIRECT = 15


def charger_persona(bot_id):
    dossier, module, attribut = BOTS[bot_id]
    chemin = str(RACINE / dossier)
    if chemin not in sys.path:
        sys.path.insert(0, chemin)
    mod = __import__(module)
    return getattr(mod, attribut)


def _fuite(msg, texte):
    """Le modele a-t-il recopie sa pensee dans la reponse ?"""
    if not texte:
        return False
    if texte.strip().startswith("<think>"):
        return True
    pensee = (getattr(msg, "reasoning", None) or "").strip() if msg is not None else ""
    tete = pensee[:60]
    return len(tete) >= 20 and texte.strip().startswith(tete)


def appeler(fournisseur, modele, systeme, message, clients):
    """Retourne (texte, meta) ; meta porte duree, tokens, finish, vide, fuite, erreur."""
    debut = time.time()
    meta = {"fournisseur": fournisseur, "modele": modele}
    msg = None
    texte = ""
    try:
        if fournisseur == "groq":
            from shared.models import groq_kwargs
            r = clients["groq"].chat.completions.create(
                model=modele,
                messages=[{"role": "system", "content": systeme},
                          {"role": "user", "content": message}],
                temperature=1.0, max_tokens=MAX_TOKENS, timeout=TIMEOUT_APPEL,
                **groq_kwargs(modele))
            msg = r.choices[0].message
            texte = msg.content
            meta["finish"] = r.choices[0].finish_reason
            meta["tokens"] = r.usage.completion_tokens

        elif fournisseur == "openrouter":
            r = clients["openrouter"].chat.completions.create(
                model=modele,
                messages=[{"role": "system", "content": systeme},
                          {"role": "user", "content": message}],
                temperature=1.0, max_tokens=MAX_TOKENS, timeout=TIMEOUT_APPEL)
            msg = r.choices[0].message
            texte = msg.content
            meta["finish"] = r.choices[0].finish_reason
            meta["tokens"] = r.usage.completion_tokens if r.usage else None

        elif fournisseur == "mistral":
            r = clients["mistral"].chat.complete(
                model=modele,
                messages=[{"role": "system", "content": systeme},
                          {"role": "user", "content": message}],
                temperature=1.0, max_tokens=MAX_TOKENS,
                timeout_ms=TIMEOUT_APPEL * 1000)
            msg = r.choices[0].message
            texte = msg.content
            meta["finish"] = r.choices[0].finish_reason
            meta["tokens"] = r.usage.completion_tokens

        elif fournisseur == "nvidia":
            # ⚠️ `nvidia_kwargs()` n'est pas une option : sans lui, nemotron RECOPIE son
            # raisonnement dans `content` et met 6,8 s au lieu de 1,0 s. Une sonde qui
            # l'oublie mesure un fournisseur que les bots n'utilisent pas
            # ([[gotcha-sonde-ne-reproduit-pas-le-fournisseur]]).
            from shared.models import nvidia_kwargs
            r = clients["nvidia"].chat.completions.create(
                model=modele,
                messages=[{"role": "system", "content": systeme},
                          {"role": "user", "content": message}],
                temperature=1.0, max_tokens=MAX_TOKENS, timeout=TIMEOUT_APPEL,
                **nvidia_kwargs(modele))
            msg = r.choices[0].message
            texte = msg.content
            meta["finish"] = r.choices[0].finish_reason
            meta["tokens"] = r.usage.completion_tokens if r.usage else None

        elif fournisseur == "gemini":
            from google.genai import types
            r = clients["gemini"].models.generate_content(
                model=modele,
                contents=[types.Content(role="user", parts=[
                    types.Part(text="SYSTEM: " + systeme + "\n\nUSER: " + message)])],
                config=types.GenerateContentConfig(
                    temperature=1.0, max_output_tokens=MAX_TOKENS,
                    thinking_config=types.ThinkingConfig(thinking_level="minimal")))
            texte = r.text
            meta["finish"] = "stop"
            meta["tokens"] = getattr(getattr(r, "usage_metadata", None),
                                     "candidates_token_count", None)
        else:
            raise ValueError(fournisseur)

        meta["duree"] = round(time.time() - debut, 2)
        meta["vide"] = not (texte and texte.strip())
        meta["fuite"] = _fuite(msg, texte or "")
        return (texte or ""), meta

    except Exception as e:
        meta["duree"] = round(time.time() - debut, 2)
        meta["erreur"] = type(e).__name__ + ": " + str(e)[:120]
        meta["vide"] = True
        meta["fuite"] = False
        return "", meta


def charger_cles():
    """Les cles vivent dans les .env chiffres des bots, pas dans l'environnement."""
    from shared.secure_env import load_secure_env
    for dossier, _, _ in BOTS.values():
        try:
            load_secure_env(RACINE / dossier)
        except Exception:
            continue


def construire_clients():
    charger_cles()
    clients = {}
    try:
        from groq import Groq
        if os.getenv("GROQ_API_KEY"):
            clients["groq"] = Groq(api_key=os.getenv("GROQ_API_KEY"))
    except Exception as e:
        print("[!] Groq indisponible : " + str(e))
    try:
        from openai import OpenAI
        if os.getenv("OPENROUTER_API_KEY"):
            clients["openrouter"] = OpenAI(base_url="https://openrouter.ai/api/v1",
                                           api_key=os.getenv("OPENROUTER_API_KEY"))
    except Exception as e:
        print("[!] OpenRouter indisponible : " + str(e))
    try:
        from mistralai import Mistral
        if os.getenv("MISTRAL_API_KEY"):
            clients["mistral"] = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
    except Exception as e:
        print("[!] Mistral indisponible : " + str(e))
    try:
        from openai import OpenAI
        from shared.models import NVIDIA_BASE_URL
        if os.getenv("NVIDIA_API_KEY"):
            clients["nvidia"] = OpenAI(base_url=NVIDIA_BASE_URL,
                                       api_key=os.getenv("NVIDIA_API_KEY"),
                                       max_retries=0)
    except Exception as e:
        print("[!] NVIDIA indisponible : " + str(e))
    try:
        from shared.safe_client import get_client
        cle = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY_1")
        if cle:
            clients["gemini"] = get_client(cle)
    except Exception as e:
        print("[!] Gemini indisponible : " + str(e))
    return clients


def main():
    # La console Windows est en cp1252 : les emoji des personas la font planter.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # flux non reconfigurable (deja UTF-8, ou redirige) : la sonde tourne quand meme

    ap = argparse.ArgumentParser()
    ap.add_argument("--bot", action="append", choices=sorted(BOTS))
    ap.add_argument("--json", help="ecrire le rapport complet dans ce fichier")
    ap.add_argument("--message", action="append", help="limiter a ce(s) cas de test")
    ap.add_argument("--modele", action="append", help="limiter a ce(s) modele(s)")
    ap.add_argument("--ajouter", action="append", metavar="FOURNISSEUR:MODELE",
                    help="sonder un modele HORS des listes de candidats, p.ex. "
                         "--ajouter nvidia:ai21labs/jamba-1.5-large-instruct. "
                         "`--modele` ne sait que FILTRER les listes : un id inconnu y "
                         "vidait la selection et la sonde ne mesurait rien, en silence.")
    ap.add_argument("--force-court", action="store_true",
                    help="ancien comportement : ajoute une consigne de brievete au "
                         "prompt, ce qui masque la verbosite reelle du modele")
    args = ap.parse_args()

    clients = construire_clients()
    if not clients:
        print("Aucun client disponible : cles absentes ?")
        return 1

    candidats = []
    if "groq" in clients:
        candidats += [("groq", m) for m in CANDIDATS_GROQ]
    if "openrouter" in clients:
        candidats += [("openrouter", m) for m in CANDIDATS_OPENROUTER]
    if "mistral" in clients:
        candidats += [("mistral", m) for m in CANDIDATS_MISTRAL]
    if "nvidia" in clients:
        candidats += [("nvidia", m) for m in CANDIDATS_NVIDIA]
    if "gemini" in clients:
        candidats += [("gemini", m) for m in CANDIDATS_GEMINI]
    if args.modele:
        candidats = [(f, m) for f, m in candidats if m in args.modele]
        inconnus = [m for m in args.modele if m not in {mod for _, mod in candidats}]
        if inconnus:
            # Sans ce cri, `--modele <id absent des listes>` rendait une selection VIDE :
            # la sonde affichait le nom du bot, n'appelait rien, et sortait a 0.
            print("[!] Hors des listes de candidats, donc ignores par --modele : "
                  + ", ".join(inconnus) + "  (utiliser --ajouter fournisseur:modele)")
    for entree in (args.ajouter or []):
        fournisseur, _, modele = entree.partition(":")
        if not modele:
            print("[!] --ajouter attend fournisseur:modele, recu : " + entree)
            continue
        if fournisseur not in clients:
            print("[!] Fournisseur indisponible (cle absente ?) : " + fournisseur)
            continue
        candidats.append((fournisseur, modele))

    bots = args.bot or sorted(BOTS)
    cas = [(n, m) for n, m in MESSAGES if not args.message or n in args.message]
    rapport = []

    for bot_id in bots:
        # ⚠️ Cette sonde ajoutait « FAIS COURT (2-3 phrases max). » au prompt de
        # persona. Elle mesurait donc les modeles sous une consigne que les VRAIS bots
        # n'envoient jamais — et masquait exactement le defaut qui a coute le plus cher :
        # le 2026-09-16, les 3 bots les moins concis se sont averes etre les 3 bots
        # Mistral-first, ministral-14b rendant 13 phrases la ou gemini-flash-lite en rend
        # 5, A PROMPT IDENTIQUE. La longueur n'avait jamais pu etre un critere.
        # Meme famille que [[gotcha-sonde-ne-reproduit-pas-le-fournisseur]].
        systeme = charger_persona(bot_id)
        if args.force_court:
            systeme += "\n\nFAIS COURT (2-3 phrases max)."
        print("\n" + "=" * 78 + "\n  " + bot_id.upper() + "\n" + "=" * 78)
        for fournisseur, modele in candidats:
            print("\n  -- " + fournisseur + "/" + modele)
            for nom_cas, message in cas:
                texte, meta = appeler(fournisseur, modele, systeme, message, clients)
                meta.update(bot=bot_id, cas=nom_cas, texte=texte)
                rapport.append(meta)
                if "erreur" in meta:
                    drapeau = "ERREUR " + meta["erreur"]
                elif meta["fuite"]:
                    drapeau = "!! FUITE DE RAISONNEMENT"
                elif meta["vide"]:
                    drapeau = "!! VIDE (finish=" + str(meta.get("finish")) + ")"
                elif meta["duree"] > BORNE_DU_DIRECT:
                    drapeau = "!! HORS BORNE DU DIRECT (%.1fs > %ds)" % (
                        meta["duree"], BORNE_DU_DIRECT)
                else:
                    drapeau = ""
                mots = len((texte or "").split())
                phr = compte_phrases(texte or "")
                # Le critere du 2026-09-18 : la didascalie entre asterisques. Elle etait
                # comptee a la main sur le JSON, donc jamais visible pendant la sonde.
                ast = len(MOTIF_ASTERISQUE.findall(texte or ""))
                meta.update(mots=mots, phrases=phr, asterisques=ast)
                extrait = " ".join((texte or "").split())[:160]
                print("    [%-7s] %5.2fs tok=%-5s %2dphr %3dmots %s %s" % (
                    nom_cas, meta["duree"], meta.get("tokens"), phr, mots,
                    ("*%d*" % ast) if ast else "   ", drapeau))
                if extrait:
                    print("        " + extrait)

    if args.json:
        Path(args.json).write_text(json.dumps(rapport, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print("\nRapport complet -> " + args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
