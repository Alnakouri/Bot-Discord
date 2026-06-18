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
                    api_name TEXT NOT NULL,
                    key_index INTEGER NOT NULL,
                    valid INTEGER DEFAULT 1,
                    cooldown_until TEXT,
                    total_calls INTEGER DEFAULT 0,
                    total_errors INTEGER DEFAULT 0,
                    last_error TEXT,
                    last_used TEXT,
                    PRIMARY KEY (api_name, key_index)
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
            cursor.execute("""
                SELECT api_name, key_index, valid, cooldown_until,
                       total_calls, total_errors, last_error, last_used
                FROM api_key_status
                ORDER BY api_name ASC, key_index ASC
            """)
            from datetime import datetime
            keys = []
            now = datetime.now()
            for row in cursor.fetchall():
                d = dict(row)
                valid = d.get("valid", 1)
                cooldown = d.get("cooldown_until")
                in_cooldown = False
                if cooldown:
                    try:
                        in_cooldown = datetime.fromisoformat(cooldown) > now
                    except (ValueError, TypeError):
                        in_cooldown = False
                if not valid:
                    status = "dead"
                elif in_cooldown:
                    status = "cooldown"
                else:
                    status = "active"
                keys.append({
                    "api_key_display": f"{d.get('api_name','?')} #{d.get('key_index','?')}",
                    "status": status,
                    "error_count": d.get("total_errors", 0),
                    "total_calls": d.get("total_calls", 0),
                    "last_used": (d.get("last_used") or "—"),
                    "last_error": (d.get("last_error") or "—"),
                })
            conn.close()
            return keys
        except Exception as e:
            print(f"Error in get_keys_status: {e}")
            if conn: conn.close()
            return []
