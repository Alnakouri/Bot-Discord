"""La phrase de lien de Sugar s'accroche au JEU diffuse — et retombe seule sans jeu.

Demande d'Ahmed le 2026-09-21 : « j'aimerai que l'annonce de sugar pour !discord s'adapte
au jeu diffuse par le stream ; s'il n'y a pas de jeu elle fait son annonce normale. »

⚠️ Ce que la mesure a montre en plus, et qui est la vraie raison de garder ca : le jeu est
la SEULE chose vraie qu'on puisse donner au modele sur le moment present. Depuis le 19/09,
prive de tout fait, il en inventait un (« une bonne tasse de caramel chaud »). Avec le jeu,
sur 6 generations : **6/6 accrochent le jeu, 0/6 inventent un objet**, et la variete revient
(sans jeu, « Viens nous voir » ouvrait 9 phrases sur 12).

    Moins complique que de battre Malenia, viens donc nous retrouver sur le serveur. ✨
    Mieux vaut y fuir les boss d'Elden Ring qu'affronter mon sarcasme la-bas. 🍬
"""
import asyncio
import types

import pytest

from shared.twitch.dispatch import DispatchMixin

# Les bots pour lesquels l'accroche a ete MESUREE.
BOTS_MESURES = {"sugar", "alfred", "malena", "johnny"}


def _faux_bot(bot_id="sugar", channels=("un_canal",), avec_cles=True):
    class Faux(DispatchMixin):
        pass

    f = Faux()
    f.bot_id = bot_id
    f.channels = list(channels)
    f.client_id = "id" if avec_cles else None
    f.client_secret = "secret" if avec_cles else None
    f.personality_prompt = "tu es un bot"
    f.system_prompt_provider = None
    f.key_manager = object()
    f.logger = types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None,
                                     warning=lambda *a, **k: None, error=lambda *a, **k: None)
    return f


def _helix(rendu, attend_live_only=True):
    """⚠️ Le faux DOIT accepter `live_only`, et verifier qu'on le lui passe.

    Sans cette assertion, le jour ou `_jeu_en_cours` cesserait de demander le direct, le
    faux rendrait le jeu quand meme et le test resterait vert — alors qu'en prod
    l'invitation se remettrait a parler du jeu de la veille, stream eteint.
    """
    class H:
        async def get_current_game(self, chan, live_only=False):
            assert live_only is attend_live_only, (
                "`_jeu_en_cours` doit demander le DIRECT : hors direct, Twitch rend "
                "toujours la derniere categorie de la chaine."
            )
            if isinstance(rendu, Exception):
                raise rendu
            return rendu
    return H()


def test_seuls_les_bots_mesures_accrochent_le_jeu():
    assert set(DispatchMixin.ACCROCHE_AU_JEU) == BOTS_MESURES, (
        "un bot a ete ajoute a ACCROCHE_AU_JEU. Trois des six en sont DEHORS pour des "
        "raisons MESUREES : M'aiq ouvre 4 phrases sur 6 avec la meme formule sans rien "
        "gagner ; Sheogorath a enfin ete mesure le 2026-09-22, sur ministral, 18 "
        "generations par bras, et le jeu le DISQUALIFIE — il repare l'objet invente "
        "mieux que tout (12/18 -> 1/18) mais fait disparaitre L'INVITATION une fois sur "
        "deux (18/18 -> 9/18, p = 0,001) et concentre les ouvertures sur « Ah, ces... » "
        "13 fois sur 18, pire que le 4/6 qui avait exclu M'aiq. Une invitation qui "
        "n'invite plus n'est pas une invitation : il recoit une CLAUSE a la place "
        "(cf. test_phrase_de_lien_clause_par_bot.py). Mesurer d'abord."
    )


def test_le_jeu_diffuse_est_rendu_tel_quel():
    f = _faux_bot()
    f._helix_client = _helix(("Elden Ring", "42"))
    assert asyncio.run(f._jeu_en_cours()) == "Elden Ring"


@pytest.mark.parametrize("categorie", [
    "Just Chatting", "just chatting", "Music", "Art", "Special Events",
    "Talk Shows & Podcasts", "", "   ",
])
def test_les_categories_qui_ne_sont_pas_des_jeux_ne_declenchent_rien(categorie):
    """S'accrocher a « Just Chatting » ferait dire n'importe quoi au bot."""
    f = _faux_bot()
    f._helix_client = _helix((categorie, "1"))
    assert asyncio.run(f._jeu_en_cours()) is None


@pytest.mark.parametrize("bot, canaux, cles", [
    ("sugar", (), True),        # aucun canal configure
    ("sugar", ("c",), False),   # pas d'identifiants Twitch
])
def test_sans_canal_ni_identifiants_on_retombe_sur_none(bot, canaux, cles):
    f = _faux_bot(bot, canaux, cles)
    assert asyncio.run(f._jeu_en_cours()) is None


def test_un_helix_en_panne_ne_casse_pas_l_invitation():
    """⚠️ Le repli demande : sans jeu, l'annonce NORMALE sort. Jamais d'exception ici."""
    f = _faux_bot()
    f._helix_client = _helix(RuntimeError("Twitch injoignable"))
    assert asyncio.run(f._jeu_en_cours()) is None


def test_le_jeu_entre_dans_la_cle_du_cache():
    """Sans ca, un changement de jeu laisserait tourner 15 minutes l'ancienne phrase.

    ⚠️ On verifie la LECTURE et l'ECRITURE du cache, pas la presence du mot `jeu` dans le
    fichier : une cle qui contiendrait le jeu a l'ecriture mais pas a la lecture ferait
    regenerer a chaque appel, et un `!discord` tape dix fois couterait dix appels LLM.
    """
    import ast
    import inspect

    source = inspect.getsource(DispatchMixin._generate_link_line)
    arbre = ast.parse(source.lstrip())
    cles = [n for n in ast.walk(arbre)
            if isinstance(n, ast.Assign)
            and getattr(n.targets[0], "id", "") == "cle_cache"]
    assert cles, "la cle de cache n'est plus construite"
    elements = [e.id for e in cles[0].value.elts if isinstance(e, ast.Name)]
    assert "jeu" in elements, f"le jeu ne fait pas partie de la cle de cache : {elements}"

    # Et le cache est bien lu ET ecrit avec cette cle.
    lectures = [n for n in ast.walk(arbre)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "get"
                and getattr(n.func.value, "id", "") == "cache"]
    assert any(getattr(a, "id", "") == "cle_cache" for n in lectures for a in n.args), \
        "le cache est lu avec une autre cle que celle qui l'ecrit"


def test_fiche_courte_comportement():
    from shared.twitch.game_info import fiche_courte
    assert fiche_courte(None) is None
    assert fiche_courte({}) is None
    assert fiche_courte({"summary": ""}) is None
    
    game = {
        "summary": "Un jeu d'aventure historique médiéval.",
        "themes": [{"id": 1, "name": "Action"}, {"id": 2, "name": "Historical"}]
    }
    assert fiche_courte(game) == "Résumé : Un jeu d'aventure historique médiéval. | Thèmes : Action, Historical"

    # Sans thèmes
    assert fiche_courte({"summary": "Texte court"}) == "Résumé : Texte court"


def test_igdb_refuse_id_non_entier():
    from shared.twitch.game_info import IGDBClient
    client = IGDBClient("client_id", "client_secret")
    assert asyncio.run(client.get_game_by_id("1; fields *")) is None
    assert asyncio.run(client.get_game_by_id(None)) is None


def test_fiche_du_jeu_ne_leve_jamais():
    f = _faux_bot()
    f._helix_client = _helix(RuntimeError("Twitch en panne"))
    assert asyncio.run(f._fiche_du_jeu()) is None


def test_instruction_inclut_la_fiche_si_disponible():
    bot = _faux_bot("sugar")
    async def faux_jeu():
        return "Kingdom Come: Deliverance II"
    async def faux_fiche():
        return "Résumé : 15th century RPG | Thèmes : Action, Historical"

    bot._jeu_en_cours = faux_jeu
    bot._fiche_du_jeu = faux_fiche

    capture = {}
    async def faux_ecrire(instruction, system_prompt, cmd):
        capture["instruction"] = instruction
        return "Venez nous voir !"

    bot._ecrire_phrase_de_lien = faux_ecrire
    asyncio.run(bot._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert "Voici la fiche officielle de ce jeu (en anglais) :" in capture["instruction"]
    assert "RPG" in capture["instruction"]
    # ⚠️ La date de la fiche ne va plus au modele : elle devenait un tic (23/09).
    assert "15th century" not in capture["instruction"]


def test_instruction_sans_fiche_ne_contient_pas_de_fiche():
    bot = _faux_bot("sugar")
    async def faux_jeu():
        return "Kingdom Come: Deliverance II"
    async def faux_fiche():
        return None

    bot._jeu_en_cours = faux_jeu
    bot._fiche_du_jeu = faux_fiche

    capture = {}
    async def faux_ecrire(instruction, system_prompt, cmd):
        capture["instruction"] = instruction
        return "Venez nous voir !"

    bot._ecrire_phrase_de_lien = faux_ecrire
    asyncio.run(bot._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert "Voici la fiche officielle de ce jeu (en anglais) :" not in capture["instruction"]



def test_une_phrase_EN_CACHE_ne_va_pas_chercher_la_fiche():
    """La fiche se cherchait AVANT le cache : chaque `!discord` servi depuis le cache
    payait la requete, et un IGDB en panne (echec jamais mis en cache) coutait jusqu'a
    3 s d'attente par invitation, devant le chat.
    """
    import time

    bot = _faux_bot("sugar")

    async def faux_jeu():
        return "Kingdom Come: Deliverance II"

    appels = []

    async def faux_fiche():
        appels.append(1)
        return None

    bot._jeu_en_cours = faux_jeu
    bot._fiche_du_jeu = faux_fiche
    bot._link_lines_cache = {("discord", "Kingdom Come: Deliverance II"):
                             (time.time(), "Deja ecrite. 🍬")}

    res = asyncio.run(bot._generate_link_line("discord", "le serveur", "https://x.y"))
    assert res == "Deja ecrite. 🍬 https://x.y"
    assert appels == [], "la fiche a ete cherchee alors que la phrase sortait du cache"


def test_clause_jeu_specifique_sugar():
    from shared.twitch.dispatch import DispatchMixin
    clause_sugar = DispatchMixin.CLAUSES_JEU_PAR_BOT["sugar"]

    # 1. sugar + jeu -> clause présente
    bot_sugar = _faux_bot("sugar")
    async def faux_jeu():
        return "Kingdom Come: Deliverance II"
    bot_sugar._jeu_en_cours = faux_jeu
    capture = {}
    async def faux_ecrire(instruction, system_prompt, cmd):
        capture["instruction"] = instruction
        return "Venez nous voir !"
    bot_sugar._ecrire_phrase_de_lien = faux_ecrire

    asyncio.run(bot_sugar._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert clause_sugar in capture["instruction"]

    # 2. sugar sans jeu -> clause absente
    bot_sugar_sans_jeu = _faux_bot("sugar")
    async def faux_jeu_none():
        return None
    bot_sugar_sans_jeu._jeu_en_cours = faux_jeu_none
    capture_sans_jeu = {}
    async def faux_ecrire_sans_jeu(instruction, system_prompt, cmd):
        capture_sans_jeu["instruction"] = instruction
        return "Venez nous voir !"
    bot_sugar_sans_jeu._ecrire_phrase_de_lien = faux_ecrire_sans_jeu

    asyncio.run(bot_sugar_sans_jeu._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert clause_sugar not in capture_sans_jeu["instruction"]

    # 3. alfred + jeu -> clause absente
    bot_alfred = _faux_bot("alfred")
    bot_alfred._jeu_en_cours = faux_jeu
    capture_alfred = {}
    async def faux_ecrire_alfred(instruction, system_prompt, cmd):
        capture_alfred["instruction"] = instruction
        return "Venez nous voir !"
    bot_alfred._ecrire_phrase_de_lien = faux_ecrire_alfred

    asyncio.run(bot_alfred._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert clause_sugar not in capture_alfred["instruction"]



def _helix_qui_note(vus):
    class H:
        async def get_current_game(self, chan, live_only=False):
            vus.append(chan)
            return ("Elden Ring", "42")
    return H()


def test_le_jeu_est_lu_sur_le_canal_de_la_commande_pas_le_premier():
    """⚠️ 23/09 : sur #chaine_du_dev, Sugar parlait du jeu de ma_streameuse —
    `_jeu_en_cours` lisait toujours le PREMIER canal configure."""
    from shared.twitch import dispatch

    vus = []
    f = _faux_bot(channels=("ma_streameuse", "chaine_du_dev"))
    f._helix_client = _helix_qui_note(vus)

    async def depuis(chan):
        jeton = dispatch._CANAL_COURANT.set(chan)
        try:
            return await f._jeu_en_cours()
        finally:
            dispatch._CANAL_COURANT.reset(jeton)

    asyncio.run(depuis("#Chaine_Du_Dev"))
    asyncio.run(f._jeu_en_cours())          # hors commande : repli sur le premier canal
    assert vus == ["chaine_du_dev", "ma_streameuse"]


def test_une_commande_transmet_SON_canal_au_callback(monkeypatch):
    """De bout en bout, par le vrai `_handle_command` : le callback voit le canal d'ou
    vient la commande, et deux commandes entrelacees ne se volent pas leur canal."""
    import collections
    from shared.twitch import dispatch

    async def faux_envoi(*a, **k):
        return None
    monkeypatch.setattr(dispatch, "send_chat_safe", faux_envoi)

    f = _faux_bot(channels=("ma_streameuse", "chaine_du_dev"))
    f.command_aliases = {}
    f.user_cooldowns, f.command_cooldowns = {}, {}
    f.global_msg_timestamps = collections.deque()

    vus = []

    async def callback(author, args):
        await asyncio.sleep(0.01)            # l'appel LLM, pendant lequel l'autre passe
        vus.append((author, f._canal_du_jeu()))
        return "ok"

    f.commands = {"discord": callback}

    # le cooldown global de 5 s par commande bloquerait la 2e : on le contourne par un
    # second nom de commande pointant sur le meme callback
    f.commands["discord2"] = callback

    async def entrelacees():
        await asyncio.gather(
            f._handle_command("chaine_du_dev", "a", "!discord", None),
            f._handle_command("ma_streameuse", "b", "!discord2", None),
        )

    asyncio.run(entrelacees())
    assert sorted(vus) == [("a", "chaine_du_dev"), ("b", "ma_streameuse")]
    assert dispatch._CANAL_COURANT.get() is None, "le canal fuit hors de la commande"


def test_appliquer_variante_sans_texte_leve():
    """Une instruction qui ne contient pas le texte demande fait lever ErreurVariante."""
    from tools.sonde_phrase_de_lien import appliquer_variante, ErreurVariante

    f = _faux_bot("sugar")
    appliquer_variante(f, ["texte_qui_n_existe_pas_dans_l_instruction"], ["remplacement"])
    with pytest.raises(ErreurVariante) as exc_info:
        asyncio.run(f._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert "doit apparaître EXACTEMENT UNE fois" in str(exc_info.value)
    assert "0 trouvé(s)" in str(exc_info.value)


def test_appliquer_variante_remplace_exactement_une_fois():
    """Une instruction avec le texte demande le remplace exactement une fois."""
    from tools.sonde_phrase_de_lien import appliquer_variante

    f = _faux_bot("sugar")
    capture = {}

    async def faux_ecrire(instruction, system_prompt, cmd):
        capture["instruction"] = instruction
        return "Venez nous voir !"

    f._ecrire_phrase_de_lien = faux_ecrire

    cible = "Ta phrase ne parle que du serveur Discord."
    remplacement = "Ta phrase ne parle que du repaire secret."
    appliquer_variante(f, [cible], [remplacement])

    res = asyncio.run(f._generate_link_line("discord", "le serveur", "https://discord.gg/test"))
    assert res is not None
    assert cible not in capture["instruction"]
    assert remplacement in capture["instruction"]
    assert capture["instruction"].count(remplacement) == 1


def test_la_bas_absent_de_la_clause_jeu_de_sugar():
    """SUITE 2 : la clause jeu de Sugar ne doit plus contenir 'là-bas'."""
    clause = DispatchMixin.CLAUSES_JEU_PAR_BOT["sugar"]
    assert "là-bas" not in clause.lower(), "« là-bas » est encore dans la clause jeu de Sugar"
    assert "serveur Discord" in clause, "la clause jeu de Sugar doit nommer le serveur Discord"


def test_la_bas_absent_du_texte_commun_de_la_phrase_de_lien():
    """SUITE 2-bis : le texte commun de _generate_link_line ne doit plus contenir 'là-bas'."""
    import ast
    import inspect
    import textwrap

    source = inspect.getsource(DispatchMixin._generate_link_line)
    arbre = ast.parse(textwrap.dedent(source))
    # Toutes les constantes chaînes (y compris les fragments de f-strings)
    chaines = [n.value for n in ast.walk(arbre) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    # Fragments appartenant à l'instruction
    fragments_instruction = [
        s for s in chaines
        if "Écris UNE seule phrase" in s or "Ta phrase" in s or "ne promets pas" in s or "⚠️ En ce moment" in s
    ]
    assert fragments_instruction, "Fragments d'instruction non trouvés par AST"
    for fragment in fragments_instruction:
        assert "là-bas" not in fragment.lower(), (
            f"« là-bas » trouvé dans le texte commun de l'instruction : {fragment!r}"
        )


