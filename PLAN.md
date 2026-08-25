# PLAN — Débloquer la boucle asyncio : 31 appels LLM synchrones dans des coroutines

## 🔴 Le problème (audit 2026-08-25)

Quatre bots sur six appellent les SDK LLM **en synchrone, directement dans un `async def`** :

```python
resp = client.models.generate_content(...)      # ← bloque la boucle
chat = groq_client.chat.completions.create(...) # ← bloque la boucle
```

Ces SDK (`google-genai`, `groq`, `mistralai`, `openai`) sont **synchrones** : l'appel
tient le thread pendant toute la génération (souvent 2 à 10 s). Or c'est le thread de
la boucle asyncio. Pendant ce temps, le bot ne fait **plus rien du tout** :

- heartbeat Discord suspendu (déconnexions / reconnexions à répétition) ;
- WebSocket Twitch EventSub muet ;
- `@tasks.loop` en retard ou sautées ;
- les autres messages en attente ne sont pas traités, même triviaux.

C'est **exactement** le bug déjà diagnostiqué et corrigé une fois (mémoire
`fix-cascade-bloque-boucle` : « SDK sync non-awaités tuaient le WS EventSub →
asyncio.to_thread ×6 »). Le correctif n'a jamais été propagé.

**Preuve que c'est le bon diagnostic** : Johnny et Sugar ont **0 appel bloquant**.
Ce sont les deux seuls bots dont la cascade passe par `shared/llm_cascade.py`, qui
fait déjà `asyncio.to_thread`. Sheogorath a aussi la bonne forme dans sa cascade
principale (`bot_sheogorath.py:2301`) — ce sont ses *autres* appels qui ont été oubliés.

## ⚖️ Contrainte : indépendance des bots

**Chaque bot doit rester déployable seul.** Ce plan la respecte intégralement :
la correction est **100 % locale à chaque fichier `bot_*.py`**, n'ajoute **aucun**
import `shared/`, ne déplace aucun code, ne crée aucune dépendance croisée.
`asyncio` est déjà importé dans les 6 bots — rien à ajouter.

Chaque bot peut être traité, testé et déployé **séparément**, dans n'importe quel ordre.

---

## Le patch type

`asyncio.to_thread(fn, **kwargs)` exécute l'appel bloquant dans un thread du pool et
rend la main à la boucle. `asyncio.wait_for` borne la durée : si un provider traîne,
on lève `TimeoutError` et la cascade bascule à l'échelon suivant au lieu de figer le bot.

**Avant**

```python
resp = client.models.generate_content(
    model=model_name,
    contents=gemini_messages,
    config=types.GenerateContentConfig(temperature=0.7),
)
```

**Après**

```python
resp = await asyncio.wait_for(
    asyncio.to_thread(
        client.models.generate_content,
        model=model_name,
        contents=gemini_messages,
        config=types.GenerateContentConfig(temperature=0.7),
    ),
    timeout=15,
)
```

La référence exacte à copier existe déjà dans le dépôt :
**`Sheogorath/bot_sheogorath.py:2301-2312`**.

### Règles de portage

1. **Ne jamais mettre les parenthèses de l'appel** après le nom de la fonction :
   on passe `client.models.generate_content` (la fonction), pas
   `client.models.generate_content(...)`. Se tromper ici annule tout l'intérêt du
   patch sans produire d'erreur visible.
2. **Tous les arguments restent identiques**, simplement décalés d'un cran.
   Vérifié : **les 31 sites utilisent uniquement des arguments nommés**, aucun
   positionnel. Le portage est donc mécanique et sûr.
3. `timeout=15` pour les appels sur le chemin d'une réponse à l'utilisateur.
   `timeout=30` pour les tâches de fond (rumeur, énigme, protip hebdo) : elles ne
   bloquent personne et gagnent à aboutir.
4. **Traiter les sites d'un même fichier de la ligne la plus BASSE vers la plus HAUTE**,
   sinon les numéros de ligne ci-dessous se décalent au fur et à mesure des éditions.
5. Ne **rien** changer d'autre : ni les prompts, ni les modèles, ni les températures,
   ni les `try/except`. Ce plan ne corrige qu'une seule chose.

---

## Inventaire exact des 31 sites

### `MaiqBot/bot_maiq.py` — 12 sites (le plus atteint)

| ligne | appel | coroutine | timeout |
|---|---|---|---|
| 1444 | `openrouter_client.chat.completions.create` | `on_message` | 15 |
| 1418 | `groq_client.chat.completions.create` | `on_message` | 15 |
| 1401 | `mistral_client.chat.complete` | `on_message` | 15 |
| 1368 | `client.models.generate_content` | `on_message` | 15 |
| 1341 | `client.models.generate_content` | `on_message` | 15 |
| 943 | `client.models.generate_content` | `maiq_rumeur` | 30 |
| 928 | `groq_client.chat.completions.create` | `maiq_rumeur` | 30 |
| 883 | `groq_client.chat.completions.create` | `profil_maiq_cmd` | 15 |
| 780 | `client.models.generate_content` | `generate_and_post_riddle` | 30 |
| 764 | `groq_client.chat.completions.create` | `generate_and_post_riddle` | 30 |
| 577 | `client.models.generate_content` | `publish_daily_rumor` | 30 |
| 562 | `groq_client.chat.completions.create` | `publish_daily_rumor` | 30 |

### `Sheogorath/bot_sheogorath.py` — 8 sites

| ligne | appel | coroutine | timeout |
|---|---|---|---|
| 1928 | `groq_client.chat.completions.create` | `on_message` | 15 |
| 1917 | `openrouter_client.chat.completions.create` | `on_message` | 15 |
| 1875 | `openrouter_client.chat.completions.create` | `on_message` | 15 |
| 1867 | `groq_client.chat.completions.create` | `on_message` | 15 |
| 1671 | `groq_client.chat.completions.create` | `imposteur_cmd` | 15 |
| 1660 | `openrouter_client.chat.completions.create` | `imposteur_cmd` | 15 |
| 1334 | `gclient.models.generate_content` | `check_missed_mentions_sheo` | 30 |
| 1319 | `groq_client.chat.completions.create` | `check_missed_mentions_sheo` | 30 |

> Les sites `2301` et suivants (cascade principale) sont **déjà corrects** — ne pas y toucher.

### `Alfred/bot_alfred.py` — 7 sites

| ligne | appel | coroutine | timeout |
|---|---|---|---|
| 1751 | `openrouter_client.chat.completions.create` | `on_message` | 15 |
| 1725 | `groq_client.chat.completions.create` | `on_message` | 15 |
| 1706 | `mistral_client.chat.complete` | `on_message` | 15 |
| 1677 | `client.models.generate_content` | `on_message` | 15 |
| 1647 | `client.models.generate_content` | `on_message` | 15 |
| 821 | `client.models.generate_content` | `analyze_audio_with_gemini` | 30 |
| 482 | `mistral_client.chat.complete` | `weekly_protip_alfred` | 30 |

### `MalenaBot/bot_malena.py` — 4 sites

| ligne | appel | coroutine | timeout |
|---|---|---|---|
| 254 | `openrouter_client.chat.completions.create` | `generate_response_hybrid` | 15 |
| 229 | `groq_client.chat.completions.create` | `generate_response_hybrid` | 15 |
| 217 | `mistral_client.chat.complete` | `generate_response_hybrid` | 15 |
| 188 | `gemini_client.models.generate_content` | `generate_response_hybrid` | 15 |

### Rien à faire

`JohnnyBot/bot_johnny.py` et `SugarBot/bot_sugar.py` : **0 site**. Ne pas les modifier.

---

## Gestion du `TimeoutError`

Chaque site est déjà dans un `try/except Exception` (ou le sera par la cascade
englobante). `asyncio.TimeoutError` **hérite de `Exception`** en Python 3.11+, donc
les `except Exception` existants l'attrapent sans modification.

Seul point d'attention : là où un `except` appelle `key_manager.report_error(...)`,
un timeout n'est **pas** une erreur de clé API. Le code lit un code via
`getattr(e, "code", getattr(e, "status_code", 0))`, ce qui donnera `0` sur un
`TimeoutError` — comportement déjà toléré aujourd'hui, donc **aucun changement
requis**. Ne pas sur-corriger.

---

## Vérification

### 1. Compilation

```bash
python -m py_compile MaiqBot/bot_maiq.py Sheogorath/bot_sheogorath.py \
                     Alfred/bot_alfred.py MalenaBot/bot_malena.py
```

### 2. Sonde automatique — doit afficher `TOTAL: 0`

Enregistrer sous `tools/sonde_blocking_calls.py` puis `python tools/sonde_blocking_calls.py` :

```python
import ast, pathlib

BLOCK = ('generate_content', 'chat.completions.create', 'chat.complete')
total = 0
for p in sorted(pathlib.Path('.').glob('*/bot_*.py')):
    src = p.read_text(encoding='utf-8')
    lines = src.splitlines()
    tree = ast.parse(src)
    fns = []

    def walk(n):
        for ch in ast.iter_child_nodes(n):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fns.append((ch.lineno, ch.end_lineno, isinstance(ch, ast.AsyncFunctionDef)))
            walk(ch)

    walk(tree)
    bad = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        seg = ast.get_source_segment(src, n.func) or ''
        if not any(b in seg for b in BLOCK):
            continue
        ctx = "\n".join(lines[max(0, n.lineno - 5):n.lineno])
        if 'to_thread' in ctx or 'run_in_executor' in ctx:
            continue
        inner = [f for f in fns if f[0] <= n.lineno <= f[1]]
        if inner and max(inner, key=lambda f: f[0])[2]:
            bad.append(n.lineno)
    total += len(bad)
    print(f"{p}: {len(bad)} appel(s) bloquant(s) {bad if bad else ''}")
print("TOTAL:", total, "-> ATTENDU: 0")
```

Cette sonde est aussi le **filet anti-régression** : elle rejouera après chaque
modification future d'un bot.

### 3. Suite de tests — les 252 doivent rester verts

```bash
python -m pytest -q
```

### 4. Test live (le seul qui prouve le gain)

Déployer bot par bot, l'indépendance le permet :

```bash
docker compose up -d --build maiq
```

Puis, dans un salon Discord : envoyer **3 messages d'affilée** à M'aiq sans attendre
sa réponse. **Avant** le patch, il traite le 1er et retarde lourdement les suivants.
**Après**, les trois doivent être pris en charge en parallèle.

Vérifier aussi dans `docker logs bot-maiq` la disparition de :

```
discord.gateway: Shard ID None heartbeat blocked for more than N seconds
```

C'est **le** message qui signe le bug.

---

## Ordre recommandé

M'aiq (12) → Sheogorath (8) → Alfred (7) → Malena (4).

M'aiq d'abord : c'est le plus atteint, ses 5 sites dans `on_message` sont sur le
chemin critique de chaque réponse, et c'est le bot dont les silences ont déjà été
signalés en production (mémoire `plan-maiq-permissionerror-fatigue`).

## Ce que ce plan ne fait PAS

- Il ne touche pas à `shared/`.
- Il ne fusionne aucune cascade, ne supprime aucune duplication.
- Il ne corrige pas l'absence de `max_output_tokens` chez Sheo/Alfred/M'aiq
  (sujet distinct, à traiter séparément).
- Il n'ajoute aucun test unitaire sur les `bot_*.py` — chantier suivant :
  test d'indépendance (`shared/` absent) + CI.

---

# ✅ RÉSULTAT — exécuté, corrigé et validé live (2026-08-25)

## Ce qui a été fait

**31 appels enveloppés** dans `asyncio.wait_for(asyncio.to_thread(...))` :
M'aiq 12, Sheogorath 8, Alfred 7, Malena 4. Johnny et Sugar non touchés (0 site).
21× `timeout=15`, 10× `timeout=30`, conformes au plan. Aucun import `shared/` ajouté :
l'indépendance des bots est intacte.

Vérifications statiques : 6/6 bots compilent, sonde à `TOTAL: 0`, aucun
`to_thread(fn(...))`, et **comparaison AST des signatures avant/après → aucun argument
perdu, ajouté ou modifié** sur les 41 appels LLM. 252 tests verts.

Le formatage laissé par le patch automatique (indentation en escalier, 58 lignes avec
espaces en fin de ligne) a été repris : 31 blocs ré-indentés, diff ramené de
612+/271− à 288+/154−.

## 🔴 La régression qu'il a fallu corriger

Après déploiement, **M'aiq et Alfred sont devenus muets**. Logs :

```
[ROUTER] 🎭 Banter adressé → Grok (xAI)
⚠️ [MISTRAL FAIL] cannot access local variable 'asyncio' where it is not associated with a value
⚠️ [GROQ FAIL] cannot access local variable 'asyncio' ...
⚠️ [OPENROUTER FAIL] cannot access local variable 'asyncio' ...
```

`on_message` contenait tout en bas un `import asyncio` redondant (M'aiq l.1538,
Alfred l.1870), alors que le module est déjà importé en tête de fichier. En Python,
un `import` dans une fonction rend ce nom **local à tout son corps** : les
`asyncio.wait_for(...)` ajoutés **plus haut** levaient donc `UnboundLocalError`, et
toute la cascade tombait.

Corrigé en supprimant les 4 `import asyncio` locaux — M'aiq et Alfred (cassés), plus
Johnny l.1051 et Sugar l.972 qui portaient la même mine sans l'avoir encore déclenchée.

**Leçon** : ce bug est invisible à `py_compile`, à la comparaison AST et aux 252 tests.
Il vit dans `on_message`, la fonction que rien ne teste. « Ça compile et les tests
passent » ne prouve rien sur le chemin de réponse des bots — le test live est obligatoire.

## Validation live (2026-08-25, 23:17-23:18)

M'aiq enchaîne quatre messages rapprochés sans décrocher :

```
21:17:16 | [ROUTER] 🎭 Banter adressé → Grok (xAI)
21:17:18 | 🌪️ [MISTRAL mistral-large-latest] M'aiq a répondu.      ← 2 s
21:17:40 | ... 21:17:42 | M'aiq a répondu.
21:18:33 | ... 21:18:35 | M'aiq a répondu.
21:18:47 | [ROUTER] 🖼️ Image (image/webp) → Gemini Vision
21:18:54 | ✅ [GEMINI gemini-3.5-flash] M'aiq via 🖼️ Image          ← 6 s sans geler la boucle
```

(Les logs conteneur sont à **−2 h** de l'heure Discord.)

**0 `heartbeat blocked` sur les 6 bots**, 0 erreur résiduelle.

## Filet anti-régression

`tools/sonde_blocking_calls.py` (versionné) contrôle désormais **trois** choses et
sort en code 1 si l'une échoue — utilisable tel quel en CI :

1. appel LLM synchrone dans une coroutine ;
2. piège des parenthèses `to_thread(fn(...))` ;
3. `import asyncio` local masquant le module (la régression ci-dessus).

Auto-testée contre le code d'avant le patch : elle y retrouve bien les 12 sites de
M'aiq, plus les deux pièges sur un fichier factice.

## Reste à faire

- Chantier suivant : test d'indépendance (importer chaque `bot_*.py` avec `shared/`
  absent) + CI GitHub Actions — le dépôt n'a **aucun** `.github`.
- Toujours ouvert : `max_output_tokens` absent chez Sheo/Alfred/M'aiq.
