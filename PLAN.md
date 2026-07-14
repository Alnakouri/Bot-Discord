# PLAN — Sheo : la longueur obéit au message reçu, pas à l'humeur (+ écho cité banni)

> Antigravity exécute. Claude a rédigé (2026-07-14).
> Cibles : `Sheogorath/sheo_data.py`, `Sheogorath/sheo_llm.py`, `shared/twitch/llm.py`,
> + tests. Repérer par CONTENU (phrases citées), pas par numéro de ligne.

## Contexte / retour user (test live 2026-07-14, ~23:35)

User à Sheo : « tu parle trop ». Résultat sur les DEUX canaux : tirade de 6+ phrases
(bocal, papillons, bibliothèque…) ouvrant par l'écho cité « Oh, "tu parles trop" ? ».
Décision user : **« la longueur de sa réponse doit dépendre de la pertinence : si une
réponse longue est nécessaire pour bien répondre, soit ; sinon une réponse courte est
préférable »** — toujours cohérent avec le message reçu ET avec sa personnalité.

Deux causes :
1. Le prompt dit déjà LONGUEUR = PERTINENCE, mais l'humeur (bliss/mania + exception du
   conteur) prend le dessus : le modèle traite une critique comme une invitation à briller.
   Il manque la règle d'arbitrage : **le message reçu décide de la longueur, l'humeur ne
   décide que du ton**.
2. Le garde anti-écho (`_strip_echo_opening`, Discord + Twitch) ne coupe que l'écho HURLÉ
   (MAJUSCULES). L'écho CITÉ entre guillemets (« "Tu parles trop" ? ») passe — et il est
   sorti deux fois de suite en ouverture.

## Phase A — Règle d'arbitrage longueur dans `PERSONALITY_BASE` (`sheo_data.py`)

Dans le bloc « ⚡ RÈGLE D'OR », JUSTE APRÈS la puce « LONGUEUR = PERTINENCE… » existante,
insérer :

```
- ⚖️ QUI DÉCIDE DE LA LONGUEUR : le MESSAGE REÇU, jamais ton humeur. L'humeur colore le
  TON (joyeux, glacial, jovial), pas le VOLUME. Avant de répondre, demande-toi : « que
  faut-il pour bien répondre à ÇA ? » — et n'écris QUE ça.
  * Pique courte, critique, ordre sec (« tu parles trop », « t'es nul », « tais-toi ») →
    riposte COURTE : 1-2 phrases qui mordent, et tu te tais. Répondre à « tu parles trop »
    par une tirade, c'est donner raison au mortel — humiliation suprême.
  * Question précise → réponse qui répond, pas plus.
  * Sujet riche, invitation à raconter, mortel de bonne compagnie → LÀ tu peux déployer
    (conteur, tirade qui monte), tant que chaque phrase AJOUTE.
- L'EXCEPTION DU CONTEUR ne s'applique JAMAIS à une critique ou une attaque, même en
  humeur bliss/mania : bonne humeur ≠ immunité au tac-au-tac sec.
```

Et dans le bloc « EXCEPTION DU CONTEUR » existant, remplacer la fin « Face à une attaque,
tu restes sec : le conteur ne sort QUE quand tu t'amuses. » par : « Face à une attaque OU
une critique (même taquine), tu restes sec — 1-2 phrases — quelle que soit ton humeur :
le conteur ne sort QUE sur invitation, jamais en défense. »

## Phase B — 2 few-shot « critique → sec » (ancrage)

1. `COMEDY_EXAMPLES_BLISS` : AJOUTER un exemple (c'est en bliss qu'il a dérapé) :
```
User: Tu parles trop.
Sheogorath: <thought>Critique sèche. Même en bliss : riposte courte, pas de tirade.</thought>
Et toi pas assez — c'est pour ça que je comble. Chut, écoute le maître. 😏
```
2. `COMEDY_EXAMPLES_MANIA` : AJOUTER :
```
User: Abrège.
Sheogorath: <thought>Ordre sec. Riposte courte et cinglante, pas de feu d'artifice.</thought>
Abréger le divin ? Je t'abrégerai TOI, ça ira plus vite. HAHA ! 🔪
```

## Phase C — Garde anti-écho : couper aussi l'écho CITÉ (Discord + Twitch)

Dans `Sheogorath/sheo_llm.py::_strip_echo_opening` ET son jumeau générique
`shared/twitch/llm.py::_strip_echo_opening` (même logique aux deux endroits, parité) :

À côté de `is_shouted_echo` (tokens MAJUSCULES qui échotent), ajouter la détection
`is_quoted_echo` : la tête de phrase contient, ENTRE guillemets (`"…"`, `«…»`, `“…”`,
`'…'`), un segment dont les mots significatifs (≥3 lettres, hors `_ECHO_STOPWORDS`,
normalisés via `_norm`) sont TOUS des mots du message du mortel. Alors :

```python
quoted_segments = re.findall(r"[\"«“‘'](.+?)[\"»”’']", head)
is_quoted_echo = any(
    (sig := {w for w in re.findall(r"\w+", _norm(seg)) if len(w) >= 3} - _ECHO_STOPWORDS)
    and sig <= user_words
    for seg in quoted_segments
)
```

et étendre la condition : `if not (is_interjection or is_shouted_echo or is_quoted_echo): break`.

⚠️ Conserver TOUTES les protections existantes : jamais sur un cri intégral ALL CAPS,
jamais si le reste < 15 caractères, casse re-capitalisée, max_strips inchangé. L'écho en
casse normale SANS guillemets (« Des pâtes ? ») reste PERMIS (canon) — seul l'écho
GUILLEMETÉ du message est coupé.

## Phase D — Tests

1. `tests/test_sheo_anti_tic.py` : étendre (les imports existent déjà) :
   - « "Tu parles trop" ? Mais mon cher pirate… la suite. » + msg « tu parle trop » →
     l'ouverture citée saute, la suite reste.
   - « Oh, "tu parles trop" ? Haha ! Toi qui m'invoques… » → idem (interjection + citation).
   - « Des pâtes ? Sans la moindre meule… » + msg « j'ai mangé des pâtes » → INTACT
     (écho casse normale sans guillemets = permis).
   - « "Nul" ? C'est petit. » + msg « t'es nul » → INTACT si la coupe laisse < 15 car.
2. Miroir Twitch dans `tests/test_twitch_antimould.py` (ou fichier des gardes Twitch
   existant) : mêmes cas sur `shared/twitch/llm.py::_strip_echo_opening`.
3. `tests/test_sheo_moods.py` : asserts prompt — « QUI DÉCIDE DE LA LONGUEUR » présent
   dans `PERSONALITY_BASE` ; « jamais en défense » présent (exception conteur resserrée).

## Garde-fous

- Ne PAS toucher aux plafonds (`max_tokens` 340, filet 10 phrases, Twitch 120t/480c) :
  la longueur se joue dans le PROMPT, les filets restent des filets.
- Ne PAS toucher aux 4 humeurs ni au reste du postprocess.
- Suite : `python -m pytest tests/ -q` verte (210+ avant chantier).

## Déploiement + test live (après commit)

`docker compose up -d --build --force-recreate sheogorath` (shared/ touché → --build).
Sondes : « tu parles trop » (Discord ET Twitch, en bliss si possible) → 1-2 phrases, sans
écho cité en ouverture · « raconte-moi une histoire » → le conteur peut se déployer ·
« j'ai mangé des pâtes » → la réflexion « Des pâtes ? » reste permise.
