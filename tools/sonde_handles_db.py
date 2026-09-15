# -*- coding: utf-8 -*-
"""Sonde : un bot retient-il des handles sur bots_database.db ?

Le 2026-09-13, `bot-maiq` gardait **15** descripteurs ouverts sur `bots_database.db`
quand les cinq autres en avaient 2. Le correctif (`7f14ca4`, toutes les connexions sous
`with connexion()`) demandait une verification EMPIRIQUE : relever le compte apres 24 h
d'uptime.

⚠️ **Cette mesure a ete perdue deux fois** — les 14 et 15/09 — parce qu'elle dependait
d'un INSTANT : l'hote s'eteint la nuit, l'uptime repart de zero, et il n'y a plus rien a
relever. Un releve a faible uptime, lui, ne tranche rien : le 15 de M'aiq s'etait
construit sur des JOURS, et a 40 min les six donnaient 1 partout.

D'ou cette sonde. Elle ne cherche pas l'instant des 24 h : elle ecrit une LIGNE par
passage, avec l'uptime en face du compte. Une serie de couples (uptime, handles) dit ce
qu'un releve isole ne peut pas dire — si le compte de M'aiq monte avec l'uptime quand
les cinq autres restent plats, la retention est la ; s'il reste plat comme les autres a
uptime comparable, elle est fermee. Et un redemarrage ne detruit plus la mesure : il
ouvre juste une nouvelle serie.

    python tools/sonde_handles_db.py            # un releve, affiche + ajoute a l'historique
    python tools/sonde_handles_db.py --histoire # relit l'historique, groupe par bot
    python tools/sonde_handles_db.py --strict   # code 1 si un bot depasse le SEUIL

L'historique vit dans `logs/handles_db.csv` (repertoire deja ignore par git).
"""
import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime, timezone

BOTS = ["alfred", "sugar", "johnny", "malena", "maiq", "sheogorath"]

# Au-dela, c'est une retention : les six tournaient a 1 ou 2 quand tout allait bien.
SEUIL = 4

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORIQUE = os.path.join(RACINE, "logs", "handles_db.csv")

# ⚠️ Compter les descripteurs DANS le conteneur, jamais depuis l'hote : le fichier est
# bind-monte, l'hote ne voit pas quel processus Linux le tient ouvert.
_COMPTE = (
    "for f in /proc/[0-9]*/fd/*; do readlink \"$f\"; done 2>/dev/null "
    "| grep -c bots_database.db"
)


def _docker(args):
    return subprocess.run(
        ["docker"] + args, capture_output=True, text=True, timeout=60
    )


def releve():
    """Rend [(bot, uptime_secondes, handles, erreur)] pour les 6 bots."""
    maintenant = datetime.now(timezone.utc)
    lignes = []
    for bot in BOTS:
        conteneur = f"bot-{bot}"
        demarre = _docker(["inspect", conteneur, "--format", "{{.State.StartedAt}}"])
        if demarre.returncode != 0:
            lignes.append((bot, None, None, "conteneur absent ou docker eteint"))
            continue
        horodatage = demarre.stdout.strip()
        try:
            # Docker rend des nanosecondes : `fromisoformat` s'arrete a 6 chiffres.
            base, _, reste = horodatage.partition(".")
            micro = (reste.rstrip("Z") + "000000")[:6]
            depart = datetime.fromisoformat(f"{base}.{micro}+00:00")
            uptime = int((maintenant - depart).total_seconds())
        except ValueError:
            uptime = None

        compte = _docker(["exec", conteneur, "sh", "-c", _COMPTE])
        sortie = compte.stdout.strip()
        if not sortie.isdigit():
            lignes.append((bot, uptime, None, sortie or compte.stderr.strip()[:60]))
            continue
        lignes.append((bot, uptime, int(sortie), None))
    return maintenant, lignes


def _duree(secondes):
    if secondes is None:
        return "?"
    heures, reste = divmod(secondes, 3600)
    return f"{heures}h{reste // 60:02d}"


def ajoute_a_l_historique(horodatage, lignes):
    os.makedirs(os.path.dirname(HISTORIQUE), exist_ok=True)
    neuf = not os.path.exists(HISTORIQUE)
    with open(HISTORIQUE, "a", newline="", encoding="utf-8") as f:
        ecrivain = csv.writer(f)
        if neuf:
            ecrivain.writerow(["horodatage_utc", "bot", "uptime_s", "handles", "erreur"])
        for bot, uptime, handles, erreur in lignes:
            ecrivain.writerow([
                horodatage.strftime("%Y-%m-%dT%H:%M:%SZ"), bot,
                "" if uptime is None else uptime,
                "" if handles is None else handles,
                erreur or "",
            ])


def montre_l_historique():
    if not os.path.exists(HISTORIQUE):
        print("Aucun historique — lance la sonde une premiere fois.")
        return
    par_bot = {}
    with open(HISTORIQUE, encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            if not ligne["handles"]:
                continue
            par_bot.setdefault(ligne["bot"], []).append(
                (int(ligne["uptime_s"] or 0), int(ligne["handles"]), ligne["horodatage_utc"])
            )
    for bot in BOTS:
        mesures = sorted(par_bot.get(bot, []))
        if not mesures:
            continue
        serie = "  ".join(f"{_duree(u)}->{h}" for u, h, _ in mesures)
        print(f"{bot:<12} {serie}")
    print(
        "\nLire ainsi : le compte doit rester PLAT quand l'uptime monte. "
        "Un bot dont la serie croit avec l'uptime retient des connexions."
    )


def main():
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--histoire", action="store_true",
                         help="relit l'historique au lieu de mesurer")
    parseur.add_argument("--strict", action="store_true",
                         help=f"code de sortie 1 si un bot depasse {SEUIL} handles")
    options = parseur.parse_args()

    if options.histoire:
        montre_l_historique()
        return 0

    horodatage, lignes = releve()
    if all(erreur for _, _, _, erreur in lignes):
        print("Docker ne repond pas — aucun releve.", file=sys.stderr)
        return 2

    ajoute_a_l_historique(horodatage, lignes)
    print(f"Releve du {horodatage.strftime('%Y-%m-%d %H:%M:%SZ')} :\n")
    depassements = []
    for bot, uptime, handles, erreur in lignes:
        if erreur:
            print(f"  {bot:<12} {'?':>4}   ({_duree(uptime)})   {erreur}")
            continue
        alerte = "  <-- RETENTION ?" if handles > SEUIL else ""
        if handles > SEUIL:
            depassements.append(bot)
        print(f"  {bot:<12} {handles:>4} handles   apres {_duree(uptime)} d'uptime{alerte}")
    print(f"\nHistorique : {os.path.relpath(HISTORIQUE, RACINE)} "
          f"(`--histoire` pour la serie complete)")

    if depassements and options.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
