# -*- coding: utf-8 -*-
"""Tests unitaires du chiffrement des .env (crypto_utils.py).

Vérifie le cycle clé propre → chiffrement → déchiffrement sur un dossier temporaire,
sans toucher aux vrais bots ni aux vraies clés."""
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from cryptography.fernet import Fernet
import crypto_utils


class TestCryptoRoundTrip(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="crypto_test_"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_get_bot_key_creates_then_reads_same(self):
        key1 = crypto_utils.get_bot_key(self.dir, create=True)
        self.assertIsNotNone(key1)
        self.assertTrue((self.dir / ".master_key").exists())
        # 2e lecture sans create → même clé
        key2 = crypto_utils.get_bot_key(self.dir, create=False)
        self.assertEqual(key1, key2)

    def test_missing_key_without_create_returns_none(self):
        self.assertIsNone(crypto_utils.get_bot_key(self.dir, create=False))

    def test_encrypt_then_decrypt_restores_content(self):
        secret = b"DISCORD_TOKEN=abc123\nGROQ_API_KEY=gsk-xyz\n"
        env_path = self.dir / ".env"
        env_path.write_bytes(secret)

        key = crypto_utils.get_bot_key(self.dir, create=True)
        fernet = Fernet(key)

        self.assertTrue(crypto_utils.encrypt_file(env_path, fernet))
        # le clair doit avoir disparu, le chiffré exister
        self.assertFalse(env_path.exists())
        self.assertTrue((self.dir / ".env.encrypted").exists())
        # le chiffré ne contient pas le secret en clair
        self.assertNotIn(b"DISCORD_TOKEN", (self.dir / ".env.encrypted").read_bytes())

        self.assertTrue(crypto_utils.decrypt_file(env_path, fernet))
        self.assertEqual(env_path.read_bytes(), secret)

    def test_wrong_key_fails_to_decrypt(self):
        env_path = self.dir / ".env"
        env_path.write_bytes(b"SECRET=1\n")
        good = Fernet(crypto_utils.get_bot_key(self.dir, create=True))
        crypto_utils.encrypt_file(env_path, good)

        wrong = Fernet(Fernet.generate_key())
        # mauvaise clé → échec propre (False), pas d'exception qui remonte
        self.assertFalse(crypto_utils.decrypt_file(env_path, wrong))


if __name__ == "__main__":
    unittest.main()
