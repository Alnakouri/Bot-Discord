# PLAN — Sheo et M'aiq sont aveugles pour de mauvaises raisons

Suite du test live du **2026-09-03** (09:43-09:45), qui **valide** le correctif
`534d54f`+`fa38515` : **aucun bot n'a decrit une image absente.** Malena, Sugar, Johnny et
Alfred ont decrit la vraie image (« chevalier en armure noire »). Sheo et M'aiq ont sorti
leur repli honnete (« J'arrive pas a voir », « les lunes sont mal alignees »).

**Le bluff est mort. Ce plan traite ce que le test live a mis a nu ENSUITE** : les deux
bots qui ont echoue n'ont pas echoue pour la meme raison, et aucune des deux n'est une
fatalite.

Redaction : Claude. Execution : Antigravity.

---

## Defaut 1 — un 503 du MODELE met la CLE en quarantaine 120s  🔴

Logs Sheo, horodatage conteneur (2h de moins que l'horloge locale) :

```
07:43:54 | ✅ [ROUTER] Média téléchargé: 142009 bytes (image/webp)
07:43:55 | ⚠️ [GEMINI FAIL] 503 UNAVAILABLE. {'message': 'This model is currently
                                              experiencing high demand...'}
          ⚠️ [KEY MANAGER] GEMINI : Clé mise en QUARANTAINE pour 120s (Erreur 503).
          🚨 [KEY MANAGER] ZÉRO clé saine restante pour GEMINI !!
          🚨 [CRITIQUE] GEMINI : TOUTES LES CLÉS SONT ÉPUISÉES OU EN COOLDOWN !
```

`shared/api_manager.py:15` — `cooldown_times = {429: 3600, 503: 120, 500: 30, 408: 15,
529: 300, 400: 5}` — et `report_error` (`:80`) met la **cle** en cooldown pour **tous**
ces codes.

Or un **503 « high demand » parle du MODELE, pas de la cle**. Un **500** non plus. Un
**400** est une erreur de **requete** (payload malforme) : la cle n'y est pour rien.

### La consequence exacte, mesuree en live
La cascade IMAGE est `[(gemini, FLASH), (gemini, FLASH_LITE)]`
(`smart_router.py:226`). Le 503 tombe sur FLASH ; la cle part en quarantaine ; le
**second echelon utilise la MEME cle** et ne peut plus demarrer. Un incident transitoire
cote Google devient **2 minutes d'aveuglement total** — et, par la regle
[[regle-une-cle-api-par-bot]], chaque bot n'a **qu'une** cle : il n'y a personne pour
prendre le relais.

⚠️ **Punir la cle pour la charge du modele, c'est transformer une panne d'une seconde en
panne de deux minutes.**

### Correction demandee
Dans `report_error`, separer **erreurs de CLE** et **erreurs de MODELE/REQUETE** :

- **cle** : `401`/`403` (desactivation definitive, inchange) et `429` (quota → cooldown,
  inchange) ;
- **modele / requete** : `503`, `500`, `408`, `529`, `400` ne doivent **plus toucher a la
  sante de la cle**. La cascade descend d'un echelon, c'est son role. Journaliser
  l'incident (le nom du modele, pas la cle) pour qu'il reste visible.

⚠️ Ne pas se contenter de raccourcir le cooldown de 120s a 5s : le probleme n'est pas la
duree, c'est qu'on accuse la mauvaise piece.

⚠️ `report_error` existe en **2 copies** (`shared/api_manager.py` et
`Sheogorath/core/api_manager.py`). Verifier s'il en existe d'autres avant de conclure, et
passer par `python tools/vendor_core.py` plutot que d'editer une copie a la main.

### Verification par mutation (obligatoire)
Test neuf, sans reseau : apres `report_error(api, key, 503)`, `is_api_available(api)` doit
rester **True** avec une seule cle enregistree ; apres `report_error(api, key, 429)` elle
doit passer **False**. Retirer le correctif → **ROUGE** sur le premier cas.

---

## Defaut 2 — 15 secondes, c'est trop court pour une image  🟠

Logs M'aiq, meme test, meme image (142 Ko webp) :

```
07:44:52 | ✅ [ROUTER] Média téléchargé: 142009 bytes (image/webp)
07:45:07 | ⚠️ [GEMINI FAIL] 
07:45:22 | ⚠️ [GEMINI FAIL] 
```

Deux echecs a **exactement 15 secondes d'intervalle** : ce sont les deux echelons Gemini
de la cascade IMAGE, tues par `timeout=15` — la meme valeur que pour un appel **texte**.

⚠️ Un appel vision transporte l'image en base64 dans la requete : il n'a aucune raison de
tenir dans le meme budget qu'un « bonjour ».

### Correction demandee
Le timeout doit dependre de ce qu'on envoie, pas etre une constante recopiee : quand
`media_data` est present, viser **45 s** (texte : on ne touche a rien, 15 s reste bon).
Les 6 bots portent leur cascade en ligne — verifier chacun, ne pas en corriger un seul.

### Verification par mutation (obligatoire)
Un test qui atteint la branche Gemini avec `media_data` et verifie le `timeout` passe a
`asyncio.wait_for`. Remettre 15 → **ROUGE**. Prouver la matiere : `assert` sur le nombre
de bots inspectes, jamais une boucle qui peut etre vide.

---

## Defaut 3 — « ⚠️ [GEMINI FAIL] » et rien d'autre  🟠

Les deux lignes ci-dessus sont **vides apres le prefixe**. C'est le gotcha connu
([[bug-cascade-reponse-vide]]) : `str(TimeoutError())` rend `""`. Le log ne dit alors ni
ce qui a echoue, ni pourquoi — il a fallu compter les 15 secondes d'ecart pour deviner.

### Correction demandee
Dans le `except` des cascades en ligne des 6 bots : si `str(e)` est vide, journaliser
`type(e).__name__` (et le modele concerne). `shared/llm_cascade.py` sait deja le faire —
s'en inspirer, ne pas reinventer.

⚠️ **Un log d'echec qui ne nomme pas l'echec ne sert a rien.**

---

## Finition — le routeur est appele DEUX fois par message  🔵

Consequence assumee du correctif precedent : la detection precoce appelle
`classify_request`, puis le routage l'appelle de nouveau. Visible en clair dans les logs
live :

```
07:43:53 | [ROUTER] 🖼️ Image (image/webp) → Gemini Vision
07:43:53 | 📸 [DEBUG] Image détectée de ledev
07:43:54 | [ROUTER] 🖼️ Image (image/webp) → Gemini Vision
```

Ce n'est **pas** un bug — les deux appels rendent forcement le meme verdict, c'etait tout
le but — mais deux lignes `[ROUTER]` identiques par message rendent les journaux
trompeurs pour la prochaine enquete.

⚠️ **Attention au piege** : le premier appel recoit `message.attachments`, le second
recoit `atts` (issu de `resolve_media_attachments`, qui **ajoute les pieces jointes du
message cite**). Les deux ne voient donc PAS toujours la meme chose : garder deux appels
est acceptable, **fusionner naivement casserait la lecture des images en reply**
([[plan-vision-reply-et-decret-gemini]]).

### Correction demandee
Le minimum : que la **detection precoce** n'emette pas la ligne `[ROUTER] ...` (niveau
`debug`, ou un appel silencieux), pour qu'une ligne `[ROUTER]` dans le journal corresponde
a **une** decision de routage. Ne pas supprimer le second appel.

---

## Ce qui est valide et ne doit pas bouger

- **Le repli honnete de Sheo** (« J'arrive pas a voir ! Des nuages de chaos... ») a sorti
  exactement quand il fallait. C'est le comportement voulu ; ne pas le maquiller.
- **La detection d'image cote routeur** : `image/webp` vu, telecharge, 142009 octets, chez
  les 6 bots. Ne pas y toucher.

## Definition of done

- [ ] Tests neufs **verifies par mutation**, message d'echec obtenu **recopie**.
- [ ] Chaque test neuf prouve qu'il a trouve sa matiere (`assert len(...) == N`).
- [ ] Les copies vendorisees regenerees par `python tools/vendor_core.py`, pas a la main.
- [ ] `python -m pytest` vert **depuis la racine** ET **depuis `tests/`**, lance **SEUL**
      (⚠️ deux pytest en parallele font echouer `tests/test_dashboard_restart.py`, port
      fixe **8599** ; ce n'est pas une regression).
- [ ] **CI verte** apres push. ⚠️ Ne jamais annoncer « c'est bon » avant de l'avoir vue verte.
- [ ] **Test live** : renvoyer la meme image aux 6 bots. Sheo et M'aiq doivent la decrire.
      Si Gemini renvoie un 503, le bot doit **descendre d'un echelon** au lieu de perdre
      sa cle.
