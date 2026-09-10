import logging
import sqlite3
import pytest
import json
import re
from pathlib import Path
from shared.bot_logger import ErrorEventHandler, setup_logger, reinitialiser_pour_tests
from shared import bot_logger
from shared import shared_database

@pytest.fixture(autouse=True)
def _kill_existing_thread():
    reinitialiser_pour_tests()

@pytest.fixture
def error_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db_path = tmp_path / "bots_database.db"
    
    yield db_path
    
    reinitialiser_pour_tests()

def _get_records(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM error_events").fetchall()]
    finally:
        conn.close()

def test_1_une_ligne_ecrite_par_erreur(error_db):
    logger = logging.getLogger("test1")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    logger.addHandler(handler)
    
    logger.error("boum")
    
    bot_logger._queue.join()
    reinitialiser_pour_tests()
    records = _get_records(error_db)
    
    assert len(records) == 1
    assert records[0]["severity"] == "ERROR"
    assert records[0]["error_message"] == "boum"

def test_2_bot_name_est_celui_du_bot_pas_logger(error_db):
    logger = logging.getLogger("smart_router")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    logger.addHandler(handler)
    
    logger.error("test")
    
    bot_logger._queue.join()
    reinitialiser_pour_tests()
    records = _get_records(error_db)
    
    assert len(records) == 1
    assert records[0]["bot_name"] == "mon_bot"

def test_3_context_json_vaut_exactement_3_cles(error_db):
    logger = logging.getLogger("test3")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    logger.addHandler(handler)
    
    logger.error("test3")
    
    bot_logger._queue.join()
    reinitialiser_pour_tests()
    records = _get_records(error_db)
    
    assert len(records) == 1
    context = json.loads(records[0]["context_json"])
    assert set(context.keys()) == {"module", "funcName", "lineno"}

def test_4_exception_type_et_trace(error_db):
    logger = logging.getLogger("test4")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    logger.addHandler(handler)
    
    try:
        raise ValueError("test exception")
    except ValueError:
        logger.error("x", exc_info=True)
        
    bot_logger._queue.join()
    reinitialiser_pour_tests()
    records = _get_records(error_db)
    
    assert len(records) == 1
    assert records[0]["error_type"] == "ValueError"
    assert records[0]["error_traceback"] is not None
    assert "ValueError: test exception" in records[0]["error_traceback"]
    assert len(records[0]["error_traceback"]) <= 8000

def test_5_rien_en_dessous_de_error(error_db):
    logger = logging.getLogger("test5")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    handler.setLevel(logging.ERROR)
    logger.addHandler(handler)
    
    logger.warning("warn")
    logger.info("info")

    # ⚠️ `join()` AVANT la remise a zero : `reinitialiser_pour_tests` VIDE la file
    # sans l'ecrire. Sans ce `join`, une ligne empilee a tort serait jetee par le
    # nettoyage et le test passerait au vert en ne verrouillant rien.
    bot_logger._queue.join()
    reinitialiser_pour_tests()

    assert error_db.exists(), "le thread ecrivain n'a meme pas cree la base"
    assert _get_records(error_db) == []

def test_6_ordre_de_pose(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTS_LOG_CONSOLE_ONLY", "")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    
    logger = logging.getLogger("mon_bot_test6")
    smart_router = logging.getLogger("smart_router")
    # ⚠️ Ces deux loggers sont GLOBAUX au processus. Ce test leur pose la panoplie
    # complete (console + fichier + JSONL + erreurs) pointee sur un tmp_path qui
    # sera detruit : sans la remise en etat du `finally`, les tests suivants
    # ecriraient dans un dossier disparu.
    handlers_bot, handlers_sr = logger.handlers[:], smart_router.handlers[:]
    logger.handlers = []
    smart_router.handlers = []
    try:
        setup_logger("mon_bot_test6", log_dir=str(tmp_path / "logs"))
        poses = [h for h in smart_router.handlers if isinstance(h, ErrorEventHandler)]
        has_error_handler = bool(poses)
        # ⚠️ Le NIVEAU se verrouille ici, pas dans le test 5 : celui-la pose lui-meme
        # `setLevel(ERROR)` sur son handler, donc il verifie `logging`, pas notre
        # cablage. C'est `setup_logger` qui doit choisir ERROR.
        niveaux = [h.level for h in poses]
    finally:
        logger.handlers = handlers_bot
        smart_router.handlers = handlers_sr
        reinitialiser_pour_tests()

    assert has_error_handler, "ErrorEventHandler absent des handlers de smart_router"
    assert niveaux == [logging.ERROR], f"handler pose au niveau {niveaux}, attendu ERROR"

def test_7_emit_ne_leve_jamais(error_db, monkeypatch):
    logger = logging.getLogger("test7")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    logger.addHandler(handler)

    # ⚠️ Faire echouer le corps d'`emit` LUI-MEME. Pointer DATA_DIR sur un chemin
    # impossible ne testait rien : c'est le thread ecrivain qui echouait alors, pas
    # `emit`, qui se contente d'empiler. `logging.Handler.handle` ne rattrape rien —
    # sans le `try/except` d'`emit`, ceci remonterait dans l'appelant.
    def _boum(*a, **k):
        raise RuntimeError("json.dumps casse")
    monkeypatch.setattr(bot_logger.json, "dumps", _boum)

    logger.error("ne doit pas lever")

    logger.removeHandler(handler)

def test_7bis_exc_info_vide_ne_perd_pas_l_evenement(error_db):
    """`exc_info=True` HORS d'un `except` donne (None, None, None)."""
    logger = logging.getLogger("test7bis")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    logger.addHandler(handler)

    logger.error("sans exception en cours", exc_info=True)

    bot_logger._queue.join()
    reinitialiser_pour_tests()
    logger.removeHandler(handler)
    records = _get_records(error_db)

    # Sans la garde `record.exc_info[0]`, `None.__name__` leve, le `except` d'`emit`
    # avale l'evenement, et la ligne disparait en silence.
    assert len(records) == 1
    assert records[0]["error_type"] == "test_error_events_handler"
    assert records[0]["error_traceback"] is None

def test_8_schemas_egaux():
    def get_columns_from_ddl(ddl):
        conn = sqlite3.connect(":memory:")
        conn.execute(ddl)
        cursor = conn.execute("PRAGMA table_info(error_events)")
        # ⚠️ (nom, type) NE SUFFIT PAS : c'est ce que comparait la premiere version
        # de ce test, et elle laissait passer `error_message TEXT` face a
        # `error_message TEXT NOT NULL`, et `severity TEXT NOT NULL` face a
        # `severity TEXT DEFAULT 'ERROR'`. On compare aussi notnull, defaut et cle.
        return [(r[1], r[2], r[3], r[4], r[5]) for r in cursor.fetchall()]
        
    bot_logger_source = Path(bot_logger.__file__).read_text(encoding="utf-8")
    
    m1 = re.search(r'CREATE TABLE IF NOT EXISTS error_events\s*\([^;]+?\)', bot_logger_source, re.IGNORECASE | re.DOTALL)
    assert m1 is not None, "Could not find CREATE TABLE error_events in bot_logger.py"
    logger_ddl = m1.group(0)
    
    db_source = Path(shared_database.__file__).read_text(encoding="utf-8")
    m2 = re.search(r'CREATE TABLE IF NOT EXISTS error_events\s*\([^;]+?\)', db_source, re.IGNORECASE | re.DOTALL)
    assert m2 is not None, "Could not find CREATE TABLE error_events in shared_database.py"
    db_ddl = m2.group(0)
    
    cols1 = get_columns_from_ddl(logger_ddl)
    cols2 = get_columns_from_ddl(db_ddl)
    
    assert cols1 == cols2
