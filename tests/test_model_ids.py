import pytest
import os
import re
from pathlib import Path

def test_no_dead_models():
    """Vérifie qu'aucun modèle mort n'est câblé en dur."""
    workspace = Path(__file__).parent.parent
    dead_patterns = [
        r"gemini-2\.5",
        r"llama-3\.3-70b-versatile",
        r"dolphin-mistral-24b"
    ]
    
    files_to_check = list(workspace.rglob("*.py"))
    
    failures = []
    
    for file in files_to_check:
        if "venv" in str(file) or "test_model_ids" in str(file) or "__pycache__" in str(file):
            continue
        try:
            content = file.read_text(encoding="utf-8")
            for pattern in dead_patterns:
                if re.search(pattern, content):
                    failures.append(f"{file.name}: contient {pattern}")
            
            # F6: Check for malformed OpenRouter slugs
            # Extract all string literals (simple heuristic)
            literals = re.findall(r'["\']([^"\']*:free)["\']', content)
            for slug in literals:
                if slug.count('/') != 1:
                    failures.append(f"{file.name}: slug mal formé '{slug}' (doit contenir exactement 1 '/')")
        except Exception:
            pass
            
    assert not failures, f"Des modèles morts ont été trouvés : {', '.join(failures)}"

def test_gemini_thinking_budget():
    """La config Gemini doit brider le thinking hors REASONING.

    thinking_level="minimal" est la seule valeur acceptee par flash ET flash-lite :
    thinking_budget=0 fait un 400 INVALID_ARGUMENT sur gemini-3.5-flash-lite.
    """
    workspace = Path(__file__).parent.parent
    needle = 'thinking_level="minimal"'

    llm_cascade = workspace / "shared" / "llm_cascade.py"
    if llm_cascade.exists():
        content = llm_cascade.read_text(encoding="utf-8")
        assert needle in content, (
            "La config Gemini dans llm_cascade.py doit specifier "
            'thinking_level="minimal" (sauf REASONING) pour eviter la troncature.'
        )
        assert "thinking_budget" not in content, (
            "thinking_budget est rejete par gemini-3.5-flash-lite (400) : "
            'utiliser thinking_level="minimal".'
        )

    bot_malena = workspace / "MalenaBot" / "bot_malena.py"
    if bot_malena.exists():
        content = bot_malena.read_text(encoding="utf-8")
        assert needle in content, (
            'bot_malena.py doit specifier thinking_level="minimal" sur son appel Gemini.'
        )
        assert "thinking_budget" not in content, (
            "thinking_budget est rejete par gemini-3.5-flash-lite (400) : "
            'utiliser thinking_level="minimal".'
        )
