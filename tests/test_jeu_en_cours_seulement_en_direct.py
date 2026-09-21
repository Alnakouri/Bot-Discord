"""« Le stream est terminé » — et l'invitation parlait toujours du jeu de la veille.

Constate le 2026-09-22, juste apres la fin d'un live. `HelixClient.get_current_game` a
DEUX etapes : `helix/streams` (ce qui passe en direct) puis, si le stream est hors ligne,
un repli sur `helix/channels` qui rend **la derniere categorie posee sur la chaine**.

Ce repli est juste pour ce a quoi il servait — repondre a une question sur le jeu marche
tres bien hors direct. Il est FAUX pour l'accroche de la phrase de lien : la demande
d'Ahmed etait « qu'elle s'adapte au jeu DIFFUSE par le stream ; s'il n'y a pas de jeu,
elle fait son annonce normale ». Stream fini = pas de jeu diffuse.

D'ou `live_only=True`, qui change le SENS de la reponse sans toucher a l'autre appelant.
⚠️ Le cache retient desormais AUSSI d'ou venait la reponse : sans ca, une entree posee
pendant le direct aurait continue de valoir « en direct » pendant trois minutes apres la
fin du stream — et une entree ecrite par l'ancienne version n'aurait aucune liveness.
"""
import asyncio
import time

import pytest

from shared.twitch import game_info as G


def _helix():
    return G.HelixClient("un-id", "un-secret")


def _cache(entree):
    G.HELIX_CACHE.clear()
    G.HELIX_CACHE["un_canal"] = entree


def _jeu(live_only):
    return asyncio.run(_helix().get_current_game("un_canal", live_only=live_only))


def test_en_direct_le_jeu_est_rendu_dans_les_deux_modes():
    _cache(("Elden Ring", "1", time.time(), True))
    assert _jeu(True) == ("Elden Ring", "1")
    assert _jeu(False) == ("Elden Ring", "1")


def test_hors_direct_live_only_ne_rend_rien():
    """LE test : c'est ce chemin qui faisait parler l'invitation du jeu de la veille."""
    _cache(("Elden Ring", "1", time.time(), False))
    assert _jeu(True) == (None, None)


def test_hors_direct_l_autre_appelant_garde_sa_reponse():
    """⚠️ Le repli hors direct n'est pas un bug : il sert a repondre aux questions sur le
    jeu quand la chaine est eteinte. On ne le retire pas, on le rend OPTIONNEL."""
    _cache(("Elden Ring", "1", time.time(), False))
    assert _jeu(False) == ("Elden Ring", "1")


def test_une_entree_de_cache_SANS_liveness_est_traitee_comme_hors_direct():
    """Les entrees ecrites avant le 2026-09-22 n'ont que trois elements.

    Le choix prudent est de les considerer hors direct : au pire l'invitation normale
    sort pendant trois minutes, au lieu de parler d'un jeu qui n'est plus diffuse.
    """
    _cache(("Elden Ring", "1", time.time()))
    assert _jeu(True) == (None, None)
    assert _jeu(False) == ("Elden Ring", "1")


def test_un_cache_perime_n_est_pas_relu():
    """Au-dela du TTL, l'entree ne doit plus decider de rien (l'appel reseau prend le
    relais — ici il echoue faute de vrais identifiants, et rend None sans lever)."""
    _cache(("Elden Ring", "1", time.time() - G.HELIX_CACHE_TTL - 1, True))
    assert _jeu(True) == (None, None)


@pytest.fixture(autouse=True)
def _cache_propre():
    yield
    G.HELIX_CACHE.clear()
