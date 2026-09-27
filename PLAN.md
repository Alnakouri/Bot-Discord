# PLAN — SUITE 10 : LAYA peut-il reconnaître une VRAIE défaite en répartie ? (mesure seule)

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**, sauf les étapes marquées
**[Claude]** ou **[Ahmed]**. Plan précédent (SUITE 9, livré `917ae22`) lisible dans git
(`0f91b91:PLAN.md`).

**Ce plan ne touche à AUCUN bot.** Il écrit un outil de mesure, le lance, et rend un
tableau. Le branchement éventuel fera l'objet d'un plan suivant, sur les chiffres d'ici.

---

## LE CONTEXTE (vérifié par Claude le 27/09)

**La « phase 3 » (le bot apprend de ses défaites) est DÉJÀ en service** sur les six bots :
`shared/repartee_lessons.py` (`d341fcd`, `2659fdc`, `8f7790b`, `5d36894`), case « Carnet de
repartie » cochée dans le dashboard. La fiche de mémoire qui la disait « perdue » était
périmée.

**Sa limite est écrite dans son code** (`detect_defeat_signal`, docstring l.55+) : elle
reconnaît une **victoire proclamée** (« t'as perdu », « tu te répètes »), pas une **vraie
défaite**. Test live du 2026-09-08 : « les papillons n'ont pas de plume, idiot » prenait
Sheogorath en flagrant délit d'absurdité, et rien ne s'est déclenché. Reconnaître ce
cas demandait « un appel LLM par message ».

**LAYA ne coûte rien par message** (~105 ms en CPU, local, sans clé). Le service
`bots-laya` tourne déjà (`docker-compose.yml` l.126, sans port publié ; `/health`
répond, vérifié le 27/09) et
`shared/journal_decisions.py` l.69–73 le désigne déjà comme candidat pour `DEFAITE`,
« mais on mesure d'abord ». **Décision d'Ahmed du 23/09** : LAYA se mesure avec un critère
fixé d'avance, un repli sur la regex obligatoire, et **la confiance n'est pas un
garde-fou** (0,91 sur une erreur, 0,15 sur une réussite).

**Il n'existe AUCUN corpus de vraies défaites** : `decisions.db` n'a que 7 lignes
`defaite`, toutes `aucune` (Sugar, Twitch, 23–24/09) ; aucune table ne garde le texte des
échanges Discord. D'où deux mesures de valeur différente :

1. **Les faux positifs, sur du RÉEL** : 1 332 messages du chat Twitch journalisés sous
   `jeu_question`, plus 46 autres (`pertinence`, `ton`, `defaite`). Personne ne les a
   écrits pour ce test : c'est la mesure qui compte. Un faux positif coûte cher : il
   brûle une des 6 leçons du jour (`_MAX_PER_DAY`) et fait réécrire au bot une consigne
   de persona sans raison.
2. **Les vraies défaites, sur des cas ÉCRITS par Claude** (ci-dessous) : **indicatif
   seulement**. Un jeu d'essai écrit par celui qui lit le résultat penche de son côté.

**Où LAYA s'insérerait, si la mesure passe** : `bot_sheogorath.py` l.2317 appelle
`detect_defeat_signal` à chaque réponse, et la réflexion part déjà en tâche de fond
(`asyncio.create_task(reflect_on_defeat(...))`). LAYA serait appelé **dans cette tâche**,
seulement quand la regex rend `None` : **zéro milliseconde ajoutée** à la réponse.

---

# LOT 0 — Avant de lancer

1. `docker ps --filter name=bots-laya` : le conteneur tourne. `docker exec bots-laya python
   -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8700/health').read())"`
   répond.
2. Ne lancer **aucun `--help`** d'un script maison : lire le fichier.
3. Rien n'est écrit dans `data/` : `decisions.db` s'ouvre **en lecture seule**
   (`sqlite3.connect("file:data/decisions.db?mode=ro", uri=True)`).

# LOT 1 — L'outil `tools/sonde_laya_defaite.py`

**Principe** : le script tourne sur l'hôte, construit la liste des cas, et les envoie en
**une seule** session `docker exec -i bots-laya python -c "<client>"`, en JSON Lines sur
l'entrée standard. Le client, **dans** le conteneur, poste chaque cas à
`http://localhost:8700/decide` avec `urllib` (pas de dépendance), chronomètre **chaque
appel** avec `time.perf_counter()`, et rend une ligne JSON par cas. Ainsi la latence
mesurée est celle du service, sans le coût de `docker exec`.

**La requête**, exactement celle que `shared/laya_client.choisir` enverrait
(`{"state": ..., "questions": {"defaite": question}}`, `laya_client.py` l.70–72) :

- `state` :
  `Dernière réplique du bot : « {replique} »\nMessage reçu en réponse : « {message} »`
- `question` = `question_choice(...)` de `shared/laya_client.py` (importer la fonction,
  ne pas la recopier) :
  - instructions : `« Que fait ce message face à la réplique du bot ? »`
  - critères, **texte exact** :

| étiquette | ce qu'elle recouvre |
|---|---|
| `pris_en_defaut` | `montre, par un fait ou un argument, que la réplique du bot était fausse, absurde ou se contredisait` |
| `victoire_proclamee` | `proclame que le bot a perdu, est à court d'arguments ou se répète` |
| `aucune` | `tout le reste : une question, une blague, une insulte sans argument, un désaccord sans preuve, du bavardage` |

- Lire la réponse comme le fait `laya_client` : `brut = answers["defaite"]`,
  `etiquette = brut[brut["type"]]`, `confiance = brut.get("confidence")`. ⚠️ `brut` est
  un **dict**, pas une chaîne (`laya_client.py` l.84–87) : comparer le dict entier donne
  0 partout.

**La réplique du bot pour le corpus réel** : les messages du chat n'ont pas de réplique
associée. Chaque message est envoyé **deux fois** :
- `A` : avec `replique = "(aucune)"` ;
- `B` : avec une réplique réelle de Sheogorath, tirée **à tour de rôle** parmi les **trois
  premières** réponses de `COMEBACK_POOL` (`Sheogorath/sheo_data.py` l.10+ : le second
  élément de chaque paire). Ce sont des répliques absurdes par nature : c'est le cas où
  LAYA risque le plus de crier « pris en défaut » à tort.

**Le corpus réel** : `SELECT DISTINCT texte FROM decisions WHERE texte IS NOT NULL AND
trim(texte) != ''`, toutes décisions confondues. Vérifié le 27/09 : **1 267** textes distincts. Noter le nombre obtenu le jour de la
mesure.

**Les cas écrits**, recopiés tels quels dans le script (liste `CAS_ECRITS`, avec l'étiquette
attendue) :

| réplique du bot | message | attendu |
|---|---|---|
| Les papillons ont des plumes d'or, je les ai comptées un mardi. 🦋 | les papillons n'ont pas de plume, idiot | pris_en_defaut |
| Le fromage de Bravil est bleu parce qu'il a peur du noir. 🧀 | le bleu du fromage c'est de la moisissure, pas la peur | pris_en_defaut |
| J'ai trois lunes dans ma poche gauche. 🌙 | t'as dit deux lunes y a cinq minutes | pris_en_defaut |
| Le Soleil tourne autour de mon trône. ☀️ | non c'est la Terre qui tourne autour du Soleil | pris_en_defaut |
| Je n'ai jamais perdu une partie d'échecs. ♟️ | tu viens de perdre contre moi il y a une heure | pris_en_defaut |
| Tous les chats de Nirn parlent latin. 🐈 | M'aiq est un Khajiit et il parle pas latin | pris_en_defaut |
| Le Skyrim est sorti en 1995. 🗡️ | Skyrim c'est 2011 | pris_en_defaut |
| Un pied mesure douze mètres, c'est connu. 📏 | un pied c'est 30 cm | pris_en_defaut |
| Ta mère t'appelle ! 😏 | t'es à court d'arguments là | victoire_proclamee |
| Silence, mortel ! 👹 | je t'ai eu, t'as plus rien à dire | victoire_proclamee |
| Silence, mortel ! 👹 | t'es nul | aucune |
| Les papillons ont des plumes d'or. 🦋 | ferme-la | aucune |
| Le fromage est la clé de l'univers. 🧀 | je suis pas d'accord mais bon | aucune |
| J'ai trois lunes dans ma poche. 🌙 | mdr t'es trop fort | aucune |
| Le Soleil tourne autour de mon trône. ☀️ | tu joues à quoi ce soir ? | aucune |
| Je n'ai jamais perdu aux échecs. ♟️ | ok et alors | aucune |
| Tous les chats parlent latin. 🐈 | c'est faux et tu le sais | aucune |
| Skyrim est sorti en 1995. 🗡️ | n'importe quoi | aucune |

⚠️ Les deux dernières lignes sont **exprès** : un désaccord **sans** fait ni argument
n'est pas une défaite. C'est la frontière que LAYA doit tenir.

**Ce que le script imprime** (et écrit en brut dans le scratch, `suite10_raw.jsonl`,
une ligne par cas avec texte, réplique, étiquette, confiance, latence) :

1. Corpus réel, séparément pour `A` et `B` : nombre de cas, et nombre d'étiquettes
   `pris_en_defaut` et `victoire_proclamee`, **avec chaque message signalé listé en
   entier**.
2. Sur le **même** corpus : combien de messages la regex actuelle
   (`shared.repartee_lessons.detect_defeat_signal(texte)`) signale. ⚠️ Cette fonction
   **écrit dans le journal des décisions** (`journalise`, l.77–78) : la neutraliser pendant
   la mesure (remplacer `shared.journal_decisions.journalise` par une fonction vide avant
   l'appel) pour ne pas polluer `decisions.db` avec 1 267 lignes de sonde.
3. Cas écrits : tableau `réplique | message | attendu | LAYA | confiance`, et le compte
   juste / faux par étiquette attendue.
4. Latence dans le conteneur : médiane, p95, max, sur tous les appels.
5. La confiance est **imprimée**, jamais utilisée pour filtrer.

Docstring du script dans le style de `tools/sonde_laya.py` : ce qu'elle mesure, ce qu'elle
ne prouve pas (les cas écrits sont indicatifs), la date.

# LOT 2 — Lancer et rendre

Lancer le script une fois. Temps attendu : ~2 × 1 267 + 18 appels à ~0,1 s, soit ~5 min.
Coller dans le compte rendu **la sortie complète**, y compris la liste de chaque message
signalé sur le corpus réel.

**Aucune décision au LOT 2.** [Claude] lit chaque message signalé et tranche s'il s'agit
d'un faux positif. Les seuils ci-dessous sont fixés d'avance ; c'est [Ahmed] qui décide du
plan suivant.

| critère | seuil pour un plan de branchement |
|---|---|
| faux positifs sur le corpus réel, variante `B` (réplique absurde) | **≤ 7** (≈ 0,5 %) |
| faux positifs sur le corpus réel, variante `A` | ≤ 7 |
| vraies défaites (8 cas `pris_en_defaut` écrits) | ≥ 6/8 (indicatif) |
| désaccords et insultes (8 cas `aucune` écrits) | ≤ 1 signalé |
| victoires proclamées (2 cas) | noter seulement : la regex les attrape déjà |
| latence p95 dans le conteneur | ≤ 300 ms (la borne de `laya_client`) |

# LOT 3 — Livrer l'outil

1. `python -m pyflakes tools/sonde_laya_defaite.py`.
2. Un test `tests/test_sonde_laya_defaite.py` **qui n'appelle pas Docker** : il vérifie
   que la construction d'une requête produit exactement le `state` et la question du LOT 1
   pour un cas donné, et que la lecture d'une réponse factice
   `{"answers": {"defaite": {"type": "choice", "choice": "aucune", "confidence": 0.4}}}`
   rend `("aucune", 0.4)`. Isoler ces deux fonctions pour les rendre testables.
3. pytest ciblé puis complet (**jamais deux pytest en parallèle**, port 8599).
4. Commit `feat(tools): sonde LAYA sur la defaite en repartie (SUITE 10)`, avec le tableau
   des seuils rempli **tel que mesuré**, y compris ce qui échoue. Push, **`gh run list`
   jusqu'au vert**. Aucun redémarrage.

---

## Hors périmètre (noté, NON planifié)

- **Le branchement** (tâche de fond dans `bot_sheogorath.py`, `LAYA_URL` pour Sheogorath
  dans `docker-compose.yml`, nouvelle catégorie `pris_en_defaut` dans
  `reflect_on_defeat`) : plan suivant, **seulement** si le LOT 2 passe et qu'Ahmed dit oui.
  ⚠️ `LAYA_URL` n'est aujourd'hui posé que pour Alfred (`docker-compose.yml` l.70).
- **Alfred et Sheogorath n'écrivent jamais dans `interactions`** (`log_interaction` n'est
  appelé que par Johnny, M'aiq, Malena et Sugar) : le graphe « Activité globale » du
  dashboard ne les comptera jamais. Constaté le 27/09, à planifier à part.
- **Migration mempalace** : traitée hors dépôt, pas dans ce plan.
