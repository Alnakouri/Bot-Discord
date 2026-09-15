# PLAN — Les événements serveur : rendre l'ENVOI observable sans attendre un humain

Rédaction : Claude, le **2026-09-15**. Exécution : **Antigravity**.
Fait suite à `e86e442` (l'accueil en dur de Johnny retiré) et au test live d'arrivée du
14/09, qui a validé **le chemin jusqu'au tirage** — et rien au-delà.

Le 14/09 à 19:37:50Z, une vraie arrivée a fait journaliser `[ARRIVEE]` aux 6 bots, et
seuls Alfred et Sugar ont atteint le tirage. **Ils l'ont tous les deux perdu** (20 % et
30 %). Depuis, l'item « l'envoi n'a jamais été vu » attend une deuxième arrivée avec
~44 % de chances d'aboutir — c'est-à-dire qu'il peut attendre des semaines.

**Ce plan retire cette attente.** Rien de ce qui reste ouvert n'exige réellement un
humain : il exige un **tirage gagnant**, et un tirage se force.

---

## LA PREUVE, relevée le 15/09 avant d'écrire ce plan

| Vérification | Résultat |
|---|---|
| Un test atteint-il `await target_channel.send(...)` ? | **NON.** `grep -n random tests/test_evenements_serveur.py` → **0 occurrence**. Aucun des 9 tests ne force le tirage : la queue des 3 gestionnaires n'a jamais tourné, ni en test, ni en live. |
| `handle_member_remove` laisse-t-il une trace ? | **AUCUNE.** Pas un `logger.*` dans la fonction. **4 sorties muettes** : `has_user_interacted` faux, pas de salon, tirage perdu, pool absent. |
| `check_and_send_birthdays` ? | **AUCUNE** non plus. `get_todays_birthdays()` vide → `return` muet. |
| `on_member_remove` est-il câblé partout ? | **OUI, sur les 6** (relevé `ast` sur les 6 `bot_*.py`). Ce n'est donc pas du code mort — mais **rien ne le prouverait si ça l'était**, et c'est exactement l'ambiguïté qui a coûté du 11 au 14/09 sur l'arrivée. |
| Le salon existe-t-il vraiment ? | **OUI** : `taverne-des-bots`, 6 occurrences dans les journaux de `bot-sugar`. Les 3 gestionnaires le trouvent. |

⚠️ **Ce qui est DÉJÀ couvert — ne pas le réécrire.** J'ai failli inscrire ici « le
`.format(user=…)` des répliques n'est jamais exercé ». **C'est faux** :
`test_aucun_bot_n_emprunte_la_voix_d_un_autre` rejoue 50 tirages par pool et compare à
`{g.format(user=valeur) for g in dictionnaire[cle]}`. Une accolade parasite dans une
réplique fait DÉJÀ crier la suite. Le trou n'est pas dans les répliques, il est dans
**l'orchestration** qui les envoie.

---

# LOT 1 — Le tirage se force, et l'envoi se voit

**Fichier : `tests/test_evenements_serveur.py`.** Aucune ligne de
`shared/server_events.py` ne change dans ce lot.

Le trou est étroit et se nomme : entre « le dé est tombé du bon côté » et « Discord a
reçu le texte », il y a la recherche du salon, le `.send()`, et le `log_event()`. Ces
trois-là n'ont jamais tourné ensemble.

### 1.1 — Un faux salon qui ENREGISTRE ce qu'on lui envoie

Ajouter, à côté de `_FauxMembre`, un `_FauxSalon` avec un `name` et un
`async def send(self, contenu)` qui empile dans une liste. Le construire avec le vrai
nom du serveur : **`taverne-des-bots`** — c'est celui que la recherche trouve en
production, un test qui passerait avec `#general` ne prouverait rien.

### 1.2 — Le verrou : Alfred et Sugar ENVOIENT, les 4 autres ne s'approchent pas du salon

Pour **les 3 gestionnaires** (`handle_member_join`, `handle_member_remove`,
`check_and_send_birthdays`), avec le tirage toujours gagnant
(`monkeypatch.setattr(ev.random, "random", lambda: 0.0)`) :

- pour chaque nom réellement passé par les bots — réutiliser `_noms_passes_par_les_bots()`,
  **ne pas recopier une liste** ([[gotcha-un-bot-sur-six-manque-toujours]]) ;
- si le bot est porte-parole : le salon a reçu **exactement un** message, et ce message
  appartient à **son** pool formaté — jamais à celui d'un autre ;
- sinon : le salon n'a **rien** reçu.

`handle_member_remove` passe par `has_user_interacted` : le neutraliser
(`monkeypatch.setattr(ev, "has_user_interacted", lambda _id: True)`), sinon le test tape
la vraie base ([[gotcha-pytest-pollue-data]]). Même chose pour `log_event` et
`get_todays_birthdays`.

`check_and_send_birthdays` prend un `bot`, pas un `member` : il lui faut un faux bot avec
`guilds` et un `get_member` qui rend le faux membre.

### 1.3 — Le tirage PERDU doit rester muet

Le même verrou avec le tirage toujours perdant (`lambda: 0.99`) : **0 message envoyé**,
pour les 6. Sans ce second sens, le test ne distingue pas « ça envoie quand il faut » de
« ça envoie toujours ».

### Mutations à rejouer (chacune doit faire CRIER le verrou)

1. remplacer `await target_channel.send(message)` par un `pass` dans `handle_member_join` ;
2. remettre le repli fautif `pools.get(cle, pools["sheogorath"])` dans `_tirer` ;
3. retirer le `if random.random() < 0.2` de `handle_member_remove` (envoi systématique)
   — celle-ci ne doit crier que sur 1.3.

---

# LOT 2 — Le départ et l'anniversaire sont AVEUGLES

**Fichier : `shared/server_events.py`.**

La leçon du 11-14/09 — *une trace AVANT le tirage, sinon « aucun message » ne veut rien
dire* — n'a été appliquée qu'à l'arrivée. `handle_member_join` porte sa ligne
`👋 [ARRIVEE] … — vu par {bot_name}` ; les deux autres gestionnaires n'ont **rien**.

Conséquence concrète : si un membre part demain, **aucun des 6 journaux ne le dira**. On
ne saura ni si l'événement est arrivé, ni si le dé a parlé.

### 2.1 — Une trace d'entrée, au même endroit et de la même forme

Première ligne de `handle_member_remove`, **avant** `has_user_interacted` :

    logger.info(f"👋 [DEPART] {member} a quitté '{member.guild.name}' — vu par {bot_name}")

Et dans `check_and_send_birthdays`, **avant** le traitement :

    logger.info(f"🎂 [ANNIVERSAIRE] {len(birthday_user_ids)} anniversaire(s) — vu par {bot_name}")

⚠️ Ne poser cette seconde ligne **que si la liste est non vide** — et garder le `return`
muet sinon. Sur un serveur sans anniversaire du jour, elle tomberait à chaque passage de
la boucle quotidienne pour ne rien dire, et une alarme qui crie pour du nominal, on
apprend à l'ignorer ([[gotcha-alerte-qui-crie-pour-du-nominal]]).

### 2.2 — Les sorties muettes de `handle_member_remove` doivent se distinguer

Comme pour l'arrivée, chaque sortie dit **pourquoi**, au bon niveau :

| Sortie | Niveau | Ce que ça veut dire |
|---|---|---|
| `has_user_interacted` faux | `debug` | nominal : on ne salue pas un inconnu |
| bot hors `_PORTE_PAROLE` | `debug` | décision du 13/09 |
| aucun salon trouvé | `info` | configuration du serveur |
| tirage perdu | `info` | le dé — et la ligne porte le seuil, comme à l'arrivée |

### 2.3 — Le filtre porte-parole passe AVANT la base

`handle_member_remove` appelle `has_user_interacted(member.id)` en toute première ligne :
**les 4 bots qui ne diront jamais rien ouvrent quand même une connexion** à chaque
départ. Déplacer le `if not participe_aux_evenements(bot_name): return` juste après la
trace de 2.1, avant l'appel à la base. Même esprit que le lot 2 du plan précédent :
aucune connexion ouverte pour rien.

### Verrou attendu

Généraliser `test_une_arrivee_laisse_une_trace_meme_sans_salon_et_meme_sans_message` aux
**3** gestionnaires : sans salon et sans message, chacun laisse sa trace. Mutation :
retirer la ligne `[DEPART]` → le verrou crie.

---

# LOT 3 — La décision du 13/09 n'est toujours pas vraie dans le code

**Fichier : `shared/server_events.py`.**

`_PORTE_PAROLE = {"alfred", "sugar"}` filtre en amont. Pourtant les tables de seuils
gardent les quatre autres, à **trois endroits** :

```python
probs = {"sheogorath": 0.3, "maiq": 0.2, "alfred": 0.2, "sugar": 0.3}   # arrivée
if random.random() < 0.2:                                              # départ, en dur
probs = {"sheogorath": 0.4, "maiq": 0.2, "alfred": 0.2, "sugar": 0.2}  # anniversaire
```

Ces valeurs `sheogorath` et `maiq` sont **inatteignables** : le code ment sur la
décision, et le `0.2` du départ n'est même pas dans une table. Un lecteur qui cherche
« qui accueille ? » trouve quatre noms.

**À faire** : une seule table de seuils par gabarit, **ne portant que les
porte-parole**, et le seuil du départ dedans. Ne **rien changer** aux valeurs d'Alfred et
de Sugar (20 % / 30 % à l'arrivée) : ce plan ne touche pas à la fréquence.

### Verrou attendu

Aucune clé d'une table de seuils hors de `_PORTE_PAROLE` — relevé par `ast` **sur le
fichier**, pas par un import : si quelqu'un rajoute un bot dans une table sans l'ajouter
à `_PORTE_PAROLE`, ça doit crier.

---

## Note — une asymétrie repérée, volontairement HORS lot

`handle_member_join` cherche « taverne »+« bot », puis se rabat sur « bienvenue » /
« welcome ». Les deux autres gestionnaires ne cherchent **que** « taverne »+« bot ». Sur
un serveur sans taverne, les arrivées parleraient et les départs seraient muets, sans
trace. Ce n'est **pas** un défaut ici — `taverne-des-bots` existe, c'est vérifié. À ne
traiter que si le serveur change : uniformiser sans raison, c'est décider du
comportement d'un serveur qu'on n'a pas.

---

## Hors lot — ce qui reste suspendu à l'extérieur

- **La mesure des handles à 24 h** (M'aiq, rétention de `bots_database.db`) : horloge
  remise à zéro le **15/09 à 10:31:44Z**, baseline **fd = 1 sur les 6**. Verdict possible
  le **16/09 après 10:31Z**, et seulement si l'hôte n'est pas éteint — la fenêtre du
  14/09 est morte à ~13 h d'uptime pour cette raison exacte.
- **La surveillance d'Alfred** (« Maître <@id> », ne pas redire « le Manoir ») : celle-ci
  demande vraiment qu'il PARLE à un humain. Aucun tirage à forcer, elle reste ouverte.
