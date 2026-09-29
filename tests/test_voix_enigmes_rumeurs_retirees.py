# -*- coding: utf-8 -*-
"""Verrous SUITE 17 : Sheogorath ne parle plus en vocal, M'aiq ne pose plus d'enigme
et ne publie plus de rumeur.

Decision d'Ahmed du 2026-09-28. La voix de Sheogorath appelait un serveur Piper qui
ne tourne plus nulle part (`docker-compose.yml` l'a retire), tout en journalisant
« Système TTS Piper activé » a chaque demarrage. Les enigmes dataient du 06/09 pour la
derniere, et la rumeur du jour visait toujours le meme et seul humain du serveur.

Ce qui RESTE et doit rester : la patrouille vocale d'Alfred (verrouillee dans
`test_alfred_allege.py`), l'ecoute du stream de Sheogorath (`enable_voice_listen`), et
le trait « menteur » de M'aiq en conversation (sa fiche de persona n'est pas touchee).
"""
import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SHEO = RACINE / "Sheogorath" / "bot_sheogorath.py"
MAIQ = RACINE / "MaiqBot" / "bot_maiq.py"


def _arbre(chemin):
    return ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))


def _commandes_prefixe(arbre):
    """Noms ET alias des commandes `@bot.command(...)`."""
    noms = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            appel = deco if isinstance(deco, ast.Call) else None
            cible = appel.func if appel else deco
            if not (isinstance(cible, ast.Attribute) and cible.attr == "command"):
                continue
            nom = noeud.name
            for kw in (appel.keywords if appel else []):
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    nom = kw.value.value
                if kw.arg == "aliases" and isinstance(kw.value, (ast.List, ast.Tuple)):
                    noms.update(e.value for e in kw.value.elts if isinstance(e, ast.Constant))
            noms.add(nom)
    return noms


def _fonctions(arbre):
    return {n.name for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _noms_lus(arbre):
    return {n.id for n in ast.walk(arbre) if isinstance(n, ast.Name)}


def _modules_importes(arbre):
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name
        elif isinstance(n, ast.ImportFrom) and n.module:
            yield n.module


# ─────────────────────────────── Sheogorath ───────────────────────────────

def test_sheogorath_n_a_plus_de_commande_vocale_ni_de_soluce():
    commandes = _commandes_prefixe(_arbre(SHEO))
    for nom in ("rejoins", "join", "vocal", "quitte", "leave", "degage",
                "voix", "speak", "dis", "solution", "soluce"):
        assert nom not in commandes, f"!{nom} existe encore chez Sheogorath"


def test_sheogorath_n_importe_plus_sheo_voice():
    arbre = _arbre(SHEO)
    assert "sheo_voice" not in set(_modules_importes(arbre))
    assert "VOICE_AVAILABLE" not in _noms_lus(arbre)
    assert "voice_idle_check" not in _fonctions(arbre)
    assert not (RACINE / "Sheogorath" / "sheo_voice.py").exists()


def test_sheogorath_ne_lit_plus_les_enigmes_de_maiq():
    noms = _noms_lus(_arbre(SHEO))
    for nom in ("get_maiq_riddle", "delete_maiq_riddle", "get_active_riddle", "delete_active_riddle"):
        assert nom not in noms, nom


def test_les_minigames_de_sheogorath_ne_gardent_que_le_fromage():
    """2026-09-29 : le code d'enigme mort de `Sheogorath/minigames.py` est retire. Il
    ecrivait dans la table partagee `riddles` et ne servait qu'aux enigmes de M'aiq."""
    arbre = _arbre(RACINE / "Sheogorath" / "minigames.py")
    assert _fonctions(arbre) == {"jeu_fromage"}
    assert "shared.shared_database" not in set(_modules_importes(arbre))
    assert "ENIGMES" not in {
        t.id for n in ast.walk(arbre) if isinstance(n, ast.Assign) for t in n.targets
        if isinstance(t, ast.Name)
    }


def test_sheogorath_garde_ses_autres_commandes():
    commandes = _commandes_prefixe(_arbre(SHEO))
    for nom in ("decret", "fromage", "wabbajack", "quete", "imposteur", "oubliemoi"):
        assert nom in commandes, f"!{nom} a disparu de Sheogorath"


# ─────────────────────────────────── M'aiq ───────────────────────────────────

def test_maiq_n_a_plus_d_enigme_ni_de_rumeur():
    commandes = _commandes_prefixe(_arbre(MAIQ))
    for nom in ("enigme", "reponse", "indice", "rumeur"):
        assert nom not in commandes, f"!{nom} existe encore chez M'aiq"


def test_maiq_n_a_plus_les_boucles_ni_le_rattrapage():
    fonctions = _fonctions(_arbre(MAIQ))
    for nom in ("daily_rumor_check", "publish_daily_rumor", "riddle_passive_hint_loop",
                "check_missed_riddle_answers", "generate_and_post_riddle", "close_riddle_cleanup"):
        assert nom not in fonctions, nom


def test_maiq_ne_touche_plus_a_la_table_des_enigmes():
    noms = _noms_lus(_arbre(MAIQ))
    for nom in ("get_active_riddle", "get_all_active_riddles", "add_riddle_winner",
                "add_riddle_streak", "reset_riddle_streak", "recent_rumor_targets"):
        assert nom not in noms, nom
    assert "minigames" not in set(_modules_importes(_arbre(MAIQ)))
    assert not (RACINE / "MaiqBot" / "minigames.py").exists()


def test_maiq_garde_ses_autres_commandes():
    commandes = _commandes_prefixe(_arbre(MAIQ))
    for nom in ("profil", "maiq", "oubliemoi"):
        assert nom in commandes, f"!{nom} a disparu de M'aiq"
