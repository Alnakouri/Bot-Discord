# -*- coding: utf-8 -*-
"""Verrou : le bot écrit la PHRASE, le code écrit le LIEN.

Le champ « Message (optionnel) » du dashboard, laissé vide, fait désormais écrire au bot
sa propre invitation, en personnage. Une seule chose ne doit jamais dépendre du modèle :
l'adresse. Un lien « presque bon » est pire qu'une phrase fade — personne ne vérifie une
URL avant de cliquer, et un LLM tronque, francise ou invente sans prévenir.

Ces tests n'appellent aucun modèle : `generate_response` est remplacée par une fonction
qui rend ce qu'on veut éprouver.
"""
import asyncio
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from shared.twitch.dispatch import DispatchMixin, _nettoyer_phrase_de_lien

URL = "https://discord.gg/exemple"


class _Journal:
    def __init__(self):
        self.lignes = []

    def info(self, msg):
        self.lignes.append(msg)

    warning = error = info


class _BotFactice(DispatchMixin):
    """Le strict nécessaire pour emprunter le vrai chemin de `_generate_link_line`."""
    bot_id = "sugar"
    bot_label = "Sugar"
    personality_prompt = "tu es Sugar"
    system_prompt_provider = None
    key_manager = object()          # non-None : sinon la méthode renonce avant d'appeler
    mistral_client = groq_client = nvidia_client = None

    def __init__(self):
        self.logger = _Journal()


def _avec_reponse(texte, compteur=None):
    """Remplace la cascade par une réponse fixe. Rend le bot prêt à être interrogé."""
    import shared.llm_cascade as cascade

    async def _faux(**kwargs):
        if compteur is not None:
            compteur["n"] += 1
        return texte

    cascade.generate_response = _faux
    return _BotFactice()


def test_la_phrase_vient_du_bot_et_le_lien_du_code():
    bot = _avec_reponse("Viens sucrer tes lèvres par ici, mon caramel")
    rendu = asyncio.run(bot._generate_link_line("discord", "discord", URL))
    assert rendu == "Viens sucrer tes lèvres par ici, mon caramel " + URL


def test_une_phrase_contenant_un_lien_est_REJETEE_pas_reparee():
    """Découper l'URL laisserait « Rejoins-nous sur tout de suite ». Fade bat cassé."""
    for invente in (
        "Rejoins-nous sur https://discord.gg/FAUX tout de suite",
        "Le vrai sucre est sur discord.gg/autrechose, bouge",
        "Tape www.pas-le-bon-lien.fr et viens",
    ):
        bot = _avec_reponse(invente)
        assert asyncio.run(bot._generate_link_line("discord", "discord", URL)) is None, (
            f"phrase acceptée alors qu'elle contient une adresse : {invente!r}"
        )


def test_rien_d_exploitable_rend_None_et_laisse_le_gabarit_prendre_le_relais():
    for vide in ("", "  ", "*soupir*", None):
        bot = _avec_reponse(vide)
        assert asyncio.run(bot._generate_link_line("discord", "discord", URL)) is None


def test_l_URL_officielle_est_toujours_intacte():
    """Quoi que rende le modèle, l'adresse sort telle qu'elle est configurée."""
    for reponse in (
        "Viens !",
        "Le sucre t'attend ici :",
        '"Entre donc"',
        "Ramène-toi " + "très " * 80 + "vite",     # très long : la phrase est coupée, pas l'URL
    ):
        bot = _avec_reponse(reponse)
        rendu = asyncio.run(bot._generate_link_line("discord", "discord", URL))
        if rendu is not None:
            assert rendu.endswith(URL), f"URL abîmée dans {rendu!r}"
            assert rendu.count(URL) == 1


def test_le_cache_evite_de_bruler_un_appel_par_commande():
    """`!discord` peut être tapé dix fois d'affilée ; le quota, lui, n'est pas infini."""
    compteur = {"n": 0}
    bot = _avec_reponse("Viens donc", compteur)
    for _ in range(4):
        rendu = asyncio.run(bot._generate_link_line("discord", "discord", URL))
        assert rendu.endswith(URL)
    assert compteur["n"] == 1, f"{compteur['n']} appels LLM pour 4 commandes : le cache ne tient pas"


def test_sans_url_configuree_on_ne_tente_rien():
    bot = _avec_reponse("Viens donc")
    assert asyncio.run(bot._generate_link_line("discord", "discord", "")) is None


def test_le_nettoyeur_retire_didascalies_guillemets_et_ponctuation_d_annonce():
    assert _nettoyer_phrase_de_lien("*sourire en coin* Ramène-toi") == "Ramène-toi"
    assert _nettoyer_phrase_de_lien('"Le sucre t\'attend"') == "Le sucre t'attend"
    assert _nettoyer_phrase_de_lien("Tout se passe ici :") == "Tout se passe ici"


def test_le_message_rempli_reste_un_gabarit_fixe():
    """Qui a pris la peine d'écrire un message ne veut pas qu'on le remplace : le mode
    « le bot écrit » ne s'active que sur un champ VIDE."""
    import ast

    chemin = os.path.join(RACINE, "shared", "twitch_chat.py")
    with open(chemin, encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)

    noms = {
        n.targets[0].id
        for n in ast.walk(arbre)
        if isinstance(n, ast.Assign) and n.targets and isinstance(n.targets[0], ast.Name)
    }
    assert "message_auto" in noms, (
        "le drapeau qui distingue « message fourni » de « message vide » a disparu : "
        "un gabarit écrit à la main risque d'être remplacé par une phrase du modèle"
    )


def test_l_emoji_SURVIT_au_nettoyage():
    """Un emoji est ce qui rend l'invitation vivante ; rien ne doit le manger.

    Le chemin Twitch le protege deja (la troncature le recolle a la fin), mais c'est ce
    nettoyeur-ci qui passe en premier, et lui retire les didascalies : la regle
    `*...*` ne doit pas emporter l'emoji qui suit.
    """
    assert _nettoyer_phrase_de_lien("Rejoins la bande, ca pique 🔥🤘") == "Rejoins la bande, ca pique 🔥🤘"
    assert _nettoyer_phrase_de_lien("*sourit* Viens voir de plus pres 😏") == "Viens voir de plus pres 😏"


def test_l_instruction_demande_l_ENVIE_et_interdit_d_inventer():
    """Une accroche enthousiaste invente un chiffre ou un salon, et le chat y croit.

    Le modele ne sait rien de ce serveur : ni qui y est, ni ce qui s'y passe, ni combien
    ils sont. L'instruction doit donc demander l'ambiance ET fermer les faits — meme
    regle que l'annonce de live, ou « enjolive le TON, jamais les FAITS » est deja ecrit.
    """
    import inspect

    from shared.twitch.dispatch import DispatchMixin

    source = inspect.getsource(DispatchMixin._generate_link_line)
    for attendu in ("ENVIE", "n'invente ni chiffre", "emoji", "N'ÉCRIS PAS l'adresse"):
        assert attendu in source, f"l'instruction ne dit plus : {attendu}"
