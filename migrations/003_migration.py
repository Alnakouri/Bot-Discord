# -*- coding: utf-8 -*-
"""
Migration 003: Ajout des profils personnalisables.
Tables: user_profiles
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from database_migrations import Migration


class ProfilesMigration(Migration):
    version = 3
    description = "Ajout profils utilisateurs personnalisables"
    
    def up(self, conn: sqlite3.Connection):
        """Crée la table des profils."""
        cursor = conn.cursor()
        
        # Table user_profiles : customisation des profils
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                bio TEXT,
                custom_color TEXT DEFAULT '#7289DA',
                custom_title TEXT,
                favorite_bot TEXT,
                profile_views INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        print("  ✅ Table user_profiles créée")
    
    def down(self, conn: sqlite3.Connection):
        """Supprime la table des profils."""
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS user_profiles")
        print("  🗑️ Table user_profiles supprimée")
