# ⚠️ FICHIER GENERE — NE PAS EDITER ICI.
# Source : shared/bot_logger.py — modifier la source puis relancer :
#     python tools/vendor_core.py
# La sonde tools/sonde_core_drift.py echoue si cette copie diverge.

# SHARED LOGGING MODULE FOR DISCORD BOTS

import logging
import os
from datetime import datetime
import json
import queue
import sqlite3
import threading
import time
import traceback
from pathlib import Path
from logging.handlers import RotatingFileHandler

class JSONLHandler(logging.Handler):
    """Handler qui écrit les logs en JSON Lines pour le dashboard."""
    
    def __init__(self, log_dir, bot_name):
        super().__init__()
        self.filepath = os.path.join(log_dir, f"{bot_name}_structured.jsonl")
    
    def emit(self, record):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "bot": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno
        }
        # Ajouter des champs extra si présents (permet un tracking avancé depuis d'autres modules sans changer la signature de base)
        for key in ["api_name", "api_key_index", "error_code", "user_id", "channel_id", "latency_ms"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        
        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # Ne jamais crasher le bot pour un log

_ECRIVAIN_HS = object()
_queue = queue.Queue(maxsize=1000)
_writer_thread = None
_writer_lock = threading.Lock()

# --- Alarme de panne du journal --------------------------------------------
# Une panne de base ne doit pas produire UNE ligne au tout debut puis plus rien :
# c'est exactement ce qui a laisse les 6 bots muets deux jours (11-13/09) sans
# que `[ERROR EVENTS]` apparaisse une seule fois. On crie donc de facon ESPACEE,
# et chaque cri porte le nombre d'evenements avales depuis le precedent.
_INTERVALLE_CRI = 300.0    # au plus une ligne toutes les 5 min
_DELAI_REPRISE = 60.0      # base morte : on ne retente pas un thread avant 60 s

_JOURNAL_ERREUR = False       # une panne est-elle en cours ?
_DEBUT_PANNE = None           # instant du premier echec de la panne en cours
_DERNIER_CRI = None           # instant du dernier cri emis
_ECHECS_AVALES = 0            # echecs encaisses depuis ce dernier cri
_DERNIER_ECHEC_INIT = None    # instant du dernier echec d'initialisation

def _maintenant():
    """Horloge du module. Indirection VOULUE : les tests la remplacent pour
    verifier la temporisation sans dormir."""
    return time.monotonic()

def _duree_lisible(secondes):
    minutes = int(secondes // 60)
    if minutes < 1:
        return f"{int(secondes)} s"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"

def _crier_panne(quoi, erreur):
    """Journalise l'echec au plus une fois toutes les `_INTERVALLE_CRI` secondes,
    en portant la duree de la panne et le nombre d'evenements perdus depuis le
    cri precedent.

    N'est appele QUE depuis le thread ecrivain, et il n'y en a qu'un a la fois
    (`_writer_lock` dans `_ensure_thread`) : pas de verrou supplementaire ici.
    """
    global _JOURNAL_ERREUR, _DEBUT_PANNE, _DERNIER_CRI, _ECHECS_AVALES

    maintenant = _maintenant()
    if not _JOURNAL_ERREUR:
        _JOURNAL_ERREUR = True
        _DEBUT_PANNE = maintenant
        _DERNIER_CRI = None
        _ECHECS_AVALES = 0

    _ECHECS_AVALES += 1
    if _DERNIER_CRI is not None and (maintenant - _DERNIER_CRI) < _INTERVALLE_CRI:
        return

    perdus = _ECHECS_AVALES
    accord = "s" if perdus > 1 else ""
    logging.getLogger("bot_logger").error(
        f"[ERROR EVENTS] {quoi} en échec depuis "
        f"{_duree_lisible(maintenant - _DEBUT_PANNE)} "
        f"({perdus} événement{accord} perdu{accord}) : {erreur}"
    )
    _DERNIER_CRI = maintenant
    _ECHECS_AVALES = 0

def _fin_de_panne():
    """Une ecriture a reussi : la panne est close, le prochain echec criera
    immediatement au lieu d'attendre la fin de l'intervalle en cours."""
    global _JOURNAL_ERREUR, _DEBUT_PANNE, _DERNIER_CRI, _ECHECS_AVALES
    _JOURNAL_ERREUR = False
    _DEBUT_PANNE = None
    _DERNIER_CRI = None
    _ECHECS_AVALES = 0

def _ensure_thread():
    global _writer_thread
    with _writer_lock:
        if _writer_thread is not None and _writer_thread.is_alive():
            return
        # ⚠️ Ne PAS supprimer la relance : c'est elle qui fait repartir le
        # journal tout seul quand la base redevient saine. C'est sa FREQUENCE qui
        # etait fautive — une base morte donnait un thread cree, une connexion
        # tentee et un abandon silencieux PAR reaction recue.
        if (_DERNIER_ECHEC_INIT is not None
                and (_maintenant() - _DERNIER_ECHEC_INIT) < _DELAI_REPRISE):
            return
        _writer_thread = threading.Thread(target=_writer_loop, daemon=True, name="ErrorEventWriter")
        _writer_thread.start()

def _empiler(item):
    try:
        _queue.put_nowait(item)
    except queue.Full:
        # Silence VOULU : la file est bornee a 1000 justement pour que le journal
        # ne puisse jamais faire grossir la memoire du bot sans limite. Perdre une
        # ligne d'erreur est preferable a la journaliser ici, ce qui rappellerait
        # ce meme handler.
        pass

def _writer_loop():
    global _DERNIER_ECHEC_INIT
    
    data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
    db_path = os.path.join(data_dir, "bots_database.db")
    
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=20)
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            # Silence VOULU : un reglage de confort, pas une condition de marche.
            # Sur un bind mount Docker/Windows un PRAGMA peut etre refuse sans que
            # la base soit inutilisable — on continue avec le reglage par defaut.
            pass

        # ⚠️ Ce CREATE TABLE doit rester STRICTEMENT identique a celui de
        # shared/shared_database.py (init_database) — contraintes et valeurs par
        # defaut comprises. Il ne sert que si un bot demarre avant que le
        # dashboard n'ait cree la base. tests/test_error_events_handler.py
        # compare les deux et echoue a la moindre divergence.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                bot_name TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                error_traceback TEXT,
                context_json TEXT,
                severity TEXT DEFAULT 'ERROR',
                resolved INTEGER DEFAULT 0,
                report_generated INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reactions_repliques (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                bot_name TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                retiree INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        _DERNIER_ECHEC_INIT = None
    except Exception as e:
        # Le thread meurt ici — c'est voulu — mais `_ensure_thread` ne doit pas en
        # relancer un par evenement recu tant que la base est morte.
        _DERNIER_ECHEC_INIT = _maintenant()
        _crier_panne("Initialisation SQLite", e)
        if conn:
            conn.close()
        return

    while True:
        try:
            item = _queue.get()
            try:
                if item is _ECRIVAIN_HS:
                    break
                
                if item.get("_type") == "reaction" or "emoji" in item:
                    conn.execute("""
                        INSERT INTO reactions_repliques (
                            timestamp, bot_name, message_id, channel_id,
                            user_id, emoji, retiree
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item["timestamp"], item["bot_name"], item["message_id"],
                        item["channel_id"], item["user_id"], item["emoji"],
                        item.get("retiree", 0)
                    ))
                else:
                    conn.execute("""
                        INSERT INTO error_events (
                            timestamp, bot_name, error_type, error_message,
                            error_traceback, context_json, severity, resolved, report_generated
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item["timestamp"], item["bot_name"], item["error_type"],
                        item["error_message"], item["error_traceback"], item["context_json"],
                        item["severity"], 0, 0
                    ))
                conn.commit()
                if _JOURNAL_ERREUR:
                    _fin_de_panne()
            finally:
                _queue.task_done()
        except Exception as e:
            _crier_panne("Écriture SQLite", e)

            if conn:
                try:
                    conn.rollback()
                except Exception:
                    # Silence VOULU : le rollback est deja un rattrapage. S'il echoue
                    # a son tour, la connexion est perdue et il n'y a rien de plus a
                    # tenter — l'echec initial vient d'etre journalise juste au-dessus.
                    pass

    if conn:
        conn.close()

class ErrorEventHandler(logging.Handler):
    def __init__(self, bot_name):
        super().__init__()
        self.bot_name = bot_name
        _ensure_thread()
        
    def emit(self, record):
        if record.name == __name__ or record.name == "bot_logger":
            return
            
        try:
            # ⚠️ `exc_info` peut valoir (None, None, None) : c'est ce que `logging`
            # pose quand on ecrit `logger.error(..., exc_info=True)` HORS d'un bloc
            # `except`. Tester le tuple seul ferait lever `None.__name__`, et le
            # `except` plus bas avalerait l'evenement entier en silence.
            exc = record.exc_info if record.exc_info and record.exc_info[0] else None

            error_type = exc[0].__name__ if exc else record.module

            error_message = record.getMessage()
            if error_message and len(error_message) > 2000:
                error_message = error_message[:1997] + "..."

            error_traceback = None
            if exc:
                error_traceback = "".join(traceback.format_exception(*exc))
                if len(error_traceback) > 8000:
                    error_traceback = error_traceback[:7997] + "..."
                    
            context_json = json.dumps({"module": record.module, "funcName": record.funcName, "lineno": record.lineno})
            
            item = {
                "timestamp": datetime.now().isoformat(),
                "bot_name": self.bot_name,
                "error_type": error_type,
                "error_message": error_message,
                "error_traceback": error_traceback,
                "context_json": context_json,
                "severity": record.levelname
            }
            
            _empiler(item)
        except Exception:
            # Silence VOULU, et c'est la regle du module : « Ne jamais crasher le bot
            # pour un log ». `Handler.handle` ne rattrape rien — une exception levee
            # ici remonterait dans `on_message`. On ne peut pas non plus la
            # journaliser : ce handler serait rappele.
            pass


def enregistrer_reaction(bot_name: str, message_id: int, channel_id: int, user_id: int, emoji: str, retiree: int = 0):
    """Enregistre une réaction sur une réplique du bot via la file d'attente (thread écrivain)."""
    try:
        _ensure_thread()
        item = {
            "_type": "reaction",
            "timestamp": datetime.now().isoformat(),
            "bot_name": bot_name,
            "message_id": int(message_id),
            "channel_id": int(channel_id),
            "user_id": int(user_id),
            "emoji": str(emoji),
            "retiree": int(retiree),
        }
        _empiler(item)
    except Exception:
        # Silence VOULU : ne jamais bloquer ou crasher le bot pour une réaction.
        pass


def setup_logger(bot_name: str, log_dir: str = "logs"):
    """
    Configure un logger avec sortie fichier, console et JSONL (Dashboard).
    
    Args:
        bot_name: Nom du bot (ex: "sheogorath", "maiq", "alfred")
        log_dir: Dossier des logs (défaut: "logs")
    
    Returns:
        Logger configuré
    """
    # Configuration du logger
    logger = logging.getLogger(bot_name)
    logger.setLevel(logging.INFO)
    
    # Éviter les doublons si déjà configuré
    if logger.handlers:
        return logger
    
    # Sous pytest (ou sur demande), on ne garde QUE la console : les handlers
    # fichier/JSONL écriraient dans les logs/ partagés que le dashboard affiche
    # comme des événements des bots LIVE (fausses alertes, heure locale vs UTC).
    console_only = bool(
        os.getenv("BOTS_LOG_CONSOLE_ONLY") or os.getenv("PYTEST_CURRENT_TEST")
    )
    
    # Format
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-7s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Handler console (toujours dispo : c'est le filet de sécurité capturé par
    # `docker logs`, donc on l'ajoute en premier et sans condition)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if not console_only:
        # Créer le dossier logs si nécessaire
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Nom du fichier avec date
        log_filename = os.path.join(log_dir, f"{bot_name}_{datetime.now().strftime('%Y-%m-%d')}.log")

        # Handler fichier (rotation : 5 MB max, 3 backups).
        # IMPORTANT : ne JAMAIS faire planter le bot si le fichier de log n'est pas
        # ouvrable (ex. bind-mount Docker Desktop Windows où les fichiers existants
        # apparaissent root:644 et l'utilisateur non-root ne peut pas les rouvrir).
        # On dégrade proprement : console seule au lieu de crasher au démarrage.
        try:
            file_handler = RotatingFileHandler(
                log_filename, encoding='utf-8',
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=3
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning(
                f"⚠️ [LOGGER] Fichier de log '{log_filename}' non ouvrable "
                f"({e}). Journalisation fichier désactivée, console seule."
            )

        # Handler JSON Lines pour le dashboard (l'emit est déjà tolérant aux erreurs)
        jsonl_handler = JSONLHandler(log_dir, bot_name)
        jsonl_handler.setLevel(logging.INFO)
        logger.addHandler(jsonl_handler)
        
        # Handler événements d'erreur pour la vue Analyse Erreurs du dashboard.
        # Posé AVANT la boucle ci-dessous : c'est elle qui recopie logger.handlers
        # sur les loggers des modules partagés.
        erreurs_handler = ErrorEventHandler(bot_name)
        erreurs_handler.setLevel(logging.ERROR)
        logger.addHandler(erreurs_handler)
        
        # ⚠️ Chaque nom doit correspondre a un `logging.getLogger("<nom>")` REEL dans
        # le module partage : un nom sans logger derriere ne cable rien, il cree un
        # objet vide. `response_memory` et `transcript` n'en ont pas — ils ne sont
        # pas dans cette liste.
        for shared_name in ("smart_router", "llm_cascade", "media_handler",
                            "safe_client", "discord_status", "discord_profile",
                            "api_manager", "api_tracking", "anti_tic",
                            "repartee_lessons", "boucles", "server_events",
                            "bot_logger"):
            shared_logger = logging.getLogger(shared_name)
            shared_logger.setLevel(logging.INFO)
            if not shared_logger.handlers:
                for h in logger.handlers:
                    shared_logger.addHandler(h)
    
    logger.info(f"=== {bot_name.upper()} STARTED ===")
    
    return logger


# logger.info("Message de log")
# logger.warning("Avertissement")
# logger.error("Erreur")

def reinitialiser_pour_tests():
    global _writer_thread, _DERNIER_ECHEC_INIT
    while not _queue.empty():
        try:
            _queue.get_nowait()
            _queue.task_done()
        except queue.Empty:
            break
            
    if _writer_thread is not None and _writer_thread.is_alive():
        _empiler(_ECRIVAIN_HS)
        _writer_thread.join(timeout=5.0)
    
    _fin_de_panne()
    _DERNIER_ECHEC_INIT = None
    _writer_thread = None
