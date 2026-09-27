# PLAN — SUITE 11 : Alfred et Sheogorath n'apparaissent jamais dans le graphe d'activité

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Plan précédent (SUITE 10-bis, livré `0dbe93e`) lisible dans git
(`c665a7c:PLAN.md`).

Fichiers : `Sheogorath/bot_sheogorath.py`, `Alfred/bot_alfred.py`, un test neuf. Aucun
appel API. Redémarrage de deux conteneurs.

---

## LE CONSTAT (vérifié par Claude le 27/09, dashboard ouvert dans Chrome)

Le graphe « Activité Globale (24h) » lit la table `interactions` de
`data/bots_database.db` (`dashboard/backend/conversation_analyzer.py` l.70–98). Cette
table n'est remplie que par `shared.shared_database.log_interaction` (l.505), et seuls
**quatre** bots l'appellent :

| bot | appel | condition |
|---|---|---|
| Johnny | `bot_johnny.py` l.929 `log_interaction(message.author.id, "Johnny", "mention")` | `DATABASE_AVAILABLE and not is_dm` |
| M'aiq | `bot_maiq.py` l.1332 `log_interaction(message.author.id, "M'aiq", "message")` | `DATABASE_AVAILABLE`, dans un `try` |
| Sugar | `bot_sugar.py` l.788 | — |
| Malena | `bot_malena.py` l.871 | — |
| **Sheogorath** | **aucun** | — |
| **Alfred** | **aucun** | — |

Dans la table : 345 lignes, **zéro** pour Alfred et Sheogorath, alors que Sheogorath est
le bot le plus sollicité. Le graphe et la tuile « Utilisateurs » sous-estiment l'activité
sans que rien ne le signale.

**Horodatage vérifié** : `log_interaction` écrit `datetime.now()` et les six conteneurs
tournent en **UTC** (`time.tzname == ('UTC','UTC')`, vérifié le 27/09), ce que
`get_activity` suppose. Rien à changer de ce côté.

---

# LOT 1 — Sheogorath

**Fichier** : `Sheogorath/bot_sheogorath.py`.

1. **Import** (l.131–134) : ajouter `log_interaction` à la liste importée de
   `shared.shared_database`, dans le `try` existant. Le `except ImportError` (l.153)
   couvre déjà le cas où `shared/` manque (`DATABASE_AVAILABLE = False`) : ne rien y
   changer.
2. **Appel** : dans `on_message`, juste **après** la ligne
   `last_exchange[message.channel.id] = (message.author.id, time.time())` (l.2179), qui
   suit `if not should_respond: return` (l.2167). À cet endroit, Sheogorath a décidé de
   répondre, quelle que soit la branche (mention, nom, continuité, proactivité, mot-clé) :

   ```python
   # ⚠️ Le graphe « Activite globale » du dashboard ne lit que `interactions`, et
   # Sheogorath n'y ecrivait jamais (constate le 2026-09-27) : il etait invisible.
   if DATABASE_AVAILABLE and message.guild:
       try:
           get_or_create_user(message.author.id, message.author.name, message.author.display_name)
           log_interaction(message.author.id, "Sheogorath",
                           "mention" if (is_mentioned or is_reply or has_name) else "message")
       except Exception as e:
           logger.warning(f"⚠️ [DB] log_interaction a echoue : {e}")
   ```

   - `message.guild` : comme Johnny, pas de DM dans le graphe d'un serveur.
   - Le `try/except` avec un journal : la base ne doit **jamais** empêcher une réponse, et
     un `except` muet est interdit par `tests/test_except_muet_documente.py`.
   - `get_or_create_user` est **déjà** importé chez Sheogorath (l.132).

# LOT 2 — Alfred

**Fichier** : `Alfred/bot_alfred.py`.

1. **Import** (l.90–92) : ajouter `get_or_create_user` **et** `log_interaction` à la liste
   importée de `shared.shared_database` (aucun des deux n'y est aujourd'hui), dans le `try`
   existant.
2. **Appel** : dans `on_message`, juste **après**
   `alfred_brain.update_user(message.author.id, message.author.name, topic=message.content[:20]+"...")`
   (l.1698, sous le commentaire `# SAVE INTERACTION`, qui suit `if not should_respond: return`
   l.1694). Même bloc que pour Sheogorath, avec `"Alfred"` et
   `"mention" if (is_mentioned or is_reply or is_name_mentioned) else "message"`.

⚠️ **Le nom écrit** : `"Sheogorath"` et `"Alfred"`, en toutes lettres. Les quatre autres
écrivent `"Johnny"`, `"M'aiq"`, `"Sugar Bot"`, `"Malena"` : ne pas les harmoniser ici, le
dashboard lit les noms tels quels (`SELECT … FROM interactions`, sans filtre par nom
dans `get_activity`).

# LOT 3 — Le verrou

**Fichier neuf** : `tests/test_six_bots_journalisent_les_interactions.py`.

Pour **chacun des six** fichiers, listés **en dur** (pas découverts par glob : un bot qui
manquerait à la découverte passerait le test,
[[gotcha-un-bot-sur-six-manque-toujours]]) :

```
Alfred/bot_alfred.py, Sheogorath/bot_sheogorath.py, MaiqBot/bot_maiq.py,
JohnnyBot/bot_johnny.py, SugarBot/bot_sugar.py, MalenaBot/bot_malena.py
```

vérifier **par l'AST** (`ast.parse`, puis `ast.walk` à la recherche d'un `ast.Call` dont
`func` est un `ast.Name` d'`id == "log_interaction"`), pas par une recherche de texte : un
commentaire ou une chaîne contenant « log_interaction » ne doit pas suffire
([[gotcha-verrou-trop-faible]]). Le message d'échec nomme le fichier fautif.

Vérifier que le test **échoue** si on retire l'appel chez Sheogorath (le faire une fois à
la main, puis remettre), et le dire dans le compte rendu.

# LOT 4 — Livrer

1. `python -m pyflakes Sheogorath/bot_sheogorath.py Alfred/bot_alfred.py tests/test_six_bots_journalisent_les_interactions.py`
   (pyflakes attrape un nom importé mais non utilisé, ou utilisé mais non importé).
2. pytest ciblé, puis la suite complète (**jamais deux pytest en parallèle**, port 8599).
   ⚠️ Les tests ne doivent pas écrire dans `data/bots_database.db` : garde `DATA_DIR`
   ([[gotcha-pytest-pollue-data]]).
3. Commit `fix(dashboard): Alfred et Sheogorath journalisent leurs interactions (SUITE 11)`.
   Push, **`gh run list` jusqu'au vert**.
4. `docker restart bot-sheogorath bot-alfred`, **hors live**. Vérifier que le code est dans
   les conteneurs (`MSYS_NO_PATHCONV=1 docker exec bot-sheogorath grep -c "log_interaction" /app/bot/bot_sheogorath.py`,
   ≥ 2 ; idem Alfred) et `docker logs --since 5m` sans erreur sur les deux.

# LOT 5 — [Ahmed] Vérifier en vrai

Envoyer un message qui mentionne Sheogorath, puis un qui mentionne Alfred, sur le serveur.
Ensuite, en **lecture seule** :

```
python -c "import sqlite3;c=sqlite3.connect('file:data/bots_database.db?mode=ro',uri=True);print(c.execute(\"select bot_name,interaction_type,timestamp from interactions order by id desc limit 3\").fetchall())"
```

Deux lignes `Sheogorath` / `Alfred` de type `mention` doivent apparaître, et le graphe du
dashboard doit montrer un point à l'heure courante.

**Critère de clôture** : tests et CI verts, conteneurs redémarrés sans erreur, les deux
lignes vues dans `interactions`.
