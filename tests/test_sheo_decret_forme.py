# -*- coding: utf-8 -*-
"""Forme du décret de Sheogorath (24/09).

Relevé : quatre phrases pour « 1-2 », les trois thèmes du prompt (« fromage, papillons,
intestins ») récités ensemble, et un titre coupé au 29e caractère avec « ... », au
milieu d'un mot, sur l'image ET sur le nom du rôle Discord.
"""
import ast
import os
import sys

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

from sheo_decrees import TITRE_MAX, texte_de_decret, titre_de_decret

MENTION = "<@123>"
BOT = os.path.join(_sheo_dir, "bot_sheogorath.py")


def test_le_titre_court_passe_tel_quel():
    assert titre_de_decret("Duc des Chaussettes") == "Duc des Chaussettes"


def test_le_titre_long_est_coupe_a_un_mot_sans_points_de_suspension():
    long = "Grand Inquisiteur Suprême des Fromages Oubliés de Cyrodiil"
    t = titre_de_decret(long)
    assert len(t) <= TITRE_MAX
    assert "..." not in t and "…" not in t
    assert long.startswith(t) and long[len(t)] == " ", f"coupé au milieu d'un mot : {t!r}"


def test_le_titre_ne_finit_pas_sur_un_petit_mot():
    t = titre_de_decret("Gardien Perpétuel et Sacré de la Cuillère")
    assert t.split()[-1].lower() not in {"de", "la", "et", "des", "du"}, t


def test_un_titre_vide_retombe_sur_le_titre_par_defaut():
    assert titre_de_decret("   ") == "Sujet de la Folie"


def test_quatre_phrases_deviennent_deux():
    texte = (f"MORTEL {MENTION} ! Tu es condamné au fromage. "
             "Les papillons te suivront. Tes intestins chanteront.")
    assert texte_de_decret(texte, MENTION) == f"MORTEL {MENTION} ! Tu es condamné au fromage."


def test_la_mention_survit_a_la_coupe():
    """Si la cible n'est nommée qu'en 3e phrase, la couper ferait un décret qui ne vise
    personne : la mention revient en tête."""
    texte = f"Oyez ! Le fromage a parlé. Et il a choisi {MENTION}."
    rendu = texte_de_decret(texte, MENTION)
    assert rendu.startswith(MENTION) and rendu.count(".") <= 2


def test_une_phrase_seule_n_est_pas_touchee():
    texte = f"{MENTION} comptera les navets jusqu'à l'aube ! 🥕"
    assert texte_de_decret(texte, MENTION) == texte


def test_le_bot_passe_par_les_deux_filets_et_ne_recite_plus_les_themes():
    """Verrou sur le FICHIER du bot (pas une copie de la logique) : l'ancien couperet
    `title[:29] + "..."` a disparu, les deux fonctions sont APPELÉES, et aucun prompt ne
    liste plus les trois thèmes."""
    source = open(BOT, encoding="utf-8").read()
    assert 'title[:29] + "..."' not in source
    appels = {n.func.id for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert {"titre_de_decret", "texte_de_decret"} <= appels
    lignes_de_prompt = [l for l in source.splitlines()
                        if "(fromage, papillons, intestins)" in l and not l.lstrip().startswith("#")]
    assert not lignes_de_prompt, lignes_de_prompt


def test_le_decret_n_existe_pas_sur_twitch():
    """Ahmed, 24/09 : le décret vit sur Discord SEULEMENT (parchemin + rôle). Sur Twitch,
    ni commande, ni alias, ni récompense de chaîne ne doit y mener.

    Verrou sur le fichier du bot : on lit les DICTIONNAIRES passés à `setup_twitch_chat`,
    pas une copie de leur contenu."""
    arbre = ast.parse(open(BOT, encoding="utf-8").read())
    fonctions = {n.name for n in ast.walk(arbre)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "cmd_decret" not in fonctions, "la commande Twitch du décret est revenue"

    vus = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("commands", "command_aliases"):
            if isinstance(n.value, ast.Dict):
                vus.append(n.targets[0].id)
                for k, v in zip(n.value.keys, n.value.values):
                    for c in (k, v):
                        if isinstance(c, ast.Constant) and isinstance(c.value, str):
                            assert "decret" not in c.value.lower() and "décret" not in c.value.lower() \
                                and "decree" not in c.value.lower(), (n.targets[0].id, c.value)
        if isinstance(n, ast.keyword) and n.arg == "eventsub_reward_map" and isinstance(n.value, ast.Dict):
            vus.append("eventsub_reward_map")
            for v in n.value.values:
                assert getattr(v, "value", "") != "decret", "une récompense Twitch mène au décret"
    assert {"commands", "command_aliases", "eventsub_reward_map"} <= set(vus), \
        f"le verrou ne trouve plus les tables Twitch de Sheogorath : {vus}"
