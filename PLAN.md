# PLAN — le 429 n'est plus le monstre qu'on croyait, et `on_ready` se sabote a chaque reconnexion

Redaction : Claude. Execution : Antigravity.

Point de depart : la fiche de reprise annoncait comme « prochain chantier » le **429 a
3600 s**, l'**`error_code = 0`** du suivi, et l'hypothese des **6 cles sur un meme
compte**. Avant d'ecrire le plan, j'ai relu le code et interroge `data/api_usage.db`
(261 lignes). **Deux tiers de ce chantier n'existent plus.** Ce qui reste est reel mais
petit, et un defaut plus concret a ete exhume des logs du test live.

⚠️ **Ce plan ne repare aucun incident observe.** Le 429 n'a pas mordu depuis que le suivi
fonctionne. C'est de la prevention sur une mine amorcee ; le lot 2, lui, tourne
aujourd'hui.

---

## Ce que les donnees disent, et qui change le plan  🔵

### Constat 1 — le cooldown de 3600 s ne concerne QUE Gemini

`report_error` a **10 sites d'appel** (hors copies vendorisees), et **tous les dix**
passent `"gemini"` en dur :

```
Alfred/bot_alfred.py:887, :1817
MaiqBot/bot_maiq.py:607, :823, :999, :1537
Sheogorath/bot_sheogorath.py:1364, :2578
shared/llm_cascade.py:245
```

Un 429 de **Mistral, Groq ou OpenRouter n'atteint jamais le gestionnaire de cles.** La
punition d'une heure n'a donc jamais pu tomber que sur une cle Gemini.

### Constat 2 — aucun 429 Gemini depuis que le suivi fonctionne

Les **25** lignes `gemini / 429` de la base datent toutes de l'ere anonyme
(**2026-04-17 → 2026-06-19**, `model = NULL`, `bot_name = 'unknown'`), avant
[[plan-suivi-appels-api]]. Les 429 de l'ere actuelle sont :

| quand | api / modele | bot | consequence reelle |
|---|---|---|---|
| 29-31/08 (x4) | `groq` / `openai/gpt-oss-120b` | sheo | **aucune** — Groq n'appelle pas `report_error` |
| 03/09 (x2) | `mistral` / `mistral-small-latest` | sheo, sugar | **aucune** — idem |

La memoire disait « Mistral a renvoye un 429 a Sheo et un a Sugar, la cle est ecartee une
heure ». **La premiere moitie est vraie, la seconde est fausse.**

### Constat 3 — `error_code = 0` est deja resolu, il n'y a rien a faire

**8 lignes sur 261** portent `error_code = 0`, et **toutes** portent
`raison = 'TimeoutError'` (5 groq, 3 gemini). La colonne `raison`, ajoutee par
[[plan-suivi-appels-api]], repond deja a la question « quota ou timeout ? ». Le reste de
la base porte de vrais codes : 404, 429, 403, 400, 503, 500.

⚠️ **Cette partie du chantier est annulee.** La fiche memoire decrivait un etat anterieur
au correctif qui l'a resolu.

### Constat 4 — les 403 Mistral sont deja fermes, ne pas les rouvrir

7 lignes `mistral-large-latest / 403` (alfred 4, sheo 3) des **29-30/08**. C'est le modele
hors free tier, deja identifie et remplace le 30/08 : `shared/models.py:19` le nomme
`MISTRAL_HORS_TIER`. **Aucune ligne apres le correctif.** Rien a faire, c'est note ici
pour qu'on ne parte pas deux fois a sa poursuite.

### Ce qui reste vrai, et qu'on corrige

`shared/api_manager.py:19` — `cooldown_times[429] = 3600`. **Une heure est une valeur
inventee.** Un 429 Gemini peut vouloir dire « trop de requetes cette **minute** » (RPM) ou
« quota du **jour** epuise » (RPD) : une heure est trop long pour la premiere et trop
court pour la seconde. On devine, alors que **le fournisseur donne la reponse**.

---

## Lot 1 — obeir au delai que le fournisseur annonce, au lieu de le deviner  🟠

`google.genai.errors.APIError` expose `.details` : le JSON de la reponse. Pour un 429,
Google y place un bloc `google.rpc.RetryInfo` avec un `retryDelay` (ex. `"24s"`). C'est la
seule source d'autorite sur la duree.

### Correction demandee

1. Dans `shared/api_manager.py`, `report_error` accepte un argument optionnel
   `retry_delay_s` (defaut `None`).
2. Sur un **429** :
   - `retry_delay_s` fourni → cooldown = cette valeur, **bornee a [5 s, 900 s]** ;
   - absent → **60 s**, pas 3600. Un free tier qui refuse se rouvre en secondes ou en
     minutes, pas en heures.
3. `cooldown_times[429]` disparait au profit de ces deux regles. Les autres codes du
   dictionnaire restent ou ils sont (ils ne servent qu'a reconnaitre l'incident depuis
   `9eb9d2f`).
4. Dans `shared/llm_cascade.py:242-245`, extraire le `retryDelay` de l'exception Gemini et
   le passer a `report_error`. L'extraction doit etre **defensive** : `details` peut etre
   un dict, une liste, ou absent ; un format inattendu rend `None` et on retombe sur les
   60 s. **Aucune exception ne doit sortir de cet extracteur** — il tourne deja dans un
   `except`.

⚠️ **Ne pas etendre `report_error` aux autres fournisseurs dans ce lot.** L'asymetrie du
constat 1 est reelle mais c'est une **decision de design**, pas un bug : la traiter
demanderait de decider ce que « sante d'une cle Mistral » veut dire quand la cascade la
depasse deja toute seule. A poser dans une fiche separee, pas ici.

⚠️ Rappel [[decision-independance-stricte-vendoring-core]] : `api_manager.py` existe en
**7 exemplaires** (`shared/` + `<Bot>/core/` x6). `tests/test_api_manager.py:59` verifie
deja que les 7 portent la meme regle — il **tombera** si les copies ne sont pas
regenerees. C'est voulu.

### Tests demandes
- un 429 **avec** `retry_delay_s=24` → cooldown a 24 s (pas 3600) ;
- un 429 **sans** delai → 60 s ;
- un `retry_delay_s` aberrant (`0`, `-1`, `100000`, `"vingt"`) → borne appliquee, aucune
  exception ;
- l'extracteur rend `None` sur `details` absent / liste vide / JSON inattendu, **sans
  lever** ;
- un cas nominal ou le `retryDelay` de Google est bien lu depuis une structure `details`
  realiste (RetryInfo imbrique dans `error.details[]`).

---

## Lot 2 — `on_ready` rejoue a chaque reconnexion et avorte son propre travail  🔴

Trouve dans les logs du test live du 03/09, sans rapport avec le lot 1.

```
ERROR discord.client Ignoring exception in on_ready
  File "/app/bot/bot_sheogorath.py", line 667, in on_ready
    status_loop_sheo.start()
RuntimeError: Task is already launched and is not completed.
```

`on_ready` **n'est pas un evenement de demarrage** : discord.py le refire a chaque
reconnexion / RESUME du WebSocket. Le premier `.start()` sans garde leve, l'exception
remonte, discord.py l'avale (`Ignoring exception`) — et **tout ce qui suit dans la
fonction n'est jamais rejoue**. Chez Sheo, ce sont les lignes 668 a 868 :
`mood_changer`, `daily_rumor_check_sheo`, `birthday_check_sheo`, `daily_bio_loop_sheo`,
`twitch_poll_loop`, `daily_backup_check`, `check_missed_mentions_sheo`,
`decree_cleanup_loop`.

Compte sur 8 h le 03/09 : **Sheo 4x, Alfred 2x, M'aiq 2x, Johnny 2x, Malena 0, Sugar 0.**

⚠️ **C'est silencieux** : les boucles lancees au tout premier `on_ready` continuent de
tourner, donc le bot a l'air sain. Ce qu'on perd, c'est toute initialisation **posterieure
a la ligne fautive** — un `.start()` conditionnel dont le toggle a change, une boucle morte
entre-temps, et tout ce qu'on ajoutera plus tard a la fin de `on_ready`.

### Correction demandee
1. Sur **chaque** `.start()` de boucle `tasks.loop` appele dans `on_ready`, dans les **6
   bots** : `if not <boucle>.is_running(): <boucle>.start()`.
2. **Le modele a copier existe deja dans le depot** : Malena (`bot_malena.py:474-481`) et
   Sugar (`bot_sugar.py:481-488`) gardent **deja** leurs `.start()` par `is_running()` —
   c'est pour ca qu'elles n'apparaissent pas dans le compte des erreurs. Reprendre leur
   forme telle quelle dans les 4 autres bots.
   ⚠️ Mais elles ne sont pas indemnes : **`twitch_poll_loop.start()` est sans garde chez
   les deux** (`bot_malena.py:500`, `bot_sugar.py:499`). La ligne n'est atteinte que si
   Twitch est actif — meme mine, simplement pas encore amorcee. La corriger aussi.
3. Ne **pas** deplacer les `.start()` hors de `on_ready` (dans `setup_hook`, par exemple) :
   c'est un refactor plus large, hors de ce plan.

### Test demande
Un test par bot, ou un test parametre sur les 6 : appeler `on_ready` **deux fois** et
verifier qu'aucune exception ne sort et que la **derniere** instruction de la fonction a
bien ete atteinte les deux fois. ⚠️ Un test qui verifie seulement « pas d'exception au
2e appel » ne prouve rien de ce qui compte : c'est **l'execution jusqu'au bout** qui est
en cause.

Indice a garder sous le coude, non explique : 5 `MOOD CHANGE` dans la **meme seconde** a
`14:00:40`, juste apres une reconnexion. Probablement lie. **Ne pas partir dessus dans ce
plan** — le noter si le lot 2 l'eclaire au passage.

---

## Regles de travail (rappel)

- **Verifier chaque nouveau test par MUTATION** : retirer le correctif, voir le test
  tomber pour la **bonne** raison. C'est la seule preuve.
- **Ne jamais dire « c'est bon » avant que la CI soit verte** — le local ment sur tout ce
  qui depend de l'environnement (cles API presentes sur la machine).
- Deux `pytest` en parallele font echouer `tests/test_dashboard_restart.py` (port fixe
  8599) : ce n'est pas une regression, relancer seul.
- Deploiement : le source est **bind-monte**, un `docker restart` suffit, pas de rebuild.
