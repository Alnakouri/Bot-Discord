# -*- coding: utf-8 -*-
"""Verrous SUITE 14 : Sugar ne réécrit plus mot pour mot une phrase qu'elle a déjà envoyée.

Vérifie que :
1. Une phrase déjà écrite dans les 20 dernières générations est rejetée par le filet
   au 1er essai, et le 2e essai est tenté.
2. Si deux redites consécutives surviennent, la génération rend None (gabarit fixe).
3. _empreinte_phrase ignore casse, ponctuation, emoji et espaces.
4. La mémoire est bornée à MEMOIRE_PHRASES_DE_LIEN (20).
5. Le registre est isolé par commande (ex. !discord et !insta).
6. Le cache de 900s n'est pas vu comme un doublon.
7. Verrou AST sur shared/twitch/dispatch.py.
"""
import ast
import asyncio
from pathlib import Path
import pytest

from shared.twitch.dispatch import DispatchMixin, _empreinte_phrase

URL = "https://discord.gg/exemple"


class _Journal:
    def __init__(self):
        self.lignes = []

    def info(self, msg):
        self.lignes.append(msg)

    warning = error = debug = info


class _BotFactice(DispatchMixin):
    bot_id = "sugar"
    bot_label = "Sugar"
    personality_prompt = "tu es Sugar"
    system_prompt_provider = None
    key_manager = object()
    mistral_client = groq_client = nvidia_client = None

    def __init__(self):
        self.logger = _Journal()

    async def _canal_en_direct(self, chan: str) -> bool:
        return True

    async def _jeu_en_cours(self):
        return None

    async def _fiche_du_jeu(self):
        return None


@pytest.fixture(autouse=True)
def _restaurer_cascade():
    """Restaure `cascade.generate_response` pour ne pas polluer les autres suites de tests."""
    import shared.llm_cascade as cascade
    orig = cascade.generate_response
    try:
        yield
    finally:
        cascade.generate_response = orig


def _avec_reponses(textes):
    """Faux modèle retournant successivement les phrases fournies."""
    import shared.llm_cascade as cascade
    compteur = {"n": 0}
    it = iter(textes)

    async def _faux(**kwargs):
        compteur["n"] += 1
        try:
            return next(it)
        except StopIteration:
            return None

    cascade.generate_response = _faux
    bot = _BotFactice()
    return bot, compteur


def test_1_cas_vecu_redite_rejetee(monkeypatch):
    """1. Le cas vécu : textes [A, A, B].
    1re génération -> A. 2e génération (cache expiré) -> 1er essai est A (rejeté),
    2e essai rend B. 3 appels au total, ligne 'deja ecrite' dans le journal.
    """
    phrase_a = "Entre Henri, les lames… ? Venez sur Discord ! 🗡️"
    phrase_b = "Une autre question ?"
    textes = [phrase_a, phrase_a, phrase_b]
    bot, compteur = _avec_reponses(textes)

    t_actuel = [0.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    # 1re génération
    r1 = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r1 is not None
    assert phrase_a in r1
    assert compteur["n"] == 1

    # 2e génération : cache expiré (t=901)
    t_actuel[0] = 901.0
    r2 = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r2 is not None
    assert phrase_b in r2
    assert compteur["n"] == 3
    assert any("deja ecrite" in l for l in bot.logger.lignes)


def test_2_deux_redites_de_suite_rend_none(monkeypatch):
    """2. Deux redites de suite -> gabarit fixe : textes [A, A, A] -> rend None."""
    phrase_a = "Entre Henri, les lames… ? Venez sur Discord ! 🗡️"
    textes = [phrase_a, phrase_a, phrase_a]
    bot, compteur = _avec_reponses(textes)

    t_actuel = [0.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    r1 = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r1 is not None

    t_actuel[0] = 901.0
    r2 = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r2 is None
    assert compteur["n"] == 3


def test_3_empreinte_ignore_casse_ponctuation_emoji_espaces():
    """3. L'empreinte ignore casse, ponctuation, emoji et espaces."""
    assert _empreinte_phrase("Venez  sur Discord ! 🗡️") == _empreinte_phrase("venez sur discord !!")
    assert _empreinte_phrase("Venez sur Discord") != _empreinte_phrase("Partez sur Discord")


def test_4_memoire_est_bornee(monkeypatch):
    """4. La mémoire est bornée : 21 phrases distinctes puis la 1re à nouveau -> acceptée."""
    n_memoire = DispatchMixin.MEMOIRE_PHRASES_DE_LIEN
    phrases = [f"Venez découvrir la surprise numéro {i} avec nous" for i in range(n_memoire + 1)]
    textes = phrases + [phrases[0]]
    bot, compteur = _avec_reponses(textes)

    t_actuel = [0.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    for i in range(n_memoire + 1):
        t_actuel[0] += 901.0
        r = asyncio.run(bot._generate_link_line("discord", "discord", URL))
        assert r is not None
        assert phrases[i] in r

    t_actuel[0] += 901.0
    r_rep = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r_rep is not None
    assert phrases[0] in r_rep


def test_5_par_commande_pas_partage(monkeypatch):
    """5. Par commande : la même phrase pour !discord puis pour !insta -> acceptée les 2 fois."""
    phrase = "Venez donc voir le serveur !"
    textes = [phrase, phrase]
    bot, compteur = _avec_reponses(textes)

    t_actuel = [0.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    r_discord = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r_discord is not None
    assert phrase in r_discord

    t_actuel[0] = 901.0
    r_insta = asyncio.run(bot._generate_link_line("insta", "instagram", "https://instagram.com/test"))
    assert r_insta is not None
    assert phrase in r_insta
    assert compteur["n"] == 2


def test_6_cache_n_est_pas_un_doublon(monkeypatch):
    """6. Le cache n'est pas un doublon : deux appels à moins de 900 s -> même phrase, 1 appel."""
    phrase = "Venez donc voir le serveur !"
    bot, compteur = _avec_reponses([phrase])

    t_actuel = [0.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    r1 = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r1 is not None

    t_actuel[0] = 50.0  # moins de 900s
    r2 = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert r2 == r1
    assert compteur["n"] == 1
    assert not any("deja ecrite" in l for l in bot.logger.lignes)


def test_7_verrou_ast_dispatch():
    """7. Verrou AST sur shared/twitch/dispatch.py."""
    fichier = Path(__file__).resolve().parent.parent / "shared" / "twitch" / "dispatch.py"
    arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))

    gen_func = None
    for node in ast.walk(arbre):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_generate_link_line":
            gen_func = node
            break
    assert gen_func is not None, "méthode _generate_link_line introuvable"

    boucle_essai = None
    for node in ast.walk(gen_func):
        if isinstance(node, ast.For) and getattr(node.target, "id", "") == "essai":
            boucle_essai = node
            break
    assert boucle_essai is not None, "boucle for essai in (1, 2) introuvable"

    appels_dans_boucle = [
        n for n in ast.walk(boucle_essai)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_empreinte_phrase"
    ]
    assert len(appels_dans_boucle) >= 1, "aucun appel à _empreinte_phrase dans la boucle for essai"

    noeuds_boucle = set(ast.walk(boucle_essai))
    appels_append_hors_boucle = []
    for node in ast.walk(gen_func):
        if node in noeuds_boucle:
            continue
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append":
            for arg in node.args:
                if isinstance(arg, ast.Call) and getattr(arg.func, "id", "") == "_empreinte_phrase":
                    appels_append_hors_boucle.append(node)

    assert len(appels_append_hors_boucle) >= 1, (
        "aucun appel à .append(_empreinte_phrase(...)) trouvé hors de la boucle for essai"
    )
