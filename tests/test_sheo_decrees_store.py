# -*- coding: utf-8 -*-
"""Tests unitaires du store de décrets persistant (Sheogorath/sheo_decrees.py).

C'est le cœur du correctif « rôle de décret orphelin » : la persistance survit aux
redémarrages pour que le filet de nettoyage puisse supprimer les rôles expirés.
On redirige DECREES_FILE vers un fichier temporaire (aucun bot ni Discord requis)."""
import os
import sys
import tempfile
import unittest

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)
_sheo_dir = os.path.join(_parent_dir, "Sheogorath")
if _sheo_dir not in sys.path:
    sys.path.insert(0, _sheo_dir)

import sheo_decrees


class TestDecreeStore(unittest.TestCase):
    def setUp(self):
        fd, self._path = tempfile.mkstemp(prefix="decrees_", suffix=".json")
        os.close(fd)
        os.remove(self._path)  # on veut l'absence initiale
        self._orig = sheo_decrees.DECREES_FILE
        sheo_decrees.DECREES_FILE = self._path

    def tearDown(self):
        sheo_decrees.DECREES_FILE = self._orig
        for p in (self._path, self._path + ".tmp"):
            if os.path.exists(p):
                os.remove(p)

    def test_load_missing_returns_empty_dict(self):
        self.assertEqual(sheo_decrees._load_decrees(), {})

    def test_add_then_load_roundtrip(self):
        entry = {"role_id": 123, "guild_id": 7, "title": "📜 ROI", "expire_at": 9999999999.0}
        sheo_decrees._add_decree(entry)
        data = sheo_decrees._load_decrees()
        self.assertIn("123", data)              # clé = str(role_id)
        self.assertEqual(data["123"]["title"], "📜 ROI")

    def test_remove_decree(self):
        sheo_decrees._add_decree({"role_id": 1, "guild_id": 1, "title": "x", "expire_at": 0})
        sheo_decrees._add_decree({"role_id": 2, "guild_id": 1, "title": "y", "expire_at": 0})
        sheo_decrees._remove_decree(1)
        data = sheo_decrees._load_decrees()
        self.assertNotIn("1", data)
        self.assertIn("2", data)

    def test_remove_absent_is_noop(self):
        sheo_decrees._add_decree({"role_id": 1, "guild_id": 1, "title": "x", "expire_at": 0})
        sheo_decrees._remove_decree(999)  # ne doit pas lever
        self.assertIn("1", sheo_decrees._load_decrees())

    def test_corrupted_file_recovers_to_empty(self):
        with open(self._path, "w", encoding="utf-8") as f:
            f.write("{ this is not json")
        self.assertEqual(sheo_decrees._load_decrees(), {})  # fail-safe, pas d'exception

    def test_save_is_atomic_no_leftover_tmp(self):
        sheo_decrees._add_decree({"role_id": 5, "guild_id": 1, "title": "z", "expire_at": 0})
        self.assertFalse(os.path.exists(self._path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
