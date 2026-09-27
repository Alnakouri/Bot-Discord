# -*- coding: utf-8 -*-
"""Tests unitaires pour la sauvegarde des bases SQLite et des cles (SUITE 12).

Tous les tests tournent strictement dans tmp_path et ne polluent jamais data/.
Verifie :
- L'API backup SQLite et l'integrite de la base copiee.
- L'absence d'impact sur la base source (jamais de WAL ni de fichiers -wal/-shm).
- Le filtre d'age --si-plus-vieux-que.
- La rotation a 14 copies pour les bases et 8 pour les cles.
- Le nettoyage des dossiers .partiel orphelins de plus de 24h.
- Le refus absolu de copier les cles a l'interieur du depot.
- Le verrou AST sur Sheogorath : aucune trace de l'ancienne fausse sauvegarde.
"""

import ast
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.sauvegarde_bases import (
    executer_sauvegarde,
    executer_rotation,
    derniere_sauvegarde_datee,
)
from tools.sauvegarde_cles import (
    executer_sauvegarde_cles,
    executer_rotation as rotation_cles,
    FICHIERS_CLES_RELATIFS,
    BOTS,
)


def test_sauvegarde_base_et_json(tmp_path):
    """Verifie la copie fidele d'une base active et d'un JSON avec integrity_check."""
    donnees = tmp_path / "data"
    donnees.mkdir()
    sortie = tmp_path / "sauvegardes"

    # Creation d'une base source de test
    src_db = donnees / "bots_database.db"
    conn = sqlite3.connect(str(src_db))
    conn.execute("PRAGMA journal_mode=TRUNCATE;")
    conn.execute("CREATE TABLE joueurs (id INTEGER PRIMARY KEY, nom TEXT);")
    conn.execute("INSERT INTO joueurs (nom) VALUES ('Alice'), ('Bob'), ('Charlie');")
    conn.commit()
    conn.close()

    # Creation d'un fichier json
    src_json = donnees / "memoires.json"
    src_json.write_text(json.dumps({"cle": "valeur", "compteur": 42}), encoding="utf-8")

    # Execution de la sauvegarde
    succes = executer_sauvegarde(donnees, sortie, si_plus_vieux_que=0.0)
    assert succes is True

    # Verification de l'arborescence
    derniere = derniere_sauvegarde_datee(sortie)
    assert derniere is not None
    nom_dossier, _ = derniere
    dossier_sauv = sortie / nom_dossier
    assert dossier_sauv.exists()
    assert not (sortie / f"{nom_dossier}.partiel").exists()

    # Verification de la base copiee
    copie_db = dossier_sauv / "bots_database.db"
    assert copie_db.exists()

    conn_copie = sqlite3.connect(str(copie_db))
    # 1. 3 lignes presentes
    cur = conn_copie.cursor()
    cur.execute("SELECT count(*) FROM joueurs;")
    assert cur.fetchone()[0] == 3

    # 2. integrity_check = ok
    cur.execute("PRAGMA integrity_check;")
    assert cur.fetchone()[0] == "ok"

    # 3. journal_mode != wal
    cur.execute("PRAGMA journal_mode;")
    mode = cur.fetchone()[0].lower()
    assert mode != "wal"
    conn_copie.close()

    # Verification du JSON
    copie_json = dossier_sauv / "memoires.json"
    assert copie_json.exists()
    assert json.loads(copie_json.read_text(encoding="utf-8")) == {"cle": "valeur", "compteur": 42}


def test_sauvegarde_ne_pollue_pas_source(tmp_path):
    """Apres une sauvegarde, la base source ne doit JAMAIS etre en WAL ni creer de -shm/-wal."""
    donnees = tmp_path / "data"
    donnees.mkdir()
    sortie = tmp_path / "sauvegardes"

    src_db = donnees / "decisions.db"
    conn = sqlite3.connect(str(src_db))
    conn.execute("PRAGMA journal_mode=TRUNCATE;")
    conn.execute("CREATE TABLE decisions (id INT);")
    conn.commit()
    conn.close()

    executer_sauvegarde(donnees, sortie, si_plus_vieux_que=0.0)

    # 1. Aucun fichier temporaire WAL a cote de la source
    fichiers_data = [p.name for p in donnees.iterdir()]
    assert not any(name.endswith("-wal") for name in fichiers_data)
    assert not any(name.endswith("-shm") for name in fichiers_data)

    # 2. Reouverture de la source : journal_mode != wal
    conn_verif = sqlite3.connect(str(src_db))
    cur = conn_verif.cursor()
    cur.execute("PRAGMA journal_mode;")
    mode = cur.fetchone()[0].lower()
    assert mode != "wal"
    conn_verif.close()


def test_si_plus_vieux_que(tmp_path):
    """Ne declenche aucune nouvelle sauvegarde si la derniere est recente (< seuil)."""
    donnees = tmp_path / "data"
    donnees.mkdir()
    sortie = tmp_path / "sauvegardes"

    src_db = donnees / "bots_database.db"
    conn = sqlite3.connect(str(src_db))
    conn.execute("CREATE TABLE t (x INT);")
    conn.close()

    # 1ere sauvegarde -> True
    ok1 = executer_sauvegarde(donnees, sortie, si_plus_vieux_que=0.0)
    assert ok1 is True
    dossiers_apres_1 = [p.name for p in sortie.iterdir() if p.is_dir()]
    assert len(dossiers_apres_1) == 1

    # 2eme sauvegarde immediate avec seuil de 20 heures -> False
    ok2 = executer_sauvegarde(donnees, sortie, si_plus_vieux_que=20.0)
    assert ok2 is False
    dossiers_apres_2 = [p.name for p in sortie.iterdir() if p.is_dir()]
    assert len(dossiers_apres_2) == 1


def test_rotation_sauvegardes_complet(tmp_path):
    """Conserve 14 sauvegardes completes les plus recentes et preserve les elements externes."""
    sortie = tmp_path / "sauvegardes"
    sortie.mkdir()

    # Creer 16 dossiers datés factices
    for jour in range(1, 17):
        nom = f"2026-09-{jour:02d}_1200"
        (sortie / nom).mkdir()

    # Creer un dossier et un fichier etrangers
    dossier_etranger = sortie / "autre_chose"
    dossier_etranger.mkdir()
    fichier_etranger = sortie / "notes.txt"
    fichier_etranger.write_text("ne pas toucher", encoding="utf-8")

    executer_rotation(sortie, retention=14)

    restants = sorted([p.name for p in sortie.iterdir() if p.is_dir() and p.name != "autre_chose"])
    assert len(restants) == 14
    # Les deux plus anciens (01 et 02) ont ete purges
    assert "2026-09-01_1200" not in restants
    assert "2026-09-02_1200" not in restants
    # Du 03 au 16 conserves
    assert restants[0] == "2026-09-03_1200"
    assert restants[-1] == "2026-09-16_1200"

    # L'etranger est toujours la
    assert dossier_etranger.exists()
    assert fichier_etranger.exists()


def test_purge_partiel_orphelin(tmp_path):
    """Purge un dossier .partiel vieux de plus de 24h et conserve un .partiel recent."""
    sortie = tmp_path / "sauvegardes"
    sortie.mkdir()

    partiel_ancien = sortie / "2026-09-10_0100.partiel"
    partiel_ancien.mkdir()
    # Vieillir artificiellement de 48 heures
    mtime_ancien = time.time() - (48 * 3600)
    os.utime(partiel_ancien, (mtime_ancien, mtime_ancien))

    partiel_recent = sortie / "2026-09-28_0100.partiel"
    partiel_recent.mkdir()

    executer_rotation(sortie, retention=14)

    assert not partiel_ancien.exists()
    assert partiel_recent.exists()


def test_sauvegarde_cles_complet(tmp_path):
    """Copie verifiee des 13 fichiers de cles sans altérer les sources."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sortie_cles = tmp_path / "sauvegardes_cles"

    # Creer les 13 fichiers attendus
    for bot in BOTS:
        bdir = repo / bot
        bdir.mkdir()
        (bdir / ".env.encrypted").write_text(f"ENCRYPTED_{bot}", encoding="utf-8")
        (bdir / ".master_key").write_text(f"KEY_{bot}", encoding="utf-8")

    dash_dir = repo / "dashboard"
    dash_dir.mkdir()
    (dash_dir / ".env").write_text("DASHBOARD_SECRET", encoding="utf-8")

    # Memento des mtime sources
    mtimes_sources = {f: (repo / f).stat().st_mtime for f in FICHIERS_CLES_RELATIFS}

    # Sauvegarde
    ok = executer_sauvegarde_cles(repo, sortie_cles, si_plus_vieux_que=0.0)
    assert ok is True

    # Verification de la destination
    dossiers_cles = [p for p in sortie_cles.iterdir() if p.is_dir()]
    assert len(dossiers_cles) == 1
    dossier_date = dossiers_cles[0]

    for rel_path in FICHIERS_CLES_RELATIFS:
        src = repo / rel_path
        dst = dossier_date / rel_path
        assert dst.exists()
        assert dst.read_bytes() == src.read_bytes()
        # Source strictement intacte
        assert src.stat().st_mtime == mtimes_sources[rel_path]


def test_sauvegarde_cles_refus_si_dans_repo(tmp_path):
    """Refus categorique si --sortie est a l'interieur du depot."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sortie_interdite = repo / "backup_interdit"

    with pytest.raises(ValueError, match="REFUS ABSOLU"):
        executer_sauvegarde_cles(repo, sortie_interdite)


def test_sauvegarde_cles_fichier_manquant(tmp_path, caplog):
    """Un fichier manquant est signale en warning sans bloquer les autres copies."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sortie_cles = tmp_path / "sauvegardes_cles"

    # Ne creer que Alfred
    alfred_dir = repo / "Alfred"
    alfred_dir.mkdir()
    (alfred_dir / ".env.encrypted").write_text("ALFRED_SECRET", encoding="utf-8")
    (alfred_dir / ".master_key").write_text("ALFRED_KEY", encoding="utf-8")

    ok = executer_sauvegarde_cles(repo, sortie_cles, si_plus_vieux_que=0.0)
    assert ok is True

    dossier_date = [p for p in sortie_cles.iterdir() if p.is_dir()][0]
    assert (dossier_date / "Alfred" / ".env.encrypted").exists()


def test_rotation_cles(tmp_path):
    """Conserve les 8 sauvegardes de cles les plus recentes."""
    sortie = tmp_path / "sauvegardes_cles"
    sortie.mkdir()

    for jour in range(1, 11):
        (sortie / f"2026-09-{jour:02d}").mkdir()

    rotation_cles(sortie, retention=8)

    restants = sorted([p.name for p in sortie.iterdir() if p.is_dir()])
    assert len(restants) == 8
    # 01 et 02 purges
    assert "2026-09-01" not in restants
    assert "2026-09-02" not in restants
    assert restants[0] == "2026-09-03"
    assert restants[-1] == "2026-09-10"


def test_verrou_ast_sheogorath():
    """Verrou AST : bot_sheogorath.py ne doit plus referencer ni importer la fausse sauvegarde."""
    fichier_sheo = RACINE / "Sheogorath" / "bot_sheogorath.py"
    assert fichier_sheo.exists()

    arbre = ast.parse(fichier_sheo.read_text(encoding="utf-8"))

    for noeud in ast.walk(arbre):
        # 1. Pas de fonction nommee daily_backup_check
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert noeud.name != "daily_backup_check", "daily_backup_check ne doit plus exister !"

        # 2. Pas d'import de backup_manager
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                assert alias.name != "backup_manager", "Import direct de backup_manager interdit"
        elif isinstance(noeud, ast.ImportFrom):
            assert noeud.module != "backup_manager", "Import depuis backup_manager interdit"

        # 3. Pas d'attribut ou appel a daily_backup_check
        if isinstance(noeud, ast.Name):
            assert noeud.id != "daily_backup_check", "Identifiant daily_backup_check interdit"
        if isinstance(noeud, ast.Attribute):
            assert noeud.attr != "daily_backup_check", "Attribut daily_backup_check interdit"
