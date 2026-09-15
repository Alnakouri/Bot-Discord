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


class _FauxSalon:
    """Faux salon Discord qui enregistre les messages envoyes."""

    def __init__(self, name="taverne-des-bots"):
        self.name = name
        self.messages = []

    async def send(self, contenu):
        self.messages.append(contenu)


class _FauxBot:
    """Faux bot Discord avec guildes et recherche de membre pour les anniversaires."""

    def __init__(self, salons=(), membre=None):
        class _Guilde:
            name = "Serveur de test"
            text_channels = list(salons)

            def get_member(self, user_id):
                if membre and membre.id == user_id:
                    return membre
                return None

        self.guilds = [_Guilde()]


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
            parle = ev.participe_aux_evenements(nom)
            for libelle, fonction, dictionnaire, valeur in pools:
                # Le pool est tire au hasard : on rejoue assez pour couvrir chaque
                # replique, sinon une seule fautive passerait entre les mailles.
                for _ in range(50):
                    sortie = fonction(nom, membre)
                    if not parle:
                        assert sortie is None, (
                            f"{nom} ne participe pas aux messages {libelle} et parle "
                            f"quand meme : {sortie!r}"
                        )
                        continue
                    assert sortie is not None, f"{nom} devrait avoir un pool {libelle}"
                    siennes = {g.format(user=valeur) for g in dictionnaire[cle]}
                    assert sortie in siennes, (
                        f"{nom} dit une replique {libelle} qui n'est PAS dans son pool "
                        f"'{cle}' : {sortie!r}"
                    )


def test_seuls_alfred_et_sugar_portent_ces_messages():
    """DECISION du 2026-09-13. Les quatre autres se taisent — et leur silence ne doit
    PAS passer par le chemin d'erreur : c'est un choix, pas un pool oublie."""
    assert ev._PORTE_PAROLE == {"alfred", "sugar"}, ev._PORTE_PAROLE

    membre = _FauxMembre()
    muets = []
    for bot, noms in _noms_passes_par_les_bots().items():
        for nom in noms:
            attendu = ev.cle_persona(nom) in ("alfred", "sugar")
            assert ev.participe_aux_evenements(nom) is attendu, nom
            if attendu:
                continue
            muets.append(nom)
            for fonction in (ev.get_welcome_message, ev.get_goodbye_message,
                             ev.get_birthday_message):
                assert fonction(nom, membre) is None, f"{nom} parle encore"

    # 4 bots muets : si ce compte bouge, la decision a change sans qu'on le dise.
    assert len({ev.cle_persona(n) for n in muets}) == 4, sorted(muets)


def test_un_silence_VOULU_ne_journalise_pas_d_avertissement():
    """Un bot qui ne participe pas n'est pas une anomalie. S'il criait a chaque
    arrivee, on apprendrait a ignorer ces lignes — et on raterait le vrai cri, celui
    d'un nom inconnu ([[gotcha-alerte-qui-crie-pour-du-nominal]])."""
    membre = _FauxMembre()
    journal = logging.getLogger("server_events")
    alertes = []

    class _Capteur(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                alertes.append(record.getMessage())

    capteur = _Capteur()
    journal.addHandler(capteur)
    try:
        ev.get_welcome_message("Sheogorath", membre)   # silence VOULU
        assert not alertes, f"un silence voulu a crie : {alertes}"
        ev.get_welcome_message("Bot Inconnu", membre)  # silence SUBI
        assert alertes, "un nom inconnu doit crier"
    finally:
        journal.removeHandler(capteur)


def test_une_arrivee_laisse_une_trace_meme_sans_salon_et_meme_sans_message(monkeypatch):
    """L'envoi est tire au sort : sans cette trace, « aucun message » ne permet pas
    de distinguer le de de l'evenement jamais recu.
    Verrou Lot 2 : generalise aux 3 gestionnaires (arrivee, depart, anniversaire).
    Sans salon et sans message, chacun laisse sa trace d'entree dans le journal.
    """
    monkeypatch.setattr(ev, "get_todays_birthdays", lambda: [4070])
    monkeypatch.setattr(ev, "has_user_interacted", lambda _id: True)
    monkeypatch.setattr(ev, "log_event", lambda *args, **kwargs: None)

    membre = _FauxMembre(salons=())        # aucun salon d'accueil : rien ne sera envoye
    faux_bot = _FauxBot(salons=(), membre=membre)

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
        asyncio.run(ev.handle_member_join(faux_bot, membre, "M'aiq"))
        asyncio.run(ev.handle_member_remove(faux_bot, membre, "M'aiq"))
        asyncio.run(ev.check_and_send_birthdays(faux_bot, "M'aiq"))
    finally:
        journal.removeHandler(capteur)
        journal.setLevel(niveau)

    assert any("[ARRIVEE]" in ligne for ligne in lignes), (
        f"aucune trace d'arrivee dans le journal : {lignes}"
    )
    assert any("[DEPART]" in ligne for ligne in lignes), (
        f"aucune trace de depart dans le journal : {lignes}"
    )
    assert any("[ANNIVERSAIRE]" in ligne for ligne in lignes), (
        f"aucune trace d'anniversaire dans le journal : {lignes}"
    )


def test_anniversaire_sans_fete_du_jour_reste_muet_sans_trace(monkeypatch):
    """Lot 2.1 : si la liste d'anniversaires est vide, check_and_send_birthdays reste
    muet et ne journalise rien (gotcha-alerte-qui-crie-pour-du-nominal).
    """
    monkeypatch.setattr(ev, "get_todays_birthdays", lambda: [])
    faux_bot = _FauxBot(salons=())
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
        asyncio.run(ev.check_and_send_birthdays(faux_bot, "Alfred"))
    finally:
        journal.removeHandler(capteur)
        journal.setLevel(niveau)

    assert not any("[ANNIVERSAIRE]" in ligne for ligne in lignes), (
        f"check_and_send_birthdays a journalise alors qu'aucun anniversaire n'etait prevu : {lignes}"
    )


def test_depart_filtre_porte_parole_avant_appel_base(monkeypatch):
    """Lot 2.3 : les 4 bots non porte-parole n'ouvrent aucune connexion a la base
    sur un depart (has_user_interacted ne doit pas etre appele).
    """
    appels_db = []
    monkeypatch.setattr(ev, "has_user_interacted", lambda _id: appels_db.append(_id))
    membre = _FauxMembre(salons=())
    faux_bot = _FauxBot(salons=(), membre=membre)

    for bot_cle, noms in _noms_passes_par_les_bots().items():
        for nom in noms:
            if not ev.participe_aux_evenements(nom):
                appels_db.clear()
                asyncio.run(ev.handle_member_remove(faux_bot, membre, nom))
                assert not appels_db, (
                    f"{nom} a appele has_user_interacted alors qu'il n'est pas porte-parole"
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

def _toutes_les_repliques():
    for dictionnaire in (ev.WELCOME_MESSAGES, ev.GOODBYE_MESSAGES, ev.BIRTHDAY_MESSAGES):
        for cle, messages in dictionnaire.items():
            for message in messages:
                yield cle, message


def test_aucune_didascalie_dans_les_repliques():
    """Alfred ET Sugar interdisent les gestes narres dans leur propre prompt — celui
    d'Alfred donne meme « *soupir* » comme contre-exemple. Trois de ses repliques en
    portaient : elles ne passent NI par le prompt NI par le LLM, donc rien ne les
    rattrapait."""
    import re

    fautifs = [
        f"{cle} : {message[:70]}"
        for cle, message in _toutes_les_repliques()
        if re.search(r"\*[^*]+\*", message)
    ]
    assert not fautifs, "didascalie (geste narre entre asterisques) : " + " | ".join(fautifs)


def test_les_repliques_de_sugar_restent_breves():
    """« ~30 mots, jamais plus » est une REGLE ABSOLUE de son prompt, pas un gout.
    Ses anciennes repliques etaient courtes mais sans voix ; en lui en donnant une,
    le risque bascule de l'autre cote."""
    trop_longues = [
        f"{len(message.split())} mots : {message[:60]}"
        for cle, message in _toutes_les_repliques()
        if cle == "sugar" and len(message.split()) > 30
    ]
    assert not trop_longues, "Sugar depasse ses 30 mots : " + " | ".join(trop_longues)

def test_aucun_bot_n_envoie_lui_meme_dans_les_evenements_serveur():
    """Un `.send()` EN DUR dans `on_member_join` / `on_member_remove` court-circuite
    tout le module partage : `_PORTE_PAROLE`, le tirage, la recherche du salon
    d'accueil, et la journalisation.

    Ce n'est pas theorique. Le 14/09, une arrivee REELLE l'a exhume : Johnny — qui
    n'est pas porte-parole et n'a plus aucun pool depuis 13a5f6b — a accueilli
    l'arrivant a 100 %, dans `guild.system_channel`, et **sans laisser une seule
    ligne de journal**. Ses 5 voisins etaient propres : un bot sur six, mais cette
    fois-ci un de TROP ([[gotcha-un-bot-sur-six-manque-toujours]]).

    Le verrou porte sur les fichiers REELS des 6 bots, par `ast` : l'appel au
    gestionnaire partage est une fonction, un envoi direct est un `.send(...)`.
    """
    violations = []
    for bot, chemin in _FICHIERS_BOTS.items():
        src = open(os.path.join(_parent_dir, chemin), encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in ("on_member_join", "on_member_remove"):
                continue
            for sous in ast.walk(node):
                if (isinstance(sous, ast.Call)
                        and isinstance(sous.func, ast.Attribute)
                        and sous.func.attr == "send"):
                    violations.append(f"{bot} → {node.name} (ligne {sous.lineno})")

    assert not violations, (
        "Envoi en dur dans un evenement serveur — il echappe a _PORTE_PAROLE, au "
        "tirage et au journal : " + ", ".join(violations)
    )


def test_verrou_alfred_et_sugar_envoient_les_autres_se_taisent(monkeypatch):
    """Verrou : sur tirage gagnant (random=0.0), Alfred et Sugar envoient exactement
    un message de leur propre pool dans taverne-des-bots. Les quatre autres ne disent rien.
    """
    monkeypatch.setattr(ev.random, "random", lambda: 0.0)
    monkeypatch.setattr(ev, "has_user_interacted", lambda _id: True)
    monkeypatch.setattr(ev, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ev, "get_todays_birthdays", lambda: [4070])

    gestionnaires = [
        ("arrivee", lambda bot, m, nom: ev.handle_member_join(bot, m, nom), ev.WELCOME_MESSAGES, "@nouveau"),
        ("depart", lambda bot, m, nom: ev.handle_member_remove(bot, m, nom), ev.GOODBYE_MESSAGES, "nouveau"),
        ("anniversaire", lambda bot, m, nom: ev.check_and_send_birthdays(bot, nom), ev.BIRTHDAY_MESSAGES, "@nouveau"),
    ]

    for bot_cle, noms in _noms_passes_par_les_bots().items():
        for nom in noms:
            parle = ev.participe_aux_evenements(nom)
            persona = ev.cle_persona(nom)
            for libelle, action, dictionnaire, valeur in gestionnaires:
                salon = _FauxSalon(name="taverne-des-bots")
                membre = _FauxMembre(salons=[salon])
                faux_bot = _FauxBot(salons=[salon], membre=membre)

                asyncio.run(action(faux_bot, membre, nom))

                if parle:
                    assert len(salon.messages) == 1, (
                        f"{nom} ({libelle}) devait envoyer 1 message, reçu : {len(salon.messages)}"
                    )
                    siennes = {g.format(user=valeur) for g in dictionnaire[persona]}
                    assert salon.messages[0] in siennes, (
                        f"{nom} ({libelle}) a envoyé un message hors de son pool '{persona}' : "
                        f"{salon.messages[0]!r}"
                    )
                else:
                    assert len(salon.messages) == 0, (
                        f"{nom} ({libelle}) ne devait rien envoyer, reçu : {salon.messages}"
                    )


def test_le_tirage_perdu_doit_rester_muet(monkeypatch):
    """Verrou : sur tirage toujours perdant (random=0.99), aucun message n'est envoyé,
    pour aucun des 6 bots, sur aucun des 3 gestionnaires.
    """
    monkeypatch.setattr(ev.random, "random", lambda: 0.99)
    monkeypatch.setattr(ev, "has_user_interacted", lambda _id: True)
    monkeypatch.setattr(ev, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ev, "get_todays_birthdays", lambda: [4070])

    gestionnaires = [
        ("arrivee", lambda bot, m, nom: ev.handle_member_join(bot, m, nom)),
        ("depart", lambda bot, m, nom: ev.handle_member_remove(bot, m, nom)),
        ("anniversaire", lambda bot, m, nom: ev.check_and_send_birthdays(bot, nom)),
    ]

    for bot_cle, noms in _noms_passes_par_les_bots().items():
        for nom in noms:
            for libelle, action in gestionnaires:
                salon = _FauxSalon(name="taverne-des-bots")
                membre = _FauxMembre(salons=[salon])
                faux_bot = _FauxBot(salons=[salon], membre=membre)

                asyncio.run(action(faux_bot, membre, nom))

                assert len(salon.messages) == 0, (
                    f"{nom} ({libelle}) a envoyé un message sur tirage perdu : {salon.messages}"
                )


def test_aucun_bot_MUET_ne_figure_dans_un_dictionnaire_du_module():
    """Lot 3, verrou sur le FICHIER. La decision du 13/09 doit etre VRAIE dans le code :
    les tables de seuils portaient encore `sheogorath` et `maiq`, inatteignables depuis
    `_PORTE_PAROLE` — le code mentait sur la decision.

    ⚠️ La premiere version de ce verrou reperait une table de seuils a la FORME de ses
    valeurs (« toutes des nombres entre 0 et 1 »). Mutation rejouee le 15/09 :

        {"sheogorath": 0.3, "alfred": 0.2, "sugar": _SEUIL_SUGAR}   -> verrou MUET

    Une seule valeur nommee au lieu d'un litteral, et la table entiere devenait
    invisible : `sheogorath` rentrait sans un bruit. C'est [[gotcha-verrou-trop-faible]]
    a l'identique — mesurer la PRESENCE d'une construction ne dit pas qu'elle COUVRE
    l'objet. L'invariant porte donc sur le NOM et sur lui seul : **aucun dictionnaire
    de ce module, hors `_CLE_PAR_BOT`, ne nomme un bot qui ne parle pas**. Seuil, pool
    ou table a inventer demain : la valeur n'a aucune importance.
    """
    chemin = os.path.join(_parent_dir, "shared", "server_events.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read())

    porte_parole, personas, table_des_cles = set(), set(), None
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Assign):
            continue
        for cible in node.targets:
            nom = getattr(cible, "id", None)
            if nom == "_PORTE_PAROLE" and isinstance(node.value, (ast.Set, ast.List, ast.Tuple)):
                porte_parole = {e.value for e in node.value.elts
                                if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            elif nom == "_CLE_PAR_BOT" and isinstance(node.value, ast.Dict):
                table_des_cles = node.value
                personas = {v.value for v in node.value.values
                            if isinstance(v, ast.Constant) and isinstance(v.value, str)}

    assert porte_parole, "_PORTE_PAROLE introuvable dans l'AST"
    assert personas, "_CLE_PAR_BOT introuvable dans l'AST"
    muets = personas - porte_parole
    assert len(muets) == 4, f"4 bots muets attendus, releve : {sorted(muets)}"

    fautifs = []
    for node in ast.walk(arbre):
        if not isinstance(node, ast.Dict) or node is table_des_cles:
            continue
        cles = {k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        intrus = cles & muets
        if intrus:
            fautifs.append(f"ligne {node.lineno} : {sorted(intrus)}")

    assert not fautifs, (
        "un bot qui ne parle JAMAIS est nomme dans un dictionnaire de server_events.py — "
        "le code ment sur la decision du 2026-09-13 : " + " | ".join(fautifs)
    )
