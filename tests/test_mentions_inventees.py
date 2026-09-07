# -*- coding: utf-8 -*-
"""Une mention que le modèle a fabriquée ne doit pas atteindre Discord.

Mesuré en test live le 2026-09-07, `!rumeur` de M'aiq :

    📢 [RUMEUR] M'aiq a entendu dire que <@123456789> collectionne les cuillères...

Le prompt demandait une rumeur « sur un joueur » sans jamais fournir d'identifiant :
le modèle en a fabriqué un, et Discord a affiché le `<@123456789>` brut.

⚠️ Ce que ce fichier garde surtout, c'est la RÈGLE du filet : elle est **structurelle**,
jamais une question de cache. Une mention valide ne peut pas être touchée — sinon le
filet deviendrait plus dangereux que le défaut, et on ne pourrait pas l'installer sur
les six bots.
"""
import ast
import asyncio
from pathlib import Path

import pytest

from shared import mentions

RACINE = Path(__file__).resolve().parent.parent
BOTS = {
    "Alfred/bot_alfred.py": "alfred",
    "JohnnyBot/bot_johnny.py": "johnny",
    "MaiqBot/bot_maiq.py": "maiq",
    "MalenaBot/bot_malena.py": "malena",
    "Sheogorath/bot_sheogorath.py": "sheogorath",
    "SugarBot/bot_sugar.py": "sugar",
}

# Des identifiants Discord reels (longueur et epoque plausibles).
VRAI = "297045071457681409"
VRAI_BIS = "123123123123123123"      # le serveur prive du mode test


# --------------------------------------------------------------------------------------
# La regle : ce qui est un flocon, et ce qui n'en est pas un
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("identifiant", [VRAI, VRAI_BIS, "80351110224678912"])
def test_un_vrai_identifiant_est_reconnu(identifiant):
    assert mentions.identifiant_plausible(identifiant) is True


@pytest.mark.parametrize("identifiant, pourquoi", [
    ("123456789", "9 chiffres : trop court pour un flocon"),
    ("1234567890123456", "16 chiffres, un de moins que le minimum"),
    ("0", "l'identifiant nul"),
    ("00000000000000001", "17 chiffres mais anterieur a l'epoque Discord"),
    ("999999999999999999999", "21 chiffres : au-dela de 64 bits utiles"),
])
def test_une_invention_est_reconnue(identifiant, pourquoi):
    assert mentions.identifiant_plausible(identifiant) is False, pourquoi


def test_un_identifiant_du_futur_est_refuse():
    """Un flocon dont la date depasse aujourd'hui n'a pas pu etre emis."""
    lointain = str(((2 ** 41) - 1) << 22)
    assert mentions.identifiant_plausible(lointain) is False


# --------------------------------------------------------------------------------------
# Le nettoyage du texte
# --------------------------------------------------------------------------------------

def test_la_mention_inventee_du_2026_09_07_est_neutralisee():
    texte = "M'aiq a entendu dire que <@123456789> collectionne les cuillères."
    nettoye, compte = mentions.neutraliser_mentions_inventees(texte)
    assert "<@123456789>" not in nettoye
    assert compte == 1
    assert nettoye.startswith("M'aiq a entendu dire que quelqu'un collectionne")


def test_une_vraie_mention_traverse_intacte():
    """⚠️ La garde la plus importante : un decret nomme sa cible avec un VRAI id."""
    texte = f"MORTEL ! <@{VRAI}> est nomme Grand Fromager des Abysses !"
    nettoye, compte = mentions.neutraliser_mentions_inventees(texte)
    assert nettoye == texte
    assert compte == 0


def test_la_forme_heritee_avec_point_d_exclamation_est_couverte():
    nettoye, compte = mentions.neutraliser_mentions_inventees("salut <@!42> ca va")
    assert compte == 1 and "42" not in nettoye


def test_les_roles_et_les_salons_ne_sont_pas_touches():
    """Effacer un role serait une regression plus visible que le defaut lui-meme."""
    texte = "<@&123456789> dans <#123456789>"
    assert mentions.neutraliser_mentions_inventees(texte) == (texte, 0)


def test_un_melange_ne_garde_que_ce_qui_est_valide():
    texte = f"<@{VRAI}> et <@123456789> et <@{VRAI_BIS}>"
    nettoye, compte = mentions.neutraliser_mentions_inventees(texte)
    assert compte == 1
    assert f"<@{VRAI}>" in nettoye and f"<@{VRAI_BIS}>" in nettoye


@pytest.mark.parametrize("entree", [None, 42, "", "aucune mention ici"])
def test_ce_qui_n_est_pas_du_texte_a_mentions_ressort_tel_quel(entree):
    """Le filet est un patch d'envoi : il voit passer toutes les formes."""
    assert mentions.neutraliser_mentions_inventees(entree) == (entree, 0)


# --------------------------------------------------------------------------------------
# Le patch d'envoi
# --------------------------------------------------------------------------------------

class _FauxCanal:
    """Assez de discord.py pour le patch : il enregistre ce qui est REELLEMENT envoye."""

    def __init__(self):
        self.recu = []


@pytest.fixture
def envois(monkeypatch):
    """Installe le filet sur une doublure, et rend la liste de ce qui passe."""
    import discord

    recu = []

    async def _origine(self, *args, **kwargs):
        recu.append((args, kwargs))
        return "envoye"

    monkeypatch.setattr(discord.abc.Messageable, "send", _origine, raising=False)
    monkeypatch.setattr(discord.InteractionResponse, "send_message", _origine, raising=False)
    monkeypatch.setattr(discord.Webhook, "send", _origine, raising=False)
    monkeypatch.setattr(mentions, "_DEJA_INSTALLE", False)
    assert mentions.installer_filtre_mentions("test") is True
    yield recu


def test_le_patch_nettoie_le_contenu_positionnel(envois):
    import discord

    asyncio.run(discord.abc.Messageable.send(
        _FauxCanal(), "rumeur sur <@123456789> !"))
    (args, _kwargs), = envois
    assert args[0] == "rumeur sur quelqu'un !"


def test_le_patch_nettoie_le_contenu_nomme(envois):
    import discord

    asyncio.run(discord.abc.Messageable.send(
        _FauxCanal(), content="rumeur sur <@123456789> !"))
    (_args, kwargs), = envois
    assert kwargs["content"] == "rumeur sur quelqu'un !"


def test_le_patch_laisse_passer_le_reste_des_arguments(envois):
    """Un embed, un fichier, `ephemeral=` : rien ne doit se perdre en route."""
    import discord

    asyncio.run(discord.abc.Messageable.send(
        _FauxCanal(), "salut", embed="EMBED", ephemeral=True))
    (args, kwargs), = envois
    assert args == ("salut",)
    assert kwargs == {"embed": "EMBED", "ephemeral": True}


def test_les_trois_chemins_de_sortie_sont_couverts(envois):
    """`Messageable.send` couvre reply/salon/MP ; les slash commands ont les 2 autres."""
    import discord

    for cible in (discord.abc.Messageable.send,
                  discord.InteractionResponse.send_message,
                  discord.Webhook.send):
        asyncio.run(cible(_FauxCanal(), "<@123456789>"))
    assert [a[0] for a, _ in envois] == ["quelqu'un"] * 3


def test_l_installation_est_idempotente(envois):
    """Deux installations empileraient deux patches sur le meme point de passage."""
    assert mentions.installer_filtre_mentions("test") is False


# --------------------------------------------------------------------------------------
# Le cablage : les SIX bots
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("chemin, bot_id", sorted(BOTS.items()))
def test_les_6_bots_installent_le_filet(chemin, bot_id):
    """⚠️ « fait sur les 6 » l'est presque toujours sur 5 : on compte les six.

    Et on exige l'APPEL avec son identifiant, pas seulement l'import : un import seul
    n'installe rien, et le test serait vert sur un bot qui publie encore des mentions
    inventees.
    """
    source = (RACINE / chemin).read_text(encoding="utf-8")
    arbre = ast.parse(source, filename=chemin)
    appels = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "installer_filtre_mentions"
        and n.args and isinstance(n.args[0], ast.Constant)
        and n.args[0].value == bot_id
    ]
    assert appels, f"{chemin} n'installe pas le filet pour « {bot_id} »"


@pytest.mark.parametrize("chemin", sorted(BOTS))
def test_l_import_du_filet_reste_optionnel(chemin):
    """`shared/` est optionnel : un bot deploye seul doit demarrer sans lui."""
    source = (RACINE / chemin).read_text(encoding="utf-8")
    arbre = ast.parse(source, filename=chemin)
    for noeud in ast.walk(arbre):
        if (isinstance(noeud, ast.ImportFrom)
                and noeud.module == "shared.mentions"):
            parents = [p for p in ast.walk(arbre)
                       if isinstance(p, ast.Try)
                       and any(noeud is x for x in ast.walk(p))]
            assert parents, f"{chemin} importe shared.mentions hors d'un try/except"
            return
    pytest.fail(f"{chemin} n'importe jamais shared.mentions")


def test_le_prompt_de_rumeur_ne_demande_plus_de_mention():
    """Le prompt seul ne suffit pas, mais demander une invention est un defaut a part."""
    source = (RACINE / "MaiqBot" / "bot_maiq.py").read_text(encoding="utf-8")
    debut = source.index('async def maiq_rumeur')
    corps = source[debut:debut + 1500]
    # Le PROMPT seul : un commentaire a le droit de citer l'ancienne formulation.
    prompt = next(l for l in corps.splitlines() if l.strip().startswith("prompt = "))
    assert "sur un joueur" not in prompt, (
        "Le prompt demande encore une rumeur « sur un joueur » sans fournir "
        "d'identifiant : c'est exactement ce qui a fait inventer <@123456789>."
    )
    assert "<@...>" in prompt, "la consigne qui interdit la mention a disparu"
