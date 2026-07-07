# PLAN — Anti-incrustation sur Johnny, Alfred, M'aiq, Malena (0 shared, chaque bot autonome)

## Contexte
Sugar est le seul bot avec une **garde anti-incrustation** : quand un échange est
manifestement adressé à un AUTRE bot, il ne s'incruste pas lors d'une intervention
aléatoire/spontanée. Constaté en live : **Johnny s'est incrusté** sur « sugar tu as de
beaux cheveux » (message nommant Sugar).

Objectif : porter cette garde sur **Johnny, Alfred, M'aiq, Malena** (Sheo l'a déjà en
partie, ligne 1972 — hors périmètre).

## Règle d'or ARCHITECTURE — chaque bot reste 100 % autonome
- **AUCUN fichier `shared/` pour cette feature.** On COPIE le code directement dans
  chaque bot (~18 lignes). Pas d'import inter-bot, pas de dépendance runtime.
- Chaque bot a sa **propre** constante `OTHER_BOT_NAMES` = les **5 AUTRES** bots
  (jamais ses propres alias, sinon il se tairait quand on le nomme lui).
- La garde ne touche QUE les branches d'intervention **non sollicitée** (random /
  proactive). Les réponses DIRECTES (mention, reply, DM, nom du bot, requête-service
  explicite) ne sont JAMAIS gardées.

## Snippet de référence (repris de SugarBot/bot_sugar.py, à adapter par bot)
À placer au niveau module (avant `on_message`), en remplaçant la liste `OTHER_BOT_NAMES`
par celle du bot concerné (voir tableau) :

```python
# Noms des AUTRES bots : si l'échange leur est visiblement adressé, on ne s'incruste
# PAS lors d'une intervention ALÉATOIRE (les mentions/nom direct du bot restent prioritaires).
OTHER_BOT_NAMES = [ ... voir tableau par bot ... ]

async def _other_bot_in_focus(message):
    """True si la conversation est manifestement tournée vers un AUTRE bot."""
    if any(n in message.content.lower() for n in OTHER_BOT_NAMES):
        return True
    try:
        async for prev in message.channel.history(limit=4, before=message):
            if prev.author == bot.user:
                return False   # ce bot était déjà dans la boucle → ok d'enchaîner
            if prev.author.bot:
                return True    # un autre bot vient de parler → c'est SON échange
            if any(n in prev.content.lower() for n in OTHER_BOT_NAMES):
                return True    # un humain vient de nommer un autre bot
    except Exception:
        return False
    return False
```

### `OTHER_BOT_NAMES` par bot (exclut ses propres alias)
| Bot | Liste |
|-----|-------|
| **Johnny** | `["sheo","sheogorath","sugar","sugar bot","alfred","pennyworth","m'aiq","maiq","malena","malèna"]` |
| **Alfred** | `["sheo","sheogorath","johnny","silverhand","samurai","silverbot","sugar","sugar bot","m'aiq","maiq","malena","malèna"]` |
| **M'aiq** | `["sheo","sheogorath","johnny","silverhand","samurai","silverbot","alfred","pennyworth","sugar","sugar bot","malena","malèna"]` |
| **Malena** | `["sheo","sheogorath","johnny","silverhand","samurai","silverbot","alfred","pennyworth","m'aiq","maiq","sugar","sugar bot"]` |

## Câblage par bot (points d'insertion EXACTS)

### 1. Johnny — `JohnnyBot/bot_johnny.py` (~ligne 783)
Remplacer :
```python
    # C. Intervention aléatoire (10%)
    if not should_respond and not is_bot_talking and random.random() < 0.10:
        should_respond = True
        logger.info(f"[INTERVENTION] Johnny intervient dans {message.channel.name}")
```
par :
```python
    # C. Intervention aléatoire (10%) — sauf si l'échange vise un AUTRE bot
    if not should_respond and not is_bot_talking and random.random() < 0.10:
        if await _other_bot_in_focus(message):
            logger.info("[ANTI-INCRUSTATION] Échange adressé à un autre bot → Johnny se tait.")
        else:
            should_respond = True
            logger.info(f"[INTERVENTION] Johnny intervient dans {message.channel.name}")
```

### 2. M'aiq — `MaiqBot/bot_maiq.py` (~lignes 1127-1130)
Remplacer :
```python
    # "L'Oreille qui traîne" (Si mot-clé + pas de mention + random 20%)
    if has_keyword and not is_mentioned and not is_reply:
         if random.random() < 0.20:
            is_eavesdropping = True
            logger.info(f"[OREILLE] Mot-clé détecté dans : {message.content[:50]}")
```
par :
```python
    # "L'Oreille qui traîne" (Si mot-clé + pas de mention + random 20%)
    if has_keyword and not is_mentioned and not is_reply:
         if random.random() < 0.20:
            if await _other_bot_in_focus(message):
                logger.info("[ANTI-INCRUSTATION] Échange adressé à un autre bot → M'aiq n'écoute pas.")
            else:
                is_eavesdropping = True
                logger.info(f"[OREILLE] Mot-clé détecté dans : {message.content[:50]}")
```

### 3. Alfred — `Alfred/bot_alfred.py`
Deux branches proactives à garder. Elles sont dans une chaîne `if/elif` : comme la
condition `elif` consomme déjà le tirage aléatoire, on garde À L'INTÉRIEUR du corps
(si focus autre bot → `should_respond` reste False, Alfred se tait).

**3a. Chaos (~ligne 1379)** — remplacer :
```python
    elif (has_chaos_keyword or is_shouting) and random.random() < 0.15:
        should_respond = True
        context_prefix = "CONTEXTE: L'utilisateur est vulgaire ou crie. Rappelle-lui les bonnes manières avec un cynisme glacé."
        print(f"☕ MAINTIEN DE L'ORDRE : Alfred réagit au chaos de {message.author.name}")
```
par :
```python
    elif (has_chaos_keyword or is_shouting) and random.random() < 0.15:
        if await _other_bot_in_focus(message):
            logger.info("[ANTI-INCRUSTATION] Chaos dans un échange adressé à un autre bot → Alfred s'abstient.")
        else:
            should_respond = True
            context_prefix = "CONTEXTE: L'utilisateur est vulgaire ou crie. Rappelle-lui les bonnes manières avec un cynisme glacé."
            print(f"☕ MAINTIEN DE L'ORDRE : Alfred réagit au chaos de {message.author.name}")
```

**3b. Chant (~ligne 1385, `elif not is_bot_talking:`)** — cette branche détecte le chant
puis décide de répondre. Repérer, DANS ce bloc, l'endroit exact où il pose
`should_respond = True` (sanction musicale) et l'entourer du même garde-fou :
```python
        if <condition de chant détecté>:
            if await _other_bot_in_focus(message):
                logger.info("[ANTI-INCRUSTATION] Chant dans un échange adressé à un autre bot → Alfred s'abstient.")
            else:
                should_respond = True
                ...  # reste inchangé
```
⚠️ Ne garder QUE le déclenchement spontané (chant). Ne pas toucher aux réponses directes.

### 4. Malena — `MalenaBot/bot_malena.py` (~lignes 409-415)
Remplacer :
```python
    if not should_respond and message.author.name in data.SPECIAL_INTERACTIONS:
        user_config = data.SPECIAL_INTERACTIONS[message.author.name]
        
        # Tirage au sort basé sur la config
        if random.random() < user_config["proba"]:
            logger.info(f"🎲 [SPECIAL INTERACTION] Malena a envie de parler à {message.author.name} ({user_config['proba']*100}%)")
            should_respond = True
```
par :
```python
    if not should_respond and message.author.name in data.SPECIAL_INTERACTIONS:
        user_config = data.SPECIAL_INTERACTIONS[message.author.name]
        
        # Tirage au sort basé sur la config
        if random.random() < user_config["proba"]:
            if await _other_bot_in_focus(message):
                logger.info("[ANTI-INCRUSTATION] Échange adressé à un autre bot → Malena s'abstient.")
            else:
                logger.info(f"🎲 [SPECIAL INTERACTION] Malena a envie de parler à {message.author.name} ({user_config['proba']*100}%)")
                should_respond = True
```

## Notes
- `_other_bot_in_focus` est **async** (lit `channel.history`). Toutes les branches ci-dessus
  sont déjà dans `on_message` (async) → le `await` est OK.
- Le helper référence `bot.user` : le `bot` module-level de chaque fichier convient.
- NE PAS garder les branches DIRECTES (mention/reply/DM/nom du bot, requête-service Alfred,
  trigger-words Malena) : seules les interventions spontanées sont concernées.

## Vérification attendue
- `python -m py_compile` sur les 4 fichiers.
- Chaque bot importable seul (autonomie préservée, 0 nouveau import inter-bot).
- (Idéal) test live : nommer un bot A, vérifier que B/C/D ne s'incrustent plus dans
  l'échange ; vérifier que l'intervention aléatoire fonctionne encore hors contexte adressé.
