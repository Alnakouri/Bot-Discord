import sqlite3
import os
import logging

logger = logging.getLogger("api_tracker")

class APITracker:
    def __init__(self, db_path):
        self.db_path = db_path
        
    def _get_connection(self):
        """Ouvre une connexion read-only sur la base de données api_usage.db."""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError("Base api_usage.db absente (normal au premier lancement)")
            
        from pathlib import Path
        uri = Path(self.db_path).absolute().as_uri() + "?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=20)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"⚠️ [API Tracker] Base api_usage.db présente mais illisible : {e}")
            raise

    def get_usage(self, hours=24):
        try:
            conn = self._get_connection()
        except FileNotFoundError as e:
            logger.info(str(e))
            return {"period_hours": hours, "total_calls": 0, "by_api": {}, "status": "missing"}
        except sqlite3.Error as e:
            return {"period_hours": hours, "total_calls": 0, "by_api": {}, "status": "error", "error": str(e)}
            
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
                "by_api": by_api,
                "status": "ok"
            }
        except Exception as e:
            if conn: conn.close()
            logger.error(f"Error reading usage: {e}")
            return {"period_hours": hours, "total_calls": 0, "by_api": {}, "status": "error", "error": str(e)}

    def get_keys_status(self):
        """Récupère l'état de santé complet des clés depuis api_key_status."""
        try:
            conn = self._get_connection()
        except FileNotFoundError as e:
            logger.info(str(e))
            return []
        except Exception as e:
            logger.error(f"⚠️ [API Tracker] État des clés illisible : {e}")
            return []
        
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
            logger.error(f"Error in get_keys_status: {e}")
            if conn: conn.close()
            return []
