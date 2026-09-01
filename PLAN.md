# PLAN — 4 défauts remontés par le test live du 2026-09-01

Source : session de test live sur Discord (transcript 16:05 → 18:09). **Aucun de ces
défauts ne vient du commit `664f75c` du jour** — ils sont préexistants. Le test live a
par ailleurs VALIDÉ : carnet de rancunes + rédemption de Sugar, accord au genre,
anti-répétition, décret + image de Sheo, commutation des 4 humeurs, énigme/indice de
M'aiq (le correctif `PermissionError` tient), `!gig`/`!loot`/`!rant` de Johnny.

Exécution : Antigravity. Rédaction : Claude.

---

## ⚠️ Règles de cette exécution (non négociables)

1. **Vérifier chaque nouveau test par MUTATION.** Écrire le test, le voir VERT, puis
   remettre le bug et le voir ROUGE. Un test qui n'a jamais échoué ne prouve rien.
   (Trois faux tests dans une seule session le 31/08 : c'est la leçon la plus chère
   du projet.)
2. **Ne rien déclarer terminé avant que la CI soit verte**, pas seulement pytest local.
3. `shared/` n'est pas touché par ce plan. Si ça devait changer :
   `python tools/vendor_core.py` puis `python tools/sonde_core_drift.py`.
4. Ne pas toucher aux personas, aux prompts, ni aux cascades. Ce plan ne corrige que
   de la **plomberie de commandes**.

---

## Chantier A — Alfred exécute CHAQUE commande deux fois  🔴 le seul grave

### Constat
`!repos` a produit **deux fois** le même message. Alfred est le **seul des 6 bots**
dans ce cas.

### Cause, prouvée par lecture
`Alfred/bot_alfred.py`, dans `on_message` :

| Ligne | Appel | Atteignable ? |
|---|---|---|
| 1314 | `process_commands` dans la branche **maintenance** | oui, puis `return` |
| 1318 | `process_commands` **chemin standard** | **toujours** |
| 1509 | `process_commands` dans la branche **chant** | oui, puis `return` |
| 1561 | `process_commands` si `not should_respond` | **oui** |

1318 et 1561 sont atteignables **dans le même message** : aucun `return` ni garde de
préfixe entre les deux. Toute commande d'Alfred part donc deux fois. Sur `!repos`
c'est cosmétique ; sur `!liberation` et `!nettoyage`, qui sont des actions de
**modération**, c'est une double exécution réelle.

Les 5 autres bots n'appellent `process_commands` qu'**une seule fois** — cf.
`JohnnyBot:816`, `MaiqBot:1080`, `Sheogorath:1769`, `SugarBot:728`, `MalenaBot`.

### Correction demandée
Ramener `on_message` d'Alfred à **exactement un** `await bot.process_commands(message)`.

Ordre à adopter — il préserve le comportement voulu « les commandes admin marchent même
en maintenance » tout en supprimant le doublon :

1. déplacer l'unique appel **AVANT** la vérification du mode maintenance ;
2. la branche maintenance ne fait plus que `return` (supprimer son appel l.1314) ;
3. **supprimer** les appels l.1509 et l.1561 — garder leurs `return`, qui eux sont utiles.

⚠️ Ne pas se contenter de retirer l.1561 : l.1509 crée le même doublon sur la branche
chant.

⚠️ Le commentaire `# Important pour !servir` de l.1561 est **faux** et sera supprimé
avec l'appel : `!servir` marchait déjà via l.1318 — et partait deux fois.

### Test (nouveau fichier `tests/test_commandes_une_seule_fois.py`)
Aucun test n'exerce `on_message` aujourd'hui, et le monter en vrai demanderait une
fausse passerelle Discord. Test **structurel par AST**, qui est ici suffisant parce que
la propriété à garantir est structurelle :

- pour **chacun des 6 bots** : parser le fichier, isoler la fonction `on_message`,
  compter les nœuds d'appel `bot.process_commands` → **exactement 1**.
- Un test de garde qui échoue si la fonction `on_message` est introuvable (sinon un
  renommage rendrait le test vert pour rien — c'est le piège du filtre trop large déjà
  rencontré dans `test_documentation.py`).

**Mutation obligatoire** : remettre un 2e `process_commands` dans Alfred → le test doit
tomber. Puis le retirer.

---

## Chantier B — un bot répond à sa propre commande une 2e fois, en LLM  🟠

### Constat
`!loot` a produit la sortie de la commande, **puis** une seconde réponse de Johnny
générée par le LLM (« Voici le Malorian Arms 3516… »).

### Cause
`JohnnyBot/bot_johnny.py:858` — l'**intervention aléatoire à 10 %** :
`if not should_respond and not is_bot_talking and not has_image_early and random.random() < 0.10:`
Rien n'exclut un message qui est une **invocation de commande**. Le message `!loot` a
donc été traité comme commande, puis tiré au sort pour du bavardage.

Coût : un appel LLM inutile, et un bot qui a l'air buggé.

### Correction demandée
Dans les **6 bots**, juste après l'unique `await bot.process_commands(message)`, sortir
si le message était une vraie commande **de ce bot** :

```python
# Un message qui est une commande de CE bot a deja produit sa reponse :
# il ne doit pas repartir dans le chemin LLM (bavardage aleatoire compris).
ctx = await bot.get_context(message)
if ctx.valid:
    return
```

⚠️ Utiliser `ctx.valid`, **pas** `content.startswith('!')` : les 6 bots partagent le
préfixe `!`, et un `startswith` rendrait chaque bot muet sur les commandes des cinq
autres — alors qu'aujourd'hui il peut légitimement réagir à `!decret` d'un voisin.
`ctx.valid` n'est vrai que pour une commande que CE bot connaît.

### Test (`tests/test_commandes_une_seule_fois.py`, même fichier)
Test structurel AST, pour les 6 bots : dans `on_message`, il existe un accès à
`ctx.valid` (ou `get_context`) **après** l'appel `process_commands`.
Compléter par un test unitaire réel de la logique si Antigravity peut monter un faux
`ctx` sans passerelle — sinon s'en tenir au structurel et **le dire**.

**Mutation obligatoire** : retirer la garde d'un bot → le test doit tomber.

---

## Chantier C — les commandes sans argument échouent en silence  🟡

### Constat
`!servir`, `!parle`, `!reponse`, `!humeur` (seul) n'ont **rien** répondu à
l'utilisateur. Ce ne sont pas des commandes cassées : il leur manquait un argument.

### Cause
Les 6 `on_command_error` sont identiques : ils avalent `CommandNotFound` (correct, cf.
le commit `29a3493`) et **journalisent tout le reste en `logger.error`** — sans jamais
répondre à l'utilisateur.

Deux conséquences : l'utilisateur reste dans le noir, **et** une simple faute de frappe
gonfle le compteur d'erreurs du dashboard au même titre qu'une vraie panne. C'est
exactement le défaut corrigé pour la sonde des clés : *un signal qui crie pour du
nominal est un signal qu'on apprend à ignorer.*

### Correction demandée
Dans les **6** `on_command_error`, avant le `logger.error` final :

```python
if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
    logger.warning(f"[COMMANDE] usage incorrect : {ctx.command} — {error}")
    await ctx.send(<une phrase EN PERSONA rappelant l'usage>)
    return
```

- `logger.warning`, **pas** `error` : une faute de frappe d'utilisateur n'est pas une
  panne du bot.
- La phrase doit être **dans la voix du bot** et contenir l'usage réel, tiré de
  `ctx.command.signature` (ex. Alfred : « Il me faudrait un ordre complet, Monsieur :
  `!servir <action>`. ☕ »). Une phrase par bot, pas un texte générique copié 6 fois.
- Ne rien changer d'autre au gestionnaire : `CommandNotFound` reste avalé en silence,
  tout le reste reste en `logger.error`.

### Test (`tests/test_erreurs_commandes.py`)
Pour les 6 bots, appeler le vrai `on_command_error` avec un faux `ctx` (mock `send`) et
une `MissingRequiredArgument` :
- `ctx.send` est appelé **une fois** ;
- le texte envoyé contient le nom de la commande ;
- rien n'est journalisé en `ERROR` (capturer avec `caplog`).
Puis : `CommandNotFound` → `send` **jamais** appelé, aucun log.

⚠️ **Piège déjà rencontré** : un faux `ctx` trop pauvre fait échouer le code pour une
AUTRE raison et rend le test vert par accident. Le mock doit porter `command`,
`command.signature` et un `send` asynchrone. **Vérifier par mutation.**

---

## Chantier D — collision de commande `!parle` entre Sheo et Alfred  🟠

### Constat
`!parle` a été traité par **Sheogorath**, pas par Alfred.

### Cause
- `Sheogorath/bot_sheogorath.py:1547` : `@bot.command(name="voix", aliases=["parle", "speak", "dis"])`
- `Alfred/bot_alfred.py:587` : `@bot.command(name="parle")`

Les deux bots vivent sur le même serveur avec le même préfixe : les deux répondent.

### Correction demandée — **soumise à l'arbitrage du user, ne pas exécuter sans son accord**
Recommandation : **retirer `"parle"` des alias de Sheo**. C'est le nom **principal**
chez Alfred, alors que ce n'est qu'un alias sur quatre chez Sheo, qui garde `voix`,
`speak` et `dis`. Coût nul pour Sheo, la collision disparaît.

### Test
Ajouter à `tests/test_commandes_une_seule_fois.py` un test **anti-collision généralisé** :
extraire par AST, pour les 6 bots, tous les `name=` et `aliases=[…]` des décorateurs
`@bot.command`, et **échouer si un même mot est revendiqué par deux bots différents**.

⚠️ Ce test vaut plus que le correctif lui-même : il empêche la prochaine collision.
S'il révèle d'autres doublons que `parle`, **les lister sans les corriger** — le
choix de qui garde quoi revient au user.

---

## Hors périmètre, à ne PAS traiter ici

- Le tic d'ouverture « Ah, » de Sheo (modèle `gpt-oss`, mesuré 5/5 par
  `tools/sonde_repartie.py`). Sujet de persona/cascade, pas de plomberie.
- Les réponses vagues de Sheo sur images (« une danse de pixels ») : soupçon que la
  vision ne reçoive rien et que le modèle brode. **À instruire séparément**, ça peut
  être un vrai bug médias comme un simple effet de prompt.
- Statuts/bios, dashboard, décret désactivable, Twitch : non testés à ce jour, ils
  restent dans la dette de validation live.

---

## Definition of done

- [ ] `python -m pytest -q` **vert en local, lancé SEUL** — ⚠️ deux pytest en parallèle
      font échouer `tests/test_dashboard_restart.py`, qui lie le **port fixe 8599**.
      Ce n'est pas une régression.
- [ ] Chaque nouveau test **vérifié par mutation**, et le dire explicitement.
- [ ] `python -m py_compile` sur les 6 `bot_*.py`.
- [ ] `python tools/sonde_core_drift.py` → *No drift detected*.
- [ ] **CI verte** après push.
- [ ] Re-test live minimal : `!repos` d'Alfred → **une** réponse ; `!loot` de Johnny →
      **une** réponse ; `!servir` seul → un message d'usage au lieu du silence.
