# PLAN — Sugar : toutes ses questions `!discord` commencent par « Combien »

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**, sauf les étapes marquées
**[Ahmed]**. Plan précédent (guillemet orphelin, livré `605fe1f`) lisible dans git
(`90f9c20:PLAN.md`).

Un seul fichier de code, et seulement si la mesure le justifie : `shared/twitch/dispatch.py`,
`CLAUSES_JEU_PAR_BOT["sugar"]` (l.863). Pas de copie vendorée de `shared/twitch/`.

---

## LE CONSTAT (vérifié le 27/09)

**En live**, depuis la livraison de SUITE 5 : **5 phrases `!discord` sur 6** commencent par
« Combien de… », et 3 parlent de « boue ». Un habitué entend la même question à chaque fois.

**En mesure, c'est pire, et c'est la clause qui le fabrique.** Les séries brutes de SUITE 5
(`~/.gemini/antigravity-cli/brain/601962eb-…/scratch/suite5_raw_{A,B1,B2}.txt`, Sugar,
Gemini, KCD2, n=18), comptées au **premier mot** :

| série | clause | commence par « Combien » |
|---|---|---|
| A | ancienne (avant SUITE 5) | **7/18** |
| B1 | « question simple … moins de 80 car. » | **14/18** |
| B2 (**en prod**) | B1 + exemples d'invitation | **17/17** |

Plus on resserre la question (courte, simple, sur le vécu, terminée par `?`), plus le
modèle converge sur la question la plus courte qui remplit le cahier des charges : une
question fermée qui demande un chiffre.

⚠️ **La sonde sous-estime le tic** : `tools/sonde_phrase_de_lien.py` (l.219) compte les
ouvertures sur les **trois** premiers mots. Pour B2 elle affichait « 9× combien de fois »,
parce que « combien d'heures » et « combien d'armures » comptent à part. **Ne pas se fier à
sa ligne `ouvertures` pour ce plan** : compter le premier mot soi-même (LOT 1).

**Ce qu'on ne touche pas** : « Bohême » dans 17/17 vient de la fiche IGDB (« set in
Bohemia »). C'est un fait vrai qu'on lui donne, pas un tic à corriger.

---

# LOT 0 — Avant toute passe

1. Lire la consommation du jour dans `data/api_usage.db` pour Sugar et Gemini (lecture
   seule, on ne modifie jamais la base). La passe coûte **54 appels** (3 séries × 18) sur
   les clés de Sugar. Si Sugar est en live sur `#ma_streameuse`, **attendre la fin du live** :
   la passe dégrade l'échelon de prod.
2. **Ne pas lancer `tools/sonde_phrase_de_lien.py --help`** : lire ses options dans le
   fichier (l.239–275).

# LOT 1 — Mesurer (aucune modification du code de prod)

Même protocole que SUITE 5 : on copie le runner de `601962eb-…/scratch/runner_suite5.py`,
`--bot sugar --tete gemini --jeu "Kingdom Come: Deliverance II" --n 18`, avec la fiche
réelle (la sonde la charge : l'en-tête de B2 disait `fiche 9184 car.`). Les clauses sont
passées par `--clause-jeu`, **sans toucher à `dispatch.py`**.

La clause d'essai = le texte **exact** de `CLAUSES_JEU_PAR_BOT["sugar"]` en prod, avec
**une seule phrase changée** :

> « La première est une question simple sur ce que CE JEU leur a fait vivre, à eux, quand
> ils y ont joué : »

| série | la phrase ci-dessus devient |
|---|---|
| **A** | inchangée (= prod, remesurée aujourd'hui : c'est la référence) |
| **C** | « La première est une question qui les invite à RACONTER ce que ce jeu leur a fait vivre, à eux, quand ils y ont joué : » |
| **D** | « La première est une question ouverte, de celles qui appellent un souvenir, sur ce que ce jeu leur a fait vivre, à eux, quand ils y ont joué : » |

⚠️ **Règles d'écriture, à ne pas enfreindre en recopiant** :
- **Ne nommer AUCUN mot interrogatif** dans la clause, ni pour l'interdire (« pas de
  Combien ») ni pour l'exemple (« Quel moment… ») : une formule nommée devient le nouveau
  tic, et une interdiction écrite fait office de démonstration.
- **Ne rien ajouter d'autre** : pas de « varie tes tournures ». Chaque appel est
  indépendant, le modèle ne voit jamais ses phrases précédentes, et la clause dit déjà
  « jamais deux fois la même » pour l'invitation.
- Tout le reste de la clause (vouvoiement, 80 car., `?` final, seconde phrase, exemples
  d'invitation, emoji) est **identique mot pour mot** à la prod.

**À compter pour chaque série, en lisant les 18 phrases** :

| critère | seuil pour livrer | A attendu (SUITE 5) |
|---|---|---|
| **premier mot le plus fréquent** (le compter soi-même) | **≤ 6/18** | ~17/18 |
| invitation finale qui nomme Discord | ≥ 16/18 | 17/18 |
| soudure (« avant de venir… » dans une seule phrase) | ≤ 2/18 | 0/18 |
| question de moins de 80 car., finie par `?` | ≥ 16/18 | — |
| pique sur le chat | 0 | 0 |
| partie en cours ou Discord inventé | ≤ A + 1 | 0 |
| même invitation mot pour mot | ≤ 6/18 | 4/18 |
| replis sur le gabarit fixe | ≤ A + 1 | 1/18 |
| longueur médiane (sans le lien) | ≤ 130 car. | 109 car. |

Noter aussi, sans seuil : le nombre de phrases contenant « boue » (B2 : 7/17).

⚠️ Plancher de bruit du harnais : ±0,4 sur les notes, jusqu'à 6/18 d'écart sur un compte.
Un gain de 17 → 12 n'est **pas** un résultat. Le seuil ≤ 6/18 est fait pour être loin du
bruit.

Sorties brutes dans le scratch d'Antigravity : `suite8_raw_{A,C,D}.txt`.

# LOT 2 — Décider

- **C ou D passe tous les seuils** → livrer le meilleur des deux (premier mot le plus bas,
  à égalité : C, le plus court). Si les deux passent, **[Ahmed]** lit les 18 phrases de
  chacun et tranche.
- **Aucun ne passe le seuil du premier mot** → **ne rien livrer**, rendre le tableau et les
  sorties brutes. Le levier suivant n'est plus dans la clause (tirer un angle de question
  côté code) et fera l'objet d'un autre plan.
- **Un des deux passe le premier mot mais casse un autre seuil** → ne pas livrer, rendre
  le tableau.

# LOT 3 — Livrer (seulement si le LOT 2 l'autorise)

1. Dans `CLAUSES_JEU_PAR_BOT["sugar"]` (`shared/twitch/dispatch.py` l.863), remplacer la
   **seule** phrase `"La première est une question simple sur ce que CE JEU leur a fait
   vivre, à eux, quand ils y ont joué : "` par la version gagnante. Rien d'autre ne change.
2. Au-dessus du dict, ajouter au tableau de SUITE 5 (l.~840) une ligne « premier mot le
   plus fréquent » avec les trois séries SUITE 5 (7/18, 14/18, 17/17) et une colonne pour la
   série livrée. Mentionner la date et la sous-estimation de la sonde (3 mots).
3. **Test** : chercher les tests qui citent le texte de la clause de Sugar
   (`grep -rn "question simple" tests/`) et les mettre à jour. Ajouter un verrou qui échoue
   si la clause de Sugar contient un mot interrogatif (`combien`, `quel`, `quelle`,
   `comment`, `pourquoi`, `qu'est-ce`), insensible à la casse, pour qu'aucune retouche future
   ne nomme de formule.
4. `python -m pyflakes shared/twitch/dispatch.py` + les fichiers de test touchés, pytest
   ciblé, puis la suite complète (**jamais deux pytest en parallèle**, port 8599).
5. Commit `fix(twitch): varier la question de Sugar sur !discord (SUITE 8)`, avec le tableau
   dans le message, **y compris les critères qui échouent**. Push, **`gh run list` jusqu'au
   vert**.
6. `docker restart bot-sugar` **hors live**. Vérifier le code dans le conteneur
   (`MSYS_NO_PATHCONV=1 docker exec bot-sugar grep -c "<un mot de la nouvelle phrase>"
   /app/shared/twitch/dispatch.py`) et `docker logs --since 5m bot-sugar` sans erreur.

**Critère de clôture** : tableau rendu. Si livraison : CI verte, conteneur redémarré sans
erreur. Ensuite, en live, **[Ahmed]** ou Claude recompte les premiers mots sur les 10
prochains `!discord` de Sugar.

---

## Hors périmètre (noté, NON planifié)

- **La sonde compte les ouvertures sur 3 mots** : c'est ce qui a caché ce tic. Ajouter une
  ligne « premier mot » à `tools/sonde_phrase_de_lien.py` serait utile, mais dans un autre
  plan : ce plan-ci ne touche pas à l'outil qui le mesure.
- **Johnny, dates inventées** : une seule phrase de lien de Johnny en live en 72 h. Rien à
  corriger tant que le live ne montre pas de replis.
- **Alfred, boisson inventée (3/4)** : dormant, `!discord` n'est pas armé chez lui.
