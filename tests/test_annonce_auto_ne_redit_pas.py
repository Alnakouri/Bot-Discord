# -*- coding: utf-8 -*-
"""Verrous SUITE 13 : l'annonce auto ne ressert plus la phrase du cache.

Sur Twitch, Sugar envoyait parfois mot pour mot la phrase du viewer qui venait
de taper `!discord` quelques minutes plus tôt (cache 900s partagé avec l'auto).
Ce fichier verrouille :
1. Une commande tapée remet le minuteur à zéro (_repousser_annonce_auto).
2. L'annonce auto n'emprunte jamais le cache (_ANNONCE_AUTO contextvar).
3. Le viewer bénéficie toujours du cache pour économiser les quotas.
4. Aucun résidu / fuite de drapeau si l'annonce échoue.
5. Verrou AST sur shared/twitch/dispatch.py.
"""
import ast
import asyncio
import collections
from pathlib import Path
import pytest

from shared.twitch.dispatch import DispatchMixin, _ANNONCE_AUTO

URL = "https://discord.gg/exemple"


class _Journal:
    def __init__(self):
        self.lignes = []

    def info(self, msg):
        self.lignes.append(msg)

    warning = error = info


class _BotFactice(DispatchMixin):
    """Le strict nécessaire pour emprunter le vrai chemin de `_handle_command` et `_try_link_timer`."""
    bot_id = "sugar"
    bot_label = "Sugar"
    personality_prompt = "tu es Sugar"
    system_prompt_provider = None
    key_manager = object()          # non-None : sinon renonce avant d'appeler
    mistral_client = groq_client = nvidia_client = None

    def __init__(self):
        self.logger = _Journal()
        self.commands = {}
        self.command_aliases = {}
        self.command_cooldowns = {}
        self.user_cooldowns = {}
        self.global_msg_timestamps = collections.deque()
        self.link_timers = []
        self._etat_timers = {}
        self._link_lines_cache = {}

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


def _avec_reponse(texte=None, compteur=None):
    """Remplace la cascade par une réponse fixe ou incrémentale. Rend le bot prêt."""
    import shared.llm_cascade as cascade
    if compteur is None:
        compteur = {"n": 0}

    async def _faux(**kwargs):
        compteur["n"] += 1
        if texte is not None:
            return texte
        return f"Phrase {compteur['n']}"

    cascade.generate_response = _faux
    bot = _BotFactice()
    return bot, compteur


def _armer_lien(bot, cmd="discord", alias="ma_streameuse", every=900, min_msgs=15, tmpl="Rejoins: {url}"):
    """Arme la commande et son minuteur comme dans shared/twitch_chat.py l.448-472."""
    async def callback(author, args, u=URL, l=cmd, c=cmd, t=tmpl):
        phrase = None
        try:
            phrase = await bot._generate_link_line(c, l, u)
        except Exception as e:
            bot.logger.error(f"erreur phrase: {e}")
        return phrase or t.format(url=u, label=l)

    bot.commands[cmd] = callback
    if alias:
        bot.command_aliases[alias] = cmd
    bot.link_timers = [
        {"cmd": cmd, "every": every, "min_msgs": min_msgs, "callback": callback}
    ]
    return callback


def test_1_cas_vecu_20h09_20h23(monkeypatch):
    """1. Le cas vécu (20:09 -> 20:23) :
    Minuteur 15 min armé depuis t=0.
    !discord tapé à t=100 -> « Phrase 1 » envoyée.
    15 messages, _try_link_timer à t=945 -> rien envoyé (ancien code envoyait « Phrase 1 » depuis cache).
    15 messages encore, _try_link_timer à t=1001 -> « Phrase 2 » (différente de Phrase 1) envoyée.
    Deux appels au modèle au total.
    """
    bot, compteur = _avec_reponse()
    _armer_lien(bot, every=900, min_msgs=15)
    bot._etat_timers[("canal", "discord")] = {"depuis": 0.0, "msgs": 0}

    t_actuel = [0.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    envoyes = []
    async def _faux_send(ws, chan, msg, **kwargs):
        envoyes.append((chan, msg))
    monkeypatch.setattr("shared.twitch.dispatch.send_chat_safe", _faux_send)

    ws = object()

    # t=100 : !discord tapé par un viewer
    t_actuel[0] = 100.0
    succes = asyncio.run(bot._handle_command("canal", "viewer1", "!discord", ws))
    assert succes is True
    assert len(envoyes) == 1
    assert envoyes[0][1] == f"Phrase 1 {URL}"
    assert compteur["n"] == 1

    # 15 messages arrivent, t=945
    bot._etat_timers[("canal", "discord")]["msgs"] = 15
    t_actuel[0] = 945.0
    sent = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent is False, "L'annonce auto ne devait rien envoyer à t=945 car 945 - 100 < 900"
    assert len(envoyes) == 1
    assert compteur["n"] == 1

    # 15 messages encore, t=1001
    bot._etat_timers[("canal", "discord")]["msgs"] = 15
    t_actuel[0] = 1001.0
    sent = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent is True
    assert len(envoyes) == 2
    assert envoyes[1][1] == f"Phrase 2 {URL}"
    assert envoyes[1][1] != envoyes[0][1]
    assert compteur["n"] == 2


def test_2_commande_repousse_minuteur(monkeypatch):
    """2. La commande repousse le minuteur :
    minuteur armé depuis t=0 avec 15 messages,
    !discord tapé à t=850 -> _etat_timers[('canal', 'discord')] == {'depuis': 850, 'msgs': 0},
    et _try_link_timer à t=950 n'envoie rien.
    """
    bot, _ = _avec_reponse()
    _armer_lien(bot, every=900, min_msgs=15)
    bot._etat_timers[("canal", "discord")] = {"depuis": 0.0, "msgs": 15}

    t_actuel = [850.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    envoyes = []
    async def _faux_send(ws, chan, msg, **kwargs):
        envoyes.append((chan, msg))
    monkeypatch.setattr("shared.twitch.dispatch.send_chat_safe", _faux_send)

    ws = object()
    asyncio.run(bot._handle_command("canal", "viewer1", "!discord", ws))

    assert bot._etat_timers[("canal", "discord")] == {"depuis": 850.0, "msgs": 0}

    t_actuel[0] = 950.0
    sent = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent is False
    assert len(envoyes) == 1  # seulement celui du viewer à t=850


def test_3_repousser_par_alias(monkeypatch):
    """3. Par l'alias aussi : même test que 2 en tapant l'alias -> minuteur repoussé."""
    bot, _ = _avec_reponse()
    _armer_lien(bot, cmd="discord", alias="ma_streameuse", every=900, min_msgs=15)
    bot._etat_timers[("canal", "discord")] = {"depuis": 0.0, "msgs": 15}

    t_actuel = [850.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    envoyes = []
    async def _faux_send(ws, chan, msg, **kwargs):
        envoyes.append((chan, msg))
    monkeypatch.setattr("shared.twitch.dispatch.send_chat_safe", _faux_send)

    ws = object()
    asyncio.run(bot._handle_command("canal", "viewer1", "!ma_streameuse", ws))

    assert bot._etat_timers[("canal", "discord")] == {"depuis": 850.0, "msgs": 0}

    t_actuel[0] = 950.0
    sent = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent is False
    assert len(envoyes) == 1


def test_4_intervalle_court_5_min(monkeypatch):
    """4. Intervalle court (5 min, every=300) :
    minuteur armé à t=0, 15 messages avant chaque appel,
    _try_link_timer à t=301 puis à t=602 -> deux phrases différentes, deux appels
    (l'ancien code resservait la première depuis le cache).
    """
    bot, compteur = _avec_reponse()
    _armer_lien(bot, every=300, min_msgs=15)
    bot._etat_timers[("canal", "discord")] = {"depuis": 0.0, "msgs": 15}

    t_actuel = [301.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    envoyes = []
    async def _faux_send(ws, chan, msg, **kwargs):
        envoyes.append((chan, msg))
    monkeypatch.setattr("shared.twitch.dispatch.send_chat_safe", _faux_send)

    ws = object()

    # t=301 : première annonce auto
    sent1 = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent1 is True
    assert len(envoyes) == 1
    assert envoyes[0][1] == f"Phrase 1 {URL}"
    assert compteur["n"] == 1

    # 15 messages, t=602 : deuxième annonce auto
    bot._etat_timers[("canal", "discord")]["msgs"] = 15
    t_actuel[0] = 602.0
    sent2 = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent2 is True
    assert len(envoyes) == 2
    assert envoyes[1][1] == f"Phrase 2 {URL}"
    assert envoyes[1][1] != envoyes[0][1]
    assert compteur["n"] == 2


def test_5_cache_sert_toujours_les_viewers(monkeypatch):
    """5. Le cache sert toujours les viewers :
    annonce auto (« Phrase 1 ») puis !discord tapé 10 s après ->
    le viewer reçoit « Phrase 1 », un seul appel au total.
    """
    bot, compteur = _avec_reponse()
    _armer_lien(bot, every=900, min_msgs=15)
    bot._etat_timers[("canal", "discord")] = {"depuis": 0.0, "msgs": 15}

    t_actuel = [901.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    envoyes = []
    async def _faux_send(ws, chan, msg, **kwargs):
        envoyes.append((chan, msg))
    monkeypatch.setattr("shared.twitch.dispatch.send_chat_safe", _faux_send)

    ws = object()

    # Annonce auto à t=901
    sent = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent is True
    assert len(envoyes) == 1
    assert envoyes[0][1] == f"Phrase 1 {URL}"
    assert compteur["n"] == 1

    # Viewer tape !discord à t=911 (10s plus tard)
    t_actuel[0] = 911.0
    succes = asyncio.run(bot._handle_command("canal", "viewer1", "!discord", ws))
    assert succes is True
    assert len(envoyes) == 2
    assert envoyes[1][1] == f"Phrase 1 {URL}"
    assert compteur["n"] == 1, "Le viewer devait être servi par le cache sans nouvel appel"


def test_6_drapeau_ne_fuit_pas(monkeypatch):
    """6. Le drapeau ne fuit pas :
    après une annonce auto dont le callback lève, puis un !discord tapé ->
    servi depuis le cache si une phrase y est (et _ANNONCE_AUTO.get() vaut False hors annonce).
    """
    bot, compteur = _avec_reponse("Phrase en cache")
    # Mettre en cache une phrase à t=950 (valide car à t=1010 : 1010 - 950 = 60 < 900)
    bot._link_lines_cache[("discord", None)] = (950.0, "Phrase en cache")

    # Minuteur qui lève une exception
    async def _cb_qui_leve(author, args):
        raise RuntimeError("Panne de génération")

    bot.link_timers = [
        {"cmd": "discord", "every": 900, "min_msgs": 15, "callback": _cb_qui_leve}
    ]
    bot._etat_timers[("canal", "discord")] = {"depuis": 0.0, "msgs": 15}

    t_actuel = [1000.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    envoyes = []
    async def _faux_send(ws, chan, msg, **kwargs):
        envoyes.append((chan, msg))
    monkeypatch.setattr("shared.twitch.dispatch.send_chat_safe", _faux_send)

    ws = object()

    # Annonce auto qui lève
    sent = asyncio.run(bot._try_link_timer("canal", ws))
    assert sent is False
    assert _ANNONCE_AUTO.get() is False, "Le drapeau _ANNONCE_AUTO doit valoir False après l'échec"

    # Maintenant le viewer tape !discord avec un vrai callback
    _armer_lien(bot, every=900, min_msgs=15)
    t_actuel[0] = 1010.0
    succes = asyncio.run(bot._handle_command("canal", "viewer1", "!discord", ws))
    assert succes is True
    assert len(envoyes) == 1
    assert envoyes[0][1] == f"Phrase en cache {URL}"
    # Le cache a été utilisé (pas de nouvel appel au modèle)
    assert compteur["n"] == 0
    assert _ANNONCE_AUTO.get() is False


def test_7_commande_bloquee_ne_repousse_rien(monkeypatch):
    """7. Une commande bloquée ne repousse rien :
    !discord refusé par le cooldown global (5 s) -> _etat_timers inchangé.
    """
    bot, _ = _avec_reponse()
    _armer_lien(bot, every=900, min_msgs=15)
    bot._etat_timers[("canal", "discord")] = {"depuis": 100.0, "msgs": 10}

    t_actuel = [120.0]
    monkeypatch.setattr("shared.twitch.dispatch.time.time", lambda: t_actuel[0])

    # Déclencher une première fois la commande pour activer le cooldown global
    bot.command_cooldowns["discord"] = 118.0  # exécutée à t=118

    envoyes = []
    async def _faux_send(ws, chan, msg, **kwargs):
        envoyes.append((chan, msg))
    monkeypatch.setattr("shared.twitch.dispatch.send_chat_safe", _faux_send)

    ws = object()
    # À t=120, le cooldown global (5s) est actif (120 - 118 = 2 < 5s)
    succes = asyncio.run(bot._handle_command("canal", "viewer1", "!discord", ws))
    assert succes is True
    assert len(envoyes) == 0, "La commande bloquée n'a rien envoyé"
    assert bot._etat_timers[("canal", "discord")] == {"depuis": 100.0, "msgs": 10}, \
        "_etat_timers n'aurait pas dû changer pour une commande bloquée"


def test_8_verrou_ast_sur_dispatch():
    """8. Verrou AST sur shared/twitch/dispatch.py :
    dans _generate_link_line, la comparaison au seuil 900 est dans un if qui lit _ANNONCE_AUTO ;
    dans _try_link_timer, _ANNONCE_AUTO.set et _ANNONCE_AUTO.reset sont présents, le reset dans un finally.
    """
    fichier = Path(__file__).resolve().parent.parent / "shared" / "twitch" / "dispatch.py"
    arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))

    gen_func = None
    timer_func = None
    for node in ast.walk(arbre):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_generate_link_line":
                gen_func = node
            elif node.name == "_try_link_timer":
                timer_func = node

    assert gen_func is not None, "méthode _generate_link_line introuvable"
    assert timer_func is not None, "méthode _try_link_timer introuvable"

    # Vérification dans _generate_link_line
    if_900_trouve = False
    for node in ast.walk(gen_func):
        if isinstance(node, ast.If):
            constantes = [n.value for n in ast.walk(node.test) if isinstance(n, ast.Constant)]
            if 900 in constantes:
                noms = [n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)]
                assert "_ANNONCE_AUTO" in noms, (
                    "Le `if` avec le seuil 900s du cache ne lit pas `_ANNONCE_AUTO`"
                )
                if_900_trouve = True
    assert if_900_trouve, "Aucun `if` avec le seuil 900 trouvé dans _generate_link_line"

    # Vérification dans _try_link_timer
    appels_set = []
    appels_reset_finally = []
    for node in ast.walk(timer_func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if getattr(node.func.value, "id", "") == "_ANNONCE_AUTO" and node.func.attr == "set":
                appels_set.append(node)
        if isinstance(node, ast.Try):
            for fin in node.finalbody:
                for sub in ast.walk(fin):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        if getattr(sub.func.value, "id", "") == "_ANNONCE_AUTO" and sub.func.attr == "reset":
                            appels_reset_finally.append(sub)

    assert appels_set, "`_ANNONCE_AUTO.set` absent de `_try_link_timer`"
    assert appels_reset_finally, "`_ANNONCE_AUTO.reset` absent du `finally` de `_try_link_timer`"
