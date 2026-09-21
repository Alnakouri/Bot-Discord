import logging
from datetime import datetime
from shared.api_tracking import tracer_etat_cle

# Ne pas recréer de logger racine si le programme principal en gère déjà un
# On crée un logger enfant
logger = logging.getLogger("api_manager")

# Fournisseurs dont le quota se compte PAR MODELE, et non par cle.
#
# ⚠️ Google le dit dans son propre 429 : le quota depasse s'appelle
# `GenerateRequestsPerMinutePerProjectPerModel` — 15 requetes/minute PAR MODELE, pas par
# projet. Poser le cooldown sur la CLE y ecarte donc des echelons dont le seau est INTACT.
# Mesure du 2026-09-20 (harnais d'eval, mais le defaut etait le meme en prod) : le juge
# saturait `gemini-3.5-flash`, et l'echelon `flash-lite` du bot mesure se retrouvait saute
# 12 a 13 fois sur 17 alors que le bot n'avait fait que DEUX appels dans la minute.
#
# ⚠️ Les autres fournisseurs restent DEHORS, et ce n'est pas un oubli. Chez eux un 429
# ecarte la cle entiere — c'est le comportement mesure et valide le 2026-09-04 (trois
# appels Mistral sur la meme cle morte dans la meme seconde). Elargir cette liste demande
# une MESURE chez le fournisseur concerne, pas une intuition : se tromper de sens ici
# rend la quarantaine inoperante et le bot retape dans le mur.
QUOTA_PAR_MODELE = frozenset({"gemini"})

class MultiAPIKeyManager:
    """Gestionnaire intelligent et centralisé de clés API."""
    
    def __init__(self):
        self.apis = {}
        # Cooldowns selon les codes d'erreur (en secondes)
        # ⚠️ Seule la duree du 429 sert encore : depuis le 2026-09-03, les autres codes
        # n'ecartent plus la cle (ils parlent du MODELE ou de la REQUETE, pas d'elle).
        # Ils restent listes ici pour que `report_error` les reconnaisse comme des
        # incidents connus et les journalise au lieu de les avaler.
        self.cooldown_times = {503: 120, 500: 30, 408: 15, 529: 300, 400: 5}
        
        self._round_robin_index = {}   # {api_name: int}
        
    def register_api(self, api_name, keys):
        """Enregistre un pool de clés pour une API donnée (ex: 'gemini', 'openrouter')."""
        valid_keys = [k for k in keys if k] if keys else []
        if valid_keys:
            self.apis[api_name] = {
                "keys": valid_keys,
                # `cooldown_modele` : {nom_du_modele: instant_de_reprise}. Vide tant
                # qu'aucun 429 par-modele n'est tombe. Cf. QUOTA_PAR_MODELE.
                "status": {
                    k: {"valid": True, "cooldown": 0, "cooldown_modele": {}}
                    for k in valid_keys
                }
            }
            logger.info(f"✅ [KEY MANAGER] {api_name.upper()}: {len(valid_keys)} clé(s) prête(s) à l'emploi.")
        else:
            logger.warning(f"⚠️ [KEY MANAGER] {api_name.upper()}: Aucune clé fournie.")
    
    @staticmethod
    def _reprise(status, modele=None):
        """Instant auquel cette clé redevient utilisable POUR CE MODELE.

        Deux seaux se cumulent, et le plus tardif gagne :
          - `cooldown` porte un incident dont on ignore le modèle (ou dont le quota se
            compte par clé) : il vaut pour TOUS les modèles ;
          - `cooldown_modele[m]` ne vaut que pour `m`.

        `modele=None` — un appelant qui ne dit pas quel modèle il vise — ne voit que le
        premier : on ne peut pas lui refuser une clé au nom d'un modèle qu'il n'a pas
        nommé, et il reste libre de se prendre le 429 qui le renseignera.
        """
        fin = status.get("cooldown", 0) or 0
        if modele is not None:
            fin = max(fin, (status.get("cooldown_modele") or {}).get(modele, 0))
        return fin

    def _est_libre(self, status, modele, now):
        """Clé ni révoquée ni en cooldown pour ce modèle."""
        return bool(status["valid"]) and self._reprise(status, modele) <= now

    def get_key(self, api_name, modele=None):
        """Rotation Round-Robin entre les clés saines (non en cooldown).

        `modele` est FACULTATIF et ne sert qu'à lire le bon seau : une clé écartée sur
        `gemini-3.5-flash` reste servie pour `gemini-3.5-flash-lite`, dont le quota est
        un autre seau chez Google. Sans `modele`, seul le cooldown de la clé compte.
        """
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
            if self._est_libre(status, modele, now):
                # Avancer l'index pour le prochain appel
                self._round_robin_index[api_name] = (idx + 1) % len(keys)
                logger.debug(f"[KEY MANAGER] {api_name.upper()} → clé idx={idx}")
                return key
                
        # Aucune clé disponible. ⚠️ Distinguer le passager du définitif : le tableau de
        # bord classe « TOUTES LES CLÉS » et « ZÉRO clé saine » en CRITICAL
        # (dashboard/backend/error_analyzer.py). Depuis que la cascade demande sa clé pour
        # les 4 fournisseurs, un simple quota Groq par minute passerait ici plusieurs fois
        # par message — et une alerte qui crie pour du nominal est une alerte qu'on
        # apprend à ignorer. Un cooldown derrière lequel la cascade bascule n'est pas une
        # panne ; une clé révoquée, si.
        revoquees = [k for k in keys if not self.apis[api_name]["status"][k]["valid"]]
        if revoquees:
            logger.error(f"🚨 [CRITIQUE] {api_name.upper()} : TOUTES LES CLÉS SONT ÉPUISÉES OU RÉVOQUÉES !")
        else:
            reprise = max(0, int(min(
                self._reprise(self.apis[api_name]["status"][k], modele) for k in keys
            ) - now))
            logger.warning(f"⏳ [KEY MANAGER] {api_name.upper()} : aucune clé libre avant {reprise}s (cooldown). L'appelant bascule.")
        return None  # Plus d'essai à l'aveugle, on avoue l'échec pour permettre le fallback

    def is_api_available(self, api_name, modele=None):
        """Vérifie s'il reste au moins une clé saine pour cette API (et ce modèle)."""
        if api_name not in self.apis: return False
        now = datetime.now().timestamp()
        for key in self.apis[api_name]["keys"]:
            status = self.apis[api_name]["status"][key]
            if self._est_libre(status, modele, now):
                return True
        return False
    
    def report_error(self, api_name, key, error_code, retry_delay_s=None, modele=None):
        """Signale une erreur sur une clé pour qu'elle soit écartée ou mise en quarantaine.

        `modele` dit QUEL modèle a pris l'erreur. Il ne change rien sauf sur un 429 chez
        un fournisseur de `QUOTA_PAR_MODELE` : là, le cooldown est posé sur le couple
        (clé, modèle) et les autres échelons de la même clé continuent de servir.
        Omis — ou fournisseur inconnu de la liste — le cooldown porte sur la CLE, comme
        avant : c'est le comportement le plus prudent, et il reste le défaut.
        """
        if api_name not in self.apis or key not in self.apis[api_name]["status"]:
            return
            
        status = self.apis[api_name]["status"][key]
        now = datetime.now().timestamp()
        
        # Erreurs fatales (Clé révoquée, interdite, ou invalide)
        if error_code in [401, 403]:
            logger.error(f"❌ [KEY MANAGER] {api_name.upper()} : Clé DÉSACTIVÉE PERMANEMMENT (Erreur {error_code}).")
            status["valid"] = False

        # Erreurs temporaires (Quotas, surcharges)
        elif error_code == 429:
            if retry_delay_s is not None:
                try:
                    delay = float(retry_delay_s)
                    cooldown_duration = max(5, min(900, int(delay)))
                except (ValueError, TypeError):
                    cooldown_duration = 60
            else:
                cooldown_duration = 60
            if modele and api_name in QUOTA_PAR_MODELE:
                status.setdefault("cooldown_modele", {})[modele] = now + cooldown_duration
                logger.warning(
                    f"⚠️ [KEY MANAGER] {api_name.upper()} : {modele} mis en QUARANTAINE "
                    f"pour {cooldown_duration}s sur cette clé (Erreur {error_code}). "
                    f"Les autres modèles de la clé ne sont PAS touchés."
                )
            else:
                status["cooldown"] = now + cooldown_duration
                logger.warning(f"⚠️ [KEY MANAGER] {api_name.upper()} : Clé mise en QUARANTAINE pour {cooldown_duration}s (Erreur {error_code}).")

            # Log instructif pour montrer à l'admin qu'il bascule
            self._log_remaining_keys(api_name, modele)
        elif error_code in self.cooldown_times:
            logger.warning(f"⚠️ [API FAIL] {api_name.upper()} : Incident modèle/requête signalé (Erreur {error_code}). La santé de la clé n'est pas affectée.")

            
        try:
            key_index = self.apis[api_name]["keys"].index(key)
        except ValueError:
            key_index = -1
            
        # Synchronisation avec la table api_key_status en DB
        #
        # ⚠️ On y écrit le cooldown de la CLE, jamais celui d'un couple (clé, modèle) :
        # la table n'a pas de colonne `modele`, et y ranger un seau par-modèle ferait dire
        # au tableau de bord « cette clé est en quarantaine » alors qu'elle sert encore
        # cinq échelons. L'incident reste visible : la ligne porte son code d'erreur.
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

    def _log_remaining_keys(self, api_name, modele=None):
        """Affiche combien de clés sont encore opérationnelles sur ce pool."""
        now = datetime.now().timestamp()
        saines = 0
        for key in self.apis[api_name]["keys"]:
            status = self.apis[api_name]["status"][key]
            if self._est_libre(status, modele, now):
                saines += 1
        
        if saines > 0:
            logger.info(f"🔄 [KEY MANAGER] Bascule en cours... Il reste {saines} clé(s) saine(s) pour {api_name.upper()}.")
        elif any(not self.apis[api_name]["status"][k]["valid"] for k in self.apis[api_name]["keys"]):
            logger.error(f"🚨 [KEY MANAGER] ZÉRO clé saine restante pour {api_name.upper()} !!")
        else:
            # Toutes en cooldown, aucune révoquée : la cascade a des échelons derrière.
            logger.warning(f"⏳ [KEY MANAGER] {api_name.upper()} : plus de clé libre pour l'instant, l'échelon sera sauté.")

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
            if self._est_libre(status, None, now):
                healthy_keys += 1
        
        return {
            "status": "healthy" if healthy_keys > 0 else ("degraded" if total_keys > 0 else "no_keys"),
            "total_keys": total_keys,
            "healthy_keys": healthy_keys,
            "current_index": api.get("index", 0)
        }
