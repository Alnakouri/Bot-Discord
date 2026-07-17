# PLAN — Plus de réaction spontanée aux images : seulement si on s'adresse au bot

> Antigravity exécute. Claude a rédigé (2026-07-17).
> Cible : les 6 `bot_*.py`. AUCUN changement dans `shared/`. Repérer par CONTENU, pas par numéro de ligne.

## Contexte / décision user

Aujourd'hui, quand quelqu'un poste une image/photo, les bots peuvent la commenter
spontanément (branches « IMAGE PRIORITY » à 100 %, tirages aléatoires 30–60 %…).
Décision user (2026-07-17) : **un bot ne réagit à une image QUE si on s'adresse à lui**
— mention @, réponse (reply) à un de ses messages, nom cité dans le message, ou DM.
La capacité vision elle-même ne bouge pas : quand le bot est sollicité avec une image,
il l'analyse comme avant.

## Règle unique (à appliquer partout)

`addressed = is_mentioned or is_reply or is_dm or is_name_mentioned` (selon les
variables déjà présentes dans chaque bot ; pas de DM chez certains → ignorer ce terme).

1. **Supprimer** toute branche qui met `should_respond = True` (ou équivalent) à cause
   de la seule présence d'une image, sans `addressed`.
2. **Empêcher** les déclencheurs spontanés restants (intervention aléatoire, mots-clés,
   oreille qui traîne, chaos) de se déclencher sur un message qui CONTIENT une image :
   ajouter `not has_image_early` (ou la variable image locale) à leur condition.
   Motif : si la branche aléatoire se déclenche sur un message avec image, le routage
   vision analyserait l'image quand même → réaction spontanée par la bande.

## Par bot

### JohnnyBot/bot_johnny.py
- Supprimer la branche `# A.bis IMAGE PRIORITY` (`elif has_image_early and not is_bot_talking: should_respond = True` + log `[IMAGE PRIORITY]`).
- Branche `# C. Intervention aléatoire (10%)` : ajouter `not has_image_early` à la condition.

### SugarBot/bot_sugar.py
- Supprimer la branche `# A.bis IMAGE PRIORITY` (même motif que Johnny, log `[IMAGE PRIORITY] Sugar Bot`).
- Branche intervention aléatoire 10 % (`elif not is_bot_talking and not should_respond and random.random() < 0.10`) : ajouter `not has_image_early`.

### Alfred/bot_alfred.py
- Supprimer la branche `elif has_image_early and not is_bot_talking:` (context_prefix « VISION: Le Maître partage une image… », log `[IMAGE PRIORITY]`).
- Branche `# C. Si Chaos détecté` (`(has_chaos_keyword or is_shouting) and random.random() < 0.15`) : ajouter `not has_image_early`.

### MaiqBot/bot_maiq.py
- Bloc `# DECISION FINAL` : supprimer entièrement `is_image_trigger` (le cas
  `image + mention/reply/nom` est déjà couvert par `is_mentioned or is_reply or
  is_name_mentioned` dans `should_respond` ; le cas `elif random.random() < 0.30`
  est exactement ce qu'on retire). Retirer `is_image_trigger` de la ligne `should_respond = ...`.
- Branche « L'Oreille qui traîne » (`has_keyword and not is_mentioned and not is_reply`, 20 %) :
  ajouter `not has_attachment_image`.

### Sheogorath/bot_sheogorath.py
- Supprimer le bloc `nosy_chance` (assigné à 0.30 si `message.attachments`, jamais lu — code mort) et son commentaire « ou si c'est un média (nosy) ».
- DECISION MATRIX : supprimer les DEUX branches image :
  - `elif has_image and not message.author.bot and (has_name or has_priority_keyword or has_keyword):` (le cas `has_name` est déjà couvert par la branche `elif has_name:` au-dessus) ;
  - `elif has_image and ... random.random() < 0.60:` (« Random Image detected »).
- Branches mots-clés spontanées (`elif has_priority_keyword ...` ×2 et `elif has_keyword and not _other_bot_named ...`) : ajouter `not has_image` à chacune.
- Ne PAS toucher à `is_proactive` ni `is_continuation` (pas liés aux images) — sauf si
  trivial d'ajouter `not has_image` à `is_continuation` aussi : le faire (une image
  postée dans la foulée d'un échange n'est pas une invitation à la commenter).

### MalenaBot/bot_malena.py
- RIEN à faire : elle ne répond déjà que si `is_mentioned or is_reply or is_name_mentioned or has_trigger_word` (+ `SPECIAL_INTERACTIONS`). Vérifier seulement qu'aucune branche image spontanée ne m'a échappé ; sinon ne pas toucher.

## Garde-fous

- Le chemin « bot sollicité + image » (mention/reply/nom/DM) doit continuer d'analyser
  l'image exactement comme avant (routage `classify_request` → vision Gemini).
- Ne rien changer aux réactions emoji automatiques éventuelles (`add_reaction`) : le
  user parle des RÉPONSES texte spontanées. (Sheo a un bloc reactions en amont — intact.)
- Convention bots indépendants : tout reste inline dans chaque bot, pas de helper `shared/`.

## Vérification

1. `python -m pytest` → tout vert (242 actuellement, aucun test ne couvre ces branches
   mais rien ne doit casser).
2. Déploiement : `docker compose up -d --build --force-recreate`.
3. Live :
   - poster une image SANS mentionner personne → aucun bot ne répond (répéter 3-4 fois
     pour écarter les anciens tirages aléatoires) ;
   - poster une image en mentionnant un bot (`@Sheogorath t'en penses quoi ?`) → il
     analyse et commente comme avant ;
   - poster une image avec le nom d'un bot dans le texte (« sugar regarde ça ») → il répond.

## Complément (vérif Claude 2026-07-17, appliqué par Claude)

L'audit initial avait raté 4 chemins spontanés supplémentaires, corrigés à la vérif :
- **Sugar** : bloc « TRAITEMENT MULTIMODAL » précoce (avant le check `should_respond`)
  qui répondait à TOUTE image → gated sur `should_respond`.
- **M'aiq** : même bloc précoce (avant même le calcul des triggers) → gated sur
  `_addressed_early` (mention/reply/nom, calculé inline).
- **Alfred** : bloc « F. VISION » qui forçait `should_respond = True # React to images!`
  sur toute image → bloc gated sur `should_respond`, ligne forcée supprimée.
- **Sheo** : `is_proactive` (2 % aléatoire) pouvait tirer sur un message avec image →
  ajout de `not has_image`.
Sheo/Johnny n'ont pas de bloc multimodal précoce (routage vision après la décision) — RAS.
