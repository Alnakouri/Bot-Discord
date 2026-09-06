# -*- coding: utf-8 -*-
"""Un `tasks.loop` ne doit pas rejouer les iterations manquees apres une veille.

`tasks.loop(minutes=5)` dort jusqu'a un instant **absolu**, calcule depuis l'iteration
precedente. Quand l'hote se met en veille, cet instant est deja passe au reveil : la
boucle s'execute, recalcule `precedent + intervalle`, retombe sur un instant encore passe,
et recommence — elle rejoue **tout** le retard, dos a dos.

Constate le **2026-09-04** dans le journal de `bot-sheogorath` : trou de 3 h 21 sans une
seule ligne (hote en veille), reconnexion de la gateway, puis **40 `MOOD CHANGE` en deux
secondes**. Le changement d'humeur etait seulement le plus visible : il est le seul a
journaliser chaque tour. Les memes secondes rejouaient `twitch_poll_loop` (90 s) et
`vocal_patrol_loop` (30 s), qui appellent de vraies API.

⚠️ Le premier test verifie que **le defaut existe toujours** dans la version installee de
discord.py. Sans lui, une correction en amont rendrait le second test vert sans que rien
ne protege plus — et personne ne le saurait.
"""
import asyncio
import datetime
import io
import time

from pathlib import Path

import pytest

from discord.ext import tasks

from shared.boucles import installer_anti_rattrapage

RACINE = Path(__file__).resolve().parent.parent

BOTS = [
    "Alfred/bot_alfred.py",
    "JohnnyBot/bot_johnny.py",
    "MaiqBot/bot_maiq.py",
    "MalenaBot/bot_malena.py",
    "Sheogorath/bot_sheogorath.py",
    "SugarBot/bot_sugar.py",
]

INTERVALLE = 5
SAUT_MINUTES = 10
# 10 min / 5 s = 120 iterations manquees.
RATTRAPAGES_ATTENDUS = SAUT_MINUTES * 60 // INTERVALLE


@pytest.fixture(autouse=True)
def _restaurer_discord():
    """Le correctif remplace une methode de classe : la rendre a l'etat trouve."""
    origine = tasks.Loop._get_next_sleep_time
    yield
    tasks.Loop._get_next_sleep_time = origine


def _rafale():
    """Fait sauter l'horloge de 10 min sous une boucle de 5 s, rend les instants d'appel."""
    appels = []

    @tasks.loop(seconds=INTERVALLE)
    async def boucle():
        appels.append(time.time())

    async def scenario():
        boucle.start()
        await asyncio.sleep(0.2)          # laisse passer la premiere iteration
        saut = datetime.timedelta(minutes=SAUT_MINUTES)
        boucle._last_iteration -= saut
        boucle._next_iteration = boucle._last_iteration + datetime.timedelta(seconds=INTERVALLE)
        boucle._handle.recalculate(boucle._next_iteration)
        await asyncio.sleep(0.5)
        boucle.cancel()

    asyncio.run(scenario())
    return appels


def test_le_defaut_de_discord_py_est_toujours_la():
    """Sans le correctif, la boucle rejoue tout le retard. Temoin."""
    appels = _rafale()
    assert len(appels) > RATTRAPAGES_ATTENDUS * 0.8, (
        "discord.py ne rejoue plus les iterations manquees : le defaut a peut-etre ete "
        "corrige en amont. Verifier avant de retirer shared/boucles.py. (%d appels)"
        % len(appels)
    )


def test_le_correctif_supprime_le_rattrapage():
    assert installer_anti_rattrapage() is True
    appels = _rafale()
    # 1 iteration au demarrage + 1 seule au reveil, puis retour au rythme normal.
    assert len(appels) <= 3, (
        "le rattrapage n'a pas ete supprime : %d appels au lieu de 2" % len(appels)
    )
    assert len(appels) >= 2, "la boucle ne tourne plus du tout : %d appel(s)" % len(appels)


def test_la_pose_est_idempotente():
    assert installer_anti_rattrapage() is True
    assert installer_anti_rattrapage() is False, (
        "une 2e pose empilerait un enrobage sur l'autre — on_ready rejoue a chaque "
        "reconnexion, ca finirait en pile"
    )


class _JournalMuet:
    """Retient les lignes info sans rien ecrire nulle part."""

    def __init__(self):
        self.info_dits = []

    def info(self, message):
        self.info_dits.append(message)

    def warning(self, message):
        pass


def test_la_pose_se_voit_dans_le_journal():
    """Un correctif qui ne se manifeste qu'au reveil de la machine est invisible.

    La ligne de rattrapage, elle, n'apparait qu'apres une vraie veille : impossible de
    verifier en live que le filet est en place. La pose, elle, se dit au demarrage.
    """
    journal = _JournalMuet()
    assert installer_anti_rattrapage(journal) is True
    assert any("anti-rattrapage" in ligne for ligne in journal.info_dits), (
        "la pose ne dit rien : rien ne permet de constater dans le journal d'un bot "
        "que le filet est en place. Lignes vues : %r" % journal.info_dits
    )


def test_une_pose_deja_faite_ne_redit_rien():
    """on_ready rejoue a chaque reconnexion : la 2e pose ne doit pas polluer le journal."""
    assert installer_anti_rattrapage() is True
    journal = _JournalMuet()
    assert installer_anti_rattrapage(journal) is False
    assert journal.info_dits == [], (
        "la 2e pose parle alors qu'elle n'a rien fait : %r" % journal.info_dits
    )


@pytest.mark.parametrize("chemin", BOTS)
def test_chaque_bot_pose_le_correctif(chemin):
    """L'import ne suffit pas : un helper importe mais jamais appele ne protege rien."""
    src = io.open(RACINE / chemin, encoding="utf-8").read()
    assert "from core.boucles import installer_anti_rattrapage" in src, (
        "%s n'importe pas le correctif" % chemin
    )
    assert "installer_anti_rattrapage(logger)" in src, (
        "%s importe le correctif mais ne l'appelle jamais" % chemin
    )
