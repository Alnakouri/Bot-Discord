# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/chrono.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

"""Chronometre le temps REELLEMENT percu par l'utilisateur : message recu -> reponse postee.

⚠️ `api_calls.latency_ms` ne mesure qu'un appel de modele. Entre le message et la reponse
il y a aussi la lecture de l'historique Discord, le telechargement d'un media, le montage
du prompt, le post-traitement et l'envoi — et surtout **la somme des echelons rates**.

Motif : le 2026-09-04, entre `[ROUTER]` et la reponse de Sheogorath, les logs montraient
**douze secondes sans une seule ligne**. Rien ne disait ou elles etaient passees.

⚠️ Base sur `time.perf_counter()`, JAMAIS `datetime.now()` : l'horloge des conteneurs
derive de 2 h par rapport a Discord, et une horloge murale peut sauter (sortie de veille).
"""
import logging
import time

logger = logging.getLogger(__name__)

# ⚠️ Import NON indente, a la ligne : `tools/vendor_core.py` ne reecrit `shared.` en
# `core.` qu'en debut de ligne (`^from shared\.`). Indente dans un try/except, il restait
# `from shared.api_tracking` dans les 6 copies vendorisees — donc un ImportError silencieux
# en conteneur, et la mesure perdue sans que personne le voie.
from core.api_tracking import tracer_reponse


class Chrono:
    """Un chronometre par reponse. Ne leve jamais : un bot muet vaut pire qu'une mesure perdue."""

    def __init__(self, bot, canal=None):
        self.bot = bot
        self.canal = str(canal) if canal is not None else None
        self._debut = time.perf_counter()
        self._dernier = self._debut
        self.etapes = {}
        self._fini = False

    def etape(self, nom):
        """Pose un jalon : le temps ecoule depuis le jalon precedent, en ms."""
        try:
            maintenant = time.perf_counter()
            self.etapes[nom] = int((maintenant - self._dernier) * 1000)
            self._dernier = maintenant
        except Exception:
            pass  # le chrono ne doit JAMAIS casser une reponse

    def fin(self, envoye=True):
        """Cloture, journalise et enregistre. Rend le total en ms (0.0 si quelque chose casse).

        ⚠️ A appeler AUSSI quand le bot renonce a repondre (`envoye=False`) : un abandon au
        bout de 15 s est precisement le cas qui ne laissait aucune trace.
        """
        try:
            if self._fini:
                return 0.0
            self._fini = True
            total = int((time.perf_counter() - self._debut) * 1000)
            detail = " | ".join(f"{nom} {ms}" for nom, ms in self.etapes.items())
            logger.info(
                f"⏱️ [CHRONO:{self.bot}] {total} ms"
                + (f" ({detail})" if detail else "")
                + ("" if envoye else " — SANS REPONSE")
            )
            tracer_reponse(
                bot=self.bot,
                total_ms=total,
                llm_ms=self.etapes.get("llm"),
                envoye=envoye,
                canal=self.canal,
            )
            return float(total)
        except Exception as e:  # pragma: no cover - garde de derniere ligne
            logger.warning(f"[CHRONO] mesure perdue : {e}")
            return 0.0
