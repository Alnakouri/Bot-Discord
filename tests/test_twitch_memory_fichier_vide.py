# -*- coding: utf-8 -*-
"""Verrou : un fichier d'état vide est du NOMINAL, jamais une ERROR.

`data/twitch_viewers_johnny.json` faisait 0 octet, et `_load_viewers_state`
criait `ERROR` à chaque lecture — 3 des 13 erreurs « actives » du tableau de
bord venaient de là. Son jumeau `_load_viewer_facts`, dix lignes plus bas dans
le même fichier, avait déjà le garde : la correction n'avait été appliquée
qu'à un lecteur sur deux.
"""

import ast
import logging
from pathlib import Path

import pytest

from shared.twitch.memory import ViewerMemoryMixin

_SOURCE = Path(ViewerMemoryMixin.__module__.replace(".", "/") + ".py")
_LECTEURS = ("_load_viewers_state", "_load_viewer_facts")


class _Faux(ViewerMemoryMixin):
    def __init__(self, bot_id, logger):
        self.bot_id = bot_id
        self.logger = logger


@pytest.fixture
def journal():
    return logging.getLogger("test_twitch_memory_fichier_vide")


@pytest.mark.parametrize("lecteur,prefixe", [
    ("_load_viewers_state", "twitch_viewers_"),
    ("_load_viewer_facts", "twitch_facts_"),
])
def test_fichier_vide_rend_un_dict_vide_sans_crier(lecteur, prefixe, tmp_path,
                                                   monkeypatch, journal, caplog):
    monkeypatch.setattr("shared.twitch.memory.DATA_DIR", str(tmp_path))
    (tmp_path / f"{prefixe}johnny.json").write_text("", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        resultat = getattr(_Faux("johnny", journal), lecteur)()

    assert resultat == {}, f"{lecteur} doit rendre {{}} sur un fichier vide"
    assert not caplog.records, (
        f"{lecteur} a journalise sur un fichier vide : "
        f"{[r.getMessage() for r in caplog.records]}"
    )


def test_aucun_lecteur_d_etat_ne_journalise_en_error():
    """Un état illisible est ignorable : il se journalise en WARNING, pas en ERROR.

    Verrou AST — une ERROR ici remonte au tableau de bord des pannes et noie les
    vraies (gotcha-alerte-qui-crie-pour-du-nominal).
    """
    arbre = ast.parse(_SOURCE.read_text(encoding="utf-8"), filename=str(_SOURCE))
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.FunctionDef) and n.name in _LECTEURS):
            continue
        for sous in ast.walk(n):
            if (isinstance(sous, ast.Call) and isinstance(sous.func, ast.Attribute)
                    and sous.func.attr == "error"
                    and isinstance(sous.func.value, ast.Attribute)
                    and sous.func.value.attr == "logger"):
                pytest.fail(
                    f"{n.name} ligne {sous.lineno} : `self.logger.error` sur la "
                    "lecture d'un etat optionnel. Utiliser `warning`."
                )


def test_les_deux_lecteurs_ont_le_garde_fichier_vide():
    """Verrou jumeaux : les DEUX lecteurs lisent puis `.strip()` avant de parser.

    `json.load(f)` direct leve sur un fichier vide — c'est le montage qui a
    produit la panne (gotcha-un-bot-sur-six-manque-toujours, version 1 sur 2).
    """
    arbre = ast.parse(_SOURCE.read_text(encoding="utf-8"), filename=str(_SOURCE))
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.FunctionDef) and n.name in _LECTEURS):
            continue
        strip = any(
            isinstance(s, ast.Call) and isinstance(s.func, ast.Attribute)
            and s.func.attr == "strip"
            for s in ast.walk(n)
        )
        assert strip, f"{n.name} ne passe pas par `.read().strip()`"
        json_load_direct = any(
            isinstance(s, ast.Call) and isinstance(s.func, ast.Attribute)
            and s.func.attr == "load"
            and isinstance(s.func.value, ast.Name) and s.func.value.id == "json"
            for s in ast.walk(n)
        )
        assert not json_load_direct, (
            f"{n.name} appelle `json.load(f)`, qui leve sur un fichier vide"
        )
