# PLAN — Découpage de `shared/twitch_chat.py` (1806 lignes) en modules satellites

> **Contexte.** `shared/twitch_chat.py` est le plus gros fichier du projet (1806 lignes) et le
> dernier monolithe non découpé en `shared/`. Il concentre ~8 préoccupations distinctes dans une
> seule classe à état `TwitchChatBot`. Objectif : le scinder en **modules satellites** (patron déjà
> adopté pour `sheo_*` / `*_data.py`) pour la lisibilité, la testabilité unitaire et la réduction du
> risque de régression à chaque évolution Twitch. **Refactor pur : zéro changement de comportement.**
>
> **Contrainte de compatibilité (NE PAS CASSER).** La surface publique consommée hors module est :
> 1. `from shared.twitch_chat import setup_twitch_chat` — utilisée par `JohnnyBot/bot_johnny.py:84`
>    et `Sheogorath/bot_sheogorath.py:135` (signature à conserver **à l'identique**, cf. lignes
>    `1665-1690` actuelles : keyword-only).
> 2. `from shared.twitch_chat import TwitchChatBot` puis `TwitchChatBot._strip_stage_directions(text)`
>    — appelé en **staticmethod externe** par `bot_johnny.py:385-386`, `bot_sheogorath.py:669-670`
>    et `shared/twitch_eventsub.py:258-259`.
>
> ➡️ `shared/twitch_chat.py` **reste le point d'entrée** (façade) : il continue d'exposer
> `setup_twitch_chat`, `TwitchChatBot`, `TwitchAuth`, `TwitchProfile`. Les bots ne changent pas
> d'import. `_strip_stage_directions` reste accessible en `TwitchChatBot._strip_stage_directions`.

> **Cadre.** [[bots-independants]] : `shared/` optionnel, import LLM/voice en try/except. Le découpage
> ne doit créer **aucune** dépendance runtime nouvelle ni changer les imports des bots. Méthode :
> **mixins** — `TwitchChatBot` reste défini dans `twitch_chat.py` mais hérite de classes-mixins
> définies dans des fichiers frères. Chaque mixin ne fait que regrouper des méthodes `self.*` ; l'état
> (`__init__`) reste centralisé dans `TwitchChatBot`. Aucune méthode ne change de corps.

---

## Cartographie actuelle (à conserver mentalement pendant le découpage)

| Lignes | Bloc | Destination |
|---|---|---|
| 40-165 | `class TwitchAuth` | `shared/twitch/auth.py` |
| 166-240 | `class TwitchProfile` | `shared/twitch/profile.py` |
| 241-413 | `TwitchChatBot.__init__` + `_parse_tags` | **reste** dans `twitch_chat.py` (état central) |
| 414-570 | `run`, `_token_refresh_loop`, `_connect_and_loop` | `shared/twitch/connection.py` (mixin) |
| 571-708 | `_generate_response`, `_strip_stage_directions` | `shared/twitch/llm.py` (mixin) |
| 709-862 | `_load/_save_profile_state`, `_generate_daily_profile`, `_ensure_daily_profile` | `shared/twitch/daily_profile.py` (mixin) |
| 863-934 | `_sanitize_input`, `stop` | `_sanitize_input`→`shared/twitch/sanitize.py` ; `stop` reste |
| 935-1055 | viewers state + facts + `_generate_templated_greet`, `_handle_usernotice` | `shared/twitch/memory.py` (mixin) |
| 1056-1185 | `_react_to_event*`, `_get_fallback_event_reply` | `shared/twitch/events.py` (mixin) |
| 1186-1448 | `_handle_privmsg`, `_handle_command`, `_try_greeting`, `_try_interjection`, `_generate_interjection` | `shared/twitch/dispatch.py` (mixin) |
| 1449-1531 | `get_broadcaster_id`, `_start_eventsub` | `shared/twitch/eventsub_bridge.py` (mixin) |
| 1532-1648 | `_start_voice_listen`, `_on_voice_transcript`, `_generate_voice_response` | `shared/twitch/voice.py` (mixin) |
| 1650-1806 | `_load_dashboard_twitch_config`, `setup_twitch_chat` | **reste** dans `twitch_chat.py` (façade) |

---

## Tâche 1 — Créer le paquet `shared/twitch/`

1.1. Créer `shared/twitch/__init__.py` (vide, ou ré-exporte les mixins pour confort).

1.2. **Helpers sans état d'abord** (les plus sûrs, aucune dépendance à `self`) :
- `shared/twitch/sanitize.py` : déplacer `_sanitize_input` **et** `_strip_stage_directions`.
  - `_strip_stage_directions` est `@staticmethod` (corps ligne 697-708) : la déplacer en **fonction
    module** `strip_stage_directions(text) -> str`.
  - `_sanitize_input` (ligne 863) utilise `self.logger`/`self.bot_id` → la garder en méthode via un
    `class SanitizeMixin` qui la contient (homogène avec les autres blocs).

## Tâche 2 — Extraire les classes déjà autonomes

2.1. `shared/twitch/auth.py` ← couper-coller `class TwitchAuth` (40-165) **tel quel**. Importer en
tête de `twitch_chat.py` : `from shared.twitch.auth import TwitchAuth`. (Vérifier les imports dont
TwitchAuth a besoin : `aiohttp`, `json`, `os`, `time` — les ajouter dans `auth.py`.)

2.2. `shared/twitch/profile.py` ← couper-coller `class TwitchProfile` (166-240) **tel quel** + ses
imports. `from shared.twitch.profile import TwitchProfile` dans la façade.

> Ces deux classes sont indépendantes (pas de couplage à `TwitchChatBot`) → extraction à risque
> quasi nul. **Commiter ici** (`refactor(twitch): extraire TwitchAuth + TwitchProfile`).

## Tâche 3 — Extraire les mixins de `TwitchChatBot`

Pour chaque bloc du tableau marqué « (mixin) », créer un fichier `shared/twitch/<nom>.py` contenant :

```python
class <Nom>Mixin:
    # méthodes déplacées VERBATIM (corps inchangé), elles continuent d'utiliser self.*
```

Ordre recommandé (du moins au plus couplé), **un commit par mixin** pour bissecter facilement :
1. `connection.py` → `ConnectionMixin` (run/refresh/connect loop)
2. `llm.py` → `LlmMixin` (`_generate_response` ; `strip_stage_directions` vit déjà dans `sanitize.py`,
   `LlmMixin` l'appelle via la fonction module)
3. `daily_profile.py` → `DailyProfileMixin`
4. `memory.py` → `ViewerMemoryMixin` (viewers + facts + greet + `_handle_usernotice`)
5. `events.py` → `EventsMixin`
6. `dispatch.py` → `DispatchMixin` (privmsg/command/greeting/interjection)
7. `eventsub_bridge.py` → `EventSubMixin`
8. `voice.py` → `VoiceMixin`

Puis dans `twitch_chat.py`, la déclaration devient :

```python
from shared.twitch.connection import ConnectionMixin
from shared.twitch.llm import LlmMixin
# ... etc.

class TwitchChatBot(
    ConnectionMixin, LlmMixin, DailyProfileMixin, ViewerMemoryMixin,
    EventsMixin, DispatchMixin, EventSubMixin, VoiceMixin, SanitizeMixin,
):
    def __init__(self, ...):   # INCHANGÉ (état central)
    def _parse_tags(...):      # reste (utilisé par connection + dispatch)
    def stop(self):            # reste
```

> **Garde-fou MRO/staticmethod :** `_strip_stage_directions` est appelé en **externe** comme
> `TwitchChatBot._strip_stage_directions(text)`. Comme on déplace le corps en fonction module, ajouter
> dans `TwitchChatBot` (ou un mixin) un **shim** pour ne pas casser les 3 appelants externes :
> ```python
> @staticmethod
> def _strip_stage_directions(text):
>     from shared.twitch.sanitize import strip_stage_directions
>     return strip_stage_directions(text)
> ```
> (Ou migrer les 3 appelants vers `from shared.twitch.sanitize import strip_stage_directions` — mais
> ça touche les bots, donc **préférer le shim** pour rester refactor-pur côté `shared/`.)

## Tâche 4 — Façade `twitch_chat.py`

Après extraction, `twitch_chat.py` ne contient plus que : imports des mixins/classes, la classe
`TwitchChatBot` (init + `_parse_tags` + `stop` + shim `_strip_stage_directions`), `_load_dashboard_twitch_config`
et `setup_twitch_chat`. **Cible ≈ 350-450 lignes** (contre 1806).

---

## Vérification (à exécuter après CHAQUE commit de tâche)

1. `python -m py_compile shared/twitch_chat.py shared/twitch/*.py` → exit 0.
2. **Compat imports bots** (ne doit RIEN renvoyer d'erreur) :
   ```
   python -c "from shared.twitch_chat import setup_twitch_chat, TwitchChatBot, TwitchAuth, TwitchProfile; \
   import inspect; print(len(inspect.signature(setup_twitch_chat).parameters), 'params'); \
   print(callable(TwitchChatBot._strip_stage_directions))"
   ```
   Attendu : le **même** nombre de params qu'avant refactor + `True`.
3. `python -m py_compile JohnnyBot/bot_johnny.py Sheogorath/bot_sheogorath.py shared/twitch_eventsub.py` → exit 0.
4. **Diff de comportement = 0** : `git diff` ne doit montrer que des **déplacements** de lignes
   (corps de méthodes identiques) + imports + la déclaration de classe + le shim. Aucune logique modifiée.
5. `pytest tests/test_twitch_config.py -q` reste vert.

## Hors périmètre (ne pas faire dans ce plan)

- Ne pas modifier les bots (`bot_johnny.py`, `bot_sheogorath.py`) : la façade absorbe tout.
- Ne pas toucher `setup_twitch_chat` (signature/corps) au-delà des imports en tête de fichier.
- Pas de refactor « tant qu'on y est » : aucun renommage de méthode, aucun changement de signature
  interne. Le seul nouveau symbole public est la fonction module `strip_stage_directions` (le reste
  passe par les mixins, invisible de l'extérieur).

## Suite possible (séparée, après ce découpage) — ✅ EXÉCUTÉ

Une fois `shared/twitch/` en place, ajouter des **tests unitaires** ciblés sur les helpers désormais
isolés (`sanitize.py` : injection/strip didascalies ; `daily_profile.py` : cache 1 LLM/jour) — c'est
la reco #5 de l'audit, plus facile une fois le monolithe scindé.

> **Fait.** `tests/test_twitch_sanitize.py` (strip didascalies + plafond longueur + retrait jetons de
> contrôle + détection d'injection insensible aux accents) et `tests/test_twitch_daily_profile.py`
> (garde « 1 appel LLM/jour » : cache mémoire process + cache JSON persistant + régénération si état
> périmé). `pytest tests/ -q` → **52 passed** (dont 17 nouveaux).
