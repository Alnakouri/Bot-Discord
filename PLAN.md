# PLAN — Images & vocaux : Sugar, Malena et M'aiq doivent réagir comme Sheo/Alfred/Johnny

Demande : **que tous les bots réagissent aux images et aux vocaux naturellement,
comme un humain** — comme le font déjà Sheo, Alfred et Johnny. Plus de
« 🎤 J'ai entendu : "..." », plus de réponses hors-sujet à une image.

---

## Ce que le test live du 2026-08-24 (20h) a montré

| Bot | Image | Vocal |
|---|---|---|
| Alfred | ✅ décrit finement, dans le personnage | ✅ répond directement |
| Johnny | ✅ décrit finement | ✅ répond directement |
| Sheo | ✅ décrit finement | ✅ répond directement |
| Sugar | — | ❌ `🎤 J'ai entendu : "..."` |
| Malena | — | ❌ `🎤 J'ai entendu : "..."` |
| M'aiq | ❌ « La boîte magique est ouverte. M'aiq cherche des pinces ici. » | ❌ (même bloc) |

## Cause unique : un bloc multimodal dédié chez 3 bots seulement

Sugar, Malena et M'aiq court-circuitent leur cascade normale par un bloc placé
**tout en haut** de `on_message`, qui appelle directement
`shared/media_handler.py` puis fait `return` :

- `MaiqBot/bot_maiq.py:1054-1096` → `process_image()` / `process_voice_message()`
- `SugarBot/bot_sugar.py:811-870` → idem
- `MalenaBot/bot_malena.py:486-548` → idem

Ces deux fonctions n'envoient à Gemini **que le prompt de personnalité brut** :
- `process_image` (`media_handler.py:66`) : ni transcript du salon, ni mémoire, ni
  consigne « décris ce que tu vois » — juste `« Analyse cette image et commente-la. »`.
  Avec la persona de M'aiq (évasif, laconique, « commence par un objet »), ça donne
  mécaniquement « La boîte magique est ouverte » au lieu d'une description.
  **M'aiq n'est pas aveugle : il voit, mais il répond sans contexte ni consigne.**
- `process_voice_message` (`media_handler.py:221`) : impose littéralement le format
  `'🎤 *J'ai entendu : "[transcription]"*\n\n[ta réponse]'` → d'où le préfixe robotique.

Sheo, Alfred et Johnny n'ont **pas** ce bloc : leur image/vocal descend dans la
cascade normale avec le transcript, la mémoire et une vraie consigne
(`bot_johnny.py:966-974`), d'où des réactions naturelles.

**Bonne nouvelle** : les 3 bots concernés ont **déjà** ce chemin générique, juste
en dessous — `bot_sugar.py:955-981`, `bot_malena.py:544-563`, `bot_maiq.py:1344-1363`.
Il est complet (image ET audio, `download_media` → `media_data` → consigne
`[VISION]` / `[🎤 VOCAL]`). Il suffit de **supprimer le court-circuit**.

---

## À faire

### 1. Supprimer les 3 blocs multimodaux dédiés
- `MaiqBot/bot_maiq.py` : supprimer le bloc `1054-1096` (de
  `if atts and not message.author.bot and _addressed_early:` jusqu'au `return` de la
  branche vocale incluse). **Garder** le calcul de `_addressed_early` et la ligne
  `atts = (await resolve_media_attachments(message) if _addressed_early else message.attachments)` :
  `atts` est réutilisé par le `classify_request` de `:1344`.
- `SugarBot/bot_sugar.py` : supprimer le bloc `811-870`.
- `MalenaBot/bot_malena.py` : supprimer le bloc `486-548`.

Après suppression, vérifier dans chaque fichier que la variable `atts` (ou
`routing`) utilisée plus bas est toujours définie sur **tous** les chemins.

### 2. Nettoyer `shared/media_handler.py`
`process_image` et `process_voice_message` n'auront plus aucun appelant
(`process_image_ollama`, lui, reste utilisé par `llm_cascade.py:82`). Les supprimer,
ainsi que les imports devenus morts dans les 3 bots. Retirer aussi `import io`
(ligne 6), mort depuis la suppression de `_convert_ogg_to_wav`.

### 3. Renforcer la consigne VISION des 3 bots
Aligner sur Johnny (`bot_johnny.py:972`) : la consigne doit demander de **décrire
ce qu'on voit** avant de réagir, sinon les personas très typées (M'aiq surtout)
esquivent. M'aiq a déjà la bonne (`bot_maiq.py:1361`) ; vérifier Sugar et Malena.

### 4. 🔧 Rendre les logs de `shared/` visibles — sans ça on diagnostique à l'aveugle
`shared/bot_logger.py:setup_logger` ne configure **que** le logger du bot.
Les loggers `smart_router`, `llm_cascade` et `media_handler` n'ont aucun handler :
ils retombent sur le « last resort » de Python, qui n'affiche que WARNING et au-dessus.
Conséquence : `[ROUTER] 🖼️ Image → Gemini Vision`, `✅ [ROUTER] Média téléchargé`,
`✅ [VISION] Image analysée` et `✅ [GEMINI ...]` sont **invisibles dans les 6 bots** —
c'est ce qui a rendu ce diagnostic long et incertain.

Dans `setup_logger`, après avoir monté les handlers, les rattacher aussi aux loggers
partagés :
```python
for shared_name in ("smart_router", "llm_cascade", "media_handler",
                    "safe_client", "discord_status", "discord_profile"):
    shared_logger = logging.getLogger(shared_name)
    shared_logger.setLevel(logging.INFO)
    if not shared_logger.handlers:
        for h in logger.handlers:
            shared_logger.addHandler(h)
```

---

## Vérification attendue

1. `.venv/Scripts/python.exe -m pytest` → **249 minimum**, 0 régression.
2. `docker compose up -d --force-recreate sheogorath maiq alfred johnny sugar malena`
3. Logs : `docker logs bot-maiq | grep ROUTER` doit **enfin** renvoyer des lignes.
4. Test live utilisateur : **la même image** envoyée aux 6 bots → 6 réactions
   naturelles qui décrivent réellement ce qu'elles voient, chacune dans son ton.
   Puis **un vocal** aux 6 → 6 réponses directes, **aucun « 🎤 J'ai entendu »**.

## Reste
- `git commit` + `git push` : la branche a **1 commit local non poussé** (`3b42e88`)
  plus les correctifs D1/D2/D3 encore non commités.
- `pydub` traîne encore dans `Alfred/requirements.txt:10` et `Sheogorath/requirements.txt:9`
  alors que plus aucun code ne l'importe.
- Tokens Twitch **401** (johnny, sugar, sheogorath) → ré-autorisation OAuth manuelle
  (`twitch_authorize.py`, gotcha : `--auth --bot <bot>` avant **chaque** bot).
