# -*- coding: utf-8 -*-
"""Sauvegarde hebdomadaire des cles de chiffrement et fichiers .env.encrypted hors du depot.

POURQUOI CET OUTIL EXISTE (constat du 2026-09-28) :
---------------------------------------------------
Aujourd'hui, les cles API et tokens Discord des six bots n'existent QUE sur le disque I: :
<Bot>/.env.encrypted + <Bot>/.master_key, plus dashboard/.env.
GitHub ne les a pas, et c'est voulu (securite).
Perdre le disque I: obligerait a regenerer toutes les cles chez chaque fournisseur,
pour les six bots et le dashboard.

CE QU'IL SAUVEGARDE (13 fichiers en dur, aucun glob) :
------------------------------------------------------
- Alfred/.env.encrypted et Alfred/.master_key
- Sheogorath/.env.encrypted et Sheogorath/.master_key
- MaiqBot/.env.encrypted et MaiqBot/.master_key
- JohnnyBot/.env.encrypted et JohnnyBot/.master_key
- SugarBot/.env.encrypted et SugarBot/.master_key
- MalenaBot/.env.encrypted et MalenaBot/.master_key
- dashboard/.env

REGLES DE SECURITE ABSOLUES :
-----------------------------
1. LECTURE SEULE sur la source : uniquement shutil.copy2.
2. REFUS CATEGORIQUE si --sortie se trouve a l'interieur du depot (evite tout risque
   d'embarquer des cles ou secrets dans git).
3. Confidentialite dans les logs : n'affiche JAMAIS le contenu d'un fichier ni son
   empreinte complete (seulement les 8 premiers caracteres du SHA-256).
4. Verifie la taille et le SHA-256 de chaque fichier apres copie.
5. Fichier absent sur la source : emis en avertissement (WARN), jamais ignore silencieusement.
6. Rotation : conserve les 8 sauvegardes completes les plus recentes (AAAA-MM-JJ).
"""

import argparse
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
import shutil
import sys
import time
from typing import List, Optional, Tuple

RACINE = Path(__file__).resolve().parent.parent

BOTS = ["Alfred", "Sheogorath", "MaiqBot", "JohnnyBot", "SugarBot", "MalenaBot"]

FICHIERS_CLES_RELATIFS = [
    f"{bot}/.env.encrypted" for bot in BOTS
] + [
    f"{bot}/.master_key" for bot in BOTS
] + [
    "dashboard/.env"
]

MOTIF_JOUR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MOTIF_JOUR_PARTIEL = re.compile(r"^\d{4}-\d{2}-\d{2}\.partiel$")

logger = logging.getLogger("sauvegarde_cles")


def configurer_journalisation(niveau: int = logging.INFO) -> None:
    """Configure la journalisation standard sur stdout."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [sauvegarde_cles] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
        root.setLevel(niveau)
    else:
        logger.setLevel(niveau)


def sha256_court(chemin: Path) -> str:
    """Calcule les 8 premiers caracteres de l'empreinte SHA-256 du fichier."""
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(65536), b""):
            h.update(bloc)
    return h.hexdigest()[:8]


def derniere_sauvegarde_datee(sortie: Path) -> Optional[Tuple[str, datetime]]:
    """Trouve la sauvegarde complete la plus recente et renvoie (nom, datetime_utc)."""
    if not sortie.exists():
        return None

    candidats = []
    for item in sortie.iterdir():
        if item.is_dir() and MOTIF_JOUR.match(item.name):
            try:
                dt = datetime.strptime(item.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                candidats.append((item.name, dt))
            except ValueError:
                continue

    if not candidats:
        return None

    candidats.sort(key=lambda x: x[1])
    return candidats[-1]


def executer_rotation(sortie: Path, retention: int = 8) -> None:
    """Conserve les `retention` sauvegardes completes les plus recentes et purge les .partiel anciens."""
    if not sortie.exists():
        return

    # 1. Sauvegardes completes
    dossiers_complets: List[Path] = []
    for item in sortie.iterdir():
        if item.is_dir() and MOTIF_JOUR.match(item.name):
            dossiers_complets.append(item)

    dossiers_complets.sort(key=lambda p: p.name)

    if len(dossiers_complets) > retention:
        a_supprimer = dossiers_complets[:-retention]
        for dossier in a_supprimer:
            logger.info("Rotation cles : suppression de l'ancienne sauvegarde %s", dossier.name)
            shutil.rmtree(dossier, ignore_errors=True)

    # 2. Nettoyage des dossiers .partiel abandonnes (> 24h)
    maintenant = time.time()
    for item in sortie.iterdir():
        if item.is_dir() and MOTIF_JOUR_PARTIEL.match(item.name):
            try:
                if maintenant - item.stat().st_mtime > 24 * 3600:
                    logger.warning("Suppression du dossier partiel orphelin (>24h) : %s", item.name)
                    shutil.rmtree(item, ignore_errors=True)
            except OSError as err:
                logger.error("Impossible de sonder/supprimer %s : %s", item.name, err)


def executer_sauvegarde_cles(
    racine: Path,
    sortie: Path,
    si_plus_vieux_que: float = 6.0,
    retention: int = 8,
) -> bool:
    """Copie securisee des cles hors du depot.
    
    Retourne True si une sauvegarde a ete realisee, False si recente.
    Leve une exception ou erreur critique en cas de violation.
    """
    racine_resolue = racine.resolve()
    sortie_resolue = sortie.resolve()

    # Interdiction formelle : --sortie ne doit JAMAIS etre dans le depot
    if sortie_resolue == racine_resolue or racine_resolue in sortie_resolue.parents:
        raise ValueError(
            f"REFUS ABSOLU : Le dossier de sortie ({sortie}) se trouve a l'interieur du depot ({racine}) !"
        )

    sortie.mkdir(parents=True, exist_ok=True)

    derniere = derniere_sauvegarde_datee(sortie)
    if derniere:
        nom_derniere, dt_derniere = derniere
        maintenant = datetime.now(timezone.utc)
        age_jours = (maintenant - dt_derniere).total_seconds() / 86400.0
        if age_jours < si_plus_vieux_que:
            logger.info(
                "Sauvegarde des cles recente (%s, age=%.1fj < seuil=%.1fj). Rien a faire.",
                nom_derniere,
                age_jours,
                si_plus_vieux_que,
            )
            executer_rotation(sortie, retention=retention)
            return False

    nom_dossier = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dossier_partiel = sortie / f"{nom_dossier}.partiel"
    dossier_final = sortie / nom_dossier

    if dossier_partiel.exists():
        shutil.rmtree(dossier_partiel, ignore_errors=True)
    dossier_partiel.mkdir(parents=True, exist_ok=True)

    nb_copies = 0
    nb_manquants = 0

    try:
        for rel_str in FICHIERS_CLES_RELATIFS:
            src_file = racine / rel_str
            if not src_file.exists():
                logger.warning("WARN : Fichier de cle introuvable sur la source : %s", rel_str)
                nb_manquants += 1
                continue

            if not src_file.is_file():
                logger.warning("WARN : L'element n'est pas un fichier : %s", rel_str)
                nb_manquants += 1
                continue

            dst_file = dossier_partiel / rel_str
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            # Copie lecture seule
            shutil.copy2(src_file, dst_file)

            # Verification taille et sha256 tronque
            src_stat = src_file.stat()
            dst_stat = dst_file.stat()

            if src_stat.st_size != dst_stat.st_size:
                raise RuntimeError(
                    f"Taille divergente apres copie de {rel_str} : {src_stat.st_size} != {dst_stat.st_size}"
                )

            src_hash = sha256_court(src_file)
            dst_hash = sha256_court(dst_file)

            if src_hash != dst_hash:
                raise RuntimeError(
                    f"Empreinte divergente apres copie de {rel_str} : {src_hash} != {dst_hash}"
                )

            logger.info(
                "Cle copiee et verifiee : %s (taille=%d o, sha256=%s...)",
                rel_str,
                dst_stat.st_size,
                dst_hash,
            )
            nb_copies += 1

        logger.info(
            "Copie terminee (%d fichiers copies, %d absents/avertissements). Finalisation...",
            nb_copies,
            nb_manquants,
        )

        if dossier_final.exists():
            shutil.rmtree(dossier_final, ignore_errors=True)
        dossier_partiel.rename(dossier_final)

    except Exception:
        logger.exception("Erreur durant la sauvegarde des cles. Nettoyage du partiel.")
        if dossier_partiel.exists():
            shutil.rmtree(dossier_partiel, ignore_errors=True)
        raise

    executer_rotation(sortie, retention=retention)
    logger.info("Sauvegarde des cles terminee avec succes dans %s", dossier_final)
    return True


def parser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sauvegarde verifiee des cles de chiffrement hors du disque du depot."
    )
    parser.add_argument(
        "--racine",
        type=Path,
        default=RACINE,
        help=f"Racine du depot (defaut: {RACINE})",
    )
    parser.add_argument(
        "--sortie",
        type=Path,
        required=True,
        help="Dossier de destination des cles (obligatoire, DOIT etre hors du depot)",
    )
    parser.add_argument(
        "--si-plus-vieux-que",
        type=float,
        default=6.0,
        metavar="JOURS",
        help="Ne sauvegarde que si la derniere sauvegarde date d'au moins JOURS (defaut: 6)",
    )
    parser.add_argument(
        "--retention",
        type=int,
        default=8,
        metavar="NB",
        help="Nombre de sauvegardes completes a conserver (defaut: 8)",
    )
    return parser.parse_args()


def main() -> int:
    configurer_journalisation()
    args = parser_arguments()

    logger.info("Demarrage sauvegarde_cles (racine=%s, sortie=%s)", args.racine, args.sortie)

    try:
        executer_sauvegarde_cles(
            racine=args.racine,
            sortie=args.sortie,
            si_plus_vieux_que=args.si_plus_vieux_que,
            retention=args.retention,
        )
        return 0
    except Exception as err:
        logger.error("Echec de la sauvegarde des cles : %s", err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
