# PLAN — Sheo bluffe sur les images

Diagnostic du **2026-09-02** (Claude, lecture seule). Symptôme observé au test live du
01/09 : Sheo répond aux images par « une danse de pixels », « une lame qui claque ».
**Ce n'est pas un effet de prompt à retoucher : le modèle ne reçoit pas l'image, et on lui
ordonne de prouver qu'il l'a vue.** Il obéit.

Trois défauts réels, vérifiés dans le code (lignes relues le 02/09, après `4c8b83d`).
Exécution : Antigravity. Rédaction : Claude.

---

## Défaut 1 — « y a-t-il une image ? » est posée DEUX fois, avec deux règles  🔴

C'est la cause racine. Le bluff est fabriqué mécaniquement.

| Où | Règle appliquée |
|---|---|
| `Sheogorath/bot_sheogorath.py:1844` | `content_type` commence par `image/` **OU** extension dans `.png .jpg .jpeg .webp .gif` |
| `Sheogorath/core/smart_router.py:157` | `content_type` **seul**, et seulement s'il est dans `IMAGE_MIME_TYPES` |

`IMAGE_MIME_TYPES` (`smart_router.py:60`) = `jpeg, png, gif, webp, bmp`. Donc une pièce
jointe `photo.jpeg` servie **sans `content_type`**, ou en `image/heic`, `image/avif`,
`image/svg+xml` : **le bot croit qu'il y a une image, le routeur non.**

### La chaîne de conséquences, dans l'ordre du fichier

1. `:1844` → `has_image = True`.
2. `:2220` → le prompt système reçoit « **NOTE: L'utilisateur a envoyé une IMAGE.
   Commente-la…** ».
3. `:2229` → si le message est vide, le message utilisateur devient « *Regarde
   attentivement l'image… **prouve que tu as vu l'image !*** ».
4. `:2307` → **seulement maintenant** le routage tranche : `has_image = False`,
   `type = TEXT/REPARTEE`.
5. `:2312` → le téléchargement est gaté sur `routing["has_image"]` → **pas de
   `download_media`**, `media_data` reste `None`.
6. `:2321` → `has_image = routing["has_image"] and media_data is not None` : la variable
   est bien corrigée… **mais le prompt est déjà écrit, et personne ne le retire.**
7. `get_model_cascade(TEXT)` rend la cascade de persona (**Groq `gpt-oss-120b`**), pas la
   cascade IMAGE, qui est Gemini-only (`smart_router.py:226`).

⚠️ Un modèle **sans yeux** reçoit l'ordre explicite de prouver qu'il a vu une image. Le
garde-fou « vision = Gemini uniquement » est contourné par le haut.

### Correction demandée

**Une seule autorité sur la question.** Le routeur décide, le bot obéit.

1. **Aligner le routeur sur la règle la plus large**, pas l'inverse : dans
   `classify_request`, accepter aussi l'**extension** du fichier quand le `content_type`
   est absent ou inconnu. Le routeur lit **déjà** `filename` juste au-dessus
   (`smart_router.py:139`, il s'en sert pour le vocal `.ogg`) : la matière est là.
   Élargir `IMAGE_MIME_TYPES` aux formats que Gemini accepte réellement plutôt que de
   laisser tomber `heic`/`avif` en silence.
2. **Supprimer la détection locale `:1844`** et faire descendre `routing["has_image"]`.
   Deux endroits qui répondent à la même question finiront toujours par diverger — c'est
   la leçon de `bug-is-voice-message-methode`, déjà la détection de média qui mentait.
3. Si l'ordre du code rend (1)+(2) trop lourd d'un coup, le **minimum non négociable** est
   de **déplacer le montage du prompt image APRÈS `:2321`** : un prompt qui affirme un
   fait ne doit jamais être écrit avant la vérification de ce fait.

⚠️ **Ne pas se contenter de retoucher la formulation du prompt.** « Prouve que tu as vu
l'image » n'est pas le bug, c'est le révélateur : la consigne est juste quand l'image est
là. Le bug, c'est qu'elle parte quand l'image n'est pas là.

### Vérification par mutation (obligatoire)
Test neuf, sans réseau : une pièce jointe factice `photo.jpeg` avec `content_type = None`
(puis `image/heic`) doit donner `classify_request(...)["has_image"] is True`. Retirer le
correctif → **ROUGE**. Plus un test garantissant qu'avec `has_image = False`, **aucune**
des deux chaînes « a envoyé une IMAGE » / « prouve que tu as vu l'image » n'apparaît dans
le prompt monté.

---

## Défaut 2 — la branche multimodale OpenRouter est du CODE MORT  🟠

Dans la même cascade `if/elif` de `bot_sheogorath.py`, la condition
`elif client_type == "openrouter" and openrouter_client:` apparaît **deux fois** :

- `:2434` — texte seul (+ tool-calling) ;
- `:2551` — **payload base64 de l'image**.

La première capture toujours. **La seconde est inatteignable** : le seul secours visuel
non-Gemini du bot n'a jamais tourné une seule fois.

### Correction demandée
Fusionner les deux branches en une seule qui **teste la présence de `media_data`** pour
choisir le payload (multimodal si image, texte sinon). Supprimer la branche morte.

⚠️ Vérifier avant de supprimer que `:2551` n'a rien que `:2434` n'ait pas (gestion
d'erreur, en-têtes, modèle) : c'est une fusion, pas une suppression.

### Vérification par mutation (obligatoire)
Un test qui atteint la branche OpenRouter **avec** `media_data` et vérifie que le payload
contient bien l'image. Sur le code d'aujourd'hui il doit être **ROUGE** — s'il est vert
d'emblée, il ne teste pas ce qu'on croit.

---

## Défaut 3 — Groq et Mistral jettent `media_data` en silence  🟠

`:2519` (mistral) et `:2535` (groq) ne construisent **aucun** payload multimodal, et
**rien ne signale** que l'image a été perdue. Masqué aujourd'hui parce que la cascade
IMAGE est Gemini-only — mais c'est exactement le défaut 1 qui contourne ce garde-fou.

### Correction demandée
Ne pas rendre ces clients multimodaux (ils ne le sont pas). Poser un **`logger.warning`
explicite** quand un échelon reçoit un `media_data` non nul sans savoir le transporter, en
nommant le client et le modèle. Une perte silencieuse de média est ce qui a rendu ce bug
invisible pendant des mois.

---

## Ce qui, lui, marche — ne pas y toucher

Le repli `:2592` (« J'arrive pas à voir ! Des nuages de chaos… ») sort correctement quand
Gemini échoue sur une **vraie** image. Le bluff ne vient pas de là.

---

## Les 5 autres bots : vérifié, plus léger mais **pas sain**

Vérifié le 02/09 : la double règle par *extension* est **propre à Sheo**. Les 5 autres
testent `content_type.startswith('image/')` — `bot_sugar.py:759`, `bot_johnny.py:847`,
`bot_maiq.py:1199`, `bot_alfred.py:1364`. Malena n'a aucune détection locale.

⚠️ **Mais `startswith('image/')` reste plus large que `IMAGE_MIME_TYPES`** : sur un
`image/heic`, ces 4 bots portent la même asymétrie que Sheo, en moins visible. Le
correctif (1) du défaut 1, appliqué aux **7 copies** de `smart_router.py`, les couvre tous.

⚠️ Les 7 copies doivent rester **identiques** (`shared/` + 6 × `<Bot>/core/`) : c'est la
dette assumée du vendoring. Ne pas corriger `shared/` seul.

---

## Definition of done

- [ ] Les tests neufs sont **vérifiés par mutation**, et le dire explicitement (message
      d'échec obtenu recopié) — un test qui n'a jamais été rouge ne prouve rien.
- [ ] Chaque test neuf prouve qu'il a trouvé sa matière (`assert len(...) == 7` sur les
      copies du routeur, jamais une boucle qui peut être vide).
- [ ] `python -m pytest` vert **depuis la racine** ET **depuis `tests/`**, lancé **SEUL**
      (⚠️ deux pytest en parallèle font échouer `tests/test_dashboard_restart.py`, port
      fixe **8599** ; ce n'est pas une régression).
- [ ] Les 7 `smart_router.py` restent identiques sur la détection d'image.
- [ ] **CI verte** après push. ⚠️ Ne jamais annoncer « c'est bon » avant de l'avoir vue verte.
- [ ] **Test live requis** : envoyer à Sheo une vraie image, puis un message sans image.
      Aucune réponse ne doit décrire une image absente.
