# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/api_manager.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

import logging
from datetime import datetime
from core.api_tracking import tracer_etat_cle

# Ne pas recréer de logger racine si le programme principal en gère déjà un
# On crée un logger enfant
logger = logging.getLogger("api_manager")

class MultiAPIKeyManager:
    """Gestionnaire intelligent et centralisé de clés API."""
    
    def __init__(self):
        self.apis = {}
        # Cooldowns selon les codes d'erreur (en secondes)
        self.cooldown_times = {429: 3600, 503: 120, 500: 30, 408: 15, 529: 300, 400: 5}
        
        self._round_robin_index = {}   # {api_name: int}
        
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
            
        try:
            key_index = self.apis[api_name]["keys"].index(key)
        except ValueError:
            key_index = -1
            
        # Synchronisation avec la table api_key_status en DB
        if key_index != -1:
            cooldown_iso = None
            if status["cooldown"] > 0:
                cooldown_iso = datetime.fromtimestamp(status["cooldown"]).isoformat()
            
            tracer_etat_cle(
                api=api_name,
                index_cle=key_index,
                valide=status["valid"],
                cooldown_iso=cooldown_iso,
                erreur=str(error_code)
            )

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
