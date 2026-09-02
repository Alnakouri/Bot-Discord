# PLAN — finir la fiabilisation des tests de commandes (2 points)

Suite du plan précédent, **exécuté et relu le 02/09**. Le travail livré est bon :

| Vérification | Résultat |
|---|---|
| `git diff --stat` | `tests/` + `PLAN.md` seuls, **aucun fichier de bot** ✅ |
| Les 3 tests branchés sur `conftest.BOT_FILES` | ✅ (ancré sur `Path(__file__)`) |
| Les 3 portent `assert len(bot_files) == 6` | ✅ |
| Mutation : `raise ImportError` en tête de `bot_sugar.py` | ✅ ROUGE, **nomme Sugar + l'erreur** |
| Mutation : `MalenaBot/` renommé | ✅ les 3 ROUGE |
| Suite complète depuis la racine | ✅ **533 passed**, exit 0 |

**Ne rien défaire de tout ça.** Il reste deux finitions, toutes deux **prouvées par
mutation ou par exécution réelle**, toutes deux **dans `tests/` uniquement**.

Exécution : Antigravity. Rédaction : Claude.

---

## Point 1 — le bot sauté faute de `on_command_error` est encore **anonyme**  🟠

### Preuve (mutation faite le 02/09, pas supposée)
`on_command_error` renommé en `on_command_error_MUT` dans `JohnnyBot/bot_johnny.py:199`.
Le test tombe bien au ROUGE — le compte fait son travail — mais il dit :

```
AssertionError: Seulement 5 bots testes. Echecs: []
```

**« Echecs: [] » alors qu'un bot manque.** On apprend qu'il en manque un, jamais **lequel**
ni **pourquoi**. C'est précisément ce que le plan précédent demandait d'éviter (« le message
d'erreur compte »). La raison : `tests/test_erreurs_commandes.py:41`

```python
if not hasattr(module, 'on_command_error'):
    continue
```

est un `continue` **muet** — il ne nourrit ni `tested_bots` ni `failed_bots`. Le chemin
« import cassé » a été instrumenté, celui-ci non.

### Correction demandée
1. Nourrir `failed_bots` sur ce chemin aussi, avec un motif distinct de l'échec d'import —
   p. ex. `"pas de on_command_error"` vs le message d'exception. Les deux causes doivent
   rester **distinguables** dans le message final : « il n'a pas la fonction » et « il ne
   s'importe plus » ne se réparent pas pareil.
2. Ne pas se contenter du compte dans le message final : lister **les bots manquants
   nommément**, en dérivant `set(bot_files) - set(tested_bots)` plutôt qu'en se fiant à ce
   que la boucle a bien pensé à enregistrer. Un bot perdu par un `continue` ajouté demain
   sera nommé sans qu'on ait à y penser.

⚠️ Garder le parcours tolérant *pendant* la boucle (bilan complet des 6) et l'échec **à la
fin** : c'est ce qui marche aujourd'hui.

### Vérification par mutation (obligatoire)
Renommer `on_command_error` chez Johnny (`bot_johnny.py:199`) → le test doit être **ROUGE**
et **nommer Johnny** *et* la raison. Puis remettre le fichier en état
(`git diff --stat JohnnyBot/` doit être vide).

---

## Point 2 — la DoD « suite verte depuis `tests/` » n'est **pas** tenue  🔴

### Preuve (exécution réelle, pas une supposition)
`python -m pytest .` lancé **depuis `tests/`** :

```
1 failed, 526 passed, 6 skipped, 46 subtests passed
FAILED test_suivi_api.py::test_9_malena_utilise_meme_fonction
E   FileNotFoundError: [Errno 2] No such file or directory: 'MalenaBot/bot_malena.py'
```

⚠️ **Ce n'est PAS une régression du plan précédent.** `tests/test_suivi_api.py:194` est
**antérieur** et porte la même maladie que les tests qu'on vient de soigner :

```python
with open("MalenaBot/bot_malena.py", "r", encoding="utf-8") as f:
```

Chemin relatif au CWD. Vérifié par grep : c'est le **seul** autre cas de tout `tests/`.

### Correction demandée
Ancrer ce `open()` sur la racine du dépôt. Deux façons acceptables, au choix :
- réutiliser `BOT_FILES` de `conftest.py` en y sélectionnant Malena ; ou
- ancrer localement sur `Path(__file__).resolve().parent.parent`, comme
  `tests/test_documentation.py:25`.

⚠️ Ne toucher **que** ce test : le reste de `test_suivi_api.py` est vert et hors sujet.
Ne pas modifier `MalenaBot/`.

### Vérification (obligatoire)
Relancer la suite **depuis `tests/`** : **0 failed**. Puis depuis la racine : toujours vert.

---

## Definition of done

- [ ] `python -m pytest` vert **depuis la racine**, lancé **SEUL** — ⚠️ deux pytest en
      parallèle font échouer `tests/test_dashboard_restart.py` (port fixe **8599**) ;
      ce n'est pas une régression.
- [ ] `python -m pytest .` vert **depuis `tests/`** — c'est le point qui échoue aujourd'hui.
- [ ] Mutation du point 1 rejouée, et **le dire explicitement** (message obtenu recopié).
- [ ] Aucun fichier de bot modifié : `git diff --stat` ne montre que `tests/` (+ `PLAN.md`).
- [ ] **CI verte** après push. ⚠️ Ne jamais annoncer « c'est bon » avant de l'avoir vue verte.
