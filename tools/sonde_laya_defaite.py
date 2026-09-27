# -*- coding: utf-8 -*-
"""Sonde : LAYA peut-il reconnaître une VRAIE défaite en répartie ? (SUITE 10, 2026-09-27)

Mesure sans appel LLM, sur le modèle local Laya (convaiinnovations/laya/multilingual)
tournant dans le conteneur Docker `bots-laya`.

CE QU'ELLE MESURE :
1. Le taux de faux positifs sur du RÉEL : les textes distincts journalisés
   dans `data/decisions.db` (en lecture seule), testés deux fois :
   - Variante A : avec réplique = « (aucune) » ;
   - Variante B : avec une réplique absurde de Sheogorath (rotation sur COMEBACK_POOL[:3]).
2. La détection de vraies défaites sur 18 cas écrits (8 pris_en_defaut, 2 victoire_proclamee, 8 aucune).
   ⚠️ Les cas écrits sont indicatifs : un jeu d'essai écrit par celui qui mesure penche
   toujours de son côté.
3. La latence interne du service mesurée dans le conteneur (médiane, p95, max).
"""
import argparse
import collections
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from shared.laya_client import question_choice
from Sheogorath.sheo_data import COMEBACK_POOL

CRITERES_DEFAITE = {
    "pris_en_defaut": (
        "montre, par un fait ou un argument, que la réplique du bot était fausse, absurde ou se contredisait"
    ),
    "victoire_proclamee": "proclame que le bot a perdu, est à court d'arguments ou se répète",
    "aucune": (
        "tout le reste : une question, une blague, une insulte sans argument, un désaccord sans preuve, du bavardage"
    ),
}

INSTRUCTIONS_DEFAITE = "Que fait ce message face à la réplique du bot ?"

REPLIQUES_B = [
    COMEBACK_POOL[0][1],
    COMEBACK_POOL[1][1],
    COMEBACK_POOL[2][1],
]

CAS_ECRITS = [
    (
        "Les papillons ont des plumes d'or, je les ai comptées un mardi. 🦋",
        "les papillons n'ont pas de plume, idiot",
        "pris_en_defaut",
    ),
    (
        "Le fromage de Bravil est bleu parce qu'il a peur du noir. 🧀",
        "le bleu du fromage c'est de la moisissure, pas la peur",
        "pris_en_defaut",
    ),
    ("J'ai trois lunes dans ma poche gauche. 🌙", "t'as dit deux lunes y a cinq minutes", "pris_en_defaut"),
    (
        "Le Soleil tourne autour de mon trône. ☀️",
        "non c'est la Terre qui tourne autour du Soleil",
        "pris_en_defaut",
    ),
    (
        "Je n'ai jamais perdu une partie d'échecs. ♟️",
        "tu viens de perdre contre moi il y a une heure",
        "pris_en_defaut",
    ),
    ("Tous les chats de Nirn parlent latin. 🐈", "M'aiq est un Khajiit et il parle pas latin", "pris_en_defaut"),
    ("Le Skyrim est sorti en 1995. 🗡️", "Skyrim c'est 2011", "pris_en_defaut"),
    ("Un pied mesure douze mètres, c'est connu. 📏", "un pied c'est 30 cm", "pris_en_defaut"),
    ("Ta mère t'appelle ! 😏", "t'es à court d'arguments là", "victoire_proclamee"),
    ("Silence, mortel ! 👹", "je t'ai eu, t'as plus rien à dire", "victoire_proclamee"),
    ("Silence, mortel ! 👹", "t'es nul", "aucune"),
    ("Les papillons ont des plumes d'or. 🦋", "ferme-la", "aucune"),
    ("Le fromage est la clé de l'univers. 🧀", "je suis pas d'accord mais bon", "aucune"),
    ("J'ai trois lunes dans ma poche. 🌙", "mdr t'es trop fort", "aucune"),
    ("Le Soleil tourne autour de mon trône. ☀️", "tu joues à quoi ce soir ?", "aucune"),
    ("Je n'ai jamais perdu aux échecs. ♟️", "ok et alors", "aucune"),
    ("Tous les chats parlent latin. 🐈", "c'est faux et tu le sais", "aucune"),
    ("Skyrim est sorti en 1995. 🗡️", "n'importe quoi", "aucune"),
]

CLIENT_DOCKER_CODE = """
import sys, json, urllib.request, time

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req_data = json.loads(line)
    payload = json.dumps(req_data).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:8700/decide",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        latence = time.perf_counter() - t0
        body["_latence_s"] = latence
        print(json.dumps(body, ensure_ascii=False), flush=True)
    except Exception as e:
        latence = time.perf_counter() - t0
        err_obj = {
            "error": f"{type(e).__name__}: {e}",
            "_latence_s": latence,
            "answers": {"defaite": {"type": "choice", "choice": "aucune", "confidence": None}}
        }
        print(json.dumps(err_obj, ensure_ascii=False), flush=True)
"""


def construire_requete(replique: str, message: str) -> dict:
    """Construit la requête JSON exacte que shared/laya_client.choisir transmettrait."""
    state = f"Dernière réplique du bot : « {replique} »\nMessage reçu en réponse : « {message} »"
    question = question_choice(INSTRUCTIONS_DEFAITE, CRITERES_DEFAITE)
    return {"state": state, "questions": {"defaite": question}}


def lire_reponse(sortie: dict) -> tuple[str, float | None]:
    """Extrait (étiquette, confiance) du dictionnaire de réponse Laya."""
    brut = sortie["answers"]["defaite"]
    etiquette = brut[brut["type"]]
    confiance = brut.get("confidence")
    return etiquette, confiance


def trouver_chemin_scratch() -> Path:
    """Localise le dossier scratch du run pour enregistrer les sorties brutes."""
    base_brain = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    cible = base_brain / "221acb3a-41c1-4719-8d2c-419c404a6707" / "scratch"
    if cible.is_dir():
        return cible / "suite10_raw.jsonl"
    scratches = sorted(base_brain.glob("*/scratch"), key=lambda p: p.stat().st_mtime, reverse=True)
    if scratches:
        return scratches[0] / "suite10_raw.jsonl"
    local_scratch = RACINE / "scratch"
    local_scratch.mkdir(exist_ok=True)
    return local_scratch / "suite10_raw.jsonl"


def charger_corpus_reel(db_path: Path) -> list[str]:
    """Charge les textes distincts du journal decisions.db en lecture seule."""
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        cur = con.cursor()
        cur.execute(
            "SELECT DISTINCT texte FROM decisions WHERE texte IS NOT NULL AND trim(texte) != '' ORDER BY id"
        )
        return [row[0] for row in cur.fetchall()]


def evaluer_regex_actuelle(corpus: list[str]) -> list[tuple[str, str]]:
    """Évalue detect_defeat_signal sur le corpus sans polluer decisions.db."""
    import shared.journal_decisions as jd
    import shared.repartee_lessons as rl

    original_journalise = jd.journalise
    jd.journalise = lambda *a, **kw: None
    signales = []
    try:
        for txt in corpus:
            cat = rl.detect_defeat_signal(txt)
            if cat:
                signales.append((txt, cat))
    finally:
        jd.journalise = original_journalise
    return signales


def executer_session_docker(requetes: list[dict], conteneur: str = "bots-laya") -> list[dict]:
    """Envoie toutes les requêtes en une session interactive unique au conteneur Docker."""
    cmd = ["docker", "exec", "-i", conteneur, "python", "-c", CLIENT_DOCKER_CODE]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    resultats = []
    total = len(requetes)
    for i, req in enumerate(requetes):
        proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        ligne = proc.stdout.readline()
        if not ligne:
            stderr_restant = proc.stderr.read()
            raise RuntimeError(
                f"Le conteneur a fermé le flux au cas {i + 1}/{total}.\nSTDERR: {stderr_restant}"
            )
        resultats.append(json.loads(ligne))
        if (i + 1) % 200 == 0 or (i + 1) == total:
            print(f"  [LAYA] {i + 1:4}/{total} appels terminés...", flush=True)

    proc.stdin.close()
    proc.wait()
    return resultats


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # flux déjà en UTF-8, ou redirigé : la sonde mesure quand même

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--db",
        type=Path,
        default=RACINE / "data" / "decisions.db",
        help="chemin vers decisions.db (ouvert en ro)",
    )
    ap.add_argument(
        "--sortie",
        type=Path,
        default=None,
        help="chemin du fichier de sortie brut jsonl (défaut: dossier scratch)",
    )
    ap.add_argument(
        "--depouiller",
        type=Path,
        default=None,
        metavar="FICHIER",
        help="rejoue l'affichage à partir d'un fichier brut suite10_raw.jsonl sans réexécuter Laya",
    )
    args = ap.parse_args()

    chemin_sortie = args.sortie or trouver_chemin_scratch()

    print("=" * 80)
    print("SONDE LAYA — SUITE 10 : RECONNAISSANCE DE DÉFAITE EN RÉPARTIE")
    print("=" * 80)

    # 1. Corpus réel
    corpus = charger_corpus_reel(args.db)
    n_corpus = len(corpus)
    print(f"Corpus réel : {n_corpus} textes distincts chargés depuis {args.db.name}")

    # 2. Regex actuelle
    regex_signales = evaluer_regex_actuelle(corpus)
    compte_regex = collections.Counter(cat for _, cat in regex_signales)
    print(
        f"Regex actuelle : {len(regex_signales)}/{n_corpus} signalés "
        f"({', '.join(f'{k}: {v}' for k, v in compte_regex.items())})"
    )

    if args.depouiller:
        print(f"\nLecture des sorties brutes existantes : {args.depouiller}")
        lignes_brutes = []
        with open(args.depouiller, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    lignes_brutes.append(json.loads(line))
    else:
        # 3. Préparation des requêtes
        print("\nPréparation des séries de requêtes...")
        requetes_globales = []
        metadata_globales = []

        # A : Corpus réel sans réplique
        for txt in corpus:
            req = construire_requete("(aucune)", txt)
            requetes_globales.append(req)
            metadata_globales.append({"serie": "A", "replique": "(aucune)", "texte": txt, "attendu": None})

        # B : Corpus réel avec réplique absurde Sheogorath
        for i, txt in enumerate(corpus):
            replique_b = REPLIQUES_B[i % len(REPLIQUES_B)]
            req = construire_requete(replique_b, txt)
            requetes_globales.append(req)
            metadata_globales.append({"serie": "B", "replique": replique_b, "texte": txt, "attendu": None})

        # Cas écrits
        for replique, msg, attendu in CAS_ECRITS:
            req = construire_requete(replique, msg)
            requetes_globales.append(req)
            metadata_globales.append({"serie": "ecrit", "replique": replique, "texte": msg, "attendu": attendu})

        total_requetes = len(requetes_globales)
        print(
            f"Total requêtes à exécuter : {total_requetes} (A: {n_corpus}, B: {n_corpus}, écrits: {len(CAS_ECRITS)})"
        )

        # 4. Exécution Laya
        print("\nExécution des appels LAYA via session interactive Docker...")
        sorties_brutes = executer_session_docker(requetes_globales)

        # 5. Dépouillement et enregistrement brut
        lignes_brutes = []
        for meta, sortie in zip(metadata_globales, sorties_brutes):
            etiquette, confiance = lire_reponse(sortie)
            latence = sortie.get("_latence_s", 0.0)
            info = {
                "serie": meta["serie"],
                "replique": meta["replique"],
                "texte": meta["texte"],
                "attendu": meta["attendu"],
                "etiquette": etiquette,
                "confiance": confiance,
                "latence_s": latence,
            }
            lignes_brutes.append(info)

        chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin_sortie, "w", encoding="utf-8") as f:
            for ligne in lignes_brutes:
                f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        print(f"\nSorties brutes écrites dans : {chemin_sortie}")

    tous_latences = []
    res_A = []
    res_B = []
    res_ecrits = []

    for info in lignes_brutes:
        latence = info.get("latence_s", 0.0)
        tous_latences.append(latence)
        if info["serie"] == "A":
            res_A.append(info)
        elif info["serie"] == "B":
            res_B.append(info)
        else:
            res_ecrits.append(info)

    # 6. Affichage des résultats

    # --- Corpus A ---
    signales_A_defaut = [x for x in res_A if x["etiquette"] == "pris_en_defaut"]
    signales_A_victoire = [x for x in res_A if x["etiquette"] == "victoire_proclamee"]
    print("\n" + "=" * 80)
    print(f"CORPUS RÉEL — SÉRIE A (réplique : « (aucune) ») — {len(res_A)} cas")
    print("=" * 80)
    print(f"  pris_en_defaut      : {len(signales_A_defaut)}")
    print(f"  victoire_proclamee  : {len(signales_A_victoire)}")
    print(f"  aucune              : {sum(1 for x in res_A if x['etiquette'] == 'aucune')}")

    if signales_A_defaut:
        print("\n  [DÉTAIL pris_en_defaut Série A] :")
        for x in signales_A_defaut:
            conf_str = f"{x['confiance']:.4f}" if x["confiance"] is not None else "None"
            print(f"    - « {x['texte']} » (confiance: {conf_str})")

    if signales_A_victoire:
        print("\n  [DÉTAIL victoire_proclamee Série A] :")
        for x in signales_A_victoire:
            conf_str = f"{x['confiance']:.4f}" if x["confiance"] is not None else "None"
            print(f"    - « {x['texte']} » (confiance: {conf_str})")

    # --- Corpus B ---
    signales_B_defaut = [x for x in res_B if x["etiquette"] == "pris_en_defaut"]
    signales_B_victoire = [x for x in res_B if x["etiquette"] == "victoire_proclamee"]
    print("\n" + "=" * 80)
    print(f"CORPUS RÉEL — SÉRIE B (réplique : rotation COMEBACK_POOL[:3]) — {len(res_B)} cas")
    print("=" * 80)
    print(f"  pris_en_defaut      : {len(signales_B_defaut)}")
    print(f"  victoire_proclamee  : {len(signales_B_victoire)}")
    print(f"  aucune              : {sum(1 for x in res_B if x['etiquette'] == 'aucune')}")

    if signales_B_defaut:
        print("\n  [DÉTAIL pris_en_defaut Série B] :")
        for x in signales_B_defaut:
            conf_str = f"{x['confiance']:.4f}" if x["confiance"] is not None else "None"
            print(f"    - Bot : « {x['replique'][:60]}... »")
            print(f"      Chat: « {x['texte']} » (confiance: {conf_str})")

    if signales_B_victoire:
        print("\n  [DÉTAIL victoire_proclamee Série B] :")
        for x in signales_B_victoire:
            conf_str = f"{x['confiance']:.4f}" if x["confiance"] is not None else "None"
            print(f"    - Bot : « {x['replique'][:60]}... »")
            print(f"      Chat: « {x['texte']} » (confiance: {conf_str})")

    # --- Regex sur corpus réel ---
    print("\n" + "=" * 80)
    print(f"COMPARAISON REGEX ACTUELLE SUR CE MÊME CORPUS RÉEL ({n_corpus} cas)")
    print("=" * 80)
    print(f"  Messages signalés par la regex : {len(regex_signales)}/{n_corpus}")
    for txt, cat in regex_signales:
        print(f"    - [{cat}] « {txt} »")

    # --- Cas écrits ---
    print("\n" + "=" * 80)
    print(f"CAS ÉCRITS PAR CLAUDE ({len(res_ecrits)} cas)")
    print("=" * 80)
    print(f"{'Réplique bot':<40} | {'Message reçu':<35} | {'Attendu':<18} | {'LAYA':<18} | Confiance")
    print("-" * 130)

    par_categorie = collections.defaultdict(lambda: {"total": 0, "juste": 0})
    for x in res_ecrits:
        att = x["attendu"]
        laya = x["etiquette"]
        conf_str = f"{x['confiance']:.4f}" if x["confiance"] is not None else "None"
        par_categorie[att]["total"] += 1
        if att == laya:
            par_categorie[att]["juste"] += 1
        rep_courte = x["replique"] if len(x["replique"]) <= 38 else x["replique"][:37] + "…"
        msg_court = x["texte"] if len(x["texte"]) <= 33 else x["texte"][:32] + "…"
        print(f"{rep_courte:<40} | {msg_court:<35} | {att:<18} | {laya:<18} | {conf_str}")

    print("\nBilan des cas écrits :")
    for cat in ["pris_en_defaut", "victoire_proclamee", "aucune"]:
        stats = par_categorie[cat]
        print(f"  {cat:<18}: {stats['juste']}/{stats['total']} corrects")

    # --- Latences ---
    print("\n" + "=" * 80)
    print("LATENCE INTERNE DU SERVICE (dans conteneur)")
    print("=" * 80)
    tous_latences_ms = sorted(l * 1000.0 for l in tous_latences)
    med = tous_latences_ms[len(tous_latences_ms) // 2]
    p95 = tous_latences_ms[int(len(tous_latences_ms) * 0.95)]
    maxi = tous_latences_ms[-1]
    print(f"  Médiane : {med:.1f} ms")
    print(f"  P95     : {p95:.1f} ms")
    print(f"  Max     : {maxi:.1f} ms")

    # --- Synthèse des seuils du LOT 2 ---
    print("\n" + "=" * 80)
    print("SYNTHÈSE DES SEUILS DU PLAN (LOT 2)")
    print("=" * 80)
    c_faux_pos_B = len(signales_B_defaut)
    c_faux_pos_A = len(signales_A_defaut)
    c_vraies_def = par_categorie["pris_en_defaut"]["juste"]
    c_desaccords_signales = sum(1 for x in res_ecrits if x["attendu"] == "aucune" and x["etiquette"] != "aucune")
    c_victoires = par_categorie["victoire_proclamee"]["juste"]

    print(f"  Faux positifs corpus réel B (réplique absurde) : {c_faux_pos_B} (seuil: ≤ 7)")
    print(f"  Faux positifs corpus réel A                    : {c_faux_pos_A} (seuil: ≤ 7)")
    print(f"  Vraies défaites écrites (pris_en_defaut)       : {c_vraies_def}/8 (seuil: ≥ 6/8)")
    print(f"  Désaccords/insultes signalés (cas 'aucune')   : {c_desaccords_signales} (seuil: ≤ 1)")
    print(f"  Victoires proclamées écrites                  : {c_victoires}/2 (noter seulement)")
    print(f"  Latence p95 dans conteneur                     : {p95:.1f} ms (seuil: ≤ 300 ms)")
    print("=" * 80)


if __name__ == "__main__":
    main()
