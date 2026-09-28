# -*- coding: utf-8 -*-
"""Garde commun des sondes : ne pas bruler le quota d'un bot qui sert en ce moment.

POURQUOI (mesure du 2026-09-28, `data/api_usage.db`, 25 → 28/09) :
Les sondes tournent sur les CLES DES BOTS (une cle par bot, jamais partagee). Elles ont
consomme 10 a 20 fois la prod : Sugar 943 appels de sonde pour 42 de prod, Johnny 336
pour 9. Une passe lancee pendant un live prend le quota que le chat attendait, et le bot
devient muet sans que rien ne dise pourquoi (cf. gotcha « la passe degrade l'echelon »).

TROIS REFUS, dans cet ordre (`--forcer` les leve tous, avec un avertissement) :
1. le bot a servi de VRAIS messages (origine `prod`) dans les 30 dernieres minutes :
   il est en conversation ou en live ;
2. le bot a pris un 429 (toutes origines) dans les 15 dernieres minutes ;
3. le budget de sonde du JOUR (UTC) serait depasse : appels de sonde deja faits
   aujourd'hui + appels prevus > `SONDE_BUDGET_JOUR` (300 par defaut).

La base est ouverte en LECTURE SEULE (`mode=ro`) : ce garde n'ecrit rien et ne change
jamais le mode de journal (WAL interdit, cf. AGENTS.md). Base absente = pas de mesure
possible : on laisse passer, en le disant.
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
BUDGET_JOUR_DEFAUT = 300
FENETRE_PROD_MIN = 30
FENETRE_429_MIN = 15

# Le nom d'une sonde (`--bot`) n'est pas toujours celui de `api_calls.bot_name`.
_NOM_EN_BASE = {"sheogorath": "sheo"}


def _chemin_base():
    data_dir = os.getenv("DATA_DIR", str(RACINE / "data"))
    return Path(data_dir) / "api_usage.db"


def _horodatage(dt):
    """Meme format que `api_tracking._maintenant_utc()` : ISO **UTC** sans fuseau, 'T'.

    ⚠️ Verifie en base le 29/09 (`2026-09-28T23:29:51.610027`) : comparer a une heure
    LOCALE decalerait toutes les fenetres de 2 h (cf. gotcha « les fenetres de temps du
    dashboard mentent »).
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def mesurer(bot, maintenant=None, chemin=None):
    """Rend (prod_recente, n_429_recents, sondes_du_jour) pour ce bot, ou None sans base."""
    chemin = Path(chemin) if chemin else _chemin_base()
    if not chemin.exists():
        return None
    nom = _NOM_EN_BASE.get(bot, bot)
    maintenant = maintenant or datetime.now(timezone.utc).replace(tzinfo=None)
    debut_jour = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    con = sqlite3.connect(f"file:{chemin.as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        prod = con.execute(
            "SELECT COUNT(*) FROM api_calls WHERE bot_name = ? AND origine = 'prod' AND timestamp >= ?",
            (nom, _horodatage(maintenant - timedelta(minutes=FENETRE_PROD_MIN)))).fetchone()[0]
        n429 = con.execute(
            "SELECT COUNT(*) FROM api_calls WHERE bot_name = ? AND error_code = 429 AND timestamp >= ?",
            (nom, _horodatage(maintenant - timedelta(minutes=FENETRE_429_MIN)))).fetchone()[0]
        sondes = con.execute(
            "SELECT COUNT(*) FROM api_calls WHERE bot_name = ? AND origine = 'sonde' AND timestamp >= ?",
            (nom, _horodatage(debut_jour))).fetchone()[0]
    finally:
        con.close()
    return prod, n429, sondes


def verifier(bot, appels_prevus, forcer=False, chemin=None, maintenant=None):
    """Rend (autorise, message). Le message est a imprimer tel quel par la sonde.

    `maintenant` : datetime UTC naif (tests) ; par defaut l'heure UTC courante.
    """
    mesure = mesurer(bot, maintenant=maintenant, chemin=chemin)
    if mesure is None:
        return True, "[garde] api_usage.db introuvable : aucune mesure, la sonde passe."
    prod, n429, sondes = mesure
    budget = int(os.getenv("SONDE_BUDGET_JOUR", BUDGET_JOUR_DEFAUT))

    refus = []
    if prod:
        refus.append(f"{bot} a servi {prod} vrai(s) message(s) dans les {FENETRE_PROD_MIN} "
                     f"dernieres minutes : il est en conversation ou en live")
    if n429:
        refus.append(f"{bot} a pris {n429} erreur(s) 429 dans les {FENETRE_429_MIN} dernieres minutes")
    if sondes + appels_prevus > budget:
        refus.append(f"budget de sonde du jour depasse : {sondes} deja faits + {appels_prevus} "
                     f"prevus > {budget} (SONDE_BUDGET_JOUR)")

    if not refus:
        return True, (f"[garde] {bot} : 0 message servi en {FENETRE_PROD_MIN} min, 0 429, "
                      f"{sondes}+{appels_prevus}/{budget} appels de sonde aujourd'hui.")
    detail = " ; ".join(refus)
    if forcer:
        return True, f"[garde] ⚠️ FORCE malgre : {detail}"
    return False, f"[garde] REFUS : {detail}. Relancer plus tard, ou --forcer en connaissance de cause."
