# -*- coding: utf-8 -*-
"""La sonde des clés doit être inoffensive, et ne jamais montrer une clé.

Elle lit les `.env` déchiffrés des 6 bots et interroge les fournisseurs : c'est
l'outil du dépôt qui manipule le plus de secrets. Les tests ci-dessous ne touchent
à aucune vraie clé et ne font aucun appel réseau — ils vérifient les invariants de
construction, seuls testables en CI (les clés ne sont pas dans le dépôt).
"""
import os
import sys

import pytest

_racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _racine not in sys.path:
    sys.path.insert(0, _racine)
sys.path.insert(0, os.path.join(_racine, "tools"))

import sonde_cles_partagees as sonde


FAUSSES_VALEURS = {
    "DISCORD_TOKEN": "faux-discord",
    "GEMINI_KEY_1": "faux-gemini",
    "MISTRAL_API_KEY": "faux-mistral",
    "GROQ_API_KEY": "faux-groq",
    "OPENROUTER_API_KEY": "faux-openrouter",
    "ELEVENLABS_API_KEY": "faux-eleven",
    "HF_TOKEN": "faux-hf",
    "TWITCH_CLIENT_ID": "faux-id",
    "TWITCH_CLIENT_SECRET": "faux-secret",
    "TWITCH_OAUTH_TOKEN": "faux-oauth",
    "TWITCH_REFRESH_TOKEN": "faux-refresh-NE-PAS-CONSOMMER",
}


def test_aucune_sonde_ne_consomme_le_refresh_token_twitch():
    """Twitch fait TOURNER le refresh token à l'usage : le tester le consommerait, et
    la valeur du `.env` deviendrait périmée. La sonde casserait alors exactement ce
    qu'elle est censée vérifier — et on ne peut pas réécrire un `.env`, `AGENTS.md`
    l'interdit."""
    for nom, url, entetes, corps in sonde._sondes(FAUSSES_VALEURS):
        assemble = url + repr(entetes) + repr(corps)
        assert "faux-refresh" not in assemble, \
            f"la sonde {nom} envoie le refresh token Twitch"


def test_toutes_les_sondes_sont_en_lecture_seule():
    """Aucun appel ne doit générer de texte ni écrire quoi que ce soit : la sonde peut
    être lancée en boucle sans coûter un centime ni modifier un compte."""
    interdits = ("chat/completions", "generateContent", "/messages", "/completions")
    for nom, url, _, _ in sonde._sondes(FAUSSES_VALEURS):
        assert not any(m in url for m in interdits), \
            f"la sonde {nom} appelle un point d'entrée de génération : {url}"


def test_chaque_cle_ne_part_que_chez_son_fournisseur():
    """Un copier-coller malheureux enverrait la clé Mistral à Groq. Les fournisseurs
    journalisent les clés reçues : une clé envoyée au mauvais est une clé à révoquer."""
    hote_attendu = {
        "DISCORD_TOKEN": "discord.com",
        "GEMINI_KEY_1": "generativelanguage.googleapis.com",
        "MISTRAL_API_KEY": "api.mistral.ai",
        "GROQ_API_KEY": "api.groq.com",
        "OPENROUTER_API_KEY": "openrouter.ai",
        "ELEVENLABS_API_KEY": "api.elevenlabs.io",
        "HF_TOKEN": "huggingface.co",
        "TWITCH_CLIENT_*": "id.twitch.tv",
    }
    for nom, url, entetes, corps in sonde._sondes(FAUSSES_VALEURS):
        assert hote_attendu[nom] in url, f"{nom} part vers {url}"
        valeur = FAUSSES_VALEURS.get(nom)
        if valeur:
            assemble = url + repr(entetes) + repr(corps)
            assert valeur in assemble, f"{nom} : la sonde n'envoie pas la clé testée"


def test_la_sonde_gemini_est_la_seule_a_mettre_la_cle_dans_l_url():
    """Une clé dans une URL finit dans les journaux d'accès et l'historique du shell.
    Google n'accepte que ça sur cet endpoint ; partout ailleurs, un en-tête."""
    for nom, url, _, _ in sonde._sondes(FAUSSES_VALEURS):
        if nom.startswith("GEMINI"):
            continue
        for valeur in FAUSSES_VALEURS.values():
            assert valeur not in url, f"{nom} met une clé dans l'URL"


def test_un_bot_sans_twitch_ne_declenche_aucun_appel():
    etat, detail = sonde.token_twitch_vivant("MalenaBot")
    assert etat == "absent"
    assert "ne va pas sur Twitch" in detail


def test_un_401_remonte_le_message_du_fournisseur():
    """Sans le corps de la réponse, « MORT 401 » ne dit pas si la clé est révoquée,
    expirée, ou si c'est le quota — trois correctifs différents."""
    detail = sonde._detail("HF_TOKEN", 401, b'{"error":"Invalid username or password."}')
    assert "Invalid username" in detail


def test_le_detail_ne_plante_pas_sur_une_reponse_non_json():
    """Cloudflare répond « error code: 1010 » en texte brut devant Groq."""
    assert "1010" in sonde._detail("GROQ_API_KEY", 403, b"error code: 1010\n")


@pytest.mark.parametrize("bot,attendu", [
    ("JohnnyBot", "johnny"), ("Sheogorath", "sheogorath"), ("SugarBot", "sugar")])
def test_le_fichier_de_token_vise_est_celui_que_le_bot_utilise(bot, attendu):
    """Le token réellement utilisé vit dans `data/twitch_chat_auth_<id>.json`, pas dans
    le `.env`. Se tromper d'identifiant ferait crier à la panne tous les jours."""
    assert sonde._ID_TWITCH[bot] == attendu
    src = open(os.path.join(_racine, "shared", "twitch", "auth.py"), encoding="utf-8").read()
    assert 'twitch_chat_auth_{bot_id}.json' in src, \
        "le nom du fichier de tokens a changé dans shared/twitch/auth.py"
