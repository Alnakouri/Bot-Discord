# PLAN — Correctifs post-audit (2026-06-30)

## Contexte
Audit complet du projet. Diagnostic global : projet **sain et bien sécurisé**
(0 secret versionné, durcissement Docker/dashboard correct, 99 fichiers
compilent, `shared/` modularisé). Un seul point méritait action : la suite de
tests paraissait cassée alors qu'elle est verte.

## Cause racine
Aucune config pytest n'existait. Sans bornage, pytest balayait tout l'arbre et
ramassait deux scripts de diagnostic **locaux non versionnés** nommés
`test_*.py` :
- `MalenaBot/test_api.py` (importe l'ancien SDK `google.generativeai` →
  ERROR de collecte bloquant toute la suite) ;
- `shared/test_ollama_vision.py` (script async standalone → FAILED).
Les 9 suites réellement versionnées vivent toutes dans `tests/`.

## Actions exécutées (par Claude, 2026-06-30)
1. **`pyproject.toml`** (nouveau) — `[tool.pytest.ini_options]` :
   `testpaths = ["tests"]`, `addopts = "-q"`, `asyncio_mode = "auto"`.
   La collecte est restreinte à `tests/` → les scripts locaux ne sont plus
   ramassés, sans toucher au runtime des bots.
2. **`shared/secure_env.py:46`** — `except:` nu → `except Exception:`
   (validation de la master key Fernet).
3. **`dashboard/backend/app.py:253`** — `except:` nu → `except Exception:`
   (fermeture défensive du WebSocket dans `finally`).

## Vérification
- `python -m pytest` (sans flag) → **84 passed, 3 subtests passed**.
- `py_compile` OK sur les fichiers édités.

## Reste éventuel (non bloquant, dette suivie en mémoire)
- Découpage des monolithes restants : `bot_alfred.py` (1757 l.),
  `bot_maiq.py` (1647 l.), `bot_sheogorath.py` (2433 l.).
- Vestige local : `MalenaBot/test_api.py` utilise encore `google.generativeai`
  alors que le projet est passé à `google-genai` (fichier non versionné, à
  rafraîchir si on le garde comme diagnostic).
