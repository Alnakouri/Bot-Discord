# PLAN — SUITE 14 : Sugar ne réécrit plus mot pour mot une phrase qu'elle a déjà envoyée

Rédaction : Claude, le **2026-09-28**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]** ou **[Claude]**. Plan précédent (SUITE 13, livré `5d6c0a2`) lisible dans git
(`98332cc:PLAN.md`).

Périmètre : **un seul fichier de code**, `shared/twitch/dispatch.py`, et deux fichiers de
tests. **Aucun appel API, aucune modification de prompt ni d'instruction, aucun `.env`.**
Un seul redémarrage, `bot-sugar`, au LOT 4, **après accord d'Ahmed**.

---

## LE CONSTAT (vérifié par Claude le 28/09 dans `docker logs bot-sugar`)

Sur les **27 phrases de lien générées** depuis le 20/09 (lignes `✨ Phrase de lien
!discord … écrite par le bot`), **26 sont distinctes**. La 27e est la copie exacte d'une
phrase écrite 2 h 47 plus tôt, par une **nouvelle génération** (ligne `✨` à chaque fois,
donc pas le cache) :

> « Entre Henri, les lames et la boue de Bohême, quel est votre favori absolu dans ce
> monde ouvert ? Venez nous en dire plus sur Discord ! 🗡️ »
> 27/09 20:09:45 (type `designer`) puis 22:56:07 (type `designer`)

Même jeu, même type de question, même instruction : flash-lite retombe sur la même
sortie. La SUITE 13 ne l'empêche pas (elle ne concerne que le cache). **Une consigne ne
le corrigera pas** (cf. SUITE 8 : une consigne ne détourne pas flash-lite de ses
formules) et nommer la phrase dans le prompt en ferait un tic. Le correctif est donc
**côté code**, comme les autres filets de `_generate_link_line` : une phrase identique à
une phrase **déjà écrite** est rejetée, et la seconde chance qui existe déjà (l.1278,
« DEUX ESSAIS, ET PAS PLUS ») en tire une autre.

---

# LOT 1 — Le code (`shared/twitch/dispatch.py` seulement)

## 1.a — L'empreinte d'une phrase

Fonction de module, placée **juste après** `_nettoyer_phrase_de_lien` :

```python
def _empreinte_phrase(phrase: str) -> str:
    """Ce qui reste d'une phrase quand on ignore casse, ponctuation, emoji et espaces.

    Deux phrases de meme empreinte se lisent pareil dans le chat : « Venez ! 🗡️ » et
    « venez !! » sont la meme redite pour un viewer.
    """
    return "".join(c for c in phrase.casefold() if c.isalnum())
```

- **Ne pas** comparer « à peu près » (distance d'édition, préfixe, mots communs) : seule
  la **redite exacte** est mesurée (1/27). Les ouvertures répétées (« Combien de fois
  Henri… ») sont un autre sujet, qui passe par la mesure et pas par ce filet.

## 1.b — Le registre des phrases déjà écrites

Constante de classe du mixin, à côté des autres constantes de `_generate_link_line` :

```python
    # Combien de phrases de lien on se souvient, par commande. 20 couvre une soiree de
    # live a 15 min d'intervalle (~5 h) ; la redite mesuree etait a 10 generations d'ecart.
    MEMOIRE_PHRASES_DE_LIEN = 20
```

Dans `_generate_link_line`, le registre est un attribut créé **à la demande**, comme
`_link_lines_cache` (l.1084-1086), **par commande seulement** (pas par jeu : la même
phrase sur deux jeux reste une redite) :

```python
        deja_ecrites = getattr(self, "_phrases_de_lien_ecrites", None)
        if deja_ecrites is None:
            deja_ecrites = self._phrases_de_lien_ecrites = {}
        empreintes = deja_ecrites.setdefault(
            cmd, collections.deque(maxlen=self.MEMOIRE_PHRASES_DE_LIEN))
```

(`collections` est déjà importé, l.6.) En mémoire seulement : un
redémarrage l'efface, c'est accepté (**ne pas** l'écrire dans `data/` ni en base).

## 1.c — Le filet, dans la boucle des deux essais

Dans la boucle `for essai in (1, 2):` (l.1278), **après** le filet d'époque
(l.1283-1284) et **avant** le `if phrase: break` :

```python
            if phrase and _empreinte_phrase(phrase) in empreintes:
                self.logger.info(
                    f"🔁 [TWITCH_CHAT:{self.bot_id}] Phrase de lien !{cmd} deja ecrite, "
                    f"essai {essai}/2 : « {phrase[:90]} »"
                )
                phrase = None
```

Et **juste avant** `cache[cle_cache] = (maintenant, phrase)` (l.1294) :

```python
        empreintes.append(_empreinte_phrase(phrase))
```

- La ligne de journal **dédiée** permet de compter le filet en live, séparément des
  autres rejets. Le `🔁 … rejetee par les filets` qui suit reste inchangé.
- Si les **deux** essais sont des redites, la méthode rend `None` et le callback prend
  le gabarit fixe : **même comportement** que les autres filets. **Ne pas** ajouter de
  3e essai, **ne pas** accepter la redite au 2e essai.
- Une phrase servie **depuis le cache** n'est ni vérifiée ni ajoutée : le cache sert
  volontairement la même phrase aux viewers qui tapent `!discord` (SUITE 13, test 5).
- **Ne pas** toucher à l'instruction, aux types de question, au cache, ni à
  `_ecrire_phrase_de_lien`.

Effet de bord connu et voulu : `tools/sonde_phrase_de_lien.py` appelle le vrai
`_generate_link_line` ; ses passes verront désormais ce filet, comme la prod. Son critère
« même question » mesurera donc le bot et plus seulement le modèle.

---

# LOT 2 — Les verrous

## 2.a — `tests/test_phrase_de_lien_sans_redite.py` (nouveau)

Même outillage que `tests/test_twitch_phrase_de_lien.py` (`_BotFactice`, fixture
`_restaurer_cascade`), **recopié**, pas importé. Le faux modèle rend les textes d'une
**liste** dans l'ordre et compte ses appels. Le cache est contourné en avançant
`time.time` de 901 s entre deux générations (ou en vidant `_link_lines_cache`), **pas**
en patchant `_generate_link_line`.

1. **Le cas vécu** : textes `["Entre Henri, les lames… ? Venez sur Discord ! 🗡️",
   "Entre Henri, les lames… ? Venez sur Discord ! 🗡️", "Une autre question ?"]`.
   1re génération → la phrase A. 2e génération (cache expiré) → le 1er essai est la
   redite, rejeté ; le 2e essai rend « Une autre question ? ». 3 appels au modèle, et une
   ligne de journal contenant `deja ecrite`.
2. **Deux redites de suite → gabarit fixe** : textes `[A, A, A]` → la 2e génération rend
   `None`. 3 appels.
3. **L'empreinte ignore casse, ponctuation, emoji et espaces** :
   `_empreinte_phrase("Venez  sur Discord ! 🗡️") == _empreinte_phrase("venez sur discord !!")`,
   et deux phrases qui diffèrent d'**un mot** ont des empreintes différentes.
4. **La mémoire est bornée** : 21 phrases distinctes puis la 1re à nouveau → acceptée
   (`MEMOIRE_PHRASES_DE_LIEN = 20`). Le test lit la constante, il ne recopie pas 20.
5. **Par commande** : la même phrase pour `!discord` puis pour `!insta` → acceptée les
   deux fois.
6. **Le cache n'est pas un doublon** : deux appels à moins de 900 s → même phrase, **un**
   appel au modèle, **aucune** ligne `deja ecrite`.
7. **Verrou AST** sur `shared/twitch/dispatch.py` : dans `_generate_link_line`, un appel
   à `_empreinte_phrase` se trouve **dans** la boucle `for essai`, et un appel à
   `.append(` dont l'argument appelle `_empreinte_phrase` se trouve **hors** de la boucle.

Les tests existants restent verts **sans modification**, en particulier
`tests/test_phrase_de_lien_seconde_chance.py` et `tests/test_annonce_auto_ne_redit_pas.py`
(mais voir 2.b).

## 2.b — Réparer le test 6 de la SUITE 13 (`tests/test_annonce_auto_ne_redit_pas.py`)

Relecture de Claude : `test_6_drapeau_ne_fuit_pas` **ne peut pas échouer**. Chaque
`asyncio.run` exécute sa coroutine dans une **copie** du contexte : même sans le
`finally`, le drapeau posé pendant l'annonce ne serait jamais vu par l'appel suivant.

Correctif : les deux appels (l'annonce auto qui lève, puis le `!discord` tapé) sont
enchaînés dans **une seule** coroutine, lancée par **un seul** `asyncio.run`, et
`_ANNONCE_AUTO.get()` est lu **dans** cette coroutine entre les deux. Rien d'autre ne
change dans ce fichier.

**Preuve exigée** : retirer temporairement `_ANNONCE_AUTO.reset(jeton_auto)` du `finally`
de `_try_link_timer`, constater que le test 6 **échoue**, remettre la ligne. Idem pour le
test 1 de 2.a : retirer le filet de 1.c, constater l'échec, remettre. Donner les deux
sorties d'échec **brutes** dans le compte rendu.

---

# LOT 3 — Vérifications avant commit

```bash
.venv/Scripts/python -m pyflakes shared/twitch/dispatch.py tests/test_phrase_de_lien_sans_redite.py tests/test_annonce_auto_ne_redit_pas.py
.venv/Scripts/python -m pytest -q
```

- `pyflakes` **avant** `pytest`. Suite **entière** verte, **jamais deux pytest en
  parallèle** (port 8599).
- `git diff --stat` : exactement `shared/twitch/dispatch.py`,
  `tests/test_phrase_de_lien_sans_redite.py`, `tests/test_annonce_auto_ne_redit_pas.py`.
  Tout autre fichier = s'arrêter et le signaler.
- Commit : `fix(twitch): une phrase de lien deja ecrite est rejetee (SUITE 14)`.
- Après le push : `gh run list --limit 3` jusqu'au vert. **Rouge = on ne déploie pas.**

---

# LOT 4 — Déploiement **[Ahmed]** donne l'accord, Antigravity exécute

**Un seul conteneur** : `bot-sugar`. Johnny prendra le code à son prochain redémarrage
(filet sans effet notable pour lui : une phrase de lien toutes les ~24 h) ; **ne pas** le
redémarrer pour ça.

```bash
docker restart bot-sugar
docker inspect -f '{{.State.StartedAt}} {{.RestartCount}}' bot-sugar
docker exec bot-sugar grep -c "_empreinte_phrase" /app/shared/twitch/dispatch.py   # attendu : >= 3
docker logs --since <StartedAt> bot-sugar 2>&1 | grep -iE "error|traceback"         # attendu : rien
```

Vérifier **`State.StartedAt`**, pas `CreatedAt`. Aucun autre conteneur ne doit avoir
redémarré.

---

# LOT 5 — Mesure en live **[Claude]**, avec celle de la SUITE 13

```bash
docker logs --since <StartedAt> bot-sugar 2>&1 | grep -E "Phrase de lien|Annonce auto|Envoyé sur .*discord.gg"
```

- **0** phrase `✨` dont l'empreinte est égale à une phrase `✨` précédente depuis le
  redémarrage ;
- nombre de lignes `deja ecrite` (attendu : rare, de l'ordre de 1 sur 25) ;
- nombre d'envois du **gabarit fixe** (`discord : https://…`) : pas plus qu'avant
  (3 sur ~30 envois depuis le 20/09).

À clore avec au moins **10 phrases générées**. Le compte rendu donne les lignes brutes.
