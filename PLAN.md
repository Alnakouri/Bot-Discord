# PLAN — Fiabiliser la suppression des rôles de décret (Sheogorath)

> **STATUT : IMPLÉMENTÉ par Claude 2026-06-21** (Antigravity n'avait rien écrit
> dans le repo malgré 2 tentatives → fait directement). `py_compile` OK.
> Reste : **test live manuel** (§6) + commit.

---

## 0. Bug corrigé

Un rôle de décret restait actif indéfiniment (constat user : encore là après
2 jours, durée prévue = 10 min). Cause : dans `Sheogorath/sheo_decrees.py`,
`apply_decree_role` programmait la suppression via
`asyncio.create_task(delayed_cleanup)` (`sleep(600)` → `role.delete()`), tâche
**en RAM** détruite à chaque redémarrage du bot ; et `cleanup_old_decree_roles`
était un **stub vide** (`pass`). → rôle orphelin éternel, aucun rattrapage.

Solution : **persister** les décrets actifs (JSON local, patron
`sheo_punishments.json`) + un **filet périodique** (`tasks.loop`) qui supprime
les rôles expirés/orphelins même après un redémarrage.

---

## 1. Changements réalisés — `Sheogorath/sheo_decrees.py`

- **Imports** : ajout `json`, `time`.
- **Store persistant** (clé = `str(role_id)`), dans `DATA_DIR` (env, même volume
  que `sheo_punishments.json`) → `DECREES_FILE = sheo_decrees_active.json` :
  - `_load_decrees()` / `_save_decrees()` (**écriture atomique** : tmp + `os.replace`)
  - `_add_decree(entry)` / `_remove_decree(role_id)`
  - schéma d'entrée : `{role_id, guild_id, title, expire_at}` (`expire_at = time.time()+duration`).
- **`apply_decree_role`** : signature **inchangée** (`guild, member, title, duration=600`).
  Après l'assignation : `_add_decree(...)`. La tâche `delayed_cleanup` best-effort
  est conservée (cas nominal sans redémarrage) mais : gère désormais
  `discord.Forbidden`, et **purge le store** (`_remove_decree`) dans un `finally`.
- **`cleanup_old_decree_roles(guild)`** (remplace le stub ; signature changée,
  `days` retiré — aucun appelant existant) :
  1. parcourt le store → supprime les rôles **expirés** de cette guild, purge les
     entrées (sur `Forbidden` : on ne purge pas, retry au tick suivant) ;
  2. **filet par-nom** : supprime les rôles `📜` **absents du store** (orphelins
     créés avant ce mécanisme → nettoie le rôle actuellement bloqué) ;
  3. collecte `tracked_ids` (toutes guilds) pour ne jamais supprimer par le filet
     par-nom un décret encore valide ;
  4. `NotFound`/`Forbidden`/`Exception` gérés partout ; sauvegarde si modifié.

## 2. Changements réalisés — `Sheogorath/bot_sheogorath.py`

- **Import** : `cleanup_old_decree_roles` ajouté aux deux branches
  (`from sheo_decrees import …` ET le fallback `from Sheogorath.sheo_decrees …`).
  *Bonus* : le fallback Discloud **n'importait pas du tout `sheo_decrees`**
  (gap préexistant qui aurait planté `apply_decree_role` en mode Discloud) →
  corrigé (ajout `generate_decree_image, apply_decree_role, cleanup_old_decree_roles`
  + `add_reputation`).
- **Boucle** `@tasks.loop(minutes=5) decree_cleanup_loop` + `@before_loop`
  `wait_until_ready` (définie après le bloc resume des punitions).
- **Démarrage** dans `on_ready` avec garde :
  `if not decree_cleanup_loop.is_running(): decree_cleanup_loop.start()`.
  Le 1er tick s'exécute peu après le ready → l'orphelin actuel part en quelques
  secondes (granularité ≤5 min en régime).

## 3. Changements réalisés — `.gitignore`

- Ajout `sheo_decrees_active.json` (donnée runtime, comme `sheo_punishments.json`).

---

## 4. Vérifications passées (Claude)

- `python -m py_compile Sheogorath/sheo_decrees.py Sheogorath/bot_sheogorath.py` → **OK**.
- Symboles présents : `_load_decrees/_save_decrees/_add_decree/_remove_decree`,
  `sheo_decrees_active`, `os.replace`, `decree_cleanup_loop`,
  `cleanup_old_decree_roles`.
- `cleanup_old_decree_roles` ne contient plus `pass` seul.
- `.gitignore` couvre le nouveau JSON.

---

## 5. Reste à faire (manuel)

1. **Commit** (sur accord user).
2. **Déployer** Sheo (rebuild conteneur) → au démarrage, l'orphelin actuel est
   nettoyé automatiquement (filet par-nom). *(Sinon : suppression manuelle
   Paramètres serveur → Rôles.)*

## 6. Recette de test (live, après déploiement)

1. `!decret` (admin) → rôle `📜` apparaît + entrée dans `sheo_decrees_active.json`.
2. **Redémarrer Sheo** avant l'expiration (simule le bug d'origine).
3. À l'échéance (+ ≤5 min de marge boucle) → le rôle **disparaît seul** et
   l'entrée JSON est **purgée**.
4. Créer un rôle `📜` bidon à la main → nettoyé au tick suivant (filet par-nom,
   loggé en `info`).

## 7. Hors périmètre

- Pas de migration vers SQLite (JSON local = cohérent + indépendance Sheo).
- Durée par défaut (600 s) et apparence du décret inchangées.
- Aucun autre bot que Sheogorath.
