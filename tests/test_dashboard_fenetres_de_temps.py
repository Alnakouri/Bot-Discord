# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.backend.api_tracker import APITracker

_RACINE = Path(__file__).resolve().parent.parent


def _creer_base_temp(chemin_db):
    conn = sqlite3.connect(chemin_db)
    conn.execute("""
        CREATE TABLE api_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            bot_name TEXT NOT NULL,
            api_name TEXT NOT NULL,
            key_index INTEGER,
            success INTEGER NOT NULL,
            error_code INTEGER,
            error_message TEXT,
            latency_ms REAL,
            model TEXT,
            tokens_used INTEGER,
            raison TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE api_key_status (
            api_name TEXT NOT NULL,
            key_index INTEGER NOT NULL,
            valid INTEGER DEFAULT 1,
            cooldown_until TEXT,
            total_calls INTEGER DEFAULT 0,
            total_errors INTEGER DEFAULT 0,
            last_error TEXT,
            last_used TEXT,
            PRIMARY KEY (api_name, key_index)
        )
    """)
    conn.commit()
    return conn


def test_fenetre_1h_ne_prend_que_les_appels_recents(tmp_path):
    db_file = tmp_path / "api_usage.db"
    conn = _creer_base_temp(db_file)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    t_30m = (now_utc - timedelta(minutes=30)).isoformat()
    t_3h = (now_utc - timedelta(hours=3)).isoformat()

    conn.execute(
        "INSERT INTO api_calls (timestamp, bot_name, api_name, success) VALUES (?, 'alfred', 'gemini', 1)",
        (t_30m,)
    )
    conn.execute(
        "INSERT INTO api_calls (timestamp, bot_name, api_name, success) VALUES (?, 'alfred', 'gemini', 1)",
        (t_3h,)
    )
    conn.commit()
    conn.close()

    tracker = APITracker(str(db_file))
    usage = tracker.get_usage(1)
    assert usage["total_calls"] == 1


def test_fenetre_24h_ne_prend_que_les_appels_recents(tmp_path):
    db_file = tmp_path / "api_usage.db"
    conn = _creer_base_temp(db_file)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    t_20h = (now_utc - timedelta(hours=20)).isoformat()
    t_30h = (now_utc - timedelta(hours=30)).isoformat()

    conn.execute(
        "INSERT INTO api_calls (timestamp, bot_name, api_name, success) VALUES (?, 'alfred', 'gemini', 1)",
        (t_20h,)
    )
    conn.execute(
        "INSERT INTO api_calls (timestamp, bot_name, api_name, success) VALUES (?, 'alfred', 'gemini', 1)",
        (t_30h,)
    )
    conn.commit()
    conn.close()

    tracker = APITracker(str(db_file))
    usage = tracker.get_usage(24)
    assert usage["total_calls"] == 1


def test_cooldown_until_utc_rend_status_cooldown(tmp_path):
    db_file = tmp_path / "api_usage.db"
    conn = _creer_base_temp(db_file)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    t_cooldown = (now_utc + timedelta(minutes=10)).isoformat()

    conn.execute(
        "INSERT INTO api_key_status (api_name, key_index, valid, cooldown_until) VALUES ('gemini', 0, 1, ?)",
        (t_cooldown,)
    )
    conn.commit()
    conn.close()

    tracker = APITracker(str(db_file))
    keys = tracker.get_keys_status()
    assert len(keys) == 1
    assert keys[0]["status"] == "cooldown"


def test_ast_aucune_occurrence_interdite():
    # 1. Aucune occurrence de datetime('now' dans dashboard/backend/*.py
    backend_dir = _RACINE / "dashboard" / "backend"
    for py_file in backend_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "datetime('now'" not in content, (
            f"{py_file.name} contient datetime('now' — utiliser strftime('%Y-%m-%dT%H:%M:%S', 'now', ...)"
        )

    # 2. Aucun datetime.now().isoformat() dans shared/api_tracking.py ni shared/journal_decisions.py
    for module_name in ("api_tracking.py", "journal_decisions.py"):
        f = _RACINE / "shared" / module_name
        content = f.read_text(encoding="utf-8")
        assert "datetime.now().isoformat()" not in content, (
            f"shared/{module_name} utilise datetime.now().isoformat() au lieu d'écrire en UTC"
        )
