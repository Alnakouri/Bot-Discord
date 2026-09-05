# -*- coding: utf-8 -*-
"""Un `except ...: pass` doit dire POURQUOI il se tait.

Ce test n'interdit pas le silence. Beaucoup de gestionnaires doivent se taire : un
`ALTER TABLE` deja passe, une annulation de tache qu'on vient soi-meme de demander, un
fichier temporaire deja disparu. Ce qu'il interdit, c'est le silence **nu** — celui dont
personne, six mois plus tard, ne saura dire s'il est voulu ou s'il avale un bug.

Ce que le silence nu a deja coute ici :

* **2026-09-05** : `end_game` levait un `NameError` sur un `color` indefini, donc
  **l'ecran de fin de quiz ne s'affichait jamais**. Les sept `on_timeout` du meme fichier
  se terminaient par `except Exception: pass` : la meme cecite, a un cran de distance.
* **2026-09-04** : la cascade NVIDIA n'avait jamais servi un seul message, et le
  `NameError` qui l'en empechait etait avale sans laisser de trace.

La regle est donc : ou bien le gestionnaire journalise, ou bien il porte un commentaire
qui dit pourquoi il ne le fait pas. Un `# ` suffit — c'est la phrase qui compte.

⚠️ Le commentaire doit etre DANS le gestionnaire (sur la ligne `except`, ou sur le
`pass`). Un commentaire place au-dessus du `try` explique le `try`, pas le silence.

⚠️ Les copies vendorisees `*/core/` sont incluses : c'est justement la qu'un correctif
de `shared/` peut ne pas etre descendu ([[decision-independance-stricte-vendoring-core]]).
"""
import ast
import io
import os

from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

SOURCES = [
    "shared",
    "dashboard",
    "tools",
    "Alfred",
    "JohnnyBot",
    "MaiqBot",
    "MalenaBot",
    "Sheogorath",
    "SugarBot",
]

IGNORES = {"__pycache__", "node_modules", ".git", "migrations"}


def _fichiers_python():
    for source in SOURCES:
        racine = RACINE / source
        if not racine.is_dir():
            continue
        for dossier, sous_dossiers, fichiers in os.walk(racine):
            sous_dossiers[:] = [d for d in sous_dossiers if d not in IGNORES]
            for fichier in sorted(fichiers):
                if fichier.endswith(".py"):
                    yield Path(dossier) / fichier


def _muets_nus(chemin):
    """Rend les lignes des `except ...: pass` qui ne portent aucun commentaire."""
    source = io.open(chemin, encoding="utf-8").read()
    try:
        arbre = ast.parse(source)
    except SyntaxError:
        return []  # deja couvert, et bien mieux, par test_aucun_nom_indefini
    lignes = source.split("\n")
    nus = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.ExceptHandler):
            continue
        if not all(isinstance(corps, ast.Pass) for corps in noeud.body):
            continue
        debut = noeud.lineno
        fin = max(corps.lineno for corps in noeud.body)
        etendue = "\n".join(lignes[debut - 1:fin])
        if "#" not in etendue:
            nus.append(debut)
    return nus


def test_aucun_except_pass_sans_explication():
    trouvailles = []
    analyses = 0
    for chemin in _fichiers_python():
        analyses += 1
        for ligne in _muets_nus(chemin):
            trouvailles.append("%s:%d" % (chemin.relative_to(RACINE).as_posix(), ligne))

    # Un `SOURCES` mal orthographie rendrait ce test vert sans rien lire.
    assert analyses > 150, "seulement %d fichiers analyses : SOURCES est-il juste ?" % analyses

    assert not trouvailles, (
        "%d `except ...: pass` sans un mot d'explication. Journalisez l'exception, ou "
        "ecrivez sur place pourquoi ce silence est voulu :\n  %s"
        % (len(trouvailles), "\n  ".join(trouvailles))
    )
