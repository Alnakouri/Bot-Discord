# -*- coding: utf-8 -*-
"""Mode test : les bots ne publient que sur le serveur privé.

La règle est FERMÉE PAR DÉFAUT. Pour une fonction dont le seul but est d'empêcher une
publication publique, se tromper dans le sens du silence est le seul sens acceptable :
mode test actif sans serveur choisi = personne ne parle, surtout pas « tout le monde
parle partout ».
"""
import json
import os
import sys

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import shared.bot_features as bf

SERVEUR_PRIVE = 111111111111111111
SERVEUR_PUBLIC = 999999999999999999


@pytest.fixture
def config(monkeypatch):
    """Remplace le fichier de configuration en mémoire, cache compris."""
    def poser(donnees):
        monkeypatch.setattr(bf, "_CACHE", {"data": donnees, "ts": float("inf")})
    return poser


# --------------------------------------------------------------------------
# Hors mode test : comportement strictement inchangé
# --------------------------------------------------------------------------

def test_hors_mode_test_tout_est_permis(config):
    config({})
    assert bf.peut_publier("sheogorath", SERVEUR_PUBLIC) is True
    assert bf.peut_publier("sheogorath", SERVEUR_PRIVE) is True
    assert bf.peut_publier("sheogorath", None) is True


def test_le_fichier_absent_ne_musele_personne(config):
    """Un dashboard jamais ouvert ne doit pas rendre les bots muets."""
    config({})
    assert bf.is_test_mode("alfred") is False
    assert bf.peut_publier("alfred", SERVEUR_PUBLIC) is True


# --------------------------------------------------------------------------
# Interrupteur global
# --------------------------------------------------------------------------

def test_le_global_musele_les_six(config):
    config({"_global": {"test_mode": True, "test_guild_id": str(SERVEUR_PRIVE)}})
    for bot in ["alfred", "johnny", "maiq", "malena", "sheogorath", "sugar"]:
        assert bf.is_test_mode(bot) is True
        assert bf.peut_publier(bot, SERVEUR_PRIVE) is True
        assert bf.peut_publier(bot, SERVEUR_PUBLIC) is False


def test_mode_test_actif_sans_serveur_choisi_coupe_tout(config):
    """Le piège : sans ce choix, un mode test « activé mais pas configuré »
    laisserait tout passer en public — exactement ce qu'on veut éviter."""
    config({"_global": {"test_mode": True, "test_guild_id": None}})
    assert bf.peut_publier("sheogorath", SERVEUR_PUBLIC) is False
    assert bf.peut_publier("sheogorath", SERVEUR_PRIVE) is False
    assert bf.peut_publier("sheogorath", None) is False


@pytest.mark.parametrize("valeur", ["", 0, "pas-un-nombre", None])
def test_un_identifiant_de_serveur_invalide_coupe_tout(config, valeur):
    config({"_global": {"test_mode": True, "test_guild_id": valeur}})
    assert bf.test_guild_id() is None
    assert bf.peut_publier("sheogorath", SERVEUR_PRIVE) is False


def test_identifiant_stocke_en_texte(config):
    """Le dashboard stocke l'identifiant en texte (un entier 64 bits est arrondi
    par le JSON du navigateur) : la comparaison doit quand même fonctionner."""
    config({"_global": {"test_mode": True, "test_guild_id": str(SERVEUR_PRIVE)}})
    assert bf.peut_publier("sheogorath", SERVEUR_PRIVE) is True
    assert bf.peut_publier("sheogorath", str(SERVEUR_PRIVE)) is True


# --------------------------------------------------------------------------
# Interrupteur par bot
# --------------------------------------------------------------------------

def test_la_case_dun_bot_ne_musele_que_lui(config):
    config({
        "_global": {"test_mode": False, "test_guild_id": str(SERVEUR_PRIVE)},
        "sheogorath": {"test_mode": True},
        "alfred": {"test_mode": False},
    })
    assert bf.peut_publier("sheogorath", SERVEUR_PUBLIC) is False
    assert bf.peut_publier("sheogorath", SERVEUR_PRIVE) is True
    assert bf.peut_publier("alfred", SERVEUR_PUBLIC) is True


def test_le_global_prime_sur_une_case_bot_decochee(config):
    """« L'un des deux suffit » : le global ne doit pas être annulé par une case."""
    config({
        "_global": {"test_mode": True, "test_guild_id": str(SERVEUR_PRIVE)},
        "alfred": {"test_mode": False},
    })
    assert bf.peut_publier("alfred", SERVEUR_PUBLIC) is False


# --------------------------------------------------------------------------
# Messages privés
# --------------------------------------------------------------------------

def test_les_messages_prives_sont_coupes_en_mode_test(config):
    """Choix explicite : en mode test, seul le serveur privé parle."""
    config({"_global": {"test_mode": True, "test_guild_id": str(SERVEUR_PRIVE)}})
    assert bf.peut_publier("sheogorath", None) is False


# --------------------------------------------------------------------------
# La garde installée sur discord.py
# --------------------------------------------------------------------------

class _FauxServeur:
    def __init__(self, gid):
        self.id = gid


class _FauxSalon:
    """Imite juste ce que la garde regarde : `.guild`."""
    def __init__(self, guild):
        self.guild = guild


def test_la_garde_couvre_reply_via_messageable_send():
    """Message.reply est un raccourci vers abc.Messageable.send : c'est CE point de
    passage qui rend la garde exhaustive. Si discord.py changeait ça, le mode test
    laisserait fuiter toutes les réponses — d'où ce test."""
    import inspect
    import discord
    source = inspect.getsource(discord.Message.reply)
    assert "Messageable.send" in source or "channel.send" in source


def test_la_garde_est_idempotente(monkeypatch):
    """on_ready peut se déclencher plusieurs fois (reconnexion) : réinstaller la
    garde par-dessus elle-même empilerait les enrobages."""
    import discord
    import shared.test_mode as tm

    monkeypatch.setattr(tm, "_DEJA_INSTALLE", False)
    origine = discord.abc.Messageable.send
    try:
        assert tm.installer_garde_publication("sheogorath") is True
        apres_une = discord.abc.Messageable.send
        assert tm.installer_garde_publication("sheogorath") is False
        assert discord.abc.Messageable.send is apres_une
    finally:
        discord.abc.Messageable.send = origine
        discord.InteractionResponse.send_message = discord.InteractionResponse.send_message


def test_la_garde_bloque_le_public_et_laisse_passer_le_prive(monkeypatch, config):
    import asyncio
    import discord
    import shared.test_mode as tm

    config({"_global": {"test_mode": True, "test_guild_id": str(SERVEUR_PRIVE)}})

    envoyes = []
    origine = discord.abc.Messageable.send
    origine_slash = discord.InteractionResponse.send_message

    async def faux_send(self, *a, **k):
        envoyes.append(getattr(getattr(self, "guild", None), "id", None))
        return "envoye"

    monkeypatch.setattr(tm, "_DEJA_INSTALLE", False)
    discord.abc.Messageable.send = faux_send
    try:
        tm.installer_garde_publication("sheogorath")
        garde = discord.abc.Messageable.send

        prive = _FauxSalon(_FauxServeur(SERVEUR_PRIVE))
        public = _FauxSalon(_FauxServeur(SERVEUR_PUBLIC))
        mp = _FauxSalon(None)

        assert asyncio.run(garde(prive, "coucou")) == "envoye"
        assert asyncio.run(garde(public, "coucou")) is None
        assert asyncio.run(garde(mp, "coucou")) is None
        assert envoyes == [SERVEUR_PRIVE], "seul le serveur privé devait recevoir"
    finally:
        discord.abc.Messageable.send = origine
        discord.InteractionResponse.send_message = origine_slash
        tm._DEJA_INSTALLE = False


# --------------------------------------------------------------------------
# Twitch
# --------------------------------------------------------------------------

def test_twitch_est_coupe_en_mode_test(config):
    """Un chat Twitch est public par nature : aucun « serveur privé » possible."""
    import asyncio
    from shared.twitch.sanitize import send_chat_safe

    config({"_global": {"test_mode": True, "test_guild_id": str(SERVEUR_PRIVE)}})

    envoyes = []

    class _FauxWS:
        async def send_str(self, texte):
            envoyes.append(texte)

    asyncio.run(send_chat_safe(_FauxWS(), "unchan", "coucou", bot_id="sheogorath"))
    assert envoyes == [], "rien ne devait partir sur Twitch"


def test_twitch_publie_normalement_hors_mode_test(config):
    import asyncio
    from shared.twitch.sanitize import send_chat_safe

    config({})
    envoyes = []

    class _FauxWS:
        async def send_str(self, texte):
            envoyes.append(texte)

    asyncio.run(send_chat_safe(_FauxWS(), "unchan", "coucou", bot_id="sheogorath"))
    assert len(envoyes) == 1 and "coucou" in envoyes[0]


# --------------------------------------------------------------------------
# Remontée des serveurs pour le menu déroulant
# --------------------------------------------------------------------------

def test_les_serveurs_sont_remontes_pour_le_dashboard(tmp_path, monkeypatch):
    import shared.test_mode as tm
    monkeypatch.setattr(tm, "DATA_DIR", str(tmp_path))

    class _FauxBot:
        guilds = [_FauxServeur(SERVEUR_PRIVE), _FauxServeur(SERVEUR_PUBLIC)]

    _FauxBot.guilds[0].name = "Mon serveur privé"
    _FauxBot.guilds[1].name = "Serveur public"

    assert tm.enregistrer_serveurs("sheogorath", _FauxBot()) is True
    ecrit = json.loads((tmp_path / "bot_guilds.json").read_text(encoding="utf-8"))
    assert ecrit["sheogorath"]["guilds"][0]["id"] == str(SERVEUR_PRIVE)
    assert ecrit["sheogorath"]["guilds"][0]["name"] == "Mon serveur privé"


def test_une_remontee_impossible_ne_casse_pas_le_demarrage(monkeypatch):
    """Un confort de dashboard ne doit JAMAIS empêcher un bot de démarrer."""
    import shared.test_mode as tm
    monkeypatch.setattr(tm, "DATA_DIR", "/chemin/qui/nexiste/pas/du/tout")

    class _BotQuiExplose:
        @property
        def guilds(self):
            raise RuntimeError("boum")

    assert tm.enregistrer_serveurs("sheogorath", _BotQuiExplose()) is False


# --------------------------------------------------------------------------
# Câblage des 6 bots
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fichier,bot_id", [
    ("Alfred/bot_alfred.py", "alfred"),
    ("JohnnyBot/bot_johnny.py", "johnny"),
    ("MaiqBot/bot_maiq.py", "maiq"),
    ("MalenaBot/bot_malena.py", "malena"),
    ("Sheogorath/bot_sheogorath.py", "sheogorath"),
    ("SugarBot/bot_sugar.py", "sugar"),
])
def test_chaque_bot_installe_la_garde(fichier, bot_id):
    """Un bot non câblé publierait en public sans la moindre erreur : invisible."""
    src = open(os.path.join(_parent_dir, fichier), encoding="utf-8").read()
    assert f'installer_garde_publication("{bot_id}"' in src
    assert f'enregistrer_serveurs("{bot_id}"' in src
