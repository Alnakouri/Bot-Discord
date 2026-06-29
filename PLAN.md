# PLAN — Améliorer la répartie des bots (routage vers le bon modèle + diversité)

> **Demande user (2026-06-29).** « Est-ce que la répartie des bots peut être améliorée ou on est au max ? »
> Après audit de la tuyauterie réelle, on n'est **pas au max**. Le plafond actuel n'est PAS le talent des
> personas (riches) ni la température (déjà à 1.0/0.9 sur le chemin principal) : c'est **le routage du modèle**
> et, accessoirement, **l'uniformité des exemples de comebacks**. Ce plan corrige ça, par phases priorisées.

> **Rédigé par Claude pour exécution Antigravity** (cf. workflow habituel). Respecter la règle d'or :
> **bots indépendants** (toute modif dans `shared/` doit dégrader proprement et rester rétro-compatible —
> un changement de signature DOIT avoir un défaut qui laisse les autres bots inchangés).

---

## DIAGNOSTIC (état vérifié du code, 2026-06-29)

1. **La vraie répartie n'atteint presque jamais Grok (le meilleur modèle d'humour). 🎯 PRINCIPAL.**
   - `shared/smart_router.py::classify_request()` ne route vers la cascade **REPARTEE** (Grok 4.20 en tête)
     **que si** `_needs_humor()` détecte des mots-clés explicites (`blague`, `insulte`, `idiot`, `taquine`…)
     ou **3+** `!`/`?`. (Voir `smart_router.py:127-132` et `:174-195`.)
   - Or une vanne normale adressée à un bot (« t'es lourd aujourd'hui Sheo », « lol bien tenté », « ok le clown »)
     **ne déclenche aucun de ces signaux** → elle part dans la cascade **TEXT** par défaut
     (Mistral large → Llama 70b → Gemma free → Gemini flash-lite). Grok n'est jamais essayé.
   - **Cause structurelle** : `classify_request(message_text, attachments)` ne voit QUE le texte. Il ignore que
     le bot vient d'être **mentionné / en reply / en continuité** — c'est CE contexte (présent dans le
     `on_message` de chaque bot) qui caractérise un échange de répartie, pas des mots-clés.

2. **Exemples de comebacks figés et 100 % insulte-centric. (secondaire)**
   - Les few-shot du prompt (ex. `Sheogorath/sheo_data.py:648-657`) sont statiques et tous orientés insulte →
     les répliques convergent vers le même moule. C'est exactement ce qui a engendré le tic d'écho corrigé en
     `7e8042e`. Les faire **tourner** + ajouter des exemples **non-insulte** diversifierait le rendu.

3. **« Apprentissage par défaite » : CODÉ AUTREFOIS PUIS PERDU (jamais commité). (optionnel)**
   - La note [[plan-repartie-auto-amelioration]] dit ce système « EXÉCUTÉ mais NON commité » (2026-06-10).
     **Vérifié le 2026-06-29 : `shared/repartee_lessons.py`, `detect_gimmick_lock`, `detect_defeat_signal`
     n'existent NI dans l'arbre NI dans aucun commit de l'historique (`git log -S` = 0).** → Le code a bien
     été perdu (jamais commité, écrasé depuis). **Le DESIGN, lui, survit en détail dans cette note mémoire**
     (Couche A `detect_gimmick_lock` + `[MODE JOUTE]` ; Couche B `repartee_lessons.py` carnet JSON par bot).
     → Donc rien à « réparer » : si on le veut, on **reconstruit depuis le design de la note** (pas de
     reconception). À valider avec le user AVANT de coder (Phase 3).

---

## DÉCISIONS DE CADRAGE

- **Priorité absolue = Phase 1 (routage).** C'est le plus gros gain pour le moins d'effort. Les Phases 2 et 3
  sont des bonus, à faire seulement après que la Phase 1 soit en prod et validée en live.
- **Maîtrise du coût.** Grok (via OpenRouter) est **payant**. On n'élargit donc PAS le routage à *tous* les
  messages : on route vers REPARTEE **uniquement quand le bot est réellement adressé en mode banter**
  (mention / reply / nom prononcé / continuité) **ET** que le message n'est ni du raisonnement, ni une vraie
  demande d'info/aide, ni une image/audio. Ce sont précisément les moments à forte valeur.
- **Rétro-compatibilité stricte.** Le nouveau signal passe par un **kwarg optionnel** avec défaut neutre →
  les 5 autres bots non câblés gardent EXACTEMENT le comportement actuel (cloisonnement respecté).
- **Pilote = Sheogorath** (la star de la répartie), puis rollout aux autres bots une fois validé.

---

## PHASE 1 — Router le banter adressé vers la cascade REPARTEE (Grok)  🎯 PRIORITAIRE

### 1.1 `shared/smart_router.py` — ajouter un signal de contexte

- Modifier la signature de `classify_request` **en ajoutant un kwarg optionnel à défaut neutre** :
  ```python
  def classify_request(message_text, attachments=None, *, addressed: bool = False):
  ```
  `addressed=False` par défaut → **aucun bot existant n'est impacté** tant qu'il ne passe pas le param.

- Dans le corps de `classify_request`, APRÈS les branches existantes (image/audio → ligne ~88-112,
  reasoning → ~119-125) et AVANT le `return` TEXT final, insérer une branche répartie élargie :
  ```python
  # Banter adressé : le bot est directement interpellé et ce n'est ni du raisonnement,
  # ni une demande d'info → on vise le meilleur modèle d'humour (cascade REPARTEE / Grok).
  if addressed and _is_banter(message_text):
      result["type"] = RequestType.REPARTEE
      result["reason"] = "🎭 Banter adressé → Grok (xAI)"
      return result
  ```
  Garder la branche `_needs_humor()` existante telle quelle (elle reste utile pour les non-adressés explicites).

- Ajouter un helper `_is_banter(text)` (à côté de `_needs_humor`) qui renvoie **True pour un échange de
  répartie court** et **False quand il vaut mieux du factuel/raisonnement** :
  - **False** si `_needs_reasoning(text)` est vrai (laisser REASONING gérer).
  - **False** si le message ressemble à une **vraie demande d'aide/info** : présence de marqueurs comme
    `comment`, `pourquoi`, `explique`, `c'est quoi`, `aide`, `tuto`, `donne-moi`, `liste`, un lien/URL, ou un
    message long (> ~200 caractères). (Réutiliser les patterns de raisonnement déjà présents si pertinent.)
  - **True** sinon (cas par défaut du banter court adressé). Le but : par défaut, un bot interpellé brièvement
    = répartie → Grok.
  - Garder le helper **conservateur et lisible** ; commenter le pourquoi (coût Grok).

### 1.2 `Sheogorath/bot_sheogorath.py` — câbler le signal (pilote)

- Au point d'appel `routing = classify_request(user_message, message.attachments)` (**ligne ~2135**),
  calculer le contexte d'adresse à partir des variables **déjà existantes** dans `on_message` et le passer :
  ```python
  _addressed = bool(is_mentioned or is_reply or has_name or is_continuation)
  routing = classify_request(user_message, message.attachments, addressed=_addressed)
  ```
  (`is_mentioned`, `is_reply`, `has_name`, `is_continuation` sont définis plus haut dans la fonction — vérifier
  les noms exacts au moment du câblage et réutiliser tels quels.)
- **Ne rien changer d'autre** au chemin LLM de Sheo : il construit déjà sa cascade via
  `get_model_cascade(routing["type"])` (ligne ~2165) → il prendra automatiquement la cascade REPARTEE.

### 1.3 Critères d'acceptation Phase 1

- `py_compile` OK sur `shared/smart_router.py` et `Sheogorath/bot_sheogorath.py`.
- **Rétro-compat** : un `grep` confirme que les 5 autres bots appellent toujours `classify_request` SANS
  `addressed=` → leur routage est inchangé (toujours TEXT/REPARTEE comme avant).
- **Test fonctionnel (sans live)** : appeler `classify_request("t'es lourd aujourd'hui", addressed=True)` →
  `type == RequestType.REPARTEE`. Avec `addressed=False` (ou non passé) → `RequestType.TEXT` (comportement
  d'origine). Une vraie question (`classify_request("comment tu fais ça ?", addressed=True)`) **ne doit PAS**
  basculer en REPARTEE (reste TEXT/REASONING).
- **Test live (user)** : interpeller Sheo avec une vanne simple → le log doit afficher
  `🎭 Banter adressé → Grok` puis `✅ [OPENROUTER x-ai/grok-4.20]` (ou fallback propre si pas de crédit).

---

## PHASE 2 — Diversifier les few-shot de comebacks (anti-uniformité)  · secondaire

> Pilote **Sheogorath** d'abord ; chaque persona a ses propres exemples → rollout ensuite, bot par bot.

- Dans `Sheogorath/sheo_data.py` (bloc d'exemples ~`:648-657`) : transformer la liste figée d'exemples de
  comebacks en un **pool plus large**, dont on injecte un **sous-ensemble tiré aléatoirement** à chaque
  réponse (rotation), au lieu de toujours les mêmes. Ajouter **des exemples NON-insulte** (réagir à une
  affirmation anodine, à une question absurde, à un compliment) pour casser le moule « tout est une joute ».
- Garder la cohérence avec l'anti-écho déjà en place (`7e8042e`) : les exemples ne doivent pas réintroduire le
  gabarit « [MOT] ?! … Tu as osé… ».
- **Acceptation** : `py_compile` OK ; vérifier de visu que 2 générations successives sur le même type de
  message ne servent plus exactement la même structure de comeback.

---

## PHASE 3 — (OPTIONNEL, à valider) Apprentissage par défaite léger  · à arbitrer avec le user

> **NE PAS coder sans feu vert.** La feature a été codée le 2026-06-10 puis **perdue (jamais commitée)** —
> cf. diagnostic n°3. **Le design complet survit dans [[plan-repartie-auto-amelioration]]** : on reconstruit
> à partir de LUI, sans reconcevoir. Résumé du design à revivre :
> - **Couche A** : `detect_gimmick_lock` dans `shared/response_memory.py` (mot présent dans les 3 dernières
>   réponses → directive `[⚠️ TU BOUCLES]`) + `[MODE JOUTE]` quand on clashe le bot (répondre à l'argument).
> - **Couche B** : `shared/repartee_lessons.py` = `detect_defeat_signal` (regex phrases de défaite) +
>   `ReparteeLessons` (carnet JSON par bot, cap 15, dédup) + `reflect_on_defeat` (LLM async → UNE méta-règle
>   in-perso), réinjecté via `format_for_prompt`.
> - **Garde-fous** : async only, cooldown 5 min/salon, bornes longueur, `<Bot>/repartee_lessons.json` (cloisonné).
> - **Indépendance** : imports shared en try/except + fallback no-op.
>
> Pour l'instant : **juste corriger la note mémoire** (fait) ; coder seulement sur feu vert user.

---

## ANTI-RÉGRESSION (transversal)

- Cloisonnement : aucune fuite inter-bots, aucune dépendance runtime nouvelle entre bots ([[bots-independants]]).
- Coût : la Phase 1 ne doit PAS envoyer du trafic non-adressé vers Grok (vérifier que `addressed=False` reste
  le défaut et que les déclencheurs sont bien gated sur l'adresse réelle).
- Ne pas casser le routage REASONING/IMAGE/AUDIO existant (les nouvelles branches s'insèrent APRÈS eux).

## ORDRE D'EXÉCUTION CONSEILLÉ

1. **Phase 1** (routage) → commit → **test live Sheo** → si OK, rollout `addressed=` aux 5 autres bots.
2. **Phase 2** (few-shot Sheo) → commit → observer → rollout.
3. **Phase 3** seulement si le user la valide.
