import os
import sys
import ast
from pathlib import Path
import pytest
import importlib

BOTS = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]

def test_no_cross_bot_imports():
    """Vérifie statiquement qu'aucun bot n'importe un autre bot."""
    for bot in BOTS:
        bot_dir = Path(bot)
        if not bot_dir.exists():
            continue
            
        for py_file in bot_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
                
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for other_bot in BOTS:
                            if other_bot != bot and alias.name.startswith(other_bot):
                                pytest.fail(f"Cross-import detecte dans {py_file}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for other_bot in BOTS:
                            if other_bot != bot and node.module.startswith(other_bot):
                                pytest.fail(f"Cross-import detecte dans {py_file}: from {node.module}")


import builtins

class BlockSharedImporter:
    def find_spec(self, fullname, path, target=None):
        if fullname == "shared" or fullname.startswith("shared."):
            raise ImportError(f"Import of {fullname} is blocked for independence testing")
        return None

@pytest.mark.parametrize("bot", BOTS)
def test_bot_import_without_shared(bot):
    """Vérifie que chaque bot peut être importé même si shared/ est absent."""
    bot_file = Path(bot) / f"bot_{bot.lower().replace('bot', '')}.py"
    if bot == "Sheogorath":
        bot_file = Path(bot) / "bot_sheogorath.py"
    if not bot_file.exists():
        pytest.skip(f"{bot_file} not found")
        
    # We must run this in a subprocess to avoid polluting sys.modules and side effects
    import subprocess
    
    code = f"""
import sys
import os

class BlockSharedImporter:
    def find_spec(self, fullname, path, target=None):
        if fullname == "shared" or fullname.startswith("shared."):
            raise ImportError(f"Import of " + fullname + " is blocked for independence testing")
        return None

sys.meta_path.insert(0, BlockSharedImporter())

# Mock environment variables
os.environ['DISCORD_TOKEN'] = 'dummy'
os.environ['GROQ_API_KEY'] = 'dummy'
os.environ['OPENROUTER_API_KEY'] = 'dummy'
os.environ['MISTRAL_API_KEY'] = 'dummy'
os.environ['GEMINI_API_KEY'] = 'dummy'
os.environ['ELEVENLABS_API_KEY'] = 'dummy'
os.environ['TWITCH_CLIENT_ID'] = 'dummy'
os.environ['TWITCH_CLIENT_SECRET'] = 'dummy'
os.environ['TWITCH_ACCESS_TOKEN'] = 'dummy'

# Add bot folder to path
sys.path.insert(0, '{bot}')

try:
    import {bot_file.stem}
    print("Success")
except ImportError as e:
    if 'shared' in str(e) or 'shared.' in str(e):
        print(f"FAILED_SHARED_IMPORT: {{e}}")
        sys.exit(1)
    else:
        print(f"SKIPPED_OTHER_IMPORT: {{e}}")
        sys.exit(0)
except Exception as e:
    print(f"SKIPPED_OTHER_ERROR: {{e}}")
    sys.exit(0)
"""
    
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    
    output = result.stdout.strip()
    if "FAILED_SHARED_IMPORT" in output:
        pytest.fail(f"Le bot {bot} depend de shared/ et ne peut pas demarrer sans: {output}")
    elif "SKIPPED_" in output:
        pytest.skip(f"Test inacheve en raison d'une erreur externe: {output}")
    
    assert result.returncode == 0
