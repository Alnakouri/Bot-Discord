# -*- coding: utf-8 -*-
"""Les CINQ branches d'intention d'Alfred sont rangees — `aucune` comprise.

Le 20/09, le journal a ete pose sur la seule branche « ordre de repos ». En deux jours
il a produit **zero ligne d'intention** : cette branche exige qu'on mentionne Alfred ET
qu'on emploie un mot d'arret, ce qui n'arrive pour ainsi dire jamais.

Les quatre autres decisions du meme bloc se prennent avec des listes de mots-cles de la
meme famille — venir, gracier, nettoyer — et deux d'entre elles declenchent une ACTION
(quitter un vocal, rejoindre un vocal), donc leur erreur se VOIT.

⚠️ Et la cinquieme, `aucune`, est la plus instructive : c'est elle qui montrera si
quelqu'un demande a Alfred de venir ou de partir avec des mots absents des listes. Un
journal qui ne garderait que les cas ou une liste MORD ne pourrait jamais le montrer —
meme raison que pour `aucune` cote questions sur le jeu.

⚠️ Verrou par AST sur le fichier du bot, jamais sur une reconstitution de sa logique
([[gotcha-test-qui-retape-la-logique]]) : un test qui rejouerait ces `if` resterait vert
le jour ou on les retirerait du bot.
"""
import ast
from pathlib import Path

BOT = Path(__file__).resolve().parent.parent / "Alfred" / "bot_alfred.py"

# Ce que la regle en place peut rendre. `repos` et `bavardage` sortent de la branche
# d'arret, deja journalisee depuis le 20/09 et servie par Laya.
ETIQUETTES = {"venue", "pardon", "nettoyage", "aucune"}


def _etiquettes_journalisees():
    """Les etiquettes litterales passees a `journalise(...)` dans le fichier du bot."""
    arbre = ast.parse(BOT.read_text(encoding="utf-8"))
    vues = set()
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "journalise"):
            continue
        # journalise(bot, decision, texte, etiquette, detail=...)
        if len(n.args) >= 4 and isinstance(n.args[3], ast.Constant):
            vues.add(n.args[3].value)
    return vues


def test_les_quatre_branches_manquantes_sont_rangees():
    vues = _etiquettes_journalisees()
    manquantes = ETIQUETTES - vues
    assert not manquantes, (
        f"ces branches d'intention ne sont plus journalisees : {sorted(manquantes)}. "
        f"Sans elles le corpus se remplit au rythme de la seule branche d'arret — "
        f"zero ligne en deux jours.")


def test_le_cas_AUCUNE_est_range_LUI_AUSSI():
    """Sans les negatifs, on ne peut pas mesurer ce que les listes de mots RATENT."""
    assert "aucune" in _etiquettes_journalisees(), (
        "le cas `aucune` a disparu : le journal ne montrerait plus que les succes des "
        "listes de mots-cles, jamais leurs manques — et c'est le manque qu'on cherche.")


def test_le_journal_ne_DECIDE_toujours_rien():
    """La garantie de ce journal depuis le 20/09 : il observe, il ne change rien.

    `journalise` ne doit jamais apparaitre dans un `if`, un `while` ou un test ternaire :
    le jour ou son resultat piloterait une branche, un bug de journal deviendrait un bug
    de bot.
    """
    arbre = ast.parse(BOT.read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if isinstance(n, (ast.If, ast.While, ast.IfExp)):
            for sous in ast.walk(n.test):
                if isinstance(sous, ast.Call) and getattr(sous.func, "id", None) == "journalise":
                    raise AssertionError(
                        "`journalise` sert de condition quelque part : ce journal doit "
                        "rester incapable de changer un comportement.")


def test_chaque_journalisation_porte_un_detail_qui_explique_le_choix():
    """`detail` est ce qui permettra de relire les desaccords sans rouvrir le code."""
    arbre = ast.parse(BOT.read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "journalise":
            noms = {k.arg for k in n.keywords}
            assert "detail" in noms, (
                f"un appel a `journalise` ligne {n.lineno} n'a pas de `detail` : on ne "
                f"pourra pas savoir QUELLE regle a decide, ni quel mot a mordu.")
