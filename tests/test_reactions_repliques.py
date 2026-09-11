# -*- coding: utf-8 -*-
"""Tests pour le LOT 1 — Enregistrement des réactions sur les répliques des bots."""

import ast
import re
import sqlite3
import pytest
from pathlib import Path

from shared import bot_logger, shared_database
from shared.bot_logger import enregistrer_reaction, reinitialiser_pour_tests


@pytest.fixture(autouse=True)
def _kill_existing_thread():
    reinitialiser_pour_tests()


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db_path = tmp_path / "bots_database.db"
    yield db_path
    reinitialiser_pour_tests()


def _get_reactions(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM reactions_repliques").fetchall()]
    finally:
        conn.close()


def test_1_schemas_reactions_repliques_egaux():
    """Le CREATE TABLE de bot_logger.py doit être STRICTEMENT identique à celui de shared_database.py."""
    def get_columns_from_ddl(ddl):
        conn = sqlite3.connect(":memory:")
        conn.execute(ddl)
        cursor = conn.execute("PRAGMA table_info(reactions_repliques)")
        return [(r[1], r[2], r[3], r[4], r[5]) for r in cursor.fetchall()]

    bot_logger_source = Path(bot_logger.__file__).read_text(encoding="utf-8")
    m1 = re.search(r'CREATE TABLE IF NOT EXISTS reactions_repliques\s*\([^;]+?\)', bot_logger_source, re.IGNORECASE | re.DOTALL)
    assert m1 is not None, "CREATE TABLE reactions_repliques introuvable dans bot_logger.py"
    logger_ddl = m1.group(0)

    db_source = Path(shared_database.__file__).read_text(encoding="utf-8")
    m2 = re.search(r'CREATE TABLE IF NOT EXISTS reactions_repliques\s*\([^;]+?\)', db_source, re.IGNORECASE | re.DOTALL)
    assert m2 is not None, "CREATE TABLE reactions_repliques introuvable dans shared_database.py"
    db_ddl = m2.group(0)

    cols1 = get_columns_from_ddl(logger_ddl)
    cols2 = get_columns_from_ddl(db_ddl)
    assert cols1 == cols2, f"Divergence de schéma : {cols1} != {cols2}"


def test_2_enregistrer_reaction_ecrit_en_base(test_db):
    """enregistrer_reaction empile et écrit correctement dans bots_database.db via le thread écrivain."""
    enregistrer_reaction(
        bot_name="alfred",
        message_id=123456789,
        channel_id=987654321,
        user_id=456789123,
        emoji="❤️",
        retiree=0
    )

    bot_logger._queue.join()
    reinitialiser_pour_tests()

    records = _get_reactions(test_db)
    assert len(records) == 1
    rec = records[0]
    assert rec["bot_name"] == "alfred"
    assert rec["message_id"] == 123456789
    assert rec["channel_id"] == 987654321
    assert rec["user_id"] == 456789123
    assert rec["emoji"] == "❤️"
    assert rec["retiree"] == 0
    assert rec["timestamp"] is not None


def test_3_les_6_bots_ecoutent_on_raw_reaction_add():
    """Les 6 bots doivent tous déclarer un gestionnaire on_raw_reaction_add.
    
    Verrou : si un seul bot l'oublie, ce test échoue (gotcha-un-bot-sur-six-manque-toujours).
    """
    racine = Path(__file__).resolve().parent.parent
    bots = [
        ("Alfred", racine / "Alfred" / "bot_alfred.py"),
        ("JohnnyBot", racine / "JohnnyBot" / "bot_johnny.py"),
        ("MaiqBot", racine / "MaiqBot" / "bot_maiq.py"),
        ("MalenaBot", racine / "MalenaBot" / "bot_malena.py"),
        ("Sheogorath", racine / "Sheogorath" / "bot_sheogorath.py"),
        ("SugarBot", racine / "SugarBot" / "bot_sugar.py"),
    ]

    for nom, chemin in bots:
        assert chemin.is_file(), f"Fichier {chemin} introuvable"
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        trouve = False
        for node in ast.walk(arbre):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_raw_reaction_add":
                trouve = True
                break
        assert trouve, f"Le bot {nom} ({chemin.name}) ne déclare pas on_raw_reaction_add !"


_BOTS = [
    ("Alfred", "Alfred/bot_alfred.py"),
    ("JohnnyBot", "JohnnyBot/bot_johnny.py"),
    ("MaiqBot", "MaiqBot/bot_maiq.py"),
    ("MalenaBot", "MalenaBot/bot_malena.py"),
    ("Sheogorath", "Sheogorath/bot_sheogorath.py"),
    ("SugarBot", "SugarBot/bot_sugar.py"),
]


def _handler_de(chemin):
    """Rend le noeud AST du on_raw_reaction_add REEL du bot, pas une copie."""
    arbre = ast.parse(Path(chemin).read_text(encoding="utf-8"), filename=str(chemin))
    for node in ast.walk(arbre):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "on_raw_reaction_add":
            return node
    return None


def _compare_a_bot_user_id(noeud):
    """Vrai si le sous-arbre compare quelque chose a `bot.user.id`."""
    for n in ast.walk(noeud):
        if not isinstance(n, ast.Compare):
            continue
        for cote in [n.left] + list(n.comparators):
            if (isinstance(cote, ast.Attribute) and cote.attr == "id"
                    and isinstance(cote.value, ast.Attribute) and cote.value.attr == "user"):
                return n
    return None


def test_4_ignorer_reaction_du_bot_lui_meme():
    """Verrou : chaque bot compare payload.user_id a bot.user.id et sort.

    Porte sur le CODE DU BOT via l'AST — surtout pas sur une copie de la logique
    retapee dans le test, qui se validerait toute seule.
    """
    racine = Path(__file__).resolve().parent.parent
    for nom, rel in _BOTS:
        h = _handler_de(racine / rel)
        assert h is not None, f"{nom} ne declare pas on_raw_reaction_add"
        trouve = False
        for n in ast.walk(h):
            if not isinstance(n, ast.Compare):
                continue
            cotes = [n.left] + list(n.comparators)
            gauche_payload = any(
                isinstance(c, ast.Attribute) and c.attr == "user_id"
                and isinstance(c.value, ast.Name) and c.value.id == "payload"
                for c in cotes
            )
            if gauche_payload and _compare_a_bot_user_id(n):
                trouve = True
                break
        assert trouve, (
            f"{nom} : on_raw_reaction_add ne compare pas payload.user_id a bot.user.id — "
            "le bot compterait ses propres reactions."
        )


def test_5_ignorer_reaction_sur_message_d_un_autre():
    """Verrou : chaque bot compare l'auteur du MESSAGE a bot.user.id, et sort si different.

    Mutation attendue rouge : retirer `if message_author_id != bot.user.id: return`
    d'UN SEUL bot.
    """
    racine = Path(__file__).resolve().parent.parent
    for nom, rel in _BOTS:
        h = _handler_de(racine / rel)
        assert h is not None, f"{nom} ne declare pas on_raw_reaction_add"
        trouve = False
        for n in ast.walk(h):
            if not isinstance(n, ast.If):
                continue
            # le corps du garde doit etre un `return` nu
            if not (len(n.body) == 1 and isinstance(n.body[0], ast.Return)
                    and n.body[0].value is None):
                continue
            test = n.test
            if not isinstance(test, ast.Compare):
                continue
            cotes = [test.left] + list(test.comparators)
            porte_sur_auteur = any(
                (isinstance(c, ast.Name) and c.id == "message_author_id")
                or (isinstance(c, ast.Attribute) and c.attr in ("author", "author_id"))
                for c in cotes
            )
            if porte_sur_auteur and _compare_a_bot_user_id(test):
                trouve = True
                break
        assert trouve, (
            f"{nom} : on_raw_reaction_add ne verifie pas que le message est DU BOT — "
            "il compterait les reactions posees sur les messages des autres."
        )


def test_6_enregistrer_quand_reaction_valide():
    """Verrou : chaque bot appelle enregistrer_reaction avec les 5 champs attendus."""
    racine = Path(__file__).resolve().parent.parent
    attendus = {"bot_name", "message_id", "channel_id", "user_id", "emoji"}
    for nom, rel in _BOTS:
        h = _handler_de(racine / rel)
        assert h is not None, f"{nom} ne declare pas on_raw_reaction_add"
        appel = None
        for n in ast.walk(h):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "enregistrer_reaction"):
                appel = n
                break
        assert appel is not None, (
            f"{nom} : on_raw_reaction_add n'appelle pas enregistrer_reaction — "
            "le gestionnaire est cable mais n'ecrit rien (gotcha-import-ajoute-mais-pas-cable)."
        )
        donnes = {kw.arg for kw in appel.keywords}
        manquants = attendus - donnes
        assert not manquants, f"{nom} : enregistrer_reaction sans {sorted(manquants)}"

        # Le nom du bot doit etre un litteral, pas une variable qui pourrait etre vide
        for kw in appel.keywords:
            if kw.arg == "bot_name":
                assert isinstance(kw.value, ast.Constant) and kw.value.value, (
                    f"{nom} : bot_name doit etre un litteral non vide"
                )


def test_7_helper_shared_database_get_reactions(test_db):
    """get_reactions_repliques de shared_database lit et filtre correctement."""
    shared_database.init_database()

    conn = shared_database.get_connection()
    conn.execute("""
        INSERT INTO reactions_repliques (timestamp, bot_name, message_id, channel_id, user_id, emoji, retiree)
        VALUES ('2026-09-11T12:00:00', 'alfred', 10, 20, 30, '👍', 0),
               ('2026-09-11T12:01:00', 'sheogorath', 11, 20, 31, '🧀', 0)
    """)
    conn.commit()
    conn.close()

    tous = shared_database.get_reactions_repliques()
    assert len(tous) == 2

    alfred_seul = shared_database.get_reactions_repliques(bot_name="alfred")
    assert len(alfred_seul) == 1
    assert alfred_seul[0]["emoji"] == "👍"

    sheo_seul = shared_database.get_reactions_repliques(bot_name="sheogorath")
    assert len(sheo_seul) == 1
    assert sheo_seul[0]["emoji"] == "🧀"
