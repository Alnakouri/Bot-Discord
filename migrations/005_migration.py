# -*- coding: utf-8 -*-
"""
Migration 005: Ajout des systèmes de cache et sécurité.
Tables: cache, rate_limits, blacklist, audit_logs
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from database_migrations import Migration


class SecurityCacheMigration(Migration):
    version = 5
    description = "Ajout cache, rate limiting et audit logs"
    
    def up(self, conn: sqlite3.Connection):
        """Crée les tables de cache et sécurité."""
        cursor = conn.cursor()
        
        # Table cache : stockage des réponses en cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_key TEXT PRIMARY KEY,
                cache_value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                hit_count INTEGER DEFAULT 0,
                cache_type TEXT DEFAULT 'generic'
            )
        """)
        
        # Table rate_limits : tracking du rate limiting par user
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Index pour performance des requêtes rate limit
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_rate_limits_user_action 
            ON rate_limits(user_id, action_type, timestamp)
        """)
        
        # Table blacklist : utilisateurs/serveurs bannis
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                reason TEXT,
                banned_by INTEGER,
                banned_at TEXT NOT NULL,
                expires_at TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        
        # Table audit_logs : logs des actions sensibles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor_id INTEGER,
                target_id INTEGER,
                target_type TEXT,
                details TEXT,
                timestamp TEXT NOT NULL,
                ip_address TEXT
            )
        """)
        
        # Table shared_memory : mémoire partagée entre bots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shared_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_name TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                content TEXT NOT NULL,
                user_id INTEGER,
                channel_id INTEGER,
                relevance_score REAL DEFAULT 1.0,
                timestamp TEXT NOT NULL,
                expires_at TEXT
            )
        """)
        
        # Index pour performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_shared_memory_bot 
            ON shared_memory(bot_name, timestamp DESC)
        """)
        
        print("  ✅ Tables cache, rate_limits, blacklist, audit_logs, shared_memory créées")
    
    def down(self, conn: sqlite3.Connection):
        """Supprime les tables de cache et sécurité."""
        cursor = conn.cursor()
        cursor.execute("DROP INDEX IF EXISTS idx_shared_memory_bot")
        cursor.execute("DROP TABLE IF EXISTS shared_memory")
        cursor.execute("DROP TABLE IF EXISTS audit_logs")
        cursor.execute("DROP TABLE IF EXISTS blacklist")
        cursor.execute("DROP INDEX IF EXISTS idx_rate_limits_user_action")
        cursor.execute("DROP TABLE IF EXISTS rate_limits")
        cursor.execute("DROP TABLE IF EXISTS cache")
        print("  🗑️ Tables cache et sécurité supprimées")
