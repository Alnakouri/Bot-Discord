# -*- coding: utf-8 -*-
"""Aucun nom indefini dans le code source, et aucun fichier qui ne compile pas.

« ⚠️ `pyflakes` AVANT `pytest` » est une regle de ce depot depuis le 2026-09-05. Elle
n'etait imposee par rien : c'etait une consigne dans un fichier de plan, donc un voeu.
Ce test en fait un verrou.

Ce qu'elle a deja coute, quand personne ne la jouait :

* **2026-09-04** : 62 `logger` indefinis livres d'un coup — dont le bouton de redemarrage
  du dashboard. Chacun transformait un `except` silencieux mais inoffensif en `NameError`
  **leve depuis le gestionnaire d'exception**. **Aucun test ne cassait.**
* **2026-09-05** : 11 fichiers en `SyntaxError` dans un lot livre. Le meme jour, un
  `color` indefini dormait dans `shared/games/views.py` : `end_game` etait la SEULE des
  six methodes construisant un embed a ne pas le definir, donc **l'ecran de fin de quiz
  ne s'affichait jamais**. L'exception partait dans un callback discord.py — nulle part
  de visible. Le rapport de la veille declarait pourtant « aucun nom indefini ».

⚠️ Ce test ne regarde QUE les noms indefinis et les erreurs de syntaxe. Les imports
inutilises de `pyflakes` sont volontairement ignores : ils ne cassent rien, et faire
echouer la CI dessus apprendrait a ignorer ce test.

⚠️ Il ne lit que le code du depot. Les `.venv*` et `site-packages` en produisent des
centaines qui ne nous regardent pas.
"""
import io
import os

from pathlib import Path

# ⚠️ Import DUR, pas `pytest.importorskip`. Un verrou qui s'auto-skippe quand sa
# dependance manque ne verrouille rien — et c'est precisement ce que ce test existe pour
# empecher. `pyflakes` est dans `requirements.txt` pour cette raison.
from pyflakes import api as pyflakes_api
from pyflakes import messages as pyflakes_messages
from pyflakes import reporter as pyflakes_reporter

RACINE = Path(__file__).resolve().parent.parent

# Le code qui nous appartient. Les copies vendorisees `*/core/` sont incluses a dessein :
# c'est justement la qu'un correctif de `shared/` peut ne pas etre descendu
# ([[decision-independance-stricte-vendoring-core]]).
SOURCES = [
    "shared",
    "dashboard",
    "tools",
    "tests",
    "Alfred",
    "JohnnyBot",
    "MaiqBot",
    "MalenaBot",
    "Sheogorath",
    "SugarBot",
]

IGNORES = {"__pycache__", "node_modules", ".git", "migrations"}

# Ce qu'on retient. `UndefinedExport` = un nom cite dans `__all__` qui n'existe pas.
FATALES = (
    pyflakes_messages.UndefinedName,
    pyflakes_messages.UndefinedLocal,
    pyflakes_messages.UndefinedExport,
)


class _Collecteur(pyflakes_reporter.Reporter):
    """Ne garde que les noms indefinis et les erreurs de syntaxe."""

    def __init__(self):
        super().__init__(io.StringIO(), io.StringIO())
        self.trouvailles = []

    def flake(self, message):
        if isinstance(message, FATALES):
            chemin = Path(message.filename).relative_to(RACINE)
            self.trouvailles.append(
                "%s:%d  %s" % (chemin, message.lineno, message.message % message.message_args)
            )

    def unexpectedError(self, filename, msg):
        self.trouvailles.append("%s  illisible : %s" % (filename, msg))

    def syntaxError(self, filename, msg, lineno, offset, text):
        chemin = Path(filename).relative_to(RACINE)
        self.trouvailles.append("%s:%s  SyntaxError : %s" % (chemin, lineno, msg))


def _fichiers_python():
    for source in SOURCES:
        racine = RACINE / source
        if not racine.is_dir():
            continue
        for dossier, sous_dossiers, fichiers in os.walk(racine):
            sous_dossiers[:] = [d for d in sous_dossiers if d not in IGNORES]
            for fichier in fichiers:
                if fichier.endswith(".py"):
                    yield os.path.join(dossier, fichier)


def test_aucun_nom_indefini_ni_erreur_de_syntaxe():
    collecteur = _Collecteur()
    analyses = 0
    for chemin in _fichiers_python():
        pyflakes_api.checkPath(chemin, collecteur)
        analyses += 1

    # Un `SOURCES` mal orthographie rendrait ce test vert sans rien lire.
    assert analyses > 200, "seulement %d fichiers analyses : SOURCES est-il juste ?" % analyses

    assert not collecteur.trouvailles, (
        "%d nom(s) indefini(s) ou erreur(s) de syntaxe. Chacun est un NameError ou un "
        "import casse qui n'attend que d'etre atteint en live :\n  %s"
        % (len(collecteur.trouvailles), "\n  ".join(collecteur.trouvailles))
    )
