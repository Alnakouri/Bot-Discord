import sqlite3
from datetime import datetime

class AuditAnalyzer:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user TEXT NOT NULL,
                    action TEXT NOT NULL,
                    bot_name TEXT,
                    details TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def log(self, action: str, bot_name: str = None, details: str = None, user: str = "admin"):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO audit_logs (timestamp, user, action, bot_name, details) VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(), user, action, bot_name, details)
            )
            conn.commit()
        except Exception as e:
            print(f"Error writing audit log: {e}")
        finally:
            conn.close()

    def get_logs(self, limit: int = 100):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"Error fetching audit logs: {e}")
            return []
        finally:
            conn.close()
