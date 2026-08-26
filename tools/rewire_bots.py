import os
import re
from pathlib import Path

MODULES = [
    "smart_router",
    "api_manager",
    "llm_cascade",
    "media_handler",
    "bot_logger",
    "secure_env",
    "graceful_shutdown",
    "safe_client",
    "response_memory",
    "models"
]

def rewire_bots():
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    
    for bot in bots:
        bot_dir = Path(bot)
        for py_file in bot_dir.rglob("*.py"):
            if "core" in py_file.parts:
                continue # don't touch core itself
                
            content = py_file.read_text(encoding="utf-8")
            orig_content = content
            
            # 1. Rewire core modules
            for mod_name in MODULES:
                content = re.sub(fr'^from shared\.{mod_name}\b', f'from core.{mod_name}', content, flags=re.MULTILINE)
                content = re.sub(fr'^import shared\.{mod_name}\b', f'import core.{mod_name}', content, flags=re.MULTILINE)
                
            # 2. Rewire shared_database and server_events
            # We look for lines like "from shared.shared_database import ..." and wrap them.
            # But wait, there might be multiple imports on multiple lines.
            
            # For simplicity, if we find "from shared.shared_database import" we replace the whole statement block with try/except
            # A safer way using regex for a single line import:
            def replace_optional(match):
                imp = match.group(0)
                return f"""try:
    {imp}
    DB_PARTAGEE = True
except ImportError:
    DB_PARTAGEE = False
    import logging
    logging.getLogger("{bot.lower()}").warning("[CORE] shared/ absent : reputation et classement inter-bots desactives.")"""
            
            # Since there can be multiple lines for imports (with parens), let's just find the `from shared.shared_database` line
            # Assuming standard single line or well-formatted. Let's do a simple replace for now and verify.
            if re.search(r'^from shared\.(shared_database|server_events)\b.*', content, flags=re.MULTILINE):
                # Actually, wait. It's better to manually do it or use a more precise regex.
                # The prompt says: "Pour shared_database et server_events, à l'inverse : ... Et chaque appel doit être gardé par le drapeau."
                # We need to make sure we don't break existing try/excepts if any, and only wrap top-level ones.
                # The manual patch is safer. Let's just do the module replacement here and I'll do shared_database manually if needed.
                pass
                
            if content != orig_content:
                py_file.write_text(content, encoding="utf-8")

if __name__ == "__main__":
    rewire_bots()
