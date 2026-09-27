# -*- coding: utf-8 -*-
"""Sauvegarde verifiee des bases SQLite et fichiers JSON hors du disque du projet.

POURQUOI CET OUTIL EXISTE (constat du 2026-09-28) :
---------------------------------------------------
La seule sauvegarde automatique du depot etait `daily_backup_check` dans Sheogorath,
qui appelait `backup_manager.py`. Elle ne produisait rien depuis des mois :
1. Boucle 24h avec condition sur heure fixe (ne declenchait que si le bot demarrait a 3h UTC).
2. Dossier cible /app/bot/backups dans un volume monte en LECTURE SEULE (:ro).
3. Ne visait que bots_database.db et ignorait decisions.db et api_usage.db.
Les seules sauvegardes existantes etaient 3 copies manuelles dans data/. Tout reposait
sur un seul fichier SQLite partage entre l'hote Windows et six conteneurs Linux.

CE QU'IL SAUVEGARDE :
---------------------
- Les bases de donnees SQLite actives (liste stricte en dur) :
  - data/bots_database.db
  - data/decisions.db
  - data/api_usage.db
  - data/dashboard_audit.db
- Tous les fichiers *.json du dossier donnees (memoires, faits, configurations, jetons Twitch).
- Exclut les vieilles copies (*backup*.db) et les journaux temporaires (*.db-journal).

COMMENT IL FONCTIONNE :
-----------------------
- Bases SQLite : copie exclusive via l'API sqlite3 `src.backup(dst)`. C'est la seule
  methode coherente et atomique pendant que les bots ecrivent.
  JAMAIS de shutil.copy sur une base active.
  NE JAMAIS executer PRAGMA journal_mode sur la source (shared_database.py pose TRUNCATE).
  Verification immediate sur la cible : PRAGMA integrity_check == 'ok' et
  PRAGMA journal_mode != 'wal'.
- Fichiers JSON : copie fidele via shutil.copy2.
- Dossier horodate : AAAA-MM-JJ_HHMM/ (UTC).
  Passe d'abord par un dossier temporaire AAAA-MM-JJ_HHMM.partiel/, renomme uniquement
  lorsque l'ensemble des copies et controles d'integrite sont valides.
- Rotation : conserve les 14 sauvegardes completes les plus recentes.
  Supprime les dossiers .partiel orphelins de plus de 24h.
  N'efface AUCUN autre dossier ou fichier que ceux correspondant aux motifs stricts.

COMMENT RESTAURER UNE SAUVEGARDE :
----------------------------------
1. ARRETER TOUS LES BOTS (docker compose down ou stop). Ne jamais ecraser une base active.
2. Choisir le dossier de sauvegarde desire : <sortie>/AAAA-MM-JJ_HHMM/
3. Copier le fichier restaure dans data/ (ex: cp bots_database.db /chemin/vers/data/)
4. Verifier les droits du fichier restaure.
5. Redemarrer les bots.
"""

import argparse
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time
from typing import List, Optional

RACINE = Path(__file__).resolve().parent.parent

BASES_SURVEILLEES = [
    "bots_database.db",
    "decisions.db",
    "api_usage.db",
    "dashboard_audit.db",
]

MOTIF_COMPLET = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}$")
MOTIF_PARTIEL = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}\.partiel$")

logger = logging.getLogger("sauvegarde_bases")


def configurer_journalisation(niveau: int = logging.INFO) -> None:
    """Configure la journalisation standard sur stdout."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [sauvegarde_bases] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
        root.setLevel(niveau)
    else:
        logger.setLevel(niveau)


def derniere_sauvegarde_datee(sortie: Path) -> Optional[tuple]:
    """Trouve la sauvegarde complete la plus recente et renvoie (nom, datetime_utc)."""
    if not sortie.exists():
        return None

    candidats = []
    for item in sortie.iterdir():
        if item.is_dir() and MOTIF_COMPLET.match(item.name):
            try:
                dt = datetime.strptime(item.name, "%Y-%m-%d_%H%M").replace(tzinfo=timezone.utc)
                candidats.append((item.name, dt))
            except ValueError:
                continue

    if not candidats:
        return None

    candidats.sort(key=lambda x: x[1])
    return candidats[-1]


def verifier_et_copier_base(src_path: Path, dst_path: Path) -> None:
    """Copie une base SQLite active via l'API backup et verifie son integrite sur la cible."""
    logger.info("Copie SQLite de %s vers %s ...", src_path.name, dst_path.name)
    src_conn = sqlite3.connect(str(src_path), timeout=30.0)
    try:
        dst_conn = sqlite3.connect(str(dst_path))
        try:
            # src.backup(dst) assure une copie coherente page par page sans verrouiller la source
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        # Aucune instruction PRAGMA n'est executee sur la source.
        src_conn.close()

    # Verification d'integrite et de mode de journal sur la cible uniquement
    check_conn = sqlite3.connect(str(dst_path))
    try:
        cur = check_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res or res[0] != "ok":
            raise RuntimeError(f"Controle d'integrite echoue sur {dst_path.name}: {res}")

        cur.execute("PRAGMA journal_mode;")
        mode_res = cur.fetchone()
        journal_mode = mode_res[0].lower() if mode_res else ""
        if journal_mode == "wal":
            raise RuntimeError(f"Base cible {dst_path.name} est en mode WAL (interdit) !")
    finally:
        check_conn.close()


def executer_rotation(sortie: Path, retention: int = 14) -> None:
    """Garde les `retention` sauvegardes completes les plus recentes et purge les .partiel anciens."""
    if not sortie.exists():
        return

    # 1. Sauvegardes completes
    dossiers_complets: List[Path] = []
    for item in sortie.iterdir():
        if item.is_dir() and MOTIF_COMPLET.match(item.name):
            dossiers_complets.append(item)

    # Tri lexicographique (ISO AAAA-MM-JJ_HHMM identique au tri chronologique)
    dossiers_complets.sort(key=lambda p: p.name)

    if len(dossiers_complets) > retention:
        a_supprimer = dossiers_complets[:-retention]
        for dossier in a_supprimer:
            logger.info("Rotation : suppression de l'ancienne sauvegarde %s", dossier.name)
            shutil.rmtree(dossier, ignore_errors=True)

    # 2. Nettoyage des dossiers .partiel abandonnes (> 24h)
    maintenant = time.time()
    for item in sortie.iterdir():
        if item.is_dir() and MOTIF_PARTIEL.match(item.name):
            try:
                age_secondes = maintenant - item.stat().st_mtime
                if age_secondes > 24 * 3600:
                    logger.warning(
                        "Suppression du dossier partiel orphelin (>24h) : %s",
                        item.name,
                    )
                    shutil.rmtree(item, ignore_errors=True)
            except OSError as err:
                logger.error("Impossible de sonder/supprimer %s : %s", item.name, err)


def executer_sauvegarde(
    donnees: Path,
    sortie: Path,
    si_plus_vieux_que: float = 20.0,
    retention: int = 14,
) -> bool:
    """Execute une passe de sauvegarde si necessaire.
    
    Retourne True si une sauvegarde a ete effectuee, False si recente ou ignoree.
    Leve une exception en cas d'echec critique.
    """
    if not donnees.exists() or not donnees.is_dir():
        raise FileNotFoundError(f"Dossier de donnees introuvable : {donnees}")

    sortie.mkdir(parents=True, exist_ok=True)

    # Verification de l'age de la derniere sauvegarde
    derniere = derniere_sauvegarde_datee(sortie)
    if derniere:
        nom_derniere, dt_derniere = derniere
        age_heures = (datetime.now(timezone.utc) - dt_derniere).total_seconds() / 3600.0
        if age_heures < si_plus_vieux_que:
            logger.info(
                "Sauvegarde recente trouvee (%s, age=%.1fh < seuil=%.1fh). Rien a faire.",
                nom_derniere,
                age_heures,
                si_plus_vieux_que,
            )
            executer_rotation(sortie, retention=retention)
            return False

    nom_dossier = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    dossier_partiel = sortie / f"{nom_dossier}.partiel"
    dossier_final = sortie / nom_dossier

    if dossier_partiel.exists():
        shutil.rmtree(dossier_partiel, ignore_errors=True)
    dossier_partiel.mkdir(parents=True, exist_ok=True)

    nb_bases_copiees = 0
    nb_json_copies = 0

    try:
        # 1. Copie des bases SQLite actives
        for nom_base in BASES_SURVEILLEES:
            src_base = donnees / nom_base
            if src_base.exists() and src_base.is_file():
                dst_base = dossier_partiel / nom_base
                verifier_et_copier_base(src_base, dst_base)
                nb_bases_copiees += 1
            else:
                logger.debug("Base non presente dans donnees : %s", nom_base)

        # 2. Copie des fichiers JSON
        for json_path in donnees.glob("*.json"):
            if json_path.is_file():
                dst_json = dossier_partiel / json_path.name
                shutil.copy2(json_path, dst_json)
                nb_json_copies += 1

        logger.info(
            "Copie temporaire terminee (%d bases, %d json). Renommage atomique vers %s",
            nb_bases_copiees,
            nb_json_copies,
            dossier_final.name,
        )

        # 3. Renommage atomique .partiel -> final
        if dossier_final.exists():
            shutil.rmtree(dossier_final, ignore_errors=True)
        dossier_partiel.rename(dossier_final)

    except Exception:
        logger.exception("Echec durant la sauvegarde. Nettoyage du dossier partiel.")
        if dossier_partiel.exists():
            shutil.rmtree(dossier_partiel, ignore_errors=True)
        raise

    # 4. Rotation apres creation reussie
    executer_rotation(sortie, retention=retention)
    logger.info("Sauvegarde terminee avec succes dans %s", dossier_final)
    return True


def parser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sauvegarde verifiee des bases SQLite et fichiers JSON de data/."
    )
    defaut_donnees = os.environ.get("DATA_DIR")
    if not defaut_donnees:
        defaut_donnees = str(RACINE / "data")

    parser.add_argument(
        "--donnees",
        type=Path,
        default=Path(defaut_donnees),
        help=f"Dossier source des bases et json (defaut: {defaut_donnees})",
    )
    parser.add_argument(
        "--sortie",
        type=Path,
        required=True,
        help="Dossier de destination des sauvegardes (obligatoire, hors du disque du projet)",
    )
    parser.add_argument(
        "--si-plus-vieux-que",
        type=float,
        default=20.0,
        metavar="HEURES",
        help="Ne sauvegarde que si la derniere sauvegarde date d'au moins HEURES (defaut: 20)",
    )
    parser.add_argument(
        "--retention",
        type=int,
        default=14,
        metavar="NB",
        help="Nombre de sauvegardes completes a conserver (defaut: 14)",
    )
    parser.add_argument(
        "--boucle",
        action="store_true",
        help="Mode daemon : s'execute en boucle avec une pause d'une heure entre chaque verification",
    )
    return parser.parse_args()


def main() -> int:
    configurer_journalisation()
    args = parser_arguments()

    logger.info("Demarrage sauvegarde_bases (donnees=%s, sortie=%s)", args.donnees, args.sortie)

    if args.boucle:
        logger.info("Mode boucle active (pause de 3600s entre chaque verification).")
        while True:
            try:
                executer_sauvegarde(
                    donnees=args.donnees,
                    sortie=args.sortie,
                    si_plus_vieux_que=args.si_plus_vieux_que,
                    retention=args.retention,
                )
            except Exception as err:
                logger.error("Erreur durant l'iteration de sauvegarde : %s", err)

            time.sleep(3600)
    else:
        try:
            executer_sauvegarde(
                donnees=args.donnees,
                sortie=args.sortie,
                si_plus_vieux_que=args.si_plus_vieux_que,
                retention=args.retention,
            )
            return 0
        except Exception as err:
            logger.error("Echec de la sauvegarde : %s", err)
            return 1


if __name__ == "__main__":
    sys.exit(main())
