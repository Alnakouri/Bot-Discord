# -*- coding: utf-8 -*-
"""Base SQLite partagée par les 6 bots.

Vu en prod le 2026-08-26 : `⚠️ [DB] Impossible d'activer WAL: disk I/O error`, suivi
d'une boucle qui meurt sur la même erreur. WAL exige un fichier de mémoire partagée
`-shm` que les montages Docker sous Windows ne servent pas toujours.

Ce qui compte alors n'est pas d'avoir WAL, c'est de ne pas laisser le mode de
journalisation au hasard — et de ne pas perdre au passage les réglages qui rendent
une base partagée vivable.
"""
import os
import sqlite3
import sys

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import shared.shared_database as db


class _FauxConnexion:
    """Enregistre les PRAGMA reçus et peut faire échouer WAL, comme en prod."""

    def __init__(self, wal_echoue=False, wal_silencieux=False):
        self.wal_echoue = wal_echoue
        self.wal_silencieux = wal_silencieux
        self.pragmas = []

    def execute(self, requete):
        self.pragmas.append(requete)
        if "journal_mode=TRUNCATE" in requete:
            if self.wal_echoue:
                raise sqlite3.Error("disk I/O error")
            if self.wal_silencieux:
                # SQLite ne leve pas toujours : il rend simplement un autre mode.
                return _Resultat("wal")
            return _Resultat("truncate")
        return _Resultat("ok")


class _Resultat:
    def __init__(self, valeur):
        self.valeur = valeur

    def fetchone(self):
        return (self.valeur,)


@pytest.fixture(autouse=True)
def _remettre_le_drapeau(monkeypatch):
    """Le mode n'est posé qu'une fois par processus : chaque test repart à zéro."""
    monkeypatch.setattr(db, "_JOURNAL_POSE", False)


def test_wal_n_est_JAMAIS_pose():
    """WAL est incompatible avec ce fichier : il est partage entre l'hote Windows
    (dashboard, sondes) et les 6 conteneurs Linux via un bind mount. WAL exige un
    `-shm` mappe en memoire que les deux mondes ne peuvent pas partager.

    Live du 2026-09-13 : la base etait en WAL, les 6 bots recevaient
    `unable to open database file` sur `is_maintenance_mode()` et restaient MUETS."""
    conn = _FauxConnexion()
    db._poser_journal(conn)
    assert not any("WAL" in p.upper() for p in conn.pragmas), (
        f"WAL a ete pose sur une base partagee hote/conteneurs : {conn.pragmas}"
    )
    assert any("journal_mode=TRUNCATE" in p for p in conn.pragmas), (
        "aucun mode sans memoire partagee n'a ete pose"
    )


def test_le_mot_WAL_n_apparait_plus_dans_le_code():
    """Verrou sur le FICHIER, pas sur une reconstitution : tant que le PRAGMA existe
    quelque part, un chemin peut le rejouer et re-empoisonner la base pour de bon
    (le mode est une propriete PERSISTANTE du fichier, il survit au redemarrage)."""
    src = open(os.path.join(_parent_dir, "shared", "shared_database.py"),
               encoding="utf-8").read()
    lignes = [
        ligne for ligne in src.splitlines()
        if "journal_mode" in ligne and not ligne.strip().startswith("#")
    ]
    code = chr(10).join(lignes)
    assert "journal_mode=WAL" not in code, (
        "shared_database.py pose encore journal_mode=WAL"
    )


def test_un_TRUNCATE_refuse_en_silence_est_signale():
    """SQLite ne leve pas toujours : il rend simplement un autre mode. Si la base
    reste en WAL, il faut au moins que ca CRIE — sinon les conteneurs tombent et
    plus rien n'explique pourquoi."""
    conn = _FauxConnexion(wal_silencieux=True)
    db._poser_journal(conn)          # ne doit pas lever
    bloc = open(os.path.join(_parent_dir, "shared", "shared_database.py"),
                encoding="utf-8").read()
    bloc = bloc.split("def _poser_journal")[1].split("def get_connection")[0]
    assert "logger.warning" in bloc, "un mode inattendu doit etre journalise"


def test_l_echec_du_pragma_ne_fait_pas_planter():
    """Une base degradee doit rester utilisable : c'est un bot, pas une banque."""
    conn = _FauxConnexion(wal_echoue=True)
    db._poser_journal(conn)          # ne doit lever aucune exception


def test_le_mode_n_est_pose_qu_une_fois():
    """C'est une propriété persistante du FICHIER : le reposer à chaque connexion
    ajoutait un PRAGMA par opération et répétait le même avertissement sans fin."""
    premiere = _FauxConnexion()
    db._poser_journal(premiere)
    seconde = _FauxConnexion()
    db._poser_journal(seconde)
    assert seconde.pragmas == [], "le mode a été reposé sur la 2e connexion"


def test_un_echec_de_journalisation_ne_fait_pas_planter():
    """Une base dégradée doit rester utilisable : c'est un bot, pas une banque."""
    class _ToutEchoue(_FauxConnexion):
        def execute(self, requete):
            self.pragmas.append(requete)
            raise sqlite3.Error("disk I/O error")

    conn = _ToutEchoue()
    db._poser_journal(conn)          # ne doit lever aucune exception


# ---------------------------------------------------------------------------
# Réglages par connexion
# ---------------------------------------------------------------------------

def test_les_reglages_de_concurrence_sont_bien_appliques():
    """`synchronous` et `busy_timeout` sont des réglages PAR CONNEXION, contrairement
    au mode de journalisation."""
    conn = db.get_connection()
    try:
        assert conn.execute("PRAGMA synchronous;").fetchone()[0] == 1, "NORMAL attendu"
        assert conn.execute("PRAGMA busy_timeout;").fetchone()[0] == 20000, \
            "sans busy_timeout, un écrivain concurrent échoue au lieu d'attendre"
    finally:
        conn.close()


def test_synchronous_survit_a_un_echec_de_wal():
    """Il était dans le MEME try que WAL : dès que WAL échouait, il n'était jamais
    posé — précisément dans le cas dégradé où il sert le plus."""
    src = open(os.path.join(_parent_dir, "shared", "shared_database.py"),
               encoding="utf-8").read()
    bloc = src.split("def get_connection()")[1].split("def ")[0]
    assert "synchronous=NORMAL" in bloc, "synchronous doit être posé dans get_connection"
    assert "journal_mode" not in bloc, \
        "le mode de journalisation ne doit plus partager le try de synchronous"


def test_l_avertissement_passe_par_le_logger():
    """Un `print()` n'atterrit ni dans les logs structurés ni dans le dashboard —
    l'incident du 2026-08-26 y serait passé inaperçu."""
    src = open(os.path.join(_parent_dir, "shared", "shared_database.py"),
               encoding="utf-8").read()
    bloc = src.split("def _poser_journal")[1].split("def get_connection")[0]
    assert "logger.warning" in bloc
    assert "print(" not in bloc
