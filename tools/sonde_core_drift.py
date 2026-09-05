import os
import sys
import re
from pathlib import Path

MODULES = [
    "smart_router.py",
    "api_manager.py",
    "llm_cascade.py",
    "media_handler.py",
    "bot_logger.py",
    "secure_env.py",
    "graceful_shutdown.py",
    "safe_client.py",
    "response_memory.py",
    "models.py",
    "api_tracking.py",
    "transcript.py",
    "chrono.py",
    "boucles.py"
]

MODULE_NAMES = [m[:-3] for m in MODULES]

HEADER_TEMPLATE = """# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/{module} — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

"""

def check_drift():
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    shared_dir = Path("shared")
    has_drift = False
    
    for bot in bots:
        core_dir = Path(bot) / "core"
        
        for module in MODULES:
            src_file = shared_dir / module
            dest_file = core_dir / module
            
            if not src_file.exists():
                continue
                
            if not dest_file.exists():
                print(f"Drift detected: {dest_file} is missing.")
                has_drift = True
                continue
                
            content = src_file.read_text(encoding="utf-8")
            
            # Rewrite imports
            for mod_name in MODULE_NAMES:
                # ⚠️ `(\s*)` : les imports du noyau sont souvent INDENTES, dans un
                # `try/except ImportError` avec repli code en dur (bots-independants).
                # Ancree en debut de ligne stricte, la reecriture les laissait passer : la
                # copie vendorisee gardait `from shared.models`, donc un bot deploye sans
                # `shared/` retombait sur le repli au lieu d'utiliser sa propre copie —
                # c'est ce qui ressuscitait `mistral-large` (403 hors abonnement).
                content = re.sub(fr'^(\s*)from shared\.{mod_name}\b', fr'\1from core.{mod_name}', content, flags=re.MULTILINE)
                content = re.sub(fr'^(\s*)import shared\.{mod_name}\b', fr'\1import core.{mod_name}', content, flags=re.MULTILINE)
                
            header = HEADER_TEMPLATE.format(module=module)
            expected_content = header + content
            
            actual_content = dest_file.read_text(encoding="utf-8")
            
            if expected_content != actual_content:
                print(f"Drift detected: {dest_file} differs from expected vendored version of {src_file}.")
                has_drift = True
                
    if has_drift:
        sys.exit(1)
    else:
        print("No drift detected.")
        sys.exit(0)

if __name__ == "__main__":
    check_drift()
