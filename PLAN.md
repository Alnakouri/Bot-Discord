# PLAN — SUITE 10-bis : le commentaire qui présente encore LAYA comme candidat pour la défaite

Rédaction : Claude, le **2026-09-27**. Exécution : **Antigravity**. Plan précédent
(SUITE 10, mesuré, `6c7c91c`) lisible dans git (`5d3de20:PLAN.md`).

**Un commentaire, rien d'autre.** Aucun comportement ne change, aucun redémarrage.

---

## POURQUOI

`shared/journal_decisions.py` l.70–73 dit encore :

```python
# ⚠️ Ajoutee le 2026-09-23. `detect_defeat_signal` reconnait une DECLARATION de victoire
# (« je t'ai eu »), pas une victoire ; sa docstring dit que reconnaitre une vraie
# defaite demanderait « un appel LLM par message ». Laya ne coute rien par message :
# c'est un candidat — mais on mesure d'abord ce que la liste rate.
```

SUITE 10 l'a mesuré (`tools/sonde_laya_defaite.py`, `6c7c91c`, chiffres recomptés par
Claude sur le JSONL brut) : LAYA est **écarté**. Un commentaire qui dit « candidat » ferait
reproposer la même piste.

# LOT 1 — Remplacer le commentaire

**Fichier** : `shared/journal_decisions.py`, les **quatre** lignes ci-dessus (l.70–73),
remplacées **exactement** par :

```python
# ⚠️ Ajoutee le 2026-09-23. `detect_defeat_signal` reconnait une DECLARATION de victoire
# (« je t'ai eu »), pas une victoire ; sa docstring dit que reconnaitre une vraie
# defaite demanderait « un appel LLM par message ».
# ⚠️ LAYA A ETE MESURE ET ECARTE le 2026-09-27 (`tools/sonde_laya_defaite.py`) : sur
# 1 268 vrais messages du chat, il crie « defaite » 626 fois sans replique et 958 fois
# face a une replique absurde de Sheogorath (seuil fixe : 7), et signale 6 desaccords
# sur 8 ; p95 433 ms. La regex, elle : 0 sur 1 268. Il juge une phrase seule, pas une
# phrase FACE a une autre. Ne pas le reproposer ici sans un autre modele.
```

La ligne `DEFAITE = "defaite"` qui suit ne change pas.

# LOT 2 — Revendorer, vérifier, livrer

1. `python tools/vendor_core.py` : recopie `shared/journal_decisions.py` dans les six
   `*/core/journal_decisions.py`. Vérifier avec `git diff --stat` que **7 fichiers** ont
   changé (la source et ses six copies), et rien d'autre.
2. `python tools/sonde_core_drift.py` : aucune dérive.
3. `python -m pyflakes shared/journal_decisions.py`, puis pytest complet (**jamais deux
   pytest en parallèle**, port 8599).
4. Commit `docs(journal): LAYA mesure et ecarte pour la defaite (SUITE 10-bis)`. Push,
   **`gh run list` jusqu'au vert**. Pas de redémarrage : c'est un commentaire.
