# -*- coding: utf-8 -*-
"""La sonde des clés doit être inoffensive, et ne jamais montrer une clé.

Elle lit les `.env` déchiffrés des 6 bots et interroge les fournisseurs : c'est
l'outil du dépôt qui manipule le plus de secrets. Les tests ci-dessous ne touchent
à aucune vraie clé et ne font aucun appel réseau — ils vérifient les invariants de
construction, seuls testables en CI (les clés ne sont pas dans le dépôt).
"""
import json
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


# ---------------------------------------------------------------------------
# Le secours Twitch : c'est le REFRESH token, pas le token d'acces
# ---------------------------------------------------------------------------
#
# La version precedente de la sonde annoncait « plus de secours si data/ est perdu »
# des que le token d'ACCES du `.env` rendait 401. Or il est fait pour expirer toutes
# les ~4 h : elle alarmait donc tous les jours pour un fonctionnement nominal, alors
# que le refresh token — le seul qui permette de repartir — etait intact.

def _pose_amorce(tmp_path, monkeypatch, refresh_data):
    """Fabrique un faux data/twitch_chat_auth_johnny.json et y pointe la sonde."""
    monkeypatch.setattr(sonde, "RACINE", tmp_path)
    if refresh_data is not None:
        d = tmp_path / "data"
        d.mkdir(exist_ok=True)
        (d / "twitch_chat_auth_johnny.json").write_text(
            '{"access_token": "peu-importe", "refresh_token": "%s"}' % refresh_data,
            encoding="utf-8")


def test_le_secours_est_intact_quand_les_deux_refresh_sont_identiques(tmp_path, monkeypatch):
    _pose_amorce(tmp_path, monkeypatch, "meme-refresh")
    etat, detail = sonde.amorce_env_reutilisable(
        "JohnnyBot", {"TWITCH_REFRESH_TOKEN": "meme-refresh"})
    assert etat == "ok", detail


def test_un_refresh_qui_a_tourne_est_signale(tmp_path, monkeypatch):
    """Twitch fait tourner le refresh a l'usage : quand data/ n'a plus le meme que le
    `.env`, l'amorce est bel et bien morte — c'est LA le vrai avertissement."""
    _pose_amorce(tmp_path, monkeypatch, "refresh-neuf")
    etat, detail = sonde.amorce_env_reutilisable(
        "JohnnyBot", {"TWITCH_REFRESH_TOKEN": "refresh-vieux"})
    assert etat == "perimee"
    assert "recopier" in detail


def test_un_env_sans_refresh_est_signale(tmp_path, monkeypatch):
    _pose_amorce(tmp_path, monkeypatch, "refresh-neuf")
    etat, _ = sonde.amorce_env_reutilisable("JohnnyBot", {"TWITCH_OAUTH_TOKEN": "x"})
    assert etat == "absente"


def test_le_secours_ne_montre_jamais_le_refresh_token(tmp_path, monkeypatch):
    """Meme regle que pour les cles : une empreinte, jamais la valeur."""
    _pose_amorce(tmp_path, monkeypatch, "SECRET-DATA")
    for env in ("SECRET-DATA", "SECRET-ENV"):
        _, detail = sonde.amorce_env_reutilisable(
            "JohnnyBot", {"TWITCH_REFRESH_TOKEN": env})
        assert "SECRET-DATA" not in detail and "SECRET-ENV" not in detail, detail


def test_un_bot_sans_twitch_n_a_pas_d_amorce_a_verifier(tmp_path, monkeypatch):
    _pose_amorce(tmp_path, monkeypatch, None)
    etat, _ = sonde.amorce_env_reutilisable(
        "MalenaBot", {"TWITCH_REFRESH_TOKEN": "x"})
    assert etat == "sans objet"


def test_la_vitalite_ne_teste_plus_le_token_d_acces_du_env():
    """Garde anti-retour : re-tester TWITCH_OAUTH_TOKEN, c'est reintroduire
    l'alarme quotidienne pour un token dont l'expiration est le fonctionnement
    normal."""
    src = open(os.path.join(_racine, "tools", "sonde_cles_partagees.py"),
               encoding="utf-8").read()
    debut = src.index("def vitalite(")
    fin = src.index("def main(", debut)
    assert "_valider_twitch(valeurs" not in src[debut:fin], (
        "vitalite() valide en ligne le token d acces du .env : alarme quotidienne")


# ---------------------------------------------------------------------------
# Un token d'acces expire n'est pas une panne
# ---------------------------------------------------------------------------
#
# Mesure du 2026-09-01 : les trois fichiers de data/ rendaient 401 uniquement parce
# que Docker Desktop etait eteint depuis la nuit. La sonde annoncait « 3 cles ne
# repondent plus » et sortait 1 en --strict, pour un etat parfaitement normal.

def _pose_data(tmp_path, monkeypatch, contenu):
    monkeypatch.setattr(sonde, "RACINE", tmp_path)
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / "twitch_chat_auth_johnny.json").write_text(contenu, encoding="utf-8")
    monkeypatch.setattr(sonde, "_valider_twitch", lambda jeton: (401, b"", 1))


def test_un_token_expire_avec_refresh_n_est_pas_une_panne(tmp_path, monkeypatch):
    """Il dure ~4 h et get_valid_token() le rafraichit au demarrage suivant."""
    import time
    _pose_data(tmp_path, monkeypatch, json.dumps({
        "access_token": "vieux", "refresh_token": "r",
        "expires_at": time.time() - 20000}))
    etat, detail = sonde.token_twitch_vivant("JohnnyBot")
    assert etat == "perime", detail
    assert "rafraichi" in detail


def test_un_401_avant_l_echeance_est_une_vraie_panne(tmp_path, monkeypatch):
    """Refuse alors qu'il devrait etre valide : le token a ete revoque cote Twitch."""
    import time
    _pose_data(tmp_path, monkeypatch, json.dumps({
        "access_token": "vivant", "refresh_token": "r",
        "expires_at": time.time() + 3600}))
    etat, detail = sonde.token_twitch_vivant("JohnnyBot")
    assert etat == "mort", detail
    assert "revoque" in detail


def test_un_token_expire_sans_refresh_est_une_vraie_panne(tmp_path, monkeypatch):
    """Rien ne le rattrapera tout seul : il faut rejouer twitch_authorize.py."""
    import time
    _pose_data(tmp_path, monkeypatch, json.dumps({
        "access_token": "vieux", "expires_at": time.time() - 20000}))
    etat, detail = sonde.token_twitch_vivant("JohnnyBot")
    assert etat == "mort", detail
    assert "twitch_authorize" in detail


def test_cles_twitch_sont_surveillees():
    for nom in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "TWITCH_OAUTH_TOKEN", "TWITCH_REFRESH_TOKEN"):
        assert nom in sonde.CLES_SURVEILLEES, f"{nom} absent de CLES_SURVEILLEES"



# ---------------------------------------------------------------------------
# SUITE 18 : deux bots sur le MEME compte Twitch. Leurs tokens different (ils tournent a
# chaque rafraichissement) : seule l'identite rendue par /oauth2/validate le trahit.
# ---------------------------------------------------------------------------

def test_deux_bots_sur_le_meme_compte_twitch_sont_signales():
    comptes = {"JohnnyBot": {"user_id": "111", "login": "a", "client_id": "app1"},
               "SugarBot": {"user_id": "111", "login": "a", "client_id": "app2"},
               "Sheogorath": {"user_id": "222", "login": "b", "client_id": "app3"}}
    partages = sonde.comptes_twitch_partages(comptes)
    assert len(partages) == 1
    quoi, bots = partages[0]
    assert quoi.startswith("compte Twitch ") and bots == ["JohnnyBot", "SugarBot"]
    assert "111" not in quoi, "l'identifiant brut ne doit pas s'afficher, seulement son empreinte"


def test_la_meme_application_twitch_est_signalee():
    comptes = {"JohnnyBot": {"user_id": "1", "client_id": "app"},
               "SugarBot": {"user_id": "2", "client_id": "app"}}
    partages = sonde.comptes_twitch_partages(comptes)
    assert [q.split(" ")[0] + " " + q.split(" ")[1] for q, _ in partages] == ["application Twitch"]


def test_des_comptes_distincts_ne_crient_pas():
    comptes = {"JohnnyBot": {"user_id": "1", "client_id": "a"},
               "SugarBot": {"user_id": "2", "client_id": "b"},
               "Sheogorath": {"user_id": None, "client_id": None}}
    assert sonde.comptes_twitch_partages(comptes) == []


def test_un_token_valide_enregistre_l_identite_du_compte(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(sonde, "RACINE", tmp_path)
    monkeypatch.setattr(sonde, "_COMPTES_TWITCH", {})
    d = tmp_path / "data"
    d.mkdir()
    (d / "twitch_chat_auth_sugar.json").write_text(json.dumps({
        "access_token": "vivant", "refresh_token": "r", "expires_at": time.time() + 3600}),
        encoding="utf-8")
    reponse = json.dumps({"login": "compte_bot_sugar", "user_id": "42", "client_id": "app",
                          "expires_in": 3000}).encode()
    monkeypatch.setattr(sonde, "_valider_twitch", lambda jeton: (200, reponse, 1))
    etat, _ = sonde.token_twitch_vivant("SugarBot")
    assert etat == "ok"
    assert sonde._COMPTES_TWITCH["SugarBot"] == {"user_id": "42", "login": "compte_bot_sugar",
                                                 "client_id": "app"}
