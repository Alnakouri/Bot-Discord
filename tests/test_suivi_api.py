import pytest
import asyncio
import threading
import sqlite3
import os
import ast
from pathlib import Path
from unittest.mock import MagicMock, patch
import time
from shared import api_tracking
from shared.llm_cascade import generate_response
from shared.smart_router import RequestType

# H.7 : réutiliser la fausse connexion de test_base_partagee plutôt que d'en écrire
# une seconde — deux doublures dérivent, c'est la leçon de f1fbf72.
from tests.test_base_partagee import _FauxConnexion, _Resultat

# Relevé à l'import du module, donc APRÈS conftest et AVANT toute fixture : la fixture
# autouse ci-dessous détourne DATA_DIR pour chaque test, elle masquerait la vraie valeur.
_DATA_DIR_DE_CONFTEST = os.environ.get("DATA_DIR")


class _FauxConnexionTruncate(_FauxConnexion):
    """La doublure partagée, à qui on apprend le PRAGMA TRUNCATE de api_tracking
    (l'autre base parle WAL) et le commit/close dont `_get_connection` a besoin."""

    def __init__(self, mode_rendu="truncate", journal_echoue=False):
        super().__init__()
        self.mode_rendu = mode_rendu
        self.journal_echoue = journal_echoue

    def execute(self, requete, params=None):
        self.pragmas.append(requete)
        if "journal_mode" in requete:
            if self.journal_echoue:
                raise sqlite3.Error("disk I/O error")
            return _Resultat(self.mode_rendu)
        return _Resultat("ok")

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture(autouse=True)
def setup_teardown(monkeypatch, tmp_path):
    """A-bis.4 : sans remise à zéro, H.5 (file pleine) rend muets tous les tests
    collectés après lui et le résultat dépend de l'ordre de collecte."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    api_tracking.reinitialiser_pour_tests()
    yield
    api_tracking.reinitialiser_pour_tests()


def _attendre_file_vide(timeout=5.0):
    """Attendre le DRAINAGE, pas la mort de l'écrivain : le thread est un démon qui
    reste bloqué sur get() une fois la file vide. Tester `is_alive()` ferait patienter
    le timeout entier à chaque test — 5 s de sable pour rien."""
    fin = time.time() + timeout
    while api_tracking._queue.unfinished_tasks > 0 and time.time() < fin:
        if api_tracking._ECRIVAIN_HS:
            return
        time.sleep(0.005)
    assert api_tracking._queue.unfinished_tasks == 0, "la file n'a jamais été drainée"

def test_1_succes_produit_ligne(tmp_path):
    api_tracking.tracer_appel("johnny", "gemini", "gemini-1.5-flash", 0, True, latence_ms=150)
    _attendre_file_vide()
    db_path = tmp_path / "api_usage.db"
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT bot_name, api_name, model, success FROM api_calls").fetchone()
    assert row == ("johnny", "gemini", "gemini-1.5-flash", 1)


def test_2_echec_mistral_produit_ligne(tmp_path):
    api_tracking.tracer_appel("alfred", "mistral", "mistral-large", None, False, raison="vide")
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    row = conn.execute("SELECT bot_name, api_name, success, raison FROM api_calls").fetchone()
    assert row == ("alfred", "mistral", 0, "vide")


def _cascade_mistral(bot_label, contenu="ok"):
    """Fait tourner la vraie cascade sur un seul échelon Mistral bouchonné."""
    mistral = MagicMock()
    mistral.chat.complete.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=contenu))]
    )
    return asyncio.run(generate_response(
        routing={"type": RequestType.TEXT, "has_image": False, "reason": "test"},
        system_prompt="sys", transcript="", user_message="salut",
        conversation_history=[], media_data=None, mime_type="",
        key_manager=MagicMock(), mistral_client=mistral,
        bot_label=bot_label, cascade=[("mistral", "mistral-large")],
    ))


def test_3_nom_du_bot_reel(tmp_path):
    """D1 : le nom vient de bot_id_depuis_label, pas du label brut et surtout pas de
    « unknown » — c'est ce mot en dur qui a rendu les 121 lignes de la base illisibles."""
    assert _cascade_mistral("Johnny Silverhand") == "ok"
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    row = conn.execute("SELECT bot_name, api_name, model, success FROM api_calls").fetchone()
    assert row == ("johnny", "mistral", "mistral-large", 1)


def test_3bis_label_inconnu_ne_devient_pas_unknown(tmp_path):
    """bot_id_depuis_label rend None si aucun marqueur ne correspond : repli sur le
    label brut en minuscules, jamais sur « unknown »."""
    _cascade_mistral("Zorglub")
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    assert conn.execute("SELECT bot_name FROM api_calls").fetchone()[0] == "zorglub"


def test_3ter_echec_de_branche_trace_sa_raison(tmp_path):
    """Une réponse vide est le motif qui a coûté f1fbf72 : la compter est tout
    l'intérêt du chantier."""
    assert _cascade_mistral("Alfred", contenu="") is None
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    row = conn.execute("SELECT bot_name, success, raison FROM api_calls").fetchone()
    assert row == ("alfred", 0, "vide")


def test_4_ecriture_impossible_ne_bloque_pas(tmp_path, caplog):
    original_get_connection = api_tracking._get_connection
    def fake_get_conn():
        raise sqlite3.OperationalError("Impossible d'ouvrir la base")
    api_tracking._get_connection = fake_get_conn
    
    try:
        api_tracking.tracer_appel("test", "test", "test", None, True)
        _attendre_file_vide()
        assert "Erreur connexion SQLite, abandon" in caplog.text
        caplog.clear()
        api_tracking.tracer_appel("test2", "test", "test", None, True)
        assert "Erreur connexion SQLite, abandon" not in caplog.text
    finally:
        api_tracking._get_connection = original_get_connection


def test_5_file_pleine_ne_bloque_pas(caplog):
    for i in range(1010):
        api_tracking.tracer_appel("test", "test", "test", None, True)
        if i == 1005:
            assert api_tracking._JOURNAL_FILE_PLEINE is True
    assert "La file de tracking API est pleine" in caplog.text
    assert caplog.text.count("pleine") == 1


def test_6_deux_threads_concurrents(tmp_path):
    def worker(bot_name):
        for _ in range(50):
            api_tracking.tracer_appel(bot_name, "test", "test", None, True)
            
    t1 = threading.Thread(target=worker, args=("t1",))
    t2 = threading.Thread(target=worker, args=("t2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    count = conn.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0]
    assert count == 100


def test_7_mode_verifie_sur_la_valeur_rendue(monkeypatch):
    """SQLite ne lève pas toujours : il rend simplement un autre mode. Si on ne
    regarde pas la valeur rendue, on croit tenir TRUNCATE et on reste en WAL — le
    mode que le bind mount Docker/Windows sert mal (D2)."""
    monkeypatch.setattr(api_tracking.sqlite3, "connect",
                        lambda *a, **k: _FauxConnexionTruncate(mode_rendu="wal"))
    with patch.object(api_tracking.logger, "warning") as alerte:
        api_tracking._get_connection()
        alerte.assert_any_call("Impossible de passer en mode TRUNCATE, mode actuel : wal")


def test_8_synchronous_survit_a_un_echec_de_journal(monkeypatch):
    """Le défaut corrigé par a6e8327 sur l'autre base : dans le même try que le
    journal, synchronous n'était jamais posé dès que le journal échouait."""
    faux = _FauxConnexionTruncate(journal_echoue=True)
    monkeypatch.setattr(api_tracking.sqlite3, "connect", lambda *a, **k: faux)
    api_tracking._get_connection()
    assert any("synchronous" in p.lower() for p in faux.pragmas)


def test_9_malena_utilise_meme_fonction():
    # Ancre sur la racine du depot : lance depuis tests/, un chemin relatif au CWD
    # faisait tomber ce test sur un FileNotFoundError (convention test_documentation.py:25).
    malena = Path(__file__).resolve().parent.parent / "MalenaBot" / "bot_malena.py"
    with open(malena, "r", encoding="utf-8") as f:
        content = f.read()
    assert "from core.api_tracking import tracer_appel" in content
    assert "sqlite3" not in content


def test_10_code_tpm_disparu():
    from shared.api_manager import MultiAPIKeyManager
    m = MultiAPIKeyManager()
    assert not hasattr(m, "track_tokens")
    assert not hasattr(m, "TPM_LIMITS")


def test_11_base_impossible_threads_stables(tmp_path):
    original_get_connection = api_tracking._get_connection
    def fake_get_conn():
        raise sqlite3.OperationalError("Impossible d'ouvrir la base")
    api_tracking._get_connection = fake_get_conn
    
    try:
        api_tracking.tracer_appel("test", "test", "test", None, True)
        time.sleep(0.1)
        initial_count = threading.active_count()
        for _ in range(50):
            api_tracking.tracer_appel("test", "test", "test", None, True)
        assert threading.active_count() <= initial_count + 1
    finally:
        api_tracking._get_connection = original_get_connection


def test_12_queue_join_rend_la_main(tmp_path):
    original_get_connection = api_tracking._get_connection
    def fake_get_conn():
        conn = original_get_connection()
        class MockConn:
            def __init__(self, c): self.c = c
            def execute(self, *args, **kwargs): raise sqlite3.OperationalError("Disk full")
            def commit(self): self.c.commit()
            def close(self): self.c.close()
        return MockConn(conn)
        
    api_tracking._get_connection = fake_get_conn
    
    try:
        api_tracking.tracer_appel("t", "t", "t", None, True)
        def join_thread():
            api_tracking._queue.join()
        t = threading.Thread(target=join_thread)
        t.daemon = True
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "queue.join() est resté bloqué"
    finally:
        api_tracking._get_connection = original_get_connection


def test_13_la_suite_n_ecrit_pas_dans_la_base_des_bots():
    """La suite tourne sur l'hôte, les bots dans des conteneurs, et les deux partagent
    `data/`. Depuis que la cascade trace, `test_cascade_reponse_vide` écrivait de vraies
    lignes (bot_name « test ») dans `data/api_usage.db` — 40 relevées le 2026-08-29.
    Même incident que pytest polluant `logs/`, même garde : DATA_DIR détourné par
    conftest.py. Sans ça, la base censée mesurer les bots mesure aussi les tests."""
    reel = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
    assert _DATA_DIR_DE_CONFTEST, "conftest.py ne pose plus DATA_DIR"
    assert os.path.abspath(_DATA_DIR_DE_CONFTEST) != reel, (
        "DATA_DIR pointe sur le data/ du dépôt : la suite va polluer la base des bots"
    )


def test_14_jetons_entree_et_sortie_enregistres(tmp_path):
    """Un appel tracé avec jetons_entree=1200, jetons_sortie=80 relu à l'identique."""
    api_tracking.tracer_appel(
        "sugar", "gemini", "gemini-3.5-flash-lite", 0, True,
        latence_ms=120, jetons_entree=1200, jetons_sortie=80
    )
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    row = conn.execute(
        "SELECT jetons_entree, jetons_sortie FROM api_calls"
    ).fetchone()
    assert row == (1200, 80)


def test_15_jetons_absents_enregistrent_null_pas_zero(tmp_path):
    """Un appel tracé sans jetons enregistre NULL en base, pas 0."""
    api_tracking.tracer_appel(
        "sugar", "gemini", "gemini-3.5-flash-lite", 0, True,
        latence_ms=120
    )
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    row = conn.execute(
        "SELECT jetons_entree, jetons_sortie FROM api_calls"
    ).fetchone()
    assert row == (None, None)


def test_16_suivi_origine_par_defaut_et_personnalise(tmp_path, monkeypatch):
    """SUIVI_ORIGINE absent -> 'prod' ; posé à 'sonde' -> 'sonde'."""
    monkeypatch.delenv("SUIVI_ORIGINE", raising=False)
    api_tracking.tracer_appel("sugar", "gemini", "gemini-3.5-flash-lite", 0, True)
    monkeypatch.setenv("SUIVI_ORIGINE", "sonde")
    api_tracking.tracer_appel("sugar", "gemini", "gemini-3.5-flash-lite", 0, True)
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    rows = conn.execute("SELECT origine FROM api_calls ORDER BY id ASC").fetchall()
    assert rows == [("prod",), ("sonde",)]


def test_17_migration_idempotente_ancienne_base(tmp_path):
    """Ouvrir deux fois une base ancienne (sans les colonnes de migration) ne lève pas."""
    db_path = tmp_path / "api_usage.db"
    conn = sqlite3.connect(db_path)
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
            tokens_used INTEGER
        )
    """)
    conn.commit()
    conn.close()

    # Deux ouvertures successives
    conn1 = api_tracking._get_connection()
    conn1.close()
    conn2 = api_tracking._get_connection()
    conn2.close()

    conn_verif = sqlite3.connect(db_path)
    cur = conn_verif.execute("PRAGMA table_info(api_calls)")
    cols = {r[1] for r in cur.fetchall()}
    assert {"jetons_entree", "jetons_sortie", "origine", "raison"}.issubset(cols)


def test_18_ast_llm_cascade_passe_jetons_entree():
    """Chaque appel tracer_appel dans shared/llm_cascade.py passe jetons_entree= en mot-clé."""
    chemin = Path(__file__).resolve().parent.parent / "shared" / "llm_cascade.py"
    source = chemin.read_text(encoding="utf-8")
    arbre = ast.parse(source)
    appels_trouves = 0
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            nom = None
            if isinstance(noeud.func, ast.Name):
                nom = noeud.func.id
            elif isinstance(noeud.func, ast.Attribute):
                nom = noeud.func.attr
            if nom == "tracer_appel":
                appels_trouves += 1
                mots_cles = {k.arg for k in noeud.keywords if k.arg is not None}
                assert "jetons_entree" in mots_cles, (
                    f"Un appel à tracer_appel à la ligne {noeud.lineno} ne passe pas le mot-clé jetons_entree="
                )
    assert appels_trouves >= 2, f"Attendu au moins 2 appels à tracer_appel, trouvé {appels_trouves}"


def test_19_cascade_extrait_jetons_mistral(tmp_path):
    """generate_response extrait les jetons d'usage de la réponse et les passe à tracer_appel."""
    mistral = MagicMock()
    reponse_mock = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))],
        usage=MagicMock(prompt_tokens=350, completion_tokens=42),
    )
    mistral.chat.complete.return_value = reponse_mock
    asyncio.run(generate_response(
        routing={"type": RequestType.TEXT, "has_image": False, "reason": "test"},
        system_prompt="sys", transcript="", user_message="salut",
        conversation_history=[], media_data=None, mime_type="",
        key_manager=MagicMock(), mistral_client=mistral,
        bot_label="Alfred", cascade=[("mistral", "mistral-large")],
    ))
    _attendre_file_vide()
    conn = sqlite3.connect(tmp_path / "api_usage.db")
    row = conn.execute("SELECT jetons_entree, jetons_sortie FROM api_calls").fetchone()
    assert row == (350, 42)

