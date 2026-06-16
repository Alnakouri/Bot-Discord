import sqlite3
import os

class APITracker:
    def __init__(self, db_path):
        self.db_path = db_path
        
    def _get_connection(self):
        """Initialise la DB si nécessaire et active le mode WAL."""
        if not os.path.exists(os.path.dirname(self.db_path)):
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
        conn = sqlite3.connect(self.db_path, timeout=20)
        conn.row_factory = sqlite3.Row
        
        # Initialisation schéma si vide
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_name TEXT,
                    endpoint TEXT,
                    timestamp TEXT DEFAULT (datetime('now')),
                    success INTEGER,
                    response_time REAL,
                    error_message TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_key_status (
                    api_key TEXT PRIMARY KEY,
                    api_name TEXT,
                    status TEXT DEFAULT 'active',
                    error_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    tpm_current INTEGER DEFAULT 0,
                    rpm_current INTEGER DEFAULT 0,
                    quota_remaining REAL,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            # Activation WAL
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
        except sqlite3.Error as e:
            print(f"⚠️ [API Tracker] Init Error: {e}")
            
        return conn

    def get_usage(self, hours=24):
        conn = self._get_connection()
        if not conn:
            return {"error": "Base de données non initialisée"}
            
        try:
            cursor = conn.cursor()
            # Total des appels sur la période
            cursor.execute("SELECT COUNT(*) FROM api_calls WHERE timestamp >= datetime('now', ?)", (f"-{hours} hours",))
            total = cursor.fetchone()[0]
            
            # Appels par API Name (Gemini, Groq, etc.)
            cursor.execute("""
                SELECT api_name, COUNT(*), SUM(success) 
                FROM api_calls 
                WHERE timestamp >= datetime('now', ?)
                GROUP BY api_name
            """, (f"-{hours} hours",))
            
            by_api = {}
            for row in cursor.fetchall():
                by_api[row[0]] = {
                    "calls": row[1],
                    "errors": row[1] - (row[2] if row[2] is not None else 0),
                    "success_rate": round((row[2] / row[1] * 100), 2) if row[1] > 0 else 0
                }
            
            conn.close()
            return {
                "period_hours": hours,
                "total_calls": total,
                "by_api": by_api
            }
        except Exception as e:
            if conn: conn.close()
            return {"error": str(e)}

    def get_keys_status(self):
        """Récupère l'état de santé complet des clés depuis api_key_status."""
        conn = self._get_connection()
        if not conn: return []
        
        try:
            cursor = conn.cursor()
            # On récupère toutes les colonnes incluant TPM et Quota
            cursor.execute("""
                SELECT api_key, status, error_count, last_error, 
                       tpm_current, rpm_current, quota_remaining 
                FROM api_key_status
                ORDER BY status ASC, error_count DESC
            """)
            keys = []
            for row in cursor.fetchall():
                d = dict(row)
                # Obscurcir la clé pour l'affichage (garder les 4 derniers caractères)
                key_raw = d["api_key"]
                d["api_key_display"] = f"***{key_raw[-4:]}" if len(key_raw) > 4 else "***"
                keys.append(d)
            
            conn.close()
            return keys
        except Exception as e:
            print(f"Error in get_keys_status: {e}")
            return []
