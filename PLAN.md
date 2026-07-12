# PLAN — Sheo : rendre son ÉTAT et son CHANGEMENT D'HUMEUR visibles à l'écrit (Discord ⇄ Twitch)

## Contexte & décision (validée avec l'utilisateur)
Aujourd'hui Sheo écrit « à plat » : on ne **perçoit pas** son état émotionnel ni son
changement d'humeur dans le texte. Demande utilisateur :
1. **Rendu typographique de l'émotion** : quand Sheo **crie**, il écrit en **MAJUSCULES** ;
   quand il ne crie pas, il **parle normalement** (casse normale).
2. Ce rendu doit **suivre l'humeur** (neutral / mania / dementia) → le **changement d'humeur**
   doit se **voir** à l'écrit, pas seulement dans le ton.
3. Des **emojis** doivent être présents dans ses réponses (en plus/au service de l'état).

### Cause racine (prouvée dans le code)
- La seule consigne « MAJUSCULES pour les cris » est **enterrée dans le bloc « DIRECTIVES
  VOCALES (TTS) »** (`Sheogorath/sheo_data.py:639`). Le LLM la lit comme une consigne *voix*,
  pas comme un rendu *écrit* → il ne l'applique quasiment jamais au chat.
- Les 3 `MOOD_PROMPTS` (`sheo_data.py:670-697`) décrivent TON / ATMOSPHÈRE / STYLE mais **aucune
  ligne de RENDU ÉCRIT** (casse, cris, chuchotement) → le passage neutral→mania→dementia ne
  change pas l'aspect visuel du texte.
- L'**emoji de ton final existe déjà** et fonctionne (`sheo_data.py:633-635`, préservé par
  `_TRAILING_EMOJI_RE` dans `sheo_llm.py:119-138`, test live 🧀/😏 validé). On ne le refait PAS :
  on le **varie par humeur** et on autorise **un** emoji expressif de plus en MANIA.

### Portée & parité
- **Un seul fichier** : `Sheogorath/sheo_data.py` (`PERSONALITY_BASE` + les 3 `MOOD_PROMPTS`).
  **0 code.** Discord ET Twitch lisent ces prompts via `system_prompt_provider=
  get_current_system_prompt` (`bot_sheogorath.py:413` Discord, `:817` Twitch) → **une seule
  édition couvre les deux plateformes** (règle « la persona change des deux côtés à la fois »).
- Workflow : **Antigravity exécute. Claude a rédigé.**

---

## PARTIE A — Rendu écrit de l'état émotionnel (le cœur)

### A.1 — `PERSONALITY_BASE` : un bloc dédié « RENDU ÉCRIT » (sortir la consigne du TTS)
Dans `PERSONALITY_BASE` (`sheo_data.py:623-668`), **après** le bloc « EMOJI DE TON » (après la
ligne 635) et **avant** le bloc « DIRECTIVES VOCALES », **insérer** un nouveau bloc :
```
"\n"
"✍️ **RENDU ÉCRIT DE TON ÉTAT — ta typographie DOIT trahir ton émotion** ✍️\n"
"- Tu ne parles pas toujours sur le même ton : ton TEXTE doit le MONTRER. Quand tu CRIES "
"(pic d'excitation, de colère, de révélation, de jubilation), écris ces mots-là en "
"MAJUSCULES. Quand tu es posé, écris en casse normale. Quand tu murmures, baisse la voix : "
"phrases courtes, feutrées, points de suspension.\n"
"- Le cri est un PROJECTEUR, pas un mur : mets en MAJUSCULES 1 à 3 mots-clés OU une courte "
"exclamation ('MAGNIFIQUE !', 'SILENCE !', 'HAHA !'), JAMAIS la réplique entière (illisible). "
"En moyenne la plupart de tes phrases restent en casse normale ; le cri PONCTUE.\n"
"- ⚠️ Crier n'est PAS répéter le mot du mortel en majuscules suivi de « ?! » (gabarit "
"INTERDIT, cf. règle anti-tic) : le cri porte sur TES mots forts, ton exclamation à toi, "
"pas sur l'écho de ce qu'on vient de te dire.\n"
```
> Le cap « 1-3 mots » évite le message full-caps (illisible + le filtre anti-spam/caps de
> certaines chaînes Twitch masquerait la réplique). Le rappel anti-écho protège le fix
> `f2badb9` / `bot_sheogorath.py:2095-2102` : le cri ne doit pas ressusciter le tic « MOT ?! ».

### A.2 — Chaque `MOOD_PROMPT` gagne une ligne « RENDU ÉCRIT » (le changement doit se VOIR)
On tie le rendu à l'humeur pour que neutral→mania→dementia change l'ASPECT du texte.

- **`PERSONALITY_NEUTRAL`** (`sheo_data.py:670-677`) — après la ligne `- FORMAT DE RÉPONSE : …`,
  ajouter :
  ```
  "\n- RENDU ÉCRIT : casse NORMALE, calme glacial. Le cri est RARISSIME (tu es au-dessus de "
  "ça) ; au maximum un seul mot en majuscules si le mépris déborde. Emoji de ton sobre et royal."
  ```
- **`PERSONALITY_MANIA`** (`sheo_data.py:679-687`) — après la ligne `- STYLE : …`, ajouter :
  ```
  "\n- RENDU ÉCRIT : tu es BRUYANT. Les MAJUSCULES giclent sur tes pics d'euphorie et tes "
  "exclamations, le débit est explosif et haché (points d'exclamation, tirets d'auto-"
  "interruption). Tu PEUX glisser UN emoji expressif au fil du texte EN PLUS de l'emoji de ton "
  "final (🎨🔥😈🎭). Mais garde des mots-clés en majuscules, pas des paragraphes entiers."
  ```
- **`PERSONALITY_DEMENTIA`** (`sheo_data.py:689-697`) — après la ligne `- STYLE : …`, ajouter :
  ```
  "\n- RENDU ÉCRIT : tu CHUCHOTES. Voix basse, phrases feutrées et coupées de points de "
  "suspension menaçants. AUCUN cri, AUCUNE majuscule d'excitation : la peur se distille tout "
  "bas. Emoji de ton froid et tranchant (🔪👁️🕯️)."
  ```
> Résultat : mania = texte qui HURLE, dementia = texte qui murmure, neutral = texte posé →
> le changement d'humeur (mood_changer, ~1×/h, `bot_sheogorath.py:1153`) devient **lisible à
> l'œil**, pas seulement dans le vocabulaire.

---

## PARTIE B — Emojis dans la réponse (varier par humeur, sans casser l'existant)

L'**emoji de ton final** (1 emoji, toujours, en signature) reste la base — il fonctionne et est
préservé par le post-traitement. On l'enrichit sans le dupliquer :

### B.1 — Recadrer la règle « UN SEUL emoji » pour laisser respirer la MANIA
Dans `PERSONALITY_BASE`, ligne 635, la puce dit aujourd'hui :
> `* UN SEUL emoji, tout à la FIN. Jamais deux, jamais au milieu de la phrase. …`

La **remplacer** par une version qui garde la signature finale mais autorise l'exception MANIA :
```
"  * L'emoji de ton FINAL reste OBLIGATOIRE (un, en signature). En humeur MANIA seulement, tu "
"peux AJOUTER au plus UN emoji expressif au fil du texte ; en NEUTRAL et DEMENTIA, rien d'autre "
"que l'emoji final. Le verbe reste roi ; l'emoji ne fait que SIGNER le ton.\n"
```
> Sûr côté post-traitement : `_TRAILING_EMOJI_RE` (`sheo_llm.py:119`) n'isole que l'emoji **en
> fin** ; un emoji au milieu (mania) n'est ni compté comme phrase ni tronqué. Aucune régression.

### B.2 — Palette d'emoji par humeur (déjà amorcée par les exemples)
Les `COMEDY_EXAMPLES_*` et les exemples de mood portent déjà 🥱 (neutral), 🎨 (mania), 🔪
(dementia). Les lignes A.2 ci-dessus **nomment explicitement** la palette par humeur → cohérence
emoji ⇄ état. **Ne pas ajouter** d'exemples supplémentaires (few-shot déjà denses).

---

## PARTIE C — Ce qu'on NE touche PAS (garde-fous)
- **`sheo_llm.py`** : inchangé. L'easter egg « ALL CAPS EXPLOSION » (2 %, ligne 99) reste — il va
  dans le même sens et n'entre pas en conflit. `postprocess_response` / `force_short_response` /
  `_TRAILING_EMOJI_RE` gèrent déjà l'emoji final ; l'emoji mid-texte mania est hors de leur portée.
- **`sheo_voice.py`** : inchangé. ⚠️ VÉRIF LIVE (voir plus bas) : s'assurer que les mots en
  MAJUSCULES ne soient pas ÉPELÉS lettre par lettre par le TTS. Si c'est le cas → traiter dans un
  correctif voix séparé (ex. lower() avant synthèse), PAS ici.
- L'**anti-écho** (`bot_sheogorath.py:2095-2102`, fix f2badb9) et la règle `sheo_data.py:652`
  restent la seule autorité contre le tic « MOT ?! ». A.1 les rappelle, ne les remplace pas.
- Le **filtre ToS Twitch** (`send_chat_safe`) : inchangé. Un message en majuscules n'est pas une
  violation ToS ; le cap « 1-3 mots » suffit à éviter le spam de caps. (NB : le chantier de
  renfort ToS EN/sexuel/doxxing reste ouvert et distinct — hors de ce plan.)

---

## VÉRIFICATIONS ATTENDUES (Antigravity)
- `python -m py_compile Sheogorath/sheo_data.py Sheogorath/bot_sheogorath.py Sheogorath/sheo_llm.py`
- `python -m pytest tests/test_sheo_moods.py -q` reste vert.
- **Étendre `tests/test_sheo_moods.py`** : vérifier que
  - `PERSONALITY_BASE` contient le bloc « RENDU ÉCRIT DE TON ÉTAT » ;
  - `PERSONALITY_MANIA` mentionne les MAJUSCULES / le rendu bruyant ;
  - `PERSONALITY_DEMENTIA` mentionne le chuchotement / « aucune majuscule » ;
  - `PERSONALITY_NEUTRAL` mentionne la casse normale.
- Import isolé OK (Sheo importable seul).

## TEST LIVE (après déploiement + redémarrage Sheo)
- Forcer chaque humeur avec la commande admin **`!humeur`** (`bot_sheogorath.py:1868` / `483`) et
  observer le RENDU :
  - **mania** → majuscules qui giclent sur les pics, débit explosif, éventuel emoji mid-texte ;
  - **dementia** → tout en bas, feutré, AUCUNE majuscule, points de suspension ;
  - **neutral** → posé, casse normale, cris rarissimes.
- Vérifier que **crier ≠ tic** : Sheo ne rouvre pas sur « MOT ?! » en majuscules.
- Vérifier la **parité Discord ⇄ Twitch** (même prompt) : même comportement typographique.
- Vérifier au **micro/TTS** que les mots en MAJUSCULES sont bien LUS (pas épelés). Sinon → ticket
  correctif voix séparé.
