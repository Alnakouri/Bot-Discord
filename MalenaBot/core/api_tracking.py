# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/api_tracking.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

import os
import queue
import sqlite3
import threading
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("api_tracking")

_queue = queue.Queue(maxsize=1000)
_writer_thread = None
_lock = threading.Lock()

_JOURNAL_FILE_PLEINE = False
_JOURNAL_ECRITURE = False
_JOURNAL_CONNEXION = False
_ECRIVAIN_HS = False

def _get_connection():
    data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "api_usage.db")
    
    conn = sqlite3.connect(db_path, timeout=20)
    
    try:
        mode = conn.execute("PRAGMA journal_mode=TRUNCATE;").fetchone()
        if mode and mode[0].lower() != "truncate":
            logger.warning(f"Impossible de passer en mode TRUNCATE, mode actuel : {mode[0]}")
    except Exception as e:
        logger.warning(f"Erreur lors du paramétrage de journal_mode: {e}")
        
    try:
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception as e:
        logger.warning(f"Erreur lors du paramétrage de synchronous: {e}")

    # Déplacé depuis _init_usage_db
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_calls (
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
            tokens_used INTEGER
        )
    """)
    
    # Temps REELLEMENT percu par l'utilisateur : message recu -> reponse postee.
    # `api_calls.latency_ms` ne mesure qu'un appel de modele ; il ne dit rien de la somme
    # des echelons rates, ni du montage du prompt, ni de l'envoi.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reponses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            bot_name TEXT NOT NULL,
            total_ms REAL NOT NULL,
            llm_ms REAL,
            envoye INTEGER NOT NULL,
            canal TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_key_status (
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
    
    # Ajout colonne 'raison'
    try:
        conn.execute("ALTER TABLE api_calls ADD COLUMN raison TEXT;")
    except sqlite3.OperationalError:
        pass  # la colonne existe deja (migration deja passee)
        
    conn.commit()
    return conn

def _writer_loop():
    global _JOURNAL_ECRITURE, _JOURNAL_CONNEXION, _ECRIVAIN_HS
    conn = None
    try:
        conn = _get_connection()
    except Exception as e:
        if not _JOURNAL_CONNEXION:
            logger.warning(f"[API TRACKING] Erreur connexion SQLite, abandon : {e}")
            _JOURNAL_CONNEXION = True
        _ECRIVAIN_HS = True
        return

    try:
        while True:
            task = _queue.get()
            try:
                if task is None: # poison pill
                    break
                    
                type_tache = task.get("type")
                
                try:
                    if type_tache == "appel":
                        conn.execute("""
                            INSERT INTO api_calls 
                            (timestamp, bot_name, api_name, model, key_index, success, error_code, latency_ms, raison)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            task["timestamp"], task["bot_name"], task["api_name"], task["model"],
                            task["key_index"], task["success"], task["error_code"], task["latency_ms"], task["raison"]
                        ))
                    elif type_tache == "reponse":
                        conn.execute("""
                            INSERT INTO reponses
                            (timestamp, bot_name, total_ms, llm_ms, envoye, canal)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            task["timestamp"], task["bot_name"], task["total_ms"],
                            task["llm_ms"], task["envoye"], task["canal"]
                        ))
                    elif type_tache == "etat_cle":
                        conn.execute("""
                            INSERT INTO api_key_status (api_name, key_index, valid, cooldown_until, last_error, last_used)
                            VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(api_name, key_index) DO UPDATE SET
                                valid=excluded.valid,
                                cooldown_until=excluded.cooldown_until,
                                last_error=excluded.last_error,
                                last_used=excluded.last_used,
                                total_errors=total_errors + CASE WHEN excluded.valid = 0 THEN 1 ELSE 0 END
                        """, (
                            task["api_name"], task["key_index"], task["valid"], task["cooldown_iso"],
                            task["erreur"], datetime.now().isoformat()
                        ))
                    conn.commit()
                except Exception as e:
                    if not _JOURNAL_ECRITURE:
                        logger.warning(f"[API TRACKING] Erreur d'écriture SQLite : {e}")
                        _JOURNAL_ECRITURE = True
            finally:
                _queue.task_done()
    finally:
        if conn:
            conn.close()

def _ensure_thread():
    global _writer_thread
    with _lock:
        if _ECRIVAIN_HS:
            return
        if _writer_thread is None or not _writer_thread.is_alive():
            _writer_thread = threading.Thread(target=_writer_loop, daemon=True)
            _writer_thread.start()

def _empiler(tache):
    global _JOURNAL_FILE_PLEINE
    try:
        _queue.put_nowait(tache)
    except queue.Full:
        if not _JOURNAL_FILE_PLEINE:
            logger.warning("La file de tracking API est pleine, pertes d'évènements à prévoir.")
            _JOURNAL_FILE_PLEINE = True

def tracer_appel(bot, api, modele, index_cle, succes, code_erreur=None, latence_ms=None, raison=None):
    if _ECRIVAIN_HS:
        return
    _ensure_thread()
    tache = {
        "type": "appel",
        "timestamp": datetime.now().isoformat(),
        "bot_name": bot,
        "api_name": api,
        "model": modele,
        "key_index": index_cle,
        "success": 1 if succes else 0,
        "error_code": code_erreur,
        "latency_ms": latence_ms,
        "raison": raison
    }
    _empiler(tache)

def tracer_reponse(bot, total_ms, llm_ms=None, envoye=True, canal=None):
    """Enregistre le temps percu d'une reponse. Meme ecrivain unique hors boucle.

    ⚠️ Surtout PAS une deuxieme connexion SQLite depuis `on_message` : 6 conteneurs sur un
    bind mount Windows, c'est le montage exact du `disk I/O error` de la memoire.
    """
    if _ECRIVAIN_HS:
        return
    _ensure_thread()
    _empiler({
        "type": "reponse",
        "timestamp": datetime.now().isoformat(),
        "bot_name": bot,
        "total_ms": total_ms,
        "llm_ms": llm_ms,
        "envoye": 1 if envoye else 0,
        "canal": canal,
    })


def tracer_etat_cle(api, index_cle, valide, cooldown_iso, erreur):
    if _ECRIVAIN_HS:
        return
    _ensure_thread()
    tache = {
        "type": "etat_cle",
        "api_name": api,
        "key_index": index_cle,
        "valid": 1 if valide else 0,
        "cooldown_iso": cooldown_iso,
        "erreur": str(erreur) if erreur else None
    }
    _empiler(tache)

def reinitialiser_pour_tests():
    global _writer_thread, _JOURNAL_FILE_PLEINE, _JOURNAL_ECRITURE, _JOURNAL_CONNEXION, _ECRIVAIN_HS
    # Vider AVANT de poser la pilule : sur une file pleine (test H.5) un
    # put_nowait lèverait queue.Full et l'écrivain ne s'arrêterait jamais.
    while not _queue.empty():
        try:
            _queue.get_nowait()
            _queue.task_done()
        except queue.Empty:
            break
    if _writer_thread and _writer_thread.is_alive():
        try:
            _queue.put_nowait(None)
            _writer_thread.join(timeout=5.0)
        except queue.Full:
            pass  # la file est pleine a l'arret : l'ecrivain se termine de toute facon
    _writer_thread = None
    _JOURNAL_FILE_PLEINE = False
    _JOURNAL_ECRITURE = False
    _JOURNAL_CONNEXION = False
    _ECRIVAIN_HS = False
