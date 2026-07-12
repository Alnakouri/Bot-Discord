# PLAN — Sheo : longueur = pertinence (anti-meublage) + anti-tics d'ouverture/clôture

> Antigravity exécute. Claude a rédigé. Cible : `Sheogorath/`. Deux problèmes distincts,
> deux leviers. Édition `sheo_data.py` = Discord + Twitch (via `system_prompt_provider`).

## Contexte / retour user

Test live 2026-07-13. Deux plaintes :
1. **Sheo meuble** — réponses trop longues pour ce qu'elles disent. La longueur doit dépendre
   de la PERTINENCE, pas remplir un budget.
2. **Il réutilise les mêmes DÉBUTS et FINS de phrase** (tics d'ouverture/clôture).

Décisions user (2026-07-13) :
- Longueur par défaut (hors répartie) : **6 → 4 phrases** (300 → 200 tokens). REPARTEE inchangé (2 / 120).
- Anti-tics : **injection dans le prompt** (0 latence, 0 coût, pas de régénération).

## Causes racines (prouvées)

- **Le plafond est décidé À L'AVANCE par un classifieur**, pas par le contenu
  (`bot_sheogorath.py:2236-2241`) : REPARTEE → 2ph/120t, sinon → **6ph/300t**. Un budget large =
  le LLM le remplit → meublage. On garde le principe du plafond (filet de sécurité) mais on le
  **baisse** et on reframe le prompt pour que le défaut soit « le plus court qui fait mouche ».
- **L'anti-répétition actuel est trop grossier** (`bot_sheogorath.py:2149-2156`) : il liste les
  5 dernières réponses ENTIÈRES (60 premiers car.) et interdit de les répéter. Il ne cible PAS
  les **amorces** ni les **clôtures** — donc les tics de début/fin passent au travers.
- La consigne persona « varie tes ENTRÉES » (`sheo_data.py`) est seulement *espérée*, jamais
  **vérifiée contre l'historique réel**.

---

## A. Longueur : plafond plus bas + prompt anti-meublage

### A.1 — `bot_sheogorath.py:2240-2241`
Baisser le bucket « non-répartie » :
```python
    else:
        max_tokens_val = 200   # était 300
        max_sentences_val = 4  # était 6
```
Ne PAS toucher au bucket REPARTEE (2 / 120).

### A.2 — `sheo_data.py`, ligne LONGUEUR (actuellement l.687)
Reformuler pour que le plafond soit un MAXIMUM d'urgence, jamais une cible. Remplacer :
> « - LONGUEUR : quand on t'attaque, réplique COURTE et cinglante (1-2 phrases). Quand tu racontes,
> digresses ou expliques, développe librement. JAMAIS de remplissage. »

par (esprit — Antigravity ajuste la formulation, garde le ton) :
> « - LONGUEUR = PERTINENCE, JAMAIS remplissage. Tu dis ce que tu as à dire puis tu t'ARRÊTES —
> dès que la pique a touché ou que l'idée folle a atterri, tu te tais. Le plus court qui fait mouche
> gagne toujours. Sur attaque : 1-2 phrases sèches. Un récit ou une digression déjantée peut
> respirer (jusqu'à ~4 phrases MAX), mais chaque phrase doit AJOUTER (une image neuve, un virage) —
> zéro phrase de transition, zéro reformulation de ce que tu viens de dire, zéro conclusion polie. »

Effet : atteint Discord ET Twitch (un seul fichier).

---

## B. Anti-tics d'ouverture et de clôture (injection prompt)

Idée : avant l'appel LLM, extraire des dernières réponses de Sheo leurs **amorces** (4-5 premiers
mots) et leurs **clôtures** (dernière proposition, emoji de ton retiré), puis les lister au modèle
comme INTERDITES. Complète le bloc anti-répétition existant (qui reste utile pour les idées entières).

### B.1 — Nouveau helper pur dans `sheo_llm.py`
Ajouter une fonction pure (testable, 0 I/O) :
```python
def build_anti_tic_consigne(recent_responses, n=5):
    """À partir des N dernières réponses, liste les AMORCES et CLÔTURES à éviter.
    Retourne un fragment de prompt (str), ou "" si rien d'exploitable."""
```
Logique :
- Pour chaque réponse récente (les `n` dernières) :
  - **Amorce** : retirer une éventuelle balise `<thought>…</thought>`, prendre les 4-5 premiers
    mots (normalisés : minuscules, ponctuation de bord retirée). Ignorer si < 2 mots.
  - **Clôture** : retirer l'emoji de ton final avec `_TRAILING_EMOJI_RE` (déjà présent l.116-124),
    découper en phrases (`re.split(r'(?<=[.!?]) +', …)`), prendre la DERNIÈRE phrase, en garder les
    ~5 derniers mots normalisés.
- Dédupliquer amorces et clôtures.
- Si non vide, retourner un fragment du style :
  ```
  [ANTI-TICS — VARIE OU MEURS]
  Tu as OUVERT tes dernières répliques par : "…", "…". INTERDIT de rouvrir par une de ces amorces
  ou une variation proche — trouve une entrée NEUVE (question sèche, non-sequitur, ordre, constat).
  Tu as CLÔTURÉ par : "…", "…". INTERDIT de refinir pareil (surtout pas un "Haskill, note ça"
  recyclé) — change de chute.
  ```
- Robustesse : try/except autour du parsing, retourne "" si quoi que ce soit échoue (ne JAMAIS
  casser la génération pour un anti-tic).

### B.2 — Câbler dans `bot_sheogorath.py` (Discord), autour de l.2149-2156
Après le bloc anti-répétition existant (le GARDER), ajouter :
```python
    anti_tic = build_anti_tic_consigne(recent_responses)
    if anti_tic:
        system_instruction += "\n\n" + anti_tic
```
(importer `build_anti_tic_consigne` depuis `sheo_llm`.)

### B.3 — Twitch (parité, SI faisable simplement)
Vérifier si le chemin Twitch de Sheo (`system_prompt_provider` / `shared/twitch/`) a accès à un
historique récent de ses propres réponses. **Si oui** : appeler le même `build_anti_tic_consigne`
et l'ajouter au system prompt Twitch. **Si non** (pas de mémoire de réponses branchée côté Twitch) :
HORS-SCOPE pour ce plan — le noter, ne pas bricoler une nouvelle mémoire ici.

---

## Tests

- `tests/` : ajouter `test_sheo_anti_tic.py` (unitaire, pur) —
  - amorces + clôtures extraites correctement ;
  - emoji de ton bien retiré de la clôture ;
  - liste vide / réponses vides → retourne "" (pas de crash) ;
  - balise `<thought>` ignorée dans l'amorce.
- Vérifier que `test_sheo_moods` reste vert.

## Validation
`python -m py_compile Sheogorath/sheo_data.py Sheogorath/bot_sheogorath.py Sheogorath/sheo_llm.py`
puis `pytest -q -k "sheo"`.

## NE PAS toucher
- L'emoji de ton final (obligatoire), le rendu écrit majuscules ([[plan-sheo-etat-humeur-ecrit]]),
  l'anti-écho « MOT ?! », le tutoiement, le ToS, l'easter egg ALL CAPS.
- Le bloc anti-répétition existant (l.2149-2156) : on le COMPLÈTE, on ne le remplace pas.
- La FOLIE motrice qu'on vient de câbler ([[plan-sheo-folie-motrice]]) : la baisse de longueur ne
  doit PAS re-brider le déjanté — 4 phrases laissent de l'air pour une digression qui déraille.

## Après exécution
py_compile + pytest verts → commit → push → `docker compose up -d --build` → test live :
juger « moins de meublage ? » ET « il ne recommence plus ses phrases pareil ? ».
Voir [[plan-sheo-folie-motrice]], [[plan-sheo-persona-canon]], [[sheo-continuite-et-ton]].
