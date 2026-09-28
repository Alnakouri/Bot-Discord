# -*- coding: utf-8 -*-
"""Verrous SUITE 16 : Alfred a perdu ce qui ne servait pas, et garde ce qui sert.

Mesure du 2026-09-28 : `!parle` refusait a chaque appel (ElevenLabs en 401 depuis le
30/08), `!ecoute` etait une demo jamais reliee au modele, la table `birthdays` etait
vide, et aucune partie de mini-jeu n'avait jamais ete recompensee. Decision d'Ahmed :
retirer tout cela POUR ALFRED SEUL, et GARDER la patrouille vocale (`!surveille`) avec
tout ce dont elle a besoin.

Ces verrous lisent le fichier du bot (AST) : un test qui retaperait la logique ne
prouverait rien sur ce que le conteneur execute.
"""
import ast
import asyncio
from pathlib import Path

import pytest

from shared.slash_commands import setup_slash_commands

RACINE = Path(__file__).resolve().parent.parent
ALFRED = RACINE / "Alfred" / "bot_alfred.py"
AUTRES_BOTS = [
    RACINE / "Sheogorath" / "bot_sheogorath.py",
    RACINE / "MaiqBot" / "bot_maiq.py",
    RACINE / "JohnnyBot" / "bot_johnny.py",
    RACINE / "SugarBot" / "bot_sugar.py",
    RACINE / "MalenaBot" / "bot_malena.py",
]
RETIREES_CHEZ_ALFRED = {"reputation", "leaderboard", "birthday", "quests"}
TOUTES = {"reputation", "leaderboard", "birthday", "quests", "stats", "ping", "help"}


def _arbre(chemin):
    return ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))


def _commandes_prefixe(arbre):
    """Noms des commandes `@bot.command(...)` : `name=` s'il est donne, sinon la fonction."""
    noms = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            appel = deco if isinstance(deco, ast.Call) else None
            cible = appel.func if appel else deco
            if isinstance(cible, ast.Attribute) and cible.attr == "command":
                nom = noeud.name
                for kw in (appel.keywords if appel else []):
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        nom = kw.value.value
                noms.add(nom)
    return noms


def _modules_importes(arbre):
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                yield alias.name
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            yield noeud.module


def _noms_appeles(arbre):
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Call):
            f = noeud.func
            yield f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)


def _appels(arbre, nom):
    return [n for n in ast.walk(arbre) if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) == nom or getattr(n.func, "attr", None) == nom)]


# ─────────────────────────── Alfred : ce qui part ───────────────────────────

def test_alfred_n_a_plus_ni_parle_ni_ecoute():
    commandes = _commandes_prefixe(_arbre(ALFRED))
    assert "parle" not in commandes
    assert "ecoute" not in commandes


def test_alfred_n_importe_plus_la_synthese_ni_la_reconnaissance_vocale():
    modules = set(_modules_importes(_arbre(ALFRED)))
    assert not any(m.split(".")[0] in {"elevenlabs", "speech_recognition"} for m in modules), modules


def test_alfred_ne_charge_plus_les_jeux_ni_les_anniversaires():
    arbre = _arbre(ALFRED)
    appeles = set(_noms_appeles(arbre))
    assert "setup_games" not in appeles
    assert "check_and_send_birthdays" not in appeles
    assert "shared.games" not in set(_modules_importes(arbre))


def test_alfred_ne_lit_plus_la_reputation_ni_les_quetes():
    appeles = set(_noms_appeles(_arbre(ALFRED)))
    for nom in ("get_reputation", "get_reputation_level", "get_daily_quests"):
        assert nom not in appeles, nom


# ─────────────────────────── Alfred : ce qui reste ───────────────────────────

def test_la_patrouille_vocale_est_intacte():
    arbre = _arbre(ALFRED)
    commandes = _commandes_prefixe(arbre)
    for nom in ("surveille", "repos", "liberation", "nettoyage", "servir", "oubliemoi"):
        assert nom in commandes, f"!{nom} a disparu d'Alfred"
    fonctions = {n.name for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    classes = {n.name for n in ast.walk(arbre) if isinstance(n, ast.ClassDef)}
    assert "vocal_patrol_loop" in fonctions
    assert "VocalPatrolSink" in classes


def test_audioop_reste_importe_au_niveau_module():
    """`VocalPatrolSink` convertit le PCM en mono avec `audioop` : l'import etait pose
    au milieu de la section `!ecoute` retiree, il doit avoir survecu en tete de fichier."""
    arbre = _arbre(ALFRED)
    au_module = {a.name for n in arbre.body if isinstance(n, ast.Import) for a in n.names}
    assert "audioop" in au_module
    assert "wave" in au_module


def test_alfred_demande_exactement_ses_trois_commandes_slash():
    appels = _appels(_arbre(ALFRED), "setup_slash_commands")
    assert len(appels) == 1
    sans = [kw.value for kw in appels[0].keywords if kw.arg == "sans"]
    assert sans, "Alfred doit passer `sans=`"
    assert isinstance(sans[0], ast.Set)
    assert {e.value for e in sans[0].elts} == RETIREES_CHEZ_ALFRED


@pytest.mark.parametrize("chemin", AUTRES_BOTS, ids=lambda p: p.parent.name)
def test_les_cinq_autres_bots_ne_changent_pas(chemin):
    appels = _appels(_arbre(chemin), "setup_slash_commands")
    assert appels, f"{chemin.name} n'appelle plus setup_slash_commands"
    for appel in appels:
        assert not any(kw.arg == "sans" for kw in appel.keywords), chemin.name


# ─────────────────────── shared/slash_commands.py, pour de vrai ───────────────────────

class _FauxArbre:
    def __init__(self):
        self.poses = {}

    def command(self, name, **kw):
        def deco(f):
            self.poses[name] = f
            return f
        return deco


class _FauxBot:
    latency = 0.05

    def __init__(self):
        self.tree = _FauxArbre()


class _FauxEmbed:
    def __init__(self, *a, **kw):
        self.champs = []

    def add_field(self, name, value, inline=True):
        self.champs.append(name)

    def set_footer(self, **kw):
        pass


class _FausseReponse:
    def __init__(self):
        self.embed = None

    async def send_message(self, *a, embed=None, **kw):
        self.embed = embed


class _FausseInteraction:
    def __init__(self):
        self.response = _FausseReponse()


def _aide(bot, monkeypatch):
    import shared.slash_commands as module
    monkeypatch.setattr(module.discord, "Embed", _FauxEmbed)
    interaction = _FausseInteraction()
    asyncio.run(bot.tree.poses["help"](interaction))
    return interaction.response.embed.champs


def test_par_defaut_les_sept_commandes_sont_posees(monkeypatch):
    bot = _FauxBot()
    setup_slash_commands(bot, "Test")
    assert set(bot.tree.poses) == TOUTES
    assert len(_aide(bot, monkeypatch)) == 6


def test_avec_le_sans_d_alfred_il_reste_ping_stats_help(monkeypatch):
    bot = _FauxBot()
    setup_slash_commands(bot, "Alfred", sans=RETIREES_CHEZ_ALFRED)
    assert set(bot.tree.poses) == {"ping", "stats", "help"}
    lignes = _aide(bot, monkeypatch)
    assert lignes == ["/stats", "/ping"]
    for nom in RETIREES_CHEZ_ALFRED:
        assert not any(nom in ligne for ligne in lignes), f"/help promet encore /{nom}"


def test_un_nom_inconnu_dans_sans_leve():
    with pytest.raises(ValueError):
        setup_slash_commands(_FauxBot(), "Test", sans={"inconnue"})
