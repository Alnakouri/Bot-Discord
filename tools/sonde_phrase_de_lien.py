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
    python tools/sonde_phrase_de_lien.py --bot sugar --n 18 --remplace "texte A" --par "texte B"

CE QUE LES OPTIONS ONT SERVI A TRANCHER
---------------------------------------
`--remplace` et `--par` — mesurer une modification du TEXTE COMMUN de l'instruction
sans toucher a `dispatch.py`. Repetables (`action="append"`). Chaque motif doit
apparaitre exactement une fois dans l'instruction transmise au modele, sinon la
sonde s'arrete aussitot pour eviter toute mesure silencieuse du texte non modifie
(SUITE 2-bis).

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

`--brut` — afficher le texte brut exact rendu par le modèle à chaque essai, avant
nettoyage ou troncature par `_borner` (SUITE 6-bis).

`--max-tokens` — écraser la borne de jetons passée à `generate_response` pour
vérifier si une fin de phrase coupée vient du budget LLM (SUITE 6-bis).

`--borne` — remplacer la borne de 200 caractères de `dispatch._borner` pour
vérifier si l'invitation a été tranchée par le nettoyeur (SUITE 6-bis).

`--relire FICHIER` — relire une sortie existante de la sonde et recompter
mécaniquement (premier mot, tutoiement, questions, redites) sans appeler `charger`
(aucun `.env` lu) ni aucun modèle. A servi à recompter SUITE 5 à 8-ter sans rappeler
le modèle (SUITE 9).
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


class ErreurVariante(RuntimeError):
    """Levée quand une substitution demandée via --remplace ne peut pas s'appliquer."""
    pass


def appliquer_variante(f, remplaces, pars):
    """Enveloppe f._ecrire_phrase_de_lien pour substituer des motifs dans l'instruction.

    ⚠️ Avant l'appel au modèle, chaque --remplace doit apparaître EXACTEMENT UNE fois
    dans l'instruction, sinon ErreurVariante est levée (pas de mesure silencieuse d'un
    texte non remplacé).
    """
    if len(remplaces) != len(pars):
        raise ErreurVariante(
            f"Nombre discordant de --remplace ({len(remplaces)}) et --par ({len(pars)})."
        )
    if not remplaces:
        return f

    original_ecrire = f._ecrire_phrase_de_lien

    async def ecrire_avec_remplacement(instruction, system_prompt, cmd):
        texte = instruction
        for r, p in zip(remplaces, pars):
            occ = texte.count(r)
            if occ != 1:
                raise ErreurVariante(
                    f"--remplace doit apparaître EXACTEMENT UNE fois dans l'instruction "
                    f"({occ} trouvé(s)) : {r!r}"
                )
            texte = texte.replace(r, p)
        return await original_ecrire(texte, system_prompt, cmd)

    f._ecrire_phrase_de_lien = ecrire_avec_remplacement
    return f


def enregistrer_bruts(f):
    """Enveloppe f._ecrire_phrase_de_lien pour capturer le texte brut de chaque essai.

    f._bruts est initialisé et vidé à chaque tour comme f._journal.
    """
    bruts = []
    f._bruts = bruts
    original_ecrire = f._ecrire_phrase_de_lien

    async def ecrire_en_notant(instruction, system_prompt, cmd):
        rendu = await original_ecrire(instruction, system_prompt, cmd)
        bruts.append(rendu)
        return rendu

    f._ecrire_phrase_de_lien = ecrire_en_notant
    return f


_TU = re.compile(r"\b(?:tu|te|toi|ton|ta|tes|viens)\b|\bt['’]", re.I)
_EXPRESSIONS_FIGEES = re.compile(r"en veux-tu en voil[àa]", re.I)
_VOUS = re.compile(r"\b(?:vous|votre|vos|venez|rejoignez|passez)\b", re.I)


def compter(phrases: list[str]) -> dict:
    res = {}
    res["n"] = len(phrases)
    pm_counter = collections.Counter()
    for p in phrases:
        m = re.match(r"\W*(\w+)", p)
        if m:
            pm_counter[m.group(1).lower()] += 1
    res["premiers_mots"] = pm_counter

    tuto_count = 0
    melange_count = 0
    for p in phrases:
        p_sans = _EXPRESSIONS_FIGEES.sub("", p)
        if _TU.search(p_sans):
            tuto_count += 1
            if _VOUS.search(p_sans):
                melange_count += 1
    res["tutoiement"] = tuto_count
    res["melange"] = melange_count

    qc = 0
    questions_count = collections.Counter()
    invit_count = collections.Counter()

    for p in phrases:
        if "?" in p:
            avant = p.split("?", 1)[0].strip()
            if len(avant) < 80:
                qc += 1
            questions_count[avant] += 1
            invit_brut = p.split("?", 1)[1]
        else:
            invit_brut = p

        cleaned = re.sub(r"[^\w\s'’\-]", " ", invit_brut, flags=re.UNICODE)
        invit_norm = " ".join(cleaned.lower().split())
        invit_count[invit_norm] += 1

    res["questions_courtes"] = qc
    res["meme_question"] = max(questions_count.values()) if questions_count else 0
    res["meme_invitation"] = invit_count.most_common(1)[0] if invit_count else ("", 0)
    res["discord"] = sum(1 for p in phrases if "discord" in p.lower())
    return res


def resumer(phrases, replis, n, types_phrases=None):
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

    c = compter(phrases)
    total = c["n"]
    top3 = c["premiers_mots"].most_common(3)
    top_str = ", ".join(f"{cnt}x « {mot} »" for mot, cnt in top3) if top3 else "aucun"
    print(f"  premier mot       : {top_str}      (les 3 plus frequents)")
    melange_txt = f"   (dont {c['melange']} melange{'s' if c['melange'] > 1 else ''} tu/vous dans la meme phrase)"
    print(f"  tutoiement        : {c['tutoiement']}/{total}{melange_txt}")
    print(f"  questions < 80 car: {c['questions_courtes']}/{total}  (texte avant le premier « ? »)")
    print(f"  meme question     : {c['meme_question']}x au plus")
    invit_txt, invit_cnt = c["meme_invitation"]
    print(f"  meme invitation   : {invit_cnt}x « {invit_txt} »")
    print(f"  nomme Discord     : {c['discord']}/{total}")

    if types_phrases and any(t for t in types_phrases):
        vus = []
        for t in types_phrases:
            if t and t not in vus:
                vus.append(t)
        for t in vus:
            phrases_t = [p for p, tp in zip(phrases, types_phrases) if tp == t]
            count_t = len(phrases_t)
            mots_t = collections.Counter()
            for p in phrases_t:
                m = re.match(r"\W*(\w+)", p)
                if m:
                    mots_t[m.group(1).lower()] += 1
            top_m = mots_t.most_common(1)
            pm, cnt = top_m[0] if top_m else ("aucun", 0)
            label = f"type {t}"
            print(f"  {label:<18}: {count_t} phrase{'s' if count_t > 1 else ''} ; premier mot {cnt}x « {pm} »")

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
    ap.add_argument("--clause-jeu", default=None,
                    help="clause JEU par-bot a essayer (CLAUSES_JEU_PAR_BOT), sans toucher "
                         "au code de prod. Ne sert que si un jeu est diffuse.")
    ap.add_argument("--force-accroche", action="store_true",
                    help="ajoute ce bot a ACCROCHE_AU_JEU le temps de la mesure")
    ap.add_argument("--fiche", dest="fiche_jeu", default=None,
                    help="fiche IGDB du jeu a donner au modele (LOT 1bis.5). Le faux Helix "
                         "ne connait aucun igdb_id : sans cette option, la mesure se fait "
                         "SANS fiche, comme quand IGDB est muet.")
    ap.add_argument("--remplace", action="append", default=[],
                    help="texte a remplacer dans l'instruction transmise au modele (repetable)")
    ap.add_argument("--par", action="append", default=[],
                    help="texte de substitution associe a --remplace (repetable, meme ordre)")
    ap.add_argument("--brut", action="store_true",
                    help="affiche sous chaque ligne le texte exact rendu par le modèle pour chaque essai")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="écrase max_tokens dans l'appel au modèle (défaut: inchangé)")
    ap.add_argument("--borne", type=int, default=None,
                    help="remplace la borne de troncature maxi dans dispatch._borner")
    ap.add_argument("--relire", default=None, metavar="FICHIER",
                    help="recompter une sortie existante sans appeler charger ni le modèle")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # flux deja en UTF-8, ou redirige : la sonde mesure quand meme

    if args.relire:
        motif = re.compile(r"^\s*\d+\.\s+\[[^\]]*\]\s+(?:\((\w+)\)\s+)?(.*\S)\s*$")
        phrases_relues, replis_relus, types_relus = [], 0, []
        with open(args.relire, "r", encoding="utf-8", errors="replace") as fp:
            for ligne in fp:
                m = motif.match(ligne)
                if not m:
                    continue
                type_opt = m.group(1)
                texte = m.group(2)
                if texte.startswith("<<"):
                    replis_relus += 1
                else:
                    phrases_relues.append(texte)
                    types_relus.append(type_opt)
        resumer(phrases_relues, replis_relus, len(phrases_relues) + replis_relus, types_relus)
        return 0

    if len(args.remplace) != len(args.par):
        print(f"[!] Autant de --par que de --remplace requis ({len(args.remplace)} vs {len(args.par)}).")
        return 1

    if args.timeout != 8.0 or args.max_tokens is not None:
        # On ne retape pas la construction de l'instruction : le VRAI
        # `_generate_link_line` la batit, et on ne desserre que la borne de l'appel
        # et/ou on écrase max_tokens.
        import shared.llm_cascade as lc
        original = lc.generate_response

        async def borne_desserree(**kw):
            if args.timeout != 8.0:
                kw["call_timeout"] = args.timeout
            if args.max_tokens is not None:
                kw["max_tokens"] = args.max_tokens
            return await original(**kw)
        lc.generate_response = borne_desserree

    if args.borne is not None:
        import shared.twitch.dispatch as dispatch_mod
        original_borner = dispatch_mod._borner

        def borner_rehausse(phrase, maxi=200):
            return original_borner(phrase, args.borne)
        dispatch_mod._borner = borner_rehausse

    from shared.twitch.dispatch import DispatchMixin
    if args.force_accroche:
        DispatchMixin.ACCROCHE_AU_JEU = set(DispatchMixin.ACCROCHE_AU_JEU) | {args.bot}
    if args.clause is not None:
        DispatchMixin.CLAUSES_PAR_BOT = dict(DispatchMixin.CLAUSES_PAR_BOT)
        DispatchMixin.CLAUSES_PAR_BOT[args.bot] = args.clause
    if args.clause_jeu is not None:
        DispatchMixin.CLAUSES_JEU_PAR_BOT = dict(DispatchMixin.CLAUSES_JEU_PAR_BOT)
        DispatchMixin.CLAUSES_JEU_PAR_BOT[args.bot] = args.clause_jeu

    fiche, cles = charger(args.bot)
    if args.tete == "gemini" and not cles:
        print(f"[!] aucune GEMINI_KEY_n pour {args.bot} : rien a mesurer.")
        return 1
    if args.tete == "mistral" and not os.getenv("MISTRAL_API_KEY"):
        print(f"[!] aucune MISTRAL_API_KEY pour {args.bot} : rien a mesurer.")
        return 1

    jeu = None if args.sans_jeu else args.jeu
    f = faux_bot(args.bot, fiche, cles, jeu, args.tete)
    if args.fiche_jeu is not None:
        async def fiche_imposee():
            return args.fiche_jeu
        f._fiche_du_jeu = fiche_imposee
    if args.remplace:
        appliquer_variante(f, args.remplace, args.par)
    if args.brut:
        enregistrer_bruts(f)
    print(f"{args.bot} | tete={args.tete} | fiche {len(fiche)} car. | jeu={jeu!r} | "
          f"n={args.n} | borne {args.timeout:g}s"
          + ("  | CLAUSE INJECTEE" if args.clause else "")
          + ("  | CLAUSE JEU INJECTEE" if args.clause_jeu else "")
          + ("  | ACCROCHE FORCEE" if args.force_accroche else "")
          + ("  | FICHE DU JEU" if args.fiche_jeu is not None else "")
          + (f"  | VARIANTE x{len(args.remplace)}" if args.remplace else "")
          + (f"  | MAX-TOKENS {args.max_tokens}" if args.max_tokens is not None else "")
          + (f"  | BORNE {args.borne}" if args.borne is not None else "")
          + ("  | BRUT" if args.brut else ""))
    print("=" * 78)

    phrases, replis, types_phrases = [], 0, []
    for i in range(args.n):
        f._link_lines_cache = {}      # sinon la 2e generation rend la 1re
        del f._journal[:]
        if hasattr(f, "_bruts"):
            del f._bruts[:]
        debut = time.perf_counter()
        try:
            rendu = await f._generate_link_line("discord", "discord", "https://X")
        except ErreurVariante:
            raise
        except Exception as e:
            rendu = f"<<EXCEPTION {type(e).__name__}: {e}>>"
        duree = time.perf_counter() - debut

        type_trouve = None
        for ligne in f._journal:
            m = re.search(r"\(type : (\w+)\)", ligne)
            if m:
                type_trouve = m.group(1)
                break

        if rendu:
            phrase = rendu.replace(" https://X", "")
            phrases.append(phrase)
            types_phrases.append(type_trouve)
        else:
            phrase = "<<repli sur le gabarit fixe>>"
            replis += 1
        prefixe_type = f"({type_trouve}) " if type_trouve else ""
        print(f"{i + 1:3}. [{duree:5.2f}s] {prefixe_type}{phrase}")
        if args.brut and hasattr(f, "_bruts"):
            for b in f._bruts:
                print(f"      ↳ brut : «{b}»")
        for ligne in f._journal:
            if "rejetee" in ligne or ligne.startswith(("ERR", "WARN")):
                print(f"      ↳ {ligne[:150]}")
        if i + 1 < args.n:
            await asyncio.sleep(args.pause)

    resumer(phrases, replis, args.n, types_phrases)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
