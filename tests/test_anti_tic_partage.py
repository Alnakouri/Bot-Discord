# -*- coding: utf-8 -*-
"""Verrous du filet anti-tics mutualisé (`shared/anti_tic.py`, vendorisé en `core/`).

Ces tests naissent de quatre défauts constatés à la promotion du filet hors de Sheo :

1. la clôture « Haskill, note ça » — le tic PROPRE à Sheo — est partie dans le module
   partagé, donc dans le prompt des cinq autres bots et de tout le chemin Twitch ;
2. le `\\n\\n` qui détachait la consigne Twitch du bloc précédent est resté derrière :
   la consigne se soudait à la phrase d'avant ;
3. `anti_tic.py` n'était dans AUCUNE des deux listes de vendoring, donc un bot déployé
   sans `shared/` retombait en silence sur un filet absent ;
4. le filet n'était câblé que sur deux bots sur six.
"""
import ast
import os
import sys

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

from shared.anti_tic import build_anti_tic_consigne  # noqa: E402

# Le bot, son fichier, et le nom sous lequel la consigne est interpolée dans son prompt.
BOTS = [
    ("Alfred", os.path.join("Alfred", "bot_alfred.py"), "anti_tic"),
    ("Johnny", os.path.join("JohnnyBot", "bot_johnny.py"), "anti_tic"),
    ("M'aiq", os.path.join("MaiqBot", "bot_maiq.py"), "anti_tic"),
    ("Malena", os.path.join("MalenaBot", "bot_malena.py"), "_anti_tic"),
    ("Sheogorath", os.path.join("Sheogorath", "bot_sheogorath.py"), "anti_tic"),
    ("Sugar", os.path.join("SugarBot", "bot_sugar.py"), "anti_tic"),
]

REPLIQUES = [
    "Par les fromages ! Voilà une question. Note ça quelque part.",
    "Par les fromages ! Encore une question. Note ça quelque part.",
]


def _source(chemin_relatif):
    chemin = os.path.join(RACINE, chemin_relatif)
    with open(chemin, encoding="utf-8") as f:
        return f.read(), chemin


# ─────────────────────────── 1. aucun nom propre dans le partagé ───────────────────────


def test_le_helper_partage_ne_cite_aucune_persona():
    """⚠️ Ce module est lu par les SIX bots et par Twitch. Un nom propre écrit ici
    ordonne aux cinq autres de ne pas imiter un personnage qu'ils ne connaissent pas."""
    source, chemin = _source(os.path.join("shared", "anti_tic.py"))
    arbre = ast.parse(source, filename=chemin)

    # Seules les CHAÎNES comptent : le docstring explique justement pourquoi le nom est
    # banni, il a le droit de le prononcer. On inspecte donc le corps de la fonction.
    fonction = next(n for n in ast.walk(arbre)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "build_anti_tic_consigne")
    litteraux = [n.value for n in ast.walk(fonction)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    corps = " ".join(litteraux[1:] if litteraux else [])  # [0] = le docstring

    for nom in ("Haskill", "Sheogorath", "Sheo", "Alfred", "M'aiq", "Maiq",
                "Johnny", "Malena", "Sugar", "Batman"):
        assert nom.lower() not in corps.lower(), (
            f"« {nom} » est écrit en dur dans la consigne partagée : les cinq autres "
            f"bots recevraient l'ordre de ne pas recycler un tic qui n'est pas le leur. "
            f"Un appelant qui a un tic nommé le passe par `exemple_cloture`."
        )


def test_le_tic_nomme_passe_par_le_parametre():
    sans = build_anti_tic_consigne(REPLIQUES)
    assert "CLÔTURÉ" in sans and "Haskill" not in sans

    avec = build_anti_tic_consigne(REPLIQUES, exemple_cloture="Haskill, note ça")
    assert "Haskill, note ça" in avec


def test_sheo_garde_sa_cloture_nommee():
    """Le filet est mutualisé, mais Sheo ne doit RIEN perdre : « Haskill, note ça »
    tenait 7 de ses 8 répliques le 07/09, c'est son tic le plus cher."""
    sys.path.insert(0, os.path.join(RACINE, "Sheogorath"))
    try:
        from sheo_llm import build_anti_tic_consigne as sheo_anti_tic
    finally:
        sys.path.pop(0)
    assert "Haskill, note ça" in sheo_anti_tic(REPLIQUES)


# ─────────────────────────── 2. le séparateur Twitch ───────────────────────────────────


def test_la_consigne_twitch_se_detache_du_bloc_precedent():
    """⚠️ L'appelant fait `system_prompt += anti_tic`, sans séparateur : le `\\n\\n` est
    la seule chose qui empêche « …toi tu pars ailleurs.[ANTI-TICS… »."""
    from shared.twitch.llm import _build_anti_tic_consigne

    consigne = _build_anti_tic_consigne(REPLIQUES)
    assert consigne, "le filet Twitch ne rend plus rien"
    assert consigne.startswith("\n\n"), repr(consigne[:40])
    assert _build_anti_tic_consigne([]) == "", "le vide doit rester vide, pas « \\n\\n »"


# ─────────────────────────── 3. le vendoring ───────────────────────────────────────────


def test_anti_tic_est_dans_les_deux_listes_de_vendoring():
    """⚠️ DEUX listes : `vendor_core.py` COPIE, `sonde_core_drift.py` SURVEILLE.
    Absent de la première, un bot déployé seul perd le filet en silence ; absent de la
    seconde, la copie peut diverger sans que rien ne le dise."""
    for outil in ("vendor_core.py", "sonde_core_drift.py"):
        source, _ = _source(os.path.join("tools", outil))
        assert '"anti_tic.py"' in source, f"anti_tic.py absent de tools/{outil}"


@pytest.mark.parametrize("bot", ["Alfred", "JohnnyBot", "MaiqBot",
                                 "MalenaBot", "Sheogorath", "SugarBot"])
def test_chaque_bot_a_sa_copie_vendorisee(bot):
    assert os.path.exists(os.path.join(RACINE, bot, "core", "anti_tic.py")), (
        f"{bot} n'a pas sa copie : `python tools/vendor_core.py`")


# ─────────────────────────── 4. le câblage des six ─────────────────────────────────────


@pytest.mark.parametrize("nom,fichier,variable", BOTS, ids=[b[0] for b in BOTS])
def test_le_filet_est_appele_ET_injecte_dans_le_prompt(nom, fichier, variable):
    """⚠️ Un test qui cherche le NOM du helper passerait au vert sur un simple import.
    On exige les trois : l'import, l'APPEL avec `message_utilisateur`, et la variable
    RÉELLEMENT interpolée dans un f-string de prompt."""
    source, chemin = _source(fichier)
    arbre = ast.parse(source, filename=chemin)

    importe = any(
        isinstance(n, ast.ImportFrom)
        and n.module in ("core.anti_tic", "shared.anti_tic", "sheo_llm",
                         "Sheogorath.sheo_llm")
        and any(a.name == "build_anti_tic_consigne" for a in n.names)
        for n in ast.walk(arbre))
    assert importe, f"{nom} n'importe pas build_anti_tic_consigne"

    appels = [n for n in ast.walk(arbre)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name)
              and n.func.id == "build_anti_tic_consigne"]
    assert appels, f"{nom} importe le filet mais ne l'appelle jamais"
    for appel in appels:
        assert "message_utilisateur" in {k.arg for k in appel.keywords}, (
            f"{nom} ne transmet pas le message de l'utilisateur : le filet interdirait "
            f"alors le SUJET de la conversation, pas seulement la rengaine.")

    # La consigne doit être CONSOMMÉE : une variable calculée puis oubliée est le défaut
    # exact que ce fichier verrouille. On n'impose pas la forme (f-string chez cinq bots,
    # `+=` chez Sheo, passage en argument chez Malena), seulement la relecture.
    relue = any(isinstance(n, ast.Name) and n.id == variable
                and isinstance(n.ctx, ast.Load)
                for n in ast.walk(arbre))
    assert relue, (
        f"{nom} calcule la consigne dans `{variable}` et ne la relit jamais : "
        f"elle n'atteint aucun prompt")
