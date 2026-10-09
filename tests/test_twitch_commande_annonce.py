# -*- coding: utf-8 -*-
"""Verrous : `!annonce` rejoue une annonce a la demande, sans mentir sur ce qu'elle montre.

La commande sert a VOIR une annonce — six personas cote a cote — sans attendre qu'un
live demarre. Trois choses doivent rester vraies, et aucune n'est evidente :

  1. elle est enregistree dans le module PARTAGE, donc sur les six bots a la fois ;
  2. elle n'obeit qu'aux gerants du serveur ;
  3. quand la chaine n'est pas en direct, elle garde le VRAI titre et le VRAI jeu, et
     elle AVOUE dans le pied de l'embed ce qui, lui, est faux.

Aucun test n'appelle Twitch ni un modele : les deux sont remplaces.
"""
import ast
import asyncio
import os
import sys

import discord

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from shared.twitch_announcer import (
    ALIAS_BOTS,
    effacer_la_commande,
    TwitchAnnouncer,
    bot_vise,
    enregistrer_commande_annonce,
    lire_arguments_annonce,
)

BOTS = ["Alfred/bot_alfred.py", "JohnnyBot/bot_johnny.py", "MaiqBot/bot_maiq.py",
        "MalenaBot/bot_malena.py", "Sheogorath/bot_sheogorath.py", "SugarBot/bot_sugar.py"]


class _Journal:
    def __init__(self):
        self.lignes = []

    def info(self, msg, **kw):
        self.lignes.append(str(msg))

    warning = error = debug = info


class _Salon:
    """Le salon d'ou part la commande : il retient ce qu'on lui envoie."""
    name = "salon-de-test"
    id = 42

    def __init__(self):
        self.envois = []

    async def send(self, content=None, embed=None):
        self.envois.append((content, embed))


class _Droits:
    def __init__(self, gerant):
        self.manage_guild = gerant
        self.administrator = False


class _Auteur:
    def __init__(self, gerant):
        self.guild_permissions = _Droits(gerant)

    def __str__(self):
        return "quelqu-un"


class _ReponseHttp:
    """`discord.NotFound` et `discord.Forbidden` exigent une reponse HTTP a construire."""
    def __init__(self, status):
        self.status = status
        self.reason = "test"


class _Message:
    """Le message `!annonce…` lui-meme. `leve` simule ce que Discord renverrait."""
    def __init__(self, leve=None):
        self.supprime = False
        self._leve = leve

    async def delete(self):
        if self._leve is not None:
            raise self._leve
        self.supprime = True


class _Contexte:
    def __init__(self, gerant=True, guild=object(), leve=None):
        self.guild = guild
        self.author = _Auteur(gerant)
        self.channel = _Salon()
        self.message = _Message(leve)


class _BotFactice:
    """Le minimum de `commands.Bot` dont l'enregistrement se sert."""
    def __init__(self):
        self.commandes = {}

    def get_command(self, nom):
        return self.commandes.get(nom)

    def command(self, name=None, **kwargs):
        def decorateur(fonction):
            self.commandes[name] = fonction
            return fonction
        return decorateur


STREAM_EN_DIRECT = {
    "id": "123", "user_id": "9", "user_login": "streameuse_amie", "user_name": "streameuse_amie",
    "title": "5 ans de stream et decouverte de Elden Ring !", "game_name": "ELDEN RING",
    "viewer_count": 12, "thumbnail_url": "https://x/{width}x{height}.jpg",
}

INFOS_HORS_LIGNE = {
    "user_id": "9", "user_login": "streameuse_amie", "user_name": "streameuse_amie",
    "title": "5 ans de stream et decouverte de Elden Ring !", "game_name": "ELDEN RING",
    "profile_image_url": "",
}


def _annonceur(stream=None, infos=None, accroche="Ca va saigner."):
    """Un annonceur dont Twitch et le modele sont remplaces."""
    a = TwitchAnnouncer(_BotFactice(), "johnny", _Journal(), "id", "secret")
    a.load_config = lambda: {
        "enabled": True,
        "subscriptions": [{"twitch_login": "streameuse_amie", "discord_channel_id": "777"}],
    }

    async def _streams(logins):
        return {l.lower(): stream for l in logins}

    async def _infos(login):
        return infos

    async def _hype(s):
        return accroche

    a.client.get_streams = _streams
    a.client.get_channel_info = _infos
    a._generate_hype = _hype
    return a


def test_la_commande_est_ajoutee_par_le_module_PARTAGE():
    """Un envoi ecrit en dur dans un bot echappe au module partage, a ses garde-fous et
    a son journal. La commande doit donc naitre dans `setup_twitch_announcer`, que les
    SIX appellent — pas dans six fichiers de bots."""
    chemin = os.path.join(RACINE, "shared", "twitch_announcer.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename=chemin)

    setups = [n for n in ast.walk(arbre)
              if isinstance(n, ast.FunctionDef) and n.name == "setup_twitch_announcer"]
    assert setups, "setup_twitch_announcer a disparu"
    appels = [n for n in ast.walk(setups[0])
              if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "enregistrer_commande_annonce"]
    assert appels, (
        "setup_twitch_announcer n'enregistre plus !annonce : la commande existerait "
        "dans le module sans etre branchee sur un seul bot"
    )

    manquants = [b for b in BOTS
                 if "setup_twitch_announcer" not in open(os.path.join(RACINE, b),
                                                         encoding="utf-8").read()]
    assert not manquants, f"ces bots n'appellent pas le setup partage : {manquants}"


def test_la_commande_ne_s_enregistre_pas_deux_fois():
    """`on_ready` rejoue a chaque reconnexion : sans garde, discord.py leve."""
    bot = _BotFactice()
    journal = _Journal()
    annonceur = _annonceur()
    assert enregistrer_commande_annonce(bot, annonceur, journal) is True
    assert enregistrer_commande_annonce(bot, annonceur, journal) is False
    assert list(bot.commandes) == ["annonce"]


def test_un_non_gerant_n_obtient_AUCUN_envoi():
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=False)
    asyncio.run(bot.commandes["annonce"](ctx))

    assert ctx.channel.envois == [], "un non-gerant a declenche une annonce"
    assert any("refusee" in l for l in journal.lignes), "le refus doit aller au JOURNAL"


def test_en_message_prive_la_commande_ne_fait_rien():
    """Hors serveur il n'y a pas de permission a verifier : ne pas ouvrir une porte."""
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=True, guild=None)
    asyncio.run(bot.commandes["annonce"](ctx))
    assert ctx.channel.envois == []


def test_hors_ligne_le_titre_reste_VRAI_et_le_pied_avoue_la_simulation():
    """Inventer un titre ne testerait rien ; ne rien avouer ferait croire a un live."""
    annonceur = _annonceur(stream=None, infos=INFOS_HORS_LIGNE)
    salon = _Salon()

    resultat = asyncio.run(annonceur.simuler_annonce(salon, "streameuse_amie"))

    assert resultat["ok"] and resultat["simulee"] is True
    contenu, embed = salon.envois[0]
    assert "5 ans de stream" in embed.description, "le titre reel a ete remplace par une invention"
    assert embed.fields[0].value == "ELDEN RING"
    assert "simulation" in embed.footer.text.lower(), (
        "rien ne distingue cette annonce d'un vrai live : le pied doit le dire"
    )
    assert "twitch.tv/streameuse_amie" in contenu


def test_en_direct_rien_n_est_marque_comme_simule():
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    salon = _Salon()

    resultat = asyncio.run(annonceur.simuler_annonce(salon, "streameuse_amie"))

    assert resultat["simulee"] is False
    _, embed = salon.envois[0]
    assert "simulation" not in embed.footer.text.lower()


def test_l_anti_doublon_est_SAUTE_pour_que_les_six_parlent():
    """`_recent_announcement_exists` fait taire le 2e bot qui cite le meme streamer dans
    les 30 minutes. Sur six bots lances ensemble, un seul parlerait."""
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)

    async def _interdit(*a, **k):
        raise AssertionError("l'anti-doublon est sur le chemin : cinq bots seraient muets")

    annonceur._recent_announcement_exists = _interdit
    salon = _Salon()
    asyncio.run(annonceur.simuler_annonce(salon, "streameuse_amie"))
    assert len(salon.envois) == 1


def test_l_annonce_part_dans_le_salon_de_la_COMMANDE():
    """Jamais dans le salon configure : un test n'a rien a faire chez la communaute."""
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=True)
    asyncio.run(bot.commandes["annonce"](ctx))
    assert len(ctx.channel.envois) == 1


def test_sans_streamer_ni_abonnement_la_commande_le_DIT_au_journal():
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    annonceur.load_config = lambda: {"enabled": True, "subscriptions": []}
    salon = _Salon()

    resultat = asyncio.run(annonceur.simuler_annonce(salon, None))
    assert resultat["ok"] is False and salon.envois == []


def test_le_repli_statique_sert_quand_le_modele_se_tait():
    """Un bot muet est pire qu'un bot banal : la phrase statique doit rester joignable."""
    annonceur = _annonceur(stream=STREAM_EN_DIRECT, accroche=None)
    salon = _Salon()

    resultat = asyncio.run(annonceur.simuler_annonce(salon, "streameuse_amie"))
    assert resultat["origine"] == "repli statique"
    contenu, _ = salon.envois[0]
    assert "twitch.tv/streameuse_amie" in contenu


def test_le_nom_d_un_bot_ne_fait_parler_QUE_lui():
    """`!annonce johnny` : les cinq autres doivent se taire, sinon le nom ne sert a rien."""
    parlants = []
    for bot_id in ALIAS_BOTS:
        bot, journal = _BotFactice(), _Journal()
        annonceur = _annonceur(stream=STREAM_EN_DIRECT)
        annonceur.bot_id = bot_id
        enregistrer_commande_annonce(bot, annonceur, journal)

        ctx = _Contexte(gerant=True)
        asyncio.run(bot.commandes["annonce"](ctx, "johnny"))
        if ctx.channel.envois:
            parlants.append(bot_id)

    assert parlants == ["johnny"], f"ces bots ont parle alors qu'on appelait Johnny : {parlants}"


def test_sans_nom_les_SIX_repondent():
    parlants = []
    for bot_id in ALIAS_BOTS:
        bot, journal = _BotFactice(), _Journal()
        annonceur = _annonceur(stream=STREAM_EN_DIRECT)
        annonceur.bot_id = bot_id
        enregistrer_commande_annonce(bot, annonceur, journal)

        ctx = _Contexte(gerant=True)
        asyncio.run(bot.commandes["annonce"](ctx))
        if ctx.channel.envois:
            parlants.append(bot_id)

    assert sorted(parlants) == sorted(ALIAS_BOTS), (
        "sans nom, la commande doit faire parler tout le monde : " + str(parlants)
    )


def test_les_SIX_dossiers_de_bots_sont_dans_la_table_des_alias():
    """Un bot absent de la table ne serait jamais appelable par son nom, en silence."""
    import re

    # L'APPEL, pas l'import ni le bouchon `def setup_twitch_announcer(*a, **k)` que
    # chaque bot definit quand le module partage manque.
    motif = re.compile(r'setup_twitch_announcer\(\s*bot,\s*"([a-z]+)"')
    ids_cables = set()
    for chemin in BOTS:
        source = open(os.path.join(RACINE, chemin), encoding="utf-8").read()
        ids_cables.update(motif.findall(source))

    assert ids_cables == set(ALIAS_BOTS), (
        "la table des alias et les bots cables divergent : "
        f"cables={sorted(ids_cables)} table={sorted(ALIAS_BOTS)}"
    )


def test_un_mot_inconnu_est_lu_comme_un_LOGIN_twitch():
    assert lire_arguments_annonce(()) == (None, None)
    assert lire_arguments_annonce(("johnny",)) == ("johnny", None)
    assert lire_arguments_annonce(("streameuse_amie",)) == (None, "streameuse_amie")
    assert lire_arguments_annonce(("johnny", "streameuse_amie")) == ("johnny", "streameuse_amie")


def test_les_accents_et_l_apostrophe_ne_perdent_pas_le_bot():
    """« M'aiq » tape a la main ne doit pas tomber dans le cas « login Twitch »."""
    assert bot_vise("M'aiq") == "maiq"
    assert bot_vise("Maïq") == "maiq"
    assert bot_vise("SHEO") == "sheogorath"
    assert bot_vise("Sugar-Bot") == "sugar"
    assert bot_vise("streameuse_amie") is None


def test_la_commande_s_efface_et_laisse_la_place_a_l_annonce():
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=True)
    asyncio.run(bot.commandes["annonce"](ctx))

    assert ctx.message.supprime is True, "le `!annonce` de l'utilisateur est reste a l'ecran"
    assert len(ctx.channel.envois) == 1


def test_un_refus_n_efface_PAS_le_message_de_l_utilisateur():
    """Effacer sans rien faire en retour donnerait une commande qui disparait dans le vide."""
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=False)
    asyncio.run(bot.commandes["annonce"](ctx))
    assert ctx.message.supprime is False


def test_l_instruction_interdit_de_VISER_le_live_sans_tuer_la_voix():
    """Alfred, 2026-10-09 EN LIVE : sa fiche « IMPITOYABLEMENT sarcastique, INTERDIT
    d'etre serviable sans mepris » a retourne la pique CONTRE le live (stream presente
    comme penible, invitation tournee en corvee). « TOUJOURS positive » ne suffit pas
    face a une fiche qui impose le mepris : l'instruction doit NOMMER la cible interdite
    — jamais le live — ET garder la voix, en consigne positive
    ([[gotcha-le-prompt-bornait-le-DECOR-pas-la-PERSONNE]]). On verrouille sur
    l'instruction REELLE que _generate_hype construit, en remplacant la cascade pour
    capturer le system_prompt — pas sur une copie de la chaine.
    """
    import shared.llm_cascade as cascade

    capture = {}

    async def _faux_generate(**kw):
        capture["system_prompt"] = kw.get("system_prompt", "")
        return "ok"

    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    annonceur.personality_prompt = "SYSTEM: persona de test"
    annonceur.key_manager = object()  # non-None : sinon _generate_hype se tait

    # _annonceur() remplace _generate_hype par un stub : on appelle la VRAIE methode
    # via la classe pour exercer le prompt reellement construit.
    vrai = cascade.generate_response
    cascade.generate_response = _faux_generate
    try:
        asyncio.run(TwitchAnnouncer._generate_hype(annonceur, STREAM_EN_DIRECT))
    finally:
        cascade.generate_response = vrai

    assert "system_prompt" in capture, "_generate_hype n'a pas atteint la cascade"
    prompt = capture["system_prompt"].lower()

    # 1. La pique est retournee AILLEURS, jamais vers le live qu'on invite a rejoindre.
    assert "jamais vers ce live" in prompt, (
        "l'instruction ne borne plus la CIBLE de l'humour : un persona acerbe peut "
        "redescendre le stream qu'il annonce"
    )
    # 2. La voix n'est pas tuee pour autant : le ton pince-sans-rire reste permis.
    assert "pince-sans-rire" in prompt, (
        "le correctif a efface la voix au lieu de rediriger la pique : un bot banal "
        "n'est pas le but"
    )


def test_le_bot_qui_n_est_pas_VISE_ne_touche_a_rien():
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    annonceur.bot_id = "alfred"
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=True)
    asyncio.run(bot.commandes["annonce"](ctx, "johnny"))
    assert ctx.message.supprime is False and ctx.channel.envois == []


def test_a_six_le_message_deja_supprime_est_le_cas_NOMINAL():
    """Cinq bots sur six tombent sur un NotFound : ni cri au journal, ni annonce perdue."""
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=True, leve=discord.NotFound(_ReponseHttp(404), "deja supprime"))
    asyncio.run(bot.commandes["annonce"](ctx))

    assert len(ctx.channel.envois) == 1, "l'annonce doit partir meme si le menage a rate"
    assert not [l for l in journal.lignes if "⚠️" in l or "impossible" in l], (
        "le cas nominal a six bots ne doit pas alarmer : " + str(journal.lignes)
    )


def test_sans_la_permission_l_annonce_part_QUAND_MEME():
    bot, journal = _BotFactice(), _Journal()
    annonceur = _annonceur(stream=STREAM_EN_DIRECT)
    enregistrer_commande_annonce(bot, annonceur, journal)

    ctx = _Contexte(gerant=True, leve=discord.Forbidden(_ReponseHttp(403), "pas le droit"))
    asyncio.run(bot.commandes["annonce"](ctx))

    assert len(ctx.channel.envois) == 1
    assert any("Gerer les messages" in l for l in journal.lignes)


def test_effacer_la_commande_rend_VRAI_seulement_quand_elle_a_efface():
    journal = _Journal()
    ctx = _Contexte()
    assert asyncio.run(effacer_la_commande(ctx, journal)) is True
    assert asyncio.run(effacer_la_commande(
        _Contexte(leve=discord.NotFound(_ReponseHttp(404), "x")), journal)) is False


def test_l_accroche_de_live_INVITE_autorise_l_emoji_et_reste_honnete():
    """Trois exigences qui tiennent ensemble, et qu'on perd une par une en reecrivant.

    - INVITER : « donne envie de regarder » rendait des constats polis (« X est en live »).
    - EMOJI : rien ne les retire sur ce chemin, mais tant qu'on ne les demandait pas
      l'accroche sortait seche.
    - HONNETE : c'est precisement une accroche enthousiaste qui invente une note, un
      superlatif ou une scene du live que le bot n'a pas regardee — et le salon y croit.
    """
    import inspect

    from shared.twitch_announcer import TwitchAnnouncer

    source = inspect.getsource(TwitchAnnouncer._generate_hype)
    for attendu in (
        "DONNE ENVIE DE REJOINDRE",
        "emoji",
        "n'invente AUCUN fait",
        "tu ne l'as pas regardé",
        "N'écris PAS le lien",
    ):
        assert attendu in source, f"l'instruction d'annonce ne dit plus : {attendu}"


def _instruction_d_annonce() -> str:
    """La consigne REELLEMENT envoyee au modele, commentaires exclus.

    ⚠️ `inspect.getsource` rend la fonction ENTIERE, commentaires compris — et le
    commentaire au-dessus du prompt raconte l'incident du 2026-09-18, donc il contient les
    memes mots que la consigne. Un verrou qui cherche « genre » dans cette source passe
    au vert alors que l'instruction ne dit plus rien : mesure du 2026-09-18, le mot retire
    du prompt, le test restait vert. C'est [[gotcha-verrou-trop-faible]] — la PRESENCE
    d'un mot dans le fichier n'est pas sa presence dans l'OBJET qu'on protege.
    """
    import inspect

    from shared.twitch_announcer import TwitchAnnouncer

    source = inspect.getsource(TwitchAnnouncer._generate_hype)
    debut = source.index("system_prompt = (")
    fin = source.index("try:", debut)
    bloc = source[debut:fin]
    # Les commentaires peuvent aussi vivre DANS le bloc : on ne garde que les lignes de
    # chaine, seules a partir chez le modele.
    return "\n".join(
        ligne for ligne in bloc.splitlines()
        if not ligne.strip().startswith("#")
    )


def test_l_accroche_n_invente_rien_sur_LA_PERSONNE_qui_stream():
    """Vu EN LIVE le 2026-09-18 (johnny, 12:12) :

        « Cinq ans de stream et un premier pas dans Elden Ring AVEC streameuse_amie »

    streameuse_amie EST la streameuse, et elle jouait seule. Deux faits inventes dans une seule
    phrase : son anciennete, et une coequipiere.

    La borne d'honnetete d'alors enumerait le JEU et le LIVE ; la PERSONNE n'y figurait
    pas, alors que la consigne juste au-dessus demande de « mettre en valeur le streamer »
    a temperature 0.95. Le prompt AUTORISAIT donc a broder sur quelqu'un et ne bornait que
    le decor ([[gotcha-une-permission-bat-une-demonstration]]).

    Le verrou vise les trois manques separement : ils ont trois causes et se reperdent un
    par un a la prochaine reecriture.
    """
    source = _instruction_d_annonce()

    # 1. l'anciennete et le passe : « cinq ans de stream » n'est vrai nulle part.
    assert "LA PERSONNE qui stream" in source and "ancienneté" in source, (
        "l'instruction n'interdit plus d'inventer un passe au streamer"
    )
    # 2. le ROLE du nom : sans lui, « ne mens pas » ne protege de rien, le modele ne
    #    recevant qu'un nom sans savoir de qui il parle.
    assert "LA PERSONNE QUI JOUE" in source, (
        "l'instruction ne dit plus QUI est la personne nommee : le modele peut la prendre "
        "pour un coequipier, un jeu ou un personnage"
    )
    assert "à plusieurs" in source, (
        "l'instruction ne refuse plus de supposer un live joue a plusieurs"
    )
    # 3. le genre. ⚠️ Le verrou vise la CONSIGNE POSITIVE, pas le mot « genre » : le
    #    premier jet disait « tourne ta phrase pour n'avoir pas a le deviner » et rendait
    #    4 tirages masculins sur 6 pour une streameuse. Mesure du 2026-09-18, memes
    #    conditions, apres reecriture : 1 sur 6. Une interdiction abstraite ne tient pas
    #    contre le masculin par defaut du francais ; dire quoi ECRIRE tient.
    assert "DÉSIGNE-LA TOUJOURS PAR SON NOM" in source, (
        "l'instruction ne dit plus de nommer la personne : sans consigne POSITIVE, le "
        "modele retombe sur le masculin par defaut et invente le genre d'une personne reelle"
    )
    assert "homme ou une femme" in source, (
        "l'instruction ne dit plus que le genre est INCONNU : la consigne de nommage perd "
        "sa raison d'etre et se fait negocier au premier tirage"
    )


def test_l_accroche_DECRIT_la_tournure_fautive_sans_la_MONTRER():
    """Une demonstration bat une interdiction — deja paye deux fois dans ce depot.

    Le 2026-09-16, `❌ INTERDIT : *allume une clope*` ENSEIGNAIT la didascalie qu'il
    interdisait (5 demos chez Johnny, 4 chez Alfred). Le 2026-09-18, la fiche d'Alfred a
    ete de-citee pour la meme raison, et sa fidelite est MONTEE en perdant ses exemples.

    Ecrire ici la tournure fautive — la preposition d'accompagnement suivie du nom du
    streamer — la placerait mot pour mot dans le contexte, a deux lignes de l'endroit ou
    le modele redige, et avec le VRAI nom interpole dedans. Le verrou interdit donc que
    l'instruction contienne ce gabarit, quelle que soit la facon dont il est amene.
    """
    import re

    # QUE la chaine d'instruction : le commentaire du dessus cite l'incident, c'est sa
    # fonction, et il ne part jamais au modele.
    instruction = _instruction_d_annonce()

    gabarit = re.compile(r"avec\s*\{?\s*streamer", re.IGNORECASE)
    assert not gabarit.search(instruction), (
        "l'instruction MONTRE la tournure qu'elle interdit, le nom du streamer interpole "
        "dedans : c'est le gabarit exact que le modele va reproduire "
        "([[gotcha-le-prompt-enseigne-le-tic-interdit]]). La decrire, ne pas la citer."
    )
