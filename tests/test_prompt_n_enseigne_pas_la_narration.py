# -*- coding: utf-8 -*-
"""Un prompt ne doit pas RENDRE la forme qu'il interdit.

Mesuré le 2026-09-16 : Johnny et Alfred sortaient des incises entre astérisques
(« *thé servi avec déférence* », « *vraiment* ») et le juge les notait 1/5 en fidélité,
« viole les règles de narration ». Leur prompt l'interdisait pourtant — RÈGLE ABSOLUE #1
chez Johnny. Mais la ligne d'interdiction **écrivait la forme interdite** :

    ❌ INTERDIT : *allume une clope*, ... *sort sa guitare*
    ❌ INTERDIT : ... (ex: *ouais bref*, *je crois*, *soupir*)

Soit cinq démonstrations du motif chez Johnny, quatre chez Alfred, contre une ligne qui
l'interdit. C'est la leçon déjà payée avec le moule Haskill
([[gotcha-le-prompt-enseigne-le-tic-interdit]]) : **une démonstration bat une
interdiction**, et renforcer le filet ne sert à rien. On NOMME la forme, on ne la REND pas.

⚠️ `Sheogorath` est un cas à part, réglé le 2026-09-16 sur décision de l'utilisateur
(« pas de narration »). Ses cinq occurrences n'étaient pas des exemples : c'étaient des
easter eggs de `SHEO_BRAIN["easter_eggs"]`, renvoyés TELS QUELS au salon par
`bot_sheogorath.py` (1 % des messages), **sans passer par le LLM** — donc pas un prompt
qui enseigne, mais un bot qui narre pour de bon, en violation de sa propre règle
« PAS DE NARRATION ». Elles ont été réécrites en PAROLES, pas supprimées : le tango,
la chanson et le quatrième mur sont toujours là, mais Sheo les DIT.
"""
import os
import re

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Les bots dont la règle interdit explicitement l'incise entre astérisques.
PERSONAS = {
    "Alfred": "alfred_data.py",
    "JohnnyBot": "johnny_data.py",
    "MaiqBot": "maiq_data.py",
    "MalenaBot": "malena_data.py",
    "Sheogorath": "sheo_data.py",
    "SugarBot": "sugar_data.py",
}

# Un segment *…* court, sur une seule ligne : le motif que les modèles recopient.
# `**gras**` est épargné (Markdown Discord), tout comme l'en-tête `# -*- coding -*-`.
MOTIF = re.compile(r"(?<!\*)\*([^*\n]{2,60})\*(?!\*)")


def test_aucune_persona_ne_rend_la_forme_qu_elle_interdit():
    fautifs = {}
    for dossier, fichier in PERSONAS.items():
        chemin = os.path.join(_parent_dir, dossier, fichier)
        if not os.path.exists(chemin):
            continue
        trouve = [x for x in MOTIF.findall(open(chemin, encoding="utf-8").read())
                  if "coding" not in x]
        if trouve:
            fautifs[dossier] = trouve

    assert not fautifs, (
        f"des personas ÉCRIVENT l'incise entre astérisques qu'elles interdisent : {fautifs}. "
        "Nommer la forme (« entre astérisques »), ne jamais la rendre — même dans un "
        "❌ MAUVAIS EXEMPLE, que le modèle recopie quand même."
    )


def test_l_interdiction_elle_meme_n_a_pas_disparu():
    """⚠️ Le contre-verrou. Retirer la démonstration ne doit pas retirer la RÈGLE :
    un `sed` trop large supprimerait la ligne entière et ce fichier resterait vert."""
    for dossier, fichier in PERSONAS.items():
        chemin = os.path.join(_parent_dir, dossier, fichier)
        if not os.path.exists(chemin):
            continue
        src = open(chemin, encoding="utf-8").read().lower()
        if dossier in ("MaiqBot", "MalenaBot"):
            continue  # ces deux-là n'ont jamais porté la règle sous cette forme
        assert "astérisque" in src, (
            f"{dossier} : la règle qui interdit les astérisques a disparu du prompt — "
            "on a retiré la démonstration ET l'interdiction"
        )



def test_sheogorath_ne_narre_plus_a_la_TROISIEME_personne():
    """Ses easter eggs étaient envoyés TELS QUELS au salon, pas donnés en exemple.

    `bot_sheogorath.py` tire dans `SHEO_BRAIN["easter_eggs"]` et renvoie la chaîne
    directement, 1 % des messages, **sans passer par le LLM**. Cinq d'entre elles étaient
    de la didascalie à la 3e personne — « Sheogorath danse le tango » — alors que sa
    propre `PERSONALITY_BASE` dit « Tu PARLES, tu ne te décris pas ». Aucun prompt ne
    pouvait corriger ça : le LLM n'était pas dans la boucle.

    Réécrites en paroles le 2026-09-16, sur décision de l'utilisateur.
    """
    chemin = os.path.join(_parent_dir, "Sheogorath", "sheo_data.py")
    src = open(chemin, encoding="utf-8").read()

    for narration in ("Sheogorath danse", "Sheogorath chante", "Sheogorath sourit",
                      "Sheogorath se", "Sheogorath regarde"):
        assert narration not in src, (
            f"didascalie à la 3e personne retrouvée : {narration!r}. Ces chaînes partent "
            "TELLES QUELLES au salon — Sheo doit le DIRE, pas se décrire."
        )

    assert "Tu PARLES, tu ne te décris pas" in src,         "la règle PAS DE NARRATION a disparu de PERSONALITY_BASE"
