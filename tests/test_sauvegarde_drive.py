# -*- coding: utf-8 -*-
"""Verrous SUITE 15 : sauvegarde chiffree a deux cles sur Google Drive.

Vérifie que :
1. Aller-retour complet : archive chiffrée puis restaurée -> fichiers identiques, manifeste validé.
2. Rien en clair : les données sensibles ne sont pas présentes en clair dans l'archive .bdsv.
3. Intégrité : toute modification d'un octet fait échouer le déchiffrement et n'écrit rien sur le disque.
4. Mauvaise phrase de passe : échec du déchiffrement et rien d'écrit.
5. Refus stricts : sortie dans le dépôt, --vers non vide, bases > 48h (code 2), source sans dossier daté (code 2),
   .partiel ignoré au profit du dernier dossier complet.
6. Rotation : conserve les 30 archives les plus récentes, ne touche pas aux fichiers annexes (notes.txt, etc.).
7. Génération de clés : refuse l'écrasement, refuse dans le dépôt, clé privée chiffrée en PKCS8.
8. Pas de fichier en clair : aucun fichier .tar temporaire n'est écrit sur disque pendant la sauvegarde.
"""

from datetime import datetime, timezone
import pytest
from cryptography.hazmat.primitives import serialization

from tools.sauvegarde_drive import (
    RACINE,
    generer_cles,
    executer_sauvegarde,
    executer_restauration,
    main,
)

TEST_PASSWORD = "phrase_de_passe_de_test_123"


@pytest.fixture
def cles_test(tmp_path):
    """Génère une paire de clés RSA 2048 rapide pour les tests."""
    priv_path = tmp_path / "test_privee.pem"
    pub_path = tmp_path / "test_publique.pem"
    code = generer_cles(
        cle_privee_path=priv_path,
        cle_publique_path=pub_path,
        taille_bits=2048,
        prompt_fn=lambda prompt: TEST_PASSWORD,
    )
    assert code == 0
    return priv_path, pub_path


@pytest.fixture
def source_test(tmp_path):
    """Crée une arborescence source valide avec bases/ et cles/."""
    source = tmp_path / "source"
    now_dt = datetime.now(timezone.utc)
    nom_bases = now_dt.strftime("%Y-%m-%d_%H%M")
    bases_dir = source / "bases" / nom_bases
    bases_dir.mkdir(parents=True)
    (bases_dir / "bots_database.db").write_bytes(b"SQLite format 3\x00 test data")
    (bases_dir / "decisions.db").write_bytes(b"SQLite format 3\x00 decisions data")
    (bases_dir / "memoires.json").write_text('{"cle": "valeur"}', encoding="utf-8")

    nom_cles = now_dt.strftime("%Y-%m-%d")
    cles_dir = source / "cles" / nom_cles
    cles_dir.mkdir(parents=True)
    (cles_dir / "Alfred.master_key").write_bytes(b"MARQUEUR_SECRET_42_FERNET")
    (cles_dir / "Alfred.env.encrypted").write_bytes(b"encrypted_env_payload")

    return source, nom_bases, nom_cles


def test_1_aller_retour(tmp_path, cles_test, source_test):
    """1. Aller-retour : archive chiffrée -> restauration -> fichiers identiques, manifeste vérifié."""
    priv_path, pub_path = cles_test
    source, nom_bases, nom_cles = source_test
    sortie = tmp_path / "drive_sortie"

    # Sauvegarde
    code_sauv = executer_sauvegarde(
        source=source,
        sortie=sortie,
        cle_publique_path=pub_path,
    )
    assert code_sauv == 0

    archive = sortie / f"BotDiscord_{nom_bases}.bdsv"
    assert archive.exists()

    # Restauration
    vers = tmp_path / "restauration"
    code_rest = executer_restauration(
        archive_path=archive,
        cle_privee_path=priv_path,
        vers_path=vers,
        prompt_fn=lambda prompt: TEST_PASSWORD,
    )
    assert code_rest == 0

    # Vérification des fichiers restaurés
    rest_db = vers / "bases" / nom_bases / "bots_database.db"
    orig_db = source / "bases" / nom_bases / "bots_database.db"
    assert rest_db.read_bytes() == orig_db.read_bytes()

    rest_key = vers / "cles" / nom_cles / "Alfred.master_key"
    orig_key = source / "cles" / nom_cles / "Alfred.master_key"
    assert rest_key.read_bytes() == orig_key.read_bytes()

    rest_manif = vers / "MANIFESTE.json"
    assert rest_manif.exists()


def test_2_rien_en_clair(tmp_path, cles_test, source_test):
    """2. Rien en clair : un faux .master_key contient MARQUEUR_SECRET_42 ; l'archive .bdsv ne le contient pas."""
    _, pub_path = cles_test
    source, nom_bases, _ = source_test
    sortie = tmp_path / "drive_sortie"

    code_sauv = executer_sauvegarde(
        source=source,
        sortie=sortie,
        cle_publique_path=pub_path,
    )
    assert code_sauv == 0

    archive = sortie / f"BotDiscord_{nom_bases}.bdsv"
    contenu_archive = archive.read_bytes()
    assert b"MARQUEUR_SECRET_42" not in contenu_archive


def test_3_integrite_echoue_et_rien_ecrit(tmp_path, cles_test, source_test):
    """3. Intégrité : un octet modifié dans le chiffré -> échec et rien écrit dans --vers."""
    priv_path, pub_path = cles_test
    source, nom_bases, _ = source_test
    sortie = tmp_path / "drive_sortie"

    executer_sauvegarde(source=source, sortie=sortie, cle_publique_path=pub_path)
    archive = sortie / f"BotDiscord_{nom_bases}.bdsv"
    raw = bytearray(archive.read_bytes())

    # Modifier un octet dans la charge utile chiffrée
    raw[-10] ^= 0xFF
    archive.write_bytes(raw)

    vers = tmp_path / "restauration_corrompue"
    code = executer_restauration(
        archive_path=archive,
        cle_privee_path=priv_path,
        vers_path=vers,
        prompt_fn=lambda prompt: TEST_PASSWORD,
    )
    assert code == 1
    assert not vers.exists() or not any(vers.iterdir())


def test_4_mauvaise_phrase_de_passe(tmp_path, cles_test, source_test):
    """4. Mauvaise phrase de passe -> échec et rien écrit dans --vers."""
    priv_path, pub_path = cles_test
    source, nom_bases, _ = source_test
    sortie = tmp_path / "drive_sortie"

    executer_sauvegarde(source=source, sortie=sortie, cle_publique_path=pub_path)
    archive = sortie / f"BotDiscord_{nom_bases}.bdsv"

    vers = tmp_path / "restauration_faux_mdp"
    code = executer_restauration(
        archive_path=archive,
        cle_privee_path=priv_path,
        vers_path=vers,
        prompt_fn=lambda prompt: "faux_mot_de_passe_invalide",
    )
    assert code == 1
    assert not vers.exists() or not any(vers.iterdir())


def test_5_refus_stricts(tmp_path, cles_test, source_test):
    """5. Refus : sortie dans le dépôt, --vers non vide, bases > 48h (code 2), source sans dossier daté (code 2), .partiel ignoré."""
    priv_path, pub_path = cles_test
    source, nom_bases, _ = source_test

    # Sortie dans le dépôt -> code 1
    sortie_depot = RACINE / "tmp_test_sortie_interdite"
    res_depot = main(["--source", str(source), "--sortie", str(sortie_depot), "--cle-publique", str(pub_path)])
    assert res_depot == 1

    # --vers non vide -> code 1
    vers_occupe = tmp_path / "vers_occupe"
    vers_occupe.mkdir()
    (vers_occupe / "fichier.txt").write_text("deja la")
    archive_bidon = tmp_path / "bidon.bdsv"
    archive_bidon.write_bytes(b"BDSV1\n1234567890123456789012345678901234567890")
    res_vers = executer_restauration(archive_bidon, priv_path, vers_occupe, prompt_fn=lambda p: TEST_PASSWORD)
    assert res_vers == 1

    # bases > 48 h -> code 2
    source_vieille = tmp_path / "source_vieille"
    (source_vieille / "bases" / "2020-01-01_1200").mkdir(parents=True)
    (source_vieille / "cles" / "2020-01-01").mkdir(parents=True)
    res_vieux = main(["--source", str(source_vieille), "--sortie", str(tmp_path / "sortie_v"), "--cle-publique", str(pub_path)])
    assert res_vieux == 2

    # source sans dossier daté -> code 2
    source_vide = tmp_path / "source_vide"
    (source_vide / "bases").mkdir(parents=True)
    (source_vide / "cles").mkdir(parents=True)
    res_vide = main(["--source", str(source_vide), "--sortie", str(tmp_path / "sortie_vide"), "--cle-publique", str(pub_path)])
    assert res_vide == 2

    # .partiel ignoré au profit du dernier complet
    # Ajouter un dossier .partiel plus récent que nom_bases
    (source / "bases" / "2099-12-31_2359.partiel").mkdir(parents=True)
    sortie_partiel = tmp_path / "sortie_partiel"
    code_partiel = executer_sauvegarde(source, sortie_partiel, pub_path)
    assert code_partiel == 0
    # L'archive doit porter le nom du dossier complet, pas du partiel
    assert (sortie_partiel / f"BotDiscord_{nom_bases}.bdsv").exists()
    assert not (sortie_partiel / "BotDiscord_2099-12-31_2359.bdsv").exists()


def test_6_rotation(tmp_path, cles_test, source_test):
    """6. Rotation : 32 archives au bon motif + notes.txt + BotDiscord_vieux.bdsv -> 30 plus récentes, autres intacts."""
    _, pub_path = cles_test
    source, _, _ = source_test
    sortie = tmp_path / "sortie_rotation"
    sortie.mkdir(parents=True)

    # Créer 32 archives factices au bon format de nom
    for i in range(1, 33):
        nom = f"BotDiscord_2026-01-{i:02d}_1200.bdsv"
        (sortie / nom).write_bytes(b"BDSV1\n" + b"0" * 50)

    # Fichiers annexes à préserver absolument
    (sortie / "notes.txt").write_text("garder ce fichier", encoding="utf-8")
    (sortie / "BotDiscord_vieux.bdsv").write_bytes(b"autre archive manuelle")

    # Exécuter sauvegarde (qui effectue la rotation)
    code = executer_sauvegarde(source, sortie, pub_path)
    assert code == 0

    # Vérifications
    restantes = [p.name for p in sortie.glob("BotDiscord_2026-*.bdsv")]
    assert len(restantes) == 30
    assert "BotDiscord_2026-01-01_1200.bdsv" not in restantes
    assert "BotDiscord_2026-01-02_1200.bdsv" not in restantes
    assert "BotDiscord_2026-01-32_1200.bdsv" in restantes

    assert (sortie / "notes.txt").exists()
    assert (sortie / "notes.txt").read_text(encoding="utf-8") == "garder ce fichier"
    assert (sortie / "BotDiscord_vieux.bdsv").exists()


def test_7_generation_cles_securisee(tmp_path):
    """7. Génération : refuse écrasement, refuse dans le dépôt, clé privée chiffrée."""
    priv = tmp_path / "priv.pem"
    pub = tmp_path / "pub.pem"

    # Génération normale
    code = generer_cles(priv, pub, taille_bits=2048, prompt_fn=lambda p: TEST_PASSWORD)
    assert code == 0

    # Refuse d'écraser
    code_re = generer_cles(priv, pub, taille_bits=2048, prompt_fn=lambda p: TEST_PASSWORD)
    assert code_re == 1

    # Refuse clé privée dans le dépôt
    priv_depot = RACINE / "priv_interdite.pem"
    pub_autre = tmp_path / "pub_autre.pem"
    code_depot = generer_cles(priv_depot, pub_autre, taille_bits=2048, prompt_fn=lambda p: TEST_PASSWORD)
    assert code_depot == 1

    # La clé privée écrite est chiffrée
    pem_prive = priv.read_bytes()
    assert b"ENCRYPTED" in pem_prive

    # Doit refuser de charger sans mot de passe
    with pytest.raises(TypeError):
        serialization.load_pem_private_key(pem_prive, password=None)


def test_8_pas_de_fichier_en_clair(tmp_path, cles_test, source_test):
    """8. Pas de fichier en clair : tmp_path ne contient aucun .tar ni fichier autre que l'archive."""
    _, pub_path = cles_test
    source, nom_bases, _ = source_test
    sortie = tmp_path / "sortie_propre"

    code = executer_sauvegarde(source, sortie, pub_path)
    assert code == 0

    fichiers_sortie = list(sortie.iterdir())
    assert len(fichiers_sortie) == 1
    assert fichiers_sortie[0].name == f"BotDiscord_{nom_bases}.bdsv"

    # Aucun .tar dans tout le dossier temporaire
    tars = list(tmp_path.rglob("*.tar"))
    assert len(tars) == 0
