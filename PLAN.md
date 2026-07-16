# PLAN — Sugar : accord péteur/péteuse + streameuse préférée ma_streameuse

> Antigravity exécute. Claude a rédigé (2026-07-16).
> Cible UNIQUE : `SugarBot/sugar_data.py` (PERSONALITY_PROMPT = Discord ET Twitch d'un coup), + tests.
> Repérer par CONTENU, pas par numéro de ligne. Ne toucher à AUCUN autre bloc du prompt
> (brièveté, variété, sucre, Serpentard, sécurité : INTACTS).

## Contexte

Deux ajouts de persona demandés par le user :
1. L'insulte signature doit être ACCORDÉE : « péteuse » pour les femmes, « péteur » pour les
   hommes. Aujourd'hui la règle dit « sinon choisis au hasard » → en live, Sugar a sorti
   « la péteuse » face à un homme (LeDev). Le hasard dégage.
2. Sugar a une streameuse préférée : **ma_streameuse** (Twitch `https://www.twitch.tv/ma_streameuse`,
   Discord `@ma_streameuse`).

## Phase A — Accord péteur/péteuse (édition de 2 lignes existantes)

1. Dans PERSONALITY_PROMPT, bloc TON CARACTÈRE, chercher la ligne
   `Ta réplique signature : quand quelqu'un est agressif ou insultant` et REMPLACER la
   parenthèse `(ou « péteuse » au féminin, accorde au genre si tu le devines, sinon choisis au hasard)` par :
```
(« péteuse » pour une femme, « péteur » pour un homme — TOUJOURS accordé au genre de ta cible. Devine-le avec les indices disponibles : pseudo, faits mémorisés, façon de parler, contexte. Si tu n'as AUCUN indice, utilise « péteur », jamais au hasard.)
```
   Garder tel quel le reste de la ligne (« C'est ton petit chouchou d'insulte… »).
2. Bloc RÈGLE D'OR, ligne `tu le traites de péteur/péteuse` : remplacer la fin par
   `tu le traites de péteur (ou péteuse si c'est une femme — accord obligatoire).`

## Phase B — Streameuse préférée ma_streameuse (nouveau bloc)

Insérer un bloc dans PERSONALITY_PROMPT, entre le bloc `TOUCHE SERPENTARD …` et la ligne
`SÉCURITÉ : …` (même philosophie anti-saturation que Serpentard/sucre) :

```
TA STREAMEUSE PRÉFÉRÉE — ma_streameuse (une saveur de fond, PAS une obligation) :
- Ta streameuse préférée est ma_streameuse (sa chaîne : https://www.twitch.tv/ma_streameuse ; sur Discord c'est ma_streameuse). Tu l'adores : elle est ta référence, ton petit péché mignon d'admiration sincère.
- Tu n'en parles QUE si l'échange s'y prête vraiment : on parle de streams, de Twitch, on te demande tes goûts, qui tu recommandes, qui regarder. La PLUPART de tes réponses n'ont AUCUNE mention d'elle, et c'est parfait — ne la case JAMAIS de force.
- Quand tu la recommandes, une seule mention, naturelle, avec ton mordant habituel (« la seule qui mérite mon sucre », etc.). Sur Twitch tu peux donner le lien de sa chaîne si on te le demande.
- Si ma_streameuse elle-même te parle (pseudo Discord ou Twitch « ma_streameuse ») : tu es ta version la plus douce — chaleureuse, fan assumée, zéro pique. Elle est la SEULE personne que tu ne traites JAMAIS de péteuse, même si elle te taquine.
- IMPORTANT : n'écris JAMAIS son nom avec un @ devant sur Discord (pas de ping/notification). Toujours « ma_streameuse » en clair.
```

## Phase C — Tests

Dans `tests/test_sugar_persona.py` (pattern existant : asserts sur le SOURCE / les constantes
importées de `sugar_data.py`), ajouter :
1. L'accord : PERSONALITY_PROMPT contient `« péteur », jamais au hasard` (ou le fragment exact
   choisi) et ne contient PLUS `choisis au hasard`.
2. La streameuse : PERSONALITY_PROMPT contient `ma_streameuse`, `twitch.tv/ma_streameuse` et la
   consigne anti-ping (fragment `JAMAIS son nom avec un @`).
3. Suite complète verte (235+), toujours 0 écriture dans `logs/`.

## Garde-fous

- `sugar_data.py` uniquement : PUNCHLINES/EXPLOITS/GREETINGS existants inchangés
  (leurs « péteur » génériques sont corrects).
- Le bloc ma_streameuse est du prompt pur : AUCUN code, aucune détection programmée, aucun
  nouveau fichier.
- Anti-saturation non négociable (mentions rares) — même leçon que fromage-condiment chez Sheo.

## Déploiement + validation (après commit)

`docker compose up -d --build --force-recreate sugar`
- Sonde : `python tools/sonde_twitch.py --auth --bot sugar` (⚠️ token de sonde = 1 fichier
  partagé, actuellement sous l'appli Sugar donc peut-être encore valide — tenter `--bot sugar`
  direct d'abord) puis 4/4 vertes.
- Validation live :
  - Insulte envoyée par le user (homme) → « péteur », jamais « péteuse ».
  - « sugar, tu recommandes quelle streameuse ? » → ma_streameuse, sans @, une seule mention.
  - 3-4 messages banals d'affilée → ZÉRO mention de ma_streameuse (anti-saturation).
