# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/boucles.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

# -*- coding: utf-8 -*-
"""Empeche `discord.ext.tasks` de rejouer toutes les iterations manquees.

## Le defaut

`tasks.loop(minutes=5)` ne dort pas « 5 minutes » : il dort **jusqu'a un instant absolu**,
calcule a partir de l'iteration PRECEDENTE (`_get_next_sleep_time` rend
`_last_iteration + intervalle`). Quand l'horloge saute — l'hote Windows se met en veille,
le conteneur gele — cet instant est deja passe au reveil. La boucle s'execute, recalcule
`precedent + intervalle`, trouve un instant **encore** passe, et recommence : elle rejoue
**toutes** les iterations manquees, dos a dos, en quelques millisecondes.

⚠️ La correction de derive d'horloge que discord.py embarque ne s'applique **qu'aux
boucles a heure explicite** (`time=`) : `while self._is_explicit_time() and ...`. Les
boucles a intervalle relatif, c'est-a-dire **toutes les notres**, n'ont aucun filet.

## Ce que ca a coute

Journal de `bot-sheogorath`, 2026-09-04 : trou de 3 h 21 sans une seule ligne
(07:56 → 11:17, hote en veille), reconnexion de la gateway, puis **40 `MOOD CHANGE` en
deux secondes** — exactement 3 h 20 / 5 min. Mesure de reproduction : un saut de 10
minutes sur une boucle de 5 s produit **120 rattrapages en 7 ms**.

Le changement d'humeur n'etait que la partie visible, parce qu'il est le seul a
journaliser chaque tour. Pour une veille nocturne de 8 h, les memes secondes rejouent
`twitch_poll_loop` (90 s) **320 fois par bot**, `vocal_patrol_loop` (30 s) 960 fois,
`check_missed_mentions` (2 min) 240 fois — dont de vrais appels a l'API Twitch.

## La correction

On ne touche pas aux 30 boucles une par une : on corrige le calcul, une fois, pour
toutes les boucles du processus — y compris celles de `shared/twitch/` et celles qui
seront ecrites demain. Si l'instant calcule est deja passe, on repart de **maintenant**
au lieu de rejouer le retard.

⚠️ Effet de bord assume : si un corps de boucle dure plus longtemps que son propre
intervalle, l'iteration suivante attend un intervalle complet au lieu de partir
immediatement. C'est le comportement souhaitable — sans quoi la boucle s'empile sur
elle-meme.
"""
import datetime
import logging

logger = logging.getLogger("boucles")


def installer_anti_rattrapage(journal=None):
    """Corrige `tasks.Loop` pour tout le processus. Idempotent.

    Rend True si la correction vient d'etre posee, False si elle l'etait deja.
    Rend False aussi si `discord.ext.tasks` n'est pas installe — le bot doit
    demarrer quand meme.
    """
    journal = journal or logger
    try:
        from discord.ext.tasks import Loop
    except ImportError as e:
        journal.warning(f"[BOUCLES] discord.ext.tasks introuvable, anti-rattrapage non pose : {e}")
        return False

    if getattr(Loop._get_next_sleep_time, "_anti_rattrapage", False):
        return False

    origine = Loop._get_next_sleep_time

    def _get_next_sleep_time(self, *args, **kwargs):
        prochain = origine(self, *args, **kwargs)
        # `_is_relative_time()` = pas de `time=` explicite, donc un intervalle. Les
        # boucles a heure fixe ont deja leur propre correction dans discord.py.
        if not self._is_relative_time():
            return prochain
        maintenant = datetime.datetime.now(datetime.timezone.utc)
        if prochain >= maintenant:
            return prochain
        retard = (maintenant - prochain).total_seconds()
        journal.info(
            f"[BOUCLES] {self.coro.__qualname__} : {retard:.0f} s de retard "
            f"(veille de l'hote ?), rattrapage abandonne, reprise du rythme normal"
        )
        return maintenant + datetime.timedelta(seconds=self._sleep)

    _get_next_sleep_time._anti_rattrapage = True
    Loop._get_next_sleep_time = _get_next_sleep_time
    # Un correctif qu'aucun journal ne montre est un correctif qu'on ne peut pas valider
    # en live ([[gotcha-echelon-de-secours-invisible]]) : il ne se manifeste sinon qu'au
    # premier reveil de la machine, c'est-a-dire jamais quand on regarde.
    journal.info("[BOUCLES] anti-rattrapage pose : les iterations manquees ne seront pas rejouees")
    return True
