# PLAN — Rendre une panne de base AUDIBLE, et ne plus dépendre du ramasse-miettes

Rédaction : Claude, le **2026-09-13**. Exécution : **Antigravity**.
Fait suite à `cbe0a06` (WAL interdit sur `bots_database.db`, déployé et vérifié).

Le correctif WAL a fermé **la cause**. Ce plan ferme **les deux défauts qui ont laissé
la panne courir deux jours sans que personne ne la voie** — ce sont eux, et non WAL,
qui expliquent qu'on ait mis 48 h à comprendre que les 6 bots étaient muets.

---

## LA PREUVE, relevée le 13/09 avant d'écrire ce plan

Les journaux Docker de `bot-maiq` couvrent **du 25/08 au 13/09** (ils survivent au
redémarrage de Docker Desktop). Sur toute cette période :

| Motif cherché | Occurrences |
|---|---|
| `unable to open database file` | **23** |
| `[ERROR EVENTS]` (le seul cri du thread écrivain) | **0** |

Et la même recherche dans `logs/` sur l'hôte : **0** également.

Autrement dit : pendant que la base refusait toute écriture, **le composant dont le
métier est de journaliser les erreurs n'a pas produit une seule ligne**. Les 23 lignes
visibles venaient toutes d'ailleurs (`[HINT LOOP]`, toutes les 5 min, classées
« inexpliqué » le 11/09 — c'était le symptôme).

---

# LOT 1 — La panne doit CRIER, et continuer de crier

**Fichier : `shared/bot_logger.py`.** Trois défauts distincts, à corriger ensemble.

### 1.1 — Le verrou `_JOURNAL_ERREUR` mute tout, définitivement

```python
except Exception as e:
    if not _JOURNAL_ERREUR:
        logging.getLogger("bot_logger").error(...)
        _JOURNAL_ERREUR = True      # <- plus jamais un mot
```

Le drapeau n'est remis à `False` **que par une écriture réussie**. Quand la base est
morte, aucune écriture ne réussit : **une seule ligne est émise, pour toute la durée de
la panne**. C'est exactement l'inverse de ce qu'on attend d'une alarme.

**À faire** : remplacer le verrou définitif par une **répétition espacée**. Au plus une
ligne toutes les 5 minutes, et cette ligne **porte le nombre d'échecs avalés depuis la
précédente** :

> `[ERROR EVENTS] Écriture SQLite en échec depuis 47 min (312 événements perdus) : <erreur>`

Garder le compteur et l'horodatage du dernier cri dans des globales du module, à côté
de `_JOURNAL_ERREUR`. Le but n'est pas de tout journaliser — c'est qu'une panne longue
laisse une **trace périodique** au lieu d'un unique message noyé deux jours plus tôt.

### 1.2 — L'échec d'initialisation tue le thread, et on en relance un par événement

```python
except Exception as e:          # connexion / CREATE TABLE impossibles
    ...
    return                      # le thread MEURT
```

`_ensure_thread()` est appelé **à chaque `enregistrer_reaction`** et relance un thread
dès que le précédent n'est plus vivant. Base morte = **un thread créé, une connexion
tentée et un abandon silencieux par réaction reçue**.

**À faire** : poser un **délai de reprise**. Mémoriser l'instant du dernier échec
d'initialisation ; `_ensure_thread()` ne retente pas avant **60 s**. Et l'échec
d'initialisation suit la règle 1.1 (répétition espacée), pas le silence.

⚠️ Ne PAS supprimer la relance : elle est utile, c'est elle qui fait repartir le
journal tout seul quand la base redevient saine. C'est sa **fréquence** qui est fautive.

### 1.3 — Le logger `bot_logger` n'est branché sur rien

`setup_logger` recopie les handlers du bot sur une liste de loggers partagés
(`smart_router`, `llm_cascade`, …). **`bot_logger` n'y est pas.** Ses messages ne
partent donc ni dans `logs/<bot>_<date>.log`, ni dans le JSONL que lit le tableau de
bord : ils ne survivent que par le `lastResort` de `logging`, sur stderr. C'est la
raison technique du `0` dans le tableau de preuve ci-dessus.

**À faire** : ajouter `"bot_logger"` à la liste des `shared_name`.

✅ **Vérifié avant d'écrire ceci — pas de boucle** : `ErrorEventHandler.emit` commence
par `if record.name == __name__ or record.name == "bot_logger": return`. Le handler
peut donc être recopié sur ce logger sans se rappeler lui-même. Ne pas « améliorer »
cette garde : c'est elle qui rend le lot possible.

### Verrous attendus (lot 1)

Dans `tests/test_error_events_handler.py` (le fichier existe) :

1. **La répétition espacée crie deux fois.** Faux temps (monkeypatch de l'horloge du
   module), écritures en échec en continu : au moins **2** lignes émises, et la 2e
   **contient le nombre d'événements perdus**. ⚠️ Le verrou porte sur le comptage réel
   du module — ne pas retaper la logique de temporisation dans le test
   (voir le gotcha « un test qui retape la logique s'auto-valide »).
2. **La reprise est espacée.** N appels d'affilée à `enregistrer_reaction` avec une
   initialisation qui échoue toujours ⇒ **un seul** thread créé, pas N.
3. **`bot_logger` est câblé.** Verrou sur le fichier : `"bot_logger"` figure bien dans
   la liste des `shared_name` de `setup_logger`.

**Rejouer la mutation sur chacun** : remettre le code fautif, vérifier que le test
crie. Un verrou qu'on n'a pas vu échouer ne verrouille rien.

---

# LOT 2 — Aucune connexion ne doit dépendre du ramasse-miettes

**Fichier : `shared/shared_database.py`.** Sur **42** fonctions qui ouvrent une
connexion, **40** l'écrivent ainsi :

```python
conn = get_connection()
cursor.execute(...)      # <- si ça lève, la ligne suivante n'est jamais atteinte
conn.close()
```

Il n'y a **ni `try/finally` ni `with`**. La fermeture n'a lieu que sur le chemin
heureux ; sur le chemin d'erreur elle ne tient qu'au comptage de références de CPython,
c'est-à-dire à un détail d'implémentation et au moment où la trace d'exception est
libérée.

Ce n'est pas théorique : `is_maintenance_mode()` → `get_config()` est dans cette liste,
et c'est **la première chose qu'appelle `on_message`** sur les 6 bots. Pendant la panne,
chaque message reçu passait par ce chemin d'erreur. La mesure du 13/09 — **15** handles
ouverts sur `bots_database.db` pour M'aiq contre **2** pour les cinq autres — est
cohérente avec ce défaut, **sans que le chemin de rétention soit prouvé** : M'aiq est le
seul à appeler `shared_database` sur une boucle de 5 min (`riddle_passive_hint_loop`),
donc le seul à emprunter ce chemin même sans trafic.

**À faire** : un gestionnaire de contexte unique dans le module, et les 40 fonctions
passent dessus.

```python
@contextmanager
def connexion():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
```

⚠️ **Refactor mécanique, 40 fois. Aucune requête SQL ne change, aucun `commit()` ne se
déplace.** Si une fonction fait autre chose que ce qui est décrit ici, la laisser en
l'état et le signaler plutôt que de l'adapter.

Les 40 fonctions, relevées par `ast` le 13/09 : `init_database`,
`add_riddle_participant`, `add_riddle_winner`, `get_or_create_user`,
`has_user_interacted`, `get_user_interactions`, `log_interaction`, `get_reputation`,
`add_reputation`, `add_riddle_streak`, `reset_riddle_streak`, `get_riddle_streak`,
`get_reputation_leaderboard`, `set_birthday`, `get_todays_birthdays`,
`get_daily_quests`, `create_daily_quests`, `complete_quest`, `get_config`, `set_config`,
`log_event`, `get_recent_logs`, `log_bot_interaction`, `get_bot_interaction_stats`,
`log_error_event`, `get_error_events`, `get_reactions_repliques`,
`get_conversation_stats`, `set_active_riddle`, `get_active_riddle`,
`get_all_active_riddles`, `delete_active_riddle`, `is_riddle_duplicate`,
`add_to_riddle_history`, `get_game_cooldown`, `set_game_cooldown`,
`get_game_daily_points`, `add_game_daily_points`, `get_game_pvp_cooldown`,
`set_game_pvp_cooldown`.

### Verrous attendus (lot 2)

1. **Mesure AVANT/APRÈS, dans le conteneur** — c'est elle qui décide si le défaut est
   réellement celui qu'on croit :
   `docker exec bot-maiq sh -c 'for f in /proc/[0-9]*/fd/*; do readlink "$f"; done | grep -c bots_database.db'`
   Relever le chiffre **avant** le correctif et **24 h après** déploiement. Il vaut 1
   par bot sur une instance fraîche (mesuré le 13/09 à 16 min d'uptime) : la fuite ne se
   voit qu'avec de la durée.
2. **Verrou AST**, dans `tests/test_base_partagee.py` : *aucune* fonction de
   `shared_database.py` n'appelle `get_connection()` sans que la fermeture soit
   couverte par un `finally` ou un `with`. **Jamais une regex** (voir le gotcha
   « des appels fournisseur HORS cascade »).
3. **Un test de fuite qui reproduit le chemin d'erreur** : une base rendue illisible, la
   fonction appelée, et on vérifie que la connexion est fermée. Sans le correctif, il
   échoue.

---

## Ce qu'il ne faut PAS faire

- **Ne pas toucher aux `except: pass` de `_empiler` et de `ErrorEventHandler.emit`.**
  Ils sont **voulus** et commentés : un journal ne doit jamais faire tomber `on_message`,
  et la file est bornée exprès. Le lot 1 rend audible le thread **écrivain**, pas les
  producteurs (voir « un défaut peut être une fonctionnalité »).
- **Ne pas reposer WAL**, sous aucun prétexte, ni ici ni dans une copie vendorisée.
  Deux tests l'interdisent déjà.
- **Ne pas fusionner les deux lots en un commit.** Ils portent sur deux fichiers et deux
  défauts sans rapport ; le lot 2 est un refactor de 40 fonctions qu'on doit pouvoir
  relire seul.

## Déploiement

- `shared/bot_logger.py` est **vendorisé** : après correction, relancer
  `python tools/vendor_core.py`, puis `python tools/sonde_core_drift.py` — les 6 copies
  `*/core/bot_logger.py` doivent être identiques, et les deux listes de vendoring aussi.
- `shared/shared_database.py` n'est **pas** vendorisé : il est bind-monté, un
  `docker restart` suffit.
- **Vérifier DANS le conteneur**, jamais depuis l'hôte, et borner tout `docker logs`
  avec `--since <ISO>Z` (sans le `Z`, le filtre est lu en heure locale et ne filtre rien).
- Compter **6 bots**, pas 5.
