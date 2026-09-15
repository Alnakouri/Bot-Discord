# PLAN — Faire parler les bots sans humain

Rédaction : Claude, le **2026-09-15**. Exécution : **Antigravity**, sauf le lot 4.
Fait suite à `abb7aea` (les événements serveur), livré et déployé le même jour.

Le plan précédent a retiré une attente en forçant un tirage. Il reste **un seul gros
bloc** de dette : « un humain doit parler aux bots » — le ton par humeur de Sheo, le
moule répétitif de Sugar, la fidélité au lore, les anti-tics, le carnet de rancunes.
Ouvert depuis le 01/09, jamais entamé, parce qu'il semblait exiger une conversation.

Il ne l'exige pas. **L'instrument existe déjà et il dort depuis trois mois.**

---

## LA PREUVE, relevée le 15/09 avant d'écrire ce plan

L'index mémoire annonçait trois chantiers à ouvrir. **Deux étaient déjà faits.** C'est
la leçon de [[dette-validation-live]] qui se répète : *une mention « reste à faire »
qu'on ne revisite jamais ne signale plus rien.*

| Ce que l'index disait | Ce que le dépôt dit |
|---|---|
| « harnais d'éval persona à construire » | **Il existe** : `tests/eval/` — `run_eval.py`, `runner.py`, `judge.py`, `persona_loader.py`, `gimmick.py`, `scenarios.json`, commit `e20c816`. Il vise déjà **les 6 bots actuels** (`BOTS` ligne 19) et **charge les 6 personas d'aujourd'hui sans erreur** (vérifié le 15/09). |
| « Répartie Phase 3 : chantier OUVERT, code perdu » | **Livrée et câblée sur les 6.** `shared/repartee_lessons.py` vendorisé dans les 6 `*/core/`, `detect_defeat_signal` + `reflect_on_defeat` + `format_for_prompt` appelés dans les **6** `bot_*.py`, `build_anti_tic_consigne` partout (le « Lot 1 » du plan `d2abc20`), et `tests/test_repartee_lessons.py` + `tests/test_anti_tic_partage.py` existent. |
| « dashboard : un clic jamais donné » | **Vrai, et seul vrai.** Le dashboard n'est même pas lancé (`127.0.0.1:8501` ne répond pas) — il se démarre à la main par `dashboard/start_dashboard.bat`. |

⚠️ **`shared/long_term_memory.py` n'existe plus, et c'est une DÉCISION, pas une perte** :
rapatriée par bot en `4cc86ac` (« solo-deploy »), conforme à [[bots-independants]]. **Ne
pas la recréer dans `shared/`.**

Le dernier rapport d'éval date du **19/06** (`tests/eval/reports/eval_20260619_0052.json`).
Entre-temps : les 4 humeurs de Sheo, sa longueur qui obéit au message, les anti-tics, la
voix de Sugar, le « Maître » d'Alfred, la cascade par persona, le transcript amputé, le
carnet de leçons. **Rien de tout cela n'a jamais été mesuré.**

---

# LOT 1 — Le harnais reprend du service : le run de référence

**Aucun fichier de bot ne change dans ce lot.** On fait tourner ce qui existe, et on
rend le résultat lisible.

    python tests/eval/run_eval.py

### 1.1 — Le piège documenté, et qui a déjà mordu

Run du 18/06 : les quotas free-tier s'épuisent **en cours de run**, et les bots évalués
en **dernier** tombent sur des cascades échouées. Ils ne rendent pas une erreur : ils
rendent des **zéros**, indiscernables d'une mauvaise persona. Trois bots sur six étaient
faux ce jour-là.

Le tell est connu : `anti_contamination` vaut **5.00 partout, constamment** ; quand un
run est sain, `anti_fuite` ne vaut pas 0. Un score à `-1` signale un juge mort.

**À faire** : `run_eval.py` doit **refuser de produire un rapport qu'on croira**. En fin
de run, un bloc de santé en tête du JSON :

- nombre de scores à `-1` (doit être 0 — c'est le critère §1.5 déjà atteint le 17/06) ;
- par bot, le nombre d'appels LLM **échoués** pendant son passage ;
- un verdict `fiable: true/false` **par bot**, faux dès qu'un appel a échoué.

Un bot non fiable ne doit **pas** apparaître dans le tableau des scores : il apparaît
dans une section « non mesuré ce jour-là, quota ». Mieux vaut trois bots mesurés que six
dont trois mentent.

### 1.2 — L'ordre des bots ne doit plus décider du résultat

`BOTS` est une liste figée : les derniers paient toujours. **Tirer l'ordre au hasard à
chaque run**, en journalisant la graine — ainsi un bot systématiquement mauvais ne peut
plus être un artefact de position, et deux runs consécutifs se contredisent visiblement
si c'est le quota qui parle.

### 1.3 — Le delta, c'est le livrable

Le rapport doit porter le **delta par critère vs le rapport précédent**, et nommer les
trois plus grosses chutes. Un tableau de 252 scores que personne ne lit ne vaut pas la
ligne « `alfred/provocation` : fidélité 4.3 → 1.0 ».

---

# LOT 2 — Les scénarios ignorent tout ce qui a été construit depuis juin

Six scénarios (`banal`, `provocation`, `autre_bot`, `repetition`, `fuite`, `fantome`) et
sept critères (`fidelite`, `longueur`, `ton_fr`, `role`, `citation`, `anti_fuite`,
`anti_contamination`). Aucun ne touche ce qui a été écrit depuis.

**À ajouter à `scenarios.json`** — et, quand c'est possible, **mesuré par du code, pas
par le juge** : un juge fatigué se trompe, un compteur de mots non.

| Scénario | Ce qu'il provoque | Mesure |
|---|---|---|
| `defaite` | un message qui doit déclencher `detect_defeat_signal` — c'est le LOT 3 | déterministe : la catégorie rendue |
| `humeur_sheo` | 4 échanges, une par humeur | juge (`ton_fr`) |
| `sugar_30_mots` | 3 messages à Sugar | **déterministe** : « ~30 mots, jamais plus » est une règle ABSOLUE de son prompt |
| `alfred_maitre` | le créateur s'adresse à Alfred | **déterministe** : « Maître » présent, « manoir » absent — en **minuscules**, [[gotcha-verrou-trop-faible]] 2e cas |

⚠️ **Ne pas ajouter de critère au juge pour ces quatre-là.** Ajouter un critère change
l'échelle de tous les rapports passés et rend le delta du lot 1 illisible. Les mesures
déterministes vivent à côté des scores, comme `gimmick.py` le fait déjà.

---

# LOT 3 — Le carnet de leçons n'a jamais été vu fonctionner

La Phase 3 est **livrée et câblée sur les 6** — mais rien ne prouve qu'elle tourne. Le
chemin est : un message de défaite → `detect_defeat_signal` rend une catégorie → le bot
ayant parlé juste avant → `reflect_on_defeat` écrit une leçon → `format_for_prompt` la
réinjecte au tour suivant.

**À faire** : un test qui parcourt ce chemin **en entier**, sans LLM (la réflexion est
remplacée par un faux), et qui vérifie la **réinjection** — pas seulement l'écriture.

Deux gardes que le plan `d2abc20` nommait comme le vrai risque, à verrouiller :

1. **la leçon est du texte inspiré par un inconnu** : assainissement (aucune consigne
   d'identité, aucune mention, longueur bornée) et débit borné (5 min/salon, 6/jour/bot).
   Sans ça, on réécrit une persona en se déclarant vainqueur trois fois ;
2. **le signal de défaite exige que le bot ait parlé juste avant** — sinon un verdict
   lancé à un humain (« t'as rien compris ») déclenche la réflexion d'un bot qui n'était
   pas dans la joute.

Mutation à rejouer pour chacune : retirer la borne de débit, retirer la condition « le
bot a parlé juste avant ». Les deux doivent faire crier.

⚠️ **Une question à trancher, pas à décider seul** : le plan du 08/09 excluait Malena
(« elle appelle le LLM avec `transcript=""`, il n'y a pas de joute à observer — **5 bots,
pas 6** »). Or `MalenaBot/bot_malena.py:763` la câble comme les autres. Soit la décision
a changé, soit le rollout a débordé. **Le signaler, ne pas retirer le câblage.**

---

# LOT 4 — Le dashboard, au navigateur — exécution : **Claude**, pas Antigravity

La seule catégorie de dette qui exige vraiment quelqu'un devant un écran, ouverte depuis
le 01/09. Claude pilote Chrome ; il faut de l'utilisateur **le démarrage et l'accès** :

    dashboard\start_dashboard.bat        # puis 127.0.0.1:8501, identifiants demandés

Protocole, dans cet ordre — et [[gotcha-regarder-l-ecran-avant-le-code]] s'applique à
chaque étape : **regarder l'écran avant d'accuser le code**, le sélecteur « Tous les
bots » masque les panneaux par-bot.

1. **Le toggle du décret** — `data/bot_features.json` porte `decret_enabled: true` pour
   les 6 ; c'est le **basculement** qu'on n'a jamais vu. Basculer, relire le fichier,
   rebasculer, relire.
2. **Le bouton de redémarrage** — `tests/test_dashboard_restart.py` existe ; le clic, non.
   Le faire sur **un seul bot**, et vérifier le redémarrage côté `docker ps`.
3. **Les graphes et le statut réel** — vérifier que « CONNECTÉ » mesure bien la connexion
   ([[gotcha-un-relooking-change-ce-que-le-libelle-affirme]] : un libellé a déjà affirmé
   autre chose que ce que la donnée mesurait).
4. **Capture d'écran à chaque étape**, jointe au compte rendu.

⚠️ Le redémarrage touche des bots **en service**. Le faire hors d'un moment où quelqu'un
leur parle, et sur un seul.

---

## Hors lot — trois lignes qui valent le détour

`⚠️ [TWITCH_CHAT:<bot>] Token invalide (code 401)` tombe en **WARNING** au démarrage des
3 bots Twitch (13/09, 14/09, 15/09). Ce n'est pas une panne : la ligne suivante est
`🔄 Token rafraîchi avec succès`, puis `🔌 Connecté à #chaine_du_dev`. Un
avertissement pour un chemin prévu et auto-réparé, c'est la **troisième** fausse alarme
Twitch de la série — et on apprend à ignorer ce qui crie pour du nominal
([[gotcha-alerte-qui-crie-pour-du-nominal]]). Passer en `info`, ou fondre les deux lignes
en une seule : « token expiré, rafraîchi ».

---

## Ce qui n'est PAS dans ce chantier

- **Recréer `shared/long_term_memory.py`** : rapatriée par bot, c'est une décision.
- **Toucher au routage de la répartie** : `TEXT == REPARTEE`, Grok a disparu du code.
- **EventSub, annonces de live, STT** : gelés le 08/09, ils demandent un vrai stream.
- **Changer les seuils, les prompts ou les répliques** sur la foi d'un seul run : le run
  de référence sert à MESURER. On corrigera ce qu'il montre, dans un plan suivant.
