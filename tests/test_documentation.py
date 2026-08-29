# -*- coding: utf-8 -*-
"""La documentation ne doit pas mentir.

Constaté le 2026-08-26 en ouvrant le dépôt sur GitHub : le README annonçait encore trois
modèles morts depuis l'audit du 24 août (deux Gemini d'une génération retirée et un Grok
qui n'existe plus chez OpenRouter) et décrivait Sugar Bot comme « personnalité vidée ».
Par ailleurs **73 liens** pointaient vers un chemin absolu de cette machine, donc cassés
pour quiconque lit ailleurs.

Les identifiants morts ne sont volontairement PAS écrits en toutes lettres ici : ils sont
lus depuis `test_model_ids`, qui est le seul fichier que son propre scan s'autorise à
ignorer.

`test_model_ids` ne scannait que les `.py`. La doc pourrissait sans filet.
"""
import os
import re
import sys
import subprocess
import urllib.parse
from pathlib import Path

import pytest

_racine = Path(__file__).resolve().parent.parent
if str(_racine) not in sys.path:
    sys.path.insert(0, str(_racine))

# Dossiers hors projet : environnements virtuels, dépendances, historique git.
_IGNORES = {".git", ".venv", ".venv-stt", "node_modules", "__pycache__",
            "ollama_storage", "piper-data", "chroma.sqlite3"}

# Documents décrivant l'ÉTAT ACTUEL. Les changelogs datés en sont exclus : ils citent
# légitimement les modèles en vigueur à l'époque, et réécrire l'histoire serait pire.
_ETAT_COURANT = ["README.md", "ARCHITECTURE.md", "API_KEYS_SETUP.md", "MAINTENANCE.md"]

# Liste lue a la source (test_model_ids) plutot que recopiee : une copie de ces motifs
# dans un autre fichier .py declencherait le scan de test_model_ids sur elle-meme.
from tests.test_model_ids import DEAD_PATTERNS   # tests/ est un paquet

# Les familles entierement retirees du projet, ecrites SANS citer d'identifiant complet
# pour la meme raison.
MODELES_MORTS = DEAD_PATTERNS + [
    "gemini-" + r"2\.0",
    "gemini-" + r"1\.5",
    "x-" + "ai/grok",
]


def _documents():
    for f in sorted(_racine.rglob("*.md")):
        if any(p in _IGNORES for p in f.parts):
            continue
        yield f


def test_il_y_a_bien_des_documents_a_verifier():
    """Un filtre trop large rendrait tous les tests suivants verts pour rien."""
    assert len(list(_documents())) >= 10


@pytest.mark.parametrize("nom", _ETAT_COURANT)
def test_aucun_modele_mort_dans_les_documents_d_etat(nom):
    chemin = _racine / nom
    if not chemin.exists():
        pytest.skip(f"{nom} absent")
    contenu = chemin.read_text(encoding="utf-8")
    trouves = [m for m in MODELES_MORTS if re.search(m, contenu)]
    assert not trouves, (
        f"{nom} cite des modèles morts : {trouves}. "
        "Les identifiants ne se recopient pas dans la doc — renvoyer vers shared/models.py."
    )


def test_aucun_lien_absolu_vers_cette_machine():
    """`file:///I:/...` marche sur un seul poste et nulle part ailleurs."""
    coupables = []
    for f in _documents():
        contenu = f.read_text(encoding="utf-8")
        if "file:///" in contenu or re.search(r"\]\([A-Za-z]:[\\/]", contenu):
            coupables.append(f.relative_to(_racine).as_posix())
    assert not coupables, f"liens absolus locaux dans : {coupables}"


def test_les_liens_internes_pointent_sur_des_fichiers_existants():
    """Un lien mort est une doc qui ment, en plus discret.

    Exister sur ce poste ne suffit pas : un lien vers un fichier GÉNÉRÉ et écarté par
    `.gitignore` (une base SQLite, un cache) passe en local et casse sur un clone frais.
    Vu le 2026-08-29 : `DEV_GUIDE.md -> data/bots_database.db` tenait uniquement parce
    qu'un test créait la base au passage ; le jour où ce test a cessé d'écrire dans
    `data/`, la CI est tombée sur un lien mort depuis des mois. Même famille que le
    `.gitignore` non ancré qui avait avalé `shared/test_mode.py` (`c1b0696`) : ce qui
    n'est pas dans le dépôt n'existe pas ailleurs que sur la machine qui l'a fabriqué.
    """
    casses = []
    for f in _documents():
        for m in re.finditer(r"\[([^\]]*)\]\(([^)\s]+)\)", f.read_text(encoding="utf-8")):
            cible = m.group(2)
            if cible.startswith(("http://", "https://", "#", "mailto:")):
                continue
            brut = urllib.parse.unquote(cible.split("#")[0])
            if not brut:
                continue
            chemin = f.parent / brut
            if not chemin.exists():
                casses.append(f"{f.relative_to(_racine).as_posix()} -> {cible} (absent)")
            elif subprocess.run(
                ["git", "check-ignore", "-q", str(chemin)],
                cwd=_racine, capture_output=True,
            ).returncode == 0:
                casses.append(
                    f"{f.relative_to(_racine).as_posix()} -> {cible} "
                    "(écarté par .gitignore : absent d'un clone frais)"
                )
    assert not casses, "liens internes cassés :\n  " + "\n  ".join(casses)


def test_le_readme_decrit_les_six_bots():
    """Sugar Bot y est restée « (personnalité vidée) » longtemps après avoir eu la sienne."""
    contenu = (_racine / "README.md").read_text(encoding="utf-8")
    for bot in ["Sheogorath", "M'aiq", "Alfred", "Johnny", "Sugar Bot", "Malena"]:
        assert bot in contenu, f"{bot} absent du README"
    assert "personnalité vidée" not in contenu


def test_le_readme_documente_ce_qui_change_le_deploiement():
    """Ces trois faits changent la façon de travailler sur le dépôt : les omettre fait
    perdre du temps à quiconque arrive dessus."""
    contenu = (_racine / "README.md").read_text(encoding="utf-8")
    assert "vendor_core.py" in contenu, "le vendoring du noyau n'est pas documenté"
    assert "sonde_core_drift.py" in contenu, "la sonde de dérive n'est pas documentée"
    assert "Mode test" in contenu, "le mode test n'est pas documenté"


def test_les_modeles_cites_dans_le_readme_existent_vraiment():
    """Le README nomme des modèles pour expliquer les choix : ils doivent au moins être
    ceux que le code utilise."""
    from shared.models import CASCADES_PERSONA, CASCADE_ANNONCE
    from shared.smart_router import get_model_cascade, RequestType

    contenu = (_racine / "README.md").read_text(encoding="utf-8")
    utilises = {m for c in CASCADES_PERSONA.values() for _, m in c}
    utilises |= {m for _, m in CASCADE_ANNONCE}
    # Vision et raisonnement ne sont pas personnalisés : leurs modèles ne sont dans
    # aucune cascade de persona, mais ils sont bel et bien utilisés.
    for type_requete in (RequestType.TEXT, RequestType.REPARTEE, RequestType.IMAGE,
                         RequestType.AUDIO, RequestType.REASONING):
        utilises |= {m for _, m in get_model_cascade(type_requete)}

    cites = set(re.findall(r"`([a-z0-9][a-z0-9./:-]*(?:-latest|[0-9]b|lite|flash))`", contenu))
    inconnus = {c for c in cites if "/" in c or c.startswith(("gemini", "mistral"))} - utilises
    assert not inconnus, (
        f"le README cite des modèles que le code n'utilise pas : {sorted(inconnus)}"
    )
