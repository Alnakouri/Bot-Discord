# PLAN — SUITE 19 : les questions `!discord` de Sugar trop longues

Rédaction : Claude, le **2026-09-29**. Exécution : **Antigravity**, sauf **[Claude]** / **[Ahmed]**.
Plans précédents (SUITES 14 et 15, livrés `905df34` et `a15b930`) : `483068c:PLAN.md`.
La SUITE 18 (rattrapage des mentions, garde des sondes, sonde Twitch) a été faite hors plan
par Claude (`10b17c3`, `3687fa4`, `1c31970`).

⚠️ **Mesure d'abord, rien n'est livré sans chiffres.** Cette passe consomme les clés de
Sugar : **jamais pendant un live**. Le garde `tools/garde_sonde.py` le refuse de lui-même ;
**ne pas utiliser `--forcer`**. Aucun redémarrage avant le LOT 4, avec l'accord d'Ahmed.

---

## LE CONSTAT (Claude, 29/09, 22 questions `!discord` réelles depuis le 20/09)

La clause dit déjà « moins de 80 caractères » : le modèle l'ignore (une règle de VOLUME
ne passe pas sur flash-lite, cf. mémoire « la longueur est un défaut de modèle »).
Longueur de la question (jusqu'au « ? ») par type tiré :

| type | n | < 80 car. | médiane |
|---|---|---|---|
| `designer` | 6 | 1 | 96 |
| `choix` | 8 | 2 | 103 |
| `chiffre` | 8 | 4 | 84 |

Les longues ont trois formes, toutes fabriquées par la consigne ou le décor :
1. **Énumération** : « Vos chevaliers préférés, ces lieux qui sentent la bière…, ou ces
   épées… ? ». La phrase du type `designer` ÉNUMÈRE elle-même « les personnages, les lieux
   ou les armes » : le modèle recopie la liste (gotcha « une formule NOMMÉE devient un tic »).
2. **Décor** avant la question : « Entre l'épée, la boue et les gueux de ce RPG historique… ».
3. **Le titre complet** : « … dans Kingdom Come: Deliverance II ? » = 28 car. à lui seul.

## LA VARIANTE B (une seule, pour isoler l'effet)

Dans `TYPES_DE_QUESTION_JEU_PAR_BOT["sugar"]` (`shared/twitch/dispatch.py`), **positif,
sans nommer de mot interdit, sans chiffre de longueur** :

- `designer` : « Cette fois, ta question, toujours au VOUVOIEMENT, leur demande leur
  personnage préféré de ce jeu. »  (UNE catégorie, plus de liste)
- `choix` : « Cette fois, ta question, toujours au VOUVOIEMENT, les fait choisir entre deux
  choses de ce jeu, chacune dite en deux ou trois mots. »
- `chiffre` : **inchangé** (témoin interne).

Et **une seule** phrase ajoutée à la fin de `CLAUSES_JEU_PAR_BOT["sugar"]` (juste après
« Un emoji peut la finir. ») : « Dis « ce jeu » plutôt que son titre. » Rien d'autre ne
change dans la clause.

---

# LOT 1 — Mesure A / B (après le live, garde compris)

```bash
.venv/Scripts/python tools/sonde_phrase_de_lien.py --bot sugar --jeu "Kingdom Come: Deliverance II" --n 18 --pause 5 > $SCRATCH/s19_A.txt
.venv/Scripts/python tools/sonde_phrase_de_lien.py --bot sugar --jeu "Kingdom Come: Deliverance II" --n 18 --pause 5 \
    --remplace "<phrase designer actuelle>" --par "<phrase designer B>" \
    --remplace "<phrase choix actuelle>" --par "<phrase choix B>" \
    --remplace "<fin de clause actuelle>" --par "<fin de clause + « Dis « ce jeu » plutôt que son titre. »>" > $SCRATCH/s19_B.txt
```

- Si le garde refuse (« en conversation ou en live »), **attendre**, ne pas forcer.
- `--pause 5` : 15 req/min/projet sur flash-lite (SUITE 8).
- Relire chaque sortie avec `--relire` (tableau recompté par l'outil, pas à la main).
- Vérifier que chaque `--remplace` a bien pris (la sonde refuse sinon).

## Critères (B contre A, sur 18 chacun, TOUS rapportés)

| critère | seuil pour livrer B |
|---|---|
| question < 80 car. | **≥ 12/18** et ≥ A + 5 |
| titre complet du jeu dans la question | ≤ 1/18 |
| tutoiement ou mélange tu/vous | ≤ 1/18 (A et B) |
| invitation Discord présente | 18/18 |
| 1er mot le plus fréquent | ≤ 6/18 |
| même question mot pour mot | 0 |
| replis (gabarit fixe) | ≤ A + 1 |
| `chiffre` (inchangé) : médiane | ± 10 car. de A (sinon la passe est bruitée) |

**Un critère qui échoue = on ne livre pas**, et le compte rendu le dit en tête. Donner les
sorties **brutes** (fichiers), pas un résumé.

# LOT 2 — [Claude] relit les sorties brutes et tranche

# LOT 3 — Livraison (seulement si LOT 2 dit oui)

Même changement que la variante B dans `dispatch.py`, verrou dans
`tests/test_phrase_de_lien_jeu_en_cours.py` : la phrase `designer` ne contient plus
« les lieux » ni « les armes » ; la clause contient « plutôt que son titre ». Suite entière,
`gh run list` vert.

# LOT 4 — [Ahmed] accord, puis `docker restart bot-sugar` seul (`State.StartedAt`).
