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
_ETAT_COURANT = ["README.md", "docs/ARCHITECTURE.md", "docs/API_KEYS_SETUP.md", "docs/MAINTENANCE.md"]

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



def _lignes_ignorees(a_verifier):
    """Rend les entrees dont le chemin est ECARTE par `.gitignore`, en UN seul appel git.

    Un fichier peut exister sur ce poste et manquer dans un clone frais : c'est arrive le
    2026-08-29 (`DEV_GUIDE.md -> data/bots_database.db`). Le test doit donc interroger git,
    mais pas une fois par lien : voir le commentaire de l'appelant.
    """
    if not a_verifier:
        return []
    entree = b"\x00".join(str(c).encode("utf-8") for _f, _c, c in a_verifier)
    res = subprocess.run(
        ["git", "check-ignore", "--stdin", "-z"],
        cwd=_racine, input=entree, capture_output=True,
    )
    # 0 = au moins un chemin ignore, 1 = aucun. Tout le reste est une vraie panne git,
    # et la taire ferait passer ce test au vert sans avoir rien verifie.
    if res.returncode not in (0, 1):
        raise AssertionError(
            f"`git check-ignore` a echoue (code {res.returncode}) : "
            f"{res.stderr.decode('utf-8', 'replace')[:200]}"
        )
    ignores = {s for s in res.stdout.decode("utf-8", "replace").split("\x00") if s}
    if not ignores:
        return []
    # git rend les chemins relatifs a la racine du depot, avec des `/`.
    def _forme_git(chemin):
        try:
            return chemin.resolve().relative_to(_racine.resolve()).as_posix()
        except ValueError:
            return str(chemin)
    return [e for e in a_verifier if _forme_git(e[2]) in ignores or str(e[2]) in ignores]


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
    a_verifier = []          # (document, cible, chemin) pour les fichiers qui EXISTENT
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
            else:
                a_verifier.append((f, cible, chemin))

    # ⚠️ UN SEUL `git check-ignore`, pas un par lien. Mesure du 2026-09-17
    # (`pytest --durations`) : ce test prenait **310 s**, plus de la moitie de toute la
    # suite, uniquement en creation de processus — Windows facture cher chaque `git`
    # lance. Le lot tient dans un appel : `--stdin` lit les chemins, `-z` les separe par
    # des NUL (indispensable ici, la racine du projet contient une espace).
    for _doc, cible, chemin in _lignes_ignorees(a_verifier):
        casses.append(
            f"{_doc.relative_to(_racine).as_posix()} -> {cible} "
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


# ---------------------------------------------------------------------------
# Une clé par bot : la règle doit être VISIBLE, et l'outil qui la vérifie exister
# ---------------------------------------------------------------------------

def test_la_regle_une_cle_par_bot_est_dans_le_fichier_lu_en_premier():
    """La règle existait dans API_KEYS_SETUP.md depuis toujours, et elle était violée :
    JohnnyBot et MalenaBot partageaient une clé Gemini (mesuré le 2026-08-30). Elle
    manquait là où les agents lisent d'abord, AGENTS.md."""
    contenu = (_racine / "AGENTS.md").read_text(encoding="utf-8")
    assert "UNE CLÉ PAR BOT" in contenu, "la règle n'est pas dans AGENTS.md"
    assert "PAS DE PARTAGE" in contenu
    assert "sonde_cles_partagees.py" in contenu, \
        "la règle est énoncée mais l'outil qui la vérifie n'est pas cité"


def test_l_outil_qui_verifie_la_regle_existe_et_ne_montre_aucune_cle():
    """Une règle qu'aucun outil ne contrôle n'est pas une règle. Et l'outil qui la
    contrôle ne doit jamais imprimer une clé en clair."""
    chemin = _racine / "tools" / "sonde_cles_partagees.py"
    assert chemin.exists(), "tools/sonde_cles_partagees.py manquant"
    src = chemin.read_text(encoding="utf-8")
    assert "hashlib.sha256" in src, "la sonde doit comparer des empreintes, pas des clés"
    assert "def empreinte" in src
    # Aucune impression directe d'une valeur de .env.
    assert "print(valeur" not in src and "print(f\"{valeur" not in src


def test_les_deux_documents_de_cles_disent_la_meme_chose():
    """API_KEYS_SETUP.md est le document de référence ; AGENTS.md le rappel. Les deux
    doivent porter la règle, sinon l'un contredit l'autre en silence."""
    for fichier in ("AGENTS.md", "docs/API_KEYS_SETUP.md"):
        contenu = (_racine / fichier).read_text(encoding="utf-8")
        assert "sonde_cles_partagees.py" in contenu, f"{fichier} ne cite pas l'outil"
        assert "PAS DE PARTAGE" in contenu.upper(), f"{fichier} n'énonce pas la règle"


def test_la_regle_dit_de_prevenir_avant_de_partager_une_cle():
    """Ajoutée le 2026-08-30 sur demande : quand une clé manque, on prévient
    l'utilisateur — on ne recopie pas celle d'un autre bot pour dépanner. C'est
    exactement comme ça qu'une clé finit mutualisée sans que personne ne l'ait décidé."""
    for fichier in ("AGENTS.md", "docs/API_KEYS_SETUP.md"):
        contenu = (_racine / fichier).read_text(encoding="utf-8").upper()
        assert "PRÉVENIR L'UTILISATEUR" in contenu or "PRÉVIENT L'UTILISATEUR" in contenu, \
            f"{fichier} : la consigne « prévenir avant de partager » manque"
        assert "NOUVEAU FOURNISSEUR" in contenu, \
            f"{fichier} : les cas qui déclenchent le signalement ne sont pas listés"


def test_aucun_document_ne_demande_de_garder_WAL():
    """AGENTS.md ordonnait de PRESERVER WAL alors que le code l'interdit depuis le 13/09 :
    un agent obeissant aurait rendu les six bots muets. Toute ligne qui parle de WAL doit
    dire qu'il est interdit."""
    fautes = []
    for nom in ("AGENTS.md", "docs/ARCHITECTURE.md", "docs/DEV_GUIDE.md"):
        for n, ligne in enumerate((_racine / nom).read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bWAL\b", ligne) and not re.search(
                    r"jamais|interdit|TRUNCATE|pas en WAL", ligne, re.IGNORECASE):
                fautes.append(f"{nom}:{n}: {ligne.strip()[:80]}")
    assert not fautes, "WAL presente comme un mode a garder :\n" + "\n".join(fautes)

