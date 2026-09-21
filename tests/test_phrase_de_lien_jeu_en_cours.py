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
    f.logger = types.SimpleNamespace(debug=lambda *a, **k: None, info=lambda *a, **k: None,
                                     warning=lambda *a, **k: None, error=lambda *a, **k: None)
    return f


def _helix(rendu):
    class H:
        async def get_current_game(self, chan):
            if isinstance(rendu, Exception):
                raise rendu
            return rendu
    return H()


def test_seuls_les_bots_mesures_accrochent_le_jeu():
    assert set(DispatchMixin.ACCROCHE_AU_JEU) == BOTS_MESURES, (
        "un bot a ete ajoute a ACCROCHE_AU_JEU. Trois des six en sont DEHORS pour des "
        "raisons mesurees : M'aiq ouvre 4 phrases sur 6 avec la meme formule sans rien "
        "gagner, et Sheogorath n'a jamais pu etre mesure (429 Groq, 2 generations "
        "exploitables sur 6). Mesurer d'abord, 6 generations sur sa vraie tete."
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
