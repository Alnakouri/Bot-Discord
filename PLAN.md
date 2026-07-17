# PLAN — Vision Gemini fiable : image du message cité + décrets Sheo via Gemini

> Antigravity exécute. Claude a rédigé (2026-07-18).
> Repérer par CONTENU, pas par numéro de ligne.

## Contexte / décisions user (2026-07-18)

Suite au verrou « réaction aux images seulement si adressé » (bd5baf5) :
1. Quand on interpelle un bot en RÉPONDANT (reply) à un message qui contient une image
   (« @Sheo t'en penses quoi ? » sous une photo), le bot doit VOIR cette image — aujourd'hui
   il ne regarde que `message.attachments` du message courant et répond à l'aveugle.
2. Vérifier que TOUS les chemins vision passent bien par la clé Gemini du bot en premier
   (repli Moondream/Ollama ensuite) — audit, corriger seulement si un chemin ne le fait pas.
3. Décrets en image de Sheo : le TEXTE du décret doit être généré par **Gemini (clé du
   bot) en premier**, OpenRouter/Dolphin passe en secours (ordre actuel inversé).

## A — Helper partagé : image du message cité

Dans `shared/smart_router.py`, ajouter :

```python
async def resolve_media_attachments(message):
    """Renvoie les attachments à router : ceux du message courant s'il y en a,
    sinon ceux du message CITÉ (reply) — permet « @bot t'en penses quoi ? » sous une image.
    Jamais d'exception : en cas d'échec, renvoie message.attachments tel quel."""
```

Comportement :
- `message.attachments` non vide → le renvoyer tel quel (comportement actuel).
- Sinon, si `message.reference` existe : prendre `message.reference.resolved` ;
  si `None` ou non-Message (`DeletedReferencedMessage`), tenter
  `await message.channel.fetch_message(message.reference.message_id)` sous `try/except`
  (tout échec → renvoyer `message.attachments`).
- Si le message cité a des attachments → les renvoyer (y compris si son auteur est un
  bot : citer l'image d'un décret de Sheo et lui demander dessus doit marcher).
- Sinon → `message.attachments`.

Test unitaire (`tests/test_smart_router.py` ou nouveau fichier, style unittest existant,
fakes simples sans discord.py) : message avec attachments → inchangé ; message sans
attachments + ref résolue avec image → attachments de la ref ; ref à fetch (resolved
None) → fetch_message appelé ; fetch qui lève → retombe sur `[]` sans exception.

## B — Câblage dans les 6 bots

Principe : partout où le CHEMIN DE RÉPONSE construit son routage/vision à partir de
`message.attachments`, utiliser `atts = await resolve_media_attachments(message)` à la
place. NE PAS toucher aux gardes anti-spontané de bd5baf5 (`has_image_early`,
`has_attachment_image`, `has_image` de la décision) : ils portent sur le message
COURANT et c'est voulu — un reply-avec-mention est déjà `addressed`, il entre par là.

Par bot (tous importent déjà `shared.smart_router` sans fallback) :

- **SugarBot/bot_sugar.py** : bloc « TRAITEMENT MULTIMODAL » (gated `should_respond`) :
  calculer `atts` juste avant, remplacer `message.attachments` dans le `if` et dans
  `classify_request(...)`. Idem au second appel `classify_request(user_message, message.attachments, addressed=_addressed)` plus bas.
- **MaiqBot/bot_maiq.py** : bloc « TRAITEMENT MULTIMODAL » (gated `_addressed_early`) :
  idem (le `if message.attachments and not message.author.bot and _addressed_early:`
  devient `if atts and ...`). Idem à l'appel `classify_request(..., addressed=_addressed)`
  du chemin principal.
- **MalenaBot/bot_malena.py** : dans le bloc `if should_respond:` : le
  `if message.attachments:` du traitement multimodal et les deux `classify_request(...)`
  passent sur `atts`.
- **JohnnyBot/bot_johnny.py** : l'appel `classify_request(user_message, message.attachments, addressed=_addressed)` passe sur `atts`.
- **Sheogorath/bot_sheogorath.py** : l'appel `classify_request(user_message, message.attachments, addressed=_addressed)` passe sur `atts` (le download `download_media(routing[...])` suit tout seul).
- **Alfred/bot_alfred.py** : bloc « F. VISION » (gated `should_respond`) : itérer sur
  `atts` au lieu de `message.attachments` (garder la limite 10 MB et le double-check
  content-length tels quels).

## C — Audit vision = clé Gemini d'abord (vérif, ne corriger que si faux)

Confirmer que chaque chemin vision essaie `key_manager.get_key("gemini")` AVANT tout
repli Moondream/`process_image_ollama` :
- cascade partagée `shared/llm_cascade.py` (IMAGE → gemini-2.5-flash → flash-lite → ollama) ;
- cascade inline de Sheo (même ordre) ;
- blocs précoces Sugar/M'aiq/Malena (`process_image(..., api_key=get_key("gemini"))`) ;
- chemin vision d'Alfred (Gemini d'abord, `process_image_ollama` en secours).
Attendu : déjà conforme partout → aucun changement. Si un chemin ne tente pas Gemini
d'abord, l'aligner sur l'ordre de `get_model_cascade(IMAGE)`.

## D — Décrets Sheo : Gemini en premier

Dans `Sheogorath/bot_sheogorath.py`, fonction `publish_daily_rumor_sheo` :
inverser l'ordre des deux tentatives de génération du texte du décret :
1. **Gemini d'abord** : bloc actuel « Fallback Gemini » (`key_manager.get_key("gemini")`
   → `gemini-2.5-flash`) devient la première tentative. ⚠️ L'appel est un SDK sync dans
   un contexte async : l'envelopper `await asyncio.to_thread(...)` (gotcha connu : les
   appels sync non-threadés bloquent la boucle et tuent le WS EventSub).
2. **OpenRouter/Dolphin en secours** : le bloc actuel « Try Grok (via OpenRouter) first »
   passe derrière (`if not full_response:`). Même remarque `asyncio.to_thread` pour
   `openrouter_client.chat.completions.create` s'il ne l'est pas déjà.
3. Le repli statique `_fallback_decrees` reste en dernier, inchangé.
Adapter les logs (`[RUMEUR SHEO] Gemini failed` / `OpenRouter failed`) à ce nouvel ordre.
NE PAS toucher à `cmd_decret` (commande Twitch, cascade TEXT déjà partagée).

## Garde-fous

- Zéro changement de comportement pour un message avec ses propres attachments.
- Les gardes anti-réaction-spontanée de bd5baf5 restent intacts.
- `shared/smart_router.py` reste importable sans discord.py (le helper ne touche que
  des attributs duck-typés du message — pas d'import discord).

## Vérification

1. `python -m pytest` → tout vert (242 + les nouveaux tests du helper).
2. Déploiement : `docker compose up -d --build --force-recreate`.
3. Live :
   - poster une photo, puis RÉPONDRE dessus avec « @Sheo t'en penses quoi ? » → il décrit
     réellement l'image (log `[ROUTER] 🖼️ Image → Gemini Vision` + `✅ [GEMINI ...]`) ;
   - pareil avec Sugar par nom (« sugar regarde ça » en reply d'une image) ;
   - `!decret @user` (admin) → log Gemini en premier pour le texte du décret ;
   - poster une image sans rien → toujours aucun bot (non-régression bd5baf5).

## Complément (vérif Claude 2026-07-18, appliqué par Claude)

- **Sugar (bug critique)** : le `else: atts = []` inséré au milieu de la branche
  « A. Message direct » avait orphané le log [NOM ALTERNATIF] et l'écriture DB (exécutés
  dans le mauvais cas). Corps de branche restauré, `atts` calculé après la branche.
- **Johnny/Sheo/Alfred** : `resolve_media_attachments` n'est appelé que si le bot est
  réellement interpellé (mention/reply/nom/DM) — pas via intervention aléatoire, chaos
  ou proactivité, sinon un reply-à-une-image pouvait être analysé spontanément par la
  bande ; chemins non-adressés → `message.attachments` (comportement d'origine).
- **Helper** : pas de `fetch_message` HTTP quand la ref est déjà résolue sans pièce
  jointe (cas courant : reply au bot) — les attachments du cache font foi. Test ajouté.
