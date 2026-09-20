# -*- coding: utf-8 -*-
import os
import sys
import pytest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_alfred_dir = os.path.join(_parent_dir, "Alfred")
if _alfred_dir not in sys.path:
    sys.path.insert(0, _alfred_dir)

import alfred_data

def test_alfred_personality_prompt_contains_pillars():
    prompt = alfred_data.PERSONALITY_PROMPT
    assert "SOLLICITUDE DÉGUISÉE" in prompt
    assert "LANGUE MATERNELLE" in prompt
    
    # Old rule should be removed
    assert "NE SOIS JAMAIS AGRÉABLE" not in prompt

def test_alfred_no_black_or_wayne_references():
    prompt = alfred_data.PERSONALITY_PROMPT
    
    assert "Maître Black" not in prompt
    assert "Résidence Black" not in prompt
    assert "Maître Wayne" not in prompt

def test_alfred_dit_le_serveur_jamais_le_manoir():
    """Alfred appelle Discord « le serveur ».

    Son lore disait 'Discord' = 'Le Manoir', 'Serveur' = 'la Résidence du Maître' —
    decision de l'utilisateur le 2026-09-13 : ce sera « le serveur », partout.

    Le verrou lit les LITTERAUX des 3 fichiers par `ast`, pas le seul prompt : les
    repliques en dur de `bot_alfred.py` et `games_persona.py` ne passent NI par le
    prompt NI par le LLM, donc rien d'autre ne les surveille
    ([[gotcha-persona-fuite-dans-le-partage]] : relire les litteraux, pas le code).
    """
    import ast

    # Les SEULES occurrences tolerees, chacune pour une raison explicite.
    tolerees = (
        # 1. L'interdiction elle-meme, dans le prompt : elle doit nommer ce qu'elle bannit.
        "Tu dis 'le serveur'",
        # 2. Le quiz Batman : « Ou vit Batman ? » — c'est de la culture generale sur
        #    Wayne Manor, pas Alfred qui designe Discord. La remplacer casserait la
        #    question.
        "Le Manoir Wayne (Wayne Manor)",
        "Le Manoir Wayne. Une bien grande",
    )

    fautifs = []
    for fichier in ("alfred_data.py", "bot_alfred.py", "games_persona.py"):
        chemin = os.path.join(_parent_dir, "Alfred", fichier)
        src = open(chemin, encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            texte = node.value
            # ⚠️ Insensible a la casse : les deux occurrences de `games_persona.py`
            # s'ecrivaient « manoir » en minuscule. Un verrou qui ne cherche que
            # « Manoir » les laisse passer et ne verrouille donc rien
            # ([[gotcha-verrou-trop-faible]]).
            minuscules = texte.lower()
            if "manoir" not in minuscules and "résidence du maître" not in minuscules:
                continue
            if any(t.lower() in minuscules for t in tolerees):
                continue
            fautifs.append(f"{fichier}:{node.lineno} : {texte[:80]}")

    saut = chr(10)
    assert not fautifs, (
        "Alfred designe encore Discord par le Manoir / la Residence du Maitre :"
        + saut + "  " + (saut + "  ").join(fautifs)
    )

def _charger_protocole_maitre():
    """Charge la VRAIE fonction depuis `Alfred/bot_alfred.py`, sans importer le bot.

    Importer `bot_alfred` exigerait les jetons Discord et construirait les clients
    d'API. On extrait donc la fonction par `ast` et on execute son source tel quel :
    le test porte sur le code du bot, jamais sur une reconstitution
    ([[gotcha-test-qui-retape-la-logique]]).
    """
    import ast

    chemin = os.path.join(_parent_dir, "Alfred", "bot_alfred.py")
    src = open(chemin, encoding="utf-8").read()
    arbre = ast.parse(src)
    for noeud in arbre.body:
        if isinstance(noeud, ast.FunctionDef) and noeud.name == "protocole_maitre":
            espace = {}
            exec(compile(ast.Module(body=[noeud], type_ignores=[]), chemin, "exec"), espace)
            return espace["protocole_maitre"]
    raise AssertionError("protocole_maitre est introuvable dans Alfred/bot_alfred.py")


class _FauxMembre:
    def __init__(self, identifiant=42, proprietaire=None, administrateur=False, avec_guild=True):
        self.id = identifiant
        if avec_guild:
            class _Guilde:
                owner_id = proprietaire
            self.guild = _Guilde()
        else:
            self.guild = None

        class _Permissions:
            administrator = administrateur
        self.guild_permissions = _Permissions()


def test_le_createur_du_serveur_est_appele_maitre_avec_sa_mention():
    protocole_maitre = _charger_protocole_maitre()
    bloc = protocole_maitre(_FauxMembre(identifiant=7, proprietaire=7))
    assert "Maître <@7>" in bloc, bloc
    assert "créateur" in bloc


def test_un_administrateur_est_appele_maitre_avec_sa_mention():
    protocole_maitre = _charger_protocole_maitre()
    bloc = protocole_maitre(_FauxMembre(identifiant=9, proprietaire=1, administrateur=True))
    assert "Maître <@9>" in bloc, bloc
    assert "administrateur" in bloc


def test_le_sarcasme_n_est_pas_suspendu_par_la_deference():
    """Sans cette phrase, « appelez-le Maitre » suffit a rendre Alfred servile —
    or son prompt entier repose sur le sarcasme permanent."""
    protocole_maitre = _charger_protocole_maitre()
    bloc = protocole_maitre(_FauxMembre(identifiant=7, proprietaire=7))
    assert "sarcasme" in bloc.lower()


def test_un_membre_ordinaire_n_est_pas_un_maitre():
    protocole_maitre = _charger_protocole_maitre()
    assert protocole_maitre(_FauxMembre(identifiant=5, proprietaire=1)) == ""


def test_en_message_prive_le_protocole_se_tait_sans_lever():
    """En MP, `message.author` est un `User` : ni serveur ni permissions. Le meme
    piege que le profil structurel, qui rend "" dans ce cas."""
    protocole_maitre = _charger_protocole_maitre()
    assert protocole_maitre(None) == ""
    assert protocole_maitre(_FauxMembre(avec_guild=False)) == ""


def test_le_protocole_est_bien_BRANCHE_dans_le_contexte():
    """Une fonction juste mais jamais appelee ne sert a rien : exiger l'APPEL, avec
    son argument ([[gotcha-import-ajoute-mais-pas-cable]])."""
    import ast

    chemin = os.path.join(_parent_dir, "Alfred", "bot_alfred.py")
    src = open(chemin, encoding="utf-8").read()
    appels = [
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "protocole_maitre"
        and len(n.args) == 1 and getattr(n.args[0], "id", None) == "member"
    ]
    assert appels, "protocole_maitre(member) n'est appele nulle part dans bot_alfred.py"


def test_alfred_ne_publie_plus_le_conseil_du_vendredi():
    """Alfred n'a plus de publication automatique du vendredi.

    Decision d'Ahmed le 2026-09-19, sur piece : le message recu disait « un the
    correctement prepare exige d'abord une tasse propre [...] si vous insistez pour en
    faire une scene de crime, au moins nettoyez les traces avec du vinaigre blanc, pas
    votre salive ».

    Le modele n'avait rien invente : la consigne LUI DEMANDAIT ce registre —
    `Sujets : savoir-vivre, hygiene, nettoyage de scenes de crime, preparation du the`
    ([[gotcha-le-prompt-enseigne-le-tic-interdit]] : une demonstration bat une
    interdiction, et ici c'etait une commande explicite). Le repli en dur parlait de
    « larmes... ou de sang », et un statut Discord annoncait « Nettoyer le sang sur le
    tapis ». Tout est parti avec la tache.

    ⚠️ Le verrou ne se contente PAS de chercher le nom `weekly_protip_alfred` : le
    renommer suffirait a le rendre vert alors que la publication serait revenue
    ([[gotcha-verrou-trop-faible]]). Il interdit les trois choses ensemble — le nom, les
    LITTERAUX de l'annonce, et le MECANISME : aucune tache `tasks.loop` d'Alfred ne doit
    se brancher sur un jour de la semaine.
    """
    import ast

    chemin = os.path.join(_parent_dir, "Alfred", "bot_alfred.py")
    arbre = ast.parse(open(chemin, encoding="utf-8").read(), filename="bot_alfred.py")

    fautes = []

    for noeud in ast.walk(arbre):
        # 1. Le nom de la tache supprimee.
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if "weekly_protip" in noeud.name:
                fautes.append(f"ligne {noeud.lineno} : la tache `{noeud.name}` est revenue")

        # 2. Les litteraux de l'annonce.
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            minuscules = noeud.value.lower()
            for interdit in ("conseil du vendredi", "conseil du majordome",
                             "scene de crime", "scène de crime",
                             "scenes de crime", "scènes de crime"):
                if interdit in minuscules:
                    fautes.append(
                        f"ligne {noeud.lineno} : « {interdit} » dans "
                        f"{noeud.value[:60]!r}"
                    )
                    break

    # 3. Le mecanisme : une boucle `tasks.loop` qui regarde le jour de la semaine.
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        est_une_boucle = any(
            "tasks.loop" in ast.unparse(d) for d in noeud.decorator_list
        )
        if not est_une_boucle:
            continue
        for interne in ast.walk(noeud):
            if (isinstance(interne, ast.Call)
                    and isinstance(interne.func, ast.Attribute)
                    and interne.func.attr == "weekday"):
                fautes.append(
                    f"ligne {interne.lineno} : la tache `{noeud.name}` se branche de "
                    "nouveau sur un jour de la semaine"
                )

    saut = chr(10)
    assert not fautes, (
        "La publication automatique du vendredi est de retour chez Alfred :"
        + saut + "  " + (saut + "  ").join(fautes)
    )


def test_la_regle_de_longueur_d_alfred_est_posee_comme_sa_forme_NORMALE():
    """La contrainte de longueur d'Alfred n'est plus une ligne enfouie.

    Mesure du 2026-09-20, sur les 68 reponses d'Alfred servies par ministral dans les
    rapports deja sur disque : mediane 4 a 5 phrases / 44 mots quand sa fiche dit
    « 2 phrases maximum », et **66 sur 68** au-dela de deux phrases. Le juge le sanctionne
    a chaque passe (`longueur` 2.90 puis 3.30, le plus faible des six bots), et il nomme
    trois choses a la fois : les phrases en trop, le double paragraphe, la relance finale
    entre parentheses.

    ⚠️ AUCUN FILET N'EST LIVRE, et c'est la mesure qui l'a dit : une coupe a deux phrases
    toucherait 97 % de ses repliques (66/68), la ou celle de Malena — deja jugee trop
    destructrice — en touchait 69 %. C'est un changement de PROMPT seul
    ([[gotcha-un-filet-ne-se-transpose-pas-d-un-bot-a-l-autre]]).

    ⚠️ Et la regle n'est PAS demontree sur un exemple de replique, contrairement a celle
    de Malena : Alfred est le bot qui RECITE sa fiche au caractere pres
    ([[gotcha-un-modele-obeissant-RECITE-la-fiche]]). On decrit la FORME — une phrase qui
    sert, une phrase qui pique — jamais la phrase elle-meme.

    Le verrou porte sur quatre choses, parce que trois d'entre elles ont deja ete
    annulees ailleurs dans ce depot :
      1. la regle est posee comme la forme NORMALE, pas comme un plafond ;
      2. ses puces s'affichent en LISTE : collees en un seul paragraphe, elles se noient
         dans le mur de texte, ce qui est exactement le defaut corrige ;
      3. elle interdit la relance (le tour en plus) ET le saut de ligne ;
      4. la SOLLICITUDE DEGUISEE, qui decrit trois mouvements, ne sert plus de permission
         de developper ([[gotcha-une-permission-bat-une-demonstration]]).
    """
    prompt = alfred_data.PERSONALITY_PROMPT
    saut = chr(10)

    debut = prompt.find("[CONTRAINTE DE LONGUEUR")
    assert debut != -1, "la section de longueur d'Alfred a disparu"
    fin = prompt.find("[RELATIONS]", debut)
    section = prompt[debut:fin]

    # 1. La forme NORMALE, pas un plafond a frôler.
    assert "FORME NORMALE" in section, (
        "la longueur est redevenue un simple plafond : c'est sous cette forme qu'elle "
        "etait ignoree 66 fois sur 68"
    )
    assert "DEUX phrases" in section

    # 2. Les puces sont une LISTE, pas un mur.
    puces = [ligne for ligne in section.split(saut) if ligne.lstrip().startswith("- ")]
    assert len(puces) >= 4, (
        "les puces de la section de longueur sont recollees en un seul paragraphe "
        f"(trouve : {len(puces)}) — la regle qu'on veut rendre visible s'y noie"
    )

    # 3. Ce que le juge reprochait, nomme explicitement.
    assert "RELANCES" in section, "l'interdiction de relancer a saute"
    assert "saut de ligne" in section, (
        "« jamais de double paragraphe » seul ne disait pas au modele ce qu'est un "
        "double paragraphe : 28 de ses 34 sorties brutes contenaient un saut de ligne"
    )
    # ⚠️ La question RHETORIQUE reste autorisee : c'est sa signature, et interdire le
    # procede au lieu de la relance abimerait le personnage
    # ([[gotcha-le-prompt-bornait-le-DECOR-pas-la-PERSONNE]]).
    assert "questions rhétoriques" in section

    # 4. La sollicitude ne rouvre pas la porte.
    soll = prompt[prompt.find("SOLLICITUDE DÉGUISÉE"):prompt.find("LA FIERTÉ DU SERVICE")]
    assert "DEUX phrases" in soll, (
        "les trois mouvements de la sollicitude deguisee redeviennent une permission "
        "de developper, et une permission bat une interdiction"
    )
