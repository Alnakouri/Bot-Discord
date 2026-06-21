# PLAN — Fiabiliser la suppression des rôles de décret (Sheogorath)

> **Pour Antigravity.** Bug confirmé : un rôle de décret reste actif
> indéfiniment (constat user : encore là après 2 jours, alors que la durée
> prévue est 10 min). Cause = le minuteur de suppression est une tâche
> `asyncio` **en mémoire vive**, perdue à chaque redémarrage du bot, et il
> n'existe **aucun rattrapage**. On rend la suppression **durable** sur le
> modèle déjà éprouvé de `sheo_punishments.json` (qui survit aux redémarrages).

---

## 0. Diagnostic (NE PAS dévier)

Fichier : `Sheogorath/sheo_decrees.py`.

- `apply_decree_role(guild, member, title, duration=600)` :
  1. crée un rôle `📜 <TITRE>`, le place sous le rôle du bot, l'assigne ;
  2. programme la suppression via
     `asyncio.create_task(delayed_cleanup())` → `await asyncio.sleep(duration)`
     puis `role.delete()`.
- Appelé **sans `duration`** dans `bot_sheogorath.py` (~ligne 818) → 600 s (10 min).
- **Faille** : `create_task` vit uniquement en RAM. Reboot/rebuild/crash du
  conteneur Sheo pendant les 10 min → la tâche est détruite, `role.delete()`
  n'arrive jamais → rôle **orphelin éternel**.
- **Pas de filet** : `cleanup_old_decree_roles(guild, days=2)` est un **stub vide**
  (`pass`).
- La création du rôle réussit → le bot a bien la permission `Manage Roles` ;
  ce n'est donc **pas** un problème de permission/hiérarchie.

**Objectif** : un rôle de décret est **toujours** supprimé à son expiration,
même si le bot a redémarré entre-temps, et les rôles 📜 déjà orphelins sont
nettoyés automatiquement.

---

## 1. Contraintes & principes

- **Indépendance du bot** : pas de dépendance à `shared/` pour ce mécanisme.
  Le store de décrets est **local à Sheogorath** (fichier JSON dans le dossier
  du bot, comme `sheo_punishments.json`). Cf. règle d'indépendance (AGENTS.md).
- **Persistance volume Docker** : le JSON doit être dans un emplacement
  **monté en volume** et accessible en écriture par l'utilisateur non-root
  (UID 10001). **Vérifier** où vit `sheo_punishments.json` et **utiliser le même
  emplacement / le même helper de chemin** pour rester cohérent (pas réinventer).
- **Idempotence & robustesse** : toute opération Discord (`role.delete`) doit
  gérer `discord.NotFound` (déjà supprimé) et `discord.Forbidden` (logguer, ne
  pas crasher). Ne jamais laisser une exception tuer la boucle.
- **Compat ascendante** : on garde la signature publique
  `apply_decree_role(guild, member, title, duration=600)` (appelée telle quelle
  dans `bot_sheogorath.py`). On change l'intérieur, pas l'interface.
- **Convention tâches** : utiliser `@tasks.loop` (discord.py), pas
  `asyncio.create_task` + `while True` (cf. conventions AGENTS.md).
- **Ne toucher à aucun secret** (`.env`, `.master_key`, `*.db`).

---

## 2. Changements dans `Sheogorath/sheo_decrees.py`

### 2.1 Store JSON des décrets actifs
Ajouter un petit module de persistance (fonctions internes, pas de classe
lourde) :

- Chemin : `DECREES_STORE_PATH` = même dossier/volume que `sheo_punishments.json`
  (réutiliser le helper existant si présent ; sinon `os.path.join(<data>, "sheo_decrees_active.json")`).
- Schéma d'une entrée :
  ```json
  {
    "role_id": 123456789,
    "guild_id": 987654321,
    "title": "PORTEUR DE CUILLÈRES",
    "expire_at": 1718900000   // epoch secondes (time.time() + duration)
  }
  ```
- Helpers : `_load_decrees() -> list`, `_save_decrees(list)`,
  `_add_decree(entry)`, `_remove_decree(role_id)`.
  Écriture **atomique** (écrire dans un `.tmp` puis `os.replace`) pour éviter la
  corruption en cas de crash pendant l'écriture (s'aligner sur ce que fait déjà
  le système de punitions s'il le fait).

### 2.2 `apply_decree_role` — persister + minuterie best-effort
- Après assignation réussie du rôle : **`_add_decree(...)`** avec
  `expire_at = time.time() + duration`.
- Conserver une suppression « best-effort » immédiate (la tâche `asyncio`
  actuelle peut rester pour le cas nominal où le bot ne redémarre pas), MAIS
  dans `delayed_cleanup`, après `role.delete()`, appeler **`_remove_decree(role_id)`**
  pour purger le store. La vraie garantie viendra de la boucle 2.4.
- Gérer `NotFound`/`Forbidden` autour du `delete` (déjà partiellement fait).

### 2.3 `cleanup_old_decree_roles` — implémenter (remplacer le `pass`)
Nouvelle logique (balayage du store, pas du nom de rôle uniquement) :
```
async def cleanup_old_decree_roles(guild):
    now = time.time()
    for entry in list(_load_decrees()):
        if entry["guild_id"] != guild.id:
            continue
        if entry["expire_at"] <= now:
            role = guild.get_role(entry["role_id"])
            if role:
                try: await role.delete(reason="Décret expiré (nettoyage)")
                except discord.NotFound: pass
                except discord.Forbidden: logger.warning(...)
            _remove_decree(entry["role_id"])   # même si le rôle n'existe plus
```
- Garder aussi un filet « par le nom » optionnel : supprimer les rôles dont le
  nom commence par `📜` **et** qui ne sont dans aucune entrée du store (rôles
  créés avant ce correctif = orphelins historiques). **Prudence** : ne supprimer
  que les rôles `📜` créés par le bot ; logguer chaque suppression.

### 2.4 Helper de reprise au démarrage
Ajouter `async def resume_decrees(bot)` (ou `reschedule_decrees`) :
- Pour chaque guild du bot, appeler `cleanup_old_decree_roles(guild)` (supprime
  les expirés, purge le store).
- Pour les entrées **non encore expirées**, soit reprogrammer une tâche
  `asyncio` avec le temps restant, soit **ne rien faire** et laisser la boucle
  périodique (2.4 bis) s'en charger → **préférer la boucle périodique** (plus
  simple, pas de tâches RAM à reconstruire).

### 2.4 bis Boucle périodique (le vrai filet)
Dans `bot_sheogorath.py`, ajouter une `@tasks.loop(minutes=5)` :
```
@tasks.loop(minutes=5)
async def decree_cleanup_loop():
    for guild in bot.guilds:
        await cleanup_old_decree_roles(guild)
```
- Démarrer la boucle dans `on_ready` (après que les guilds sont chargées),
  avec `@decree_cleanup_loop.before_loop` → `await bot.wait_until_ready()`.
- Au premier tick (ou via `resume_decrees` appelé une fois dans `on_ready`),
  les rôles orphelins des redémarrages sont nettoyés au plus tard ~5 min après
  le boot. Granularité acceptable pour des décrets de 10 min ? **Oui** pour le
  rattrapage ; le cas nominal reste précis grâce à la tâche best-effort 2.2.

---

## 3. Changements dans `bot_sheogorath.py`

- Importer les nouveaux symboles depuis `sheo_decrees`
  (`cleanup_old_decree_roles`, `resume_decrees` si créé, et la `tasks.loop` si
  définie côté bot).
- Dans `on_ready` : appeler une fois la reprise + démarrer
  `decree_cleanup_loop` (idempotent : ne pas la relancer si déjà active —
  `if not decree_cleanup_loop.is_running(): decree_cleanup_loop.start()`).
- Ne **pas** modifier l'appel `apply_decree_role(...)` ligne ~818 (signature
  inchangée).

---

## 4. Nettoyage de l'orphelin actuel

Le rôle déjà bloqué (créé avant le correctif) sera capté par le filet « par le
nom » de 2.3 au prochain démarrage **si** on l'active. Sinon, indiquer à l'user
de le supprimer à la main (Paramètres serveur → Rôles). **Décision** : activer
le filet par-nom pour les rôles `📜` orphelins, mais **logguer en `info`** chaque
suppression pour traçabilité.

---

## 5. Vérifications (Antigravity)

1. `python -m py_compile Sheogorath/sheo_decrees.py Sheogorath/bot_sheogorath.py`
   → OK.
2. `cleanup_old_decree_roles` ne contient plus `pass` seul ; signature cohérente
   avec ses appels.
3. `grep -n "create_task(delayed_cleanup" Sheogorath/sheo_decrees.py` → la tâche
   best-effort purge bien le store après delete (ou est retirée si on s'appuie
   uniquement sur la boucle).
4. `@tasks.loop` présente + démarrée dans `on_ready` avec garde `is_running()`
   et `before_loop` → `wait_until_ready`.
5. Écriture du JSON **atomique** (`os.replace`) et au **bon emplacement**
   (même volume que `sheo_punishments.json`, accessible UID 10001).
6. Gestion `discord.NotFound` / `discord.Forbidden` partout où on `delete`.
7. Aucun secret modifié ; aucun autre bot touché (correctif **local Sheo**).

---

## 6. Tests / recette (manuel, après déploiement)

1. Lancer un décret (commande admin `!decret`) → rôle `📜` apparaît.
2. **Redémarrer Sheo** immédiatement (avant 10 min).
3. Attendre l'expiration (+ ≤5 min de marge boucle) → le rôle **disparaît seul**.
4. Vérifier le JSON : l'entrée a été **purgée** après suppression.
5. Créer un rôle `📜` bidon à la main → au prochain tick, il est nettoyé (filet
   par-nom) et loggé.

---

## 7. Hors périmètre

- Pas de migration vers la DB SQLite partagée (JSON local suffit, cohérent avec
  `sheo_punishments.json`, et préserve l'indépendance du bot).
- Pas de changement de la durée par défaut (600 s) ni de l'apparence du décret.
- Aucun autre bot que Sheogorath.
