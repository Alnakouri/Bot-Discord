# PLAN — les 104 `except: pass` : lus un par un, et le silence nu interdit

Redaction et execution : Claude, le 2026-09-05 (3e session du jour).

Suite directe du lot `25141f9`. Le seul chantier encore ouvert etait celui-ci ; il est
ferme, et verrouille.

---

## Etat : vert  🟢

**633 tests passent** (+46 sous-tests), suite complete en un seul processus. Zero nom
indefini, zero erreur de syntaxe, aucune derive du noyau vendorise.

---

## Ce que la validation live a ferme au passage  ✅

Le transcript Discord du 05/09 (13:49–13:51) clot **la vision de Sugar**, dernier des six
a n'avoir jamais recu d'image en direct : image postee a 13:49, description rendue a
13:50 (« Un chevalier tout en pointes et en acier… »). Les six ont repondu dans la meme
minute, et le decret de Sheogorath a bien rendu son image a 20:10.

---

## Le chantier : 104 `except ...: pass`, lus un par un

L'inventaire par `ast` du 05/09 en comptait **104 dans 36 fichiers**, hors copies
vendorisees. Le decompte a ete **reproduit a l'identique** avant de toucher quoi que ce
soit — un chantier qui commence par un chiffre qu'on ne sait pas refaire commence mal.

⚠️ Un premier detecteur, plus large (« tout gestionnaire qui ne journalise ni ne releve »),
en trouvait **366**. Ce n'est pas le meme objet : il comptait les gestionnaires qui font
un vrai repli (`except ValueError: elapsed = 0`). Le chiffre de 104 vise le `pass` nu,
celui qui n'a aucune intention lisible.

### La regle appliquee

Trois issues, jamais une seule :

1. **Journaliser** quand le silence peut cacher un bug — en `debug` si l'echec est
   nominal (message deja supprime, permission absente), en `warning` s'il laisse le
   systeme dans un etat faux.
2. **Rester muet, mais le dire** — un commentaire sur place qui donne la raison.
3. **Ne jamais ecrire `logger.` dans un fichier qui n'en a pas** : ce serait un
   `NameError` **leve depuis le gestionnaire d'exception**, strictement pire que le
   silence. Les 8 fichiers concernes ont ete traites en (2), sauf `dashboard/backend/app.py`
   qui utilise deja `print`.

### Ce que la lecture a trouve

**Les 7 `on_timeout` de `shared/games/views.py` sont la meme cecite que le bug du quiz.**
Chacun construit un embed puis edite le message, le tout sous `except Exception: pass`.
Un message supprime et un `NameError` y ont exactement le meme aspect : aucun.
C'est cette forme qui a fait que **l'ecran de fin de quiz ne s'affichait jamais** pendant
des semaines. → helper `_ecran_expiration_echoue()` : `debug` pour un `HTTPException`
(nominal), `warning` + `exc_info` pour tout le reste (un bug).

**Trois silences laissaient le systeme dans un etat faux** — passes en `warning` :

| endroit | ce que le silence cachait |
|---|---|
| `MaiqBot/bot_maiq.py:691` | suppression de l'enigme en base : **l'enigme restait active** |
| `MaiqBot/bot_maiq.py:1146,1641` | participant non enregistre : il ne comptait pour rien |
| `Alfred/bot_alfred.py:1204-1229` | retrait du timeout, du role et du pseudo de sanction : **l'utilisateur restait puni** |

**Six appels LLM avalaient leur echec** (`bot_sheogorath.py`, feature imposteur, Groq et
Mistral) : la reponse retombait sur un texte par defaut sans que rien ne dise pourquoi.
→ `debug` nomme par fournisseur.

**Un chemin media** (`shared/smart_router.py:414`) et **une fenetre d'annonce**
(`shared/twitch_announcer.py:375`) ont recu le `debug` que le plan precedent avait deja
identifie.

**Le reste est legitimement muet** — et le dit maintenant : `ALTER TABLE` deja passe,
`queue.Full` a l'arret, `IntegrityError` sur doublon, annulation d'une tache qu'on vient
soi-meme d'annuler, fichier temporaire deja disparu, flux console non reconfigurable,
`shared/` absent (les bots doivent tourner sans).

---

## Le verrou : `tests/test_except_muet_documente.py`  ✅

Il **n'interdit pas le silence** — beaucoup de gestionnaires doivent se taire. Il interdit
le silence **nu** : un `except ...: pass` doit porter un commentaire, sur la ligne
`except` ou sur le `pass`.

⚠️ Le commentaire doit etre **dans** le gestionnaire. Un commentaire au-dessus du `try`
explique le `try`, pas le silence.

⚠️ Les copies `*/core/` sont **incluses** : c'est la qu'un correctif de `shared/` peut ne
pas etre descendu. Le test les a d'ailleurs immediatement prises en flagrant delit — il a
fallu rejouer `tools/vendor_core.py`.

Verifie par **mutation** : commentaire retire de `shared/chrono.py:42` → rouge sur la
bonne ligne.

⚠️ `tests/test_depot_complet.py` a fait son travail : le nouveau fichier de test n'etait
pas suivi par git, et il l'a dit. Il n'existait que sur cette machine.

---

## Ce qui reste ouvert

- **`report_error` n'est appele que pour Gemini** : decision de design a poser.
- **5 `MOOD CHANGE` dans la meme seconde** apres une reconnexion : jamais explique.
- Un **5e fournisseur reste inutile**. Pistes jamais sondees : Cerebras, Together.
- Un reglage nemotron plus mordant que `reasoning_effort=none` (`chat_template_kwargs`,
  `/no_think`) : jamais sonde, NVIDIA rate-limite des qu'on enchaine. Sans urgence, le
  filet anti-fuite couvre le cas.
- Le reste de [[dette-validation-live]] est inchange.
- Les 2 pistes de fond : **Phase 3 repartie** (a re-specifier, code perdu) et la
  **migration mempalace**.

---

## Regles de travail — celles qui ont paye aujourd'hui

- ⚠️ **Un chantier commence par reproduire son propre chiffre.** Deux definitions de
  « gestionnaire muet » donnent 366 et 104 ; sans reproduire le 104 on aurait cru a une
  explosion du probleme.
- ⚠️ **Ne jamais ecrire `logger.` sans avoir verifie qu'il existe** dans ce fichier-la.
- ⚠️ **`git checkout -- <fichier>` pour annuler une mutation de test efface aussi le
  travail non commite du meme fichier.** C'est arrive sur `shared/chrono.py` : la
  mutation a bien vire au rouge, et le correctif est parti avec. Sauvegarder ailleurs.
- ⚠️ **Editer en remontant** : convertir un `except: pass` d'une ligne en deux lignes
  decale tout ce qui suit. Traiter les cibles par numero de ligne **decroissant**.
- ⚠️ Les fichiers du depot sont en CRLF cote disque et en LF dans l'index. Un outil qui
  reecrit en LF ne change rien au contenu commite, mais `git status` peut afficher des
  fichiers « modifies » a diff vide : `git checkout --` sur des fichiers reellement
  identiques nettoie l'affichage.
- ⚠️ **Ne jamais lancer deux `pytest` en parallele** : ils partagent `data/` et le port 8599.
