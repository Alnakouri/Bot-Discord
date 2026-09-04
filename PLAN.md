# PLAN — audit de Sheogorath : pourquoi il repond en 10 a 35 secondes

Redaction : Claude. Execution : Antigravity.

Audit demande le **2026-09-04** apres le test live de 13:19-13:20 : « sheo et sugar ont mis
du temps a rep ».

⚠️ **L'horloge des conteneurs est a −2 h.** Le test de **13:19-13:20** en Discord est le
bloc **11:19-11:21** dans les logs et en base. Ne jamais chercher a l'heure de Discord.

---

## Verdict  🔴

**Le prompt de Sheogorath fait 4 505 tokens. Le quota Groq est de 8 000 tokens PAR MINUTE.
Sheo ne peut donc s'offrir qu'UN message par minute.** Le deuxieme prend un 429, que le
SDK Groq absorbe en dormant 7 secondes avant de re-essayer. L'utilisateur attend. Rien
n'est journalise, rien n'est trace.

Ce n'est ni le reseau, ni le modele, ni la cascade, ni un echelon mort.

---

## La preuve, mesuree  🔵

### 1. Le meme modele repond en 287 ms a Johnny et en 34 s a Sheo

Meme cle, meme machine, meme instant, `openai/gpt-oss-120b`, `max_tokens=340`,
`reasoning_effort=low` :

| Prompt systeme | Tokens en entree | Temps mur |
|---|---|---|
| Johnny (`PERSONALITY_PROMPT`, 6 917 car) | 2 189 | **749 ms** puis **287 ms** |
| **Sheo** (`MOOD_PROMPTS["bliss"]`, 14 809 car) | **4 505** | **9 837 ms** puis **34 673 ms** |

Le pire cas mesure (34,7 s) colle au pire cas historique de la base
(`api_calls`, sheo/groq : **max 37 390 ms**).

### 2. Le serveur, lui, travaille 0,22 seconde

Sur l'appel a 11 583 ms, Groq rend ses propres compteurs :

```
prompt_time     = 0,0148 s
completion_time = 0,2074 s      ->  0,22 s de calcul reel
```

**11,4 s des 11,6 s ne sont pas du calcul : c'est de l'attente.** Un prompt tronque de
moitie (2 355 tokens) repond en **635 ms**, avec le meme temps de calcul serveur. La
latence n'est donc pas proportionnelle a la taille : elle bascule d'un coup.

### 3. La bascule, c'est un 429 — invisible parce que le SDK le mange

Avec `max_retries=0`, le voile tombe immediatement :

```
RateLimitError apres 271 ms
  retry-after:                    7
  x-ratelimit-limit-tokens:       8000
  x-ratelimit-remaining-tokens:   3771
  x-ratelimit-reset-tokens:       31.7s
```

⚠️ **Le budget est de 8 000 tokens par minute et par cle. Un seul message de Sheo en
consomme 4 505, soit 56 %.** Deux messages dans la meme minute = 9 010 > 8 000 = 429.
C'est exactement ce que tu as fait pendant le test live.

Le client Groq est construit avec ses reglages par defaut (`max_retries=2`) : il **dort
`retry-after` secondes et recommence, en silence**. D'ou 9,8 s / 11,6 s / 34,7 s.

⚠️ **Les cles ne sont PAS partagees** — verifie, les 6 bots ont des empreintes Groq
distinctes et des compteurs independants ([[regle-une-cle-api-par-bot]] est tenue). Le
probleme est bien la taille du prompt de Sheo, pas une mutualisation.

### 4. Pourquoi personne ne l'a jamais vu

- Le 429 n'apparait **nulle part** : le SDK le rattrape avant que le code le voie.
- `on_message` de Sheogorath **n'appelle jamais `tracer_appel`** : ses appels sont
  **directs, hors `llm_cascade`** (`bot_sheogorath.py:2545` et `:2563`). Pendant tout le
  test live, la table `api_calls` n'a **aucune ligne** pour sheo, alfred et maiq — les
  trois bots dont le chemin conversationnel echappe au noyau.
- Cote logs, un seul jalon : `[ROUTER]` a 11:20:06 puis `⚡ [GROQ] a repondu` a 11:20:18.
  **Douze secondes sans une ligne**, et rien ne dit pourquoi.

### 5. D'ou viennent les 4 505 tokens

`PERSONALITY_BASE` fait **11 242 caracteres (~2 810 tokens) a lui seul**, et il est
**recopie dans les quatre humeurs** :

| Humeur | Total | dont tronc commun | specifique |
|---|---|---|---|
| bliss | 14 809 | 11 242 | 3 567 |
| mania | 14 602 | 11 242 | 3 360 |
| dementia | 13 923 | 11 242 | 2 681 |
| neutral | 13 999 | 11 242 | 2 757 |

⚠️ **Le tronc commun mange 35 % du quota minute a chaque appel, avant d'avoir dit un mot
de l'humeur en cours.** Et `on_message` empile encore ~15 blocs par-dessus (memoire,
faits, faveur, anti-repetition, anti-tics, memes, mentions, transcript).

A titre de comparaison : Johnny 6 917 car, Sugar 8 970, Malena 5 677. **Sheo est le double
du deuxieme.**

---

## Correction demandee  🟠

### 1. Voir le 429 — c'est le prealable a tout le reste

⚠️ **Ne pas commencer par optimiser.** Tant que le 429 est invisible, aucune amelioration
ne sera mesurable.

- Construire **tous** les clients Groq avec `max_retries=0`, dans `shared/models.py` ou au
  point de construction. La cascade est deja le mecanisme de repli : laisser le SDK dormir
  7 s **court-circuite la cascade**, qui aurait bascule sur Mistral ou Gemini en 300 ms.
  ⚠️ C'est le coeur du correctif : **un 429 doit faire descendre la cascade, pas dormir.**
- Journaliser le 429 avec son `retry-after` et son `x-ratelimit-remaining-tokens`.
- Faire remonter le code 429 dans `tracer_appel(code_erreur=429)`.

### 2. Tracer les 3 bots aveugles

Alfred, M'aiq et Sheogorath n'enregistrent aucun appel conversationnel. Appeler
`tracer_appel(...)` autour de chaque appel SDK direct — **strictement additif**, pas de
refonte du chemin LLM.

⚠️ Ne PAS les faire passer par `core.llm_cascade` dans ce lot : Sheo a un post-traitement
maison (`sheo_llm.py`), des outils (`SHEO_TOOLS_DEFINITION`) et une boucle d'appel
d'outils a deux passes. C'est un chantier a part.

⚠️ Verifier ensuite **en base** que les 3 bots apparaissent : c'est le seul moyen de savoir
que le cablage a pris ([[gotcha-import-ajoute-mais-pas-cable]]).

### 3. Degraisser le prompt de Sheogorath

Objectif chiffre : **passer sous 2 000 tokens**, soit ~8 000 caracteres — le niveau de
Johnny, qui repond en 300 ms.

- `PERSONALITY_BASE` (11 242 car) est le seul vrai gisement. Il est recopie a l'identique
  dans les 4 humeurs : le reduire profite 4 fois.
- ⚠️ **C'est une question de PERSONA, pas de technique.** Ne pas tailler a l'aveugle :
  [[feedback-sheo-longueur-densite]] rappelle que la densite se gouverne par le prompt.
  Proposer une version courte et la faire **valider avant** de la deployer.
- ⚠️ **Sonder apres coup** : `tools/sonde_repartie.py` et les criteres de
  [[critere-repartie-modeles.md]] existent pour verifier qu'un Sheo plus court reste Sheo.

### 4. Le chronometre bout-en-bout (le lot precedemment planifie)

Toujours pertinent, et cet audit dit pourquoi : entre `[ROUTER]` et la reponse, il y a eu
**12 secondes sans une seule ligne de log**.

Nouveau `shared/chrono.py`, base sur `time.perf_counter()` (**jamais** `datetime.now()` :
l'horloge des conteneurs derive de 2 h), qui journalise
`⏱️ [CHRONO:sheo] 12 043 ms (contexte 210 | llm 11 780 | postprod 53)` et persiste la
mesure dans une table `reponses` de `data/api_usage.db`, **par l'ecrivain unique existant**
de `shared/api_tracking.py`.

⚠️ Ne jamais lever : tout en `try/except`, un chronometre qui casse `on_message` serait
pire que pas de chronometre. ⚠️ Appeler `fin()` **aussi quand le bot renonce a repondre** —
un abandon a 15 s est precisement le cas invisible aujourd'hui. ⚠️ **6 bots, Malena
comprise.**

---

## Les 5 autres bots : verifie le 04/09  🔵

⚠️ **Sheo n'est pas un cas particulier. Il est juste le premier a taper le mur.**

### Le 429 silencieux est UNIVERSEL — 6 bots sur 6

**Aucun** bot ne construit ses clients avec `max_retries=0` :

```
Alfred/bot_alfred.py:317        Groq(api_key=GROQ_API_KEY)
JohnnyBot/bot_johnny.py:223     Groq(api_key=GROQ_API_KEY)
MaiqBot/bot_maiq.py:250         Groq(api_key=GROQ_API_KEY)
MalenaBot/bot_malena.py:124     Groq(api_key=GROQ_API_KEY)
Sheogorath/bot_sheogorath.py:397 Groq(api_key=GROQ_API_KEY)
SugarBot/bot_sugar.py:373       Groq(api_key=GROQ_API_KEY)
```

Idem pour les clients `OpenAI(...)` d'OpenRouter (12 constructions, toutes par defaut).
**Les six dormiront `retry-after` secondes au lieu de descendre la cascade.**

⚠️ Mistral, lui, **fait remonter ses 429 en 190-390 ms** : ses erreurs sont visibles en
base. C'est bien le SDK Groq (et OpenAI) qui avale l'information.

### Le budget de 8 000 tokens/minute : tous concernes, a des seuils differents

Tokens **reellement mesures** sur la cle de chaque bot (persona seule, `max_tokens=1`) :

| Bot | Tokens | Part du quota | Messages/min avant 429 |
|---|---|---|---|
| **Sheogorath** | **4 505** | **56 %** | **1,8** |
| Alfred | 2 653 | 33 % | 3,0 |
| SugarBot | 2 594 | 32 % | 3,1 |
| JohnnyBot | 2 189 | 27 % | 3,7 |
| MaiqBot | 2 147 | 27 % | 3,7 |
| MalenaBot | 1 903 | 24 % | 4,2 |

⚠️ **C'est un plancher** : `on_message` empile encore ~15 blocs et le transcript par-dessus.
Le seuil reel est donc plus bas partout.

⚠️ Pendant le test live, chaque bot n'a recu **qu'un** message : c'est la seule raison pour
laquelle seul Sheo a souffert. **Deux messages d'affilee au meme bot suffisent a reproduire
le probleme sur n'importe lequel des six.**

⚠️ La lenteur de Sugar ce jour-la n'etait **pas** ce probleme : c'etait un **timeout Gemini
de 15 s** en tete de sa cascade. Deux causes distinctes, ne pas les confondre.

### `on_ready` qui plante a la reconnexion : 3 bots sur 6

Le 04/09 a **11:17:45**, les 6 bots ont rejoue `on_ready` (reconnexion apres une sortie de
veille de l'hote). Trois ont plante :

| Bot | Ligne | Ce que le crash avorte |
|---|---|---|
| **Alfred** | `:417` | les mini-jeux |
| **M'aiq** | `:362` | les mini-jeux **et le rattrapage des enigmes manquees** |
| **Sheogorath** | `:884` | les mini-jeux **et la reprise des punitions** |

Johnny et Malena survivent : ils entourent l'appel d'un `try/except` et journalisent
`[SLASH] Erreur:`. **Sugar fait mieux que tout le monde** — un drapeau `_ready_setup_done`
rend le bloc idempotent, **plus** un `try/except` (`bot_sugar.py:450-466`). C'est le patron
a recopier.

⚠️ **Le `RuntimeError: Task is already launched` de [[bug-on-ready-taches-relancees]] est
bien mort** : plus une seule occurrence apres `839fae5` (les dernieres datent du 03/09
13:59, avant le correctif). C'est `CommandAlreadyRegistered` qui a pris sa place —
**meme mecanisme, meme degat, autre exception**. Le correctif visait les `.start()` ; il
manquait tout le reste de `on_ready`.

---

## Trouvailles annexes, reelles, hors perimetre de la lenteur

### A. `on_ready` de Sheogorath **plante encore** a chaque reconnexion  🔴

```
11:17:45 ERROR Ignoring exception in on_ready
  File "/app/bot/bot_sheogorath.py", line 884, in on_ready
    setup_slash_commands(bot, "Sheogorath")
discord.app_commands.errors.CommandAlreadyRegistered: Command 'reputation' already registered.
```

⚠️ [[bug-on-ready-taches-relancees]] n'est corrige **qu'a moitie**. `839fae5` a mis un
`is_running()` devant les 11 `.start()` de taches, mais `setup_slash_commands` leve
toujours au deuxieme appel — et **avorte tout ce qui suit** :

- `await sync_slash_commands(bot)` — les commandes slash ne sont pas resynchronisees ;
- `setup_games(...)` — **les mini-jeux ne sont pas reinitialises** ;
- **la reprise des punitions** (`RESUME PUNISHMENTS`) — un utilisateur puni pendant une
  reconnexion **ne sera jamais retabli**.

Confirme par les logs : les demarrages de 22:17, 22:18, 05:30 et 07:31 affichent bien
`[GAMES]` et `[PERSISTENCE]` ; celui de **11:17:45 s'arrete net sur la trace**.

Correctif : garder `setup_slash_commands` par un drapeau module (`_slash_deja_pose`), ou
l'entourer d'un `try/except CommandAlreadyRegistered`. ⚠️ **Verifier ensuite les 5 autres
bots** : ils partagent `shared/slash_commands.py`.

### B. Mistral est un echelon mort payé a chaque message

`api_calls` : **17 × 429**, **7 × 403**, **3 × 503** — tous ranges sous le meme
`raison="SDKError"`, qui ne dit rien. Le 429 de Mistral est visible dans les logs de
Johnny et de Sugar **a la meme seconde** pendant le test live.

⚠️ `key_manager.report_error(...)` n'est appele **que pour Gemini**
(`llm_cascade.py:~305`, `bot_sheogorath.py:~2586`). Mistral, Groq et OpenRouter ne sont
donc **jamais** mis en quarantaine : chaque bot re-tente un Mistral sature **a chaque
message**, et paie 200-400 ms pour rien.

⚠️ Enregistrer `raison` a partir du **code HTTP** (`429`, `403`, `503`) et non du nom de
classe du SDK : `SDKError` masque exactement l'information qui aurait designe le probleme.

### C. La rafale de `MOOD CHANGE` est expliquee

17 changements d'humeur en 2 secondes a 11:20:49-50. `mood_changer` est bien un
`@tasks.loop(minutes=5)` unique et garde par `is_running()`.

**C'est un rattrapage de `discord.tasks`** : la boucle recalcule sa prochaine echeance a
partir de la precedente, donc apres une suspension de l'hote elle rejoue toutes les
iterations manquees d'affilee. 17 iterations × 5 min = **85 minutes** — ce qui colle a la
reconnexion de 11:17:45 et au `WebSocket ferme : No PONG received` de 11:18:04, signature
classique d'une machine qui sort de veille.

⚠️ **Sans consequence fonctionnelle** (l'humeur finale reste aleatoire), mais ca pollue les
logs et ca a occupe une ligne « jamais explique » dans [[reprise-en-cours]]. La fermer.

---

## Ce que ce plan ne fait PAS

- Il ne refond pas le chemin LLM d'Alfred, M'aiq et Sheo vers `llm_cascade`.
- Il ne change pas les cascades par persona ([[plan-cascade-par-persona]]) : une fois le
  429 visible et le prompt degraisse, **remesurer avant de decider**.
- Il ne touche pas au dashboard.

## Regles de travail (rappel)

- **Ne jamais dire « c'est bon » avant que la CI soit verte.**
- **Relire ce qu'Antigravity a livre avant de commiter.** Sur le lot precedent, 4 bots sur
  5 etaient casses et un ne compilait meme plus, derriere une suite verte.
- **Verifier chaque test par MUTATION.**
- Deux `pytest` en parallele font echouer `tests/test_dashboard_restart.py` (port 8599).
- Un fichier de test neuf doit etre **suivi par git** (`tests/test_depot_complet.py`).
- Noms de service compose : `alfred`, `johnny`, `maiq`, `malena`, `sheogorath`, `sugar` —
  **pas** `bot-alfred`.
- Deploiement : le source est **bind-monte**, un `docker restart` suffit.
