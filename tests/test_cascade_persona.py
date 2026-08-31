# -*- coding: utf-8 -*-
"""Chaque bot doit avoir SA cascade de modèles, pas celle du voisin.

Avant le 2026-08-26, les 6 bots partageaient exactement la même cascade : même modèle
en tête pour tout le monde, donc la même « voix » de fond sous six personnalités
différentes. Le choix par persona vient d'une sonde réelle
(`tools/sonde_modeles_persona.py`), pas d'une intuition.
"""
import os
import re
from pathlib import Path
import sys

import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from shared.models import (
    CASCADES_PERSONA, bot_id_depuis_label, cascade_persona, OPENROUTER_ECARTE,
)
from shared.smart_router import get_model_cascade, RequestType

_parent_dir_path = Path(_parent_dir)

BOTS = ["alfred", "johnny", "maiq", "malena", "sheo", "sugar"]


def test_les_six_bots_ont_une_cascade():
    assert sorted(CASCADES_PERSONA) == sorted(BOTS)


@pytest.mark.parametrize("bot", BOTS)
def test_chaque_cascade_a_au_moins_deux_echelons(bot):
    """Un seul échelon = plus aucun repli quand le fournisseur throttle."""
    assert len(CASCADES_PERSONA[bot]) >= 2


@pytest.mark.parametrize("bot", BOTS)
def test_chaque_cascade_melange_les_fournisseurs(bot):
    """Les quotas sont par fournisseur : trois échelons chez le même ne protègent de rien."""
    fournisseurs = {f for f, _ in CASCADES_PERSONA[bot]}
    assert len(fournisseurs) >= 2, f"{bot} : cascade mono-fournisseur"


def test_les_bots_ne_partagent_pas_tous_la_meme_tete():
    """Le but même du chantier : des voix distinctes."""
    tetes = {bot: CASCADES_PERSONA[bot][0] for bot in BOTS}
    assert len(set(tetes.values())) >= 3, \
        f"trop de bots démarrent sur le même modèle : {tetes}"


@pytest.mark.parametrize("bot", BOTS)
def test_aucune_cascade_persona_ne_depend_du_free_tier_openrouter(bot):
    """Mesuré le 2026-08-26 : 12 échecs sur 12 (429 en rafale, 60-120 s de latence)."""
    modeles = [m for _, m in CASCADES_PERSONA[bot]]
    suffixe_gratuit = ":" + "free"  # assemble : test_model_ids scanne tous les .py
    assert not any(m.endswith(suffixe_gratuit) for m in modeles), \
        f"{bot} : depend d'un modele gratuit, mesure non fiable"


@pytest.mark.parametrize("label,attendu", [
    ("Alfred", "alfred"),
    ("Johnny", "johnny"),
    ("Johnny Silverhand", "johnny"),
    ("M'aiq", "maiq"),
    ("M'aiq le Menteur", "maiq"),
    ("Maiq", "maiq"),
    ("Malena", "malena"),
    ("Sheogorath", "sheo"),
    ("Sugar Bot", "sugar"),
])
def test_les_etiquettes_reellement_utilisees_sont_toutes_reconnues(label, attendu):
    """Les bots ne normalisent pas leur bot_label : « Johnny » et « Johnny Silverhand »
    coexistent, « M'aiq » s'écrit avec ou sans apostrophe. Une étiquette non reconnue
    ferait silencieusement retomber le bot sur la cascade générique."""
    assert bot_id_depuis_label(label) == attendu


@pytest.mark.parametrize("valeur", [None, "", "Zorglub", "un bot inconnu"])
def test_un_bot_inconnu_retombe_sur_la_cascade_generique(valeur):
    assert cascade_persona(valeur) is None
    assert get_model_cascade(RequestType.TEXT, valeur) == get_model_cascade(RequestType.TEXT)


@pytest.mark.parametrize("bot", BOTS)
@pytest.mark.parametrize("type_requete", [RequestType.TEXT, RequestType.REPARTEE])
def test_texte_et_repartie_utilisent_la_cascade_de_la_persona(bot, type_requete):
    assert get_model_cascade(type_requete, bot) == CASCADES_PERSONA[bot]


@pytest.mark.parametrize("bot", BOTS)
@pytest.mark.parametrize("type_requete", [RequestType.IMAGE, RequestType.AUDIO])
def test_la_vision_n_est_pas_personnalisee(bot, type_requete):
    """Pour l'image et l'audio c'est la CAPACITÉ du modèle qui commande, pas le ton :
    router Sheo vers un modèle sans vision le rendrait aveugle."""
    assert get_model_cascade(type_requete, bot) == get_model_cascade(type_requete)
    assert all(f == "gemini" for f, _ in get_model_cascade(type_requete, bot))


def test_le_raisonnement_n_est_pas_personnalise():
    assert get_model_cascade(RequestType.REASONING, "sheo") == \
           get_model_cascade(RequestType.REASONING)


def test_les_6_copies_vendorisees_portent_les_cascades():
    """Un bot déployé seul doit garder SA voix."""
    for dossier in ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]:
        src = open(os.path.join(_parent_dir, dossier, "core", "models.py"), encoding="utf-8").read()
        assert "CASCADES_PERSONA" in src, f"{dossier} : cascades absentes de la copie"
        src_router = open(os.path.join(_parent_dir, dossier, "core", "smart_router.py"),
                          encoding="utf-8").read()
        assert "def get_model_cascade(routing_type, bot_id=None)" in src_router, \
            f"{dossier} : signature du routeur pas à jour"


@pytest.mark.parametrize("fichier,attendu", [
    ("Alfred/bot_alfred.py", '"alfred"'),
    ("MaiqBot/bot_maiq.py", '"maiq"'),
    ("MalenaBot/bot_malena.py", '"malena"'),
    ("Sheogorath/bot_sheogorath.py", '"sheo"'),
])
def test_les_cascades_inline_passent_bien_leur_identifiant(fichier, attendu):
    """Ces 4 bots n'utilisent pas llm_cascade : sans l'identifiant en argument, ils
    retomberaient silencieusement sur la cascade générique — le bug serait invisible,
    le bot répondrait juste avec la mauvaise voix."""
    src = open(os.path.join(_parent_dir, fichier), encoding="utf-8").read()
    assert f"get_model_cascade(routing[\"type\"]" in src
    assert attendu in src.split("get_model_cascade(routing[\"type\"]")[1][:80], \
        f"{fichier} : get_model_cascade appelé sans {attendu}"


def test_llm_cascade_transmet_le_label_du_bot():
    """Johnny et Sugar passent par llm_cascade : c'est bot_label qui identifie la persona."""
    src = open(os.path.join(_parent_dir, "shared", "llm_cascade.py"), encoding="utf-8").read()
    assert 'get_model_cascade(routing["type"], bot_label)' in src


# ---------------------------------------------------------------------------
# Annonces de live : sortie PUBLIQUE, c'est la qualité de langue qui commande
# ---------------------------------------------------------------------------

from shared.models import CASCADE_ANNONCE, GROQ_QWEN


def test_l_annonce_a_sa_propre_cascade():
    """Une annonce n'est pas une réponse de chat : elle est lue par tout le monde."""
    assert len(CASCADE_ANNONCE) >= 2
    assert len({f for f, _ in CASCADE_ANNONCE}) >= 2, "cascade mono-fournisseur"
    suffixe_gratuit = ":" + "free"
    assert not any(m.endswith(suffixe_gratuit) for _, m in CASCADE_ANNONCE)


def test_l_annonce_n_utilise_pas_le_modele_au_francais_bancal():
    """Signalé en prod le 2026-08-26 : « son goat de Bohême », puis mesuré sur 4
    tirages — « KCD2, ça s'quille ! [...] derrière les foudres du fer ». qwen a le
    français le plus faible de la sélection ; il ne doit pas écrire les annonces."""
    assert CASCADE_ANNONCE[0][1] != GROQ_QWEN, \
        "qwen ne doit pas être en tête de la cascade des annonces"


def test_l_annonceur_utilise_cette_cascade_et_ne_tronque_plus():
    src = open(os.path.join(_parent_dir, "shared", "twitch_announcer.py"), encoding="utf-8").read()
    assert "from shared.models import CASCADE_ANNONCE" in src
    assert "cascade=CASCADE_ANNONCE" in src
    bloc = src.split("async def _generate_hype")[1]
    assert "max_tokens=120" not in bloc, \
        "120 tokens coupaient l'annonce en plein mot (mesuré sur mistral-large)"
    assert "max_tokens=200" in bloc


def test_une_cascade_forcee_prime_sur_celle_de_la_persona():
    """Sans quoi l'annonce repartirait sur le modèle du bot."""
    src = open(os.path.join(_parent_dir, "shared", "llm_cascade.py"), encoding="utf-8").read()
    assert "cascade: list | None = None" in src
    assert "cascade = list(cascade) if cascade else get_model_cascade(" in src


def test_les_6_copies_vendorisees_portent_la_cascade_d_annonce():
    for dossier in ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]:
        src = open(os.path.join(_parent_dir, dossier, "core", "models.py"), encoding="utf-8").read()
        assert "CASCADE_ANNONCE" in src, f"{dossier} : cascade d'annonce absente"
        src_c = open(os.path.join(_parent_dir, dossier, "core", "llm_cascade.py"), encoding="utf-8").read()
        assert "cascade: list | None = None" in src_c, f"{dossier} : surcharge absente"


@pytest.mark.parametrize("bot", BOTS)
def test_aucune_cascade_n_utilise_le_modele_au_francais_faible(bot):
    """Mesuré le 2026-08-26, 5 réponses par bot : « Tu ne me trompez pas »,
    « Rien de spiciale », « chewing-gue », « une serpipe » — environ une faute réelle
    sur deux réponses. Le modèle était le plus incisif et le plus bref ; la brièveté ne
    vaut pas ce prix. Le constant reste défini pour documenter le refus."""
    assert GROQ_QWEN not in [m for _, m in CASCADES_PERSONA[bot]],         f"{bot} : qwen a été remis dans la cascade"


# ---------------------------------------------------------------------------
# mistral-large : hors abonnement depuis le 2026-08-30
# ---------------------------------------------------------------------------

from shared.models import MISTRAL_HORS_TIER, MISTRAL_MAIN


@pytest.mark.parametrize("bot", BOTS)
def test_aucune_cascade_n_utilise_le_modele_hors_abonnement(bot):
    """Sonde du 2026-08-30 : 9 appels sur 3 personas, 9 refus identiques —
    403 « This model is not available in your subscription tier » (code 1910).
    Confirmé en base : 7 échecs sur 7, latence 134-283 ms, le temps d'un refus.

    Alfred le portait en TÊTE : il perdait un appel à chaque message. Sheo l'avait
    juste derrière Groq, donc il tombait dessus pile après un 429.

    ⚠️ `models.list()` le liste quand même (54 ids rendus, celui-ci inclus) : ne pas
    le remettre sur la foi du catalogue, seul un appel réel tranche.
    """
    assert MISTRAL_HORS_TIER not in [m for _, m in CASCADES_PERSONA[bot]], \
        f"{bot} : mistral-large a été remis dans la cascade (403 tier_not_allowed)"


def test_ni_l_annonce_ni_les_cascades_generiques_ne_l_utilisent():
    """La cascade d'annonce et les replis de smart_router le portaient aussi."""
    assert MISTRAL_HORS_TIER not in [m for _, m in CASCADE_ANNONCE]
    types_requete = [RequestType.TEXT, RequestType.REPARTEE, RequestType.IMAGE,
                     RequestType.AUDIO, RequestType.REASONING]
    for type_requete in types_requete:
        cascade = get_model_cascade(type_requete, None)
        assert MISTRAL_HORS_TIER not in [m for _, m in cascade], \
            f"{type_requete} : cascade générique sur un modèle hors abonnement"


def test_le_repli_sans_shared_ne_ressuscite_pas_le_modele_mort():
    """Les branches `except ImportError` recopient les ids en dur : sans ce test,
    un bot déployé seul repartirait sur mistral-large — la règle d'indépendance
    remettrait en marche exactement ce que ce correctif retire."""
    for module in ("smart_router", "media_handler"):
        src = open(os.path.join(_parent_dir, "shared", module + ".py"), encoding="utf-8").read()
        repli = src.split("except ImportError")[1].split("\ndef ")[0]
        assert MISTRAL_HORS_TIER not in repli, \
            f"shared/{module}.py : le repli sans shared/ ressuscite mistral-large"


def test_mistral_main_pointe_sur_un_modele_de_l_abonnement():
    assert MISTRAL_MAIN != MISTRAL_HORS_TIER


# ---------------------------------------------------------------------------
# La répartie est un critère d'admission, pas une impression
# ---------------------------------------------------------------------------

def test_les_criteres_d_admission_sont_ecrits_dans_la_source_de_verite():
    """Ajouté le 2026-08-30 : la répartie a été mesurée pour la première fois, et trois
    modèles « sans filtre » ont capitulé devant l'insulte — hermes-3 (2/5), hermes-4
    (« Désolé »), dolphin-venice. Rien ne mesurait ça avant, donc rien ne l'interdisait.

    Les critères vivent dans `shared/models.py`, à côté des cascades qu'ils gouvernent :
    dans un document séparé, ils seraient périmés en trois semaines."""
    src = open(os.path.join(_parent_dir, "shared", "models.py"), encoding="utf-8").read()
    assert "CRITERES D'ADMISSION" in src
    for critere in ("FRANCAIS", "REPARTIE", "FUITE", "VIDE", "LATENCE", "TIC"):
        assert critere in src, f"le critère {critere} n'est plus documenté"
    for sonde in ("sonde_modeles_persona.py", "sonde_repartie.py"):
        assert sonde in src, f"{sonde} n'est pas cité comme l'outil qui tranche"


def test_l_outil_qui_mesure_la_repartie_existe():
    chemin = os.path.join(_parent_dir, "tools", "sonde_repartie.py")
    assert os.path.exists(chemin), "tools/sonde_repartie.py manquant"
    src = open(chemin, encoding="utf-8").read()
    assert "CAPITULE" in src, "la sonde ne détecte plus la capitulation"
    assert "FUITE" in src, "la sonde ne détecte plus la fuite de raisonnement"
    # Les modèles EN PLACE doivent y figurer : un candidat ne vaut que comparé.
    for enplace in ("gpt-oss-120b", "mistral-small", "flash-lite"):
        assert enplace in src, f"{enplace} (en production) absent des candidats comparés"


def test_la_sonde_de_repartie_mesure_bien_la_capitulation():
    """Le test le plus important du lot : si les marqueurs ne détectent rien, la sonde
    rend « 0/5 » pour tout le monde et son classement ne veut plus rien dire."""
    sys.path.insert(0, os.path.join(_parent_dir, "tools"))
    import sonde_repartie

    couche = "Tu as raison, je ne sers pas à grand-chose."          # dolphin-venice, réel
    tient = "Ah, c'est mignon, le peteur qui croit que l'ignorance est un talent."
    assert any(m in couche.lower() for m in sonde_repartie.CAPITULE)
    assert not any(m in tient.lower() for m in sonde_repartie.CAPITULE)

    fuite = "Thinking Process: 1. **Analyze the Request:** * Role: Sugar Bot."  # qwen3.5, réel
    assert any(m in fuite.lower() for m in sonde_repartie.FUITE)
    assert not any(m in tient.lower() for m in sonde_repartie.FUITE)


# ---------------------------------------------------------------------------
# nemotron : ecarte pour fuite de raisonnement, et pourtant encore appele
# ---------------------------------------------------------------------------

_BOTS_SOURCES = ["Alfred", "JohnnyBot", "MaiqBot", "MalenaBot", "Sheogorath", "SugarBot"]


def test_aucune_cascade_ne_rappelle_le_modele_qui_fuit():
    """nemotron recopie sa pensee dans `content` (cf. `_fuite_de_raisonnement`).

    Il figurait pourtant encore en dernier echelon de la cascade REPARTIE generique,
    sous un commentaire qui vantait « Mistral Large en tete » — un modele hors
    abonnement depuis le 2026-08-30. La cascade decrivait un monde disparu.
    """
    for bot in BOTS:
        assert OPENROUTER_ECARTE not in [m for _, m in CASCADES_PERSONA[bot]]
    for type_requete in (RequestType.TEXT, RequestType.REPARTEE, RequestType.IMAGE,
                         RequestType.AUDIO, RequestType.REASONING):
        cascade = get_model_cascade(type_requete, None)
        assert OPENROUTER_ECARTE not in [m for _, m in cascade], \
            f"{type_requete} : cascade generique sur un modele ecarte"


@pytest.mark.parametrize("bot", _BOTS_SOURCES)
def test_aucun_bot_n_appelle_le_modele_qui_fuit_hors_cascade(bot):
    """Le vrai danger n'etait pas la cascade, c'etait les appels DIRECTS.

    Sheogorath appelait nemotron dans 4 endroits vivants (rumeur du jour, imposteur
    x3) sans passer par `llm_cascade` — donc sans `_fuite_de_raisonnement()` ni
    `_est_vide()`. C'est le montage exact qui a fait reciter son raisonnement a Malena
    en plein Discord. Un modele ecarte doit l'etre PARTOUT, pas seulement dans les
    listes ou on pense a regarder.

    ⚠️ On ne cherche PAS le mot « nemotron » : les commentaires et les docstrings qui
    documentent le refus le citent legitimement, et un test qui les interdit pousse a
    effacer la memoire du bug. On cherche les deux formes qui le remettent EN SERVICE :
    le passer comme `model=` d'un appel, ou le redefinir en constante de repli.
    """
    # Trois formes, parce que deux ne suffisaient pas — verifie par mutation : remettre
    # l'appel d'origine `model=OPENROUTER_FREE` passait au travers, le nom de la
    # constante masquant l'identifiant du modele.
    #   1. le litteral passe a un appel ;
    #   2. le NOM historique, qui signifiait « en service » ;
    #   3. une constante redefinie avec cet id — sauf *_ECARTE, qui dit son statut :
    #      c'est la memoire du refus, pas une remise en service.
    dangereux = re.compile(
        r"""model\s*=.*nemotron"""
        r"""|OPENROUTER_FREE"""
        r"""|^\s*(?!\w*ECARTE)[A-Z_]+\s*=\s*["']nvidia/nemotron""")
    sources = (list((_parent_dir_path / bot).glob("*.py"))
               + list((_parent_dir_path / bot / "core").glob("*.py")))
    assert sources, f"{bot} : aucune source lue, le test ne prouverait rien"
    for source in sources:
        for numero, ligne in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            # On ne juge que la partie CODE : citer le nom dans un commentaire, c'est
            # documenter le refus, et un test qui l'interdit pousse a effacer la
            # memoire du bug. Ce qui suit un « # » n'est jamais execute.
            code = ligne.split("#", 1)[0]
            assert not dangereux.search(code), (
                f"{source.name}:{numero} remet en service un modele ecarte pour "
                f"fuite de raisonnement")
