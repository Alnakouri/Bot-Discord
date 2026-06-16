# -*- coding: utf-8 -*-
"""
Migration 002: Ajout du système de niveaux et achievements.
Tables: user_xp, achievements, user_achievements
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from database_migrations import Migration


class AchievementsMigration(Migration):
    version = 2
    description = "Ajout système XP/niveaux et achievements"
    
    def up(self, conn: sqlite3.Connection):
        """Crée les tables XP et achievements."""
        cursor = conn.cursor()
        
        # Table user_xp : progression des utilisateurs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_xp (
                user_id INTEGER PRIMARY KEY,
                total_xp INTEGER DEFAULT 0,
                level INTEGER GENERATED ALWAYS AS (CAST(SQRT(total_xp / 100.0) AS INTEGER)) STORED,
                last_xp_gain TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Table achievements : définitions des achievements
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                achievement_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                icon TEXT,
                reward_gold INTEGER DEFAULT 0,
                reward_xp INTEGER DEFAULT 0,
                rarity TEXT DEFAULT 'common',
                category TEXT
            )
        """)
        
        # Table user_achievements : achievements débloqués par user
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                achievement_id TEXT NOT NULL,
                unlocked_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (achievement_id) REFERENCES achievements(achievement_id),
                UNIQUE(user_id, achievement_id)
            )
        """)
        
        # Insérer achievements de base
        achievements = [
            ("first_blood", "Premier Sang", "Première interaction avec un bot", "🩸", 50, 10, "common", "social"),
            ("social_butterfly", "Papillon Social", "Parler à 5 bots différents", "🦋", 200, 50, "uncommon", "social"),
            ("chatterbox", "Bavard", "Envoyer 100 messages aux bots", "💬", 150, 30, "common", "social"),
            ("duel_master", "Maître Duelliste", "Gagner 10 duels", "⚔️", 500, 100, "rare", "combat"),
            ("first_victory", "Première Victoire", "Gagner ton premier duel", "🏆", 100, 25, "common", "combat"),
            ("rich_boi", "Magnat", "Obtenir 1000 gold", "💰", 0, 50, "uncommon", "economy"),
            ("shopaholic", "Accro du Shopping", "Acheter 10 items", "🛒", 250, 40, "uncommon", "economy"),
            ("quest_hero", "Héros des Quêtes", "Compléter 25 quêtes", "📜", 300, 75, "rare", "quest"),
            ("daily_grinder", "Assidu", "Se connecter 7 jours d'affilée", "📅", 200, 50, "uncommon", "loyalty"),
            ("legend", "Légende", "Atteindre le niveau 50", "👑", 1000, 0, "legendary", "progression"),
            ("lore_master", "Maître du Lore", "Répondre parfaitement au quiz lore", "📚", 300, 60, "rare", "knowledge"),
            ("cheese_lover", "Amoureux du Fromage", "Mentionner le fromage 50 fois à Sheogorath", "🧀", 100, 20, "uncommon", "fun"),
            ("cat_whisperer", "Chuchoteur de Chats", "Avoir 100 conversations avec M'aiq", "🐱", 250, 50, "rare", "social"),
            ("pirate_legend", "Légende Pirate", "Terminer toutes les quêtes de Za'ji", "🏴‍☠️", 500, 100, "epic", "quest"),
            ("diplomat", "Diplomate", "Aider Rigurt dans 20 missions", "🎖️", 400, 80, "rare", "quest"),
        ]
        
        cursor.executemany("""
            INSERT OR IGNORE INTO achievements 
            (achievement_id, name, description, icon, reward_gold, reward_xp, rarity, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, achievements)
        
        print("  ✅ Tables user_xp, achievements, user_achievements créées")
    
    def down(self, conn: sqlite3.Connection):
        """Supprime les tables XP et achievements."""
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS user_achievements")
        cursor.execute("DROP TABLE IF EXISTS achievements")
        cursor.execute("DROP TABLE IF EXISTS user_xp")
        print("  🗑️ Tables XP et achievements supprimées")
