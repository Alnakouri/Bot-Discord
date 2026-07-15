# PLAN — Anti-doublon Discord↔Twitch (Sheo pilote) + anti-teaser + sondes live automatisées

> Antigravity exécute. Claude a rédigé (2026-07-15).
> Cibles : `shared/twitch/llm.py`, `Sheogorath/bot_sheogorath.py`, `Sheogorath/sheo_data.py`,
> `tools/sonde_twitch.py` (nouveau), + tests. Repérer par CONTENU, pas par numéro de ligne.

## Contexte / constat (test live 2026-07-15 ~20:42)

À la même insulte, Sheo a sorti quasi la MÊME punchline sur les deux canaux :
- Discord : « Quelle poésie ! Quelle élégance ! … des sonnets pour les latrines de Dementia »
- Twitch : « Quelle poésie ! Quelle élégance ! … des sonnets pour les égouts »

Cause : chaque canal a son anti-répétition (Discord `response_memory` par guild,
Twitch `recent_self_responses` par salon) mais ils ne se VOIENT pas. Même persona + même
input + même humeur → Mistral converge. Les deux tournent dans le MÊME process Python.

Second constat : le filet de phrases peut guillotiner une histoire NON invitée en laissant
une promesse en l'air (« Très bien. Une histoire, donc. 🧀 » — puis rien).

## Phase A — Pont anti-doublon inter-canaux (générique + câblage Sheo)

### A1. Hook générique côté Twitch (`shared/twitch/llm.py`)

Dans la méthode qui construit le prompt (celle qui contient `[ANTI-RÉPÉTITION ABSOLUE]`
et lit `self.recent_self_responses.get(chan_lower)`) :

1. Juste après avoir obtenu `self_recent`, fusionner un apport externe optionnel :
```python
# PONT INTER-CANAUX (optionnel) : un bot peut fournir ses dernières réponses
# émises AILLEURS (ex. Discord) pour que l'anti-répétition couvre les 2 canaux.
extra_recent = []
if getattr(self, "extra_recent_provider", None):
    try:
        extra_recent = list(self.extra_recent_provider() or [])
    except Exception as e:
        self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] extra_recent_provider a échoué : {e}")
merged_recent = (list(self_recent) if self_recent else []) + extra_recent
```
2. Utiliser `merged_recent` (au lieu de `self_recent`) pour : le bloc
   `[ANTI-RÉPÉTITION ABSOLUE]` (snippets `[-5:]` → passer à `[-8:]` puisque 2 canaux)
   ET l'appel `_build_anti_tic_consigne(...)`.
3. ⚠️ GÉNÉRIQUE : même patron que `tone_directive_provider` (hook optionnel, try/except,
   aucune logique spécifique-bot dans shared/). Ne PAS toucher `_strip_repeated_opening`
   ni l'écriture de `recent_self_responses` (l'apport externe est en lecture seule).

### A2. Câblage Sheo (`Sheogorath/bot_sheogorath.py`)

1. Helper pur (dans `sheo_llm.py`, à côté de `build_anti_tic_consigne`) :
```python
def merge_recent_responses(*sources, limit=8):
    """Fusionne des listes de réponses récentes (None-safe), dédoublonne en gardant l'ordre."""
    seen, out = set(), []
    for src in sources:
        for r in (src or []):
            if r and r not in seen:
                seen.add(r)
                out.append(r)
    return out[-limit:]
```
2. Sens Discord→Twitch : là où le client de chat Twitch est créé/configuré (près du
   câblage de `tone_directive_provider` s'il existe pour Sheo, sinon près de
   `setup_twitch_chat`), poser :
   `client.extra_recent_provider = lambda: [r for hist in response_memory.memory.values() for r in hist][-6:]`
   (accès en lecture au store Discord existant ; pas de nouvel état).
3. Sens Twitch→Discord : dans la construction du prompt Discord, remplacer
   `recent_responses = response_memory.get_recent(message.guild.id)` par une fusion :
```python
recent_responses = merge_recent_responses(
    response_memory.get_recent(message.guild.id),
    _twitch_recent_responses(),   # helper local : lit recent_self_responses du client twitch s'il existe
)
```
   `_twitch_recent_responses()` : retourne `[]` si le client Twitch n'est pas démarré
   (try/except AttributeError + garde None) — le bot doit rester déployable SEUL,
   Twitch coupé ne casse rien.
4. Les blocs existants `[ANTI-RÉPÉTITION ABSOLUE]` + `build_anti_tic_consigne` côté
   Discord consomment la liste fusionnée sans autre modification.

## Phase B — Anti-teaser (`Sheogorath/sheo_data.py`)

Dans le bloc « ⚖️ QUI DÉCIDE DE LA LONGUEUR », ajouter UNE puce :
```
  * N'ANNONCE JAMAIS une histoire, une suite ou une chute que tu ne donnes pas DANS ce
    message. Pas de « Très bien. Une histoire, donc. » suivi de rien : si tu n'as pas la
    place de la raconter, ne la promets pas.
```

## Phase C — Sondes live automatisées (`tools/sonde_twitch.py`, nouveau)

But : remplacer les tests live manuels de fin de chapitre par un script relançable.

1. **Lecture** : connexion IRC anonyme Twitch (`nick justinfan<rand>`, pas d'auth,
   lecture seule) sur le salon tiré de `data/twitch_config.json` →
   `<bot>/chat_channels[0]`.
2. **Envoi** : compte du STREAMER (les comptes bots sont mutuellement ignorés via
   TWITCH_PEER_BOTS → inutilisables comme sondeurs). Réutiliser le flux d'auth device
   existant du projet pour créer `data/twitch_chat_auth_probe.json` (une seule
   autorisation manuelle du user, puis refresh automatique comme les bots).
   Si le token probe est absent → message clair « lance d'abord --auth » et sortie 1.
3. **Sondes par défaut** (CLI `--bot sheogorath`, options `--probe` répétable) :
   | envoi | assertions déterministes |
   |---|---|
   | `<trigger> es-tu fou ?` | réponse < 60 s, ≤ 4 phrases |
   | `<trigger> t'es nul` | ≤ 4 phrases |
   | `<trigger> raconte-moi une histoire` | réponse arrive, ≤ 10 phrases |
   | `<trigger> n'importe quoi` | ≤ 4 phrases, ne se TERMINE PAS par une annonce vide (regex `(histoire|suite|conte)[,.]?\s*(donc)?\s*[.!?…]*\s*\W*$` sur la dernière phrase → WARN, pas FAIL) |
   Assertions communes : se termine par ponctuation finale ou emoji (pas de coupe en
   plein mot) ; l'ouverture ne cite pas la sonde entre guillemets (garde anti-écho).
4. Comptage de phrases : IMPORTER la logique existante (le split `\s+` après `[.!?]`,
   les « ... » neutres) depuis `shared/twitch/llm.py` — ne PAS réécrire une variante
   (leçon du bug e1c7e50).
5. Sortie : tableau `sonde → OK/FAIL/WARN + la réponse reçue`, code retour ≠ 0 si un FAIL.
   Espacement 15 s entre sondes (anti rate-limit + laisser le bot répondre).
6. Le script vit dans `tools/` (PAS dans `tests/` : `testpaths` pytest ne doit pas le
   collecter ; il exige le réseau + un bot déployé).

## Phase D — Tests (unitaires, sans réseau)

1. `merge_recent_responses` : None-safe, dédoublonne, garde l'ordre, respecte `limit`.
2. Hook `extra_recent_provider` : provider mocké → les snippets Twitch incluent les
   réponses « Discord » ; provider qui lève → warning + comportement inchangé ;
   pas de provider → strictement identique à avant (non-régression).
3. Côté Discord : la fusion passe bien au bloc anti-répétition (test sur le helper).
4. Parsing des sondes : les assertions de C3 sur des réponses canned (courte OK,
   longue FAIL, coupe en plein mot FAIL, teaser → WARN).
5. Suite complète verte (219+).

## Garde-fous

- `shared/twitch/llm.py` reste 100 % générique (hook optionnel, défaut = comportement actuel).
- Bots indépendants : tout accès croisé Discord↔Twitch est défensif (try/except +
  fallback `[]`) — chaque moitié marche sans l'autre.
- Ne PAS toucher : filet `sentence_budget`/`_force_sentence_cap`, humeurs, few-shot,
  max_tokens, garde anti-écho.
- Le pont est en RAM, même process — AUCUNE persistance ni fichier nouveau (sauf le
  token probe, qui suit le format d'auth existant).
- Rollout Johnny/Sugar du pont : PAS dans ce chapitre (Sheo pilote ; le hook générique
  rend le rollout trivial ensuite).

## Déploiement + validation (après commit)

`docker compose up -d --build --force-recreate sheogorath` (shared/ touché → --build).
Puis : auth one-shot `python tools/sonde_twitch.py --auth`, et
`python tools/sonde_twitch.py --bot sheogorath` → tout vert.
Validation du pont : envoyer la MÊME insulte sur Discord puis sur Twitch à < 2 min
d'écart → les deux réponses ne doivent PAS partager leur punchline/amorce.
