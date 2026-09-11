# PLAN — Élargir ce que les bots savent de leur interlocuteur, sans rien inventer

Rédaction : Claude, le **2026-09-11**. Exécution : **Antigravity**.
Fait suite à `c3887a9` (mémoire des faits resserrée sur l'auto-attribution, déployée).

**L'idée directrice** : tous les faits ajoutés ici sont **structurels** — calculés à partir
de données que Discord fournit, jamais extraits par un LLM. Ils ne peuvent donc **pas**
être hallucinés, et ils sont immunisés par construction contre la boucle d'auto-attribution
qu'on vient de fermer. Ils ne passent **jamais** par la balise `<fact>`.

---

# DEUX VÉRIFICATIONS QUI ONT CHANGÉ L'ORDRE DES LOTS

J'avais classé « le profil Discord » en premier en le croyant gratuit. Vérification faite :

1. **Les réactions marchent déjà.** `Intents.default()` inclut `reactions` : `on_reaction_add`
   fonctionne sur les 6 bots **sans toucher à un seul intent**. Aucun des six ne l'écoute.
   C'est donc le lot le moins cher, pas le deuxième.
2. **Une partie du profil est déjà accessible, l'autre non.** `message.author` est un
   `Member` livré dans la charge utile du message : **`roles`, `joined_at`, `nick`,
   `premium_since` sont lisibles aujourd'hui**, sans intent supplémentaire. En revanche
   **`activities`** (ce qu'il est en train de jouer) exige l'intent privilégié
   `presences` — **hors périmètre**, voir la fin.

## ⚠️ Et un vrai défaut trouvé en chemin

**`on_member_join` ne s'est JAMAIS déclenché sur M'aiq ni sur Sheogorath.** Les six bots
déclarent ce gestionnaire, mais seuls Alfred, Johnny, Malena et Sugar posent
`intents.members = True` :

| Bot | `intents.members` | `on_member_join` |
|---|---|---|
| Alfred, Johnny, Malena, Sugar | ✅ | fonctionne |
| **M'aiq** (`MaiqBot/bot_maiq.py`) | ❌ | **code mort** |
| **Sheogorath** (`Sheogorath/bot_sheogorath.py:1442`) | ❌ | **code mort** |

C'est le lot 4, et il porte un piège de déploiement décrit là-bas.

---

# LOT 1 — Les réactions : le seul retour honnête sur leurs propres répliques

**Pourquoi en premier** : zéro configuration, zéro intent, et c'est le seul signal de
**qualité mesurée** au lieu de déclarée. Aujourd'hui, aucun bot ne sait si une vanne a fait
rire ou est tombée à plat.

## Le travail

Ajouter `on_reaction_add` dans les 6 bots. Ne compter **que** les réactions posées sur un
message **du bot lui-même** (`reaction.message.author.id == bot.user.id`), et ignorer les
réactions du bot.

Stocker dans une nouvelle table de `shared/shared_database.py`, sur le modèle de
`error_events` :

```
reactions_repliques(id, timestamp, bot_name, message_id, channel_id,
                    user_id, emoji, retiree)
```

⚠️ Écrire via la **file + thread écrivain** de `shared/bot_logger.py` ou
`shared/api_tracking.py` — **pas** de `sqlite3.connect` depuis `on_reaction_add`, qui vit
dans la boucle asyncio. C'est le montage exact du `disk I/O error` documenté dans
`api_tracking.py`.

⚠️ `on_reaction_add` ne se déclenche que sur les messages **en cache**. Pour les anciens,
il faut `on_raw_reaction_add`. **Prendre `on_raw_reaction_add`** : sinon le signal
disparaît dès que le bot redémarre, et personne ne s'en apercevra.

## Ce qu'on en fait — et ce qu'on n'en fait PAS

- **Ce lot ne change AUCUN prompt.** Il ne fait que **collecter**. On regarde les chiffres
  d'abord, on décide ensuite.
- **Ne pas** brancher ça sur le carnet de répartie dans le même lot, même si c'est la
  suite évidente. Un lot, une chose.

---

# LOT 2 — Le profil Discord, lisible aujourd'hui

## Ce qui est disponible sans toucher aux intents

Depuis `message.author` (un `Member` en salon serveur) :

| Donnée | Ce qu'elle vaut |
|---|---|
| `joined_at` | ancienneté sur le serveur — « tu traînes ici depuis deux ans » |
| `roles` | ses rôles, hors `@everyone` |
| `nick` vs `name` | s'il se donne un surnom, et lequel |
| `premium_since` | booster du serveur |
| `created_at` | ancienneté du **compte** Discord |

## Le travail

Une fonction dans chaque bot — ou mieux, **une seule dans `shared/`, vendorisée** — qui
rend un bloc court, injecté dans le prompt **à côté** du bloc `[CE QUE TU SAIS SUR …]`,
jamais dedans. Points d'ancrage du bloc existant, vérifiés :

| Bot | Ligne |
|---|---|
| Alfred | `bot_alfred.py:200` |
| Johnny | `bot_johnny.py:930` |
| M'aiq | `bot_maiq.py:1336` |
| Sheogorath | `bot_sheogorath.py:2255` |
| Sugar | `bot_sugar.py:843` |
| Twitch | `shared/twitch/llm.py:243` |

⚠️ **Le module Twitch n'a pas de `Member` Discord.** Ne pas y câbler ce lot — il a ses
propres signaux (ancienneté de suivi, abonné, modérateur), qui sont un autre chantier.

⚠️ **`message.author` est un `User` et non un `Member` en message privé** : `roles` et
`joined_at` n'existent pas. Garder le bloc vide dans ce cas, sans lever.

⚠️ **Ne pas stocker ces données.** Elles se relisent à chaque message, elles sont toujours
à jour, et les écrire en base créerait une copie qui diverge. C'est le défaut de la grille
des bots du dashboard, corrigé au Lot 1 du portage v2.

---

# LOT 3 — Ce qui dort déjà en base

`reputation` (6 lignes) et `quests` (3 lignes) existent, et **ne sont injectés dans aucun
prompt**. Les accesseurs sont déjà écrits dans `shared/shared_database.py` :
`get_reputation` (l. 492), `get_reputation_level` (l. 529), `get_daily_quests` (l. 695).

Les ajouter au même bloc que le lot 2 : niveau, points, `riddle_streak`, quêtes du jour
faites ou non.

⚠️ **Zéro nouveau mécanisme dans ce lot** : que du câblage. Si l'exécution ajoute une
table, une colonne ou un calcul, c'est qu'elle a dérivé.

⚠️ `shared_database.py` **n'est pas vendorisé** : les bots l'importent dans un
`try/except ImportError`. Respecter ce montage — un bot déployé sans `shared/` doit
continuer à tourner, simplement sans ce bloc.

---

# LOT 4 — Le gestionnaire mort de M'aiq et Sheogorath

Ajouter `intents.members = True` dans `MaiqBot/bot_maiq.py` et
`Sheogorath/bot_sheogorath.py`, à côté de `intents.message_content` (respectivement vers
les lignes 363-365 pour Sheo).

## ⚠️⚠️ LE PIÈGE — À LIRE AVANT DE TOUCHER À CETTE LIGNE

`members` est un **intent privilégié**. Le poser dans le code **sans l'avoir activé dans le
Discord Developer Portal** pour cette application fait **échouer la connexion au
démarrage** (`PrivilegedIntentsRequired`) : **le bot ne démarre plus du tout.**

Donc :
1. **C'est l'utilisateur qui doit d'abord cocher « SERVER MEMBERS INTENT »** dans le portail
   Discord, pour l'application de M'aiq **et** celle de Sheogorath.
2. **Ne pas livrer ce lot avant d'avoir sa confirmation.** Le livrer en avance, c'est
   casser deux bots au prochain redémarrage.
3. **Le signaler dans le rapport de livraison** même si le reste est fait.

---

# RECETTE

1. `pyflakes` sur les bots touchés, `shared/`, `tests/` — **avant** `pytest`.
2. `pytest` **seul**. Référence : **913 tests, 0 échec**.
3. `python tools/vendor_core.py` **si et seulement si** le lot 2 crée un module dans
   `shared/` destiné aux bots — et dans ce cas **l'ajouter aux DEUX listes**
   (`tools/vendor_core.py` et `tools/sonde_core_drift.py`), puis
   `python tools/sonde_core_drift.py`.
4. Les mutations rejouées, chacune vérifiée rouge.
5. **Ne pas déployer le lot 4** sans la confirmation du portail.

## Verrous attendus

- Le bloc de profil est **absent** quand `message.author` est un `User` (message privé) —
  *mutation : le construire quand même → rouge*.
- Les 6 bots écoutent `on_raw_reaction_add` — *mutation : le retirer d'UN SEUL → rouge*
  ([[gotcha-un-bot-sur-six-manque-toujours]]).
- Une réaction sur le message **d'un autre** n'est pas comptée — *mutation : retirer le
  test d'auteur → rouge*.
- Le profil structurel **ne passe pas** par `<fact>` — *mutation : l'y faire passer →
  rouge*.

---

# LES RÈGLES

1. **Aucun de ces faits ne passe par le LLM.** Ils sont calculés, jamais extraits. C'est
   toute leur valeur.
2. **Le lot 1 ne modifie aucun prompt** — il collecte, on décide après.
3. **Ne pas toucher à la consigne `<fact>`** : elle vient d'être resserrée et déployée.
4. **Éditer les fichiers directement**, pas de script jetable
   ([[gotcha-script-jetable-dit-success]]).
5. **Ne pas commiter, ne pas pousser.** La relecture commite.
6. **Livrer lot par lot, en s'arrêtant entre chaque.**
7. **Rendre compte de ce qui n'a pas été fait**, nommément.

---

# HORS PÉRIMÈTRE, ET POURQUOI

- **`member.activities`** (ce qu'il joue en ce moment) : exige l'intent privilégié
  `presences` sur les 6 applications, plus une case à cocher par bot dans le portail. Gros
  coût de configuration manuelle pour un signal volatil. À rouvrir si le reste plaît.
- **La mémoire inter-bots** (M'aiq sait que tu compares Sheo à de la nourriture, Sheo
  l'ignore) : c'est le plus puissant, et le seul qui demande une **décision
  d'architecture** — il heurte [[bots-independants]]. Voir
  [[idee-memoire-partagee-discord-twitch]], jamais démarrée. À arbitrer séparément.
- **Le 2ᵉ échelon de Sheogorath** : à 3300 tokens de prompt contre 8000 tokens/minute chez
  Groq, il tombe sur `ministral-14b` une réponse sur deux ou trois. Rien de ce plan n'y
  change quoi que ce soit.
