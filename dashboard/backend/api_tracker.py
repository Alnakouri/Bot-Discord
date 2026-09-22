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
            cursor.execute("SELECT COUNT(*) FROM api_calls WHERE timestamp >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)", (f"-{hours} hours",))
            total = cursor.fetchone()[0]
            
            # Appels par API Name (Gemini, Groq, etc.)
            # ⚠️ Un echelon SAUTE n'est pas un appel rate. La cascade ecrit `raison` pour
            # ca : `quarantaine` (la cle dormait, on est passe au suivant) et `non_tentee`
            # (aucun client construit) sont des lignes ou AUCUNE requete n'est partie —
            # latence 0. Les compter en erreurs donnait, le 2026-09-17 : « gemini 43.56 % »
            # alors que les 98 appels reellement tentes avaient TOUS reussi, et
            # « nvidia 0.0 % » pour un fournisseur qu'on n'avait jamais appele.
            # Le code de la cascade le disait deja : « ce n'est pas un echec d'API, et ca ne
            # doit pas remplir la base d'echecs sans cause ». On cessait juste de le lire.
            cursor.execute("""
                SELECT api_name,
                       COUNT(*),
                       SUM(success),
                       SUM(CASE WHEN success = 0 AND raison IN ('non_tentee','quarantaine')
                                THEN 1 ELSE 0 END)
                FROM api_calls
                WHERE timestamp >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)
                GROUP BY api_name
            """, (f"-{hours} hours",))

            by_api = {}
            for row in cursor.fetchall():
                appels = row[1]
                succes = row[2] or 0
                sautes = row[3] or 0
                tentes = appels - sautes
                by_api[row[0]] = {
                    "calls": appels,
                    "tentes": tentes,
                    "sautes": sautes,
                    "errors": tentes - succes,
                    # None, pas 0 : un fournisseur jamais appele n'a pas « 0 % de succes »,
                    # il n'a pas de taux. Afficher 0 % faisait passer un echelon non cable
                    # pour un fournisseur en panne.
                    "success_rate": round((succes / tentes * 100), 2) if tentes > 0 else None
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
            # ⚠️ `api_key_status.total_calls` n'est JAMAIS incrémenté : l'upsert de
            # `shared/api_tracking.py` ne touche que `total_errors`. La table affichait donc
            # « gemini #0 | Appels 0 | Erreurs 69 » — un compteur qui ne sait que se plaindre.
            # Les compteurs viennent maintenant d'`api_calls`, seule source qui voit chaque
            # appel, et ils excluent les échelons sautés comme le tableau ci-dessus.
            # ⚠️ `key_index` ne distingue PAS les six bots : chacun a sa propre clé (règle
            # du projet) et toutes portent l'index 0 dans cette base. Une ligne « #0 »
            # agrège donc six clés différentes ; elle dit la santé d'un FOURNISSEUR, pas
            # celle d'une clé.
            cursor.execute("""
                SELECT s.api_name, s.key_index, s.valid, s.cooldown_until,
                       COALESCE(c.appels, 0)  AS total_calls,
                       COALESCE(c.erreurs, 0) AS total_errors,
                       s.last_error, s.last_used
                FROM api_key_status s
                LEFT JOIN (
                    SELECT api_name, key_index,
                           SUM(CASE WHEN NOT (success = 0
                                    AND COALESCE(raison,'') IN ('non_tentee','quarantaine'))
                                    THEN 1 ELSE 0 END) AS appels,
                           SUM(CASE WHEN success = 0
                                    AND COALESCE(raison,'') NOT IN ('non_tentee','quarantaine')
                                    THEN 1 ELSE 0 END) AS erreurs
                    FROM api_calls
                    GROUP BY api_name, key_index
                ) c ON c.api_name = s.api_name AND c.key_index = s.key_index
                ORDER BY s.api_name ASC, s.key_index ASC
            """)
            from datetime import datetime, timezone
            keys = []
            now = datetime.now(timezone.utc).replace(tzinfo=None)
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
                    # ⚠️ `api_name` et `key_index` ne sortaient PAS d'ici, alors que le
                    # front groupe les cles par fournisseur (`byProvider[k.api_name]`,
                    # app.js). Resultat a l'ecran : un seul groupe intitule « undefined »
                    # au-dessus de toutes les cles. Le nom n'existait que fondu dans
                    # `api_key_display`, ou le JS ne pouvait pas le relire.
                    "api_name": d.get("api_name"),
                    "key_index": d.get("key_index"),
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
