# PLAN — Cause racine trouvée : toute pièce jointe était classée « message vocal »

## 🔴 Le vrai bug (2026-08-24, 22:54)

Sugar répond « J'entends de douces vibrations dans l'air » à une **image**. Les logs
`shared/` — enfin visibles depuis le passage précédent — donnent la réponse en clair :

```
[ROUTER] 🎤 Message vocal Discord → Gemini Audio
✅ [ROUTER] Média téléchargé: 113044 bytes (image/webp)
```

Le routeur annonce « message vocal » sur un **image/webp**.

**Cause** : `shared/smart_router.py` faisait
```python
is_voice = getattr(att, 'is_voice_message', False) or ...
```
Or dans discord.py 2.7, `Attachment.is_voice_message` est une **méthode**, pas un
attribut (vérifié dans le conteneur : `type: <class 'function'>`). Un `getattr` nu
renvoie donc la **méthode liée**, toujours vraie → **toutes** les pièces jointes,
images comprises, partaient en cascade AUDIO.

**Ça explique tout l'historique** :
- les « 🎤 J'ai entendu : "..." » sur des **images** — c'étaient des captures d'écran :
  Gemini, sommé de transcrire, lisait le texte de l'image et le rapportait comme
  entendu (d'où des « transcriptions » étrangement exactes) ;
- M'aiq et Sugar hors-sujet sur des images ;
- Sheo/Alfred/Johnny s'en sortaient par chance : leur cascade AUDIO tape le même
  Gemini, qui voyait bien une image et la décrivait malgré la consigne `[🎤 VOCAL]`.

**Pourquoi aucun test ne l'a vu** : `tests/test_smart_router.py::_FakeAttachment`
exposait `is_voice_message` comme un **attribut booléen** — le mock ne reproduisait
pas la vraie API, donc il testait un monde qui n'existe pas.

## ✅ Corrigé et déployé

- `shared/smart_router.py` : helper `_is_voice_message()` qui **appelle** la méthode
  (et tolère un booléen pour les mocks / vieilles versions).
- `tests/test_smart_router.py` : le mock expose désormais une **méthode**, plus trois
  tests anti-retour (image ≠ vocal, vrai vocal toujours détecté, les deux styles d'API).
- **252 tests passent** (249 → 252). 6 conteneurs recréés, démarrage propre.

## Reste — LE test qui compte
Envoyer **une image** aux 6 bots. Les logs doivent maintenant dire
`[ROUTER] 🖼️ Image (image/...) → Gemini Vision` et non plus « Message vocal ».

---

# PLAN — Médias unifiés sur les 6 bots : exécution vérifiée (2026-08-24)

Antigravity a exécuté le plan. **Le travail est bon, mais Sugar était cassé :
`bot_sugar.py` ne compilait plus** — corrigé pendant la vérification. Déployé.

## 🔴 Défaut bloquant corrigé — Sugar ne démarrait plus

Le bloc multimodal supprimé (`if atts and should_respond:`) était **chaîné** au
`elif` de l'intervention aléatoire juste en dessous. En retirant le `if`, le `elif`
est resté orphelin :
```
SyntaxError: invalid syntax   (SugarBot/bot_sugar.py:812, `elif not is_bot_talking ...`)
```
Sugar n'aurait même pas pu importer son module — bot mort au démarrage.

Corrigé en transformant le `elif` en `if`. **Sémantique inchangée** : la branche
supprimée exigeait `should_respond` **vrai**, le `elif` exige `should_respond`
**faux** — les deux étaient déjà mutuellement exclusifs.

Leçon : après suppression d'un bloc, `py_compile` sur **tous** les fichiers touchés.
Les tests ne l'attrapent pas (aucun n'importe `bot_sugar.py`).

## ✅ Vérifié

| Étape | État | Preuve |
|---|---|---|
| 1. Blocs multimodaux supprimés | ✅ | M'aiq (`-45 l.`), Sugar (`-86 l.`), Malena (`-54 l.`) — tous passent par la cascade générique désormais |
| 2. `media_handler` nettoyé | ✅ | `process_image` et `process_voice_message` supprimées (plus aucun appelant), `import io` mort retiré ; `process_image_ollama` conservée (utilisée par `llm_cascade.py:82`) |
| 3. Consignes VISION renforcées | ✅ | Sugar et Malena disent maintenant « Décris ce que tu vois » ; M'aiq l'avait déjà (`:1361`) |
| 4. Logs `shared/` visibles | ✅ | sondé dans `bot-johnny` : `smart_router`, `llm_cascade`, `media_handler` → **3 handlers, niveau INFO**, les lignes `[TEST]` sortent bien dans `docker logs` |
| Imports morts | ✅ | `process_image` / `process_voice_message` retirés des 5 bots qui les importaient |
| `pydub` | ✅ | retiré de `Alfred/requirements.txt` et `Sheogorath/requirements.txt` |
| Syntaxe | ✅ | `py_compile` OK sur les 7 fichiers modifiés |
| Tests | ✅ | **249 passed, 46 subtests** |
| Déploiement | ✅ | 6 conteneurs recréés, tous `STARTED` / `prêt`, 0 traceback |

## ⚠️ Détail mineur

Le câblage des loggers partagés est placé **dans** le bloc `if not console_only:`
de `setup_logger`. En mode console seule (`BOTS_LOG_CONSOLE_ONLY=1`, ou sous pytest)
les logs `shared/` redeviennent invisibles. Sans effet en Docker, mais à remonter
d'un cran si on veut l'observabilité partout.

## Reste — test live utilisateur (c'est le seul juge)
1. **La même image** envoyée aux 6 bots → 6 réactions naturelles qui décrivent
   réellement ce qu'elles voient, chacune dans son ton. M'aiq inclus.
2. Vérifier au passage que Sugar répond bien (c'est lui qui était cassé) :
   `docker logs bot-sugar | grep -E "ROUTER|GEMINI|MISTRAL"` doit enfin être bavard.

## 🅿️ Vocal : mis de côté (décision utilisateur, 2026-08-24)
On ne travaille plus le vocal et on ne le teste plus. Le code reste en place tel
quel — l'audio descend dans la cascade générique comme l'image, sans préfixe
« J'ai entendu » — mais ce n'est plus un critère de validation. Seule l'image compte.

## Reste — divers
- `git commit` + `git push` : la branche a **2 commits locaux non poussés**
  (`3b42e88`, `586bb89`) plus ces modifications.
- Tokens Twitch **401** (johnny, sugar, sheogorath) → ré-autorisation OAuth manuelle
  (`twitch_authorize.py`, gotcha : `--auth --bot <bot>` avant **chaque** bot).
