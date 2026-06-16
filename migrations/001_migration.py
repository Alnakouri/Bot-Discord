# -*- coding: utf-8 -*-
"""
Migration 001: Ajout des tables pour le système d'économie.
Tables: economy, items, shop
"""
import sqlite3
import sys
from pathlib import Path

# Import de la classe de base
sys.path.insert(0, str(Path(__file__).parent.parent))
from database_migrations import Migration


class EconomyMigration(Migration):
    version = 1
    description = "Ajout système d'économie (economy, items, shop)"
    
    def up(self, conn: sqlite3.Connection):
        """Crée les tables d'économie."""
        cursor = conn.cursor()
        
        # Table economy : gold des utilisateurs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id INTEGER PRIMARY KEY,
                gold INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                last_transaction TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Table items : inventaire des utilisateurs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                acquired_at TEXT,
                expires_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Table shop : catalogue d'items
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop (
                item_id TEXT PRIMARY KEY,
                item_name TEXT NOT NULL,
                item_type TEXT NOT NULL,
                price INTEGER NOT NULL,
                description TEXT,
                stock INTEGER DEFAULT -1,
                enabled INTEGER DEFAULT 1
            )
        """)
        
        # Insérer items de base dans le shop
        shop_items = [
            ("custom_color", "Couleur Personnalisée", "profile", 500, "Change la couleur de ton profil", -1, 1),
            ("custom_title", "Titre Personnalisé", "profile", 300, "Débloque un titre unique", -1, 1),
            ("xp_boost_1h", "Boost XP 1h", "consumable", 200, "Double ton XP pendant 1h", -1, 1),
            ("xp_boost_24h", "Boost XP 24h", "consumable", 1000, "Double ton XP pendant 24h", -1, 1),
            ("bot_summon", "Invocation de Bot", "consumable", 150, "Force un bot à répondre", -1, 1),
            ("lucky_coin", "Pièce Chanceuse", "consumable", 250, "Double tes gains pendant 1h", -1, 1),
        ]
        
        cursor.executemany("""
            INSERT OR IGNORE INTO shop (item_id, item_name, item_type, price, description, stock, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, shop_items)
        
        print("  ✅ Tables economy, items, shop créées")
    
    def down(self, conn: sqlite3.Connection):
        """Supprime les tables d'économie."""
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS shop")
        cursor.execute("DROP TABLE IF EXISTS items")
        cursor.execute("DROP TABLE IF EXISTS economy")
        print("  🗑️ Tables economy, items, shop supprimées")
