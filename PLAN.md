# PLAN — Les bots écrivent leur propre mémoire sur toi, et se la resservent

Rédaction : Claude, le **2026-09-10**, après le test live de 23:37. Exécution : **Antigravity**.

Ce plan ne parle plus de Jyggalag. Le correctif Jyggalag **marche** — la preuve est plus
bas. Le test live a exhumé autre chose, plus profond, et qui touche **5 bots sur 6**.

---

# CE QUE LE TEST LIVE A MONTRÉ

```
LeDev : je t'ai vu te transformer en jiggalag
Sheogorath : une ombre glisse, murmure que même tes yeux trahissent le secret de ce
             jiggalag... tu penses me voir, mais c'est le reflet qui me regarde, pas
             l'inverse. 👁️

LeDev : apres la marche grise
Sheogorath : La Marche Grise n'est qu'un menuet que Jyggalag danse pour tromper les
             idiots... Après ? Après, il y aura des cornichons dorés à la place des
             étoiles, et tes larmes seront servies en gelée de sucre sur des toasts de
             mensonge.
```

## Le correctif Jyggalag tient — et le journal le prouve

| Message | Modèle qui a répondu | Verdict |
|---|---|---|
| 1 — « je t'ai vu te transformer en jiggalag » | **GROQ gpt-oss-120b** | registre TOMBÉ, menace, aucun aveu, **aucun sucre** ✅ |
| 2 — « apres la marche grise » | 429 → quarantaine 5 s → **MISTRAL ministral-14b** | cornichons dorés, gelée de sucre ❌ |

Le premier message est répondu par le **premier échelon**, et il fait exactement ce que
`ac6914b` demandait. Le second est répondu par le **repli 14B**, qui ne tient pas le
registre — la sonde l'avait déjà montré ce matin. **Ce n'est donc pas la persona.**

## Pourquoi le repli est atteint si souvent — c'est mesuré

Journal, 21:38:04 :
> `Rate limit ... tokens per minute (TPM): Limit 8000, Used 2514, Requested 6059`

Le prompt de persona pèse **~3300 tokens** (13 000 caractères) et Groq plafonne à **8000
tokens par minute**. Donc **à partir du 3ᵉ message dans la même minute, Sheo tombe sur le
14B**. Dans toute conversation vivante, une réponse sur deux ou trois vient du modèle
faible. Ça n'explique pas que Jyggalag, ça explique beaucoup de « Sheo était plat ce
soir-là ».

---

# LA VRAIE TROUVAILLE — une boucle fermée

## Le mécanisme, étape par étape

1. Sheo répond avec des cornichons.
2. **Dans la même réponse**, il émet lui-même une balise `<fact>…</fact>`
   (`Sheogorath/sheo_llm.py:70` — `extract_facts`).
3. Le contenu est stocké **comme un fait sur l'utilisateur**
   (`sheo_memory.py:167`, `data/sheo_facts.json`).
4. Au message suivant, ce fait est réinjecté **à la toute fin du prompt système**
   (`bot_sheogorath.py:2250-2256`), après la persona, après les démonstrations, suivi de :
   > `Utilise ces infos pour personnaliser ta réponse.`
5. Sheo ressert des cornichons. **Retour à l'étape 1.**

## Ce que ça a produit, en clair

`data/sheo_facts.json`, faits stockés sur l'utilisateur :

```
- L'utilisateur semble obsédé par les accessoires alimentaires (chapeaux de confiture, cornichons)…
- L'utilisateur semble particulièrement sensible aux insultes liées aux accessoires alimentaires (cornichons, cuillères)…
- L'utilisateur semble obsédé par les comparaisons alimentaires et les métaphores visuelles absurdes…
- L'utilisateur semble obsédé par les métaphores alimentaires violentes (cornichons, confiture)…
- L'utilisateur semble obsédé par les conséquences post-Marche Grise et les métaphores culinaires violentes (cornichons, gelée, toasts).
```

**L'utilisateur n'a jamais écrit un seul de ces mots.** C'est Sheo qui les a dits, puis
qui a conclu que son interlocuteur en était obsédé, puis qui a reçu l'ordre de s'en servir.

⚠️ Ça explique enfin le **cornichon**, qui n'apparaît **nulle part** dans
`sheo_data.py` (mesuré) et revenait pourtant à chaque échange : il ne venait pas de la
persona, il venait de `sheo_facts.json`.

⚠️ Le plafond de **10 faits par utilisateur** (`sheo_memory.py:172`) fait que ce bruit
auto-généré **chasse les vrais faits**. Ceux qui restent : « Il aime le mot *sugar* »,
« ledev veut que Sheogorath devienne son serviteur ». Ceux-là sont vrais et utiles —
et ils sont minoritaires.

## Ce n'est pas que Sheo — mesure sur les 9 fichiers de faits

| Fichier | Faits | Dont du type « semble obsédé par… » |
|---|---|---|
| `alfred_facts.json` | 11 | **10** |
| `twitch_facts_sheogorath.json` | 8 | **8** |
| `sheo_facts.json` | 15 | **8** |
| `sugar_facts.json` | 27 | **8** |
| `onizuka_facts.json` | 7 | 4 (bot retiré) |
| `twitch_facts_johnny.json` | 2 | **2** |
| `johnny_facts.json` | 42 | 2 |
| `maiq_facts.json` | 15 | **0** |

Le mécanisme existe dans **Alfred, Johnny, M'aiq, Sheogorath, SugarBot** et dans
`shared/twitch/llm.py`. **Malena n'en a pas.** M'aiq à 0 sur 15 montre que ce n'est pas
une fatalité : c'est la formulation de la consigne d'extraction qui décide.

---

# LE TRAVAIL

## Lot 1 — fermer le CANAL, pas filtrer la sortie

⚠️ **Ne PAS écrire un filtre par mots-clés** qui rejetterait « semble », « obsédé »,
« métaphore ». C'est la leçon [[gotcha-filtre-de-sortie-ne-ferme-pas-le-canal]] : un filtre
de sortie laisse passer ce qui compte et efface du légitime. Et
[[gotcha-filet-structurel-pas-le-cache]] : chercher l'invariant vrai.

**L'invariant vrai est celui-ci : un fait doit porter sur ce que l'UTILISATEUR a dit ou
fait, jamais sur le registre, le style ou le lexique de la conversation.** C'est une
contrainte de **consigne d'extraction**, pas de filtre.

Le travail : reprendre la consigne qui demande `<fact>` dans chaque persona concernée et la
rendre explicite. Ce qu'elle doit dire, sans le recopier mot pour mot :

- un fait note **ce que le mortel a dit de lui-même** : un goût, un métier, un projet, une
  habitude, un nom qu'il donne aux choses ;
- **JAMAIS** une observation sur le ton de l'échange, sur les images employées, ni sur ce
  dont « il semble obsédé » — **tes propres réponses font partie de la conversation, et
  elles ne t'apprennent rien sur lui** ;
- si rien de neuf n'a été dit sur le mortel, **n'émets pas de balise du tout**.

⚠️ **Commencer par M'aiq.** `maiq_facts.json` est à **0 sur 15** : sa consigne d'extraction
fait déjà quelque chose de juste. **La lire avant d'écrire quoi que ce soit** — c'est
peut-être toute la réponse, déjà présente dans le dépôt.

## Lot 2 — purger le bruit déjà stocké

Les faits empoisonnés sont **actifs** : ils sont injectés à chaque message. Corriger la
consigne n'efface pas ce qui est en base.

Écrire `tools/purge_faits_auto.py` qui, pour les 9 fichiers `data/*facts*.json` :
- **imprime** chaque fait avec son fichier et son utilisateur, marqué « à retirer » ou
  « gardé », et **ne modifie rien sans `--appliquer`** ;
- fait une **copie de sauvegarde** horodatée avant d'écrire ;
- ne retire QUE les faits qui décrivent le registre de la conversation.

⚠️ **C'est un humain qui valide la liste avant l'écriture.** Ce sont des données réelles
sur de vraies personnes, et certaines lignes sont justes (« Il aime le mot *sugar* »,
« ledev veut que Sheogorath devienne son serviteur ») : elles doivent survivre.

## Lot 3 — le plafond de 10 ne doit plus laisser le bruit chasser le vrai

`sheo_memory.py:170-174` : au-delà de 10, `pop(0)` retire le **plus ancien**, donc les
faits fondateurs partent en premier alors que le bruit auto-généré, plus récent, reste.

Ne pas inventer un système de score. Le minimum utile et honnête : **remonter le plafond
n'est pas la réponse** — c'est la qualité de l'entrée qui compte (lots 1 et 2). Se
contenter ici de **documenter le comportement** en commentaire, et vérifier que les 5 bots
ont bien la même règle. Si l'un diverge, l'aligner.

## Lot 4 — le verrou

`tests/test_faits_utilisateur.py`, neuf. Trois tests, chacun avec sa mutation :

1. **La consigne d'extraction interdit les faits de registre.** Pour chacune des 5
   personas concernées, le texte qui demande `<fact>` contient bien l'interdiction.
   *Mutation : la retirer d'une seule persona → rouge.* ⚠️ Le test doit boucler sur les
   **5** bots, jamais sur un seul : [[gotcha-un-bot-sur-six-manque-toujours]].
2. **`extract_facts` refuse un fait vide ou tronqué.** Comportement déjà présent — le
   verrouiller pour qu'une réécriture ne le perde pas.
3. **Le purgeur ne touche rien sans `--appliquer`.** *Mutation : écrire par défaut →
   rouge.*

---

# RECETTE

1. `pyflakes` sur les bots touchés, `tests/` et `tools/` — **avant** `pytest`.
2. `pytest` **seul**. Référence : **913 tests, 0 échec**.
3. Les mutations rejouées, chacune vérifiée rouge.
4. `tools/purge_faits_auto.py` lancé **sans `--appliquer`**, et sa sortie **remise à
   l'utilisateur** — il valide avant toute écriture.
5. **Ne rien déployer avant cette validation.**

# LES RÈGLES

1. **Ne pas toucher à la persona de Sheo** — `ac6914b` est validé en live sur le premier
   échelon, ce n'est pas le sujet ici.
2. **Ne pas écrire de filtre par mots-clés.** Voir le lot 1.
3. **Ne pas modifier `data/` sans `--appliquer`**, et jamais sans copie de sauvegarde.
4. **Lire la consigne de M'aiq d'abord.**
5. **Éditer les fichiers directement**, pas de script jetable.
6. **Ne pas commiter, ne pas pousser.** La relecture commite.
7. **Rendre compte de ce qui n'a pas été fait**, nommément.

---

# HORS PÉRIMÈTRE, MAIS À TRANCHER UN JOUR

**Le quota Groq fait tomber Sheo sur un 14B une réponse sur deux ou trois.** Le prompt à
3300 tokens contre 8000 tokens/minute, c'est structurel : ni la persona ni la mémoire n'y
changeront rien. Deux directions, à arbitrer par l'utilisateur, **pas dans ce lot** :
un **deuxième échelon plus fort** que `ministral-14b`, ou un **prompt plus court**. La
seconde aiderait aussi le premier échelon à mieux suivre ses consignes.
