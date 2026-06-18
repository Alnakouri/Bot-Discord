import os
import sys
import json
import asyncio
import glob
import shutil
from datetime import datetime

# Injection du répertoire racine dans sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from tests.eval.runner import run_scenario_for_bot, key_manager, groq_client, mistral_client, openrouter_client
from tests.eval.gimmick import detect_gimmick
from tests.eval.judge import evaluate_response

# Liste des bots à évaluer
BOTS = ["johnny", "maiq", "alfred", "malena", "onizuka", "sheogorath"]

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
        
    # 2. Chercher le dernier rapport avant d'en écrire un nouveau
    last_report_path = get_last_report()
    last_report_data = None
    if last_report_path:
        print(f"[REF] Rapport de reference trouve : {os.path.basename(last_report_path)}")
        try:
            with open(last_report_path, "r", encoding="utf-8") as f:
                last_report_data = json.load(f)
        except Exception as e:
            print(f"Impossible de lire le dernier rapport : {e}")
            
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    results = []
    
    # 3. Boucler sur les bots et les scénarios
    for bot_id in BOTS:
        print(f"\n[BOT] Evaluation du bot : {bot_id.upper()}")
        print("-" * 50)
        
        for scenario in scenarios:
            scenario_id = scenario["id"]
            print(f"   Scenario : {scenario_id}...")
            
            try:
                # Exécution du scénario
                responses = await run_scenario_for_bot(bot_id, scenario)
                
                # Détection déterministe de gimmick
                gimmick_detected, gimmick_detail = detect_gimmick(responses)
                
                # Récupération du persona pour le juge
                from tests.eval.persona_loader import load_persona
                persona = load_persona(bot_id)
                system_prompt = persona["system_prompt"]
                
                # Évaluation par le juge LLM
                # On passe le transcript du scénario s'il existe
                transcript_str = scenario.get("transcript", "")
                
                scores = await evaluate_response(
                    system_prompt=system_prompt,
                    transcript=transcript_str,
                    user_messages=scenario["user_messages"],
                    responses=responses,
                    key_manager=key_manager,
                    groq_client=groq_client,
                    mistral_client=mistral_client,
                    openrouter_client=openrouter_client
                )
                
                success = all(resp != "[Toute la cascade de modèles a échoué]" for resp in responses)
                
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
                    "gimmick_detail": gimmick_detail
                }
                
                results.append(eval_result)
                print(f"   Score global: Fidelite={scores.get('fidelite')}, Ton={scores.get('ton_fr')}, Concision={scores.get('longueur')}")
                if gimmick_detected:
                    print(f"   [WARNING] Gimmick detecte : {gimmick_detail}")
                    
            except Exception as e:
                print(f"   [ERROR] Erreur d'evaluation pour {bot_id} sur {scenario_id} : {e}")
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
                    "gimmick_detail": ""
                })
                
    # 4. Écrire le nouveau rapport
    new_report_data = {
        "timestamp": timestamp,
        "results": results
    }
    
    reports_dir = os.path.join(eval_dir, "reports")
    new_report_path = os.path.join(reports_dir, f"eval_{timestamp}.json")
    with open(new_report_path, "w", encoding="utf-8") as f:
        json.dump(new_report_data, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] Nouveau rapport enregistre sous : {new_report_path}")
    
    # 5. Calculer le delta vs rapport précédent
    metrics = ["fidelite", "ton_fr", "anti_contamination", "anti_fuite", "longueur"]
    
    def calculate_averages(report_data):
        if not report_data:
            return None
        averages = {}
        # Moyennes globales
        total_scores = {m: [] for m in metrics}
        # Moyennes par bot
        bot_scores = {b: {m: [] for m in metrics} for b in BOTS}
        
        for res in report_data.get("results", []):
            bot = res["bot"]
            scores = res.get("scores", {})
            for m in metrics:
                val = scores.get(m, -1)
                if val != -1:
                    total_scores[m].append(val)
                    if bot in bot_scores:
                        bot_scores[bot][m].append(val)
                        
        averages["global"] = {m: (sum(vals) / len(vals) if vals else 0.0) for m, vals in total_scores.items()}
        averages["bots"] = {}
        for b in BOTS:
            averages["bots"][b] = {m: (sum(vals) / len(vals) if vals else 0.0) for m, vals in bot_scores[b].items()}
        return averages

    current_avg = calculate_averages(new_report_data)
    prev_avg = calculate_averages(last_report_data)
    
    # 6. Affichage du résumé console
    print("\n" + "=" * 80)
    print(f"RESUME CONSOLE DE L'EVALUATION PERSONA (Rapport {timestamp})")
    print("=" * 80)
    print(f"{'Bot':<12} | {'Scenario':<12} | {'Fidelite':<8} | {'Ton FR':<6} | {'Anti-Cont':<9} | {'Anti-Fuite':<10} | {'Concision':<9} | Verdict")
    print("-" * 80)
    
    for res in results:
        scores = res.get("scores", {})
        f = scores.get("fidelite", -1)
        t = scores.get("ton_fr", -1)
        c = scores.get("anti_contamination", -1)
        fu = scores.get("anti_fuite", -1)
        l = scores.get("longueur", -1)
        v = res.get("verdict", "")
        # Tronquer le verdict si trop long
        v_short = v[:25] + "..." if len(v) > 25 else v
        
        print(f"{res['bot']:<12} | {res['scenario_id']:<12} | {f:<8} | {t:<6} | {c:<9} | {fu:<10} | {l:<9} | {v_short}")
        
    print("=" * 80)
    print("MOYENNES ET DELTAS GLOBAUX")
    print("=" * 80)
    
    for m in metrics:
        curr_val = current_avg["global"][m]
        if prev_avg:
            prev_val = prev_avg["global"][m]
            diff = curr_val - prev_val
            diff_str = f"{diff:+.2f}" if diff != 0 else "0.00"
            print(f" - {m:<18} : {curr_val:.2f} ({diff_str} vs ref)")
        else:
            print(f" - {m:<18} : {curr_val:.2f}")
            
    print("\n" + "=" * 80)
    print("DETAIL PAR BOT (MOYENNE GLOBALE DES SCORES)")
    print("=" * 80)
    for b in BOTS:
        b_avg = current_avg["bots"][b]
        score_sum = sum(b_avg.values()) / len(b_avg) if b_avg else 0.0
        if prev_avg and b in prev_avg["bots"]:
            prev_b_avg = prev_avg["bots"][b]
            prev_sum = sum(prev_b_avg.values()) / len(prev_b_avg) if prev_b_avg else 0.0
            diff = score_sum - prev_sum
            diff_str = f"{diff:+.2f}" if diff != 0 else "0.00"
            print(f" - {b:<12} : {score_sum:.2f} ({diff_str} vs ref)")
        else:
            print(f" - {b:<12} : {score_sum:.2f}")
            
    # Nettoyage final
    cleanup_pycache()

if __name__ == "__main__":
    asyncio.run(main())
