# -*- coding: utf-8 -*-
"""Sauvegarde chiffree a deux cles sur Google Drive hors machine.

POURQUOI CET OUTIL EXISTE (constat du 2026-09-28) :
---------------------------------------------------
Depuis la SUITE 12, les sauvegardes des bases et des cles sont sur D: (autre disque physique que I:),
mais tout est dans le même PC : un vol, un incendie ou une surtension emporterait I: et D: ensemble.
Google Drive permet de conserver une copie hors site.

CHIFFREMENT ASYMETRIQUE A DEUX CLES :
-------------------------------------
Pour ne laisser aucun secret de dechiffrement sur le PC :
1. Une cle publique RSA 4096 bits (commitee dans le depot) permet a cet outil de chiffrer
   les archives sans aucune phrase de passe ni secret resident.
2. Une cle privee RSA 4096 bits, protegee par une phrase de passe forte, est conservee
   hors de la machine (cle USB / gestionnaire de mots de passe) par Ahmed. Elle seule dechiffre.

FORMAT D'ARCHIVE (.bdsv, chiffrement hybride) :
-----------------------------------------------
b"BDSV1\\n"                      6 octets, en-tete
longueur cle enveloppee          2 octets, big-endian
cle AES-256 enveloppee           RSA-OAEP (SHA256, MGF1-SHA256)
nonce                            12 octets
donnees chiffrees + tag AES-GCM  AES-256-GCM, AAD = b"BDSV1\\n"
"""

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import tarfile
import time
from typing import Callable, List, Optional, Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

RACINE = Path(__file__).resolve().parent.parent

MAGIC = b"BDSV1\n"
MOTIF_BASES = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{4}$")
MOTIF_CLES = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MOTIF_ARCHIVE = re.compile(r"^BotDiscord_\d{4}-\d{2}-\d{2}_\d{4}\.bdsv$")
MOTIF_ARCHIVE_PARTIEL = re.compile(r"^BotDiscord_\d{4}-\d{2}-\d{2}_\d{4}\.bdsv\.partiel$")

logger = logging.getLogger("sauvegarde_drive")


def configurer_journalisation(niveau: int = logging.INFO) -> None:
    """Configure la journalisation standard sur stdout."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [sauvegarde_drive] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
        root.setLevel(niveau)
    else:
        logger.setLevel(niveau)


def est_dans_depot(chemin: Path) -> bool:
    """Vrai si le chemin resolu se trouve a l'interieur du depot Git."""
    try:
        chemin.resolve().relative_to(RACINE.resolve())
        return True
    except (ValueError, RuntimeError):
        return False


def est_sous_drive(chemin: Path) -> bool:
    """Vrai si le chemin resolu se trouve sous le lecteur G: (Google Drive)."""
    try:
        resolved = str(chemin.resolve()).upper()
        return resolved.startswith("G:\\") or resolved.startswith("G:/")
    except Exception:
        return False


def empreinte_sha256_court(data: bytes) -> str:
    """Retourne les 16 premiers caracteres du SHA-256 des octets donnes."""
    return hashlib.sha256(data).hexdigest()[:16]


def generer_cles(
    cle_privee_path: Path,
    cle_publique_path: Path,
    taille_bits: int = 4096,
    prompt_fn: Optional[Callable[[str], str]] = None,
) -> int:
    """Mode --generer-cles : genere la paire RSA 4096 avec phrase de passe."""
    if prompt_fn is None:
        prompt_fn = getpass.getpass

    if est_dans_depot(cle_privee_path):
        logger.error("❌ Refus : la clé privée ne doit JAMAIS se trouver dans le dépôt.")
        return 1

    if est_sous_drive(cle_privee_path):
        logger.error("❌ Refus : la clé privée ne doit JAMAIS être stockée sur Google Drive.")
        return 1

    if cle_privee_path.exists():
        logger.error("❌ Refus : le fichier de clé privée existe déjà (%s). Jamais d'écrasement.", cle_privee_path)
        return 1

    if cle_publique_path.exists():
        logger.error("❌ Refus : le fichier de clé publique existe déjà (%s). Jamais d'écrasement.", cle_publique_path)
        return 1

    p1 = prompt_fn("Phrase de passe pour la clé privée : ")
    p2 = prompt_fn("Confirmation de la phrase de passe : ")

    if len(p1) < 12:
        logger.error("❌ Refus : la phrase de passe doit contenir au moins 12 caractères.")
        return 1

    if p1 != p2:
        logger.error("❌ Refus : les deux saisies de phrase de passe diffèrent.")
        return 1

    priv = rsa.generate_private_key(public_exponent=65537, key_size=taille_bits)
    pub = priv.public_key()

    pem_prive = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(p1.encode("utf-8")),
    )
    pem_pub = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    cle_privee_path.parent.mkdir(parents=True, exist_ok=True)
    cle_privee_path.write_bytes(pem_prive)

    cle_publique_path.parent.mkdir(parents=True, exist_ok=True)
    cle_publique_path.write_bytes(pem_pub)

    empreinte = empreinte_sha256_court(pem_pub)
    print(f"Empreinte de la clé publique (SHA-256) : {empreinte}")
    logger.info("Clés générées avec succès. Empreinte clé publique : %s", empreinte)
    return 0


def trouver_sources_recentes(source: Path) -> Tuple[Optional[Path], Optional[Path], int]:
    """Trouve les derniers dossiers datés complets pour bases et clés.

    Retourne (dernier_bases, dernier_cles, code_erreur).
    """
    dossier_bases_dir = source / "bases"
    dossier_cles_dir = source / "cles"

    if not dossier_bases_dir.exists() or not dossier_cles_dir.exists():
        logger.error("❌ Dossiers source bases/ ou cles/ introuvables sous %s", source)
        return None, None, 2

    candidats_bases = [
        item for item in dossier_bases_dir.iterdir()
        if item.is_dir() and MOTIF_BASES.match(item.name)
    ]
    if not candidats_bases:
        logger.error("❌ Aucun dossier daté complet dans %s", dossier_bases_dir)
        return None, None, 2

    candidats_bases.sort(key=lambda p: p.name)
    dernier_bases = candidats_bases[-1]

    try:
        dt_bases = datetime.strptime(dernier_bases.name, "%Y-%m-%d_%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.error("❌ Nom de dossier bases invalide : %s", dernier_bases.name)
        return None, None, 2

    age_heures = (datetime.now(timezone.utc) - dt_bases).total_seconds() / 3600.0
    if age_heures > 48.0:
        logger.error("❌ Dossier bases périmé (%.1fh > 48h) : %s", age_heures, dernier_bases.name)
        return None, None, 2

    candidats_cles = [
        item for item in dossier_cles_dir.iterdir()
        if item.is_dir() and MOTIF_CLES.match(item.name)
    ]
    if not candidats_cles:
        logger.error("❌ Aucun dossier daté complet dans %s", dossier_cles_dir)
        return None, None, 2

    candidats_cles.sort(key=lambda p: p.name)
    dernier_cles = candidats_cles[-1]

    return dernier_bases, dernier_cles, 0


def executer_sauvegarde(
    source: Path,
    sortie: Path,
    cle_publique_path: Path,
) -> int:
    """Mode par défaut : archive, chiffre et copie sur Google Drive."""
    if est_dans_depot(sortie):
        logger.error("❌ Refus : le dossier de sortie se trouve dans le dépôt (%s).", sortie)
        return 1

    # Refus (code 2) si le lecteur cible est inaccessible (ex: G:\ non monté)
    if str(sortie).upper().startswith("G:") and not Path("G:/").exists():
        logger.error("❌ Lecteur G:\\ introuvable (Google Drive arrêté ?)")
        return 2

    if sortie.drive and not Path(sortie.drive + "\\").exists():
        logger.error("❌ Lecteur %s introuvable.", sortie.drive)
        return 2

    dernier_bases, dernier_cles, code = trouver_sources_recentes(source)
    if code != 0:
        return code

    nom_archive = f"BotDiscord_{dernier_bases.name}.bdsv"
    archive_cible = sortie / nom_archive
    if archive_cible.exists():
        logger.info("Archive %s déjà présente pour la source %s : rien à faire.", nom_archive, dernier_bases.name)
        return 0

    if not cle_publique_path.exists():
        logger.error("❌ Fichier de clé publique introuvable : %s", cle_publique_path)
        return 1

    try:
        pem_pub_bytes = cle_publique_path.read_bytes()
        cle_pub = serialization.load_pem_public_key(pem_pub_bytes)
    except Exception as err:
        logger.error("❌ Erreur chargement clé publique : %s", err)
        return 1

    empreinte_cle_pub = empreinte_sha256_court(pem_pub_bytes)

    # 4. Construction du tar en mémoire (sans compression)
    tar_buffer = io.BytesIO()
    manifeste = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "cle_publique_sha256": empreinte_cle_pub,
        "source_bases": dernier_bases.name,
        "source_cles": dernier_cles.name,
        "fichiers": [],
    }

    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        for dossier, prefixe in [(dernier_bases, "bases"), (dernier_cles, "cles")]:
            for f in sorted(dossier.rglob("*")):
                if f.is_file():
                    arcname = f"{prefixe}/{dossier.name}/{f.relative_to(dossier).as_posix()}"
                    taille = f.stat().st_size
                    h = hashlib.sha256()
                    with open(f, "rb") as fp:
                        for chunk in iter(lambda: fp.read(65536), b""):
                            h.update(chunk)
                    sha_val = h.hexdigest()
                    manifeste["fichiers"].append({
                        "chemin": arcname,
                        "taille": taille,
                        "sha256": sha_val,
                    })
                    tar.add(f, arcname=arcname)
                    logger.debug("Fichier ajouté : %s (%d octets, sha=%s)", arcname, taille, sha_val[:8])

        manif_bytes = json.dumps(manifeste, indent=2).encode("utf-8")
        ti = tarfile.TarInfo(name="MANIFESTE.json")
        ti.size = len(manif_bytes)
        ti.mtime = int(time.time())
        tar.addfile(ti, io.BytesIO(manif_bytes))

    tar_bytes = tar_buffer.getvalue()
    logger.info("Tar en mémoire créé : %d octets, %d fichiers.", len(tar_bytes), len(manifeste["fichiers"]))

    # 5. Chiffrement hybride
    cle_aes = AESGCM.generate_key(bit_length=256)
    cle_aes_env = cle_pub.encrypt(
        cle_aes,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    nonce = os.urandom(12)
    aesgcm = AESGCM(cle_aes)
    chiffre_et_tag = aesgcm.encrypt(nonce, tar_bytes, MAGIC)

    archive_bytes = (
        MAGIC
        + len(cle_aes_env).to_bytes(2, "big")
        + cle_aes_env
        + nonce
        + chiffre_et_tag
    )

    sortie.mkdir(parents=True, exist_ok=True)
    fichier_partiel = sortie / f"{nom_archive}.partiel"
    with open(fichier_partiel, "wb") as f:
        f.write(archive_bytes)
    os.replace(fichier_partiel, archive_cible)

    # 6. Relecture et vérification de taille et d'en-tête
    with open(archive_cible, "rb") as f:
        entete = f.read(len(MAGIC))
        taille_lue = archive_cible.stat().st_size

    if entete != MAGIC or taille_lue != len(archive_bytes):
        logger.error("❌ Échec de vérification de l'archive après écriture.")
        return 1

    logger.info("Archive %s écrite et vérifiée avec succès (%d octets).", nom_archive, taille_lue)

    # 7. Rotation : conserve les 30 archives les plus récentes
    archives_existantes = [
        item for item in sortie.iterdir()
        if item.is_file() and MOTIF_ARCHIVE.match(item.name)
    ]
    archives_existantes.sort(key=lambda p: p.name)
    if len(archives_existantes) > 30:
        a_supprimer = archives_existantes[:-30]
        for v in a_supprimer:
            logger.info("Rotation : suppression de l'archive ancienne %s", v.name)
            v.unlink()

    # Nettoyage des .partiel orphelins de plus de 24h
    now_ts = time.time()
    for item in sortie.iterdir():
        if item.is_file() and MOTIF_ARCHIVE_PARTIEL.match(item.name):
            if (now_ts - item.stat().st_mtime) > 24 * 3600:
                logger.info("Nettoyage d'un partiel orphelin ancien : %s", item.name)
                item.unlink()

    return 0


def executer_restauration(
    archive_path: Path,
    cle_privee_path: Path,
    vers_path: Path,
    prompt_fn: Optional[Callable[[str], str]] = None,
) -> int:
    """Mode --restaurer : déchiffre, valide contre le MANIFESTE et extrait."""
    if prompt_fn is None:
        prompt_fn = getpass.getpass

    if est_dans_depot(vers_path):
        logger.error("❌ Refus : le dossier de restauration ne doit pas être dans le dépôt.")
        return 1

    if vers_path.exists() and any(vers_path.iterdir()):
        logger.error("❌ Refus : le dossier cible %s existe et n'est pas vide.", vers_path)
        return 1

    if not archive_path.exists():
        logger.error("❌ Archive introuvable : %s", archive_path)
        return 1

    if not cle_privee_path.exists():
        logger.error("❌ Clé privée introuvable : %s", cle_privee_path)
        return 1

    phrase = prompt_fn("Phrase de passe pour la clé privée : ")

    try:
        cle_privee = serialization.load_pem_private_key(
            cle_privee_path.read_bytes(),
            password=phrase.encode("utf-8") if phrase else None,
        )
    except Exception as err:
        logger.error("❌ Impossible de charger la clé privée (mauvaise phrase de passe ?) : %s", err)
        return 1

    raw = archive_path.read_bytes()
    min_len = len(MAGIC) + 2 + 12 + 16
    if len(raw) < min_len or raw[:len(MAGIC)] != MAGIC:
        logger.error("❌ En-tête BDSV1 manquant ou fichier corrompu.")
        return 1

    offset = len(MAGIC)
    klen = int.from_bytes(raw[offset:offset + 2], "big")
    offset += 2

    if len(raw) < offset + klen + 12 + 16:
        logger.error("❌ Format d'archive tronqué.")
        return 1

    cle_aes_env = raw[offset:offset + klen]
    offset += klen
    nonce = raw[offset:offset + 12]
    offset += 12
    chiffre_et_tag = raw[offset:]

    try:
        cle_aes = cle_privee.decrypt(
            cle_aes_env,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        aesgcm = AESGCM(cle_aes)
        tar_bytes = aesgcm.decrypt(nonce, chiffre_et_tag, MAGIC)
    except Exception as err:
        logger.error("❌ Échec du déchiffrement (archive modifiée ou corrompue) : %s", err)
        return 1

    try:
        tar = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r")
    except Exception as err:
        logger.error("❌ Archive tar corrompue : %s", err)
        return 1

    try:
        try:
            manif_file = tar.extractfile("MANIFESTE.json")
            if manif_file is None:
                raise ValueError("MANIFESTE.json introuvable dans le tar.")
            manifeste = json.loads(manif_file.read().decode("utf-8"))
        except Exception as err:
            logger.error("❌ Impossible de lire MANIFESTE.json : %s", err)
            return 1

        fichiers_attendus = manifeste.get("fichiers", [])
        # Contrôle strict de chaque fichier avant toute écriture sur le disque
        for entree in fichiers_attendus:
            chemin_rel = entree["chemin"]
            taille_att = entree["taille"]
            sha_att = entree["sha256"]
            try:
                f_obj = tar.extractfile(chemin_rel)
                if f_obj is None:
                    raise ValueError(f"Fichier {chemin_rel} non extractible du tar.")
                contenu = f_obj.read()
                if len(contenu) != taille_att:
                    raise ValueError(f"Taille non conforme pour {chemin_rel} ({len(contenu)} != {taille_att})")
                sha_calc = hashlib.sha256(contenu).hexdigest()
                if sha_calc != sha_att:
                    raise ValueError(f"SHA-256 non conforme pour {chemin_rel}")
            except Exception as err:
                logger.error("❌ Contrôle d'intégrité échoué pour %s : %s", chemin_rel, err)
                return 1

        vers_path.mkdir(parents=True, exist_ok=True)
        if hasattr(tarfile, "data_filter"):
            tar.extractall(path=vers_path, filter="data")
        else:
            for member in tar.getmembers():
                resolved = (vers_path / member.name).resolve()
                if not str(resolved).startswith(str(vers_path.resolve())):
                    raise ValueError(f"Chemin d'extraction non sécurisé : {member.name}")
            tar.extractall(path=vers_path)

        nb = len(fichiers_attendus)
        logger.info("✅ Restauration réussie : %d/%d fichiers vérifiés dans %s.", nb, nb, vers_path)
        return 0
    finally:
        tar.close()


def parser_arguments(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Sauvegarde chiffrée à deux clés sur Google Drive",
    )
    parser.add_argument(
        "--generer-cles",
        action="store_true",
        help="Génère la paire de clés RSA 4096 (Ahmed seulement)",
    )
    parser.add_argument(
        "--cle-privee",
        type=Path,
        metavar="PEM",
        help="Chemin vers la clé privée PEM",
    )
    parser.add_argument(
        "--cle-publique",
        type=Path,
        default=RACINE / "tools" / "sauvegarde_drive_cle_publique.pem",
        metavar="PEM",
        help="Chemin vers la clé publique PEM (défaut: tools/sauvegarde_drive_cle_publique.pem)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("D:/Sauvegardes/BotDiscord"),
        metavar="DIR",
        help="Dossier source contenant bases/ et cles/ (défaut: D:/Sauvegardes/BotDiscord)",
    )
    parser.add_argument(
        "--sortie",
        type=Path,
        default=Path("G:/Mon Drive/Sauvegardes BotDiscord"),
        metavar="DIR",
        help="Dossier de destination (défaut: G:/Mon Drive/Sauvegardes BotDiscord)",
    )
    parser.add_argument(
        "--restaurer",
        type=Path,
        metavar="ARCHIVE",
        help="Chemin de l'archive .bdsv à restaurer",
    )
    parser.add_argument(
        "--vers",
        type=Path,
        metavar="DIR",
        help="Dossier vide où restaurer les données",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Point d'entrée principal."""
    configurer_journalisation()
    args = parser_arguments(argv)

    if args.generer_cles:
        if not args.cle_privee:
            logger.error("❌ L'argument --cle-privee est requis pour --generer-cles.")
            return 1
        return generer_cles(
            cle_privee_path=args.cle_privee,
            cle_publique_path=args.cle_publique,
        )

    if args.restaurer:
        if not args.cle_privee or not args.vers:
            logger.error("❌ Les arguments --cle-privee et --vers sont requis pour --restaurer.")
            return 1
        return executer_restauration(
            archive_path=args.restaurer,
            cle_privee_path=args.cle_privee,
            vers_path=args.vers,
        )

    return executer_sauvegarde(
        source=args.source,
        sortie=args.sortie,
        cle_publique_path=args.cle_publique,
    )


if __name__ == "__main__":
    sys.exit(main())
