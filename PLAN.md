# PLAN — Profil Twitch autonome (bio + couleur choisies par la persona, 1×/jour) + garde anti-saturation API

> **Contexte** : `shared/twitch_chat.py` est en prod (présence permanente Sheo sur Twitch).
> Le profil (bio + couleur) est aujourd'hui **statique** : bio = `sheo_data.TWITCH_BIO`,
> couleur = `blue_violet` figée, appliquées **une seule fois par process** (`_profile_applied`).
>
> **Objectif** : Sheo choisit **lui-même** sa bio et sa couleur **selon sa personnalité**,
> **une fois par jour**, et **ça reste fixe pour la journée** (persisté, survit aux
> redémarrages). Et : **aucune saturation de la clé API** quand on lui parle — il doit se
> comporter comme sur Discord (cooldowns + cascade + rate-limit déjà en place).
>
> Conventions : module **générique** (Sheo = pilote, paramètres optionnels, fallback no-op,
> aucune exception ne remonte au bot), indépendance des bots, données runtime gitignorées.

> **Déjà fait dans cette session (à conserver / commiter)** :
> - **Fix bio** : `helix/users` doit être appelé en **`PUT`** (le `PATCH` renvoyait 404).
>   Corrigé dans `shared/twitch_chat.py` (`TwitchProfile.update_profile`, requête bio).
> - JSON d'auth périmé (`data/twitch_chat_auth_sheogorath.json`) supprimé → ré-amorçage
>   sur le token frais du `.env` (token valide, scopes `chat:read chat:edit user:edit
>   user:manage:chat_color` confirmés via `oauth2/validate`).

---

## 1. Palette de couleurs valides (contrainte Twitch)

Un compte **sans Turbo/Prime** ne peut poser que **15 couleurs nommées**. Ajouter une
constante module dans `shared/twitch_chat.py` :

```python
TWITCH_NAMED_COLORS = [
    "blue", "blue_violet", "cadet_blue", "chocolate", "coral",
    "dodger_blue", "firebrick", "golden_rod", "green", "hot_pink",
    "orange_red", "red", "sea_green", "spring_green", "yellow_green",
]
```

Le choix de Sheo **doit** appartenir à cette liste (sinon `PUT chat/color` échoue). Toute
valeur LLM hors-liste → fallback `blue_violet`.

---

## 2. Profil autonome 1×/jour — `shared/twitch_chat.py`

### 2.1 État persistant (fichier runtime, gitignoré)
Fichier `data/twitch_profile_{bot_id}.json` :
```json
{ "date": "2026-06-23", "bio": "...", "color": "hot_pink" }
```
- `date` = date **locale** du jour (`datetime.now().strftime("%Y-%m-%d")`).
- Lu au démarrage ; écrit après chaque (re)génération réussie.
- Lecture/écriture best-effort (try/except, jamais bloquant).

### 2.2 Génération LLM — **un seul appel par jour**
Méthode `async _generate_daily_profile() -> (bio: str, color: str)` :
- Réutilise **la même cascade** que le chat (`shared.llm_cascade.generate_response`),
  donc rotation de clés + fallback providers. `max_tokens` court (~120), `temperature ~0.9`.
- Base = **la personnalité de fond** (`self.personality_prompt` / `PERSONALITY_BASE`),
  **pas** l'humeur Discord du moment (l'utilisateur veut un profil stable, « ça reste »).
- **Un seul prompt** qui renvoie un petit JSON, pour ne faire qu'**un appel** :
  > « Tu es <persona>. Choisis ta bio de chaîne Twitch et ta couleur de pseudo pour
  >   aujourd'hui, fidèles à ta personnalité. Réponds UNIQUEMENT par un JSON :
  >   `{"bio": "<1-2 phrases, 1re personne, en personnage, ≤280 caractères, sans
  >   guillemets ni didascalies>", "color": "<un nom EXACT parmi: blue, blue_violet,
  >   cadet_blue, chocolate, coral, dodger_blue, firebrick, golden_rod, green, hot_pink,
  >   orange_red, red, sea_green, spring_green, yellow_green>"}`. »
- **Parsing robuste** : extraire le JSON (regex `\{.*\}` en dernier recours), valider :
  - `bio` : strip didascalies (`_strip_stage_directions`), retirer guillemets encadrants,
    tronquer à **300** car. Si vide → fallback `self.profile_bio` (bio statique persona).
  - `color` : `.lower()`; si ∉ `TWITCH_NAMED_COLORS` → fallback `self.chat_color or "blue_violet"`.
- Si la cascade échoue (exception / texte vide) → renvoyer les **valeurs de secours**
  (bio statique + couleur par défaut), **sans crash**.

### 2.3 Application quotidienne — remplace `_apply_profile` / `_profile_applied`
Nouvelle méthode `async _ensure_daily_profile()` :
```
state = _load_profile_state()          # {date, bio, color} ou None
today = date locale
if state and state["date"] == today:
    bio, color = state["bio"], state["color"]      # PAS d'appel LLM
else:
    bio, color = await _generate_daily_profile()   # 1 appel LLM/jour
    _save_profile_state({date: today, bio, color})
await self.profile_helper.update_profile(bio=bio, chat_color=color)  # best-effort Helix
```
- Au **même jour** : on ré-applique les valeurs stockées (appels Helix idempotents, **0**
  appel LLM) → cohérent même après redémarrage, sans coût LLM.
- Au **changement de jour** : 1 génération LLM, persistée.
- Garde un flag mémoire `self._profile_day` pour ne pas spammer Helix dans la même journée
  (appliquer une fois par process + une fois par bascule de date).

### 2.4 Déclenchement (cycle de vie)
- **Au démarrage** : appeler `_ensure_daily_profile()` après la 1re connexion réussie
  (remplace l'actuel `asyncio.create_task(self._apply_profile())` en `run()`), en tâche de
  fond, non bloquant.
- **Bascule de minuit** : dans `_token_refresh_loop` (déjà réveillé toutes les 60 s),
  ajouter un contrôle léger : si `self._profile_day != today` → relancer
  `_ensure_daily_profile()`. (Pas de nouvelle boucle dédiée nécessaire.)
- Toujours `try/except` autour : un échec profil ne doit jamais tuer la boucle chat.

### 2.5 Câblage Sheo (`Sheogorath/bot_sheogorath.py`)
- `setup_twitch_chat("sheogorath", …)` continue de passer `profile_bio=TWITCH_BIO`
  (devient le **fallback** si la génération LLM échoue) et `chat_color` par défaut.
- Rien d'autre à changer côté bot : la logique « 1×/jour + persona » vit dans le module
  générique → les 5 autres bots en hériteront tels quels.

---

## 3. Garde anti-saturation API — parité Discord (vérif + 1 durcissement)

**Déjà en place (à NE PAS casser, vérifier présence)** :
- Réponse uniquement si mot déclencheur (`trigger_re`).
- **Cooldown 3 s / utilisateur** (`user_cooldowns`).
- **Plafond global 18 msg / 30 s** (`global_msg_timestamps`).
- Cascade `shared/llm_cascade` + `classify_request` + `key_manager` (rotation de clés),
  `max_tokens=120`, traitement **séquentiel** des messages.

**Durcissement** :
- **Compter la tentative, pas seulement le succès** : actuellement
  `global_msg_timestamps.append(...)` n'a lieu qu'**après** une réponse non vide (l.444).
  Un appel LLM qui échoue/retourne vide n'est donc pas compté → une rafale d'échecs peut
  multiplier les appels. → Enregistrer le timestamp **au moment où on décide de générer**
  (juste avant `_generate_response`), pour que chaque **appel** compte dans le plafond.
- La génération quotidienne de profil = **1 appel/jour** (garanti par l'état persistant
  §2.3) → négligeable, n'entame pas le budget.

---

## 4. Vérifications (avant test live)
- `python -m py_compile shared/twitch_chat.py Sheogorath/bot_sheogorath.py` → OK.
- `_generate_daily_profile` : sur réponse LLM bidon / hors-JSON / couleur invalide →
  renvoie bien les fallbacks, jamais d'exception.
- `color` retournée **toujours** ∈ `TWITCH_NAMED_COLORS`.
- `bio` ≤ 300 car., sans didascalie, sans guillemets encadrants.
- Relancer 2× le bot le **même jour** → **aucun** nouvel appel LLM de profil (état lu),
  profil ré-appliqué à l'identique.
- Simuler un changement de date (modifier `date` du JSON) → 1 régénération.
- Module toujours importable seul ; aucun crash si `key_manager`/cascade indisponibles.

## 5. Recette de test (live)
1. Démarrer le bot → logs `✅ Description mise à jour` (plus de 404) **et**
   `✅ Couleur du chat mise à jour (<couleur choisie>)`.
2. Page `https://www.twitch.tv/compte_bot_sheo` → bio = texte généré en personnage.
3. Chat : `sheo ...` → réponse en personnage, **pseudo coloré** (refresh du chat).
4. Redémarrer le même jour → bio/couleur **identiques**, pas de nouvel appel LLM (logs).
5. Spammer `sheo ...` rapidement → cooldown 3 s + plafond 18/30 s tiennent, pas de
   saturation de clé (logs `⏳ cooldown` / `🚨 rate limit`).

## 6. Hors périmètre
- Couleurs hex arbitraires (nécessiteraient Turbo/Prime sur le compte) — écarté.
- Bio basée sur l'humeur Discord du jour (l'utilisateur veut un profil **stable**) — écarté.
- Photo de profil (non modifiable par l'API Helix) — reste manuelle.
- Généralisation du profil autonome aux 5 autres bots (le module est déjà générique).
