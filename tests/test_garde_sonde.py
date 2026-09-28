# -*- coding: utf-8 -*-
"""Verrous SUITE 18 : le garde commun des sondes (`tools/garde_sonde.py`).

Mesure du 2026-09-28 : les sondes ont consomme 10 a 20 fois la prod, sur les cles des
bots (Sugar 943 appels de sonde / 42 de prod en 4 jours). Tout ici tourne sur une base
TEMPORAIRE : jamais `data/api_usage.db`.
"""
import ast
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "tools"))
import garde_sonde  # noqa: E402

MAINTENANT = datetime(2026, 9, 29, 14, 0, 0)  # UTC naif, comme api_tracking


def _base(tmp_path, lignes):
    """Base minimale : seules les colonnes lues par le garde. lignes = (bot, origine, code, age_min)."""
    chemin = tmp_path / "api_usage.db"
    con = sqlite3.connect(chemin)
    con.execute("CREATE TABLE api_calls (id INTEGER PRIMARY KEY, timestamp TEXT, bot_name TEXT, "
                "origine TEXT, error_code INTEGER)")
    for bot, origine, code, age in lignes:
        ts = (MAINTENANT - timedelta(minutes=age)).isoformat()
        con.execute("INSERT INTO api_calls (timestamp, bot_name, origine, error_code) VALUES (?,?,?,?)",
                    (ts, bot, origine, code))
    con.commit()
    con.close()
    return chemin


def test_un_bot_au_repos_passe(tmp_path):
    chemin = _base(tmp_path, [("sugar", "prod", None, 45), ("sugar", "sonde", None, 60)])
    ok, avis = garde_sonde.verifier("sugar", 36, chemin=chemin, maintenant=MAINTENANT)
    assert ok, avis
    assert "1+36/300" in avis


def test_un_bot_qui_sert_est_refuse(tmp_path):
    """Le cas du 28/09 au soir : Sugar en live, 1 vrai message il y a 5 min."""
    chemin = _base(tmp_path, [("sugar", "prod", None, 5)])
    ok, avis = garde_sonde.verifier("sugar", 36, chemin=chemin, maintenant=MAINTENANT)
    assert not ok
    assert "en conversation ou en live" in avis


def test_un_429_recent_est_refuse(tmp_path):
    chemin = _base(tmp_path, [("johnny", "sonde", 429, 10)])
    ok, avis = garde_sonde.verifier("johnny", 10, chemin=chemin, maintenant=MAINTENANT)
    assert not ok and "429" in avis


def test_un_429_ancien_ne_bloque_plus(tmp_path):
    chemin = _base(tmp_path, [("johnny", "sonde", 429, 20)])
    ok, _ = garde_sonde.verifier("johnny", 10, chemin=chemin, maintenant=MAINTENANT)
    assert ok


def test_le_budget_du_jour_est_tenu(tmp_path, monkeypatch):
    monkeypatch.setenv("SONDE_BUDGET_JOUR", "50")
    chemin = _base(tmp_path, [("maiq", "sonde", None, 60)] * 40)
    ok, avis = garde_sonde.verifier("maiq", 11, chemin=chemin, maintenant=MAINTENANT)
    assert not ok and "40 deja faits + 11" in avis
    ok, _ = garde_sonde.verifier("maiq", 10, chemin=chemin, maintenant=MAINTENANT)
    assert ok, "40 + 10 = 50 : pile le budget, doit passer"


def test_les_sondes_d_hier_ne_comptent_pas(tmp_path, monkeypatch):
    monkeypatch.setenv("SONDE_BUDGET_JOUR", "50")
    chemin = _base(tmp_path, [("maiq", "sonde", None, 15 * 60)] * 40)  # hier 23:00 UTC
    ok, avis = garde_sonde.verifier("maiq", 11, chemin=chemin, maintenant=MAINTENANT)
    assert ok, avis


def test_forcer_passe_mais_le_dit(tmp_path):
    chemin = _base(tmp_path, [("sugar", "prod", None, 5)])
    ok, avis = garde_sonde.verifier("sugar", 36, forcer=True, chemin=chemin, maintenant=MAINTENANT)
    assert ok and "FORCE" in avis


def test_les_autres_bots_ne_comptent_pas(tmp_path):
    chemin = _base(tmp_path, [("johnny", "prod", None, 5), ("johnny", "sonde", 429, 5)])
    ok, avis = garde_sonde.verifier("sugar", 36, chemin=chemin, maintenant=MAINTENANT)
    assert ok, avis


def test_sheogorath_est_cherche_sous_son_nom_en_base(tmp_path):
    chemin = _base(tmp_path, [("sheo", "prod", None, 5)])
    ok, _ = garde_sonde.verifier("sheogorath", 10, chemin=chemin, maintenant=MAINTENANT)
    assert not ok, "la sonde dit « sheogorath », api_calls dit « sheo »"


def test_sans_base_la_sonde_passe_en_le_disant(tmp_path):
    ok, avis = garde_sonde.verifier("sugar", 36, chemin=tmp_path / "absente.db")
    assert ok and "introuvable" in avis


def test_le_garde_n_ecrit_rien_dans_la_base(tmp_path):
    """Lecture seule : ni -wal, ni -shm, ni changement de mode (WAL interdit, AGENTS.md)."""
    chemin = _base(tmp_path, [("sugar", "prod", None, 5)])
    avant = chemin.read_bytes()
    garde_sonde.verifier("sugar", 36, chemin=chemin, maintenant=MAINTENANT)
    assert chemin.read_bytes() == avant
    assert not list(tmp_path.glob("*-wal")) and not list(tmp_path.glob("*-shm"))


@pytest.mark.parametrize("rel", ["tools/sonde_phrase_de_lien.py", "tools/sonde_ton_twitch.py"])
def test_les_deux_grosses_sondes_passent_par_le_garde(rel):
    """AST : `garde_sonde.verifier` est appele dans `main`, avec `forcer=args.forcer`."""
    arbre = ast.parse((RACINE / rel).read_text(encoding="utf-8"))
    main = next(n for n in ast.walk(arbre) if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")
    appels = [n for n in ast.walk(main) if isinstance(n, ast.Call)
              and getattr(n.func, "attr", None) == "verifier"
              and getattr(n.func.value, "id", None) == "garde_sonde"]
    assert appels, f"{rel} ne passe plus par le garde"
    assert any(kw.arg == "forcer" for kw in appels[0].keywords)


def test_relire_ne_passe_pas_par_le_garde():
    """`--relire` ne fait AUCUN appel API : il doit rendre la main avant le garde."""
    source = (RACINE / "tools/sonde_phrase_de_lien.py").read_text(encoding="utf-8")
    assert source.index("if args.relire:") < source.index("garde_sonde.verifier(")
