"""NVIDIA doit etre joignable par les SIX bots, pas seulement par le noyau.

Le 2026-09-04, NVIDIA a ete ajoute comme 4e fournisseur. `get_model_cascade()` rend bien
`nvidia` en dernier echelon pour les six personas. Pourtant, au 2026-09-05, **NVIDIA
n'avait jamais servi un seul message** :

* Sheogorath, Alfred, M'aiq et Malena portent leur cascade **INLINE** dans `on_message`.
  Le lot du 04/09 n'avait cable que `shared/llm_cascade.py` et ses copies vendorisees :
  ces quatre-la n'avaient aucune branche `client_type == "nvidia"`, donc l'echelon
  tombait dans le vide sans un mot dans les logs.
* Johnny et Sugar passent bien par le noyau, mais n'importaient pas `NVIDIA_BASE_URL` :
  la construction du client levait un `NameError` **avale par son propre `except`**, et
  `nvidia_client` restait None.

⚠️ C'est la cause commune de l'audit du 04/09 sous sa forme la plus pure : un correctif
pose dans `shared/` ne descend PAS dans les quatre cascades recopiees, et le health check
du demarrage annoncait « NVIDIA : Oui » parce qu'il regarde la CLE, jamais le cablage.

Ces tests lisent la STRUCTURE des fichiers : ils n'ont besoin d'aucune cle et disent donc
la meme chose ici et en CI ([[feedback-le-local-ment-sans-cles]]).
"""
import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

BOTS = {
    "Alfred": "bot_alfred.py",
    "JohnnyBot": "bot_johnny.py",
    "MaiqBot": "bot_maiq.py",
    "MalenaBot": "bot_malena.py",
    "Sheogorath": "bot_sheogorath.py",
    "SugarBot": "bot_sugar.py",
}

# Les 4 bots qui recopient la cascade dans leur `on_message`. Johnny et Sugar appellent
# `generate_response()` du noyau, qui porte deja la branche.
CASCADES_INLINE = {
    "Alfred": "bot_alfred.py",
    "MaiqBot": "bot_maiq.py",
    "MalenaBot": "bot_malena.py",
    "Sheogorath": "bot_sheogorath.py",
}


def _source(dossier, fichier):
    return (RACINE / dossier / fichier).read_text(encoding="utf-8")


def _noms_du_module(src):
    """Les noms qu'un `import` ou une affectation rend disponibles dans le module."""
    arbre = ast.parse(src)
    noms = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Assign):
            noms |= {c.id for c in noeud.targets if isinstance(c, ast.Name)}
        elif isinstance(noeud, (ast.Import, ast.ImportFrom)):
            noms |= {(a.asname or a.name).split(".")[0] for a in noeud.names}
        elif isinstance(noeud, ast.FunctionDef):
            noms.add(noeud.name)
    return noms


def test_les_4_cascades_inline_ont_une_branche_nvidia():
    """Sans branche, l'echelon `nvidia` est saute EN SILENCE — pas meme un log."""
    manquants = [
        f"{dossier}/{fichier}"
        for dossier, fichier in CASCADES_INLINE.items()
        if 'client_type == "nvidia"' not in _source(dossier, fichier)
    ]
    assert not manquants, (
        "Ces cascades inline ignorent le 4e fournisseur : la cascade rend bien un "
        "echelon `nvidia`, aucune branche ne le sert.\n  " + "\n  ".join(manquants)
    )


def test_la_branche_nvidia_coupe_la_fuite_de_raisonnement():
    """⚠️ Une branche NVIDIA sans `nvidia_kwargs()` fait RECITER son raisonnement au bot.

    Mesure du 04/09 : 6 779 ms de meta-discours sans le parametre, 1 001 ms avec. Malena
    a deja recite son raisonnement en plein Discord une fois. Le filet
    `_fuite_de_raisonnement()` doit doubler le parametre, au cas ou il cesse d'etre
    honore.
    """
    fautifs = []
    for dossier, fichier in CASCADES_INLINE.items():
        src = _source(dossier, fichier)
        debut = src.index('client_type == "nvidia"')
        # La branche court jusqu'au `except` du tour de cascade.
        fin = src.index("except Exception as e:", debut)
        branche = src[debut:fin]
        for exigence in ("nvidia_kwargs(", "_fuite_de_raisonnement(", "_est_vide("):
            if exigence not in branche:
                fautifs.append(f"{fichier} : branche nvidia sans {exigence}")
    assert not fautifs, "\n  " + "\n  ".join(fautifs)


def test_les_6_bots_definissent_vraiment_leur_client_nvidia():
    """Le piege : `NVIDIA_BASE_URL` non importe, `NameError` avale par le `except`.

        try: nvidia_client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_BASE_URL, ...)
        except Exception as e: logger.warning(f'[NVIDIA] client indisponible: {e}')

    Le bot demarre, annonce « NVIDIA : Oui » (il regarde la cle) et n'a pas de client.
    """
    fautifs = []
    inspectes = 0
    for dossier, fichier in BOTS.items():
        src = _source(dossier, fichier)
        noms = _noms_du_module(src)
        for appel in re.findall(r"OpenAI\([^)]*NVIDIA[^)]*\)", src):
            inspectes += 1
            for nom in re.findall(r"\b(NVIDIA_\w+)\b", appel):
                if nom not in noms:
                    fautifs.append(f"{fichier} : {nom} n'est ni importe ni defini")
    assert inspectes == 6, f"On attendait 1 client NVIDIA par bot, on en a inspecte {inspectes}"
    assert not fautifs, "\n  " + "\n  ".join(fautifs)


def test_les_helpers_ne_sont_pas_recopies_une_8e_fois():
    """⚠️ Les 4 cascades inline IMPORTENT les gardes, elles ne les redefinissent pas.

    Il existe deja 7 copies du noyau ([[decision-independance-stricte-vendoring-core]]).
    Une 8e copie du garde anti-fuite dans un `bot_*.py` serait un endroit de plus a
    oublier le jour ou il change. Malena est l'exception historique assumee : ses helpers
    sont locaux depuis sa cascade d'origine.
    """
    for dossier, fichier in CASCADES_INLINE.items():
        if dossier == "MalenaBot":
            continue
        src = _source(dossier, fichier)
        assert "def _fuite_de_raisonnement" not in src, (
            f"{fichier} redefinit _fuite_de_raisonnement au lieu de l'importer du noyau"
        )
        assert "from core.llm_cascade import" in src, (
            f"{fichier} n'importe rien du noyau : d'ou viennent ses gardes ?"
        )
