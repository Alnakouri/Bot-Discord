# PLAN — Rollout du pont anti-doublon Discord↔Twitch : Johnny + Sugar

> Antigravity exécute. Claude a rédigé (2026-07-16).
> Cibles : `shared/response_memory.py`, `JohnnyBot/bot_johnny.py`, `SugarBot/bot_sugar.py`, + tests.
> Repérer par CONTENU, pas par numéro de ligne. **Ne PAS toucher à Sheogorath ni à `shared/twitch/llm.py`** :
> le pilote Sheo est déployé et validé (c651489), on réplique son câblage à l'identique.

## Contexte

Le pont anti-doublon (même vanne servie sur Discord ET Twitch) tourne sur Sheo :
1. **Twitch lit Discord** : `twitch_chat.extra_recent_provider = lambda: ...` posé au setup —
   le hook générique de `shared/twitch/llm.py` fusionne déjà cette liste dans le prompt
   Twitch ET dans le filet `_strip_repeated_opening` (v2, c651489). Johnny/Sugar l'ont
   GRATUITEMENT dès que le provider est posé.
2. **Discord lit Twitch** : helper local `_twitch_recent_responses()` + fusion
   `merge_recent_responses(...)` dans le bloc anti-répétition du prompt Discord, avec la
   consigne « mots-clés saillants ».

Référence exacte du câblage pilote : `Sheogorath/bot_sheogorath.py` (chercher
`extra_recent_provider`, `_twitch_recent_responses`, `merge_recent_responses`) et
`Sheogorath/sheo_llm.py` (chercher `def merge_recent_responses`).

## Phase A — Helper partagé

1. Copier `merge_recent_responses` (VERBATIM depuis `Sheogorath/sheo_llm.py`, ~10 lignes,
   None-safe, dédoublonne en gardant l'ordre, `limit=8`) dans `shared/response_memory.py`,
   sous la classe `ResponseMemory`. Les deux bots importent DÉJÀ ce module sans fallback
   (`from shared.response_memory import ResponseMemory`) → ajouter la fonction à l'import.
2. NE PAS toucher à la copie de `sheo_llm.py` (Sheo reste autonome, convention
   « bots indépendants » ; une migration Sheo→shared est hors chapitre).

## Phase B — Johnny (`JohnnyBot/bot_johnny.py`)

1. **Helper module-level** (poser près de `twitch_chat = None`, ou juste avant
   `on_message`) — copie du helper Sheo :
```python
def _twitch_recent_responses():
    """Helper local qui lit les réponses récentes du bot sur Twitch s'il est actif."""
    global twitch_chat
    if not twitch_chat:
        return []
    try:
        resps = []
        for chan_resps in twitch_chat.recent_self_responses.values():
            resps.extend(list(chan_resps))
        return resps
    except Exception:
        return []
```
2. **Bloc `# ANTI-RÉPÉTITION`** (chercher `[ANTI-RÉPÉTITION] Johnny a déjà dit récemment`) :
   remplacer la source :
```python
    recent_responses = merge_recent_responses(
        response_memory.get_recent(message.guild.id if message.guild else 0),
        _twitch_recent_responses(),
    )
```
   et renforcer la consigne finale (garder « Ne répète PAS ces phrases ! Sois ORIGINAL ! »
   et AJOUTER) :
```
 Ne réutilise AUCUN mot-clé saillant de ces répliques (mots en MAJUSCULES, images,
métaphores, chutes) : si l'une d'elles crie ÉVALUATION, toi tu pars ailleurs.
```
3. **Provider Twitch** : dans le `if twitch_chat:` qui suit `setup_twitch_chat("johnny", ...)`,
   AVANT le `create_task` :
```python
            twitch_chat.extra_recent_provider = lambda: [r for hist in response_memory.memory.values() for r in hist][-6:]
```

## Phase C — Sugar (`SugarBot/bot_sugar.py`)

Mêmes 3 édits :
1. Helper `_twitch_recent_responses()` module-level (Sugar a déjà `global twitch_chat`).
2. Bloc anti-répétition (chercher `[ANTI-RÉPÉTITION] Tu as déjà dit récemment`) : même
   fusion `merge_recent_responses(...)` ; la consigne Sugar parle déjà d'OSSATURE →
   AJOUTER à la fin la même phrase « mot-clé saillant » que Johnny.
3. Provider posé dans le `if twitch_chat:` après `setup_twitch_chat("sugar", ...)`.

## Phase D — Tests

1. `shared/response_memory.py::merge_recent_responses` : reprendre les cas de
   `tests/test_twitch_double_repetition.py` (None-safe, dédoublonnage+ordre, limit).
2. Câblage Johnny/Sugar : `bot_johnny.py`/`bot_sugar.py` sont trop lourds à importer →
   asserts SUR LE SOURCE (pattern existant, cf. `tests/test_johnny_persona.py`) : présence
   de `extra_recent_provider`, `_twitch_recent_responses`, `merge_recent_responses(` et
   « mot-clé saillant » dans chacun des 2 fichiers.
3. Suite complète verte (229+). Grâce à c651489, le run ne doit RIEN écrire dans `logs/`.

## Garde-fous

- Sheogorath, `shared/twitch/llm.py`, filet de phrases, caps : INTACTS.
- Le provider est une lambda posée sur l'objet → no-op si `setup_twitch_chat` retourne None
  (Twitch coupé) ; le helper Discord est try/except → no-op si Twitch down.
- `shared/response_memory.py` reste sans dépendance (fonction pure).

## Déploiement + validation (après commit)

`docker compose up -d --build --force-recreate johnny sugar`
(⚠️ les 6 conteneurs sont DOWN depuis la nuit du 2026-07-15→16 — les relancer tous si voulu :
`docker compose up -d`.)
- Sondes : `python tools/sonde_twitch.py --bot johnny` puis `--bot sugar` → 4/4 vertes.
- Validation live : même pique envoyée Discord puis Twitch à < 2 min, pour chaque bot →
  ni punchline ni mot-clé saillant partagés.
- Reste aussi du chapitre précédent : **validation B Sheo** (même insulte 2 canaux) —
  toujours à faire manuellement.
