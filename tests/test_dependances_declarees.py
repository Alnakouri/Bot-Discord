# -*- coding: utf-8 -*-
"""Une dependance utilisee par les tests mais absente de `requirements.txt` ne se voit
pas : elle est deja installee sur la machine du developpeur, souvent tiree par une
autre bibliotheque, et la suite est verte. C'est la CI qui tombe — ailleurs, plus tard,
sur un message qui ne dit pas d'ou vient le probleme.

Vecu le 2026-08-31 : `fontTools` (lu pour verifier la `cmap` d'une police) etait
present en local via Pillow, absent en CI. 500 tests verts ici, `ModuleNotFoundError`
la-bas.
"""
import ast
import sys
from pathlib import Path

_RACINE = Path(__file__).resolve().parent.parent

# Modules du depot lui-meme : ils n'ont rien a faire dans requirements.txt.
# ⚠️ DEDUITS du depot, jamais ecrits en dur : la suite importe des modules de bots par
# manipulation de `sys.path` (`sheo_data`, `relauncher`, `sonde_repartie`...) et une
# liste figee prendrait chaque nouveau module pour une dependance manquante — un test
# qui crie a tort finit ignore, puis desactive.
_IGNORES = {".git", "__pycache__", "node_modules", ".venv", "venv", "assets", "logs"}


def _modules_locaux():
    noms = set()
    for chemin in _RACINE.rglob("*"):
        if any(part in _IGNORES for part in chemin.parts):
            continue
        if chemin.suffix == ".py":
            noms.add(chemin.stem)
        elif chemin.is_dir():
            noms.add(chemin.name)
    return noms


_LOCAUX = _modules_locaux()

# Le nom qu'on importe n'est pas toujours celui qu'on installe.
_NOM_PAQUET = {
    "PIL": "pillow",
    "fontTools": "fonttools",
    "discord": "discord.py",
    "dotenv": "python-dotenv",
    "google": "google-genai",
    "speech_recognition": "speechrecognition",
    "nacl": "pynacl",
    "yaml": "pyyaml",
    "pytest_asyncio": "pytest-asyncio",
}


def _modules_importes(chemin):
    """Les modules de PREMIER niveau importes par un fichier, imports locaux inclus."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                yield alias.name.split(".")[0]
        elif isinstance(noeud, ast.ImportFrom):
            if noeud.level == 0 and noeud.module:
                yield noeud.module.split(".")[0]


def test_toute_dependance_des_tests_est_declaree():
    """Le contrat porte sur les TESTS : c'est eux que la CI joue.

    Les imports faits a l'interieur d'une fonction comptent autant que ceux du haut du
    fichier — `fontTools` etait importe dans le corps d'un test, ce qui l'a rendu
    d'autant plus discret.
    """
    requirements = (_RACINE / "requirements.txt").read_text(encoding="utf-8").lower()

    manquants = {}
    for fichier in sorted((_RACINE / "tests").rglob("*.py")):
        for module in _modules_importes(fichier):
            if module in sys.stdlib_module_names or module in _LOCAUX:
                continue
            paquet = _NOM_PAQUET.get(module, module).lower()
            if paquet not in requirements:
                manquants.setdefault(paquet, set()).add(fichier.name)

    assert not manquants, (
        "ces dependances sont utilisees par la suite mais absentes de "
        f"requirements.txt — la CI tombera dessus : "
        + ", ".join(f"{p} ({', '.join(sorted(f))})" for p, f in sorted(manquants.items()))
    )


def test_le_lecteur_de_cmap_est_declare():
    """Garde nommee sur le cas reel, pour que le message soit lisible s'il revient :
    seule la `cmap` dit si une police possede un caractere — le rendu, lui, dessine la
    boite .notdef sans rien signaler."""
    requirements = (_RACINE / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "fonttools" in requirements
