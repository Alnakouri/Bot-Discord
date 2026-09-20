# -*- coding: utf-8 -*-
"""Une fiche de persona est une LISTE, et elle ne donne aucune phrase à réciter.

Deux défauts mesurés le 2026-09-20, sur les six fiches chargées comme le harnais les
envoie (`load_persona`, pas le fichier source) :

1. LES PUCES COLLÉES. M'aiq avait 63 puces au milieu de leur ligne et 268 caractères
   par ligne en moyenne — 82 % de sa fiche tenait en 4 méga-lignes. Alfred en avait 28.
   Johnny, Malena, Sugar et Sheogorath : zéro. Le modèle recevait un mur là où les
   autres recevaient une liste. C'est le même défaut qui avait rendu la contrainte de
   longueur d'Alfred invisible : une règle rangée au milieu d'un paragraphe est une
   règle qu'on ne lit pas.

2. LES RÉPLIQUES PRÊTES À SERVIR. Le 2026-09-20, M'aiq a rendu « Le silence est d'or.
   M'aiq prend l'or. Toi, tu gardes le silence. » — 67 caractères recopiés au caractère
   près de sa propre fiche, et la SEULE récitation des six bots ce jour-là. Sa fiche
   alignait quatre réponses aux insultes, quatre esquives et cinq exemples contextuels.
   Alfred avait été de-cité le 18/09 pour la même raison, et le personnage y avait
   GAGNÉ : fidélité 4.20 -> 4.80 ([[gotcha-un-modele-obeissant-RECITE-la-fiche]]).

⚠️ Le verrou de récitation ne vise QUE M'aiq et Alfred, les deux cas mesurés. Sugar et
Sheogorath gardent des exemples cités et notent 5.00 sur `longueur` avec 0 récitation :
leur imposer la même règle serait punir là où la mesure ne dit rien
([[gotcha-un-defaut-peut-etre-une-fonctionnalite]] — viser l'invariant le plus étroit).
"""
import re
import sys
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from tests.eval.persona_loader import load_persona, PERSONAS

# Une puce qui commence au MILIEU d'une ligne, après du texte et des espaces.
_PUCE_COLLEE = re.compile(r"\S {2,}[-*] ")

# Une réplique prête à servir : une phrase citée après une flèche ou un deux-points,
# plus longue que le seuil de récitation du harnais (`_RECITATION_MIN`, 30 car.).
_REPLIQUE_CITABLE = re.compile(
    r"(?:->|→|:)\s*['«“]([^'»”\n]{30,})['»”]"
)

# Les deux bots dont la récitation a été MESURÉE, eux seuls.
_DE_CITES = ("maiq", "alfred")


def test_aucune_fiche_n_empile_plusieurs_regles_sur_une_ligne():
    """Les six fiches s'affichent en listes : une puce par ligne.

    ⚠️ Le critère est la puce COLLÉE, pas la ligne longue. Une puce de 400 caractères
    est une règle bavarde, et Malena, Sugar et Sheogorath en ont — c'est leur affaire.
    Une puce collée derrière une autre est une règle CACHÉE, et c'est le défaut qui
    rendait la contrainte de longueur d'Alfred invisible. Mesurer la longueur d'une
    ligne aurait fait rougir trois bots sains ([[gotcha-verrou-trop-faible]]).
    """
    fautes = []
    for bot in PERSONAS:
        prompt = load_persona(bot)["system_prompt"]
        collees = _PUCE_COLLEE.findall(prompt)
        if collees:
            lignes = prompt.split("\n")
            fautes.append(
                f"{bot} : {len(collees)} puce(s) collée(s) au milieu d'une ligne "
                f"({len(prompt) // max(len(lignes), 1)} car./ligne en moyenne)"
            )
    saut = chr(10)
    assert not fautes, (
        "des fiches sont redevenues des murs de texte — une règle rangée au milieu "
        "d'un paragraphe est une règle invisible :" + saut + "  " + (saut + "  ").join(fautes)
    )


def test_maiq_et_alfred_ne_donnent_aucune_replique_a_reciter():
    """Les deux fiches dont la récitation a été mesurée ne citent plus de réponse toute faite."""
    fautes = []
    for bot in _DE_CITES:
        prompt = load_persona(bot)["system_prompt"]
        for trouve in _REPLIQUE_CITABLE.findall(prompt):
            fautes.append(f"{bot} : « {trouve[:70]} »")

    saut = chr(10)
    assert not fautes, (
        "une fiche redonne des répliques prêtes à servir, et un modèle les RECOPIE "
        "(M'aiq, 67 car. au caractère près le 2026-09-20). Décrire l'ANGLE et la "
        "TECHNIQUE, jamais la phrase :" + saut + "  " + (saut + "  ").join(fautes)
    )


def test_maiq_doit_encore_PARLER_de_lui_a_la_3e_personne():
    """Sa règle ne peut pas se respecter en ne se nommant JAMAIS.

    ⚠️ Régression mesurée le 2026-09-20, et le juge ne l'a pas vue. Après la première
    réécriture de sa fiche, M'aiq est passé de 11/17 et 10/17 réponses contenant son
    nom à **0/17** — zéro occurrence sur dix-sept réponses — pendant que `fidelite`
    montait à 5.00. Il n'avait pas enfreint « tu ne dis jamais JE » : il avait cessé de
    parler de lui du tout, ce qui la respecte à la lettre et l'annule en pratique.

    La cause était dans la réécriture : « son nom n'ouvre qu'une phrase sur trois »
    portait sur les OUVERTURES, mais rien ne disait qu'il devait rester ailleurs, et les
    fragments qui le montraient avaient été retirés avec les répliques citables.

    Le verrou exige les deux moitiés ensemble : l'interdiction du 'je' ET l'obligation de
    se nommer. Une seule des deux est ce qui a produit la régression.
    """
    prompt = load_persona("maiq")["system_prompt"]
    assert "TU NE DIS JAMAIS 'JE'" in prompt, "l'interdiction du 'je' a disparu"
    assert "ET TU PARLES DE TOI" in prompt, (
        "l'obligation de se nommer a disparu : sans elle, M'aiq respecte sa règle en "
        "ne parlant plus jamais de lui (0/17 réponses le 2026-09-20)"
    )


def test_la_replique_que_maiq_recitait_a_bien_disparu():
    """Le cas exact mesuré : la ligne recopiée le 2026-09-20 n'est plus dans sa fiche.

    ⚠️ Ce verrou-ci est étroit EXPRÈS. Le précédent vise le mécanisme (une réplique
    citable) et pourrait être contourné par une autre mise en forme ; celui-ci épingle
    la phrase qui a réellement fuité, et il resterait rouge même si la forme changeait
    ([[gotcha-verrou-trop-faible]]).
    """
    prompt = load_persona("maiq")["system_prompt"]
    recitee = "Le silence est d'or. M'aiq prend l'or. Toi, tu gardes le silence."
    assert recitee not in prompt, (
        "la réplique que M'aiq recopiait mot pour mot est revenue dans sa fiche"
    )
