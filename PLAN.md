# PLAN — Vérification post-exécution de l'audit (2026-08-24)

Le plan d'audit a été exécuté par Antigravity. Vérification faite : **l'essentiel est
bon, mais 1 défaut bloquant + 5 finitions manquantes.** Rien n'est commité ni déployé.

`git status` : 9 fichiers modifiés, 2 nouveaux (`shared/models.py`, `tests/test_model_ids.py`).

---

## ✅ Ce qui est correct

- **248 tests passent** (247 + le nouveau `test_model_ids`), 46 subtests, 0 régression.
- **0 référence morte restante** : plus aucun `gemini-2.5-*`, `llama-3.3-70b-versatile`
  ni `dolphin-mistral-24b` dans tout l'arbre (vérifié par grep ET par le nouveau test).
- **Vision débloquée** : `shared/media_handler.py` l. 81 et 229 → `gemini-3.5-flash`. ✅
  C'était le correctif prioritaire, il est bon.
- `gemini-2.5-flash` → `gemini-3.5-flash` : 17/17 sites corrigés
  (smart_router ×9, media_handler ×2, MaiqBot ×3, Sheogorath ×2, Alfred ×1,
  plus `tests/eval/judge.py` que le plan avait manqué — bien vu).
- `llama-3.3-70b-versatile` → `openai/gpt-oss-120b` : 10/10 sites corrigés.
- Durcissement écritures : `MalenaBot/malena_memory.py:57` ✅ et
  `Sheogorath/sheo_memory.py:154` (`FactMemory.save_facts`) ✅.
- `shared/models.py` créé avec les 5 bons identifiants.

---

## 🔴 DÉFAUT BLOQUANT — mauvais slug OpenRouter (5 sites)

Le remplacement de Dolphin n'a substitué que **le nom du modèle**, en gardant le
**préfixe éditeur** de l'ancien. Résultat :

```
cognitivecomputations/nvidia/nemotron-3-super-120b-a12b:free
^^^^^^^^^^^^^^^^^^^^^^ ← à supprimer
```

Sondé en vrai (`bot-maiq`, clé de prod) :
```
FAIL  cognitivecomputations/nvidia/nemotron-3-super-120b-a12b:free
      -> 400 'not a valid model ID'
OK    nvidia/nemotron-3-super-120b-a12b:free
```

**L'échelon OpenRouter est donc mort dans les 5 cas** — exactement le problème que
l'audit devait résoudre. Le test anti-retour ne l'attrape pas (il ne cherche que les
3 anciens patterns).

Sites à corriger — remplacer par `nvidia/nemotron-3-super-120b-a12b:free` :
- `shared/smart_router.py:185`
- `Sheogorath/bot_sheogorath.py:1089`
- `Sheogorath/bot_sheogorath.py:1652`
- `Sheogorath/bot_sheogorath.py:1867`
- `Sheogorath/bot_sheogorath.py:1909`

---

## ⚠️ Finitions manquantes

### F1 — Cascade REASONING : même modèle deux fois
`shared/smart_router.py:158-162` rend aujourd'hui :
```python
("gemini", "gemini-3.5-flash"),
("gemini", "gemini-3.5-flash"),   # ← doublon : aucun repli réel
```
Si Gemini throttle, la cascade n'a **rien** derrière. Rétablir la diversité prévue :
```python
("gemini",  "gemini-3.5-flash"),
("mistral", "mistral-large-latest"),
("groq",    "openai/gpt-oss-120b"),
```

### F2 — `("ollama", "moondream")` toujours dans la cascade IMAGE
`shared/smart_router.py:171`. Le service a été **retiré du `docker-compose.yml`**
(feature GPU parkée) : cet échelon ne peut que timeout. À supprimer.

### F3 — `shared/models.py` n'est utilisé nulle part
Le fichier existe mais **aucun `import` ne le référence** : les identifiants restent
copiés en dur dans 32 endroits. L'objectif de l'étape 4 (« qu'une prochaine
dépréciation ne coûte pas 32 éditions ») n'est donc pas atteint — c'est précisément
ce qui a permis le défaut bloquant ci-dessus.

Câbler `shared/smart_router.py`, `shared/media_handler.py` et les 6 `bot_*.py` dessus,
en respectant la règle **bots indépendants** :
```python
try:
    from shared.models import GEMINI_FLASH, GEMINI_FLASH_LITE, GROQ_FAST, MISTRAL_MAIN, OPENROUTER_FREE
except ImportError:  # bot déployé seul, sans shared/
    GEMINI_FLASH      = "gemini-3.5-flash"
    GEMINI_FLASH_LITE = "gemini-3.5-flash-lite"
    GROQ_FAST         = "openai/gpt-oss-120b"
    MISTRAL_MAIN      = "mistral-large-latest"
    OPENROUTER_FREE   = "nvidia/nemotron-3-super-120b-a12b:free"
```

### F4 — Durcissement des écritures : 3 sites sur 5 restent nus
Dont **le plus important**, oublié :

| Fichier | Ligne | Fonction | Pourquoi ça compte |
|---|---|---|---|
| `Sheogorath/sheo_memory.py` | 57 | `DailyMemory.save_memory()` | appelée par `add_interaction` → c'est **le** chemin chaud (`bot_sheogorath.py:2065`, `:2573`) ; une exception y saute `response_memory.add()` et l'anti-répétition cesse de mémoriser |
| `Sheogorath/sheo_faveur.py` | 81 | `save()` | — |
| `Sheogorath/sheo_punishments.py` | 41 | `save_punishments()` | — |

Même motif que celui déjà appliqué dans `FactMemory.save_facts` :
```python
try:
    with open(self.filename, "w", encoding="utf-8") as f:
        json.dump(self.memory, f, indent=4)
except OSError as e:
    logger.warning(f"⚠️ Sauvegarde {self.filename} impossible ({e}) — état non persisté.")
```
(`sheo_punishments.py` n'est pas une méthode : utiliser `PUNISHMENT_FILE`.)

### F5 — Commentaires obsolètes (étape 6, pas faite)
`shared/smart_router.py:178-181` décrit encore la cascade REPARTEE comme
« Llama-3.3-70b (Groq) en secours, puis Dolphin-Venice :free » — ces deux modèles
n'existent plus. Et l. 189-191 affirme que `google/gemma-4-26b-a4b-it:free`
« n'existe pas sur OpenRouter » : **il existe à nouveau** (il est dans les 18 slugs
`:free` listés), il renvoie simplement 429 aujourd'hui. Réécrire les deux blocs.

### F6 — Renforcer le test anti-retour
`tests/test_model_ids.py` ne détecte pas un slug OpenRouter mal formé. Ajouter un
contrôle : tout littéral contenant `:free` doit compter **exactement un `/`**
(`éditeur/modèle:free`) — ce qui aurait attrapé le défaut bloquant.

---

## Ordre d'exécution

1. Défaut bloquant (5 slugs) — **d'abord**, c'est le seul qui casse la prod.
2. F1, F2, F4, F5 (édits mécaniques).
3. F6 puis F3 (F3 en dernier : c'est la refonte la plus large).
4. `.venv/Scripts/python.exe -m pytest` → **248 minimum, 0 régression**.
5. Sonde live des 4 cascades, chaque échelon un par un :
   ```bash
   MSYS_NO_PATHCONV=1 docker exec bot-maiq python -c "
   import sys, os; sys.path.insert(0,'/app'); os.chdir('/app/bot')
   from pathlib import Path
   from shared.secure_env import load_secure_env
   load_secure_env(Path('/app/bot'))
   from openai import OpenAI
   o = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=os.getenv('OPENROUTER_API_KEY'))
   print(o.chat.completions.create(model='nvidia/nemotron-3-super-120b-a12b:free',
         messages=[{'role':'user','content':'dis OK'}], max_tokens=20).choices[0].message.content)"
   ```
   ⚠️ `MSYS_NO_PATHCONV=1` obligatoire sous Git Bash. Clé Gemini = `GEMINI_KEY_1`.
   ⚠️ Ne jamais valider un modèle sur `models.list()` : la liste ment (elle affichait
   encore `gemini-2.5-*` alors qu'ils renvoient 404). Seul un appel réel fait foi.
6. Commit + `docker compose up -d --build --force-recreate`.
7. Test vision live : poster une image dans Discord → un bot doit la décrire.

## Reste côté utilisateur
Tokens Twitch **401** (johnny, sugar, sheogorath) → ré-autorisation OAuth manuelle
(`twitch_authorize.py`, gotcha : `--auth --bot <bot>` avant **chaque** bot).
