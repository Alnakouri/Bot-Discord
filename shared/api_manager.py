import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from collections import deque

# Ne pas recréer de logger racine si le programme principal en gère déjà un
# On crée un logger enfant
logger = logging.getLogger("api_manager")

class MultiAPIKeyManager:
    """Gestionnaire intelligent et centralisé de clés API."""
    
    def __init__(self):
        self.apis = {}
        # Cooldowns selon les codes d'erreur (en secondes)
        # 429 = Rate Limit / Resource Exhausted -> 1 heure 
        # 503 = Service Unavailable -> 2 minutes
        # 500 = Internal Server Error -> 30 secondes
        # 408 = Timeout -> 15s
        # 529 = Overloaded -> 5min (OpenRouter spécifique)
        # 400 = Bad Request -> 5s (Evite de spammer en cas de bug de payload)
        self.cooldown_times = {429: 3600, 503: 120, 500: 30, 408: 15, 529: 300, 400: 5}
        
        self._round_robin_index = {}   # {api_name: int}
        self._tpm_windows = {}         # {key: deque([(timestamp, tokens)])}
        self.TPM_LIMITS = {            # Limites tokens/minute par API
            "gemini": 1_000_000,       
            "groq": 100_000,           
            "mistral": 500_000,        
        }
        self.TPM_ALERT_THRESHOLD = 0.85
        self.TPM_PAUSE_THRESHOLD = 0.95
        
        self._usage_db = None
        self._init_usage_db()
        
    def _init_usage_db(self):
        """Initialise la base de tracking API (lazy, dans data/)."""
        try:
            data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "api_usage.db")
            self._usage_db = sqlite3.connect(db_path, check_same_thread=False)
            self._usage_db.execute("""
                CREATE TABLE IF NOT EXISTS api_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    bot_name TEXT NOT NULL,
                    api_name TEXT NOT NULL,
                    key_index INTEGER,
                    success INTEGER NOT NULL,
                    error_code INTEGER,
                    error_message TEXT,
                    latency_ms REAL,
                    model TEXT,
                    tokens_used INTEGER
                )
            """)
            self._usage_db.execute("""
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
            self._usage_db.commit()
        except Exception as e:
            logger.warning(f"⚠️ [API TRACKER] DB init failed: {e}")
            
    def track_call(self, bot_name, api_name, key_index, success, 
                   error_code=None, error_message=None, latency_ms=None, 
                   model=None, tokens_used=None):
        """Enregistre un appel API pour le tracking dashboard."""
        if not self._usage_db:
            return
        try:
            self._usage_db.execute("""
                INSERT INTO api_calls 
                (timestamp, bot_name, api_name, key_index, success, 
                 error_code, error_message, latency_ms, model, tokens_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(), bot_name, api_name, key_index,
                1 if success else 0, error_code, error_message, 
                latency_ms, model, tokens_used
            ))
            self._usage_db.commit()
        except Exception:
            pass  # Ne jamais crasher le bot
    
    def register_api(self, api_name, keys):
        """Enregistre un pool de clés pour une API donnée (ex: 'gemini', 'openrouter')."""
        valid_keys = [k for k in keys if k] if keys else []
        if valid_keys:
            self.apis[api_name] = {
                "keys": valid_keys,
                "status": {k: {"valid": True, "cooldown": 0} for k in valid_keys}
            }
            logger.info(f"✅ [KEY MANAGER] {api_name.upper()}: {len(valid_keys)} clé(s) prête(s) à l'emploi.")
        else:
            logger.warning(f"⚠️ [KEY MANAGER] {api_name.upper()}: Aucune clé fournie.")
    
    def get_key(self, api_name):
        """Rotation Round-Robin entre les clés saines (non en cooldown)."""
        if api_name not in self.apis:
            return None
        keys = self.apis[api_name]["keys"]
        if not keys:
            return None
            
        now = datetime.now().timestamp()
        start_idx = self._round_robin_index.get(api_name, 0)
        
        for i in range(len(keys)):
            idx = (start_idx + i) % len(keys)
            key = keys[idx]
            status = self.apis[api_name]["status"][key]
            if status["valid"] and status["cooldown"] <= now:
                # Avancer l'index pour le prochain appel
                self._round_robin_index[api_name] = (idx + 1) % len(keys)
                logger.debug(f"[KEY MANAGER] {api_name.upper()} → clé idx={idx}")
                return key
                
        # Si on arrive ici, toutes les clés sont soit invalides, soit en cooldown massif
        logger.error(f"🚨 [CRITIQUE] {api_name.upper()} : TOUTES LES CLÉS SONT ÉPUISÉES OU EN COOLDOWN !")
        return None  # Plus d'essai à l'aveugle, on avoue l'échec pour permettre le fallback

    def is_api_available(self, api_name):
        """Vérifie s'il reste au moins une clé saine pour cette API."""
        if api_name not in self.apis: return False
        now = datetime.now().timestamp()
        for key in self.apis[api_name]["keys"]:
            status = self.apis[api_name]["status"][key]
            if status["valid"] and status["cooldown"] <= now:
                return True
        return False

    def track_tokens(self, api_name: str, key: str, tokens_used: int):
        """
        Enregistre les tokens consommés et applique un cooldown préventif
        si la clé approche la limite TPM (tokens per minute).
        """
        if not key or api_name not in self.apis or not tokens_used:
            return
        
        now = datetime.now().timestamp()
        if key not in self._tpm_windows:
            self._tpm_windows[key] = deque()
        
        window = self._tpm_windows[key]
        window.append((now, tokens_used))
        
        # Purger les entrées > 60 secondes
        while window and window[0][0] < now - 60:
            window.popleft()
        
        total_tpm = sum(t for _, t in window)
        limit = self.TPM_LIMITS.get(api_name, 100_000)
        ratio = total_tpm / limit
        
        if ratio >= self.TPM_PAUSE_THRESHOLD:
            # Cooldown préventif 30s
            status = self.apis[api_name]["status"].get(key)
            if status:
                status["cooldown"] = now + 30
                logger.warning(f"🔶 [TPM PRÉVENTIF] {api_name.upper()} clé ...{key[-4:]} : {total_tpm:,}/{limit:,} TPM → pause 30s")
        elif ratio >= self.TPM_ALERT_THRESHOLD:
            logger.warning(f"⚠️ [TPM PROCHE LIMITE] {api_name.upper()} clé ...{key[-4:]} : {total_tpm:,}/{limit:,} TPM")
    
    def report_error(self, api_name, key, error_code):
        """Signale une erreur sur une clé pour qu'elle soit écartée ou mise en quarantaine."""
        if api_name not in self.apis or key not in self.apis[api_name]["status"]:
            return
            
        status = self.apis[api_name]["status"][key]
        now = datetime.now().timestamp()
        
        # Erreurs fatales (Clé révoquée, interdite, ou invalide)
        if error_code in [401, 403]:
            logger.error(f"❌ [KEY MANAGER] {api_name.upper()} : Clé DÉSACTIVÉE PERMANEMMENT (Erreur {error_code}).")
            status["valid"] = False
            
        # Erreurs temporaires (Quotas, surcharges)
        elif error_code in self.cooldown_times:
            cooldown_duration = self.cooldown_times[error_code]
            status["cooldown"] = now + cooldown_duration
            logger.warning(f"⚠️ [KEY MANAGER] {api_name.upper()} : Clé mise en QUARANTAINE pour {cooldown_duration}s (Erreur {error_code}).")
            
            # Log instructif pour montrer à l'admin qu'il bascule
            self._log_remaining_keys(api_name)
            
        # Tracking de l'erreur
        try:
            key_index = self.apis[api_name]["keys"].index(key)
        except ValueError:
            key_index = -1
            
        self.track_call(
            bot_name="unknown",
            api_name=api_name,
            key_index=key_index,
            success=False,
            error_code=error_code
        )
        
        # Synchronisation avec la table api_key_status en DB
        if key_index != -1 and self._usage_db:
            try:
                cooldown_iso = None
                if status["cooldown"] > 0:
                    cooldown_iso = datetime.fromtimestamp(status["cooldown"]).isoformat()
                
                self._usage_db.execute("""
                    INSERT INTO api_key_status 
                        (api_name, key_index, valid, cooldown_until, total_errors, last_error, last_used)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(api_name, key_index) DO UPDATE SET
                        valid = excluded.valid,
                        cooldown_until = excluded.cooldown_until,
                        total_errors = api_key_status.total_errors + 1,
                        last_error = excluded.last_error,
                        last_used = excluded.last_used
                """, (api_name, key_index, 1 if status["valid"] else 0, cooldown_iso, str(error_code),
                      datetime.now().isoformat()))
                self._usage_db.commit()
            except Exception as e:
                logger.debug(f"[API MANAGER] Error syncing DB: {e}")

    def _log_remaining_keys(self, api_name):
        """Affiche combien de clés sont encore opérationnelles sur ce pool."""
        now = datetime.now().timestamp()
        saines = 0
        for key in self.apis[api_name]["keys"]:
            status = self.apis[api_name]["status"][key]
            if status["valid"] and status["cooldown"] <= now:
                saines += 1
        
        if saines > 0:
            logger.info(f"🔄 [KEY MANAGER] Bascule en cours... Il reste {saines} clé(s) saine(s) pour {api_name.upper()}.")
        else:
            logger.error(f"🚨 [KEY MANAGER] ZÉRO clé saine restante pour {api_name.upper()} !!")

    def get_status(self, api_name: str) -> dict:
        """Retourne le statut d'une API pour le healthcheck."""
        if api_name not in self.apis:
            return {"status": "unknown", "keys": 0}
        
        api = self.apis[api_name]
        total_keys = len(api["keys"])
        now = datetime.now().timestamp()
        
        healthy_keys = 0
        for key in api["keys"]:
            status = api["status"][key]
            if status["valid"] and status["cooldown"] <= now:
                healthy_keys += 1
        
        return {
            "status": "healthy" if healthy_keys > 0 else ("degraded" if total_keys > 0 else "no_keys"),
            "total_keys": total_keys,
            "healthy_keys": healthy_keys,
            "current_index": api.get("index", 0)
        }
