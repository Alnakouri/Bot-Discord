# PLAN — Sugar : ton adaptatif sur Twitch + sucre non-obligatoire (Discord ⇄ Twitch)

## Contexte & décisions (validées avec l'utilisateur)
Constat live (chat Twitch, 2026-07-11) : Sugar reste **taquine même quand on est amical**
(« quel est ton jeu préféré **bg** » → réponse moqueuse) et **place un petit nom sucré à
CHAQUE réplique** (4/4 : caramel, bonbon, berlingot, nougat), alors que la persona dit déjà
que le sucre doit être rare. Deux corrections demandées :

1. **Ton adaptatif sur Twitch** : porter une **consigne de ton LÉGÈRE** (amical → chaleureuse,
   hostile → griffes), en réutilisant le lexique de `SugarBot/sugar_grudge.py`. **PAS** le carnet
   persistant (pas de score/rédemption sur Twitch pour l'instant) — juste la consigne par message,
   pour une **parité de ton** avec Discord. Cause racine du log : sur Twitch, Sugar tourne sur le
   `PERSONALITY_PROMPT` brut, sans aucune modulation de ton (les consignes du carnet sont Discord-only).
2. **Vocabulaire « sucre » NON-obligatoire** (petits noms + métaphores) : seulement quand la
   répartie s'y prête. C'est un changement de **PERSONNALITÉ** → il vaut **Discord ET Twitch**.
   Les deux plateformes lisent le **même** `PERSONALITY_PROMPT` (`SugarBot/sugar_data.py`), donc
   **une seule édition** de ce prompt couvre les deux — c'est la règle « ce qui change la persona
   sur une plateforme change sur l'autre ».

Workflow : **Antigravity exécute ce plan. Claude a rédigé.**

## Rappel architecture (pour ne rien casser)
- `shared/twitch/` est **générique** (Sheo, Johnny, Sugar). ⚠️ **NE PAS** y coder de logique
  spécifique-Sugar. On ajoute un **hook générique** `tone_directive_provider` (même patron que
  `system_prompt_provider` déjà en place), que **seule Sugar câble**. Les autres bots ne le
  passent pas → `None` → comportement inchangé.
- Le point d'injection du prompt de réponse « quand nommé » est
  `shared/twitch/llm.py:_generate_response` (déjà plein de `system_prompt += …`).
- Bots indépendants : Sugar importe `sugar_grudge` avec try/except déjà en place
  (`bot_sugar.py:276-279`). Rien de nouveau côté imports.

---

## PARTIE A — Ton adaptatif sur le chat Twitch (hook léger générique)

### A.1 — `SugarBot/sugar_grudge.py` : helper de ton PUR (sans persistance)
Après le dict `_DIRECTIVE_BY_SCORE` (après la ligne 139), ajouter une fonction module-level
qui réutilise le **même** lexique (`classify_tone`) et les **mêmes** consignes que le carnet,
mais **sans** toucher au score ni au fichier :
```python
def tone_directive(text):
    """Consigne de ton PURE (sans carnet ni persistance), pour les surfaces sans
    mémoire de rancune (ex. chat Twitch). Réutilise le MÊME lexique et les MÊMES
    consignes de ton que le carnet Discord → parité de ton entre plateformes.
    - kind          → accueil chaleureux (elle ne mord pas quelqu'un d'aimable)
    - neutral       → avenante, mordant rangé
    - aggro/apology → '' : persona brute (le mordant est OK face à une hostilité)."""
    tone = classify_tone(text)
    if tone == "kind":
        return _DIRECTIVE_KIND
    if tone == "neutral":
        return _DIRECTIVE_NEUTRAL
    return ""
```
> Note : c'est exactement la branche « score 0 » de `GrudgeBook.update` (lignes 257-261),
> extraite en fonction sans état. Zéro I/O, zéro LLM → sûr dans le chemin de réponse.

### A.2 — `shared/twitch_chat.py` : nouveau hook générique `tone_directive_provider`
Trois retouches, en miroir EXACT de `system_prompt_provider` :
1. **Signature `__init__`** (près de la ligne 95, sous `system_prompt_provider = None,`) :
   ```python
           tone_directive_provider = None,
   ```
2. **Stockage** (près de la ligne 131, sous `self.system_prompt_provider = …`) :
   ```python
           # Optionnel : callable (author, message) -> str renvoyant une consigne de TON
           # à injecter par message (ex. Sugar : chaleureuse si amical, griffes si hostile).
           # Hook GÉNÉRIQUE — aucune logique spécifique-bot ici.
           self.tone_directive_provider = tone_directive_provider
   ```
3. **Factory `setup_twitch_chat`** (signature près de la ligne 274, sous `system_prompt_provider=None,`) :
   ```python
                         tone_directive_provider=None,
   ```
   **et** dans la construction `TwitchChatBot(...)` (près de la ligne 461, sous
   `system_prompt_provider=system_prompt_provider,`) :
   ```python
           tone_directive_provider=tone_directive_provider,
   ```

### A.3 — `shared/twitch/llm.py` : appliquer le hook dans `_generate_response`
Dans `_generate_response`, **après** le bloc ANTI-RÉPÉTITION (après la ligne 107) et **avant**
le `try: from shared.llm_cascade import generate_response` (ligne 109), insérer :
```python
        # CONSIGNE DE TON (générique, optionnelle) : un bot peut fournir une consigne
        # par message. Pour Sugar : chaleureuse face à un message amical, griffes face
        # à une attaque. Hook générique — aucune logique spécifique-bot ici.
        if getattr(self, "tone_directive_provider", None):
            try:
                td = self.tone_directive_provider(author, clean)
                if td:
                    system_prompt += td
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] tone_directive_provider a échoué : {e}")
```
> On passe `clean` (message déjà nettoyé de l'anti-injection), pas `message`.

### A.4 — `shared/twitch/voice.py` : parité de ton à l'oral (recommandé)
Quand Sugar est **nommée au micro**, même adaptation. Dans `_generate_voice_response`,
**après** `full_system_prompt = system_prompt + "\n\n" + ANTI_INJECTION_GUARD` (ligne 90) :
```python
        if getattr(self, "tone_directive_provider", None):
            try:
                td = self.tone_directive_provider("", text)
                if td:
                    full_system_prompt += td
            except Exception as e:
                self.logger.warning(f"⚠️ [TWITCH_CHAT:{self.bot_id}] tone_directive_provider a échoué (voix) : {e}")
```
> `author=""` : le provider de Sugar ne l'utilise pas (il ne lit que le texte). Sans effet
> pour Sheo/Johnny (ils ne passent pas le hook). Voice listen de Sugar est OFF aujourd'hui
> (`bot_sugar.py:467`) → inerte tant que non réactivé, mais prêt.

### A.5 — `SugarBot/bot_sugar.py` : câbler le provider
1. **Import** (là où `GrudgeBook, classify_tone` sont importés, lignes 276 & 279), ajouter
   `tone_directive` à **chaque** import du try/except :
   ```python
       from sugar_grudge import GrudgeBook, classify_tone, tone_directive
   ...
       from SugarBot.sugar_grudge import GrudgeBook, classify_tone, tone_directive
   ```
2. **Appel `setup_twitch_chat`** (bloc lignes 457-468) : ajouter le kwarg
   ```python
           tone_directive_provider=lambda author, message: tone_directive(message),
   ```
   (le `lambda` ignore `author` : le ton ne dépend que du message courant).

### A.6 — Ce qu'on NE touche PAS
- Le **carnet persistant** (`sugar_grudge.json`) reste **Discord-only** : pas de score ni de
  rédemption sur Twitch (décision « léger »). Évolution possible plus tard : instancier un
  `GrudgeBook("data/sugar_grudge_twitch.json")` clé = login Twitch, et brancher le provider
  dessus. **Hors périmètre ici.**
- `enable_interjections`/`enable_greetings` restent `False` (silence sauf si nommé).

---

## PARTIE B — Vocabulaire « sucre » non-obligatoire (PERSONNALITÉ, Discord + Twitch)

Fichier **unique** : `SugarBot/sugar_data.py`, `PERSONALITY_PROMPT`. Les deux plateformes le
lisent → une seule édition suffit. La persona dit déjà « rare » (lignes 41 & 57) mais le modèle
l'ignore car le bloc « LANGAGE SUCRÉ » (54-57) survend les petits noms. On **rééquilibre** :
le défaut devient ZÉRO sucre, le sucre est un assaisonnement rare et plafonné.

### B.1 — Durcir la règle prioritaire (ligne 41)
Remplacer la puce actuelle :
> `- Un petit nom sucré, c'est RARE et jamais en tête de phrase par réflexe : la PLUPART de tes répliques n'en ont aucun. S'il en faut un, glisse-le au milieu ou à la fin.`

par (plus contraignant, avec plafond chiffré) :
```
- PETIT NOM SUCRÉ = RARE ET FACULTATIF. Par DÉFAUT, tu n'en mets AUCUN. La grande majorité
  de tes répliques n'ont ni petit nom (« mon caramel », « mon berlingot »…) ni métaphore
  sucrée — et c'est très bien. Tu n'en glisses un QUE si la vanne s'y prête vraiment ; en cas
  de doute, tu n'en mets pas. PLAFOND : jamais un petit nom deux répliques de suite, et jamais
  en tête de phrase par réflexe (au milieu ou à la fin, s'il y en a un).
```

### B.2 — Recadrer le bloc « LANGAGE SUCRÉ » (lignes 54-57)
Garder la saveur mais retirer l'incitation à en mettre partout. Réécrire la puce d'intro
(ligne 54-55) pour qu'elle présente le sucre comme une **option occasionnelle**, pas une marque
à apposer à chaque fois :
```
LANGAGE SUCRÉ — une saveur OCCASIONNELLE, pas une signature à coller partout :
- Ton nom est Sugar, mais tu ne le prouves PAS en saupoudrant du sucre à chaque phrase. Le sucre
  est une touche rare : petits noms (mon sucre d'orge, ma praline, mon caramel, mon berlingot,
  mon nougat…) ET métaphores (fondant, collant comme du caramel, acidulé, glaçage, bonbon…) sont
  disponibles, mais tu ne les sors QUE quand ça coule de source. Le plus souvent : aucune touche.
```
Conserver telle quelle la puce « Même tes piques sont enrobées de sucre… » (ligne 56) et la
puce « Le sucre doit rester NATUREL… mieux vaut zéro touche que du sucre forcé » (ligne 57) —
elles vont dans le bon sens et renforcent la consigne.

### B.3 — Ancrer par l'exemple (ligne 47-52, bloc EXEMPLES DE VOIX)
Les few-shot pilotent fortement le style. Aujourd'hui 1 exemple sur 5 a un petit nom
(« mon caramel », ligne 49). C'est déjà un bon ratio — **ne pas en ajouter**. Vérifier
seulement qu'aucune retouche B.1/B.2 n'introduit de nouveau petit nom dans les exemples.

### B.4 — Ce qu'on NE touche PAS
- La réplique signature « **péteur / péteuse** » (ligne 22) : inchangée, c'est l'insulte-maison,
  pas du vocabulaire sucre.
- La touche Serpentard (59-62) : déjà cadrée « saveur de fond, PAS une obligation ».

---

## VÉRIFICATIONS ATTENDUES
- `python -m py_compile SugarBot/bot_sugar.py SugarBot/sugar_grudge.py SugarBot/sugar_data.py shared/twitch_chat.py shared/twitch/llm.py shared/twitch/voice.py`
- `python -m pytest tests/test_twitch_features.py` reste vert (le hook est optionnel → pas de régression).
- Import isolé OK : `python -c "import sys; sys.path.insert(0,'SugarBot'); import sugar_grudge; print(sugar_grudge.tone_directive('bg t es cool'))"`
  → doit renvoyer la consigne `_DIRECTIVE_KIND` (non vide) ; `tone_directive('ferme la')` → `''`.
- Chaque bot Twitch reste importable seul (Sheo/Johnny ne passent pas le hook → `None`, inchangés).

## TEST LIVE (après déploiement)
- Chat Twitch « **quel est ton jeu préféré bg** » → Sugar répond **chaleureusement**
  (accueil taquin léger), plus de moquerie sèche.
- Chat Twitch « **t'es nulle Sugar** » → Sugar sort les griffes (répartie fine, « péteur »),
  comportement inchangé.
- Sur plusieurs répliques d'affilée : **la plupart SANS petit nom sucré** ; jamais deux
  petits noms consécutifs. Idem côté **Discord** (même prompt) → vérifier la parité.
- Aucune régression Sheo/Johnny (ton et style identiques à avant).
