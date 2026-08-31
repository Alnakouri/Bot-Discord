# -*- coding: utf-8 -*-
"""`tools/preparer_env.py` manipule les CLES : une erreur ici ne se voit pas, elle se
paie plus tard par un bot muet ou une cle perdue.

Tous les tests tournent sur un faux depot en tmp_path : la suite ne lit ni n'ecrit
jamais un vrai .env.
"""
import os
import sys
import pytest
from pathlib import Path

_racine = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_racine))
sys.path.insert(0, str(_racine / "tools"))

Fernet = pytest.importorskip("cryptography.fernet").Fernet
import preparer_env
from shared.secure_env import load_secure_env


CLES = {
    "DISCORD_TOKEN": "jeton-discord",
    "GEMINI_KEY_1": "cle-gemini-partagee",
    "GROQ_API_KEY": "cle-groq",
    "MISTRAL_API_KEY": "cle-mistral",
    "OPENROUTER_API_KEY": "cle-openrouter",
    "HF_TOKEN": "jeton-mort",
}


@pytest.fixture
def faux_depot(tmp_path, monkeypatch):
    """Deux bots chiffres : Sheogorath (4 emplacements Gemini, un jeton mort) et
    MalenaBot (un SEUL emplacement), qui partagent la meme cle Gemini."""
    for bot, nb_emplacements in (("Sheogorath", 4), ("MalenaBot", 1)):
        d = tmp_path / bot
        d.mkdir()
        cle = Fernet.generate_key()
        (d / ".master_key").write_bytes(cle)
        contenu = "\n".join(f"{n}={v}" for n, v in CLES.items()
                            if n != "HF_TOKEN" or bot == "Sheogorath")
        (d / ".env.encrypted").write_bytes(Fernet(cle).encrypt(contenu.encode()))
        # La source du bot : c'est elle qui dit combien d'emplacements il LIT.
        (d / f"bot_{bot.lower()}.py").write_text(
            "\n".join(f'os.getenv("GEMINI_KEY_{i}")' for i in range(1, nb_emplacements + 1)),
            encoding="utf-8")

    monkeypatch.setattr(preparer_env, "RACINE", tmp_path)
    monkeypatch.setattr(preparer_env, "BOTS", ["Sheogorath", "MalenaBot"])
    return tmp_path


def _variables_du_fichier(chemin):
    return dict(preparer_env.variables(chemin.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Le piege qui corromprait une cle en silence
# ---------------------------------------------------------------------------

def test_aucun_commentaire_ne_suit_jamais_une_valeur(faux_depot):
    """`shared/secure_env.py` fait `nom, valeur = ligne.split("=", 1)` et ne retire
    AUCUN commentaire. Un marqueur «  # partagee » ecrit en fin de ligne finirait donc
    DANS la cle : le bot enverrait une cle invalide et rendrait 401 sans que rien
    n'explique pourquoi. Les marqueurs vont sur la ligne du dessus, toujours."""
    preparer_env.ouvrir()
    for bot in ("Sheogorath", "MalenaBot"):
        for ligne in (faux_depot / bot / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.strip().startswith("#"):
                _, valeur = ligne.split("=", 1)
                assert "#" not in valeur, f"{bot} : commentaire avale dans une valeur"


def test_les_valeurs_traversent_l_ouverture_sans_changer(faux_depot, monkeypatch):
    """Le test de bout en bout : ce que le VRAI lecteur du depot relit dans le fichier
    prepare doit etre exactement ce qui etait dans le chiffre."""
    preparer_env.ouvrir()
    for nom in CLES:
        monkeypatch.delenv(nom, raising=False)
    assert load_secure_env(faux_depot / "Sheogorath") is True
    for nom, valeur in CLES.items():
        if nom == "HF_TOKEN":
            continue
        assert os.environ[nom] == valeur, f"{nom} a ete abime a l'ouverture"


# ---------------------------------------------------------------------------
# Ce que --ouvrir prepare
# ---------------------------------------------------------------------------

def test_le_jeton_mort_est_retire_et_la_raison_est_ecrite(faux_depot):
    preparer_env.ouvrir()
    contenu = (faux_depot / "Sheogorath" / ".env").read_text(encoding="utf-8")
    assert "HF_TOKEN=" not in contenu, "le jeton mort est encore actif"
    assert "HF_TOKEN" in contenu, "retire sans dire pourquoi : ca reviendra"


def test_le_chiffre_d_origine_n_est_pas_touche_par_l_ouverture(faux_depot):
    """--ouvrir ne doit RIEN ecrire de destructif : tant que --sceller n'a pas relu et
    compare, le .env.encrypted d'origine reste le seul exemplaire sur : c'est le filet
    si la saisie tourne mal."""
    avant = (faux_depot / "Sheogorath" / ".env.encrypted").read_bytes()
    preparer_env.ouvrir()
    assert (faux_depot / "Sheogorath" / ".env.encrypted").read_bytes() == avant


def test_on_ne_propose_que_les_emplacements_que_le_bot_lit(faux_depot):
    """MalenaBot ne lit qu'UNE cle Gemini. Lui proposer un GEMINI_KEY_2 ferait saisir
    une cle qui ne servirait jamais — et donnerait l'illusion d'une rotation."""
    preparer_env.ouvrir()
    malena = _variables_du_fichier(faux_depot / "MalenaBot" / ".env")
    sheo = _variables_du_fichier(faux_depot / "Sheogorath" / ".env")
    assert "GEMINI_KEY_2" not in malena
    assert ["GEMINI_KEY_2", "GEMINI_KEY_3", "GEMINI_KEY_4"] == [
        n for n in sheo if n.startswith("GEMINI_KEY_") and n != "GEMINI_KEY_1"]
    assert all(v == "" for n, v in sheo.items() if n in ("GEMINI_KEY_2", "GEMINI_KEY_3"))


def test_la_cle_partagee_est_signalee_chez_LES_DEUX_bots(faux_depot):
    """Sur les deux, pas sur un seul : c'est l'utilisateur qui choisit lequel garde
    l'ancienne cle."""
    preparer_env.ouvrir()
    for bot in ("Sheogorath", "MalenaBot"):
        assert "PARTAGEE" in (faux_depot / bot / ".env").read_text(encoding="utf-8")


def test_une_variable_identique_par_construction_n_est_pas_un_partage(faux_depot):
    """La liste des salons Twitch est la MEME chez plusieurs bots, c'est voulu. La
    signaler ferait crier l'outil tous les jours, et une alerte permanente n'alerte
    plus personne."""
    assert "TWITCH_CHAT_CHANNELS" in preparer_env.NON_SECRETES
    for bot in ("Sheogorath", "MalenaBot"):
        d = faux_depot / bot
        cle = (d / ".master_key").read_bytes()
        texte = Fernet(cle).decrypt((d / ".env.encrypted").read_bytes()).decode()
        (d / ".env.encrypted").write_bytes(
            Fernet(cle).encrypt((texte + "\nTWITCH_CHAT_CHANNELS=zaji").encode()))
    assert not [b for (n, b) in preparer_env.partagees() if n == "TWITCH_CHAT_CHANNELS"]


# ---------------------------------------------------------------------------
# --sceller : refermer sans jamais perdre une cle
# ---------------------------------------------------------------------------

def test_sceller_sauvegarde_rechiffre_et_efface_le_clair(faux_depot):
    preparer_env.ouvrir()
    chemin = faux_depot / "Sheogorath" / ".env"
    chemin.write_text(chemin.read_text(encoding="utf-8").replace(
        "GEMINI_KEY_2=", "GEMINI_KEY_2=cle-neuve"), encoding="utf-8")

    preparer_env.sceller()

    assert not chemin.exists(), "le clair traine encore sur le disque"
    assert list((faux_depot / "Sheogorath").glob(".env.encrypted.bak_*")), \
        "rechiffre sans sauvegarde de l'ancien"
    cle = (faux_depot / "Sheogorath" / ".master_key").read_bytes()
    relu = Fernet(cle).decrypt(
        (faux_depot / "Sheogorath" / ".env.encrypted").read_bytes()).decode("utf-8")
    assert "GEMINI_KEY_2=cle-neuve" in relu


def test_le_clair_survit_si_la_relecture_ne_correspond_pas(faux_depot, monkeypatch):
    """Le pire scenario possible : effacer le clair apres avoir ecrit un chiffre
    illisible. Les cles seraient perdues pour de bon. La relecture doit garder le clair
    en place au moindre ecart."""
    preparer_env.ouvrir()

    class _ChiffreMenteur:
        def encrypt(self, _donnees):
            return b"charabia"

        def decrypt(self, _donnees):
            return b"pas ce qui a ete ecrit"

    monkeypatch.setattr(preparer_env, "fernet_du_bot", lambda _d: _ChiffreMenteur())
    preparer_env.sceller()
    assert (faux_depot / "Sheogorath" / ".env").exists(), \
        "le clair a ete efface alors que le chiffre est illisible"


def test_sceller_ne_touche_pas_un_bot_sans_env_en_clair(faux_depot):
    """--sceller passe sur les 6 bots. Celui qu'on n'a pas ouvert ne doit pas etre
    rechiffre au passage : ce serait une sauvegarde de plus et un fichier remue pour
    rien."""
    preparer_env.ouvrir()
    (faux_depot / "MalenaBot" / ".env").unlink()
    avant = (faux_depot / "MalenaBot" / ".env.encrypted").read_bytes()
    preparer_env.sceller()
    assert (faux_depot / "MalenaBot" / ".env.encrypted").read_bytes() == avant


# ---------------------------------------------------------------------------
# Aucune valeur ne doit sortir de l'outil
# ---------------------------------------------------------------------------

def test_l_outil_n_imprime_jamais_une_valeur(faux_depot, capsys):
    preparer_env.ouvrir()
    preparer_env.etat()
    sortie = capsys.readouterr().out
    for valeur in CLES.values():
        assert valeur not in sortie, "une valeur de cle est passee dans la sortie"
