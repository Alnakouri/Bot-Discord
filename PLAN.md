# PLAN — audit complet des 6 bots : la cause commune

Redaction : Claude. Execution : Antigravity.

Audit demande le **2026-09-04** : « fais un audit complet des bots pour trouver la cause de
tous les problemes ».

---

## Verdict : il n'y a pas six problemes, il y en a UN  🔴

**`on_message` est recopie a l'identique dans les 6 bots : 2 832 lignes au total.**

| Bot | `on_message` | `on_ready` | Fichier |
|---|---|---|---|
| Sheogorath | **913** | 320 | 2 712 |
| Alfred | 628 | 64 | 1 952 |
| M'aiq | 528 | 74 | 1 742 |
| Sugar | 294 | 96 | 1 033 |
| Johnny | 280 | 230 | 1 108 |
| Malena | 189 | 41 | 927 |

Tout ce qu'on a corrige aujourd'hui l'a ete **N fois** :

- le transcript ampute → **5 fois** ;
- le tracage des appels API → **3 fois** (les cascades inline) ;
- la garde de `on_ready` → **3 fois** ;
- `max_retries=0` → **12 fois**.

⚠️ **C'est la cause commune.** Chaque correctif doit etre applique six fois, et il suffit
d'en oublier un pour que le bug survive — c'est exactement ce qui est arrive avec
[[gotcha-import-ajoute-mais-pas-cable]] (Johnny corrige nulle part, derriere un test vert).

⚠️ **Ce n'est PAS un appel a tout refactoriser.** [[decision-independance-stricte-vendoring-core]]
est une decision assumee : chaque bot doit tourner seul. Le remede n'est pas de fusionner
les six, c'est de **faire remonter dans `shared/` ce qui est identique**, et de **tester la
presence du cablage** partout ailleurs.

---

## Ce que l'audit a trouve, verifie  🔵

### A. OpenRouter est du code mort — dans les 6 bots  🟠

`get_model_cascade()` ne rend **jamais** OpenRouter : ni dans les 6 cascades par persona,
ni dans les cascades generiques (TEXT, REPARTEE, IMAGE, AUDIO, REASONING), ni dans
`CASCADE_ANNONCE`. Il a ete retire le 2026-08-30 (free tier : 12 echecs sur 12), **mais
tout le code est reste** :

- **12 clients OpenRouter** construits au demarrage, pour rien ;
- une branche `elif client_type == "openrouter"` dans **4 cascades** (le noyau + 3 copies
  inline), soit ~120 lignes jamais atteintes ;
- `OPENROUTER_API_KEY` reclame dans le socle de `tools/preparer_env.py`.

⚠️ **Et c'est un piege arme** : `_fuite_de_raisonnement()` — la garde qui a empeche Malena
de reciter son raisonnement en Discord ([[gotcha-modeles-raisonnement-groq-openrouter]]) —
n'est appelee **que** dans la branche OpenRouter de `shared/llm_cascade.py`. Alfred et
M'aiq, qui ont leur cascade inline, **ne l'appellent nulle part**. Le jour ou quelqu'un
remet OpenRouter dans une cascade, ces deux-la recitent leur raisonnement.

**A faire** : trancher explicitement — soit retirer le code OpenRouter, soit le garder et
**cabler la garde dans les 3 cascades inline**. Ne pas laisser l'entre-deux. Un test doit
figer la decision.

### B. Sheogorath n'a pas la garde anti-incrustation  🟠

`_other_bot_in_focus` est present dans **5 bots sur 6** — Alfred, Johnny, M'aiq, Malena,
Sugar. **Sheogorath ne l'a pas**, sous aucun nom (`grep` sur `in_focus`,
`ANTI-INCRUSTATION`, `anti_incrust` : zero).

[[plan-anti-incrustation-4bots]] parlait de « ×4 » ; un 5e l'a recu depuis. Sheo est le
seul restant.

⚠️ **Verifie en logs le 04/09** : `[ANTI-INCRUSTATION] … se tait` apparait chez Johnny et
Sugar, jamais chez Sheo. Quand tu ecris a un autre bot, **Sheogorath peut s'incruster**.

**A trancher** : est-ce voulu (Sheo est le « pilote » de plusieurs mecanismes) ou est-ce un
oubli ? Si c'est voulu, **l'ecrire dans le code**, parce que rien ne le dit aujourd'hui et
que le prochain audit reposera la meme question.

### C. 46 blocs `except` totalement muets  🟠

Sur **219** blocs `except` dans les 6 bots, **46 avalent l'erreur sans un log** :

| Bot | `except` | muets |
|---|---|---|
| M'aiq | 47 | **15** |
| Alfred | 50 | **13** |
| Sheogorath | 57 | **11** |
| Malena | 21 | 3 |
| Johnny | 23 | 2 |
| Sugar | 21 | 2 |

⚠️ **C'est la meme famille que tous les bugs de la journee** : un 429 avale par le SDK, une
cascade non tracee, un `on_ready` qui plante « en silence » dans les logs de Discord. **Ce
qu'on ne voit pas, on ne le corrige pas.**

Ne PAS tous les convertir a l'aveugle : certains sont legitimes (un `_chrono.fin()` ne doit
jamais casser une reponse). **Les passer en revue un par un**, et mettre un
`logger.debug(...)` partout ou le silence n'est pas justifie par un commentaire.

### D. Ce que l'audit a verifie et trouve SAIN  🟢

- **Aucun appel bloquant** dans la boucle asyncio (`tools/sonde_blocking_calls.py` : 0
  probleme sur les 8 fichiers). L'audit de [[audit-2026-08-25-boucle-asyncio-et-independance]]
  tient toujours.
- **Aucune cle partagee** entre bots, sur les 5 fournisseurs
  (`tools/sonde_cles_partagees.py`).
- **Aucune derive** du noyau vendorise (`tools/sonde_core_drift.py`).
- Le silence entre bots, l'arret propre, le gestionnaire de cles, le statut Discord et la
  resolution des medias du message cite sont presents dans les **6**.
- ⚠️ Deux « absences » relevees par l'inspection sont **volontaires et documentees** :
  Malena n'a ni transcript ni memoire anti-repetition (cascade inline, aucun contexte de
  salon) ; Johnny et Sugar n'appellent pas `tracer_appel` **parce qu'ils passent par le
  noyau**, qui le fait pour eux.

---

## Corrections deja appliquees dans ce lot  ✅

1. **Mistral : toute la famille `mistral-*` est plafonnee** (429 permanent depuis le
   04/09). Ce n'est ni un probleme de cle — `models.list()` rend 46 modeles, les 6 bots ont
   des cles distinctes — ni une limite par minute : le refus persiste apres **70 s**
   d'inactivite. `mistral-medium` et `magistral-small` sont plafonnes aussi.
   → `MISTRAL_MAIN` bascule sur **`ministral-14b-latest`**, choisi sur sonde reelle
   (`tools/sonde_modeles_persona.py`, 90 appels, les 6 vraies personas) :

   | modele | mediane | asterisques | echo en ouverture |
   |---|---|---|---|
   | **ministral-14b-latest** | **1,28 s** | **11/18** | **0/6** |
   | open-mistral-nemo | 1,29 s | 15/18 | 1/6 |
   | ministral-8b-latest | 1,70 s | 16/18 | 1/6 |

   Les 4 cascades qui citaient `MISTRAL_SMALL` en dur ont ete basculees. `MISTRAL_PLAFONNE`
   est interdit dans les cascades par un test, sur le modele de `MISTRAL_HORS_TIER`.

2. **Un defaut de modele ne se corrige PAS par le prompt.** Mesure : Sheogorath est le
   **seul** bot dont le prompt interdise explicitement les asterisques — en tete, en
   majuscules, avec un 🚫 — et le **seul a 9/9** reponses qui en contiennent. Le taux le
   plus eleve des six. → `strip_markdown_emphasis()` retire les marqueurs, et
   `_strip_echo_opening` voit desormais `*Nul* ?!` comme une citation (il connaissait
   `"..."`, `«...»`, `“...”`, `'...'`, **pas le markdown**).
   ⚠️ **L'ordre est le correctif** : le nettoyage passe APRES le detecteur, sinon on lui
   retire le marqueur sur lequel il s'appuie. Un test fige cet ordre.

3. **`NVIDIA_API_KEY` prepare** : ajoute au socle de `tools/preparer_env.py` (l'outil le
   reclame pour les 6) et aux `.env.example` — **dont celui de Malena, qui n'existait pas
   du tout**.

---

## Ce que ce plan ne fait PAS

- Il ne fusionne pas les 6 `on_message` : l'independance stricte est une decision assumee.
- Il ne touche pas aux 46 `except` muets : ils demandent une revue cas par cas.
- Il ne tranche pas le sort d'OpenRouter ni celui de la garde de Sheo : ce sont deux
  decisions, pas deux correctifs.

## Regles de travail (rappel)

- **Ne jamais dire « c'est bon » avant que la CI soit verte.**
- **Relire ce qu'Antigravity a livre avant de commiter.**
- **Verifier chaque test par MUTATION.**
- ⚠️ **Le heredoc du Bash tool detruit les sequences d'echappement** : `\\` disparait,
  `\b` et `\1` deviennent des caracteres de controle **invisibles**. Une regex a ete
  silencieusement corrompue aujourd'hui. Construire les backslashes avec `chr(92)`, ou
  patcher **par index de ligne**.
- Deux `pytest` en parallele font echouer `tests/test_dashboard_restart.py` (port 8599).
- Un fichier de test neuf doit etre **suivi par git**.
- Noms de service compose : `alfred`, `johnny`, `maiq`, `malena`, `sheogorath`, `sugar`.
- Deploiement : le source est **bind-monte**, un `docker restart` suffit.
