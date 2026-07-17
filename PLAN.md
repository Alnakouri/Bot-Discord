# PLAN — Statuts Discord lisibles : passage au statut personnalisé (CustomActivity)

> Antigravity exécute. Claude a rédigé (2026-07-17).
> Cible principale : `shared/discord_status.py` + `tests/test_discord_status.py`.
> Optionnel (étape C) : le repli inline des 6 bots. Repérer par CONTENU, pas par numéro de ligne.

## Contexte / problème

Les statuts affichés sous les noms des bots dans la liste des membres Discord ont l'air
cassés : « avec le feu », « au jeu du péteur », « les rêves des innocents »…

Cause : `shared/discord_status.py` génère des textes conçus pour SUIVRE le verbe du type
d'activité (`playing` → « Joue avec le feu », `listening` → « Écoute les rêves des
innocents »). Or la liste des membres n'affiche QUE le texte, sans le verbe — le verbe
n'apparaît que dans la carte de profil. Résultat : des bouts de phrase orphelins.

Décision user (2026-07-17) : passer au **statut personnalisé** (`discord.CustomActivity`),
affiché TEL QUEL partout, sans verbe imposé. Les statuts deviennent des phrases courtes
autonomes, toujours générées 1×/jour par la persona. discord.py >= 2.4 supporte le statut
personnalisé pour les bots (on est en >= 2.7.1 partout) : `discord.CustomActivity(name="…")`.

## A — `shared/discord_status.py`

Le contrat public ne bouge pas : mêmes noms (`DiscordDailyStatus`, `ensure_daily_status`,
`pick_activity`), mêmes paramètres du constructeur. Les 6 bots n'ont RIEN à changer.

1. **Représentation interne : des chaînes, plus des tuples.**
   `self._items` devient une liste de `str` (phrases autonomes ≤ `MAX_STATUS_LEN`).

2. **Conversion des fallbacks (constructeur).** `fallback_activities` reste reçu au format
   historique `[(type, texte)]` (les 6 bots fournissent ça). Les convertir en phrases
   autonomes via un préfixe verbal déterministe :
   - `watching` → `Regarde {texte}` ; `playing` → `Joue {texte}` ; `listening` → `Écoute {texte}`.
   - Ex. `("playing", "avec le feu")` → `Joue avec le feu` ;
     `("listening", "Night City cramer 🔥")` → `Écoute Night City cramer 🔥`.
   - Helper module pur, ex. `_legacy_to_text(type_str, text) -> str` (réutilisé au point 5).
   - Tronquer à `MAX_STATUS_LEN` après préfixage.

3. **Prompt LLM (dans `_generate_daily_status`).** Demander `count` STATUTS PERSONNALISÉS :
   phrases COURTES (≤ 8 mots), AUTONOMES (lisibles seules, sans verbe sous-entendu),
   en personnage, sans guillemets ni didascalies, emoji de ton optionnel en fin.
   Réponse = UNIQUEMENT un tableau JSON de chaînes, ex. :
   `["Je fais fondre le caramel 🍬", "Recrutement de bonbons rebelles", "Le sucre d'orge craque encore"]`

4. **`_parse_items` : accepter les deux formats.** Toujours statique, toujours tolérante
   (fences ```…```, texte autour, dédoublonnage insensible à la casse, troncature
   `MAX_STATUS_LEN`, entrées vides ignorées). Renvoie désormais une liste de `str` :
   - élément `str` → pris tel quel (strip, guillemets retirés, espaces compactés) ;
   - élément `dict {"type","text"}` (ancien format, le LLM peut retomber dessus) →
     converti via `_legacy_to_text` (alias FR/EN des types conservés ; type inconnu → jeté).

5. **Persistance : nouveau champ, rétro-compat un jour.** Nouveau format
   `{"date": "...", "texts": ["…", …]}`. Au chargement (`ensure_daily_status`) :
   - `texts` présent → utiliser tel quel ;
   - sinon ancien champ `items` (paires) du MÊME jour → convertir via `_legacy_to_text`
     et continuer (0 appel LLM) ; la prochaine sauvegarde écrit le nouveau format.
   La sauvegarde n'écrit plus que `texts`.

6. **`pick_activity`.** Tire une chaîne au hasard et renvoie
   `discord.CustomActivity(name=texte)` (import local `discord` conservé, `None` si
   import impossible ou aucune chaîne). Le nom de méthode ne change pas : les
   `bot.change_presence(activity=…)` des 6 bots marchent tel quel.

## B — Tests (`tests/test_discord_status.py`)

Réécrire pour le nouveau contrat (garder le style unittest existant, module importable
sans discord.py sauf mention) :
- tableau JSON de chaînes simple → liste de `str` ;
- fences + texte autour → OK ;
- dédoublonnage insensible à la casse ; chaîne vide/espaces jetée ; troncature à
  `MAX_STATUS_LEN` ; garbage/None/non-liste → `[]` ;
- ancien format objets `{"type":"playing","text":"avec le feu"}` → `"Joue avec le feu"`
  (idem watching/listening + alias FR « Regarde »/« ÉCOUTE ») ; type inconnu jeté ;
- `_legacy_to_text` direct : les 3 types + troncature après préfixe ;
- constructeur : `fallback_activities=[("playing","avec le feu")]` → `_items == ["Joue avec le feu"]` ;
- si discord.py est dispo dans l'env de test : `pick_activity()` renvoie un
  `discord.CustomActivity` dont `.name` est dans la liste (sinon skipTest).

## C — Optionnel : repli inline des 6 bots

Chaque bot a un repli local si `shared/` est absent (convention bots indépendants), ex.
`JohnnyBot/bot_johnny.py` boucle `status_loop_johnny` : `discord.Activity(type=…, name=…)`
depuis `_STATUS_FALLBACK`. Pour l'aligner : préfixer le verbe comme en A.2 et renvoyer
`discord.CustomActivity(name=…)`. Faible enjeu (chemin dégradé) — à faire seulement si
rapide, sur les 6 (`Alfred`, `JohnnyBot`, `MaiqBot`, `MalenaBot`, `Sheogorath`, `SugarBot`).

## Garde-fous

- NE PAS toucher aux personas ni aux autres modules `shared/`.
- `shared/discord_status.py` doit rester importable sans discord.py (import local dans
  `pick_activity` uniquement).
- Ne pas supprimer les `data/discord_status_*.json` existants : la rétro-compat A.5 les
  convertit au vol.

## Vérification

1. `python -m pytest` → tout vert (237 avant, + les nouveaux).
2. Déploiement : `docker compose up -d --build --force-recreate` (shared/ est COPIÉ dans
   les images → --build obligatoire).
3. Live : attendre une rotation (boucle 30 min, ou restart d'un bot) puis vérifier dans la
   liste des membres que chaque bot affiche une phrase complète autonome (plus de
   fragments type « avec le feu »).
