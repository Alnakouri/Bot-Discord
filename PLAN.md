# PLAN — Clins d'œil « mèmes FR » dans les réponses des bots (banque curée + consigne, 6 bots)

> **Objectif (demande user).** Que les bots glissent, **quand la conversation s'y prête**, une
> référence à un mème/punchline de la culture française (ex. « le fort sûr » de Macron, « 8 morts
> 6 blessés je pète ma bière à ma libellule », OSS 117, etc.) — **passé ou du moment**, mais
> **toujours reformulée DANS la voix du bot**, jamais plaquée ni citée mot pour mot, jamais expliquée,
> jamais forcée. C'est du **sel culturel opportuniste**, pas du name-dropping systématique.
>
> **Décisions cadrées avec le user (2026-06-27) :**
> - **Mécanisme = banque curée + consigne.** Un fonds commun `shared/memes_fr.py` fournit la matière
>   fiable ; une **consigne** injectée dans le prompt système gère le **dosage** et impose la
>   **reformulation persona**.
> - **Portée = les 6 bots** (Johnny, Sheogorath, M'aiq, Alfred, Onizuka, Malena). Même fonds commun,
>   **rendu propre à chacun** (la persona reste sacrée — cf. garde ci-dessous).
> - **Fraîcheur = intemporels curés** à la main. **PAS** de WebSearch/actu auto (coût + risque de réf
>   ratée/sensible). Le fonds est un fichier statique, élargissable plus tard à la main.

> **Cadre [[bots-independants]].** `shared/memes_fr.py` est **optionnel** : chaque bot l'importe en
> `try/except ImportError` avec **fallback no-op** (`def build_meme_consigne(*a, **k): return ""`).
> Aucune dépendance runtime nouvelle, aucun bot ne casse si le module manque. **Zéro appel réseau,
> zéro LLM supplémentaire** : la sélection est locale (matching mots-clés), la consigne est juste
> ajoutée au prompt système déjà envoyé.

> **GARDE PERSONA (exigence n°1 du user : « biensur le bot reste dans son personnage »).** La consigne
> n'injecte **jamais** la réf en clair dans la réponse. Elle dit au bot : « tu PEUX, si ça coule de
> source, évoquer CE clin d'œil **en le reformulant dans TON style** ». Donc :
> - Alfred la glisse avec dédain aristocratique / understatement britannique.
> - M'aiq la tourne en proverbe khajiit / lore Elder Scrolls.
> - Onizuka en vanne de prof de rue.
> - Johnny en punchline cynique de rockerboy.
> - Sheogorath en délire daedrique (fromage/papillons).
> - Malena selon sa persona.
> Le mème est un **angle**, pas une **citation**.

---

## Architecture cible

```
shared/memes_fr.py            # NOUVEAU — banque + sélection + fabrique de consigne (sans état réseau)
tests/test_memes_fr.py        # NOUVEAU — tests unitaires (pertinence, anti-répétition, parcimonie)
<chaque bot>/bot_*.py         # +import try/except, +état anti-répétition, +_get_meme_addition() au prompt
```

Point d'injection identique dans les 6 bots : là où le prompt persona est assemblé juste avant
l'appel LLM. Référence (Onizuka) : `OnizukaBot/bot_onizuka.py:528`
`full_personality = f"{PERSONALITY_PROMPT}{_get_memory_addition()}\n{keyword_boost}"`
→ devient `... {_get_memory_addition()}{_get_meme_addition()}\n{keyword_boost}"`.

---

## Tâche 1 — Créer `shared/memes_fr.py`

### 1.1 Structure de données — la banque (intemporels curés)

```python
# -*- coding: utf-8 -*-
"""Banque de clins d'œil 'mèmes FR' + sélection locale (0 réseau, 0 LLM).
Optionnel : si absent, les bots tournent sans (fallback no-op côté bot)."""

# Chaque entrée : la référence (matière), des tags de déclenchement (mots du contexte qui la
# rendent pertinente), et une note d'angle. Le bot REFORMULE, il ne cite pas.
MEMES_FR = [
    {
        "ref": "le « fort sûr » de Macron (assurance excessive qui sonne faux)",
        "tags": ["sûr", "certain", "garanti", "promesse", "confiance", "évidemment", "président", "politique"],
        "note": "quand quelqu'un affirme un truc avec une assurance exagérée/douteuse",
    },
    {
        "ref": "« 8 morts, 6 blessés, je pète ma bière à ma libellule » (absurde nonchalant)",
        "tags": ["bière", "chaos", "catastrophe", "fête", "absurde", "n'importe quoi", "soirée"],
        "note": "pour commenter un chaos total avec un détachement absurde",
    },
    {
        "ref": "OSS 117 — « Je vous le dis tout net » / le mépris décomplexé de Hubert",
        "tags": ["évidemment", "naïf", "condescendant", "expliquer", "sûr de lui", "vintage"],
        "note": "registre condescendant/daté assumé",
    },
    {
        "ref": "« C'est cuit pour toi mon p'tit pote » (Kaaris)",
        "tags": ["perdu", "fini", "échec", "défi", "battu", "cuit", "fromage"],
        "note": "pour signifier à quelqu'un qu'il a perdu / c'est fichu",
    },
    {
        "ref": "« J'ai glissé chef ! » (Le Dîner de Cons / classique de l'excuse foireuse)",
        "tags": ["erreur", "faute", "excuse", "accident", "désolé", "raté", "maladresse"],
        "note": "pour une excuse foireuse après une bourde",
    },
    {
        "ref": "« Non mais allô quoi » (Nabilla)",
        "tags": ["évident", "stupide", "comprendre", "logique", "basique", "sérieux"],
        "note": "pour souligner que l'autre énonce une évidence / dit une bêtise",
    },
    {
        "ref": "« Et tout le monde s'en fout » (la chronique)",
        "tags": ["inutile", "anecdote", "détail", "personne", "osef", "info"],
        "note": "pour dégonfler une info sans intérêt",
    },
    {
        "ref": "« La rumeur » / « j'ai cru voir... » (registre commère)",
        "tags": ["rumeur", "ragot", "paraît", "entendu", "secret", "potin"],
        "note": "registre commérage",
    },
    # ... Antigravity : ÉTENDRE cette liste à ~20-30 entrées intemporelles et CONSENSUELLES
    # (cinéma culte FR, punchlines rap entrées dans le langage, répliques TV, classiques internet FR).
    # Curation à la main, pas de génération LLM.
]
```

> **Sensibilité (à respecter pendant la curation).** Uniquement des réfs **légères et consensuelles**
> (gaffes politiques bon enfant OK, répliques cultes OK). **Exclure** tout ce qui est haineux,
> discriminatoire, complotiste, ou qui vise une personne réelle de façon dégradante. En cas de doute
> sur une entrée → ne pas l'ajouter.

### 1.2 Sélection locale `pick_meme(context_text, recent_refs)`

- Normalise `context_text` (minuscule, sans accents — réutiliser le helper d'`accents` déjà présent
  dans `shared/twitch/sanitize.py` si exposable, sinon `unicodedata`).
- Score chaque entrée = nombre de `tags` présents dans le contexte. Ne **retient** que les entrées
  avec **score ≥ 1** (pertinence réelle ; pas de réf hors-sujet).
- Exclut toute `ref` dans `recent_refs` (anti-répétition).
- Si plusieurs candidats : `random.choice` parmi les mieux scorés. **Si aucun candidat pertinent →
  retourne `None`** (cas le plus fréquent : on ne force JAMAIS).

### 1.3 Fabrique de consigne `build_meme_consigne(context_text, recent_refs, proba=0.18)`

```python
def build_meme_consigne(context_text: str, recent_refs, proba: float = 0.18) -> str:
    """Retourne une CONSIGNE courte à concaténer au prompt système, ou '' (rien)."""
    import random
    if random.random() > proba:          # parcimonie : la plupart du temps, rien
        return ""
    meme = pick_meme(context_text, recent_refs)
    if not meme:                          # rien de pertinent → rien
        return ""
    return (
        "\n\n[CLIN D'ŒIL CULTUREL — OPTIONNEL ET DISCRET] "
        "Si — et seulement si — ça coule VRAIMENT de source dans cette conversation, tu PEUX "
        "évoquer ce clin d'œil à un mème français EN LE REFORMULANT TOTALEMENT DANS TON STYLE : "
        f"« {meme['ref']} ». "
        "Règles : jamais cité mot pour mot, jamais expliqué, jamais signalé comme une référence, "
        "et UNE SEULE fois max. Si ça ne colle pas naturellement, n'en mets AUCUNE — c'est l'option "
        "par défaut."
    )
```

> **Pourquoi `proba` + score + `recent_refs` cumulés ?** Trois garde-fous indépendants contre la
> saturation : (a) la plupart des messages → `''` (proba) ; (b) même tiré, si rien de pertinent →
> `''` (score) ; (c) jamais 2× la même réf de suite (recent_refs). Le `proba` est réglable par bot
> (ex. Johnny/Onizuka plus hauts, Alfred/M'aiq plus bas si on veut doser par persona — défaut 0.18).

> **Exposer aussi** une constante `__all__ = ["MEMES_FR", "pick_meme", "build_meme_consigne"]`.

## Tâche 2 — Câbler les 6 bots (un commit par bot pour bissecter)

Pour **chaque** `bot_*.py`, 3 petits ajouts, **au plus près du patron existant** :

**2.a — Import optionnel** (à côté des autres imports `shared/`, patron [[bots-independants]]) :
```python
try:
    from shared.memes_fr import build_meme_consigne
    MEMES_AVAILABLE = True
except ImportError:
    MEMES_AVAILABLE = False
    def build_meme_consigne(*a, **k): return ""
```

**2.b — État anti-répétition par salon** (au niveau module, à côté de `response_memory = ...`) :
```python
import collections
meme_recent = collections.defaultdict(lambda: collections.deque(maxlen=8))  # {channel_id: deque[ref]}
```

**2.c — Helper local + injection** dans le handler de message, juste après `_get_memory_addition` :
```python
def _get_meme_addition():
    chan_id = message.channel.id
    consigne = build_meme_consigne(message.content or "", set(meme_recent[chan_id]))
    # mémorise la ref proposée pour ne pas la re-proposer en boucle dans ce salon
    if consigne:
        import re as _re
        m = _re.search(r"« (.+?) »", consigne)
        if m:
            meme_recent[chan_id].append(m.group(1))
    return consigne
```
puis à l'assemblage du prompt :
```python
full_personality = f"{PERSONALITY_PROMPT}{_get_memory_addition()}{_get_meme_addition()}\n{keyword_boost}"
```

> **Adapter au nom réel de la variable de prompt dans chaque bot** (`PERSONALITY_PROMPT`,
> `system_instruction`, `full_system`, etc.). Repérer **tous** les chemins d'assemblage du prompt
> texte (message texte ; et idéalement image/vocal s'ils réutilisent `full_personality`). Au minimum,
> câbler le **chemin texte principal**. Ne PAS toucher aux chemins où ce serait incohérent.

> **Twitch.** Hors périmètre de ce plan (le chat Twitch a sa propre cascade courte et ses propres
> contraintes anti-saturation). Si on l'étend plus tard, ce sera via `shared/twitch/llm.py`, dans un
> plan séparé.

## Tâche 3 — Tests `tests/test_memes_fr.py`

- `pick_meme` retourne **`None`** sur un contexte sans aucun tag pertinent.
- `pick_meme` **n'extrait jamais** une `ref` présente dans `recent_refs`.
- `pick_meme` retourne bien une entrée quand un tag matche (ex. contexte « t'es sûr de toi ? » →
  doit pouvoir tomber sur l'entrée Macron).
- `build_meme_consigne(..., proba=0.0)` → **`""`** (parcimonie absolue).
- `build_meme_consigne(..., proba=1.0)` sur contexte pertinent → contient la balise
  `[CLIN D'ŒIL CULTUREL` **et** l'ordre « reformule dans ton style » (garde persona testée).
- `build_meme_consigne(..., proba=1.0)` sur contexte **non** pertinent → **`""`**.
- (Robustesse accents) un tag sans accent matche un contexte accentué et vice-versa.

---

## Vérification (après chaque commit)

1. `python -m py_compile shared/memes_fr.py <bot modifié>.py` → exit 0.
2. **Import standalone** (patron [[bots-independants]]) : `python -c "import shared.memes_fr as m;
   print(m.build_meme_consigne('t es sur de toi', set(), proba=1.0)[:40] or 'VIDE')"`.
3. `pytest tests/test_memes_fr.py -q` → vert.
4. `pytest tests/ -q` → toujours vert (pas de régression).
5. **Sanity persona** : lire 2-3 sorties de `build_meme_consigne(proba=1.0)` et confirmer que la
   consigne **n'impose jamais** une citation littérale, seulement une reformulation optionnelle.

## Hors périmètre (ne pas faire)

- Pas de WebSearch / mèmes d'actualité auto (décision user : intemporels curés seulement).
- Pas de génération LLM de la banque : curation **manuelle** (qualité + sensibilité maîtrisées).
- Pas de modif du chat Twitch (plan séparé si besoin).
- Pas de nouvelle dépendance pip. Pas d'appel réseau dans `memes_fr.py`.
- Ne pas augmenter la fréquence au point de saturer : `proba` défaut **0.18**, jamais 2× la même réf
  d'affilée par salon. En cas de doute, **moins** plutôt que plus (la rareté fait la punchline).

---
---

# PLAN B — Décret de Sheogorath désactivable depuis le dashboard (Discord + Twitch)

> **Objectif (demande user).** Pouvoir **désactiver le décret** de Sheogorath depuis le dashboard.
> Décision user (2026-06-27) : **un seul toggle** qui coupe à la fois **le décret Discord** (auto
> quotidien `daily_rumor_check_sheo` jours impairs + commande admin `!décret` qui pose rôle+image)
> **ET la commande `!décret` texte sur Twitch**. Le **nettoyage** des rôles existants
> (`decree_cleanup_loop`) **reste actif** quoi qu'il arrive (sinon des rôles resteraient orphelins).

> **Constat archi.** Le dashboard ne gère pour l'instant que la config **Twitch** (`twitch_config.json`
> via `TwitchConfigManager`, `dashboard/backend/twitch_config.py`). Le décret est une **feature Discord**
> → il faut un **petit canal de config Discord** séparé, sur le **même patron** : un fichier
> `data/bot_features.json` écrit par le dashboard et lu par le bot. Dashboard et bots partagent déjà
> `data/` (`DATA_DIR = os.getenv("DATA_DIR", <repo>/data)` côté bots ; `DATA_DIR = ROOT_DIR/"data"`
> côté dashboard, `app.py:36`). Réutiliser exactement cette résolution.

> **Cadre [[bots-independants]].** `shared/bot_features.py` est **optionnel** (import bot en
> `try/except ImportError` + fallback `lambda *a, **k: True` → **feature ON par défaut** si le module
> ou le fichier manquent : un bot déployé seul, sans dashboard, garde son comportement actuel).

## Tâche B1 — Lecture côté bot : `shared/bot_features.py` (NOUVEAU)

Mirror de `_load_dashboard_twitch_config` (`shared/twitch_chat.py:239`).

```python
# -*- coding: utf-8 -*-
import os, json, time
from pathlib import Path
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
_CACHE = {"data": None, "ts": 0.0}
_TTL = 5.0   # relit le fichier au plus toutes les 5 s → toggle quasi-live sans redémarrage

def _load() -> dict:
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _TTL:
        return _CACHE["data"]
    path = os.path.join(DATA_DIR, "bot_features.json")
    data = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = {}   # illisible → on n'empêche jamais la feature (default géré par l'appelant)
    _CACHE["data"] = data; _CACHE["ts"] = now
    return data

def is_feature_enabled(bot_id: str, feature: str, default: bool = True) -> bool:
    """True si la feature est active pour ce bot. Fichier/clé absents → `default`."""
    bot = _load().get(bot_id, {})
    val = bot.get(feature, default)
    return bool(val) if isinstance(val, bool) else default
```

> **TTL 5 s** : permet de désactiver dans le dashboard et voir l'effet sans redémarrer le bot, sans
> marteler le disque dans les boucles `@tasks.loop`. Lecture seule côté bot (jamais d'écriture).

## Tâche B2 — Brancher les 3 chemins du décret dans `Sheogorath/bot_sheogorath.py`

Import optionnel (à côté des autres imports `shared/`) :
```python
try:
    from shared.bot_features import is_feature_enabled
except ImportError:
    def is_feature_enabled(*a, **k): return True
```
`bot_id` de Sheo = **`"sheogorath"`** (cf. `dashboard/backend/twitch_config.py:317`). Feature = `"decret_enabled"`.

**B2.1 — Décret auto quotidien.** Dans la fonction de publication de rumeur/décret (la coroutine
appelée par `daily_rumor_check_sheo`, autour de `bot_sheogorath.py:893-926`), **tout en haut**, avant
toute génération/collecte :
```python
if not is_feature_enabled("sheogorath", "decret_enabled", default=True):
    logger.info("🚫 [DÉCRET] Désactivé via dashboard — publication auto ignorée.")
    return
```

**B2.2 — Commande Discord `!décret`.** Dans `decret_cmd` (`bot_sheogorath.py:1058-1060`), juste après
le contrôle des permissions :
```python
if not is_feature_enabled("sheogorath", "decret_enabled", default=True):
    await ctx.send("🚫 Le Prince a suspendu ses décrets… pour l'instant. (désactivé via le dashboard)")
    return
```
> Formuler le refus **en personnage** (Sheogorath) plutôt qu'un message technique sec, mais garder la
> mention « désactivé via le dashboard » pour que l'admin comprenne.

**B2.3 — Commande Twitch `!décret`.** Dans `cmd_decret` (`bot_sheogorath.py:642`, le générateur
texte-seul), au tout début :
```python
if not is_feature_enabled("sheogorath", "decret_enabled", default=True):
    return "Le Prince a rangé ses décrets dans un fromage. Reviens plus tard, mortel."  # en personnage
```

> **NE PAS toucher** `decree_cleanup_loop` ni `cleanup_old_decree_roles` : le nettoyage doit tourner
> même décret désactivé (purge des rôles déjà posés). Idem `apply_decree_role` reste tel quel.

## Tâche B3 — Écriture côté dashboard : `dashboard/backend/features_config.py` (NOUVEAU)

Mirror **minimal** de `TwitchConfigManager` (même style : `_load_raw`/`_save_raw` atomique,
`get_all` avec valeurs par défaut depuis `BOT_REGISTRY`).

```python
import os, json
from pathlib import Path
from bot_manager import BOT_REGISTRY

DEFAULTS = {"decret_enabled": True}   # extensible : ajouter ici les futures features Discord

class FeaturesConfigManager:
    def __init__(self, data_dir: Path):
        self.config_path = data_dir / "bot_features.json"
        self.data_dir = data_dir
    def _load_raw(self) -> dict: ...        # idem TwitchConfigManager (try/except → {})
    def _save_raw(self, data: dict): ...     # idem (écriture atomique via .tmp + os.replace)
    def get_all(self) -> dict:
        cfg = self._load_raw(); updated = False
        for bot_id in BOT_REGISTRY:
            if bot_id not in cfg: cfg[bot_id] = {}; updated = True
            for k, v in DEFAULTS.items():
                if k not in cfg[bot_id]: cfg[bot_id][k] = v; updated = True
        if updated: self._save_raw(cfg)
        return cfg
    def get_bot(self, bot_id: str) -> dict:
        if bot_id not in BOT_REGISTRY: raise ValueError(f"Bot '{bot_id}' non enregistré.")
        return self.get_all()[bot_id]
    def set_feature(self, bot_id: str, feature: str, value: bool):
        if bot_id not in BOT_REGISTRY: raise ValueError(f"Bot '{bot_id}' non enregistré.")
        if feature not in DEFAULTS: raise ValueError(f"Feature '{feature}' inconnue.")
        if not isinstance(value, bool): raise ValueError("'value' doit être un booléen.")
        cfg = self.get_all(); cfg[bot_id][feature] = value; self._save_raw(cfg)
```

## Tâche B4 — Endpoints API `dashboard/backend/app.py`

À côté de `twitch_config_manager = TwitchConfigManager(DATA_DIR)` (`app.py:134`) :
```python
from features_config import FeaturesConfigManager
features_config_manager = FeaturesConfigManager(DATA_DIR)
```
Mirror des endpoints `@app.get/put("/api/twitch/chat/{bot_id}")` (`app.py:356-372`) :
```python
@app.get("/api/features/{bot_id}")
def get_features(bot_id: str):
    try: return features_config_manager.get_bot(bot_id)
    except ValueError as e: raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/features/{bot_id}")
def set_feature(bot_id: str, body: dict):
    try:
        features_config_manager.set_feature(bot_id, body["feature"], body["value"])
        return {"ok": True}
    except (ValueError, KeyError) as e: raise HTTPException(status_code=400, detail=str(e))
```
> Respecter le **même style d'auth/erreurs** que les endpoints `/api/twitch/*` voisins (dépendances
> de session si présentes). Ne pas inventer un schéma d'auth différent.

## Tâche B5 — Frontend : toggle « Décret » dans la carte Sheogorath

- `dashboard/frontend/index.html` : ajouter, dans la section/onglet du bot **sheogorath**, un petit bloc
  « **Fonctionnalités Discord** » avec une case **« Décret activé »** (`<input type="checkbox" id="feat-decret-sheogorath">`).
  Mirror visuel des toggles chat Twitch existants (events/interjections/greetings).
- `dashboard/frontend/js/app.js` : mirror de `loadChatConfig`/`updateChatConfig` (~lignes 645-685) :
  ```js
  async function loadFeatures(botId) {
      const res = await fetch(`${API_BASE}/features/${botId}`);
      const cfg = await res.json();
      const el = document.getElementById(`feat-decret-${botId}`);
      if (el) el.checked = cfg.decret_enabled !== false;
  }
  async function updateDecret(botId, value) {
      await fetch(`${API_BASE}/features/${botId}`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feature: "decret_enabled", value })
      });
  }
  ```
  Appeler `loadFeatures("sheogorath")` au chargement de la carte ; câbler `onchange` de la case →
  `updateDecret("sheogorath", el.checked)`. (Pour l'instant **seul sheogorath** affiche ce toggle ;
  l'archi reste générique pour d'autres bots/features plus tard.)

## Tâche B6 — Tests `tests/test_bot_features.py` (NOUVEAU)

- Fichier `bot_features.json` **absent** → `is_feature_enabled(..., default=True)` == `True`
  (et `default=False` == `False`). (Pointer `DATA_DIR` sur un tmp via monkeypatch/env.)
- Fichier avec `{"sheogorath": {"decret_enabled": false}}` → renvoie `False`.
- JSON corrompu → renvoie le `default` (jamais d'exception qui remonte).
- `FeaturesConfigManager.set_feature("sheogorath","decret_enabled",False)` puis `get_bot` → `False` ;
  `set_feature` sur bot inconnu ou feature inconnue → `ValueError`.
- (Cache TTL) après `set_feature`, une relecture **après expiration TTL** reflète la nouvelle valeur.

---

## Vérification PLAN B (après chaque commit)

1. `python -m py_compile shared/bot_features.py dashboard/backend/features_config.py Sheogorath/bot_sheogorath.py dashboard/backend/app.py` → exit 0.
2. **Default ON** (déploiement sans dashboard) : `python -c "from shared.bot_features import is_feature_enabled; print(is_feature_enabled('sheogorath','decret_enabled'))"` → `True`.
3. `pytest tests/test_bot_features.py -q` → vert ; `pytest tests/ -q` → pas de régression.
4. **Bout-en-bout manuel** (gotcha [[plan-dashboard-hybride-bots]] : relancer `start_dashboard.bat`
   après modif backend) : toggler « Décret activé » OFF dans le dashboard → `data/bot_features.json`
   passe à `false` → dans ≤5 s, `!décret` (Discord + Twitch) refuse en personnage et l'auto quotidien
   est sauté ; ON → décret revient.

## Hors périmètre PLAN B

- Ne pas désactiver/altérer le **nettoyage** des rôles de décret (doit tourner en permanence).
- Pas de nouveau système d'auth dashboard (réutiliser celui des endpoints `/api/twitch/*`).
- Pas de toggle pour les autres bots dans ce plan (archi générique posée, mais UI = sheogorath seul).
- Pas de migration des autres features vers `bot_features.json` ici (le fichier est extensible, on ne
  déplace rien d'existant).
