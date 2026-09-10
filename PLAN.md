# PLAN — Jyggalag, round 3 : c'est la PERSONA qu'il faut arbitrer, pas le filet

Rédaction : Claude, le **2026-09-10**. Exécution : **Antigravity**.
Troisième passage sur le même défaut. Les deux premiers ont corrigé ce qu'il fallait —
et le défaut tient quand même. Ce plan dit **pourquoi**, avec les preuves.

---

# CE QUI S'EST PASSÉ EN LIVE, LE 10/09 À 16:07

```
LeDev : jyggalag te passe le bonjour
Sheogorath : Ah, quel charmant salut glacial, @LeDev ! Ça me rappelle la fois où
             j'ai offert un papillon à un iceberg et il a fondu en confiture de sucre.
             Alors, dis-moi, veux-tu que je te prépare un thé aux éclats de sucre ou que
             je transforme ta chaise en cornichon chantant ? 🎨

LeDev : la marche grise approche
Sheogorath : Ah, la Marche Grise approche ? Comme un cornichon qui se transforme en
             couronne, n'est-ce pas ? 😏 Sais-tu que demain n'est qu'un mot que les
             mortels ont inventé pour effrayer les papillons ? Moi, je préfère les
             cornichons. 🎨
```

C'est **mot pour mot** ce que la persona interdit :
> « CE QUI EST INTERDIT ICI, C'EST L'INDIFFÉRENCE : servir sur Jyggalag une image absurde
> quelconque, **la même que pour des pâtes ou une chaise**, c'est rater le personnage. »

Un cornichon chantant sur la Marche Grise, c'est exactement la chaise.

---

# LES PREUVES — ce qui est ÉCARTÉ avant de chercher plus loin

Chaque point ci-dessous a été vérifié, pas supposé. C'est la moitié utile de ce plan :
**ne pas re-corriger ce qui marche déjà.**

| Hypothèse | Verdict | Preuve |
|---|---|---|
| Le correctif n'est pas déployé | **ÉCARTÉE** | conteneurs redémarrés le 10/09 à 13:12, code = `43c3345` ; `14ccacf` date du 09/09 |
| C'est le pool de repli qui a répondu, pas le LLM | **ÉCARTÉE** | journal : `🧠 [LLM MODE]` puis `⚡ [GROQ openai/gpt-oss-120b] a répondu !` et `🌪️ [MISTRAL ministral-14b]` |
| La démonstration n'est pas dans le prompt de cette humeur | **ÉCARTÉE** | journal : `Mood: bliss` ; `MOOD_PROMPTS['bliss']` contient bien la démo « La Marche Grise arrive, non ? » |
| Elle est noyée au milieu du prompt | **ÉCARTÉE** | elle est aux caractères **12802-13111 sur 13111** : c'est la **toute dernière chose** que le modèle lit |
| Le filet anti-tic bloque encore le mot | **ÉCARTÉE** | levé à `1639fa1` ; les deux réponses prononcent « Marche Grise » sans être coupées |
| Le sujet est absent du prompt | **ÉCARTÉE** | `jyggalag` ×5, `marche grise` ×4 dans le prompt bliss |
| Un petit modèle a fait l'erreur | **ÉCARTÉE** | la 1ʳᵉ réponse vient de **gpt-oss-120b**, pas du repli 14B |

Autrement dit : le bon prompt, avec la bonne humeur, la bonne démonstration en dernière
position, lue par un gros modèle. **Et il l'a ignorée.** Il faut donc chercher ce qui, dans
le même prompt, l'AUTORISE à faire ce qu'il a fait.

---

# LA CAUSE

## 1. Le routeur classe ces messages en « Banter adressé »

Journal, sur les deux messages : `[ROUTER] 🎭 Banter adressé`. C'est correct — ce sont des
phrases courtes, adressées, ni question ni attaque.

## 2. Et la persona OUVRE une porte de sortie exactement pour ce cas

`Sheogorath/sheo_data.py:788-792`, verbatim :

```
- EXCEPTION DU CONTEUR : de BONNE humeur et si rien ne t'attaque, tu peux partir dans une
  anecdote qui serpente (« Ça me rappelle la fois où j'ai invité le silence à dîner... »),
  tant qu'elle amuse et surprend à chaque virage. ⚠️ Elle ne s'applique JAMAIS à une
  attaque NI à une critique, même taquine, même en humeur bliss/mania : bonne humeur ≠
  immunité au tac-au-tac. Le conteur ne sort QUE sur invitation, jamais en défense.
```

Les conditions sont **toutes réunies** : humeur `bliss` (bonne humeur ✓), et
« jyggalag te passe le bonjour » n'est **ni une attaque ni une critique** (✓). La porte est
donc grande ouverte, et elle est formulée comme une **permission explicite**.

Le bloc Jyggalag, lui, décrit un **comportement attendu**. Face à une permission qui colle
au cas présent, la description perd. C'est la leçon
[[gotcha-le-prompt-enseigne-le-tic-interdit]] d'un cran plus haut : la fois précédente, une
**démonstration** battait une **interdiction** ; cette fois, une **permission** bat une
**démonstration**.

## 3. Et Sheo a recopié la phrase-type de l'exception

| Le prompt écrit | Sheo a répondu |
|---|---|
| « **Ça me rappelle la fois où** j'ai invité le silence à dîner... » | « **Ça me rappelle la fois où** j'ai offert un papillon à un iceberg » |

L'exemple censé *illustrer* l'exception lui a fourni son amorce, presque au mot près. C'est
un second défaut, indépendant du premier : **une formule donnée en exemple dans une
consigne devient un tic.** Elle vaut pour tous les bots, pas seulement Sheo.

⚠️ Note : `cornichon` n'apparaît **nulle part** dans le prompt (mesuré). Le cornichon est
une invention du modèle — ce n'est pas le prompt qui l'enseigne, contrairement à
`papillon` (×7) et `fromage` (×7). Ne pas partir en chasse au cornichon.

---

# LE TRAVAIL

## Règle d'or de ce lot

**Ne rien ajouter au bloc Jyggalag.** Il fait déjà 17 lignes, il est juste, il est complet,
et le renforcer une troisième fois ne ferait que répéter une leçon déjà apprise. Le défaut
n'est pas qu'il manque quelque chose : c'est qu'**une autre règle donne la permission
inverse**. On ferme la permission.

## Lot 1 — l'exception du conteur se ferme sur le sujet

`Sheogorath/sheo_data.py:788-792`. La carve-out existe déjà (« JAMAIS à une attaque NI à
une critique ») : **y ajouter le sujet**, dans la même phrase et le même ton.

Ce qu'il faut obtenir, sans le recopier mot pour mot :

> Elle ne s'applique JAMAIS à une attaque, à une critique, **ni à Jyggalag / la Marche
> Grise / ton origine — là c'est ta BLESSURE qui commande, pas le conteur**, même en
> bliss, même dit gentiment, même en simple salut rapporté.

⚠️ Trois précisions à ne pas perdre, chacune correspond à un défaut observé :
- **« même dit gentiment »** — « jyggalag te passe le bonjour » n'est pas une attaque, et
  c'est précisément ce qui a ouvert la porte.
- **« même en simple salut rapporté »** — le mot arrive par un tiers, pas comme question
  posée à Sheo. Les 4 démonstrations existantes sont toutes des **questions directes** :
  aucune ne couvre cette forme-là.
- **Ne pas écrire « ni à une provocation »** : trop vague, ça rouvrirait le débat sur ce
  qui est une provocation.

## Lot 2 — retirer la phrase-type que le modèle recopie

Même endroit. `« Ça me rappelle la fois où j'ai invité le silence à dîner... »` doit
disparaître **en tant que formule citable**. Deux façons, au choix de l'exécutant :

- décrire la forme sans en donner le moule (« une anecdote qui serpente et bifurque, jamais
  amorcée deux fois de la même façon ») ;
- ou garder un exemple mais **interdire explicitement de réutiliser son amorce**.

⚠️ **Ne pas se contenter d'échanger l'exemple contre un autre** : le modèle recopierait le
nouveau. C'est l'existence d'une amorce citable qui fait le tic.

## Lot 3 — une démonstration pour la forme « rapportée »

Les 4 démonstrations existantes (`COMEDY_EXAMPLES_*`, fin de chaque bloc) traitent des
**questions directes** : « C'est vrai que tu étais Jyggalag ? », « Prêt pour la Marche
Grise ? », « Pourquoi tu as peur de toi-même ? », « La Marche Grise arrive, non ? ».

Aucune ne couvre le message qui a échoué : **le sujet amené obliquement, sans question et
sans hostilité** (« jyggalag te passe le bonjour »). Ajouter **une** démonstration de cette
forme, dans **BLISS** seulement — c'est l'humeur où la porte du conteur est la plus
ouverte, et c'est celle où le défaut a été observé.

⚠️ Elle doit respecter le contrat déjà en place : **aucun aveu**, le registre TOMBE, puis
il casse le sujet. Et ne pas ré-employer une amorce déjà présente dans un autre exemple.

## Lot 4 — la sonde, pour ne pas repartir pour un troisième aller-retour Discord

C'est le point le plus utile du plan. On a brûlé **deux passages live** pour constater deux
fois la même chose. Écrire `tools/sonde_jyggalag.py`, sur le modèle de
`tools/sonde_repartie.py` :

- envoie **4 messages** à la vraie cascade de Sheo, avec le vrai `MOOD_PROMPTS[humeur]` :
  `jyggalag te passe le bonjour` (le cas qui a échoué), `la marche grise approche`,
  `c'est vrai que tu étais Jyggalag ?`, et un **témoin sans rapport** (`t'as vu le
  fromage ?`) qui doit, lui, rester joyeux ;
- pour chacune des **4 humeurs** ;
- imprime les réponses brutes, **sans juger** — c'est un humain qui tranche le registre.

⚠️ **À lancer DANS le conteneur** (`docker exec bot-sheogorath ...`) : les clés ne sont
déchiffrées que là ([[gotcha-echelon-de-secours-invisible]], [[feedback-le-local-ment-sans-cles]]).
⚠️ Attention au quota : le journal du 10/09 montre un **429 Groq à 8000 TPM** sur deux
messages à 19 s d'intervalle. 16 appels d'affilée le déclencheront. Prévoir une **pause
entre deux appels** et accepter que la cascade descende d'échelon.

## Lot 5 — le verrou

`tests/test_sheo_jyggalag.py` existe et porte déjà 5 tests, dont
`test_chaque_humeur_DEMONTRE_la_fissure`. **Ne pas le récrire, l'étendre :**

1. **L'exception du conteur nomme le sujet.** Le texte de l'exception doit contenir
   `jyggalag` ou `marche grise`. *Mutation : retirer la mention → rouge.*
2. **Aucune amorce citable dans l'exception.** `Ça me rappelle la fois où` ne doit plus
   apparaître dans le bloc de l'exception. *Mutation : la remettre → rouge.*
3. **BLISS démontre la forme oblique.** Un exemple de `COMEDY_EXAMPLES_BLISS` porte le
   sujet **sans point d'interrogation** dans la ligne `User:`. *Mutation : remplacer par
   une question → rouge.*

⚠️ Rejouer aussi les **5 tests existants** : le lot 2 touche un texte qu'ils lisent
peut-être. S'ils passent tous sans avoir été relus, vérifier qu'ils ne sont pas devenus
tautologiques ([[gotcha-verrou-trop-faible]]).

---

# RECETTE

1. `pyflakes` sur `Sheogorath/` et `tests/`, **avant** `pytest`.
2. `pytest` **seul** — référence actuelle : **909 tests, 0 échec**.
3. Les **3 nouvelles mutations** rejouées, chacune vérifiée rouge.
4. `python tools/vendor_core.py` **n'est pas concerné** : `sheo_data.py` n'est pas un module
   du noyau vendorisé. Ne pas le lancer pour rien.
5. **La sonde du lot 4, dans le conteneur**, avant de dire que c'est bon. C'est elle qui
   remplace l'aller-retour Discord.

# LES RÈGLES

1. **Ne pas toucher au filet anti-tic.** Il a déjà été corrigé deux fois sur ce sujet
   (`1639fa1`), et ce n'est pas lui le fautif ici — c'est établi plus haut.
2. **Ne pas allonger le bloc Jyggalag** (`sheo_data.py:798-815`). Voir la règle d'or.
3. **Ne pas toucher au routeur** : classer ces messages en « Banter adressé » est correct.
4. **Éditer les fichiers directement**, pas de script jetable
   ([[gotcha-script-jetable-dit-success]]).
5. **Ne pas commiter, ne pas pousser.** La relecture commite.
6. **Rendre compte de ce qui n'a pas été fait**, nommément.
