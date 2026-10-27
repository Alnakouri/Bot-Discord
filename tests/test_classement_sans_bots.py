# -*- coding: utf-8 -*-
"""Le classement de réputation ne compte plus les BOTS.

Mesuré en test live le 2026-09-07 : `/leaderboard` et `!equipage` listaient

    2. Sheogorath — 0 pts
    3. Onizuka    — 0 pts
    4. Johnny silverhand — 0 pts

« Onizuka » est SugarBot lui-même : la ligne date du 2026-06, avant le renommage, et
`users` fige le nom au jour de la première interaction. Trois fantômes à 0 point,
entrés en base avant que les six bots ne se taisent entre eux.

⚠️ On ne peut pas les reconnaître au NOM — il est périmé, et par construction. Le seul
qui sache qu'un bot est un bot, c'est le bot : il se déclare au démarrage.
"""
import ast
import os
import sys
import tempfile
from pathlib import Path

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import shared.shared_database as db

RACINE = Path(_parent_dir)
BOTS = {
    "Alfred/bot_alfred.py": "alfred",
    "JohnnyBot/bot_johnny.py": "johnny",
    "MaiqBot/bot_maiq.py": "maiq",
    "MalenaBot/bot_malena.py": "malena",
    "Sheogorath/bot_sheogorath.py": "sheogorath",
    "SugarBot/bot_sugar.py": "sugar",
}

HUMAIN = 551916719308943781        # identifiant fabrique (flocon plausible de 2019)
SUGAR = 1467929828060561583        # « Onizuka » en base : le meme compte, renomme


@pytest.fixture
def base(monkeypatch):
    """Une base neuve par test. ⚠️ `DB_PATH` est lu à l'import, pas à l'appel."""
    with tempfile.TemporaryDirectory() as dossier:
        monkeypatch.setattr(db, "DB_PATH", Path(dossier) / "test.db")
        db.init_database()
        yield


def _peupler(base_inutile=None):
    db.get_or_create_user(HUMAIN, "ledev", "LeDev")
    db.add_reputation(HUMAIN, 481)
    db.get_or_create_user(SUGAR, "Onizuka", "Onizuka")


def test_le_classement_montrait_bien_le_bot_avant_le_marquage(base):
    """La reproduction du défaut : sans marquage, le fantôme est là."""
    _peupler()
    noms = [e["username"] for e in db.get_reputation_leaderboard(10)]
    assert "Onizuka" in noms


def test_un_bot_marque_disparait_du_classement(base):
    _peupler()
    assert db.marquer_utilisateur_bot(SUGAR, "compte_bot_sugar", "Sugar bot") is True
    noms = [e["username"] for e in db.get_reputation_leaderboard(10)]
    assert noms == ["ledev"], f"le bot est encore classé : {noms}"


def test_le_marquage_rafraichit_le_nom_perime(base):
    """« Onizuka », « Rigurt le Hardi » : les noms datent de la première interaction."""
    _peupler()
    db.marquer_utilisateur_bot(SUGAR, "compte_bot_sugar", "Sugar bot")
    conn = db.get_connection()
    ligne = conn.execute("SELECT username, display_name FROM users WHERE user_id = ?",
                         (SUGAR,)).fetchone()
    conn.close()
    assert (ligne["username"], ligne["display_name"]) == ("compte_bot_sugar", "Sugar bot")


def test_le_marquage_ne_cree_personne(base):
    """Un bot jamais inscrit n'a pas à l'être ici : la fonction ne fait qu'UPDATE."""
    assert db.marquer_utilisateur_bot(999999999999999999, "fantome") is False
    conn = db.get_connection()
    reste = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    conn.close()
    assert reste == 0


def test_le_marquage_sans_nom_ne_l_efface_pas(base):
    """`COALESCE` : appeler sans nom marque le bot sans écraser ce qui est en base."""
    _peupler()
    db.marquer_utilisateur_bot(SUGAR)
    conn = db.get_connection()
    ligne = conn.execute("SELECT username, is_bot FROM users WHERE user_id = ?",
                         (SUGAR,)).fetchone()
    conn.close()
    assert ligne["username"] == "Onizuka" and ligne["is_bot"] == 1


def test_une_base_d_avant_la_migration_ne_vide_pas_le_classement(base):
    """⚠️ La garde qui compte le plus.

    Sur une base antérieure, `is_bot` peut valoir NULL — et `NULL = 0` ne vaut PAS
    « vrai » en SQL. Sans `COALESCE`, le classement serait entièrement VIDE : un filtre
    qui efface tout le monde est bien pire que le défaut qu'il corrige.
    """
    _peupler()
    db.marquer_utilisateur_bot(SUGAR)
    conn = db.get_connection()
    # L'etat exact d'une ligne jamais touchee par la migration.
    conn.execute("UPDATE users SET is_bot = NULL WHERE user_id = ?", (HUMAIN,))
    conn.commit()
    conn.close()
    noms = [e["username"] for e in db.get_reputation_leaderboard(10)]
    assert noms == ["ledev"], (
        f"classement {noms} : un `is_bot` NULL doit rester VISIBLE (COALESCE), "
        "et un bot marque doit disparaitre."
    )


def test_la_migration_est_rejouable(base):
    """`init_database` tourne à chaque démarrage des six bots."""
    db.init_database()
    db.init_database()
    conn = db.get_connection()
    colonnes = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
    conn.close()
    assert colonnes.count("is_bot") == 1


@pytest.mark.parametrize("chemin, bot_id", sorted(BOTS.items()))
def test_les_6_bots_se_declarent_au_demarrage(chemin, bot_id):
    """⚠️ « fait sur les 6 » l'est presque toujours sur 5 : on compte les six.

    Et on exige l'APPEL avec son argument : un import seul ne marque rien, et
    `/leaderboard` continuerait d'afficher le bot qui l'a oublié.
    """
    arbre = ast.parse((RACINE / chemin).read_text(encoding="utf-8"), filename=chemin)
    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "marquer_utilisateur_bot" and n.args
    ]
    assert appels, f"{chemin} ne se declare jamais comme bot au demarrage"
