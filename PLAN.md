# PLAN — pytest ne pollue plus les logs du dashboard + pont anti-doublon v2

> Antigravity exécute. Claude a rédigé (2026-07-15, tard).
> Cibles : `shared/bot_logger.py`, `tests/conftest.py` (nouveau), `shared/twitch/llm.py`,
> `Sheogorath/bot_sheogorath.py`, + tests. Repérer par CONTENU, pas par numéro de ligne.

## Contexte / constats (2026-07-15 soir)

1. **Fausses alertes dashboard** : chaque run pytest sur l'hôte importe les modules des
   bots → `setup_logger` écrit « === SHEOGORATH STARTED === » + les warnings ATTENDUS des
   tests (ex. `test_corrupted_file_recovers_to_empty` → « Erreur chargement store
   décrets ») dans les MÊMES fichiers `logs/*.log` + `logs/*_structured.jsonl` que les
   conteneurs. Le dashboard les affiche comme des événements du bot live, en heure LOCALE
   entrelacée avec l'UTC du conteneur. Ça a coûté une soirée de diagnostic.
2. **Pont anti-doublon partiel** (validation 22:35) : même insulte sur les 2 canaux →
   punchlines différentes ✅ mais même riff d'ouverture (« Oh, … ÉVALUATION ») ❌.
   La réponse Discord ÉTAIT dans la liste interdite du prompt Twitch → Mistral a désobéi
   à « variations proches ». Et le filet déterministe `_strip_repeated_opening` ne lit que
   `recent_self_responses` (pas la liste fusionnée).

## Phase A — Logs silencieux sous pytest

1. `shared/bot_logger.py`, dans `setup_logger`, juste après la création du logger et le
   garde `if logger.handlers:` :
```python
    # Sous pytest (ou sur demande), on ne garde QUE la console : les handlers
    # fichier/JSONL écriraient dans les logs/ partagés que le dashboard affiche
    # comme des événements des bots LIVE (fausses alertes, heure locale vs UTC).
    console_only = bool(
        os.getenv("BOTS_LOG_CONSOLE_ONLY") or os.getenv("PYTEST_CURRENT_TEST")
    )
```
   Puis conditionner l'ajout du `RotatingFileHandler` ET du `JSONLHandler` à
   `if not console_only:`. Le handler console et la ligne « STARTED » restent (filet
   `docker logs` inchangé).
2. `tests/conftest.py` (NOUVEAU, à la racine de `tests/`) :
```python
# -*- coding: utf-8 -*-
"""Garde globale : les tests ne doivent JAMAIS écrire dans logs/* (le dashboard
les afficherait comme des événements des bots live). Posé AVANT tout import de
module bot par les tests — conftest est chargé en premier par pytest."""
import os

os.environ.setdefault("BOTS_LOG_CONSOLE_ONLY", "1")
```
   (`PYTEST_CURRENT_TEST` n'existe pas encore au moment des imports de collection,
   d'où la ceinture ET les bretelles.)
3. ⚠️ Ne PAS toucher aux appels `setup_logger(...)` des bots ni au format des lignes.

## Phase B — Pont anti-doublon v2 (déterministe + consigne)

1. `shared/twitch/llm.py` : au post-traitement, là où
   `text = _strip_repeated_opening(text, self.recent_self_responses.get(chan_lower))`,
   passer la MÊME liste fusionnée que celle du prompt. `merged_recent` est calculée plus
   haut dans la même méthode → la réutiliser (la faire descendre jusqu'au post-traitement ;
   si les deux points sont dans des portées différentes, recalculer la fusion sur place
   avec le même code provider + try/except).
2. Renforcer la consigne des DEUX blocs `[ANTI-RÉPÉTITION ABSOLUE]` (celui de
   `shared/twitch/llm.py` ET celui de `Sheogorath/bot_sheogorath.py`) en ajoutant à la
   fin de l'interdiction :
```
Ne réutilise AUCUN mot-clé saillant de ces répliques (mots en MAJUSCULES, images,
métaphores, chutes) : si l'une d'elles crie ÉVALUATION, toi tu pars ailleurs.
```
3. `_strip_repeated_opening` lui-même : NE PAS élargir sa clé (4 premiers mots) — c'est
   voulu qu'il ne coupe que les vrais moules ; le riff conceptuel est du ressort de la
   consigne (2).

## Phase C — Tests

1. `setup_logger` avec `BOTS_LOG_CONSOLE_ONLY=1` (monkeypatch env + logger name unique) :
   aucun fichier créé dans un `tmp_path` passé comme `log_dir` ; sans la variable (et sans
   `PYTEST_CURRENT_TEST` — la retirer du env dans le test) : les fichiers apparaissent.
   ⚠️ `logging.getLogger` est un singleton par nom → utiliser des noms de bot uniques
   (`f"testbot_{uuid4().hex[:6]}"`) pour ne pas hériter des handlers d'un autre test.
2. Twitch : `_strip_repeated_opening` reçoit la liste fusionnée — test : une réponse
   Twitch dont l'ouverture reprend une réplique « Discord » du provider est bien coupée.
3. Asserts consigne : « mot-clé saillant » présent dans les 2 blocs anti-répétition
   (prompt Twitch construit via mock + fragment Discord).
4. Suite complète verte (226+) — et vérifier qu'après le run, `logs/` ne contient AUCUNE
   ligne nouvelle du jour (c'est le but de la phase A : en faire l'assert d'un test
   d'intégration si simple, sinon vérification manuelle au déploiement).

## Garde-fous

- La ligne « === X STARTED === » reste loggée (console) — ne casse pas `docker logs`.
- `shared/bot_logger.py` est partagé par les 6 bots : la garde doit être NO-OP en prod
  (aucune des 2 variables n'existe dans les conteneurs).
- Phase B : ne rien changer d'autre au pipeline (filet de phrases, cap, anti-écho intacts).
- Le pont reste Sheo pilote — pas de rollout Johnny/Sugar dans ce chapitre.

## Déploiement + validation (après commit)

`docker compose up -d --build --force-recreate sheogorath`.
Validation A : lancer `python -m pytest` sur l'hôte → le dashboard ne doit plus afficher
de « STARTED »/« Erreur décrets » fantômes (et `logs/sheogorath_structured.jsonl` ne doit
plus grossir pendant le run).
Validation B : même insulte Discord puis Twitch à < 2 min → ni punchline ni mot-clé
saillant partagés. Puis `python tools/sonde_twitch.py --bot sheogorath` → 4/4 vertes.
