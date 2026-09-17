import sqlite3
import os
from datetime import datetime, timedelta

class ConversationAnalyzer:
    def __init__(self, db_path):
        self.db_path = db_path
        
    def _get_connection(self):
        if not os.path.exists(self.db_path):
            return None
        from pathlib import Path
        uri = Path(self.db_path).absolute().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    def get_stats(self, days=7, bot=None):
        conn = self._get_connection()
        if not conn: return {"error": "DB non trouvée"}
        
        try:
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            
            stats = {
                "period_days": days,
                "total_interactions": 0,
                "unique_users": 0,
                "by_bot": {},
                "by_type": {}
            }
            
            # Total
            query = "SELECT COUNT(*), COUNT(DISTINCT user_id) FROM interactions WHERE timestamp > ?"
            params = [cutoff]
            if bot:
                query += " AND bot_name = ?"
                params.append(bot)
                
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()
            if row:
                stats["total_interactions"] = row[0]
                stats["unique_users"] = row[1]
                
            # Par bot
            # ⚠️ `unique_users` n'etait jamais calcule ici : la requete ne ramenait que
            # COUNT(*), et le rapport lisait `data.get("unique_users", 0)` — donc une
            # colonne « Utilisateurs Uniques » a 0 sur CHAQUE ligne, a cote d'un total
            # global a 1. Un chiffre faux vaut moins qu'une colonne absente : il fait
            # douter de tout le tableau.
            cursor.execute("""SELECT bot_name, COUNT(*), COUNT(DISTINCT user_id)
                              FROM interactions WHERE timestamp > ? GROUP BY bot_name""", (cutoff,))
            for r in cursor.fetchall():
                stats["by_bot"][r[0]] = {"messages": r[1], "unique_users": r[2]}
                
            # Par type
            cursor.execute("SELECT interaction_type, COUNT(*) FROM interactions WHERE timestamp > ? GROUP BY interaction_type", (cutoff,))
            for r in cursor.fetchall():
                key = r[0] if r[0] else "message"
                stats["by_type"][key] = stats["by_type"].get(key, 0) + r[1]
                
            conn.close()
            return stats
        except Exception as e:
            if conn: conn.close()
            return {"error": str(e)}

    def get_activity(self, hours=24):
        conn = self._get_connection()
        if not conn: return {"error": "DB non trouvée"}
        
        try:
            cursor = conn.cursor()
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            cursor.execute("""
                SELECT strftime('%Y-%m-%dT%H:00', timestamp) as hr, COUNT(*)
                FROM interactions
                WHERE timestamp > ?
                GROUP BY hr
                ORDER BY hr ASC
            """, (cutoff,))
            
            rows = cursor.fetchall()
            db_data = {r[0]: r[1] for r in rows if r[0]}
            
            buckets = []
            now = datetime.now()
            for i in range(hours):
                dt = now - timedelta(hours=hours - 1 - i)
                hour_str = dt.strftime('%Y-%m-%dT%H:00')
                count = db_data.get(hour_str, 0)
                buckets.append({"hour": hour_str, "count": count})
                
            conn.close()
            return {"buckets": buckets}
        except Exception as e:
            if conn: conn.close()
            return {"error": str(e)}
