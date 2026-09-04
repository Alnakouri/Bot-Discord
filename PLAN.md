# PLAN — audit des 6 bots : lot execute, revu, corrige

Redaction : Claude. Execution : Antigravity. **Revue et reparation : Claude, le 2026-09-05.**

Suite de l'audit du 2026-09-04 (« trouver la cause de tous les problemes »). Le lot a ete
execute par Antigravity, **relu avant commit** comme le veut la regle — et la relecture a
trouve de quoi remplir cette page.

---

## Etat : vert, non commite  🟢

**621 tests, `exit=0`, aucun nom indefini (`pyflakes`), aucune derive du noyau.**
5 mutations passees, 5 rouges pour la bonne raison. Reste : commit, CI, deploiement,
validation live.

---

## Ce que la relecture a trouve dans le lot livre  🔴

Le lot **ne compilait pas**. Trois familles de degats, toutes du meme geste : une
suppression **par motif textuel** au lieu d'une suppression par structure.

| # | Degat | Portee |
|---|---|---|
| 1 | 193 `except` muets convertis **a l'aveugle** | 29 fichiers |
| 2 | `SyntaxError` : la signature gardait une virgule orpheline | **11 fichiers** |
| 3 | 22 noms indefinis apres la suppression d'OpenRouter | 12 fichiers |

### 1. Les 193 logs aveugles — retires  ⚠️

Le plan disait : *« Ne PAS tous les convertir a l'aveugle. Les passer en revue un par
un. »* Ils l'ont tous ete, avec le meme message :

    logger.debug("Exception silencieuse ignorée dans healthcheck.py")

⚠️ **Ce message ne porte pas l'exception.** Il dit qu'il s'est passe quelque chose, jamais
quoi : exactement le defaut qu'on voulait corriger, avec une ligne de log en plus.

⚠️ **Pire : `logger` n'existe pas dans 29 de ces fichiers.** `pyflakes` en comptait **62
occurrences** — `dashboard/backend/relauncher.py` (le bouton de redemarrage),
`shared/twitch/connection.py`, les 6 `core/models.py`, les sondes. Un `except` silencieux
mais inoffensif devenait un `NameError` **leve depuis le gestionnaire d'exception**.

→ Les 193 lignes sont retirees (169 seules, 24 en ligne restaurees en `except X: pass`).
Le sujet reste ouvert, cf. plus bas.

### 2. Les 11 `SyntaxError` — reparees

`openrouter_client=None,` a ete supprime en laissant `,` seul sur sa ligne dans les **7**
cascades, un `try:` sans corps chez Alfred et M'aiq, une liste `SOCLE` sans crochet
fermant, et une ligne coupee en deux dans une sonde.

Meme geste dans `tests/test_crypto_roundtrip.py` : la fixture a ete supprimee **parce
qu'elle citait la chaine `OPENROUTER_API_KEY`**, et le test s'est mis a lire une variable
qui n'existait plus.

### 3. Les 22 noms indefinis — reparees

Les signatures ont ete nettoyees, **pas les corps ni les appelants** : `self.openrouter_client
= openrouter_client` survivait dans `discord_profile`, `discord_status` et
`twitch_announcer` ; `key_manager.register_api("openrouter", …)` chez Johnny et Sugar.

---

## Deux bugs ANTERIEURS au lot, exhumes par la relecture  🔴

### A. NVIDIA n'avait jamais servi un seul message

Le 4e fournisseur a ete ajoute le 04/09. `get_model_cascade()` rend bien `nvidia` en
dernier echelon **pour les six personas**. Il n'a pourtant jamais repondu :

* **Sheogorath, Alfred, M'aiq et Malena** portent leur cascade **INLINE** dans
  `on_message`. Le lot du 04/09 n'a cable que `shared/llm_cascade.py` et ses 6 copies
  vendorisees. Ces quatre-la n'avaient **aucune** branche `client_type == "nvidia"` :
  l'echelon tombait dans le vide, **sans un mot dans les logs**.
* **Johnny et Sugar** passent par le noyau, mais n'importaient pas `NVIDIA_BASE_URL`. La
  construction du client levait un `NameError` **avale par son propre `except`**.

⚠️ Le health check annoncait « NVIDIA : Oui » sur les six — il regarde **la cle**, jamais
le cablage. C'est ce qui a fait croire au 04/09 que le fournisseur etait en service.

⚠️ **C'est la cause commune de l'audit sous sa forme la plus pure** : un correctif pose
dans `shared/` ne descend pas dans les quatre cascades recopiees.

→ **Cable dans les 4**, avec `nvidia_kwargs()` (sans lui nemotron recite sa pensee et met
six fois plus de temps), le filet `_fuite_de_raisonnement()` et la garde `_est_vide()`.
Alfred, M'aiq et Sheo **n'avaient ni l'un ni l'autre** : ils les **importent** du noyau au
lieu d'en faire une 8e copie. Verrouille par `tests/test_nvidia_cable_partout.py`.

### B. EventSub Twitch ne pouvait pas demarrer

`shared/twitch/eventsub_bridge.py` passe `nvidia_client=` a `TwitchEventSub(...)` depuis
`4292cf0`, mais la signature ne l'a **jamais** eu : `TypeError` a la construction. Le corps
affectait `self.nvidia_client` a partir d'un nom inexistant. → signature corrigee.

### C. Deux appels a un `generate_response` jamais importe

Le `_daily_llm_call` d'Alfred et celui de M'aiq appelaient `generate_response` sans que le
nom existe dans le module : `NameError` a chaque lecture du jour. → import ajoute (il
venait de toute facon avec les gardes).

---

## La decision qui restait a prendre : OpenRouter est RETIRE  ✅

C'etait la question ouverte n°1 de l'audit. Reponse : **retire**, et fige par
`tests/test_openrouter_est_retire.py` (5 tests).

Le motif n'est pas le menage, c'est un **piege arme** : `_fuite_de_raisonnement()` — la
garde qui a empeche Malena de reciter son raisonnement en Discord — n'etait appelee que
dans la branche OpenRouter du noyau. Le jour ou quelqu'un remettait OpenRouter dans une
cascade, les cascades inline recitaient leur raisonnement en clair.

⚠️ **Verifie avant de trancher** : le retrait ne coute aucune capacite. La cascade IMAGE
ne rend que `["gemini", "gemini"]` pour les six personas ; la branche OpenRouter
« secours multimodal » n'etait jamais atteinte. Le tool-use agentique de Sheo via
OpenRouter etait mort pour la meme raison — le sien passe par Gemini.

**Les 9 tests qui verrouillaient la branche ont ete retournes, pas supprimes** :

| test | avant | apres |
|---|---|---|
| `test_cascade_reponse_vide` (5) | echelon suivant = OpenRouter | = **NVIDIA** |
| `test_aucun_client_…_ne_dort_sur_un_429` | 6 clients OpenRouter | **6 clients NVIDIA** |
| `test_timeout_media` | media porte par gemini **et openrouter** | **gemini seul** |
| `test_sheo_images` | payload multimodal OpenRouter | **payload Gemini** |

---

## L'autre decision : la garde anti-incrustation de Sheogorath  ✅

Livree par Antigravity, verifiee : `_other_bot_in_focus` est desormais dans les **6**.

---

## Ce qui reste ouvert

### Les 46 `except` muets — a refaire, une par une

Le sujet n'est pas clos, il est **remis a zero**. Ce qu'il faut, et que la conversion
aveugle n'a pas fait :

1. **Porter l'exception** : `except Exception as e:` puis `logger.debug(f"… : {e}")`.
   Un log sans l'erreur ne sert a rien.
2. **Verifier qu'un `logger` existe** dans le fichier — 29 n'en ont pas.
3. **Laisser muets ceux qui doivent l'etre**, avec un commentaire qui le dit (un
   `_chrono.fin()` ne doit jamais casser une reponse).

Ce n'est pas un travail de motif textuel. C'est 46 lectures.

### Validation live

Rien de tout ceci n'a tourne en vrai. En particulier :

* **`🟩 [NVIDIA` doit enfin apparaitre** dans les logs des 6 bots. C'est la preuve que le
  4e fournisseur existe. Il est en dernier echelon : invisible tant que les 3 autres
  repondent.
* Le reste de la dette de validation live est inchange.

---

## Regles de travail — celles qui ont paye aujourd'hui

- ⚠️ **Relire ce qu'Antigravity a livre avant de commiter.** 11 fichiers ne compilaient
  pas. Un `pytest` suffisait a le voir.
- ⚠️ **`pyflakes` avant `pytest`.** Les 62 `logger` indefinis et les 22 noms orphelins ne
  cassaient **aucun** test : ils n'auraient explose qu'en live, dans un `except`.
- ⚠️ **Ne jamais supprimer du code par motif textuel.** Toute la casse du jour vient de
  la : une virgule orpheline, un `try:` sans corps, une fixture de test effacee parce
  qu'elle **citait** le mot.
- ⚠️ **Un correctif dans `shared/` ne descend pas dans les 4 cascades inline.** NVIDIA
  vient d'en faire la demonstration complete.
- ⚠️ **Un health check qui regarde la cle ne prouve pas le cablage.**
- ⚠️ **Verifier chaque test neuf par MUTATION.** 5 mutations, 5 rouges.
- ⚠️ **Le heredoc du Bash tool detruit les sequences d'echappement** : un `\n` ecrit
  ainsi coupe la chaine en deux. Passer par l'edition de fichier, ou `chr(92)`. Paye une
  fois de plus aujourd'hui.
- Deux `pytest` en parallele font echouer `tests/test_dashboard_restart.py` (port 8599).
- Noms de service compose : `alfred`, `johnny`, `maiq`, `malena`, `sheogorath`, `sugar`.
- Deploiement : le source est **bind-monte**, un `docker restart` suffit.
