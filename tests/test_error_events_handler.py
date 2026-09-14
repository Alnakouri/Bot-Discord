import ast
import logging
import sqlite3
import threading
import pytest
import json
import re
from pathlib import Path
from types import SimpleNamespace
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
    # `bot_logger` fait partie des shared_name depuis le lot « la panne doit
    # CRIER » : il recoit donc lui aussi la panoplie pointee sur ce tmp_path.
    journal = logging.getLogger("bot_logger")
    # ⚠️ Ces deux loggers sont GLOBAUX au processus. Ce test leur pose la panoplie
    # complete (console + fichier + JSONL + erreurs) pointee sur un tmp_path qui
    # sera detruit : sans la remise en etat du `finally`, les tests suivants
    # ecriraient dans un dossier disparu.
    handlers_bot, handlers_sr = logger.handlers[:], smart_router.handlers[:]
    handlers_journal = journal.handlers[:]
    logger.handlers = []
    smart_router.handlers = []
    journal.handlers = []
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
        journal.handlers = handlers_journal
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


# ---------------------------------------------------------------------------
# Lot « la panne doit CRIER » : une base morte doit laisser une trace PERIODIQUE,
# et ne pas faire relancer un thread ecrivain par evenement recu.
# ---------------------------------------------------------------------------

class _ConnexionQuiRefuseLesEcritures:
    """Base joignable — les CREATE TABLE passent — mais toute ecriture echoue.

    C'est la forme exacte de la panne du 11-13/09 : `unable to open database
    file` a l'INSERT, pas au `connect`.
    """

    def __init__(self, horloge, pas):
        self.horloge = horloge
        self.pas = pas
        # Point de rendez-vous : `rollback` est appele APRES `_crier_panne`.
        # `_queue.join()` ne suffit PAS — `task_done()` a lieu dans le `finally`
        # interne, donc AVANT que le `except` n'ait crie.
        self.tour_fini = threading.Semaphore(0)

    def execute(self, sql, *args):
        if sql.lstrip().upper().startswith("INSERT"):
            # Le temps avance AVEC les echecs : la temporisation du module
            # devient observable sans jamais dormir.
            self.horloge[0] += self.pas
            raise sqlite3.OperationalError("unable to open database file")
        return None

    def commit(self):
        return None

    def rollback(self):
        self.tour_fini.release()

    def close(self):
        return None


def test_9_la_panne_crie_plusieurs_fois_et_compte_les_perdus(tmp_path, monkeypatch, caplog):
    """Une panne qui dure laisse PLUSIEURS lignes, et la 2e porte le compte.

    Le verrou porte sur le comptage et la temporisation REELS du module : le
    test n'avance qu'une horloge, il ne retape aucune regle d'espacement.
    """
    horloge = [0.0]
    conn = _ConnexionQuiRefuseLesEcritures(horloge, bot_logger._INTERVALLE_CRI / 2)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(bot_logger, "_maintenant", lambda: horloge[0])
    monkeypatch.setattr(bot_logger, "sqlite3",
                        SimpleNamespace(connect=lambda *a, **k: conn))

    logger = logging.getLogger("test9")
    logger.setLevel(logging.DEBUG)
    handler = ErrorEventHandler("mon_bot")
    logger.addHandler(handler)
    try:
        with caplog.at_level(logging.ERROR, logger="bot_logger"):
            for i in range(3):
                logger.error(f"boum {i}")
                assert conn.tour_fini.acquire(timeout=5.0), \
                    f"le thread ecrivain n'a pas traite l'echec {i}"
    finally:
        logger.removeHandler(handler)
        reinitialiser_pour_tests()

    cris = [r.getMessage() for r in caplog.records if r.name == "bot_logger"]

    # 3 echecs espaces d'un demi-intervalle : cri au 1er, silence au 2e, cri au
    # 3e. Avec l'ancien verrou definitif, il n'y en avait qu'UN, pour TOUTE la
    # duree de la panne.
    assert len(cris) == 2, f"{len(cris)} ligne(s) pour une panne qui dure : {cris}"
    assert "2 événements perdus" in cris[1], cris[1]
    assert "depuis 5 min" in cris[1], cris[1]


def test_10_base_morte_ne_relance_pas_un_thread_par_evenement(tmp_path, monkeypatch):
    """Init impossible : UN thread, pas un par reaction recue — et la relance
    reste possible passe le delai."""
    horloge = [0.0]
    idents = []

    def _connexion_impossible(*a, **k):
        idents.append(threading.get_ident())
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(bot_logger, "_maintenant", lambda: horloge[0])
    monkeypatch.setattr(bot_logger, "sqlite3",
                        SimpleNamespace(connect=_connexion_impossible))

    def _reaction_puis_attendre_la_mort_du_thread():
        bot_logger.enregistrer_reaction("mon_bot", 1, 2, 3, "OK")
        t = bot_logger._writer_thread
        if t is not None:
            t.join(timeout=5.0)
            assert not t.is_alive(), "le thread ecrivain aurait du mourir sur l'init"

    try:
        for _ in range(5):
            _reaction_puis_attendre_la_mort_du_thread()
        pendant_le_delai = len(idents)

        # ⚠️ La relance n'est pas supprimee, elle est ESPACEE : c'est elle qui
        # fait repartir le journal tout seul quand la base redevient saine.
        horloge[0] += bot_logger._DELAI_REPRISE
        _reaction_puis_attendre_la_mort_du_thread()
        apres_le_delai = len(idents)
    finally:
        reinitialiser_pour_tests()

    assert pendant_le_delai == 1, f"{pendant_le_delai} threads lances pour une base morte"
    assert apres_le_delai == 2, "passe le delai, le thread doit pouvoir repartir"


def test_11_le_logger_bot_logger_est_cable():
    """Sans ce cablage, le cri de la panne n'atteint ni logs/ ni le JSONL du
    tableau de bord : il ne survit que par le `lastResort` de logging, sur
    stderr. C'est la raison technique des 0 `[ERROR EVENTS]` du 11-13/09.

    Verrou par `ast` sur le fichier REEL — jamais une regex, jamais une copie
    de la liste ici.
    """
    arbre = ast.parse(Path(bot_logger.__file__).read_text(encoding="utf-8"))
    setup = next(n for n in ast.walk(arbre)
                 if isinstance(n, ast.FunctionDef) and n.name == "setup_logger")

    noms = set()
    for noeud in ast.walk(setup):
        if (isinstance(noeud, ast.For)
                and isinstance(noeud.target, ast.Name)
                and noeud.target.id == "shared_name"):
            noms = {e.value for e in ast.walk(noeud.iter)
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}

    assert noms, "boucle `for shared_name in (...)` introuvable dans setup_logger"
    assert "bot_logger" in noms, f"`bot_logger` absent des shared_name : {sorted(noms)}"
