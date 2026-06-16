import sqlite3
import os
import json

ERROR_PATTERNS = {
    "api_rate_limit": {
        "patterns": [r"429", r"Resource Exhausted", r"rate.?limit", r"quota"],
        "severity": "WARNING",
        "category": "API Quota",
        "auto_diagnosis": "Quota API épuisé.",
        "suggested_fix": "Vérifier le cooldown automatique ou ajouter des clés."
    },
    "api_auth_failed": {
        "patterns": [r"401", r"403", r"invalid.?api.?key"],
        "severity": "CRITICAL",
        "category": "Auth API",
        "auto_diagnosis": "Clé API invalide ou révoquée.",
        "suggested_fix": "Mettre à jour .env.encrypted."
    },
    "key_exhausted": {
        "patterns": [r"TOUTES LES CLÉS", r"ZÉRO clé saine", r"CLÉS SONT ÉPUISÉES"],
        "severity": "CRITICAL",
        "category": "API Indisponible",
        "auto_diagnosis": "Toutes les clés sont épuisées.",
        "suggested_fix": "Ajouter des clés ou patienter."
    }
}

class ErrorAnalyzer:
    def __init__(self, db_path):
        self.db_path = db_path
        
    def _get_connection(self):
        if not os.path.exists(self.db_path):
            return None
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_errors(self, bot=None, severity=None, resolved=None):
        conn = self._get_connection()
        if not conn: return []
        
        try:
            query = "SELECT * FROM error_events WHERE 1=1"
            params = []
            if bot:
                query += " AND bot_name = ?"
                params.append(bot)
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if resolved is not None:
                query += " AND resolved = ?"
                params.append(1 if resolved else 0)
                
            query += " ORDER BY timestamp DESC LIMIT 50"
            
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return results
        except Exception:
            return []

    def analyze(self, error_id):
        conn = self._get_connection()
        if not conn: return {"error": "DB non trouvée"}
        
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM error_events WHERE id = ?", (error_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row: return {"error": "Non trouvé"}
        
        msg = row['error_message']
        diagnosis = "Erreur inconnue."
        fix = "Vérifier les logs manuellement."
        cat = "Inconnu"
        
        import re
        for key, pattern_info in ERROR_PATTERNS.items():
            for pat in pattern_info['patterns']:
                if re.search(pat, msg, re.IGNORECASE):
                    diagnosis = pattern_info['auto_diagnosis']
                    fix = pattern_info['suggested_fix']
                    cat = pattern_info['category']
                    break
        
        return {
            "error_id": error_id,
            "category": cat,
            "severity": row['severity'],
            "auto_diagnosis": diagnosis,
            "suggested_fix": fix,
            "context": json.loads(row['context_json']) if row['context_json'] else {}
        }
