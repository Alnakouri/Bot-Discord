# PLAN — M'aiq : jeux SUR COMMANDE uniquement + suite complète de mini-jeux

## Contexte
Aujourd'hui M'aiq lance ses **énigmes automatiquement** (boucle `auto_riddle_loop_maiq`)
et peut même en déclencher **spontanément en pleine conversation** via un outil LLM
(`start_custom_riddle`). Le user veut :

1. **Couper tout l'automatique** → les jeux ne démarrent QUE sur commande explicite.
2. **Implémenter tous les mini-jeux discutés** ([[idee-minijeux-defi]]) : Morpion,
   Puissance 4, Pierre-Feuille-Ciseaux, Blackjack, Quiz persona — en plus des énigmes.

### Décisions produit arrêtées (validées par le user 2026-07-01)
- **Adversaire : bot + 1v1 entre membres.** IA déterministe quand on joue contre M'aiq,
  ET commande `!defi @membre` pour affronter un autre joueur (M'aiq arbitre).
- **Récompenses : réputation avec anti-farm.** Les victoires alimentent le système de
  réputation existant (`add_reputation`), bornées par cooldown + plafond quotidien.

### Contraintes techniques (déjà établies)
- discord.py **2.7.1** → `discord.ui.View` / `Button` / `Select` disponibles.
- Préfixe commande : **`!`** (`commands.Bot(command_prefix='!')`).
- **Logique de jeu 100 % déterministe** (pas de LLM pour les règles → gratuit, increvable,
  anti-triche). LLM = zéro ici ; l'habillage persona vient de **répliques curées** (banques
  de phrases M'aiq), pas d'appel réseau.
- Réputation existante : `add_reputation(user_id, points, reason)`, `get_reputation(user_id)`,
  `get_reputation_level(points)` dans `shared/shared_database.py`.
- Respecter [[bots-independants]] : tout vit dans `MaiqBot/`, fallback propre si `shared/`
  absent. Les moteurs sont **persona-agnostiques** (promouvables vers `shared/` plus tard).

---

## Partie A — Couper l'automatique (sur commande uniquement)

Fichier : `MaiqBot/bot_maiq.py`

1. **Ne plus démarrer la boucle d'énigmes auto.** Dans `on_ready` (~ligne 293),
   supprimer/commenter :
   ```python
   auto_riddle_loop_maiq.start()  # ← À RETIRER
   ```
   Laisser la définition de `auto_riddle_loop_maiq` en place (mort mais inoffensif) OU la
   supprimer entièrement avec sa fonction. **Reco : supprimer** la fonction `auto_riddle_loop_maiq`
   et son `@tasks.loop(...)` (~ligne 565) pour ne pas laisser de code mort.
2. **Garder** `riddle_passive_hint_loop` (~ligne 294) et `check_missed_riddle_answers`
   (startup) : inoffensifs sans énigme active, utiles pour les énigmes lancées par commande.
3. **Retirer l'outil LLM `start_custom_riddle`** pour que M'aiq ne lance plus rien
   spontanément :
   - Enlever le bloc `start_custom_riddle` de `MAIQ_TOOLS_DEFINITION` (~ligne 208-219).
   - Enlever le dispatch correspondant (~ligne 1391-1392 : `if tool_name == "start_custom_riddle"`).
   - Enlever la fonction `tool_start_custom_riddle` (~ligne 174) si plus référencée.
4. **Conserver** la commande `!enigme` (~ligne 660) et **toute la mécanique de réponse
   passive** aux énigmes (~ligne 1080+) : elles ne s'activent QUE si une énigme a été
   lancée par `!enigme`. C'est exactement le comportement « sur commande » voulu.

Résultat attendu : plus AUCUNE énigme ne pop toute seule ; `!enigme` reste le seul point
d'entrée des devinettes.

---

## Partie B — Moteurs de jeux déterministes (purs, testables)

Nouveau fichier : `MaiqBot/game_engines.py` — **aucune dépendance discord**, logique pure,
entièrement unit-testable. Chaque moteur = état + fonctions de transition + détection de fin.

### B.1 Morpion (`tictactoe`)
- Grille 3×3 (liste de 9 cases : `None` / `"X"` / `"O"`).
- `TicTacToe` : `play(idx)`, `winner()` → `"X"|"O"|"draw"|None`, `available()`.
- IA : **minimax** parfait (`best_move(board, mark)`), avec **paramètre `difficulty`**
  (`"pro"` = minimax pur ; `"normal"` = minimax mais 15 % de coups aléatoires pour rester
  battable). Défaut : `"normal"`.

### B.2 Puissance 4 (`connect4`)
- Grille 7 colonnes × 6 lignes.
- `Connect4` : `drop(col)`, `winner()` (aligne 4 : horiz/vert/diag), `is_full()`, `valid_cols()`.
- IA : **alpha-beta** profondeur 4-5 avec heuristique simple (compte les fenêtres de 4).
  Fonction `best_col(board, mark, depth=5)`.

### B.3 Pierre-Feuille-Ciseaux (`rps`)
- Résolution pure : `resolve(a, b)` → `"a"|"b"|"draw"` sur `{"pierre","feuille","ciseaux"}`.
- Format **best-of-3** (premier à 2 manches). IA = choix aléatoire uniforme (pas de triche,
  sauf clin d'œil persona : voir Partie E — laisser `bot_move()` aléatoire pur).

### B.4 Blackjack (`blackjack`)
- Sabot 1 jeu de 52 mélangé par partie (seed injectable pour tests).
- `BlackjackGame` : `hand_value(cards)` (as = 11/1), `player_hit()`, `player_stand()`
  (le croupier tire jusqu'à ≥17), `result()` → `"player"|"dealer"|"push"|"blackjack"`.
- **Contre la banque uniquement** (pas de PvP : le croupier EST M'aiq).

### B.5 Quiz persona (`quiz`)
- Banque de questions **pré-écrites** dans `MaiqBot/game_data.py` (voir Partie C) :
  ~20-30 questions QCM (4 choix), thèmes M'aiq / Elder Scrolls **léger** + culture générale,
  pour rester accessibles. Format : `{"q", "choices":[...], "answer_idx", "flavor"}`.
- Moteur : tirage sans répétition de N questions (défaut 5), calcul du score.

Toutes les structures exposent un `serialize()`/rendu texte de la grille pour l'affichage
(la couche Discord fabrique les embeds à partir de ça).

---

## Partie C — Couche Discord (Views à boutons + commandes)

Nouveaux fichiers :
- `MaiqBot/game_views.py` — les `discord.ui.View` (boutons), le registre des parties, et
  l'enregistrement des commandes via une fonction `setup_games(bot, logger, ctx_helpers)`.
- `MaiqBot/game_data.py` — banques de **répliques persona M'aiq** (victoire/défaite/égalité/
  provocation) + banque **quiz**. Zéro réseau.

### C.1 Principes communs des Views
- **Timeout 180 s** ; à l'expiration : boutons désactivés + message « M'aiq s'est lassé
  d'attendre… la partie est annulée. »
- **Garde d'interaction** : seuls les joueurs de la partie peuvent cliquer. Un intrus reçoit
  une réponse **éphémère** « Ce n'est pas ta partie, voyageur. »
- **Registre en mémoire** `active_games: dict[user_id -> message_id]` : **max 1 partie à
  boutons active par joueur** (anti-spam). Libéré à la fin / au timeout. (Les énigmes,
  gérées en DB, ne comptent pas dans ce registre.)
- Fin de partie : boutons désactivés, résultat affiché, récompense appliquée (Partie D).

### C.2 Modes bot vs 1v1 membre
- Sans mention → **contre M'aiq** (IA de la Partie B).
- Avec mention `@membre` → **duel**. M'aiq poste une invitation avec bouton
  **✅ Accepter / ❌ Refuser** (timeout 60 s) ; à l'acceptation la partie démarre, tours
  alternés gérés par la garde d'interaction. Refus/timeout → annulation propre.
- **Interdits** : se défier soi-même, défier un bot → message d'erreur persona.

### C.3 Commandes (préfixe `!`)
| Commande | Alias | Effet |
|---|---|---|
| `!jeux` | `!games` | Embed listant tous les jeux + comment jouer |
| `!morpion [@membre]` | `!ttt` | Morpion vs bot (ou duel) — grille 9 boutons |
| `!puissance4 [@membre]` | `!p4`, `!c4` | Puissance 4 vs bot (ou duel) — 7 boutons colonnes |
| `!pfc [@membre]` | `!rps` | Pierre-Feuille-Ciseaux best-of-3 (3 boutons) |
| `!blackjack` | `!bj` | Blackjack vs la banque (boutons Tirer / Rester) |
| `!quiz` | — | Quiz persona solo (5 questions, boutons de choix) |
| `!defi @membre` | — | Ouvre un menu (boutons Morpion / Puissance 4 / PFC) ciblant le membre |
| `!enigme` | — | (existant) Lance une énigme — inchangé |

`!defi @membre` réutilise la mécanique d'invitation C.2 après le choix du jeu.

### C.4 Rendu
- Morpion : 3×3 `discord.ui.Button` (grille), X/O affichés sur les boutons, case jouée
  désactivée.
- Puissance 4 : 7 boutons (1 par colonne) + grille rendue en emojis (🔴🟡⚪) dans l'embed.
- PFC : 3 boutons (🪨📄✂️), score des manches dans l'embed.
- Blackjack : boutons **Tirer** / **Rester** ; mains affichées, main croupier masquée jusqu'au
  stand.
- Quiz : 4 boutons de choix par question, progression « Q2/5 », score final.

---

## Partie D — Réputation & anti-farm

Nouveau fichier : `MaiqBot/game_rewards.py` — barrière anti-farm + attribution, **backée par
un JSON** `data/maiq_games_rewards.json` (pas de migration DB ; cohérent avec l'écriture
atomique déjà utilisée ailleurs).

### D.1 Barème (valeurs par défaut, ajustables en constantes en tête de fichier)
- Morpion / Puissance 4 : **+10** rep (victoire), **+3** (nul), 0 (défaite).
- PFC (best-of-3) : **+5** (victoire), 0 sinon.
- Blackjack : **+8** (win), **+15** (blackjack naturel), **+2** (push), 0 (perte).
- Quiz : **+2 par bonne réponse** (max +10 sur 5 questions).

### D.2 Anti-farm (fonction `try_award(user_id, game_key, base_points) -> int`)
Retourne les points réellement crédités (0 si bloqué) et appelle `add_reputation` seulement
si > 0.
- **Cooldown par (user, jeu)** : une victoire n'est récompensée qu'une fois toutes les
  **10 min** pour un même jeu (les parties suivantes restent jouables mais rapportent 0).
- **Plafond quotidien global jeux** : **50 rep/jour/joueur** issues des mini-jeux
  (compteur remis à zéro au changement de date).
- **PvP anti-collusion** : en duel, récompense uniquement si les 2 IDs sont distincts ET
  humains ; même paire de joueurs = récompense plafonnée à **1 fois / 10 min**.
- Le loser ne perd jamais de réputation (pas de solde négatif).

### D.3 Intégration
La couche Discord (Partie C), à la fin d'une partie, appelle
`awarded = try_award(winner_id, game_key, base)` puis affiche « +{awarded} réputation »
(ou une pique persona « M'aiq ne récompense pas la gourmandise » si `awarded == 0` par
cooldown/plafond).

---

## Partie E — Habillage persona (léger, sans réseau)

`MaiqBot/game_data.py` fournit des **listes de répliques M'aiq** piochées aléatoirement :
- `TAUNTS` (au lancement d'un duel), `WIN_LINES` (M'aiq gagne), `LOSE_LINES` (M'aiq perd),
  `DRAW_LINES`, `TIMEOUT_LINES`.
- Ton : menteur farceur à la 3ᵉ personne (« M'aiq a déjà gagné cette partie dans un autre
  royaume… »). Cohérent avec la persona existante.
- **Aucun appel LLM** : c'est du texte curé → gratuit et increvable (aligné [[plan-memes-fr]]
  côté philosophie « pas de réseau pour du flavor »).

---

## Partie F — Tests

Nouveau fichier : `MaiqBot/tests/test_game_engines.py` (ou `tests/` du repo selon la config
pytest existante — respecter [[audit-2026-06-30]] : `testpaths` déjà borné, y ajouter le
dossier si besoin).
- Morpion : minimax ne perd jamais (contre coups aléatoires sur 200 parties → 0 défaite IA
  en mode `pro`) ; détection victoire/nul correcte.
- Puissance 4 : détection des 4 alignements (H/V/diag ↑ et ↓) ; `best_col` bloque une menace
  immédiate.
- PFC : table de résolution complète (9 cas).
- Blackjack : `hand_value` gère les as multiples ; croupier tire jusqu'à ≥17 ; résultats.
- Quiz : tirage sans doublon, score = nb de bonnes réponses.
- `game_rewards` : cooldown respecté, plafond quotidien respecté, reset à minuit (date
  injectable).

Les moteurs étant purs, ces tests ne touchent ni Discord ni le réseau.

---

## Fichiers créés / modifiés
**Créés**
- `MaiqBot/game_engines.py` — moteurs purs (Morpion, P4, PFC, Blackjack, Quiz).
- `MaiqBot/game_views.py` — Views boutons + registre + commandes + `setup_games(...)`.
- `MaiqBot/game_data.py` — répliques persona + banque quiz.
- `MaiqBot/game_rewards.py` — anti-farm + attribution réputation (JSON `data/`).
- `MaiqBot/tests/test_game_engines.py` — tests unitaires des moteurs + rewards.

**Modifiés**
- `MaiqBot/bot_maiq.py` :
  - Partie A (retrait auto-énigmes + outil LLM `start_custom_riddle`).
  - Import + `setup_games(bot, logger, ...)` appelé dans `on_ready` (après
    `setup_slash_commands`).
- `data/` : nouveau `maiq_games_rewards.json` (créé au runtime, **gitignore** comme les
  autres états ; vérifier `.gitignore`).

**Inchangés (volontairement)** : tout le système d'énigmes DB (`minigames.py`,
`shared_database`), la réputation, la réponse passive aux énigmes.

---

## Critères d'acceptation
1. **Aucune énigme ne se poste automatiquement** ; aucune énigme spontanée en conversation.
   `!enigme` fonctionne toujours.
2. `!jeux` liste les jeux ; chaque commande lance une partie jouable aux boutons.
3. Morpion & Puissance 4 : jouables **contre M'aiq** (IA correcte) **et** en `!... @membre`
   (invitation → duel alterné).
4. PFC (best-of-3), Blackjack (vs banque), Quiz (solo) fonctionnels de bout en bout.
5. `!defi @membre` propose un menu de jeux et lance le duel choisi.
6. Les victoires créditent de la réputation **avec** cooldown + plafond quotidien effectifs
   (vérifiable : farmer la même partie n'augmente pas la rep au-delà des bornes).
7. Timeouts et gardes d'interaction OK (boutons se désactivent, intrus bloqué en éphémère,
   1 seule partie à boutons active par joueur).
8. `py_compile` OK sur tous les fichiers ; `pytest` vert sur `test_game_engines.py`.
9. M'aiq reste **déployable seul** (aucune régression sur les autres bots ; `shared/` non requis
   pour les jeux).

---

## Notes d'exécution pour Antigravity
- Ne **pas** introduire d'appels LLM dans les jeux (règles ET flavor = déterministe/curé).
- Réutiliser le style d'écriture JSON atomique déjà présent dans le repo pour
  `maiq_games_rewards.json`.
- Garder les moteurs (`game_engines.py`) **sans import discord** pour la testabilité.
- Après exécution : test live manuel de chaque commande (checklist des critères 1-7).
