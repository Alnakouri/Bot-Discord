# -*- coding: utf-8 -*-
"""
Migration 004: Ajout du système arena/tournois.
Tables: arena_matches, tournaments, tournament_participants
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from database_migrations import Migration


class ArenaMigration(Migration):
    version = 4
    description = "Ajout système arena et tournois"
    
    def up(self, conn: sqlite3.Connection):
        """Crée les tables arena et tournois."""
        cursor = conn.cursor()
        
        # Table arena_matches : historique des matchs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arena_matches (
                match_id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_type TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                opponent_id INTEGER,
                opponent_type TEXT DEFAULT 'bot',
                player_score INTEGER,
                opponent_score INTEGER,
                winner_id INTEGER,
                reward_gold INTEGER DEFAULT 0,
                reward_xp INTEGER DEFAULT 0,
                played_at TEXT NOT NULL,
                duration_seconds INTEGER,
                FOREIGN KEY (player_id) REFERENCES users(user_id)
            )
        """)
        
        # Table tournaments : définition des tournois
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                tournament_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                game_type TEXT NOT NULL,
                status TEXT DEFAULT 'registration',
                max_participants INTEGER DEFAULT 32,
                start_date TEXT,
                end_date TEXT,
                prize_pool INTEGER,
                created_at TEXT
            )
        """)
        
        # Table tournament_participants : inscrits aux tournois
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tournament_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                seed INTEGER,
                current_round INTEGER DEFAULT 0,
                eliminated INTEGER DEFAULT 0,
                final_rank INTEGER,
                prize_won INTEGER DEFAULT 0,
                registered_at TEXT,
                FOREIGN KEY (tournament_id) REFERENCES tournaments(tournament_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(tournament_id, user_id)
            )
        """)
        
        # Table arena_leaderboard : classement par jeu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS arena_leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_type TEXT NOT NULL,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                total_matches INTEGER DEFAULT 0,
                best_score INTEGER DEFAULT 0,
                elo_rating INTEGER DEFAULT 1200,
                last_match TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, game_type)
            )
        """)
        
        print("  ✅ Tables arena_matches, tournaments, tournament_participants, arena_leaderboard créées")
    
    def down(self, conn: sqlite3.Connection):
        """Supprime les tables arena."""
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS arena_leaderboard")
        cursor.execute("DROP TABLE IF EXISTS tournament_participants")
        cursor.execute("DROP TABLE IF EXISTS tournaments")
        cursor.execute("DROP TABLE IF EXISTS arena_matches")
        print("  🗑️ Tables arena supprimées")
