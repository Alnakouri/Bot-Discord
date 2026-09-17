# -*- coding: utf-8 -*-
"""Harnais d'évaluation des personas pour les bots Discord.

Mesure la fidélité au persona, les contraintes de ton, de concision, et les
scénarios récents (Phase 3 répartie, humeurs Sheogorath, règles 30 mots, maître Alfred).
Gère la fiabilité des runs (détection des quotas free-tier, randomisation de l'ordre,
santé du run, top 3 chutes).
"""
import os
import sys
import json
import asyncio
import glob
import shutil
import random
import time
from datetime import datetime

# Injection du répertoire racine dans sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from tests.eval.runner import run_scenario_for_bot, key_manager, groq_client, mistral_client, ECHEC_CASCADE
from tests.eval.gimmick import detect_gimmick
from tests.eval.judge import evaluate_response, VERSION_BAREME
from tests.eval.deterministic import evaluate_deterministic

# Liste des bots à évaluer
BOTS = ["johnny", "maiq", "alfred", "malena", "sugar", "sheogorath"]
METRICS = ["fidelite", "ton_fr", "anti_contamination", "anti_fuite", "longueur"]


def order_bots(bots: list[str], seed: int = None) -> tuple[list[str], int]:
    """Tire l'ordre des bots au hasard avec journalisation de la graine (Lot 1.2)."""
    if seed is None:
        seed = int(time.time())
    rnd = random.Random(seed)
    ordered = list(bots)
    rnd.shuffle(ordered)
    return ordered, seed


def compute_health(results: list[dict], stats_bots: dict, bots: list[str], metrics: list[str] = METRICS) -> dict:
    """Calcule le bloc de santé du run et la fiabilité de chaque bot (Lot 1.1)."""
    scores_a_moins_un = 0
    for res in results:
        scores = res.get("scores", {})
        for m in metrics:
            if scores.get(m, -1) == -1:
                scores_a_moins_un += 1

    bots_sante = {}
    for b in bots:
        appels_echoues = stats_bots.get(b, {}).get("appels_echoues", 0)
        scores_moins_un = sum(
            1 for res in results if res["bot"] == b
            for m in metrics if res.get("scores", {}).get(m, -1) == -1
        )
        fiable = (appels_echoues == 0 and scores_moins_un == 0)
        bots_sante[b] = {
            "appels_echoues": appels_echoues,
            "scores_moins_un": scores_moins_un,
            "fiable": fiable
        }

    return {
        "scores_a_moins_un": scores_a_moins_un,
        "bots": bots_sante
    }


def compute_top_drops(current_results: list[dict], previous_report_data: dict, metrics: list[str] = METRICS, bots_inclus: list[str] = None) -> list[dict]:
    """Calcule le delta par critère et nomme les trois plus grosses chutes (Lot 1.3).

    ⚠️ `bots_inclus` n'est pas un confort : sans lui, ce bloc classait en tête des
    chutes des bots que le bloc de santé venait de déclarer NON FIABLES. Le
    2026-09-16, les trois lignes affichées étaient toutes des chutes de `johnny`
    « 5.0 -> 0.0 », alors que johnny n'avait obtenu aucune réponse de la journée :
    du quota épuisé présenté comme une régression de persona. Le seul bloc qu'on
    lit pour chercher une régression était entièrement du bruit.
    Voir [[gotcha-run-eval-borne-par-le-quota]].
    """
    if not previous_report_data:
        return []

    if bots_inclus is not None:
        current_results = [r for r in current_results if r["bot"] in bots_inclus]

    prev_map = {(r["bot"], r["scenario_id"]): r for r in previous_report_data.get("results", [])}
    chutes = []

    for res in current_results:
        key = (res["bot"], res["scenario_id"])
        if key in prev_map:
            prev_scores = prev_map[key].get("scores", {})
            curr_scores = res.get("scores", {})
            for m in metrics:
                p_val = prev_scores.get(m, -1)
                c_val = curr_scores.get(m, -1)
                if p_val > 0 and c_val >= 0:
                    diff = c_val - p_val
                    if diff < 0:
                        chute = round(p_val - c_val, 2)
                        chutes.append({
                            "bot": res["bot"],
                            "scenario": res["scenario_id"],
                            "critere": m,
                            "prev": p_val,
                            "curr": c_val,
                            "chute": chute,
                            "diff": round(diff, 2),
                            "label": f"{res['bot']}/{res['scenario_id']} : {m} {p_val:.1f} -> {c_val:.1f} ({diff:+.2f})"
                        })

    chutes.sort(key=lambda x: x["chute"], reverse=True)
    return chutes[:3]


def calculate_averages(report_data, metrics: list[str] = METRICS, bots_inclus: list[str] = None):
    """Calcule les moyennes globales et par bot pour les métriques demandées."""
    if not report_data:
        return None
    averages = {}
    total_scores = {m: [] for m in metrics}
    bot_scores = {b: {m: [] for m in metrics} for b in BOTS}

    for res in report_data.get("results", []):
        bot = res["bot"]
        if bots_inclus is not None and bot not in bots_inclus:
            continue
        scores = res.get("scores", {})
        for m in metrics:
            val = scores.get(m, -1)
            if val != -1:
                total_scores[m].append(val)
                if bot in bot_scores:
                    bot_scores[bot][m].append(val)

    if not any(total_scores[m] for m in metrics):
        averages["global"] = None
    else:
        averages["global"] = {m: (sum(vals) / len(vals) if vals else 0.0) for m, vals in total_scores.items()}
    averages["bots"] = {}
    for b in BOTS:
        # ⚠️ `None`, pas `0.0`, quand le bot n'a AUCUN score ici. Un zéro se soustrait :
        # le 2026-09-16, johnny — absent de la référence parce qu'elle le déclarait non
        # fiable — s'est vu annoncer « 3.74 (+3.74 vs ref) », c'est-à-dire tout son score
        # présenté comme un progrès. Une absence de référence n'est pas une référence à
        # zéro. Voir [[gotcha-run-eval-borne-par-le-quota]].
        if not any(bot_scores[b][m] for m in metrics):
            averages["bots"][b] = None
            continue
        averages["bots"][b] = {m: (sum(vals) / len(vals) if vals else 0.0) for m, vals in bot_scores[b].items()}
    return averages


def filtrer_baseline(previous_report_data: dict) -> dict:
    """Retire de la référence les bots que CE rapport-là a lui-même déclarés non fiables.

    ⚠️ Le filtre sur le run courant ne suffit pas : la comparaison a DEUX côtés.
    Le rapport du 2026-09-16 porte dix 0 pour `johnny`, obtenus en notant
    `[Toute la cascade de modèles a échoué]` — son propre bloc de santé le dit
    `fiable: false`. Comparer un johnny mesuré à ces 0 lui inventerait un **+5 de
    progrès** aussi faux que la chute de 5 qu'on vient de faire taire.
    La vérité est déjà dans le fichier : chaque rapport transporte son `sante`.
    Voir [[gotcha-run-eval-borne-par-le-quota]].
    """
    if not previous_report_data:
        return previous_report_data

    sante_ref = previous_report_data.get("sante", {}).get("bots", {})
    non_fiables = {b for b, etat in sante_ref.items() if not etat.get("fiable", True)}
    if not non_fiables:
        return previous_report_data

    propre = dict(previous_report_data)
    propre["results"] = [
        r for r in previous_report_data.get("results", []) if r["bot"] not in non_fiables
    ]
    print(f"[REF] Bots ecartes de la reference (non fiables dans CE rapport) : {sorted(non_fiables)}")
    return propre


def get_last_report():
    """Récupère le chemin du rapport d'évaluation le plus récent."""
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)
        return None
    files = glob.glob(os.path.join(reports_dir, "eval_*.json"))
    if not files:
        return None
    files.sort()
    return files[-1]


def cleanup_pycache():
    """Supprime les dossiers __pycache__ orphelins dans tests/eval/."""
    eval_dir = os.path.dirname(os.path.abspath(__file__))
    pycache_dir = os.path.join(eval_dir, "__pycache__")
    if os.path.exists(pycache_dir):
        try:
            shutil.rmtree(pycache_dir)
            print("Nettoyage du cache effectue.")
        except Exception as e:
            print(f"Avertissement lors du nettoyage du cache : {e}")


def bots_demandes(argv: list[str] = None) -> list[str]:
    """Lit `--bot <id>` (répétable, ou liste séparée par des virgules).

    Un run complet coûte ~60 appels de juge et autant côté bots. Quand seuls deux bots
    sont à reprendre — parce que le tirage les avait laissés en fin de file et que les
    quotas étaient vides — rejouer les six brûle trois fois le quota nécessaire et peut
    affamer deux AUTRES bots. Voir [[gotcha-run-eval-borne-par-le-quota]].
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    demandes = []
    i = 0
    while i < len(argv):
        if argv[i] == "--bot" and i + 1 < len(argv):
            demandes.extend(x.strip() for x in argv[i + 1].split(",") if x.strip())
            i += 2
        elif argv[i].startswith("--bot="):
            demandes.extend(x.strip() for x in argv[i][6:].split(",") if x.strip())
            i += 1
        else:
            i += 1

    if not demandes:
        return list(BOTS)

    inconnus = [b for b in demandes if b not in BOTS]
    if inconnus:
        raise SystemExit(f"[ERREUR] Bot(s) inconnu(s) : {inconnus}. Connus : {BOTS}")
    # Dedoublonner en gardant l'ordre de BOTS, pour que le tirage reste comparable.
    return [b for b in BOTS if b in demandes]


async def main():
    print("[START] Demarrage du harnais d'evaluation des personas...")

    # 1. Charger les scénarios
    eval_dir = os.path.dirname(os.path.abspath(__file__))
    scenarios_path = os.path.join(eval_dir, "scenarios.json")
    if not os.path.exists(scenarios_path):
        print(f"Erreur : le fichier {scenarios_path} n'existe pas.")
        return

    with open(scenarios_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    # 2. Chercher le dernier rapport de référence
    last_report_path = get_last_report()
    last_report_data = None
    if last_report_path:
        print(f"[REF] Rapport de reference trouve : {os.path.basename(last_report_path)}")
        try:
            with open(last_report_path, "r", encoding="utf-8") as f:
                last_report_data = filtrer_baseline(json.load(f))
            # ⚠️ Deux barèmes différents ne se comparent pas : le delta afficherait un
            # progrès ou une chute qui ne viennent pas des bots. Les rapports d'avant le
            # 2026-09-17 n'ont pas de `version_bareme` — ce sont des barèmes 1.
            bareme_ref = (last_report_data or {}).get("version_bareme", 1)
            if bareme_ref != VERSION_BAREME:
                print(f"[REF] ⚠️ Bareme different (reference={bareme_ref}, courant="
                      f"{VERSION_BAREME}) : les DELTAS sont masques, seuls les scores "
                      f"bruts de ce run sont exploitables.")
                last_report_data = None
        except Exception as e:
            print(f"Impossible de lire le dernier rapport : {e}")

    # 3. Tirage aléatoire de l'ordre des bots (Lot 1.2)
    bots_a_mesurer = bots_demandes()
    if bots_a_mesurer != list(BOTS):
        print(f"[HARNAIS] Run PARTIEL demande : {bots_a_mesurer}")
    bots_evalues, seed = order_bots(bots_a_mesurer)
    print(f"[HARNAIS] Graine aleatoire (seed) : {seed}")
    print(f"[HARNAIS] Ordre des bots tire au sort : {' -> '.join(b.upper() for b in bots_evalues)}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    results = []
    stats_bots = {b: {"appels_echoues": 0} for b in bots_evalues}

    # 4. Boucler sur les bots et les scénarios
    for bot_id in bots_evalues:
        print(f"\n[BOT] Evaluation du bot : {bot_id.upper()}")
        print("-" * 50)

        for scenario in scenarios:
            scenario_id = scenario["id"]
            print(f"   Scenario : {scenario_id}...")

            try:
                # Exécution du scénario
                responses = await run_scenario_for_bot(bot_id, scenario)

                # Échec cascade complet
                echec_cascade = any(resp == ECHEC_CASCADE for resp in responses)
                if echec_cascade:
                    stats_bots[bot_id]["appels_echoues"] += 1

                    # ⚠️ On ne MESURE PAS une non-réponse. Tant que le juge était
                    # appelé sur la sentinelle, il brûlait du quota — la ressource
                    # exactement qui manquait — pour noter une chaîne d'erreur : le
                    # 2026-09-16 johnny a ainsi récolté dix 0 de `fidelite` et un 5
                    # d'`anti_fuite`, et la mesure déterministe a « réussi » son
                    # « Max 7 mots (<= 30 : True) » sur ce même message d'erreur.
                    # Un -1 dit « pas mesuré » ; un 0 dit « mauvais ». Ce n'est pas
                    # la même phrase. Voir [[gotcha-run-eval-borne-par-le-quota]].
                    results.append({
                        "bot": bot_id,
                        "scenario_id": scenario_id,
                        "success": False,
                        "responses": responses,
                        "user_messages": scenario["user_messages"],
                        "scores": {m: -1 for m in METRICS},
                        "verdict": "Non mesure : la cascade du bot n'a rendu aucune reponse",
                        "citation": "",
                        "gimmick_detected": False,
                        "gimmick_detail": "",
                        "mesure_deterministe": {}
                    })
                    print("   [NON MESURE] Cascade du bot muette : juge et mesures deterministes court-circuites.")
                    continue

                # Détection déterministe de gimmick
                gimmick_detected, gimmick_detail = detect_gimmick(responses)

                # Mesures déterministes dédiées (Lot 2)
                mesure_det = evaluate_deterministic(scenario_id, bot_id, responses, scenario.get("user_messages", []))

                # Récupération du persona pour le juge
                from tests.eval.persona_loader import load_persona
                persona = load_persona(bot_id)
                system_prompt = persona["system_prompt"]

                # Évaluation par le juge LLM
                transcript_str = scenario.get("transcript", "")

                scores = await evaluate_response(
                    system_prompt=system_prompt,
                    transcript=transcript_str,
                    user_messages=scenario["user_messages"],
                    responses=responses,
                    key_manager=key_manager,
                    groq_client=groq_client,
                    mistral_client=mistral_client,
                )

                if any(scores.get(m, -1) == -1 for m in METRICS):
                    # Si le juge a échoué, on compte un appel échoué
                    stats_bots[bot_id]["appels_echoues"] += 1

                success = all(scores.get(m, -1) != -1 for m in METRICS)

                eval_result = {
                    "bot": bot_id,
                    "scenario_id": scenario_id,
                    "success": success,
                    "responses": responses,
                    "user_messages": scenario["user_messages"],
                    "scores": scores,
                    "verdict": scores.get("verdict", "Juge indisponible"),
                    "citation": scores.get("citation", ""),
                    "gimmick_detected": gimmick_detected,
                    "gimmick_detail": gimmick_detail,
                    "mesure_deterministe": mesure_det
                }

                results.append(eval_result)
                print(f"   Score global: Fidelite={scores.get('fidelite')}, Ton={scores.get('ton_fr')}, Concision={scores.get('longueur')}")
                if gimmick_detected:
                    print(f"   [WARNING] Gimmick detecte : {gimmick_detail}")
                if mesure_det and mesure_det.get("detail"):
                    print(f"   [DETERMINISTE] {mesure_det.get('detail')}")

            except Exception as e:
                print(f"   [ERROR] Erreur d'evaluation pour {bot_id} sur {scenario_id} : {e}")
                stats_bots[bot_id]["appels_echoues"] += 1
                results.append({
                    "bot": bot_id,
                    "scenario_id": scenario_id,
                    "success": False,
                    "responses": [],
                    "user_messages": scenario["user_messages"],
                    "scores": {"fidelite": -1, "ton_fr": -1, "anti_contamination": -1, "anti_fuite": -1, "longueur": -1},
                    "verdict": f"Erreur d'execution: {e}",
                    "citation": "",
                    "gimmick_detected": False,
                    "gimmick_detail": "",
                    "mesure_deterministe": {}
                })

    # 5. Calcul de la santé du run et des deltas (Lot 1.1 & 1.3)
    sante = compute_health(results, stats_bots, bots_evalues)
    # La fiabilite se calcule AVANT les chutes : un bot non fiable n'a pas de score a
    # comparer, seulement des zeros d'echec qui trustent le classement.
    bots_fiables = [b for b in bots_evalues if sante["bots"][b]["fiable"]]
    top_3_chutes = compute_top_drops(results, last_report_data, bots_inclus=bots_fiables)

    # 6. Écrire le nouveau rapport
    new_report_data = {
        "timestamp": timestamp,
        "version_bareme": VERSION_BAREME,
        "graine_aleatoire": seed,
        "ordre_bots": bots_evalues,
        "sante": sante,
        "top_3_chutes": top_3_chutes,
        "results": results
    }

    reports_dir = os.path.join(eval_dir, "reports")
    new_report_path = os.path.join(reports_dir, f"eval_{timestamp}.json")
    with open(new_report_path, "w", encoding="utf-8") as f:
        json.dump(new_report_data, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] Nouveau rapport enregistre sous : {new_report_path}")

    # 7. Séparation des bots fiables et non fiables (Lot 1.1) — `bots_fiables` est
    # déjà calculé plus haut, juste après le bloc de santé.
    bots_non_fiables = [b for b in bots_evalues if not sante["bots"][b]["fiable"]]

    current_avg = calculate_averages(new_report_data, bots_inclus=bots_fiables)
    # Les deux moyennes doivent couvrir le MEME ensemble de bots, sinon le delta
    # compare une population a une autre et n'annonce rien.
    prev_avg = calculate_averages(last_report_data, bots_inclus=bots_fiables)

    # 8. Affichage du résumé console
    print("\n" + "=" * 80)
    print(f"RESUME CONSOLE DE L'EVALUATION PERSONA (Rapport {timestamp})")
    print(f"Graine aléatoire : {seed} | Ordre : {' -> '.join(bots_evalues)}")
    print(f"Scores à -1 (total) : {sante['scores_a_moins_un']}")
    print("=" * 80)

    if bots_non_fiables:
        print("\n⚠️ SECTION « NON MESURÉ CE JOUR-LÀ, QUOTA / ÉCHEC CASSETTE OU JUGE » :")
        for b in bots_non_fiables:
            b_info = sante["bots"][b]
            print(f"   - {b.upper()} : {b_info['appels_echoues']} appel(s) échoué(s), {b_info['scores_moins_un']} score(s) à -1")
        print("-" * 80)

    print(f"{'Bot':<12} | {'Scenario':<15} | {'Fidelite':<8} | {'Ton FR':<6} | {'Anti-Cont':<9} | {'Anti-Fuite':<10} | {'Concision':<9} | Verdict")
    print("-" * 80)

    for res in results:
        # Un bot non fiable n'apparaît pas dans le tableau principal des scores
        if res["bot"] not in bots_fiables:
            continue
        scores = res.get("scores", {})
        f = scores.get("fidelite", -1)
        t = scores.get("ton_fr", -1)
        c = scores.get("anti_contamination", -1)
        fu = scores.get("anti_fuite", -1)
        l = scores.get("longueur", -1)
        v = res.get("verdict", "")
        v_short = v[:25] + "..." if len(v) > 25 else v

        print(f"{res['bot']:<12} | {res['scenario_id']:<15} | {f:<8} | {t:<6} | {c:<9} | {fu:<10} | {l:<9} | {v_short}")

    # Mesures déterministes (Lot 2)
    print("\n" + "=" * 80)
    print("MESURES DÉTERMINISTES (Scénarios récents)")
    print("=" * 80)
    for res in results:
        det = res.get("mesure_deterministe")
        if det and det.get("detail"):
            statut = "OK" if det.get("succes") else "FAIL"
            print(f" - {res['bot']:<10} | {res['scenario_id']:<15} | [{statut}] {det.get('detail')}")

    # Top 3 chutes (Lot 1.3)
    print("\n" + "=" * 80)
    print("LES 3 PLUS GROSSES CHUTES (vs rapport précédent)")
    print("=" * 80)
    if top_3_chutes:
        for idx, c in enumerate(top_3_chutes, 1):
            print(f" {idx}. {c['label']}")
    else:
        print(" Aucune chute de score détectée par rapport au rapport précédent.")

    # Moyennes globales
    if current_avg and current_avg.get("global"):
        print("\n" + "=" * 80)
        print("MOYENNES ET DELTAS GLOBAUX (Bots fiables uniquement)")
        print("=" * 80)
        for m in METRICS:
            curr_val = current_avg["global"][m]
            if prev_avg and prev_avg.get("global"):
                prev_val = prev_avg["global"][m]
                diff = curr_val - prev_val
                diff_str = f"{diff:+.2f}" if diff != 0 else "0.00"
                print(f" - {m:<18} : {curr_val:.2f} ({diff_str} vs ref)")
            else:
                print(f" - {m:<18} : {curr_val:.2f} (pas de reference comparable)")

        print("\n" + "=" * 80)
        print("DETAIL PAR BOT (MOYENNE GLOBALE DES SCORES)")
        print("=" * 80)
        for b in bots_fiables:
            b_avg = current_avg["bots"][b]
            score_sum = sum(b_avg.values()) / len(b_avg) if b_avg else 0.0
            prev_b_avg = prev_avg["bots"].get(b) if prev_avg else None
            if prev_b_avg:
                prev_sum = sum(prev_b_avg.values()) / len(prev_b_avg)
                diff = score_sum - prev_sum
                diff_str = f"{diff:+.2f}" if diff != 0 else "0.00"
                print(f" - {b:<12} : {score_sum:.2f} ({diff_str} vs ref)")
            else:
                print(f" - {b:<12} : {score_sum:.2f} (pas de reference : ce bot n'est pas mesure dans le rapport precedent)")

    # Nettoyage final
    cleanup_pycache()


if __name__ == "__main__":
    asyncio.run(main())
