# -*- coding: utf-8 -*-
import os
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sugar_dir = os.path.join(_parent_dir, "SugarBot")
if _sugar_dir not in sys.path:
    sys.path.insert(0, _sugar_dir)

import sugar_data
from shared.identites import STREAMEUSE

def test_sugar_personality_prompt_gender_agreement():
    prompt = sugar_data.PERSONALITY_PROMPT
    
    # 1. L'accord : PERSONALITY_PROMPT contient « péteur », jamais au hasard et ne contient plus choisis au hasard
    assert "« péteur », jamais au hasard" in prompt
    assert "choisis au hasard" not in prompt
    
    # Check that "péteur (ou péteuse si c'est une femme — accord obligatoire)" is in prompt
    assert "péteur (ou péteuse si c'est une femme — accord obligatoire)" in prompt

def test_sugar_personality_prompt_twitch_streamer():
    prompt = sugar_data.PERSONALITY_PROMPT
    
    # 2. La streameuse : PERSONALITY_PROMPT contient son pseudo (réel si data/identites_locales.json
    #    existe, fictif sinon), le lien de sa chaîne et la consigne anti-ping
    assert STREAMEUSE in prompt
    assert f"twitch.tv/{STREAMEUSE}" in prompt
    assert "JAMAIS son nom avec un @" in prompt


# ---------------------------------------------------------------------------------------
# Le budget de mots : sa fiche dit « ~30 mots, JAMAIS plus »
# ---------------------------------------------------------------------------------------

def test_sugar_tient_son_budget_de_30_mots():
    """⚠️ Mesure sur les 85 reponses des rapports d'eval du 16 au 19/09 : **18 depassaient
    30 mots**, jusqu'a 67. Sa fiche dit pourtant « Vise ~30 mots, JAMAIS plus »
    (`sugar_data.py:30`), et le harnais le mesure deja (`deterministic.py`, cas
    `sugar_30_mots`) — il sortait `False` a chaque passe.
    """
    from SugarBot.sugar_filtres import filtre_sortie

    trop_long = (
        "La vie, c'est un bonbon a croquer sans se presser : on savoure l'enveloppe "
        "avant de decouvrir le coeur. Et le mien ? C'est un melange de sang-froid et "
        "de rires qui grattent les nerfs des peteurs. Si tu veux des details, je te "
        "conseille d'aller voir ailleurs, elle explique bien mieux que moi."
    )
    assert len(trop_long.split()) > 30, "le cas de test ne teste rien"
    rendu = filtre_sortie(trop_long)
    assert len(rendu.split()) <= 30, f"{len(rendu.split())} mots rendus"


def test_le_budget_ne_coupe_JAMAIS_au_milieu_d_une_phrase():
    """⚠️ Une punchline amputee est pire qu'une punchline longue.

    Le filet garde des phrases ENTIERES, et jamais moins d'une — meme si cette seule
    phrase depasse le budget. Trois des 85 reponses mesurees sont dans ce cas (max 34
    mots) : les raccourcir voudrait dire couper dedans, et « ~30 » est approximatif.
    """
    from SugarBot.sugar_filtres import budget_de_mots

    une_seule = ("Un serpentard ne balance jamais ses petits secrets comme on jette des "
                 "bonbons a la fete foraine, surtout quand on le lui demande aussi "
                 "maladroitement que tu viens de le faire devant tout le monde.")
    assert len(une_seule.split()) > 30, "le cas de test ne teste rien"
    assert budget_de_mots(une_seule) == une_seule, (
        "Le filet a coupe dans une phrase unique au lieu de la laisser passer."
    )

    deux = "Premiere phrase courte. " + " ".join(["mot"] * 40) + "."
    rendu = budget_de_mots(deux)
    assert rendu == "Premiere phrase courte.", (
        "La deuxieme phrase ne tenait pas dans le budget : elle devait tomber ENTIERE."
    )


def test_le_budget_epargne_une_reponse_deja_courte_et_est_idempotent():
    """Un filet qui rogne le nominal n'est plus un filet. Et sur Discord, le tour suivant
    relit le message DEJA envoye
    ([[gotcha-un-filtre-non-idempotent-laisse-du-travail-a-l-ecran]])."""
    from SugarBot.sugar_filtres import filtre_sortie

    courte = "Quel peteur ambitieux. Tes secrets sont plus mal gardes que les miens."
    assert filtre_sortie(courte) == courte

    long_texte = " ".join("Phrase numero %d ici meme." % i for i in range(1, 12))
    une_fois = filtre_sortie(long_texte)
    assert filtre_sortie(une_fois) == une_fois


def test_le_budget_preserve_l_emoji_final_et_ne_le_compte_pas():
    """L'emoji de ton ferme la replique ; le perdre en tronquant change le ton."""
    from SugarBot.sugar_filtres import budget_de_mots

    texte = ("Les critiques, c'est comme les bonbons aigres : ca pique la langue et ca "
             "passe mal. Mais un vrai peteur en fait un sport national, et ca c'est "
             "juste pathetique de sa part. \U0001F36C")
    rendu = budget_de_mots(texte)
    assert rendu.endswith("\U0001F36C"), "l'emoji de ton a disparu"
    # L'emoji ne doit pas manger une place dans le budget.
    assert len(rendu.replace("\U0001F36C", "").split()) <= 30


def test_sugar_peut_developper_quand_on_le_lui_demande():
    """⚠️ Decision d'Ahmed le 2026-09-19, APRES la livraison du budget absolu.

    Le budget etait absolu parce que sa fiche disait « JAMAIS plus ». Il a tranche
    l'inverse : elle doit pouvoir developper quand on le lui demande EXPLICITEMENT.
    Sans ce cas, le filet la coupe la ou sa fiche l'autorise desormais a s'etendre —
    exactement le defaut qui avait fait tomber `longueur` a 0.50/5 chez un autre bot
    ([[gotcha-le-juge-punissait-la-ou-la-fiche-autorise]]).
    """
    from SugarBot.sugar_filtres import filtre_sortie, budget_demande

    assert budget_demande("c'est quoi ton jeu prefere ?") == 30
    assert budget_demande("Raconte-moi ta philosophie de vie") == 60
    assert budget_demande("explique-moi ce truc") == 60

    long_texte = " ".join("Phrase numero %d de test ici." % i for i in range(1, 16))
    assert len(filtre_sortie(long_texte, "salut").split()) <= 30
    rendu_long = filtre_sortie(long_texte, "raconte-moi ta vie").split()
    assert 30 < len(rendu_long) <= 60, (
        f"{len(rendu_long)} mots : l'invitation n'ouvre pas le budget, ou l'ouvre trop."
    )


def test_la_fiche_de_sugar_et_le_filet_disent_la_MEME_chose():
    """⚠️ Un filet plus permissif que le prompt laisse passer ce que la fiche interdit ;
    un filet plus strict coupe ce qu'elle autorise. Les deux doivent bouger ENSEMBLE.

    C'est la raison d'etre de ce verrou : le budget a ete change dans le code le
    2026-09-19, et la fiche devait suivre dans le meme commit.
    """
    import sugar_data

    prompt = sugar_data.PERSONALITY_PROMPT
    # ⚠️ La formule EXACTE, pas « jamais plus » tout court : la fiche dit aussi
    # « JAMAIS plusieurs paragraphes », qui n'a rien a voir et que le motif large
    # attrapait ([[gotcha-verrou-trop-faible]]).
    assert "~30 mots, jamais plus" not in prompt.lower(), (
        "La fiche interdit encore de depasser, alors que le filet l'autorise sur "
        "invitation : le modele obeira a la fiche et la permission ne servira jamais."
    )
    assert "~60 mots" in prompt, "La fiche ne nomme pas le budget long."
    assert "~30 mots" in prompt, "La fiche ne nomme plus le budget normal."


def test_le_bot_passe_le_VRAI_message_au_filtre():
    """⚠️ Le budget est inerte si l'appelant ne lui donne pas le message.

    Et ce doit etre `user_msg_content`, pas `user_message` : ce dernier a pu recevoir
    le texte de substitution des images. Verrou AST sur le fichier du bot, jamais une
    reconstitution ([[gotcha-test-qui-retape-la-logique]]).
    """
    import ast

    chemin = os.path.join(_parent_dir, "SugarBot", "bot_sugar.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename="bot_sugar.py")
    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "filtre_sortie"]
    assert appels, "bot_sugar.py n'appelle plus filtre_sortie"

    nus = [n.lineno for n in appels if len(n.args) < 2]
    assert not nus, (
        f"filtre_sortie appele sans le message ligne(s) {nus} : le budget ne peut plus "
        "voir un « raconte » et coupera a 30 mots quoi qu'on lui demande."
    )
    mauvais = [n.lineno for n in appels
               if isinstance(n.args[1], ast.Name) and n.args[1].id != "user_msg_content"]
    assert not mauvais, f"ligne(s) {mauvais} : passer le message NON modifie par le code."


def test_le_harnais_mesure_le_budget_APPLICABLE_pas_30_en_aveugle():
    """⚠️ La mesure et le bot doivent lire le meme barème.

    Si le harnais juge tout a 30 mots alors que le bot en autorise 60 sur invitation,
    il rend `False` sur une reponse parfaitement conforme — et on « corrige » un bot
    qui n'avait rien de casse.
    """
    import sys as _sys
    _tests_dir = os.path.dirname(os.path.abspath(__file__))
    if _tests_dir not in _sys.path:
        _sys.path.insert(0, _tests_dir)
    from eval.deterministic import evaluate_deterministic

    cinquante_cinq = " ".join(["mot"] * 55)

    ok = evaluate_deterministic("sugar_30_mots", "sugar",
                                [cinquante_cinq], ["Raconte-moi ta philosophie"])
    assert ok["succes"] is True, "55 mots sur un « raconte » tiennent dans le budget de 60"

    pas_ok = evaluate_deterministic("sugar_30_mots", "sugar",
                                    [cinquante_cinq], ["et sinon ca va ?"])
    assert pas_ok["succes"] is False, "55 mots sur une banalite depassent le budget de 30"

    # Un autre bot n'est pas concerne par la regle de Sugar.
    autre = evaluate_deterministic("sugar_30_mots", "johnny",
                                   [cinquante_cinq], ["et sinon ca va ?"])
    assert autre["succes"] is True, "le critere des 30 mots n'appartient qu'a Sugar"


def test_les_exemples_ne_jugent_plus_le_message():
    """⚠️ 24/09 : deux exemples jugeaient le MESSAGE de l'autre, et Sugar le faisait
    ~16 fois sur 18 face a un simple « sugar ». Une demonstration bat une consigne."""
    import sugar_data
    prompt = sugar_data.PERSONALITY_PROMPT
    debut = prompt.index("EXEMPLES DE VOIX")
    exemples = prompt[debut:prompt.index("\n\n", debut)]
    for motif in (
        "message entier", "rien d'intéressant qui suit", "Trois fois mon nom",
        "manquait justement", "Drôle de régime", "Je range les griffes",
    ):
        assert motif not in exemples, motif
    assert "Reproche gentil" in exemples
    assert not any(l.rstrip().endswith("? »") for l in exemples.splitlines()), \
        "un exemple finit par une question : la fiche l'interdit"


def test_sonde_detection_recopie():
    """Vérifie la détection de recopie par la sonde sans réseau."""
    from tools.sonde_ton_twitch import est_recopie, reponses_des_exemples
    import sugar_data

    # 1. Cas vrai : partage une suite de 5 mots consécutifs
    exemples = ["Me voilà. Ce chat manquait justement d'un peu de peps."]
    assert est_recopie("Me voilà. Ce chat manquait justement d'un peu de peps, Ahmed.", exemples) is True

    # 2. Cas faux : pas de suite commune de 5 mots
    assert est_recopie("Je réponds présente et le stream se passe très bien.", exemples) is False
    assert est_recopie(None, exemples) is False
    assert est_recopie("", exemples) is False
    assert est_recopie("Me voilà.", exemples) is False

    # 3. reponses_des_exemples renvoie autant de réponses que de lignes → «
    prompt = sugar_data.PERSONALITY_PROMPT
    debut = prompt.index("EXEMPLES DE VOIX")
    fin = prompt.find("\n\n", debut)
    bloc = prompt[debut:fin] if fin != -1 else prompt[debut:]
    lignes_avec_fleche_et_guillemet = [
        l for l in bloc.splitlines()
        if "→" in l and l.rfind("«") > l.rfind("→")
    ]
    reps = reponses_des_exemples(prompt)
    assert len(reps) == len(lignes_avec_fleche_et_guillemet)
    assert all(r for r in reps)


def test_regle_variete_ne_prescrit_plus_la_mechancete_par_defaut():
    """⚠️ 25/09 : la règle de variété prescrivait trois ossatures méchantes sur quatre
    pour TOUTE réplique, rendant Sugar agressive même sur un simple « sugar ».
    Le mordant est désormais réservé à qui la cherche."""
    import sugar_data
    prompt = sugar_data.PERSONALITY_PROMPT
    debut = prompt.index("VARIÉTÉ DE STRUCTURE")
    fin = prompt.index("EXEMPLES DE VOIX", debut)
    bloc_variete = prompt[debut:fin]
    for motif in ("cinglante", "moqueur", "pique nette"):
        assert motif not in bloc_variete, f"{motif!r} encore présent dans la règle de variété"
    assert "le mordant, garde-le pour qui te cherche" in bloc_variete

