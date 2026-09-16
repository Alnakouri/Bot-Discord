# -*- coding: utf-8 -*-
"""La sonde qui CHOISIT les modèles ne doit rien souffler au modèle qu'elle mesure.

`tools/sonde_modeles_persona.py` ajoutait « FAIS COURT (2-3 phrases max). » au prompt de
persona, en dur. Elle mesurait donc les candidats sous une consigne que les VRAIS bots
n'envoient jamais — et c'est ce qui a masqué le défaut le plus coûteux de la journée du
2026-09-16 : les trois bots les moins concis se sont avérés être exactement les trois
bots Mistral-first, `ministral-14b` rendant **13 phrases** là où `gemini-3.5-flash-lite`
en rend **5**, À PROMPT IDENTIQUE. La longueur n'avait jamais PU être un critère de
sélection : la sonde l'effaçait avant de mesurer.

Même famille que [[gotcha-sonde-ne-reproduit-pas-le-fournisseur]] : une sonde qui ne
reproduit pas les conditions réelles mesure autre chose que ce qu'on croit.

La consigne reste disponible derrière `--force-court`, pour reproduire l'ancien relevé.
"""
import ast
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONDE = os.path.join(_parent_dir, "tools", "sonde_modeles_persona.py")


def test_la_consigne_de_brievete_n_est_pas_injectee_par_defaut():
    """Elle doit vivre sous un `if`, jamais dans la construction du prompt."""
    arbre = ast.parse(open(SONDE, encoding="utf-8").read())

    souffles = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Constant) or not isinstance(noeud.value, str):
            continue
        if "FAIS COURT" not in noeud.value:
            continue
        souffles.append(noeud)

    assert souffles, (
        "la consigne a totalement disparu : `--force-court` ne peut plus reproduire "
        "l'ancien relevé, et on perd la comparaison avec les mesures d'avant"
    )

    # ⚠️ Viser le DRAPEAU, pas la présence d'un `if` : un `if True:` est un `ast.If`
    # parfaitement valide et laisserait passer la régression
    # ([[gotcha-verrou-trop-faible]], mutation jouée le 2026-09-16 — le verrou est
    # resté MUET au premier essai).
    def teste_le_drapeau(noeud_if):
        return any(
            (isinstance(x, ast.Attribute) and x.attr == "force_court")
            or (isinstance(x, ast.Name) and x.id == "force_court")
            for x in ast.walk(noeud_if.test)
        )

    gardes = [n for n in ast.walk(arbre) if isinstance(n, ast.If) and teste_le_drapeau(n)]
    assert gardes, "aucun `if` ne teste `force_court` : le drapeau ne commande rien"

    for souffle in souffles:
        sous_garde = any(any(x is souffle for x in ast.walk(g)) for g in gardes)
        assert sous_garde, (
            "la consigne de brièveté est injectée sans dépendre de `--force-court` : la "
            "sonde souffle la réponse au modèle qu'elle évalue, et la verbosité réelle "
            "devient invisible"
        )


def test_la_sonde_mesure_la_longueur():
    """Si elle ne compte ni phrases ni mots, la longueur ne peut pas peser dans le choix."""
    src = open(SONDE, encoding="utf-8").read()
    assert "phrases=phr" in src or '"phrases"' in src, \
        "la sonde ne releve pas le nombre de phrases"
    assert "mots=mots" in src or '"mots"' in src, \
        "la sonde ne releve pas le nombre de mots"


def test_le_drapeau_existe_dans_la_ligne_de_commande():
    src = open(SONDE, encoding="utf-8").read()
    assert "--force-court" in src, "le drapeau qui restitue l'ancien comportement a disparu"
