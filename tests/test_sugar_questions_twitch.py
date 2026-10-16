# -*- coding: utf-8 -*-
"""Tests des questions Twitch pour Sugar (SugarBot/sugar_questions_twitch.py).

Couvre :
A. Repérage (destinataire_evident, est_une_question).
B. Magasin (persistance, dédoublonnage, purge, résilience JSON cassé).
C. Rapport et tri LLM (filtrage, pagination, échappement, concurrence d'observation).
D. Demande Discord et vérification des permissions.
E. Crochet shared (DispatchMixin._handle_privmsg, setup_twitch_chat, verrous AST).
"""
import ast
import asyncio
import collections
import inspect
import os
import re
import sys
import types
from types import SimpleNamespace

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from SugarBot.sugar_questions_twitch import (
    QuestionsTwitch,
    destinataire_evident,
    demande_la_liste,
    peut_demander,
    est_une_question,
)
from shared.twitch.dispatch import DispatchMixin
from shared.twitch_chat import setup_twitch_chat


# ── A. Repérage ───────────────────────────────────────────────────────────────

def test_reperage_mention_streameuse():
    res = destinataire_evident("ma_streameuse", "bob", "@ma_streameuse tu joues à quoi demain ?", {}, bot_login="compte_bot_sugar")
    assert res == "streameuse"


def test_reperage_reply_parent_streameuse():
    res = destinataire_evident(
        "ma_streameuse", "bob", "@ma_streameuse et après ça ?",
        {"reply-parent-user-login": "ma_streameuse"}, bot_login="compte_bot_sugar"
    )
    assert res == "streameuse"


def test_reperage_reply_parent_viewer_ignore():
    res = destinataire_evident(
        "ma_streameuse", "bob", "@un_viewer tu parles de quel jeu ?",
        {"reply-parent-user-login": "un_viewer"}, bot_login="compte_bot_sugar"
    )
    assert res is None


def test_reperage_mention_autre_viewer_ou_bot_ignore():
    # Textes assez longs exprès pour passer est_une_question
    res1 = destinataire_evident("ma_streameuse", "bob", "@un_viewer t'as vu ce qu'elle a fait ?", {}, bot_login="compte_bot_sugar")
    assert res1 is None
    res2 = destinataire_evident("ma_streameuse", "bob", "@compte_bot_sugar tu dors encore ou quoi ?", {}, bot_login="compte_bot_sugar")
    assert res2 is None


def test_reperage_question_trop_courte():
    assert not est_une_question("??")
    assert not est_une_question("quoi ?")
    assert destinataire_evident("ma_streameuse", "bob", "??", {}, bot_login="compte_bot_sugar") is None
    assert destinataire_evident("ma_streameuse", "bob", "quoi ?", {}, bot_login="compte_bot_sugar") is None


def test_reperage_streameuse_elle_meme_ignore():
    res = destinataire_evident("ma_streameuse", "Ma_Streameuse", "vous voulez quel jeu demain ?", {}, bot_login="compte_bot_sugar")
    assert res is None


def test_reperage_commande_ignore():
    assert destinataire_evident("ma_streameuse", "bob", "!discord ?", {}, bot_login="compte_bot_sugar") is None


def test_reperage_question_ambigue_a_trier():
    res = destinataire_evident("ma_streameuse", "bob", "c'est quoi ce jeu ?", {}, bot_login="compte_bot_sugar")
    assert res == "a_trier"


def test_reperage_sans_point_d_interrogation_a_trier():
    res = destinataire_evident("ma_streameuse", "bob", "pourquoi tu ris", {}, bot_login="compte_bot_sugar")
    assert res == "a_trier"


def test_reperage_pas_une_question_ignore():
    res = destinataire_evident("ma_streameuse", "bob", "trop bien ce live", {}, bot_login="compte_bot_sugar")
    assert res is None


# ── B. Magasin ────────────────────────────────────────────────────────────────

def test_magasin_dedoublonnage(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    qt.observer("ma_streameuse", "bob", "c'est quoi ce jeu ?", {}, [])
    qt.observer("ma_streameuse", "bob", "  C'est quoi ce jeu ?  ", {}, [])
    assert len(qt.entrees) == 1


def test_magasin_rechargement(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    qt.observer("ma_streameuse", "bob", "c'est quoi ce jeu ?", {}, [])
    assert len(qt.entrees) == 1

    qt2 = QuestionsTwitch(p)
    assert len(qt2.entrees) == 1
    assert qt2.entrees[0]["texte"] == "c'est quoi ce jeu ?"


def test_magasin_purge_et_fenetre(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    maintenant = 1000000.0

    # Question de plus de 48h (purgée à la sauvegarde)
    qt.entrees.append({
        "id": 1, "ts": maintenant - 49 * 3600, "chan": "ma_streameuse",
        "auteur": "vieux", "texte": "c'est quoi ce jeu 1 ?", "dest": "streameuse"
    })
    # Question de 13h (conservée sur disque mais hors rapport)
    qt.entrees.append({
        "id": 2, "ts": maintenant - 13 * 3600, "chan": "ma_streameuse",
        "auteur": "moyen", "texte": "c'est quoi ce jeu 2 ?", "dest": "streameuse"
    })
    qt._sauvegarder(maintenant=maintenant)

    qt_relue = QuestionsTwitch(p)
    ids = [e["id"] for e in qt_relue.entrees]
    assert 1 not in ids
    assert 2 in ids

    # Le rapport à `maintenant` exclut l'entrée de 13h
    pages = asyncio.run(qt_relue.rapport(None, maintenant=maintenant))
    assert pages == ["Aucune question pour la streameuse sur les 12 dernières heures."]


def test_magasin_fichier_json_casse(tmp_path):
    p = str(tmp_path / "casse.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write("{ceci n'est pas du json valide")

    qt = QuestionsTwitch(p)
    assert qt.entrees == []
    assert qt.prochain_id == 1


def test_magasin_contexte_max_4_lignes(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    contexte_10 = [f"ligne {i}" for i in range(10)]
    qt.observer("ma_streameuse", "bob", "c'est quoi ce jeu ?", {}, contexte_10)
    assert len(qt.entrees) == 1
    ctx = qt.entrees[0]["contexte"]
    assert len(ctx) == 4
    assert ctx == ["ligne 6", "ligne 7", "ligne 8", "ligne 9"]


# ── C. Rapport et tri ─────────────────────────────────────────────────────────

def test_rapport_tri_llm_et_non_repetition(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    qt.observer("ma_streameuse", "u1", "c'est quoi ce jeu 1 ?", {}, [])  # id 1 -> a_trier
    qt.observer("ma_streameuse", "u2", "c'est quoi ce jeu 2 ?", {}, [])  # id 2 -> a_trier
    qt.observer("ma_streameuse", "u3", "c'est quoi ce jeu 3 ?", {}, [])  # id 3 -> a_trier
    qt.observer("ma_streameuse", "u4", "@ma_streameuse tu viens quand ?", {}, [])  # id 4 -> streameuse

    appels = []
    async def faux_llm(sp, um):
        appels.append((sp, um))
        return "1:S\n2:V\n3:A"

    pages = asyncio.run(qt.rapport(faux_llm))
    assert len(appels) == 1
    texte = "\n".join(pages)
    assert "u1" in texte
    assert "u4" in texte
    assert "u2" not in texte
    assert "u3" not in texte

    # Relire depuis le disque pour vérifier la persistance des verdicts
    qt_disk = QuestionsTwitch(p)
    dests = {e["id"]: e["dest"] for e in qt_disk.entrees}
    assert dests[1] == "streameuse"
    assert dests[2] == "viewer"
    assert dests[3] == "personne"

    # Second rapport : aucun appel LLM nécessaire
    asyncio.run(qt.rapport(faux_llm))
    assert len(appels) == 1


def test_rapport_llm_panne_laisse_a_trier(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    qt.observer("ma_streameuse", "bob", "c'est quoi ce jeu ?", {}, [])

    async def faux_none(sp, um):
        return None

    pages = asyncio.run(qt.rapport(faux_none))
    assert "Pas sûre du destinataire" in pages[0]
    assert "bob" in pages[0]
    assert qt.entrees[0]["dest"] == "a_trier"

    async def faux_exception(sp, um):
        raise RuntimeError("LLM indisponible")

    pages2 = asyncio.run(qt.rapport(faux_exception))
    assert "Pas sûre du destinataire" in pages2[0]
    assert qt.entrees[0]["dest"] == "a_trier"


def test_rapport_concurrence_nouvelle_question_pendant_llm(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    qt.observer("ma_streameuse", "u1", "c'est quoi ce jeu ?", {}, [])

    async def faux_llm_entrant(sp, um):
        # Nouvelle question arrivant PENDANT le tri LLM (au moins 8 lettres hors mention)
        qt.observer("ma_streameuse", "u_nouveau", "@ma_streameuse tu viens quand aujourd'hui ?", {}, [])
        return "1:S"

    asyncio.run(qt.rapport(faux_llm_entrant))

    # Vérification en mémoire et sur disque
    auteurs_mem = [e["auteur"] for e in qt.entrees]
    assert "u1" in auteurs_mem
    assert "u_nouveau" in auteurs_mem

    qt_disk = QuestionsTwitch(p)
    auteurs_disk = [e["auteur"] for e in qt_disk.entrees]
    assert "u1" in auteurs_disk
    assert "u_nouveau" in auteurs_disk


def test_rapport_pagination_60_questions(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    for i in range(60):
        # Questions longues avec mention streameuse
        qt.observer("ma_streameuse", f"viewer_{i}", f"@ma_streameuse {'mot ' * 35} ? ({i})", {}, [])

    pages = asyncio.run(qt.rapport(None))
    assert len(pages) > 1
    for page in pages:
        assert len(page) <= 1900
        for ligne in page.splitlines():
            assert (
                ligne.startswith("**❓")
                or ligne.startswith("<t:")
                or ligne.startswith("**Pas")
            ), f"Ligne coupée ou invalide : {ligne}"


def test_rapport_echappement_everyone_et_markdown(tmp_path):
    p = str(tmp_path / "questions.json")
    qt = QuestionsTwitch(p)
    qt.observer("ma_streameuse", "troll", "@ma_streameuse @everyone regarde **ça** ?", {}, [])

    pages = asyncio.run(qt.rapport(None))
    texte = "\n".join(pages)
    assert "@everyone" not in texte
    assert "@\u200beveryone" in texte
    assert "**ça**" not in texte
    assert r"\*\*ça\*\*" in texte


def test_rapport_vide(tmp_path):
    p = str(tmp_path / "vide.json")
    qt = QuestionsTwitch(p)
    pages = asyncio.run(qt.rapport(None))
    assert pages == ["Aucune question pour la streameuse sur les 12 dernières heures."]


# ── D. Demande et droits ──────────────────────────────────────────────────────

def test_demande_la_liste():
    assert demande_la_liste("les questions ?", en_prive=True) is True
    assert demande_la_liste("Sugar, les questions du live", en_prive=False) is True
    assert demande_la_liste("Sugar, t'as des questions ?", en_prive=False) is False
    assert demande_la_liste("les questions de la stremeuse", en_prive=False) is True
    assert demande_la_liste("les questions des viewver", en_prive=False) is True
    assert demande_la_liste("salut Sugar", en_prive=False) is False
    assert demande_la_liste("salut Sugar", en_prive=True) is False


def test_peut_demander():
    # Propriétaire
    g_owner = SimpleNamespace(owner_id=123, get_member=lambda uid: None)
    assert peut_demander([g_owner], 123) is True

    # Modérateur manage_messages
    m_manage = SimpleNamespace(guild_permissions=SimpleNamespace(administrator=False, manage_messages=True, moderate_members=False))
    g_mod = SimpleNamespace(owner_id=999, get_member=lambda uid: m_manage if uid == 456 else None)
    assert peut_demander([g_mod], 456) is True

    # Modérateur moderate_members
    m_mod = SimpleNamespace(guild_permissions=SimpleNamespace(administrator=False, manage_messages=False, moderate_members=True))
    g_mod2 = SimpleNamespace(owner_id=999, get_member=lambda uid: m_mod if uid == 789 else None)
    assert peut_demander([g_mod2], 789) is True

    # Membre simple
    m_simple = SimpleNamespace(guild_permissions=SimpleNamespace(administrator=False, manage_messages=False, moderate_members=False))
    g_simple = SimpleNamespace(owner_id=999, get_member=lambda uid: m_simple if uid == 111 else None)
    assert peut_demander([g_simple], 111) is False

    # Absent de tous les serveurs
    assert peut_demander([g_simple], 222) is False


# ── E. Crochet shared ─────────────────────────────────────────────────────────

class _FauxDispatch(DispatchMixin):
    def __init__(self, observer=None):
        self.bot_id = "sugar"
        self.logger = types.SimpleNamespace(
            debug=lambda *a, **k: None,
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
        )
        self.message_observer = observer
        self.enable_events = False
        self.enable_viewer_memory = False
        self.enable_game_qa = False
        self.enable_interjections = False
        self.enable_greetings = False
        self.enable_voice_listen = False
        self.user_cooldowns = {}
        self.global_msg_timestamps = collections.deque()
        self.channel_recent = {}
        self.session_seen = set()
        self.viewers_state = {}
        self.link_timers = []
        self.passive_handler = None
        self.trigger_re = re.compile(r"\b(?:sugar)\b", re.I)
        self._save_viewers_state_debounced = lambda: None

    async def _handle_command(self, chan, author, text, ws):
        return text.startswith("!")

    def _question_de_jeu(self, text, contexte_ou_voie=""):
        return None

    def _defaite_observee(self, text):
        return False

    async def _generate_response(self, *a, **k):
        return None


def test_crochet_dispatch_comportements():
    appels = []
    def observateur(chan, author, text, tags, contexte):
        appels.append((chan, author, text, tags, list(contexte)))

    bot = _FauxDispatch(observer=observateur)
    bot.channel_recent["un_canal"] = collections.deque(["user1: premier message"], maxlen=10)

    # 1. Message passif
    asyncio.run(bot._handle_privmsg("un_canal", "user2", "salut tout le monde", {}, None))
    assert len(appels) == 1
    assert appels[0] == ("un_canal", "user2", "salut tout le monde", {}, ["user1: premier message"])

    # 2. Message qui mentionne le bot
    appels.clear()
    asyncio.run(bot._handle_privmsg("un_canal", "user3", "sugar tu dors ?", {}, None))
    assert len(appels) == 1
    assert appels[0][1] == "user3"

    # 3. Commande Twitch -> pas appelé
    appels.clear()
    asyncio.run(bot._handle_privmsg("un_canal", "user4", "!discord", {}, None))
    assert len(appels) == 0

    # 4. Message avec bits -> pas appelé
    appels.clear()
    asyncio.run(bot._handle_privmsg("un_canal", "user5", "salut", {"bits": "100"}, None))
    assert len(appels) == 0

    # 5. Observateur qui lève -> message passif quand même rangé dans channel_recent
    def obs_plante(chan, author, text, tags, contexte):
        raise ValueError("erreur volontaire de test")

    bot_crash = _FauxDispatch(observer=obs_plante)
    bot_crash.channel_recent["un_canal"] = collections.deque(maxlen=10)
    asyncio.run(bot_crash._handle_privmsg("un_canal", "user6", "salut les amis", {}, None))
    assert any("user6: salut les amis" in m for m in bot_crash.channel_recent["un_canal"])


def test_setup_twitch_chat_transmet_message_observer():
    sig = inspect.signature(setup_twitch_chat)
    assert "message_observer" in sig.parameters

    with open("shared/twitch_chat.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, "id", None)
            if func_name == "TwitchChatBot":
                for kw in node.keywords:
                    if kw.arg == "message_observer":
                        found = True
                        break
    assert found, "TwitchChatBot(...) dans shared/twitch_chat.py ne reçoit pas message_observer"


def test_verrou_cablage_bot_sugar_ast():
    with open("SugarBot/bot_sugar.py", "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    found_setup_kw = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, "id", None)
            if func_name == "setup_twitch_chat":
                for kw in node.keywords:
                    if kw.arg == "message_observer":
                        found_setup_kw = True
                        break
    assert found_setup_kw, "setup_twitch_chat dans SugarBot/bot_sugar.py ne passe pas message_observer"

    found_demande = False
    found_peut = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "on_message":
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = getattr(child.func, "id", None)
                    if name == "demande_la_liste":
                        found_demande = True
                    elif name == "peut_demander":
                        found_peut = True
    assert found_demande, "on_message dans SugarBot/bot_sugar.py n'appelle pas demande_la_liste"
    assert found_peut, "on_message dans SugarBot/bot_sugar.py n'appelle pas peut_demander"
