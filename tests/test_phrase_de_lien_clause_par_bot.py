"""La clause de la phrase de lien est PAR BOT, et elle le reste.

Le 2026-09-21, une phrase de Sugar sur Twitch promettait « une bonne tasse de caramel
chaud » — un objet qui n'existe pas, alors que l'instruction lui interdit deja d'inventer
une recompense. Deux formulations ont ete mesurees pour le corriger :

    variante                                sugar        maiq        alfred
    A : texte commun actuel                 4/6 objets   2/4         2/4
    B : « tu n'offres rien de materiel »    1/6          3/5         3/5
    C : B + « varie ce que tu annonces »    0/6          1/4         2/4

Second reproche le meme soir : Sugar parlait du Discord comme du SIEN (« Viens sur mon
serveur »), alors qu'il est celui de la communaute. La clause collective mesuree :

    sugar (avec sa clause)   0/6 « mon serveur », 0/6 objet, voix intacte
    maiq  (texte commun)     5/5 ouvertures IDENTIQUES, le feu de camp revient
    alfred (texte commun)    5/5 inventent un the ou des tasses (2/4 avant)

Prive de ce qu'il peut promettre, le modele se rabat sur ce qu'il imagine du lieu : chez
Sugar la clause anti-objet retient la derive, chez les autres elle s'aggrave.

⚠️ **B et C reparent Sugar et CASSENT M'aiq** : ses ouvertures s'effondrent sur une seule
formule (5/5 « Les Plaines de l'Echo... » en B, 3/4 en C) quand le texte commun en rend
quatre differentes. Aucune formulation partagee n'ameliore les six
([[gotcha-un-filet-ne-se-transpose-pas-d-un-bot-a-l-autre]]).

La variante C est donc livree POUR SUGAR SEUL. Ce que ce fichier garde :
  - qu'un bot ABSENT de la table recoit le texte commun, au caractere pres ;
  - que la table n'accueille que des bots MESURES — y ajouter un nom est un acte qui
    demande une mesure, et ce test le rappelle en echouant.
"""
import ast
import inspect
from pathlib import Path

import pytest

from shared.twitch.dispatch import DispatchMixin, _nettoyer_phrase_de_lien

RACINE = Path(__file__).resolve().parent.parent

# Les seuls bots pour lesquels une clause a ete MESUREE. Cf. l'entete.
BOTS_MESURES = {"sugar", "johnny"}


def test_seuls_les_bots_mesures_ont_une_clause():
    assert set(DispatchMixin.CLAUSES_PAR_BOT) == BOTS_MESURES, (
        "un bot a ete ajoute (ou retire) de CLAUSES_PAR_BOT. Cette table ne se remplit "
        "pas a l'intuition : la meme clause fait passer Sugar de 4 objets inventes sur 6 "
        "a zero, et effondre les ouvertures de M'aiq sur une formule unique. Mesurer le "
        "bot concerne, puis mettre BOTS_MESURES a jour ici."
    )


def test_un_bot_absent_recoit_exactement_le_texte_commun():
    """Le defaut est la chaine VIDE, pas une clause « neutre »."""
    assert DispatchMixin.CLAUSES_PAR_BOT.get("maiq", "") == ""
    assert DispatchMixin.CLAUSES_PAR_BOT.get("un-bot-qui-n-existe-pas", "") == ""


def test_la_clause_de_sugar_porte_bien_les_trois_regles_mesurees():
    clause = DispatchMixin.CLAUSES_PAR_BOT["sugar"]
    assert "matériel" in clause, "la regle qui retire l'objet invente a disparu"
    assert "change à chaque fois" in clause, (
        "la regle de variete a disparu : sans elle, la seule interdiction fait tomber "
        "Sugar sur une formule d'attente toute faite (mesure : 3 fois sur 6)."
    )
    assert "appartient à la communauté" in clause, (
        "la regle collective a disparu : sans elle, Sugar parle du Discord comme du SIEN "
        "(« Viens sur mon serveur »), alors qu'il est celui de la communaute."
    )
    assert "NOUS" in clause, "le « on/nous » n'est plus demande"


def test_la_clause_de_johnny_vise_la_PROMESSE_pas_le_mot():
    """Le whisky et la clope SONT son vocabulaire : les interdire l'appauvrirait.

    Mesure du 2026-09-21 sur ministral, 8 generations par variante : 6/8 promettaient
    une biere ou une clope au lecteur avec le texte commun, 3/8 avec cette clause.
    """
    clause = DispatchMixin.CLAUSES_PAR_BOT["johnny"]
    assert "ne promets rien" in clause
    assert "restent les TIENS" in clause, (
        "la clause a ete durcie en interdisant le VOCABULAIRE : Johnny sans clope ni "
        "whisky n'est plus Johnny. C'est la promesse qui est interdite, pas le mot."
    )


def test_la_clause_est_vraiment_LUE_par_la_fonction():
    """⚠️ Exiger l'APPEL avec ses arguments, pas la presence du nom dans le fichier.

    Une table declaree et jamais lue passerait n'importe quel test de contenu, et la
    phrase de Sugar continuerait d'inventer sa tasse de caramel.
    """
    source = inspect.getsource(DispatchMixin._generate_link_line)
    arbre = ast.parse(source.lstrip())
    lectures = [
        n for n in ast.walk(arbre)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "get"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "CLAUSES_PAR_BOT"
    ]
    assert lectures, "`_generate_link_line` ne lit pas CLAUSES_PAR_BOT"
    for appel in lectures:
        assert len(appel.args) == 2, (
            "la lecture doit porter un defaut explicite : `.get(self.bot_id, \"\")`. "
            "Sans lui, un bot absent recevrait `None` et l'instruction serait corrompue."
        )
        assert getattr(appel.args[1], "value", None) == "", (
            "le defaut d'un bot non mesure doit etre la chaine VIDE."
        )


# --------------------------------------------------------------------------------------
# L'emballage : une replique entiere entre asterisques etait JETEE
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("brut, attendu", [
    # Le cas mesure : avec l'accroche au jeu, ministral enrobe 5 repliques de Johnny
    # sur 6. `strip_stage_directions` y voyait une didascalie et rendait None — cinq
    # invitations ecrites pour rien, remplacees par le gabarit fixe.
    ("""*"Viens, je te raconterai comment j'ai fait sauter Arasaka. 🎸"*""",
     "Viens, je te raconterai comment j'ai fait sauter Arasaka. 🎸"),
    ("""\"Viens nous voir la-bas, on t'attend. 🔥\"""",
     "Viens nous voir la-bas, on t'attend. 🔥"),
    ("*Viens donc nous voir maintenant.*", "Viens donc nous voir maintenant."),
    ("Sans aucun emballage, viens donc. 🎸", "Sans aucun emballage, viens donc. 🎸"),
])
def test_une_replique_enrobee_est_deballee_pas_jetee(brut, attendu):
    assert _nettoyer_phrase_de_lien(brut) == attendu


@pytest.mark.parametrize("didascalie", [
    "*sourit*",
    "*hausse les epaules*",
    "*Il sourit puis repart tranquillement*",
])
def test_une_VRAIE_didascalie_reste_jetee(didascalie):
    """⚠️ Le garde-fou du deballage, et il a demande deux criteres.

    Avec le seul compte de mots, `*Il sourit puis repart tranquillement*` — une vraie
    didascalie de cinq mots — ressortait comme invitation. On exige donc AUSSI une
    ponctuation de fin de phrase, qu'aucune didascalie de ces bots ne porte.
    """
    assert _nettoyer_phrase_de_lien(didascalie) is None
