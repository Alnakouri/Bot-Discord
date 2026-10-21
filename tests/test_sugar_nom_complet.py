# -*- coding: utf-8 -*-
"""Sugar ne répond qu'à son nom COMPLET (« sugarbot » / « sugar bot »), sur Discord et Twitch.

« Sugar » tout court est le nom que le chat donne à la streameuse (ma_streameuse) : le bot
répondait à sa place, et intervenait en plus au hasard sur Discord (10 %). Les verrous lisent
le VRAI fichier du bot (AST) : `bot_sugar.py` importe discord et ne s'importe pas en test.
"""
import ast
import os
import re
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.twitch_chat import TwitchChatBot

_FICHIER = os.path.join(_parent_dir, "SugarBot", "bot_sugar.py")
with open(_FICHIER, "r", encoding="utf-8") as _f:
    _ARBRE = ast.parse(_f.read())

# Phrases que le chat adresse à la STREAMEUSE : aucune ne doit réveiller le bot.
_POUR_LA_STREAMEUSE = [
    "Sugar, tu joues à quoi demain ?",
    "salut sugar",
    "ma_streameuse est en live",
    "gg sugar !",
]
_POUR_LE_BOT = ["SugarBot t'en penses quoi", "sugar bot dis bonjour", "@SugarBot", "Sugar Bot ?"]


def _regle_du_bot():
    """Exécute les VRAIES affectations SUGARBOT_TERMS / SUGARBOT_RE de bot_sugar.py."""
    noeuds = [n for n in _ARBRE.body if isinstance(n, ast.Assign)
              and any(isinstance(c, ast.Name) and c.id in ("SUGARBOT_TERMS", "SUGARBOT_RE")
                      for c in n.targets)]
    assert len(noeuds) == 2, "SUGARBOT_TERMS et SUGARBOT_RE doivent être définis au niveau module"
    ns = {"re": re}
    exec(compile(ast.Module(body=noeuds, type_ignores=[]), _FICHIER, "exec"), ns)
    return ns["SUGARBOT_TERMS"], ns["SUGARBOT_RE"]


def _on_message():
    for n in _ARBRE.body:
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_message":
            return n
    raise AssertionError("on_message introuvable dans bot_sugar.py")


def test_discord_ne_repond_pas_au_prenom_seul():
    termes, regle = _regle_du_bot()
    assert "sugar" not in termes
    for phrase in _POUR_LA_STREAMEUSE:
        assert not regle.search(phrase), f"Discord réveille Sugar sur : {phrase!r}"
    for phrase in _POUR_LE_BOT:
        assert regle.search(phrase), f"Discord ignore : {phrase!r}"


def test_discord_le_nom_passe_par_la_regle():
    """`is_name_mentioned` doit venir de SUGARBOT_RE, pas d'une liste recopiée."""
    for n in ast.walk(_on_message()):
        if isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id == "is_name_mentioned" for c in n.targets):
            assert "SUGARBOT_RE" in ast.unparse(n.value)
            return
    raise AssertionError("is_name_mentioned n'est plus calculé dans on_message")


def test_discord_plus_d_intervention_au_hasard():
    """Plus aucun tirage dans on_message : Sugar ne parle que si on l'appelle."""
    for n in ast.walk(_on_message()):
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "random.random":
            raise AssertionError(f"tirage aléatoire dans on_message, ligne {n.lineno}")


def test_twitch_recoit_les_memes_termes():
    for n in ast.walk(_ARBRE):
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "setup_twitch_chat":
            kw = {k.arg: ast.unparse(k.value) for k in n.keywords}
            assert kw.get("trigger_terms") == "SUGARBOT_TERMS"
            return
    raise AssertionError("setup_twitch_chat introuvable dans bot_sugar.py")


def _twitch(**kw):
    return TwitchChatBot(bot_id=kw.pop("bot_id", "sugar"), logger=__import__("logging").getLogger("t"),
                         username=kw.pop("username", "compte_bot_sugar"), channels=["x"],
                         client_id="a", client_secret="b", auth=None, **kw)


def test_twitch_trigger_terms_remplace_les_noms_deduits():
    termes, _ = _regle_du_bot()
    bot = _twitch(bot_label="Sugar Bot", trigger_terms=termes)
    for phrase in _POUR_LA_STREAMEUSE:
        assert not bot.trigger_re.search(phrase), f"Twitch réveille Sugar sur : {phrase!r}"
    for phrase in _POUR_LE_BOT + ["@compte_bot_sugar coucou"]:
        assert bot.trigger_re.search(phrase), f"Twitch ignore : {phrase!r}"


def test_twitch_sans_trigger_terms_rien_ne_change():
    """Les cinq autres bots ne passent pas `trigger_terms` : nom court toujours actif."""
    bot = _twitch(bot_id="johnny", username="johnnybot", bot_label="Johnny")
    assert bot.trigger_re.search("salut johnny")
    assert bot.trigger_re.search("@johnnybot")
