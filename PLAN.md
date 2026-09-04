# PLAN — le transcript amputé fait mentir les bots

Redaction : Claude. Execution : Antigravity.

Trouve au **test live du 2026-09-04 (00:12-00:30)**, en regardant les 6 bots repondre.

A 00:28, l'utilisateur ecrit **seulement** `@Johnny silverhand`. Johnny repond :

> **Sheogorath qui beugue ? Encore.** Ce dieu du fromage a plus de bugs qu'un netrunner
> sous Adrenaline. 🧀🔥

Personne n'avait parle d'un bug de Sheogorath. Sheo venait au contraire de repondre
normalement deux fois (`22:26:33` et `22:27:07`, GROQ `gpt-oss-120b`, sans une erreur).

⚠️ **Ce n'est pas une hallucination gratuite : c'est la bonne conclusion tiree d'un
contexte faux.** Le correctif porte donc sur le contexte, pas sur le prompt.

---

## Le mecanisme, verifie dans le code  🔵

`JohnnyBot/bot_johnny.py:949-953` — et la **meme boucle**, au mot pres, dans 4 autres
bots :

```python
for hist_msg in reversed(messages_list):
    # Silence total entre bots : on n'inclut PAS les autres bots dans le contexte.
    if hist_msg.author.bot and hist_msg.author != bot.user:
        continue
    transcript += f"{hist_msg.author.name}: {hist_msg.content}\n"
```

Ne survivent que **l'utilisateur** et **le bot lui-meme**. Johnny n'avait pas parle depuis
plusieurs minutes : son `CONTEXTE DU SALON` se reduisait donc a

```
CONTEXTE DU SALON (Chronologique) :
ledev: sheo
ledev: chut
ledev: @M'aiq
ledev: @Johnny silverhand
```

⚠️ **Un humain qui appelle quatre noms d'affilee sans qu'aucun ne reponde, ca ressemble a
une panne.** Le modele a lu ce qu'on lui a donne et l'a rationalise de la facon la plus
evidente.

⚠️ **Masquer une information et la supprimer ne sont pas la meme chose.**
[[plan-anti-contamination-transcript]] voulait empecher un bot de **recopier le verbatim**
d'un autre ; [[plan-silence-total-bots]] les a purement **effaces**. Le premier protege,
le second **fabrique un mensonge**.

Meme famille que [[bug-sheo-bluff-images]] : le bot **affirme un fait sur un passe qui n'a
pas eu lieu**. La cause y etait un prompt monte avant verification ; ici c'est un
transcript ampute. Le symptome est le meme.

Indice plus faible, meme soiree : Sugar, appelee **une** fois (`22:25:10`,
`[NOM ALTERNATIF]`), ouvre par « **Trois fois** mon nom en un clin d'oeil ». Un decompte
invente, sur un contexte du meme genre. Ne pas en faire un critere de reussite : c'est
peut-etre sa coquetterie. Le cas Johnny suffit.

### Les 5 sites exacts

| Fichier | Ligne | Format |
|---|---|---|
| `Alfred/bot_alfred.py` | 1606-1610 | `nom (mention): contenu` |
| `MaiqBot/bot_maiq.py` | 1295-1299 | `nom (mention): contenu` |
| `Sheogorath/bot_sheogorath.py` | 2277-2281 | `nom (mention): contenu` |
| `JohnnyBot/bot_johnny.py` | 949-953 | `nom: contenu` |
| `SugarBot/bot_sugar.py` | 874-878 | `nom: contenu` |

⚠️ **Malena n'est PAS concernee.** Elle a **sa propre cascade inline** — le rappel de
[[bug-cascade-reponse-vide]] : « corriger `shared/` ne la couvre pas » — et cette cascade
ne recoit que `sys_prompt` et `prompt`. Aucun contexte de salon nulle part : le mot
`transcript` n'apparait qu'une fois dans son fichier, a `bot_malena.py:149`, et c'est
`transcript=""`. Ne pas lui en fabriquer un ici : ce serait un changement de comportement,
pas un correctif. **5 bots, pas 6.**

---

## Correction demandee  🟠

### 1. Un helper partage, parce qu'il y a 5 copies de la meme boucle

Nouveau `shared/transcript.py` :

```python
def ligne_de_contexte(hist_msg, moi, *, avec_mention=False):
    """Rend la ligne a mettre au transcript pour ce message, ou None s'il n'y a rien a dire."""
```

- message de l'utilisateur → la ligne verbatim, dans le format demande ;
- message du bot **lui-meme** (`hist_msg.author == moi`) → verbatim aussi : il doit savoir
  ce qu'il a dit ;
- message d'un **autre bot** → une **trace neutre**, sans une lettre de son contenu :
  `f"{nom} : [a repondu]"`.

C'est tout ce que la trace doit dire. Elle repond a la seule question que le modele se
posait — « est-ce que quelqu'un a repondu ? » — sans rien reveler du **quoi**, qui est
precisement ce que [[plan-anti-contamination-transcript]] protege.

⚠️ **Ne pas nommer le modele, l'humeur, ni la longueur.** Tout ce qu'on ajoute au-dela de
« quelqu'un a repondu » redevient de la contamination.

### 2. Cabler les 5 bots

Remplacer les 5 boucles par un appel au helper, en gardant chacun **son** format
(`avec_mention=True` pour Alfred, M'aiq et Sheo). Ne rien changer d'autre dans ces
boucles : la collecte de `active_mortals` reste ou elle est.

### 3. Le vendoring, qui est le vrai piege ici

⚠️ `tools/vendor_core.py` porte une liste `MODULES` **en dur** : un fichier neuf dans
`shared/` n'est **pas** copie tant qu'il n'y figure pas. Ajouter `"transcript.py"` a
`MODULES`, puis relancer `python tools/vendor_core.py`, puis verifier que les 6
`<Bot>/core/transcript.py` existent. Sans ca les bots plantent a l'import une fois
deployes, et **les tests, qui importent `shared/`, ne verront rien**.

⚠️ Import cote bot : `from core.transcript import ligne_de_contexte`, dans le meme
`try/except ImportError` que les autres modules du noyau ([[bots-independants]]).

---

## Tests demandes

1. **La trace remplace le verbatim** — un historique contenant le message d'un autre bot
   produit un transcript qui **contient** `[a repondu]` et **ne contient pas** le contenu
   de ce message. C'est la garantie anti-contamination, jamais testee jusqu'ici.
2. **Le bot se voit lui-meme** — son propre message ressort **verbatim**.
3. **Le cas Johnny, reconstitue** — l'historique exact du 04/09 (`sheo`, reponse de Sheo,
   `chut`, reponse de Sheo, `@M'aiq`, reponse de M'aiq, `@Johnny silverhand`) doit
   produire un transcript ou **les reponses des autres apparaissent**. ⚠️ Ce test ne peut
   pas verifier que Johnny cesse d'inventer — il verifie que **le contexte ne ment plus**.
   Ne pas pretendre le contraire dans son nom ni dans son message d'echec.
4. **Les 5 bots utilisent le helper** — sur le modele de
   `tests/test_api_manager.py:59` : partir de la liste des 5, compter les fichiers
   inspectes, `assert trouves == 5`. ⚠️ **Deriver le compte de la liste de depart, pas de
   la boucle.**
5. **Le module est vendorise** — les 6 `<Bot>/core/transcript.py` existent et sont
   identiques a la source (la sonde `tools/sonde_core_drift.py` couvre deja ce role :
   verifier qu'elle voit le nouveau fichier, sinon le test ci-dessus ne prouve rien).

⚠️ **Verifier chaque test par MUTATION** : remettre le `continue` dans un bot, voir le
test 4 tomber ; faire rendre le verbatim par le helper, voir le test 1 tomber. Retirer le
correctif et voir le test rougir **pour la bonne raison** est la seule preuve.

---

## Ce que ce plan ne fait PAS

- Il ne touche pas a `on_message` : **un bot continue de ne jamais repondre a un bot**
  ([[plan-silence-total-bots]]). Seul le CONTEXTE change.
- Il ne touche pas a la garde `_other_bot_in_focus` ([[plan-anti-incrustation-4bots]]),
  qui lit le salon directement et non le transcript. Elle a fonctionne toute la soiree du
  04/09 (`[ANTI-INCRUSTATION] … se tait`, Johnny 2x, Sugar 1x) : ne pas y toucher.
- Il ne donne pas de transcript a Malena.

## Regles de travail (rappel)

- **Ne jamais dire « c'est bon » avant que la CI soit verte** — le local ment sur tout ce
  qui depend de l'environnement.
- Deux `pytest` en parallele font echouer `tests/test_dashboard_restart.py` (port fixe
  8599) : relancer seul.
- Un fichier de test neuf doit etre **suivi par git**, sinon
  `tests/test_depot_complet.py` refuse la suite (c'est voulu).
- Deploiement : le source est **bind-monte**, un `docker restart` suffit.
