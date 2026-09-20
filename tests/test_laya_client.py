# -*- coding: utf-8 -*-
"""Le service Laya est PARTAGÉ : sa panne doit coûter une amélioration, jamais un bot.

Six bots derrière un seul service, c'est un point de passage commun — l'inverse de ce
que `decision-independance-stricte-vendoring-core` protège. Arbitrage de l'utilisateur
le 2026-09-20 : acceptable tant que tout tourne sur une machine, à revoir le jour d'un
serveur à part. Ce qui rend l'arbitrage tenable, c'est que le client soit inoffensif —
et c'est ce que ces verrous tiennent, parce qu'une seule ligne suffirait à les perdre.

Les trois règles, dans l'ordre où elles cassent si on ne les surveille pas :
  1. BORNE DURE — sinon un service lent devient un bot lent, sur CHAQUE message ;
  2. TOUTE panne rend le REPLI — jamais None, jamais une exception qui remonte ;
  3. AUCUN ÉTAT — pas de cache : deux bots ne s'influencent pas à travers le service.
"""
import ast
import asyncio
import importlib
import os
import sys

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)


def _client(monkeypatch, url="http://bots-laya:8700", borne="0.3"):
    monkeypatch.setenv("LAYA_URL", url)
    monkeypatch.setenv("LAYA_BORNE_S", borne)
    from shared import laya_client
    return importlib.reload(laya_client)


def test_sans_URL_le_client_rend_le_repli_sans_rien_appeler(monkeypatch):
    """L'état par défaut : tant qu'un bot n'est pas branché, il garde son comportement."""
    lc = _client(monkeypatch, url="")
    etiquette, source, conf = asyncio.run(lc.choisir("coucou", "q", {}, repli="bavardage"))
    assert (etiquette, source, conf) == ("bavardage", "repli", None)


def test_un_service_INJOIGNABLE_rend_le_repli(monkeypatch):
    """Port fermé : l'exception réseau ne doit jamais remonter jusqu'au bot."""
    lc = _client(monkeypatch, url="http://127.0.0.1:9")  # port « discard », rien n'écoute
    etiquette, source, _ = asyncio.run(
        lc.choisir("Alfred repos", "intention", {}, repli="repos"))
    assert (etiquette, source) == ("repos", "repli")


def test_un_service_LENT_rend_le_repli_avant_la_borne(monkeypatch):
    """Sans borne dure, un service lent devient un bot lent sur chaque message."""
    lc = _client(monkeypatch, url="http://10.255.255.1:8700", borne="0.2")  # non routable
    import time
    t0 = time.perf_counter()
    etiquette, source, _ = asyncio.run(
        lc.choisir("Alfred repos", "intention", {}, repli="repos"))
    ecoule = time.perf_counter() - t0
    assert (etiquette, source) == ("repos", "repli")
    assert ecoule < 2.0, f"le client a attendu {ecoule:.2f}s malgré une borne de 0,2s"


def test_une_reponse_ILLISIBLE_rend_le_repli(monkeypatch):
    """`answers[q]` est un dict ; un jour où le service changera de forme, on replie."""
    lc = _client(monkeypatch)

    class _Fausse:
        status = 200
        async def json(self):  # noqa: D401 — forme inattendue, volontairement
            return {"answers": {"intention": "repos"}}   # chaîne au lieu d'un dict
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _Session:
        def __init__(self, *a, **k): pass
        def post(self, *a, **k): return _Fausse()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", _Session)
    etiquette, source, _ = asyncio.run(
        lc.choisir("x", "intention", {}, repli="bavardage"))
    assert (etiquette, source) == ("bavardage", "repli")


def test_une_reponse_VALIDE_est_lue_dans_le_dict(monkeypatch):
    """Le cas nominal — et il vérifie qu'on lit bien `brut[brut['type']]`."""
    lc = _client(monkeypatch)

    class _Vraie:
        status = 200
        async def json(self):
            return {"answers": {"intention": {
                "type": "choice", "choice": "bavardage",
                "probabilities": {"bavardage": 0.8}, "confidence": 0.36}}}
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    class _Session:
        def __init__(self, *a, **k): pass
        def post(self, *a, **k): return _Vraie()
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", _Session)
    etiquette, source, conf = asyncio.run(
        lc.choisir("Alfred arrete de parler la", "intention", {}, repli="repos"))
    assert (etiquette, source, conf) == ("bavardage", "laya", 0.36)


def test_le_client_ne_garde_AUCUN_etat():
    """Pas de cache : un redémarrage du service ne perd rien, et les bots ne se parlent pas.

    On vérifie la STRUCTURE, pas un comportement : un cache s'ajoute en une ligne, et il
    ne se verrait que le jour où deux bots se répondraient l'un pour l'autre.
    """
    source = open(os.path.join(_parent_dir, "shared", "laya_client.py"),
                  encoding="utf-8").read()
    arbre = ast.parse(source)
    globales = {t.id for n in ast.walk(arbre) if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)}
    # Seuls des scalaires de configuration sont tolérés au niveau module.
    interdits = {g for g in globales if g.lower().endswith(("cache", "memoire", "_vu"))}
    assert not interdits, f"le client garde un état : {interdits}"
    assert "lru_cache" not in source, "un cache masquerait les pannes du service"


def test_alfred_passe_bien_son_REPLI_au_client():
    """Le plancher d'Alfred reste sa règle en place, quoi qu'il arrive au service.

    ⚠️ Lu par `ast` : un `repli=` cité dans un commentaire ne protège rien
    ([[gotcha-test-qui-retape-la-logique]]). C'est l'argument NOMMÉ qu'on exige, parce
    qu'un appel positionnel le rendrait silencieusement optionnel.
    """
    chemin = os.path.join(_parent_dir, "Alfred", "bot_alfred.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename="bot_alfred.py")
    appels = [n for n in ast.walk(arbre) if isinstance(n, ast.Call)
              and getattr(n.func, "id", None) == "choisir"]
    assert appels, "Alfred n'appelle jamais choisir()"
    for appel in appels:
        noms = {k.arg for k in appel.keywords}
        assert "repli" in noms, (
            "choisir() est appelé sans `repli=` nommé : sans lui, une panne du service "
            "partagé changerait le comportement d'Alfred au lieu de le laisser intact"
        )
