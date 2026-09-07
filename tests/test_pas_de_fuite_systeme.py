# -*- coding: utf-8 -*-
"""Aucun bot ne parle de sa propre mecanique au salon.

Vu en test live le 2026-09-07, session 2 du protocole. `!decret`, l'interrupteur
bascule depuis le dashboard :

    🚫 Le Prince a suspendu ses décrets… pour l'instant. (désactivé via le dashboard)

Sheogorath ignore qu'il est un programme — c'est tout son personnage. La parenthese
revelait la mecanique a tout le salon, et n'apprenait rien a personne : l'admin qui a
coupe l'interrupteur le sait deja, et les autres ne peuvent rien en faire.

Le meme defaut vivait chez Malena, sur l'echec d'un appel LLM :

    Ay caramba ! J'ai mal à la tête, laissez-moi tranquille ! (Erreur API)

⚠️ La regle : ce qui explique une panne va dans le JOURNAL, jamais dans la replique.
Un utilisateur ne debugge pas, il discute.
"""
import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
BOTS = [
    "Alfred/bot_alfred.py",
    "JohnnyBot/bot_johnny.py",
    "MaiqBot/bot_maiq.py",
    "MalenaBot/bot_malena.py",
    "Sheogorath/bot_sheogorath.py",
    "SugarBot/bot_sugar.py",
]

# Ce qu'une replique ne doit jamais nommer. Volontairement court : chaque entree est un
# mot que le PERSONNAGE ne peut pas connaitre, pas un mot « technique » en general.
# « API » figure tel quel : c'est le sigle qui a fuite chez Malena.
_MOTS_INTERDITS = [
    "dashboard", "erreur api", "api error", "traceback", "exception",
    "timeout", "rate limit", "quota", "token", "webhook", "json",
    "désactivé via", "desactive via", "feature flag", "config",
]

# Les fonctions qui parlent AU SALON. `send`/`reply` couvrent tout : `Message.reply`
# est un raccourci vers `Messageable.send` (cf. shared/test_mode.py).
_SORTIES = {"send", "reply", "send_message", "respond"}


def _chaines_envoyees(arbre):
    """Les litteraux passes a un envoi Discord, avec leur ligne.

    Les f-strings comptent par leurs morceaux CONSTANTS : `f"...{e}"` fuite par son
    texte fixe, pas par sa variable.
    """
    trouvees = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call)
                and isinstance(noeud.func, ast.Attribute)
                and noeud.func.attr in _SORTIES):
            continue
        for argument in list(noeud.args) + [k.value for k in noeud.keywords
                                            if k.arg in (None, "content")]:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                trouvees.append((argument.lineno, argument.value))
            elif isinstance(argument, ast.JoinedStr):
                fixe = "".join(v.value for v in argument.values
                               if isinstance(v, ast.Constant) and isinstance(v.value, str))
                if fixe:
                    trouvees.append((argument.lineno, fixe))
    return trouvees


@pytest.mark.parametrize("chemin", BOTS)
def test_aucune_replique_ne_nomme_la_mecanique(chemin):
    """⚠️ « fait sur les 6 » l'est presque toujours sur 5 : on compte les six."""
    source = (RACINE / chemin).read_text(encoding="utf-8")
    arbre = ast.parse(source, filename=chemin)

    fuites = []
    for ligne, texte in _chaines_envoyees(arbre):
        bas = texte.lower()
        for mot in _MOTS_INTERDITS:
            if mot in bas:
                fuites.append(f"  {chemin}:{ligne} — « {mot} » dans : {texte[:90]}")

    assert not fuites, (
        "Des repliques nomment la mecanique du bot :\n" + "\n".join(fuites)
        + "\n\nCe qui explique une panne va dans le JOURNAL, jamais dans la replique."
    )


def test_le_refus_de_decret_reste_dans_la_voix_du_prince():
    """Le cas exact du 2026-09-07 : le refus existe toujours, et il est en personnage."""
    source = (RACINE / "Sheogorath" / "bot_sheogorath.py").read_text(encoding="utf-8")
    assert "SHEO_DECRETS_SUSPENDUS" in source, "le lot de refus a disparu"
    assert "désactivé via le dashboard" not in source

    arbre = ast.parse(source)
    lot = next((n for n in ast.walk(arbre)
                if isinstance(n, ast.Assign)
                and any(getattr(c, "id", None) == "SHEO_DECRETS_SUSPENDUS" for c in n.targets)),
               None)
    assert lot is not None and isinstance(lot.value, ast.List)
    refus = [e.value for e in lot.value.elts if isinstance(e, ast.Constant)]
    assert len(refus) >= 3, "un refus unique redevient un tic au bout de trois essais"
    for texte in refus:
        assert "dashboard" not in texte.lower()


def test_le_refus_est_journalise_pour_qui_lit_les_journaux():
    """Retirer l'explication de la replique ne doit pas la faire DISPARAITRE."""
    source = (RACINE / "Sheogorath" / "bot_sheogorath.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    commande = next(n for n in ast.walk(arbre)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == "decret_cmd")
    journaux = [n for n in ast.walk(commande)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("info", "warning")
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "logger"]
    assert journaux, (
        "Le refus ne laisse plus AUCUNE trace : ni au salon, ni au journal. "
        "Un admin qui a oublie l'interrupteur n'a plus rien pour comprendre."
    )
