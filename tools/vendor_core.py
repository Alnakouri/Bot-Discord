import os
import shutil
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

def vendor_core():
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    shared_dir = Path("shared")
    
    for bot in bots:
        core_dir = Path(bot) / "core"
        core_dir.mkdir(parents=True, exist_ok=True)
        
        init_file = core_dir / "__init__.py"
        if not init_file.exists():
            init_file.touch()
            
        for module in MODULES:
            src_file = shared_dir / module
            if not src_file.exists():
                print(f"Skipping {module} (not found in shared/)")
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
            final_content = header + content
            
            dest_file = core_dir / module
            dest_file.write_text(final_content, encoding="utf-8")
            
    print("Vendoring complete.")

if __name__ == "__main__":
    vendor_core()
