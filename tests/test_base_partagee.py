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


# ---------------------------------------------------------------------------
# LOT 2 — Aucune connexion ne doit dépendre du ramasse-miettes
# ---------------------------------------------------------------------------

def test_ast_aucune_connexion_sans_finally_ni_with():
    """Verrou AST (lot 2) : aucune connexion ne repose sur le ramasse-miettes.

    L'invariant porte sur le NOM : un appel direct a `get_connection()` n'est
    tolere que si la connexion qu'il rend est affectee a un nom, et que ce nom
    precis est ferme dans un `finally`. Tout le reste doit passer par
    `with connexion() as conn:`, qui ne l'appelle pas directement.

    ⚠️ La premiere version de ce verrou se contentait de « la fonction contient
    un `with` quelque part » : un `with open(...)` sans aucun rapport suffisait a
    la faire taire sur une connexion nue. Mutation rejouee, elle est muette.
    """
    import ast

    fichier = os.path.join(_parent_dir, "shared", "shared_database.py")
    with open(fichier, "r", encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=fichier)

    fonctions = [n for n in ast.walk(arbre)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    noms = {n.name for n in fonctions}
    assert "connexion" in noms, "connexion() doit etre defini dans shared_database.py"

    def fermes_dans_un_finally(fn):
        """Noms N tels qu'un `finally` de la fonction contient `N.close()`."""
        fermes = set()
        for t in ast.walk(fn):
            if not isinstance(t, ast.Try):
                continue
            for stmt in t.finalbody:
                for sub in ast.walk(stmt):
                    if (isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "close"
                            and isinstance(sub.func.value, ast.Name)):
                        fermes.add(sub.func.value.id)
        return fermes

    violations = []
    directes = []
    for fn in fonctions:
        if fn.name == "get_connection":
            continue

        # Les appels `get_connection()` affectes a un nom, et ce nom.
        affectes = {}
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Call)
                    and getattr(node.value.func, "id", None) == "get_connection"):
                for cible in node.targets:
                    if isinstance(cible, ast.Name):
                        affectes[id(node.value)] = cible.id

        appels = [n for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "get_connection"]
        if not appels:
            continue
        directes.append(fn.name)

        fermes = fermes_dans_un_finally(fn)
        for appel in appels:
            nom = affectes.get(id(appel))
            if nom is None:
                violations.append(f"{fn.name} (connexion non affectee a un nom)")
            elif nom not in fermes:
                violations.append(f"{fn.name} (`{nom}` jamais ferme dans un finally)")

    assert not violations, (
        "Connexions dont la fermeture depend du ramasse-miettes : "
        + ", ".join(violations)
    )
    # Le reste du module doit passer par `with connexion()`. Si cette liste
    # s'allonge, c'est une decision, pas un oubli : elle doit se voir ici.
    assert set(directes) == {"connexion", "marquer_utilisateur_bot"}, (
        f"appels directs a get_connection() : {sorted(directes)}"
    )


def test_fuite_fermeture_garantie_sur_chemin_d_erreur(tmp_path, monkeypatch):
    """Verrou fuite (lot 2) : sur un chemin d'erreur (base corrompue/illisible),
    la connexion DOIT être fermée. Sans le gestionnaire de contexte connexion(),
    la connexion fuit."""
    fausse_db = tmp_path / "corrompue.db"
    fausse_db.write_bytes(b"contenu non sqlite corrompu")

    monkeypatch.setattr(db, "DB_PATH", fausse_db)

    connexions_ouvertes = []
    orig_connect = sqlite3.connect

    def spy_connect(*args, **kwargs):
        c = orig_connect(*args, **kwargs)
        connexions_ouvertes.append(c)
        return c

    monkeypatch.setattr(sqlite3, "connect", spy_connect)

    # get_config est la première fonction appelée par on_message (via is_maintenance_mode)
    with pytest.raises(sqlite3.DatabaseError):
        db.get_config("maintenance_mode")

    assert len(connexions_ouvertes) == 1, "Une connexion aurait dû être tentée"
    conn = connexions_ouvertes[0]

    connexion_fermee = False
    try:
        conn.cursor()
    except sqlite3.ProgrammingError:
        connexion_fermee = True

    assert connexion_fermee, "Fuite de connexion : la connexion n'a pas été fermée lors de l'erreur"

