# -*- coding: utf-8 -*-
"""SUITE 20 -- Twitch jette en silence un message identique envoye < 30 s apres.

1. send_chat_safe n'envoie pas un doublon < 32 s (meme bot, meme canal, meme texte).
2. Les NOTICE de Twitch partent au journal au lieu d'etre ignores.
"""
import asyncio
from pathlib import Path

import pytest

import shared.twitch.sanitize as san
from shared.twitch.connection import ConnectionMixin
from shared.twitch_chat import TwitchChatBot

RACINE = Path(__file__).resolve().parent.parent


class _FauxWS:
    def __init__(self):
        self.envoyes = []

    async def send_str(self, texte):
        self.envoyes.append(texte)


class _FauxLogger:
    def __init__(self):
        self.infos, self.warnings = [], []

    def info(self, m, *a, **k):
        self.infos.append(m)

    def warning(self, m, *a, **k):
        self.warnings.append(m)

    def debug(self, *a, **k):
        pass

    error = debug


@pytest.fixture
def horloge(monkeypatch):
    t = [0.0]
    monkeypatch.setattr("shared.twitch.sanitize._horloge", lambda: t[0], raising=False)
    monkeypatch.setattr("shared.twitch.sanitize._mode_test_actif", lambda b: False)
    return t


def _envoyer(ws, chan, texte, bot_id, logger=None):
    asyncio.run(san.send_chat_safe(ws, chan, texte, bot_id=bot_id, logger=logger))


TEXTE = "Combien d'heures avez-vous perdues ? Rejoignez le Discord"


def test_cas_vecu_meme_phrase_30s_apres_n_est_pas_renvoyee(horloge):
    ws, log = _FauxWS(), _FauxLogger()
    _envoyer(ws, "ma_streameuse", TEXTE, "sugar", log)
    horloge[0] = 30.0
    _envoyer(ws, "ma_streameuse", TEXTE, "sugar", log)
    assert len([e for e in ws.envoyes if e.startswith("PRIVMSG")]) == 1
    assert any("Doublon NON envoyé" in m for m in log.infos)


def test_apres_la_fenetre_le_meme_texte_repart(horloge):
    ws = _FauxWS()
    _envoyer(ws, "ma_streameuse", TEXTE, "sugar")
    horloge[0] = 33.0
    _envoyer(ws, "ma_streameuse", TEXTE, "sugar")
    assert len(ws.envoyes) == 2


def test_un_doublon_refuse_ne_rallonge_pas_la_fenetre(horloge):
    ws = _FauxWS()
    _envoyer(ws, "ma_streameuse", TEXTE, "sugar")
    horloge[0] = 20.0
    _envoyer(ws, "ma_streameuse", TEXTE, "sugar")
    assert len(ws.envoyes) == 1
    horloge[0] = 33.0
    _envoyer(ws, "ma_streameuse", TEXTE, "sugar")
    assert len(ws.envoyes) == 2


def test_texte_different_ou_autre_canal_ou_autre_bot_part(horloge):
    ws = _FauxWS()
    _envoyer(ws, "chanX", "A", "sugar")
    horloge[0] = 1.0
    _envoyer(ws, "chanX", "B", "sugar")
    _envoyer(ws, "chanY", "A", "sugar")
    _envoyer(ws, "chanX", "A", "johnny")
    assert len(ws.envoyes) == 4


class _F(ConnectionMixin):
    def __init__(self):
        self.NOTICE_RE = TwitchChatBot.NOTICE_RE
        self.bot_id = "sugar"
        self.logger = _FauxLogger()


def test_notice_msg_duplicate_va_au_journal():
    f = _F()
    line = ("@msg-id=msg_duplicate :tmi.twitch.tv NOTICE #ma_streameuse :Your message is "
            "identical to the one you sent less than 30 seconds ago.")
    assert f._handle_notice(line, TwitchChatBot._parse_tags(line)) is True
    assert len(f.logger.warnings) == 1
    assert "msg_duplicate" in f.logger.warnings[0]
    assert "ma_streameuse" in f.logger.warnings[0]


def test_privmsg_et_usernotice_ne_sont_pas_des_notice():
    f = _F()
    for line in (
        "@msg-id=sub :tmi.twitch.tv USERNOTICE #c :hey",
        ":bob!bob@bob.tmi.twitch.tv PRIVMSG #c :regarde :tmi.twitch.tv NOTICE #c :x",
    ):
        assert f._handle_notice(line, TwitchChatBot._parse_tags(line)) is False
    assert f.logger.warnings == []


def test_la_boucle_irc_appelle_handle_notice_avant_privmsg():
    src = (RACINE / "shared" / "twitch" / "connection.py").read_text(encoding="utf-8")
    i_notice = src.find("self._handle_notice(line, tags)")
    i_privmsg = src.find("self.PRIVMSG_RE.match(line)")
    assert i_notice != -1, "_handle_notice n'est jamais appele dans la boucle"
    assert i_privmsg != -1
    assert i_notice < i_privmsg
