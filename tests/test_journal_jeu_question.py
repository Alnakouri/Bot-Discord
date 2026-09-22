# -*- coding: utf-8 -*-
"""`detect_game_question` est RANGEE dans le journal — sans changer une decision.

Pourquoi elle, et pourquoi maintenant : les trois decisions deja instrumentees
(intention, ton, pertinence) ont produit **30 lignes en deux jours**, dont ZERO pour
`intention`. Un corpus ne se construit pas a ce rythme. `detect_game_question` tourne
sur le chat Twitch et se declenche cent fois plus souvent.

⚠️ Ce lot ne branche PAS Laya. Il n'en est que le prealable : sans corpus, on ne sait
pas a quelle frequence les 66 motifs regex de `shared/twitch/game_info.py` se trompent,
et « Laya ferait mieux » reste une opinion.
"""
import ast
import types
from pathlib import Path
from unittest.mock import patch

from shared.journal_decisions import DECISIONS, JEU_QUESTION
from shared.twitch.dispatch import DispatchMixin

DISPATCH = Path(__file__).resolve().parent.parent / "shared" / "twitch" / "dispatch.py"


def _faux_bot(bot_id="sugar"):
    class Faux(DispatchMixin):
        pass
    f = Faux()
    f.bot_id = bot_id
    f.logger = types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None,
                                     warning=lambda *a, **k: None, error=lambda *a, **k: None)
    return f


def test_l_etiquette_est_acceptee_par_le_journal():
    assert JEU_QUESTION in DECISIONS, (
        "`journalise` leve sur une decision inconnue : sans cette entree, chaque message "
        "du chat produirait une exception au lieu d'une ligne de journal.")


def test_la_decision_n_est_PAS_changee():
    """Le lot observe, il ne decide pas. La categorie rendue est celle de la regex."""
    f = _faux_bot()
    with patch("shared.twitch.game_info.detect_game_question", return_value="platform") as d:
        with patch("shared.journal_decisions.journalise"):
            assert f._question_de_jeu("c'est sur quelle plateforme ?", "mention") == "platform"
    d.assert_called_once_with("c'est sur quelle plateforme ?")


def test_le_cas_AUCUNE_est_journalise_lui_aussi():
    """C'est le cas le plus important : un journal qui ne garde que les detections ne
    peut jamais montrer les questions que les 66 motifs ont RATEES."""
    f = _faux_bot("maiq")
    with patch("shared.twitch.game_info.detect_game_question", return_value=None):
        with patch("shared.journal_decisions.journalise") as j:
            assert f._question_de_jeu("c'est quoi ce truc qu'il joue", "cohost") is None
    j.assert_called_once()
    args, kwargs = j.call_args
    assert args[0] == "maiq"
    assert args[1] == JEU_QUESTION
    assert args[3] == "aucune", "un None doit etre range sous `aucune`, pas jete"
    assert "cohost" in kwargs.get("detail", ""), "la voie doit etre tracee"


def test_un_journal_casse_ne_coute_pas_une_reponse():
    f = _faux_bot()
    with patch("shared.twitch.game_info.detect_game_question", return_value="genre"):
        with patch("shared.journal_decisions.journalise", side_effect=RuntimeError("base morte")):
            assert f._question_de_jeu("c'est un rpg ?", "mention") == "genre"


def test_plus_aucun_appel_NU_a_detect_game_question():
    """Sans ce verrou, un futur appel direct rouvrirait un trou dans le corpus en
    silence — le bot repondrait bien, et la ligne manquerait sans que rien n'alerte.
    """
    arbre = ast.parse(DISPATCH.read_text(encoding="utf-8"))
    dedans = {n.name for n in ast.walk(arbre)
              if isinstance(n, ast.FunctionDef) and n.name == "_question_de_jeu"}
    assert dedans, "_question_de_jeu a disparu"
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.FunctionDef) and noeud.name != "_question_de_jeu":
            appels = [n for n in ast.walk(noeud) if isinstance(n, ast.Call)
                      and getattr(n.func, "id", None) == "detect_game_question"]
            assert not appels, (
                f"`{noeud.name}` appelle detect_game_question directement : sa decision "
                f"echapperait au journal. Passer par `self._question_de_jeu`.")


def test_observer_ne_fait_JAMAIS_parler_le_bot():
    """La garantie demandee par Ahmed le 22/09 : « le bot ne posera pas de question aux
    gens ? » — non, jamais, et voici le verrou plutot que la parole donnee.

    `_question_de_jeu` lit un texte, range une ligne, rend une valeur. Elle n'envoie
    rien, ne genere rien, n'appelle aucun modele. Le jour ou quelqu'un y glisserait un
    envoi, ce test tombe.
    """
    arbre = ast.parse(DISPATCH.read_text(encoding="utf-8"))
    fonction = next(n for n in ast.walk(arbre)
                    if isinstance(n, ast.FunctionDef) and n.name == "_question_de_jeu")
    interdits = {"send_chat_safe", "_generate_response", "_fetch_game_facts_block",
                 "_generate_link_line", "generate_response", "_fiche_du_jeu"}
    for n in ast.walk(fonction):
        if isinstance(n, ast.Call):
            nom = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            assert nom not in interdits, (
                f"`_question_de_jeu` appelle `{nom}` : elle OBSERVE, elle ne parle pas. "
                f"Le journal a ete construit pour ne jamais changer un comportement.")


def test_la_REPONSE_reste_conditionnee_a_game_qa():
    """Observer ne doit pas allumer la fonctionnalite.

    ⚠️ C'est le defaut trouve le 22/09 : la detection etait SOUS `enable_game_qa`, qui
    est a False chez les sept bots — le journal ne pouvait donc rien enregistrer, et le
    cocher pour observer aurait mis les bots a repondre aux questions sur le jeu.
    Les deux sont maintenant separes, et ce test verifie que la separation tient DANS LES
    DEUX SENS : la detection hors du garde, l'appel aux faits IGDB dedans.
    """
    src = DISPATCH.read_text(encoding="utf-8")
    arbre = ast.parse(src)
    lignes_fetch, lignes_garde = [], []
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "_fetch_game_facts_block":
            lignes_fetch.append(n.lineno)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "getattr":
            if len(n.args) >= 2 and getattr(n.args[1], "value", None) == "enable_game_qa":
                lignes_garde.append(n.lineno)
    assert lignes_fetch, "plus aucun appel aux faits du jeu : la fonctionnalite a disparu"
    assert lignes_garde, "`enable_game_qa` ne garde plus rien"
    # Chaque appel aux faits IGDB doit avoir un garde `enable_game_qa` au-dessus de lui.
    for ligne in lignes_fetch:
        assert any(g <= ligne for g in lignes_garde), (
            f"l'appel aux faits du jeu ligne {ligne} n'est plus garde par `enable_game_qa` : "
            f"journaliser allumerait la fonctionnalite chez les six bots.")


def test_les_messages_PASSIFS_sont_ranges_eux_aussi():
    """C'est eux, le corpus. Les mentions sont une poignee ; le chat, c'est le reste.

    Sans cette voie, le journal se remplirait au rythme des trois decisions d'avant —
    30 lignes en deux jours — et ne trancherait jamais rien sur Laya.
    """
    arbre = ast.parse(DISPATCH.read_text(encoding="utf-8"))
    voies = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "_question_de_jeu":
            for a in n.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    voies.add(a.value)
    assert "passif" in voies, (
        f"la voie `passif` a disparu : seules {sorted(voies)} restent, et le corpus "
        f"ne se remplira plus qu'au compte-gouttes.")
    assert "mention" in voies
