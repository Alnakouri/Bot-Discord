# -*- coding: utf-8 -*-
"""Verrous sur `shared/server_events.py`.

Le defaut qu'ils interdisent : le nom que chaque bot passe (« M'aiq », « Sugar Bot »,
« Johnny ») n'est PAS la cle de ses pools de repliques, et le repli
`.get(cle, ...["sheogorath"])` leur faisait dire les repliques de SHEOGORATH. Trois bots
sur six auraient accueilli un nouveau membre avec « NOUVEAU MORTEL ! Bienvenue dans mon
royaume de folie » — invisible jusqu'ici parce que `on_member_join` etait du code mort
sur M'aiq et Sheogorath jusqu'au 11/09, et qu'une arrivee est rare ET tiree au sort.
"""
import ast
import asyncio
import logging
import os
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared import server_events as ev

# Les 6 bots, et le fichier ou chacun cable les evenements serveur.
_FICHIERS_BOTS = {
    "sheogorath": "Sheogorath/bot_sheogorath.py",
    "maiq": "MaiqBot/bot_maiq.py",
    "alfred": "Alfred/bot_alfred.py",
    "johnny": "JohnnyBot/bot_johnny.py",
    "malena": "MalenaBot/bot_malena.py",
    "sugar": "SugarBot/bot_sugar.py",
}

_FONCTIONS = {
    # nom de la fonction -> position de l'argument `bot_name`
    "handle_member_join": 2,
    "handle_member_remove": 2,
    "check_and_send_birthdays": 1,
}


def _noms_passes_par_les_bots():
    """Releve, par `ast`, les noms que les 6 bots passent REELLEMENT.

    On lit les fichiers des bots plutot que de recopier une liste ici : si un bot est
    renomme, ou un 7e ajoute, le verrou le voit ([[gotcha-un-bot-sur-six-manque-toujours]]).
    """
    trouves = {}
    for bot, chemin in _FICHIERS_BOTS.items():
        src = open(os.path.join(_parent_dir, chemin), encoding="utf-8").read()
        noms = set()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            nom_fn = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if nom_fn not in _FONCTIONS:
                continue
            arg = None
            for kw in node.keywords:
                if kw.arg == "bot_name":
                    arg = kw.value
            if arg is None:
                pos = _FONCTIONS[nom_fn]
                if len(node.args) > pos:
                    arg = node.args[pos]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                noms.add(arg.value)
        trouves[bot] = noms
    return trouves


class _FauxMembre:
    """Le strict minimum qu'utilisent les fonctions testees."""

    def __init__(self, salons=()):
        self.mention = "@nouveau"
        self.display_name = "nouveau"
        self.name = "nouveau"
        self.id = 4070

        class _Guilde:
            name = "Serveur de test"
            text_channels = list(salons)

        self.guild = _Guilde()

    def __str__(self):
        return "nouveau#0001"


def test_les_6_bots_sont_bien_releves():
    """Si ce test tombe, c'est le RELEVE qui est casse, pas les bots : les verrous
    suivants ne verifieraient plus rien sans crier."""
    trouves = _noms_passes_par_les_bots()
    manquants = [bot for bot, noms in trouves.items() if not noms]
    assert not manquants, f"aucun nom releve pour : {manquants}"
    assert len(trouves) == 6, f"6 bots attendus, {len(trouves)} releves"


def test_aucun_bot_n_emprunte_la_voix_d_un_autre():
    """LE verrou. Chaque bot dit SES repliques, ou se tait — jamais celles d'un autre."""
    membre = _FauxMembre()
    # (libelle, fonction, dictionnaire, valeur substituee a {user} par la fonction)
    pools = [
        ("de bienvenue", ev.get_welcome_message, ev.WELCOME_MESSAGES, membre.mention),
        ("de depart", ev.get_goodbye_message, ev.GOODBYE_MESSAGES, membre.display_name),
        ("d'anniversaire", ev.get_birthday_message, ev.BIRTHDAY_MESSAGES, membre.mention),
    ]
    for bot, noms in _noms_passes_par_les_bots().items():
        for nom in noms:
            cle = ev.cle_persona(nom)
            for libelle, fonction, dictionnaire, valeur in pools:
                # Le pool est tire au hasard : on rejoue assez pour couvrir chaque
                # replique, sinon une seule fautive passerait entre les mailles.
                for _ in range(50):
                    sortie = fonction(nom, membre)
                    if cle is None:
                        assert sortie is None, (
                            f"{nom} n'a pas de pool {libelle} et parle quand meme : {sortie!r}"
                        )
                        continue
                    assert sortie is not None, f"{nom} devrait avoir un pool {libelle}"
                    siennes = {g.format(user=valeur) for g in dictionnaire[cle]}
                    assert sortie in siennes, (
                        f"{nom} dit une replique {libelle} qui n'est PAS dans son pool "
                        f"'{cle}' : {sortie!r}"
                    )


def test_une_arrivee_laisse_une_trace_meme_sans_salon_et_meme_sans_message():
    """L'envoi est tire au sort (20-30 %) : sans cette trace, « aucun message » ne
    permet pas de distinguer le dé de l'evenement jamais recu. C'est exactement
    l'ambiguite qui a laisse `on_member_join` « a valider » pendant des jours."""
    membre = _FauxMembre(salons=())        # aucun salon d'accueil : rien ne sera envoye
    journal = logging.getLogger("server_events")
    lignes = []

    class _Capteur(logging.Handler):
        def emit(self, record):
            lignes.append(record.getMessage())

    capteur = _Capteur()
    journal.addHandler(capteur)
    niveau = journal.level
    journal.setLevel(logging.INFO)
    try:
        asyncio.run(ev.handle_member_join(None, membre, "M'aiq"))
    finally:
        journal.removeHandler(capteur)
        journal.setLevel(niveau)

    assert any("[ARRIVEE]" in ligne for ligne in lignes), (
        f"aucune trace d'arrivee dans le journal : {lignes}"
    )


def test_le_logger_du_module_est_cable_sur_les_handlers_du_bot():
    """Verrou sur le FICHIER : un logger absent de cette liste n'atteint ni
    logs/<bot>_<date>.log ni le JSONL du tableau de bord — il ne survivrait que par le
    `lastResort` de `logging`, qui ignore INFO. La trace ci-dessus serait perdue."""
    src = open(os.path.join(_parent_dir, "shared", "bot_logger.py"), encoding="utf-8").read()
    bloc = src.split("for shared_name in (")[1].split("):")[0]
    assert '"server_events"' in bloc, (
        "server_events n'est pas dans la liste des shared_name de setup_logger"
    )
