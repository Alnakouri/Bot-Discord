# PLAN — Sheogorath v3 : tutoiement, mordant, longueur adaptive, rapidité, didascalies propres

## Contexte
Test live v2.1 (2026-07-02) : les fixes techniques marchent (crochets `[laugh]` disparus, hype_train
400→403, boucle largement dégelée). MAIS le user demande un virage de FOND + 4 correctifs. Certains
**inversent la v1** (cf. [[plan-sheo-persona-canon]]) — c'est assumé.

Fichiers : `Sheogorath/sheo_data.py` (persona), `Sheogorath/bot_sheogorath.py` (cascade inline +
routage + longueur + `!humeur`), `Sheogorath/sheo_llm.py` (strip + longueur), `shared/twitch/sanitize.py`
(strip générique, bénéficie aux 6 bots). NE PAS toucher `sheo_voice.py`.

⚠️ **Découverte clé** : Sheo n'utilise PAS `shared/llm_cascade.py` pour son chemin principal — il a
sa **propre cascade inline** dans `bot_sheogorath.py` (~l.2210-2388, logs « souffle des vents de folie »).
Le fix `to_thread` déjà posé dans `shared/llm_cascade.py` ne couvre donc PAS Sheo → à refaire ici.

---

## Axe A — TUTOIEMENT (inverse la v1 : vous → tu)
Le user veut que Sheo **tutoie**. On GARDE l'éloquence, la menace, la condescendance — mais en « tu »
(familiarité méprisante/joueuse : le mortel est son jouet, son « pote » qu'il malmène). Sheogorath
tutoyant reste canon (intime avec ses « amis »).

**Réécrire TOUT le « vous/votre » → « tu/ton/tes » dans `sheo_data.py`** :
- `COMEBACK_POOL` (15 répliques) : « Ton audace », « tu peines », « Prends garde », « Tu me dois »…
  (garder les impératifs à Haskill : « Haskill, fais-le taire »).
- `PERSONALITY_BASE` : remplacer « Tu vouvoies TOUJOURS » par « Tu TUTOIES TOUJOURS le mortel, avec une
  familiarité MÉPRISANTE et joueuse (c'est ton jouet, ton pantin) ».
- Les 3 blocs `COMEDY_EXAMPLES_NEUTRAL / _MANIA / _DEMENTIA` : tout passer en « tu ».
- Suffixes d'humeur + leurs EXEMPLES (l.665-693).
- Bloc inférence de genre (l.658-661) : « Tu es devenu / devenue un fromage ! » (garder l'accord
  masculin/féminin du participe, juste vous→tu).
- Garder la règle mention `<@ID>` et `{comebacks_placeholder}`.
- ⚠️ Vérifier qu'il ne reste AUCUN « vous/votre/-vous » résiduel : `grep -in "vous\|votre" sheo_data.py`.

## Axe B — PLUS MORDANT / MOINS PACIFISTE (le cœur de la demande)
Le user : « trop pacifiste, il ne se défend plus par une répartie cinglante comme avant ». La v1/v2
l'a trop poli/mesuré. Quand on l'ATTAQUE, il doit rendre coup pour coup, en PIRE.

- `PERSONALITY_BASE` (bloc RÈGLE D'OR) — ajouter/renforcer :
  « FACE À UNE ATTAQUE (insulte, mépris, ordre de te taire) : sois IMPITOYABLE. Réplique du tac au tac,
  sèchement, cruellement — humilie, retourne l'insulte en pire. AUCUNE politesse, AUCune mesure, pas de
  'mais soit...' conciliant. Tu es un Prince Daedra qu'on vient de manquer de respect : fais-le PAYER
  verbalement. »
- Renforcer les few-shot d'INSULTE des 3 humeurs : 1re phrase = gifle verbale immédiate (pas de préambule
  poli, pas de question rhétorique molle). Modèle « avant » = tranchant, imprévisible, méchant-drôle.
- Retirer les tournures conciliantes (« Mais soit... », « Très bien. ») en tête de riposte à une attaque.

## Axe C — LONGUEUR ADAPTIVE (règle aussi les réponses coupées)
Le user : « parfois réponse trop longue inutilement, je veux long OU court au besoin ». Aujourd'hui
`force_short_response(max_sentences=4)` (`sheo_llm.py:116`) COUPE dur → tue les chutes de blague
(bug constaté). Et `max_tokens=300` partout.

**Piloter la longueur par le TYPE de requête** (`routing["type"]`) :
- **REPARTEE** (attaque/banter adressé) → COURT et sec : `max_tokens ≈ 120`, `force_short_response`
  à **2-3 phrases**. Un jab, pas un paragraphe.
- **TEXT** (question, récit, digression) → libre : `max_tokens = 300` (voire 400), `force_short` à
  **6 phrases** (assez pour une histoire complète → plus de chute coupée).
- `PERSONALITY_BASE` — ajouter : « LONGUEUR : quand on t'attaque, réplique COURTE et cinglante (1-2
  phrases). Quand tu racontes, digresses ou expliques, développe librement. JAMAIS de remplissage. »
- `force_short_response` : accepter `max_sentences` en paramètre depuis l'appelant selon le type.

## Axe D — DIDASCALIES EN PROSE (fuite constatée v2.1)
En interdisant `[laugh]`, le modèle narre en clair : « un soupir théâtral », « Un rire cristallin,
soudain glacé », « <Un silence. Puis un chuchotement rauque...> ». Le strip actuel ne prend que les
didascalies en VERBE, pas les groupes nominaux ni les `<...>` à espaces.

1. **Prompt** (`sheo_data.py` ~l.634) : RETIRER l'exemple « (un soupir) » (il encourage la fuite) et
   durcir : « Pour rire, écris une onomatopée à la 1re personne ('Haha !', 'Héhé'). N'écris JAMAIS de
   didascalie narrée (ni [crochets], ni <chevrons>, ni 'un rire cristallin', ni action à la 3e
   personne) : tu PARLES, tu ne te décris pas. »
2. **Filet** (`shared/twitch/sanitize.py`, bénéficie aux 6 bots) — étendre :
   - `clean_internal_tags` (`sheo_llm.py`) ou sanitize : strip des `<...>` **contenant un espace**
     (`re.sub(r"<[^>]*\s[^>]*>", "", txt)`) — SAFE : les mentions `<@123>` et emojis `<:x:1>` n'ont
     jamais d'espace.
   - `strip_bare_stage_directions` : ajouter les didascalies en GROUPE NOMINAL d'émotion, curées et
     ancrées (début / après ponctuation), tail minuscule jusqu'au 1er mot capitalisé :
     `(?:un|une|le|la|d['’]un)\s+(?:soupir|rire|ricanement|chuchotement|silence|sourire|grognement|souffle|gloussement)\w*` + tail.
   - ⚠️ Rester conservateur (ne pas rogner du vrai dialogue) + tests de non-régression.

## Axe E — RAPIDITÉ (Sheo trop lent, « une éternité »)
Cause : les appels inline de Sheo sont **synchrones** → ils gèlent la boucle (WS EventSub meurt sur
trigger Twitch), ET Mistral-large peut traîner (pics à ~47s).

**⚠️ ORDRE DE CASCADE IMPOSÉ PAR LE USER (2026-07-02) : Mistral-large → Llama-3.3-70b (Groq) → Dolphin
`:free`. NE PAS mettre Groq en tête.** Le « secours » (3e échelon) = `cognitivecomputations/dolphin-mistral-24b-venice-edition:free`
(choix Claude : décensuré/mordant, sert l'Axe B). On garde donc `get_model_cascade(REPARTEE)` tel quel.

1. **Dégeler la boucle (le vrai fix WS)** — envelopper TOUS les appels bloquants de la cascade inline de
   Sheo (`bot_sheogorath.py` ~l.2268/2281/2317/2333/2344/2374 + l'appel Gemini avant l.2240) dans
   `asyncio.to_thread(...)`. (`import asyncio` à vérifier en tête.)
2. **Borner le pire cas SANS changer l'ordre** — envelopper chaque appel provider lent dans un timeout :
   `await asyncio.wait_for(asyncio.to_thread(...), timeout=15)`. Si Mistral dépasse ~15s, on `except
   asyncio.TimeoutError` → `continue` vers l'échelon suivant (Llama-3.3, rapide). Ça coupe les pics à
   47s tout en gardant Mistral en tête quand il répond normalement. (Le thread Mistral finit en fond,
   son résultat est ignoré — acceptable.)
3. **Banter court = Mistral plus rapide** — via l'Axe C (REPARTEE `max_tokens ≈ 120`), Mistral génère
   moins de tokens donc répond plus vite sur les ripostes.
- ⚠️ Ne PAS toucher `shared/smart_router.py` (ordre partagé conservé, les 6 bots identiques).

## Axe F — Commande de test `!humeur` (éphémère)
Dans le placeholder `!debug_sheo` (`bot_sheogorath.py:1866`, actuellement `pass`), ajouter une commande
admin **`!humeur <neutral|mania|dementia>`** qui force `current_mood` + `current_system_prompt`
(réutilise `tool_set_mood`). Permet de tester le CONTRASTE des 3 humeurs à la demande (le
`mood_changer` aléatoire 1×/h empêche de comparer la même insulte). À retirer avant le commit final —
OU garder gardé derrière `guild_permissions.administrator` (au choix du user).

---

## Ce qu'on GARDE
- Structure v2 : 3 humeurs distinctes + few-shot par humeur + maître du jeu 2 temps + mordant.
- Crochets `[laugh]` interdits (Axe D renforce), `{comebacks_placeholder}`, mention `<@ID>`, outils
  (wabbajack/set_mood/imposteur), inférence de genre, anti-tic « MOT ?! », emoji rare (0-1), anti-spam.
- `sheo_voice.py` intact (la voix régénère ses rires depuis les onomatopées).

## Ce qu'on INVERSE (assumé, cf. v1)
- Vouvoiement → **tutoiement** (Axe A).
- « 2-4 phrases » rigide → **longueur adaptive** (Axe C).
- Ton mesuré/poli → **mordant impitoyable sur attaque** (Axe B).

## Critères d'acceptation
1. Sheo **tutoie** partout (0 « vous/votre » dans une réponse ; `grep` sheo_data.py propre).
2. Sur une insulte, riposte **courte, sèche, cruelle**, sans préambule poli ni « mais soit... ».
3. Longueur : jab court sur attaque, tirade complète sur récit (plus de blague coupée).
4. Rapidité : plus de gel de boucle (WS EventSub ne meurt plus sur trigger Twitch `👑`) ; plus de pic
   au-delà de ~15s (timeout → bascule Llama-3.3) ; ripostes plus courtes = plus rapides. Ordre de
   cascade Mistral→Llama→Dolphin conservé.
5. Zéro didascalie narrée en texte (`[..]`, `<...>`, « un rire cristallin »).
6. `py_compile` des 4 fichiers OK ; `pytest tests/` vert (dont nouveaux tests strip) ; les bots démarrent.

## Tests
- Étendre `tests/test_sheo_moods.py` (ou nouveau fichier) :
  - `test_sheo_tutoie` : `COMEBACK_POOL` + les 3 `COMEDY_EXAMPLES_*` ne contiennent pas «\bvous\b|\bvotre\b».
  - `test_strip_prose_stage_directions` : `sanitize`/`clean` retire `<Un silence. …>` et « un soupir
    théâtral » MAIS préserve `<@123456>` et le dialogue normal.
  - Garder les tests existants (humeurs distinctes, no-brackets, strip TTS) verts.

## Notes pour Antigravity
- 4 fichiers. Le levier persona = FEW-SHOT (montre le tutoiement + le mordant, ne dicte pas).
- ORDRE cascade IMPOSÉ : Mistral-large → Llama-3.3 → Dolphin:free. NE PAS toucher `shared/smart_router.py`.
- `to_thread` + `wait_for(timeout=15)` sur TOUS les appels providers synchrones de la cascade inline de
  Sheo (c'est le vrai fix WS + le borne-latence).
- Après exécution : `py_compile` ×4 + `pytest tests/` + relire 1 insulte par humeur (tutoiement +
  mordant + pas de didascalie). Test live user : provoquer via `!humeur` dans les 3 humeurs, vérifier
  vitesse + morsure + longueur.
