# PLAN — Jouer contre N'IMPORTE QUEL bot (humain vs bot), système de jeux partagé

## Contexte
Les mini-jeux (Morpion, Puissance 4, PFC, Blackjack, Quiz + duels 1v1 membres) existent
aujourd'hui **uniquement chez M'aiq** (`MaiqBot/game_*.py`, cf. [[idee-minijeux-defi]]).
Le user veut que **le joueur puisse affronter les AUTRES bots** (Sheogorath, Johnny, Onizuka,
Alfred, Malena), pas seulement M'aiq. **Toujours humain vs bot** — jamais bot contre bot
(on ne rouvre PAS le [[plan-silence-total-bots]]).

### Contrainte technique DURE (structurante)
Sur Discord, **les clics de boutons ne sont reçus que par le bot qui a envoyé le message**.
Donc pour jouer contre Sheo, c'est **Sheo qui doit héberger la partie** (poster le plateau,
recevoir les clics, jouer son IA). Aucune communication inter-process n'est nécessaire :
**un seul bot est impliqué par partie** → conforme à [[bots-independants]] ET à
[[plan-silence-total-bots]] (rien à voir avec du bot-vs-bot).

### Principe retenu
Le **bot ciblé héberge la partie**. Déclencheur = **mention du bot** :
- `!morpion` (sans mention) → contre **M'aiq** (hôte par défaut, rétro-compatible).
- `!morpion @Sheogorath` → contre **Sheo** (Sheo poste la grille, joue son IA, ses répliques).
- `!morpion @membre_humain` → **duel PvP** (géré par l'hôte par défaut M'aiq).
Chaque bot ne réagit QUE s'il est concerné (voir Partie C, anti-spam à 6 bots).

---

## Décisions produit — VALIDÉES par le user (2026-07-01)
- **D1 = LES 6 BOTS.** M'aiq, Sheogorath, Johnny, Onizuka, Alfred, Malena reçoivent tous les
  jeux, chacun avec ses répliques + quiz dans sa persona.
- **D2 = PLAFOND ANTI-FARM COMMUN.** 50 rep/jour/joueur **tous bots confondus** → le compteur
  anti-farm vit dans la **DB partagée** (`shared_database`), pas en JSON par bot.

*(Syntaxe par mention, 1 partie active/bot/joueur, timeouts : imposés par la technique ou
déjà tranchés.)*

---

## Partie A — Promouvoir le système de jeux dans `shared/`
Créer le paquet `shared/games/` (moteurs + UI + récompenses **persona-agnostiques**), en
déplaçant/refactorant l'existant M'aiq. **Zéro import discord dans les moteurs** (testables),
**zéro réseau/LLM** (règles curées + flavor curé), cf. [[plan-memes-fr]].

**Fichiers créés :**
- `shared/games/__init__.py` — expose `setup_games(...)`.
- `shared/games/engines.py` ← copie de `MaiqBot/game_engines.py` (TicTacToe minimax,
  Connect4 alpha-beta, RPS, Blackjack, Quiz). **Inchangé fonctionnellement.**
- `shared/games/views.py` ← copie de `MaiqBot/game_views.py`, **paramétré par persona**
  (voir Partie B) : plus aucune chaîne « M'aiq » en dur ; les répliques viennent de l'objet
  persona injecté.
- `shared/games/rewards.py` ← copie de `MaiqBot/game_rewards.py`, backend **DB partagée**
  si D2 = commun (sinon JSON par bot). `try_award(user_id, game_key, base, bot_name, ...)`.

**Compat [[bots-independants]] :** l'import se fait en `try/except ImportError` avec no-op
propre — un bot déployé seul sans `shared/` garde son fallback (pas de jeux, pas de crash).

## Partie B — Interface « persona » injectable
Chaque bot fournit ses propres textes. `setup_games` prend un objet/dict **persona** :
```python
setup_games(bot, logger, persona={
    "name": "Sheogorath",
    "taunts": [...], "win_lines": [...], "lose_lines": [...],
    "draw_lines": [...], "timeout_lines": [...],
    "quiz_questions": [...],          # QCM propres à la persona
    "is_default_host": False,         # True uniquement pour M'aiq
})
```
- `shared/games/views.py` lit ces listes au lieu des constantes M'aiq en dur.
- Nouveau fichier **par bot** : `<Bot>/games_persona.py` (répliques + quiz **dans le ton du
  bot**). M'aiq réutilise ses textes actuels (`MaiqBot/game_data.py` → `games_persona.py`).
- **Quiz :** chaque bot a ses propres questions (thème persona + culture générale). Les
  Elder-Scrolls-centrées restent chez M'aiq/Sheo ; Johnny/Onizuka/Alfred/Malena → questions
  cohérentes avec leur univers + général. Antigravity rédige ~15-20 QCM/bot (curées, 0 LLM).

## Partie C — Câblage par bot + résolution de la cible (anti-spam à 6 bots)
Dans le `on_ready` de **chaque** bot : `from shared.games import setup_games` puis
`setup_games(bot, logger, persona=...)`.

**Règle de réponse (chaque commande de jeu), pour éviter que 6 bots répondent :**
Pour `!<jeu> [cible]`, un bot agit ainsi :
- **cible = un bot** :
  - si c'est **moi** → j'héberge la partie, joueur vs mon IA.
  - si c'est **un autre bot** → **silence total** (`return`, aucun message).
- **cible = un humain** : si je suis `is_default_host` (M'aiq) → duel PvP ; sinon silence.
- **pas de cible** : si je suis `is_default_host` (M'aiq) → partie vs moi (rétro-compat) ;
  sinon silence.

Conséquences :
- `!morpion @Sheogorath` → seul Sheo répond et héberge. M'aiq voit la commande mais se tait
  (cible = un autre bot que lui). Aucun double message.
- `!blackjack @Onizuka` → Onizuka est le croupier. `!quiz @Johnny` → Johnny te fait passer
  SON quiz. `!pfc @Alfred` → Alfred joue.
- `!jeux` / `!defi @humain` → gérés par l'hôte par défaut (M'aiq) uniquement.
- `!enigme` reste **M'aiq-only** (non promu ; propre à sa persona).
- **`!defi @bot`** : ajouter le cas « cible = bot » → l'ouvre en menu de choix de jeu hébergé
  par CE bot (réutilise le menu `DefiSelectView`, mais côté « vs le bot » et non PvP).

**Registre `active_games` :** reste **par process** (chaque bot son registre en RAM). Un
joueur peut donc avoir 1 partie ouverte avec M'aiq ET 1 avec Sheo simultanément — acceptable
(chaque bot borne à 1 partie active contre lui-même). Pas de registre global à maintenir.

## Partie D — Récompenses & anti-farm (D2 = plafond commun)
- **Barème inchangé** (Morpion/P4 +10, PFC +5, Blackjack +8/+15/+2, Quiz +2/bonne rép.).
- Déplacer le suivi anti-farm dans la **DB partagée** (`shared_database`) : cooldown par
  (user, jeu, bot) + **plafond quotidien global 50 rep/j/joueur TOUS BOTS confondus**.
  SQLite gère la concurrence multi-process mieux qu'un JSON écrit par 6 process.
  `add_reputation` est déjà partagé.
- Le JSON M'aiq actuel (`data/maiq_games_rewards.json`) est **retiré** au profit de la DB.
- Cooldown anti-collusion PvP conservé (duels humains via l'hôte par défaut).

## Partie E — Tests
Étendre `tests/test_game_engines.py` (les moteurs sont inchangés → tests toujours verts) et
ajouter :
- `tests/test_games_persona.py` : `setup_games` accepte une persona ; les répliques
  injectées sont bien utilisées (pas de « M'aiq » en dur quand la persona est Sheo).
- `tests/test_games_rewards_shared.py` : le plafond quotidien est bien **partagé** entre deux
  `bot_name` différents (farmer M'aiq puis Sheo respecte le plafond global) ; cooldown par
  (user, jeu, bot) OK ; date injectable.
- **Non testable en unit** (→ checklist live) : le routage par mention à 6 bots (un seul
  répond), rendu des embeds/boutons.

## Partie F — Migration propre de M'aiq
- Remplacer le contenu de `MaiqBot/game_engines.py` / `game_views.py` / `game_rewards.py`
  par des **ré-exports** depuis `shared/games/` (compat imports existants) OU adapter le
  `on_ready` de M'aiq pour appeler directement `shared.games.setup_games(...)` et supprimer
  les fichiers M'aiq devenus redondants. **Reco : supprimer les copies M'aiq** et ne garder
  que `MaiqBot/games_persona.py` + l'appel `setup_games`. Éviter le code dupliqué.
- Vérifier que `MaiqBot/bot_maiq.py` importe désormais `from shared.games import setup_games`
  (au lieu de `from game_views import setup_games`).

---

## Fichiers créés / modifiés
**Créés**
- `shared/games/__init__.py`, `shared/games/engines.py`, `shared/games/views.py`,
  `shared/games/rewards.py`
- `<Bot>/games_persona.py` pour **chacun** des bots retenus (D1) — répliques + quiz persona.
- `tests/test_games_persona.py`, `tests/test_games_rewards_shared.py`

**Modifiés**
- `on_ready` de chaque bot retenu : import + `setup_games(bot, logger, persona=...)`.
- `MaiqBot/bot_maiq.py` : bascule vers `shared.games` (Partie F).
- `shared/shared_database.py` : table/schéma anti-farm jeux (cooldown + plafond quotidien global).
- `.gitignore` : retirer l'entrée du JSON M'aiq devenu inutile (suivi passé en DB).

**Supprimés (Partie F, si reco suivie)**
- `MaiqBot/game_engines.py`, `MaiqBot/game_views.py`, `MaiqBot/game_rewards.py`,
  `MaiqBot/game_data.py` (contenu migré vers `shared/games/` + `MaiqBot/games_persona.py`).

---

## Critères d'acceptation
1. `!morpion @Sheogorath` lance une vraie partie hébergée par **Sheo** (grille Sheo, IA Sheo,
   répliques Sheo) ; **M'aiq ne dit rien**. Idem pour chaque bot retenu et chaque jeu à
   adversaire (Morpion, P4, PFC, Blackjack, Quiz).
2. `!morpion` sans mention → toujours contre M'aiq (rétro-compat). `!morpion @humain` → duel.
3. **Un seul bot répond** quand on cible un bot (pas de double/sextuple message).
4. Aucun bot ne joue contre un autre bot ; aucune boucle inter-bot (silence total préservé).
5. Récompenses créditées avec cooldown + plafond **global tous bots confondus** (farmer en
   tournant les bots ne dépasse pas 50 rep/j/joueur).
6. `py_compile` OK partout ; `pytest` vert (moteurs + persona + rewards partagés).
7. Chaque bot reste **déployable seul** (fallback no-op si `shared/games` absent).

## Notes d'exécution pour Antigravity
- **Jamais** de bot-vs-bot : si la cible est un bot ≠ moi, `return` **silencieux** (0 message).
- Aucun appel réseau/LLM dans les jeux (règles ET flavor curés).
- Garder `shared/games/engines.py` **sans import discord**.
- Écriture concurrente : l'anti-farm passe par la DB partagée (plafond commun), pas de JSON.
- Après exécution : checklist live — pour CHAQUE bot retenu, tester 1 commande de jeu ciblée
  (`!blackjack @<bot>`), vérifier qu'un seul bot répond et que les répliques sont dans SA
  persona.
