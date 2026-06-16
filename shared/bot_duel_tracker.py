# -*- coding: utf-8 -*-
"""
Anti-boucle duel tracker — Version SQLite (WAL-safe pour Docker multi-processus).
API publique identique pour ne pas casser les bots existants.
"""
import sqlite3
import time
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DUEL_DURATION = 120  # Secondes avant expiration d'un duel
DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
DB_PATH = os.path.join(DATA_DIR, "bots_database.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def _ensure_table():
    try:
        conn = _get_conn()
        conn.execute('''CREATE TABLE IF NOT EXISTS duel_state (
            channel_id INTEGER NOT NULL PRIMARY KEY,
            bot_a TEXT NOT NULL,
            bot_b TEXT NOT NULL,
            started_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )''')
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[DUEL] Table creation failed: {e}")

_ensure_table()

def cleanup_expired_duels():
    try:
        conn = _get_conn()
        now = time.time()
        conn.execute("DELETE FROM duel_state WHERE expires_at < ?", (now,))
        conn.commit()
        conn.close()
    except Exception:
        pass

def can_join_duel(channel_id, requesting_bot, opponent, priority=1) -> bool:
    """Vérifie si un bot peut participer à un duel dans ce canal."""
    try:
        if priority >= 10:  # PRIORITY_MENTION = 10
            return True
            
        conn = _get_conn()
        now = time.time()
        
        # Nettoyer les duels expirés
        conn.execute("DELETE FROM duel_state WHERE expires_at < ?", (now,))
        conn.commit()
        
        # Vérifier s'il y a un duel actif
        row = conn.execute(
            "SELECT bot_a, bot_b FROM duel_state WHERE channel_id = ?",
            (int(channel_id),)
        ).fetchone()
        
        if not row:
            conn.close()
            return True  # Pas de duel en cours
            
        bot_a, bot_b = row[0], row[1]
        
        # Le duel en cours implique-t-il ce bot ?
        if requesting_bot in (bot_a, bot_b):
            # Update expiry
            conn.execute("UPDATE duel_state SET expires_at = ? WHERE channel_id = ?", (now + DUEL_DURATION, int(channel_id)))
            conn.commit()
            conn.close()
            return True
        
        conn.close()
        logger.info(f"🚫 [DUEL BLOCKED] {requesting_bot} cannot disturb {bot_a} & {bot_b}")
        return False
        
    except Exception as e:
        logger.warning(f"[DUEL] can_join_duel error: {e}")
        return True  # En cas d'erreur, on autorise


def register_duel(channel_id, bot_a, bot_b, priority=1):
    """Enregistre un duel actif dans ce canal."""
    try:
        conn = _get_conn()
        now = time.time()
        conn.execute(
            "INSERT OR REPLACE INTO duel_state (channel_id, bot_a, bot_b, started_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (int(channel_id), bot_a, bot_b, now, now + DUEL_DURATION)
        )
        conn.commit()
        conn.close()
        logger.info(f"[DUEL] Registered: {bot_a} vs {bot_b} in channel {channel_id}")
    except Exception as e:
        logger.warning(f"[DUEL] register_duel error: {e}")

def get_duel_probability(bot_a, bot_b, base=0.05):
    """Fixed low probability for safety"""
    return 0.05
