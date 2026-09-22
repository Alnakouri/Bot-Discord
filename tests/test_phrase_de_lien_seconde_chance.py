"""Les filets REJETTENT : sans seconde chance, une faute au tirage coute l'invitation.

Le 2026-09-22, en demandant a la phrase de « claquer », 2 generations sur 8 retournaient
la pique contre le chat Twitch — « fatigue moins que de supporter vos commentaires en
boucle » — alors que la clause dit « jamais sur ceux qui regardent ». Une interdiction de
prompt tient a 75 %, c'est la lecon de la soiree : d'ou un filet deterministe.

Mais un filet qui rejette sans rien proposer fait sortir le gabarit fixe une fois sur
quatre. Un SECOND appel ramene ce risque a ~6 %, pour ~1,4 s de plus (la mediane mesuree
de flash-lite le soir meme). Deux essais, pas trois : quelqu'un attend devant son chat.

⚠️ Ce fichier garde les quatre chemins, parce que trois d'entre eux sont muets en prod —
un rattrapage, un double rejet et une panne franche se ressemblent tous depuis le salon.
"""
import asyncio
import types

import pytest

from shared.twitch.dispatch import DispatchMixin


def _bot(sorties):
    """Un bot dont l'appel au modele rend `sorties`, dans l'ordre."""
    class Faux(DispatchMixin):
        bot_id = "sugar"
        bot_label = "Sugar"
        channels = []
        client_id = client_secret = None
        key_manager = object()
        mistral_client = groq_client = None
        personality_prompt = "fiche"
        system_prompt_provider = None
        logger = types.SimpleNamespace(
            debug=lambda *a, **k: None, info=lambda *a, **k: None,
            warning=lambda *a, **k: None, error=lambda *a, **k: None)

    f = Faux()
    restant = list(sorties)
    f.appels = 0

    async def faux_appel(instruction, system_prompt, cmd):
        f.appels += 1
        return restant.pop(0) if restant else None

    f._ecrire_phrase_de_lien = faux_appel
    return f


def _lancer(bot):
    return asyncio.run(bot._generate_link_line("discord", "le serveur", "https://x.y"))


def test_une_phrase_propre_ne_coute_qu_un_appel():
    bot = _bot(["Viens voir, on t'attend pour rire un coup. 🍬"])
    assert _lancer(bot) == "Viens voir, on t'attend pour rire un coup. 🍬 https://x.y"
    assert bot.appels == 1, "un second appel a ete paye pour rien"


def test_une_phrase_rejetee_est_RATTRAPEE_par_le_second_essai():
    bot = _bot(["Mieux vaut nous voir que vos tchats.",
                "Viens rire avec nous. 🍬"])
    assert _lancer(bot) == "Viens rire avec nous. 🍬 https://x.y"
    assert bot.appels == 2


def test_deux_rejets_rendent_la_main_au_gabarit_fixe():
    """Et surtout : on s'ARRETE a deux. Trois appels feraient du gabarit fixe le choix
    le plus rapide, ce qui serait absurde."""
    bot = _bot(["Mieux vaut nous voir que vos tchats.",
                "On s'en reparlera, viens."])
    assert _lancer(bot) is None
    assert bot.appels == 2


def test_une_panne_franche_ne_declenche_PAS_de_second_appel():
    """⚠️ Un modele muet le restera : reessayer, c'est doubler l'attente pour rien."""
    bot = _bot([None, "cette phrase ne doit jamais etre demandee"])
    assert _lancer(bot) is None
    assert bot.appels == 1


@pytest.mark.parametrize("faute", [
    "Mourir cent fois fatigue moins que de supporter vos commentaires en boucle, viens.",
    "Mieux vaut nous voir que vos tchats en silence.",
    "Mourir cent fois fatigue moins que supporter ton chat en boucle, viens souffler.",
])
def test_les_fautes_mesurees_sont_bien_celles_qui_declenchent_le_rattrapage(faute):
    bot = _bot([faute, "Viens rire avec nous. 🍬"])
    assert _lancer(bot) == "Viens rire avec nous. 🍬 https://x.y"
    assert bot.appels == 2, f"cette faute n'a pas ete rejetee : {faute}"


@pytest.mark.parametrize("phrase,jeu,attendu", [
    ("Le treizième siècle sans armure, ça pique un peu, mais on t'attend de pied ferme sur le discord. ✨", "Kingdom Come: Deliverance II", True),
    ("Entre deux roustes au Moyen Âge, viens donc faire un tour sur le serveur, on t'y garde une place au chaud. 🍬", "Kingdom Come: Deliverance II", False),
    ("En 1403 on se battait moins bien que toi, viens nous voir.", "Kingdom Come: Deliverance II", True),
    ("Au XVe, même les chevaliers auraient rejoint le serveur.", "Kingdom Come: Deliverance II", True),
    ("La vie de chevalier use, viens souffler avec nous.", "Kingdom Come: Deliverance II", False),
    ("Night City t'attend en 2077, viens nous voir.", "Cyberpunk 2077", False),
    ("Le treizième siècle sans armure, ça pique un peu, mais on t'attend de pied ferme sur le discord. ✨", None, False),
    ("Viens nous voir, on t'attend depuis des siècles. 🍬", "Kingdom Come: Deliverance II", True),
])
def test_affirme_une_epoque(phrase, jeu, attendu):
    from shared.twitch.dispatch import _affirme_une_epoque
    assert _affirme_une_epoque(phrase, jeu) is attendu


def test_une_epoque_inventee_est_RATTRAPEE_par_le_second_essai():
    bot = _bot(["Le treizième siècle sans armure, ça pique un peu, mais on t'attend. ✨",
                "Entre deux roustes, viens souffler avec nous. 🍬"])

    async def jeu():
        return "Kingdom Come: Deliverance II"
    bot._jeu_en_cours = jeu

    assert _lancer(bot) == "Entre deux roustes, viens souffler avec nous. 🍬 https://x.y"
    assert bot.appels == 2

