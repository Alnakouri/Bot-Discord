# PLAN — validation live de NVIDIA : faite, et ce qu'elle a trouve

Redaction et execution : Claude, le 2026-09-05.

Suite directe de l'audit du 04/09. Le lot precedent (`cb65ca0`) etait pousse, CI verte,
deploye — il ne restait que **la validation live**, seul point ouvert. Elle est faite.
Elle a aussi exhume un trou que personne n'avait vu.

---

## Etat : vert  🟢

Les 6 conteneurs redemarres, **zero traceback et zero mention d'OpenRouter** sur toute la
fenetre de demarrage, les six annoncent NVIDIA. NVIDIA repond **dans les six**, par la
cascade du noyau comme en direct.

La session a livre **trois** choses, dans cet ordre : la validation live elle-meme, puis
les deux defauts qu'elle a exhumes — le filet anti-fuite mort chez NVIDIA, et un
`NameError` qui empechait l'ecran de fin de quiz de s'afficher. Les deux sont **corriges,
verrouilles par des tests, et verifies par mutation**.

---

## Ce que la validation live a prouve  ✅

### 1. Le demarrage est propre sur les six

    docker logs --since 15m <bot> | grep -icE "traceback|openrouter"   →  0, six fois

⚠️ **Le compteur brut ment** : `docker logs` sans fenetre rend tout l'historique du
conteneur, y compris les lignes d'avant le correctif (jusqu'a 95 mentions d'OpenRouter
chez Sheogorath). Un `restart` ne remet pas ce journal a zero. **Toujours borner par
`--since`** avant de conclure quoi que ce soit d'un `grep` sur `docker logs`.

### 2. NVIDIA sert vraiment — mais aucun log ne pouvait le dire

`data/api_usage.db` au 05/09 : **zero appel NVIDIA** depuis son ajout. Non pas parce
qu'il est casse — parce qu'il est **4e echelon** et que les trois premiers repondent
toujours. Attendre `🟩 [NVIDIA` dans les logs, c'etait attendre une panne triple.

→ D'ou `tools/sonde_nvidia.py`, qui va le chercher au lieu de l'attendre. Elle s'execute
**dans** les conteneurs (`docker exec`) : les cles sont chiffrees et ne se dechiffrent
qu'avec la `.master_key` montee dans l'image, donc la lancer depuis l'hote ne dirait rien.

| mode | ce qu'il prouve |
|---|---|
| `ping` | la cle, le modele, l'URL et `nvidia_kwargs()` sont bons dans le conteneur |
| `--cascade` | `generate_response()` descend jusqu'a l'echelon `nvidia` et en rend du texte |

Mesure : **6/6 au ping, 6/6 a la cascade**, 400 ms – 1 s en regime normal. Et six cles
**differentes**, conformement a [[regle-une-cle-api-par-bot]].

⚠️ `--cascade` exerce **le noyau**. Alfred, M'aiq, Malena et Sheogorath portent leur
cascade dans `on_message` : ce vert ne dit rien de leur cablage, et leur code n'est pas
appelable hors d'un vrai message Discord. Pour eux l'autorite reste
`tests/test_nvidia_cable_partout.py`, qui en lit la structure. La sonde le **dit** en fin
de rapport plutot que de laisser croire l'inverse.

---

## Ce que la sonde a trouve — et qui est corrige  ✅

### Le filet anti-fuite du noyau etait MORT sur NVIDIA

Mesure du 05/09, ~56 appels : nemotron laisse fuir du meta-discours dans `content`
**environ une fois sur vingt**, malgre `reasoning_effort=none` :

    'p? The user wants exactly: pong'              (malena)
    'p deepellsellsellsellsellsellsworth, pong'    (maiq)

C'est ce qui serait parti dans Discord. Or le filet cense l'arreter ne peut pas :

```python
def _fuite_de_raisonnement(msg):
    pensee = (getattr(msg, "reasoning", None) or "").strip()
    contenu = (getattr(msg, "content", None) or "").strip()
    if not pensee or not contenu:
        return False          # ← NVIDIA sort TOUJOURS par ici
```

**L'endpoint NVIDIA ne remplit jamais `reasoning`** (verifie : 16 appels, vide a chaque
fois). Le detecteur rend donc `False` quoi qu'il arrive. Le commentaire de la branche
nvidia — « Filet malgre tout : le parametre pourrait cesser d'etre honore » — promet une
protection **qui n'existe pas**. Il ne protege que la forme OpenRouter, celle pour
laquelle il a ete ecrit, et qui vient d'etre retiree du code.

⚠️ C'est encore la meme cause commune : un filet ecrit pour un fournisseur, reconduit tel
quel sur un autre, sans que rien ne verifie qu'il mord toujours.

### La decision, prise : le filet lit desormais le CONTENU  ✅

`_fuite_de_raisonnement()` teste maintenant **deux** formes. La forme 1 (le champ
`reasoning`) est conservee telle quelle — elle sert si un fournisseur remplit ce champ.
La forme 2 est neuve : des **marqueurs de meta-discours** cherches dans `content` seul.

Les marqueurs ne sont pas inventes : ils viennent de `tools/sonde_fuite_raisonnement.py`,
qui les a etablis et **elargis au francais** le 04/09 (un detecteur anglophone avait
classe « propres » trois vraies fuites).

⚠️ **Mesure faite AVANT de brancher**, parce qu'un filet a faux positifs est pire que pas
de filet :

| mesure | resultat |
|---|---|
| 460 vraies reponses des 6 bots (memoires, archives, bios, statuts) | **0 faux positif** |
| 12 appels NVIDIA **sans** garde-fou (temoin) | **12 fuites sur 12, toutes attrapees** |
| 40 appels NVIDIA **avec** `reasoning_effort=none` | 0 fuite sur 28 aboutis |

Le seul marqueur qui produisait un faux positif, `mon rôle est de`, a ete **retire** du
noyau : « Mon rôle est de répondre, pas de me taire » est une replique **en personnage**.
Il reste dans la sonde, ou un humain lit le verdict. Un cas de test garde la porte fermee.

⚠️ **La forme 2 juge le TEXTE**, donc elle s'applique a tout appelant, pas seulement a
NVIDIA. C'est assume : le cout mesure est nul, et un echelon non terminal ne perd qu'un
saut de cascade.

⚠️ **La copie privee de Malena a ete supprimee.** Elle redefinissait
`_fuite_de_raisonnement()` dans son propre fichier : elle n'aurait **jamais recu** la
forme 2 — et Malena est precisement le bot qui a deja recite son raisonnement en plein
Discord. Elle importe le noyau maintenant, comme Alfred, M'aiq et Sheogorath. Le test qui
exigeait `def _fuite_de_raisonnement` chez elle a ete **retourne** : il exige l'import,
l'appel, **et l'absence** de re-definition ([[gotcha-import-ajoute-mais-pas-cable]]).

Le commentaire mensonger « Filet malgre tout » est corrige dans les **5** branches nvidia.

Verifie par **2 mutations** : filet neutralise → les 3 fuites reelles passent au rouge ;
copie de Malena ressuscitee → son test passe au rouge.

**Ce qui reste non sonde** : un reglage nemotron plus mordant que `reasoning_effort=none`
(`chat_template_kwargs={"thinking": False}`, directive systeme `/no_think`). La mesure a
ete tentee et **NVIDIA a rate-limite** (429 sur 12 des 40 appels de la premiere
configuration, 40/40 sur la suivante). Sans interet immediat : le filet couvre le cas.

### Latence NVIDIA tres irreguliere

400 ms en regime normal, mais des pics a **7–10 s** sur des reponses parfaitement
propres, sans correlation avec la fuite. En 4e echelon, apres trois echecs, cela
s'ajoute. A garder en tete si la cascade descend souvent jusque-la.

---

## Le second volet : « pyflakes avant pytest » etait un voeu  ✅

La regle est ecrite dans ce fichier depuis le 05/09, et **rien ne la jouait**. Un
`pyflakes` lance a la main pendant cette session a trouve, dans un fichier que le rapport
de la veille declarait propre :

    shared/games/views.py:821:  undefined name 'color'

`end_game` est la **seule des six methodes** de ce fichier qui construisent un embed a ne
pas definir `color = discord.Color.gold()`. **L'ecran de fin de quiz ne s'affichait donc
jamais** : `NameError` leve dans un callback discord.py, c'est-a-dire nulle part de
visible. → corrige, avec le commentaire qui dit pourquoi la ligne est la.

⚠️ **La CI ne pouvait pas le voir** : son etape `py_compile` couvre
`shared/*.py` — sans recursion — donc pas `shared/games/`. Et un `NameError` ne se voit
de toute facon pas a la compilation.

→ **`tests/test_aucun_nom_indefini.py`** : `pyflakes` joue **dans la suite**, sur les 10
racines du depot, copies vendorisees `*/core/` comprises. Il ne retient que les
**noms indefinis** et les **erreurs de syntaxe** — pas les imports inutilises, dont
l'echec apprendrait a ignorer le test. Verifie par **mutation** (le correctif retire →
rouge sur la bonne ligne).

⚠️ **`pyflakes` a ete ajoute a `requirements.txt`.** Sans ca le test faisait
`importorskip` et **se serait skippe en silence en CI** — un verrou qui s'auto-desarme
quand sa dependance manque, c'est-a-dire le piege meme qu'il ferme. L'import est
desormais **dur**.

Ce que ce verrou aurait attrape s'il avait existe : les **62 `logger` indefinis** du
04/09 et les **11 `SyntaxError`** du 05/09, qui ne cassaient aucun test.

---

## Ce qui reste ouvert par ailleurs

### Les 46 `except` muets — inventaire refait, chantier intact

Le decompte du plan precedent etait faux. **Mesure par `ast` le 05/09 : 104 gestionnaires
muets dans 36 fichiers**, hors copies vendorisees `*/core/` (qui se regenerent depuis
`shared/`). Les gros porteurs : `MaiqBot/bot_maiq.py` (15), `Alfred/bot_alfred.py` (13),
`Sheogorath/bot_sheogorath.py` (11), `shared/games/views.py` (7).

Et la contrainte qui avait fait echouer la conversion aveugle est maintenant **cartographiee** :
**7 fichiers n'ont aucun `logger`** — `dashboard/backend/features_config.py`,
`dashboard/backend/relauncher.py`, `shared/twitch/connection.py`, `shared/twitch_chat.py`,
`shared/twitch_announcer.py` et les sondes de `tools/`. Y ecrire `logger.debug(...)`
fabrique un `NameError` **leve depuis le gestionnaire d'exception**, ce qui est
strictement pire que le silence.

La methode reste celle du plan precedent, inchangee :

1. **Porter l'exception** : `except Exception as e:` puis `logger.debug(f"… : {e}")`.
2. **Verifier qu'un `logger` existe** — les 7 ci-dessus n'en ont pas.
3. **Laisser muets ceux qui doivent l'etre**, avec un commentaire qui le dit.

Premiere lecture faite sur les 9 de `shared/` : la plupart sont **legitimement muets**
(`sqlite3.OperationalError` sur un `ADD COLUMN` deja passe, `queue.Full` a l'arret,
`IntegrityError` sur un doublon, le `chrono` qui ne doit jamais casser une reponse). Deux
meritent un `debug` : `smart_router.py:414` (`except Exception` autour de
`fetch_message` — c'est la resolution du media d'un message cite qui echoue en silence)
et `twitch_announcer.py:375` (parsing ISO qui retombe sur la fenetre par defaut sans le
dire) — **mais ce dernier fichier n'a pas de `logger`**.

### Inchange

Vision de Sugar jamais exercee en live ; `report_error` n'est appele que pour Gemini ;
les 5 `MOOD CHANGE` dans la meme seconde apres reconnexion ; le reste de
[[dette-validation-live]]. Un 5e fournisseur reste inutile.

---

## Regles de travail — celles qui ont paye aujourd'hui

- ⚠️ **Borner `docker logs` par `--since`.** Sans fenetre, le journal d'un conteneur
  redemarre contient encore tout l'avant-correctif.
- ⚠️ **Un filet ecrit pour un fournisseur ne mord pas chez le suivant.** Le verifier au
  lieu de le reconduire — c'est la meme cause que les 4 cascades inline sans branche
  `nvidia`.
- ⚠️ **Un echelon de secours ne se valide pas en regardant les logs** : par construction
  il ne sert que quand tout le reste est tombe. Il faut aller le chercher.
- ⚠️ **Un detecteur ne se recopie pas dans une sonde** : la premiere version du verdict
  utilisait trois marqueurs choisis a la main et a compte OK une vraie fuite. Mais
  importer celui de la prod n'aurait rien valu non plus ici — il est mort sur ce
  fournisseur. Il a fallu un critere qui ne depende ni de l'un ni de l'autre.
- ⚠️ **Un verdict trop strict est un verdict qu'on apprend a ignorer** : compter `'Ping'`
  au lieu de `'pong'` comme un echec, c'est signaler un modele mal luné comme une panne.
- ⚠️ **Une regle qu'aucun outil ne joue est un voeu.** « pyflakes avant pytest » etait
  ecrit ici depuis un jour, et un `NameError` dormait deja dans le code.
- ⚠️ **Un verrou qui s'auto-skippe ne verrouille rien** : `importorskip` sur une
  dependance absente de `requirements.txt` rend un test vert en CI sans rien lire.
- ⚠️ **Ne jamais lancer deux `pytest` en parallele** : ils partagent `data/` et le port
  8599. Trois echecs distincts observes aujourd'hui — `test_dashboard_restart`,
  `test_sheo_anti_tic`, `test_sheo_cheese_dose` — tous **verts en isolation** (32/32).
- Le Bash tool casse les echappements dans un heredoc, et la console Windows est en
  cp1252 : un `⚠️` dans un `print()` leve `UnicodeEncodeError`. Docstrings seulement.
- `MSYS_NO_PATHCONV=1` pour un chemin conteneur ; `docker exec -i … python -` plutot que
  `docker cp`, qui echoue sur le montage lecture seule.
- Noms de conteneur : `bot-alfred`, `bot-johnny`, `bot-maiq`, `bot-malena`,
  `bot-sheogorath`, `bot-sugar`. Le source est bind-monte : un `docker restart` deploie.
