# -*- coding: utf-8 -*-
"""Le journal des décisions observe, il ne décide pas — et il ne ralentit personne.

Il existe parce que le dépôt ne garde AUCUN texte de message : `bots_database.db` a
`user_id + type + horodatage`, `api_usage.db` des durées, et les rapports d'éval ne
contiennent que 18 messages distincts (mesure du 2026-09-20). Sans corpus, on ne peut
ni mesurer le taux d'erreur des règles en place, ni affiner quoi que ce soit.

Ce que ces verrous tiennent :
  1. il n'est JAMAIS sur le chemin de la réponse (file non bloquante, écriture différée) ;
  2. il refuse une décision inconnue plutôt que de la ranger en silence ;
  3. il n'ouvre JAMAIS la base en WAL — un WAL orphelin sur un volume monté depuis
     l'hôte Windows éjecte les six conteneurs EN SILENCE
     ([[gotcha-wal-orphelin-verrouille-la-base]]) ;
  4. les trois points de décision sont bien CÂBLÉS dans les bots, vérifié par `ast` et
     non par une regex : un `journalise` recopié dans un commentaire ne compte pas.
"""
import ast
import os
import sqlite3
import sys
import tempfile
import time

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)


@pytest.fixture()
def journal(monkeypatch):
    """Un journal neuf, dans un dossier jetable — jamais la base des bots vivants."""
    monkeypatch.setenv("DATA_DIR", tempfile.mkdtemp(prefix="journal-test-"))
    import importlib
    from shared import journal_decisions as jd
    importlib.reload(jd)
    return jd


def _attendre(jd, attendu, limite=5.0):
    """L'écriture est différée : on attend le compte, on ne dort pas au hasard."""
    t0 = time.time()
    while time.time() - t0 < limite:
        if sum(jd.compte().values()) >= attendu:
            return True
        time.sleep(0.05)
    return False


def test_une_decision_rangee_est_relisible(journal):
    journal.journalise("alfred", journal.INTENTION, "Alfred arrete de parler la",
                       "repos", detail="stop=['arrete'] rattrapage=['la']")
    assert _attendre(journal, 1), "l'entrée n'a jamais été écrite"
    assert journal.compte() == {"intention": 1}


def test_une_decision_INCONNUE_est_refusee_au_lieu_d_etre_rangee_en_silence(journal):
    """Une étiquette libre rendrait le corpus inexploitable sans que rien ne le dise."""
    with pytest.raises(ValueError):
        journal.journalise("alfred", "humeur", "coucou", "gai")


def test_un_texte_vide_n_est_pas_range(journal):
    journal.journalise("sugar", journal.TON, "", "neutral")
    time.sleep(0.3)
    assert journal.compte() == {}


def test_la_base_n_est_JAMAIS_en_WAL(journal):
    """Un WAL orphelin sur `data/` rend les six bots muets, en silence."""
    journal.journalise("sugar", journal.TON, "desole mais t es nulle", "apology")
    assert _attendre(journal, 1)
    conn = sqlite3.connect(journal._chemin())
    try:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() != "wal", f"journal_mode={mode} — interdit sur data/"


def test_la_file_pleine_JETTE_au_lieu_de_bloquer_le_bot(journal, monkeypatch):
    """Le bot passe avant son journal : une file saturée ne doit pas le faire attendre.

    On empêche l'écrivain de démarrer, on sature la file, puis on mesure que l'appel
    suivant rend la main tout de suite. Sans le `put_nowait`, il attendrait pour
    toujours — et le salon avec lui.
    """
    monkeypatch.setattr(journal, "_demarre", lambda: None)
    for i in range(journal._TAILLE_FILE + 5):
        journal.journalise("johnny", journal.PERTINENCE, f"message {i}", "tirage")
    t0 = time.perf_counter()
    journal.journalise("johnny", journal.PERTINENCE, "celui de trop", "tirage")
    ecoule = time.perf_counter() - t0
    assert ecoule < 0.1, f"journalise() a bloqué {ecoule:.2f}s sur une file pleine"
    assert journal._jetees > 0, "rien n'a été jeté alors que la file débordait"


# ── Le câblage dans les bots, lu par `ast` et non par une regex ───────────────
# Un `journalise(...)` cité dans un commentaire ou une docstring ne câble rien
# ([[gotcha-test-qui-retape-la-logique]]).
_ATTENDUS = {
    ("Alfred", "bot_alfred.py"): "INTENTION",
    ("SugarBot", "bot_sugar.py"): "TON",
    ("JohnnyBot", "bot_johnny.py"): "PERTINENCE",
}


@pytest.mark.parametrize("cible,constante", sorted(_ATTENDUS.items()))
def test_le_point_de_decision_est_bien_CABLE(cible, constante):
    dossier, fichier = cible
    chemin = os.path.join(_parent_dir, dossier, fichier)
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename=fichier)

    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call)
              and getattr(n.func, "id", None) == "journalise"]
    assert appels, f"{fichier} n'appelle jamais journalise()"

    # La constante de décision doit être IMPORTEE, pas retapée en chaîne : une chaîne
    # « ton » qui devient « tons » passerait le verrou et casserait le corpus.
    importees = {a.name for n in ast.walk(arbre) if isinstance(n, ast.ImportFrom)
                 and (n.module or "").endswith("journal_decisions") for a in n.names}
    assert constante in importees, (
        f"{fichier} doit importer {constante} depuis journal_decisions, "
        f"pas retaper l'étiquette à la main (importé : {sorted(importees)})"
    )


def test_le_module_est_vendorise_pour_les_six():
    """Les bots importent `core.journal_decisions` : la copie doit exister partout.

    ⚠️ Et les DEUX listes de vendoring doivent le connaître — `vendor_core.py` copie,
    `sonde_core_drift.py` surveille ([[gotcha-deux-listes-vendoring]]).
    """
    bots = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]
    manquants = [b for b in bots
                 if not os.path.exists(os.path.join(_parent_dir, b, "core",
                                                    "journal_decisions.py"))]
    assert not manquants, f"copie vendorisée absente chez : {manquants}"

    for outil in ("vendor_core.py", "sonde_core_drift.py"):
        texte = open(os.path.join(_parent_dir, "tools", outil), encoding="utf-8").read()
        assert "journal_decisions.py" in texte, (
            f"{outil} ignore journal_decisions.py — les deux listes doivent être égales"
        )
