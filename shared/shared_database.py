# -*- coding: utf-8 -*-

# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

"""
Base de données SQLite partagée pour les bots Discord.
Gère : utilisateurs, réputation, anniversaires, interactions, quêtes, logs.
"""
import sqlite3
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import json

DATA_DIR = os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = Path(DATA_DIR) / "bots_database.db"


def get_connection() -> sqlite3.Connection:
    """Crée une connexion à la base de données avec gestion de la concurrence (WAL)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=20)
    conn.row_factory = sqlite3.Row
    # Activation du mode WAL (Write-Ahead Logging) pour les écritures concurrentes
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.Error as e:
        print(f"⚠️ [DB] Impossible d'activer WAL: {e}")
    return conn


def init_database():
    """Initialise toutes les tables de la base de données."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table des utilisateurs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            display_name TEXT,
            first_interaction TEXT,
            last_interaction TEXT,
            total_interactions INTEGER DEFAULT 0
        )
    """)
    
    # Table de réputation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reputation (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0,
            level TEXT DEFAULT 'Inconnu',
            last_gain TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Table des anniversaires
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS birthdays (
            user_id INTEGER PRIMARY KEY,
            birth_day INTEGER NOT NULL,
            birth_month INTEGER NOT NULL,
            registered_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Table des interactions (pour tracker qui a interagi avec quel bot)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_name TEXT NOT NULL,
            interaction_type TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Table des quêtes quotidiennes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            quest_type TEXT NOT NULL,
            quest_date TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            reward INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Table des logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            bot_name TEXT NOT NULL,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            user_id INTEGER,
            channel_id INTEGER
        )
    """)
    
    # Table de configuration (maintenance, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    
    # Table des événements d'erreur (pour le dashboard)
    cursor.execute("""
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
    
    # Table des logs d'audit (pour tracer les actions sur le dashboard)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user TEXT NOT NULL,
            action TEXT NOT NULL,
            bot_name TEXT,
            details TEXT
        )
    """)
    
    # Table des interactions entre bots (NOUVEAU - pour stats des duels)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot1 TEXT NOT NULL,
            bot2 TEXT NOT NULL,
            channel_id INTEGER,
            guild_id INTEGER,
            triggered INTEGER DEFAULT 1,
            timestamp TEXT NOT NULL,
            success INTEGER DEFAULT 1
        )
    """)

    # Table des énigmes actives (Pour M'aiq / Sheogorath Shared State)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS riddles (
            channel_id INTEGER PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            hint TEXT,
            reward INTEGER DEFAULT 15,
            started_at TEXT NOT NULL,
            message_id INTEGER,  -- ID du message épinglé
            participants TEXT DEFAULT '[]' -- Liste JSON des user_ids ayant participé
        )
    """)
    
    # Table d'historique des énigmes (Anti-Doublon)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS riddle_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_hash TEXT UNIQUE,
            question TEXT,
            answer TEXT,
            timestamp TEXT
        )
    """)

    # Check if columns exist (Migration Manual)
    try:
        cursor.execute("SELECT message_id FROM riddles LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE riddles ADD COLUMN message_id INTEGER")
            print("[DATABASE] Colonne message_id ajoutee a riddles.")
        except Exception as e:
            print(f"[DATABASE] Erreur migration riddles (message_id): {e}")

    try:
        cursor.execute("SELECT participants FROM riddles LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE riddles ADD COLUMN participants TEXT DEFAULT '[]'")
            print("[DATABASE] Colonne participants ajoutee a riddles.")
        except Exception as e:
            print(f"[DATABASE] Erreur migration riddles (participants): {e}")

    try:
        cursor.execute("SELECT winners FROM riddles LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE riddles ADD COLUMN winners TEXT DEFAULT '[]'")
            print("[DATABASE] Colonne winners ajoutee a riddles.")
        except Exception as e:
            print(f"[DATABASE] Erreur migration riddles (winners): {e}")

    try:
        cursor.execute("SELECT answer FROM riddle_history LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE riddle_history ADD COLUMN answer TEXT")
            print("[DATABASE] Colonne answer ajoutee a riddle_history.")
        except Exception as e:
            print(f"[DATABASE] Erreur migration riddle_history (answer): {e}")

    try:
        cursor.execute("SELECT is_impossible FROM riddles LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE riddles ADD COLUMN is_impossible INTEGER DEFAULT 0")
            print("[DATABASE] Colonne is_impossible ajoutee a riddles.")
        except Exception as e:
            print(f"[DATABASE] Erreur migration riddles (is_impossible): {e}")

    try:
        cursor.execute("SELECT riddle_streak FROM reputation LIMIT 1")
    except sqlite3.OperationalError:
        try:
            cursor.execute("ALTER TABLE reputation ADD COLUMN riddle_streak INTEGER DEFAULT 0")
            print("[DATABASE] Colonne riddle_streak ajoutee a reputation.")
        except Exception as e:
            print(f"[DATABASE] Erreur migration reputation (riddle_streak): {e}")

    # Tables pour le système de mini-jeux partagé (cooldowns, daily caps et pvp pairs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_cooldowns (
            user_id INTEGER,
            game_key TEXT,
            bot_name TEXT,
            last_reward_time REAL,
            PRIMARY KEY (user_id, game_key, bot_name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_daily_caps (
            user_id INTEGER,
            date_str TEXT,
            points INTEGER,
            PRIMARY KEY (user_id, date_str)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_pvp_cooldowns (
            pair_key TEXT PRIMARY KEY,
            last_reward_time REAL
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DATABASE] Base initialisee: {DB_PATH}")



def add_riddle_participant(channel_id: int, user_id: int):
    """Ajoute un participant à l'énigme active."""
    try:
        riddle = get_active_riddle(channel_id)
        if not riddle: 
            print(f"⚠️ [DB] add_riddle_participant: Pas d'énigme pour {channel_id}")
            return
        
        participants = riddle.get("participants", [])
        if user_id not in participants:
            participants.append(user_id)
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE riddles SET participants = ? WHERE channel_id = ?", (json.dumps(participants), channel_id))
            conn.commit()
            conn.close()
            print(f"✅ [DB] Participant ajouté: {user_id} (Total: {len(participants)})")
        else:
            print(f"ℹ️ [DB] Participant {user_id} déjà présent.")
    except Exception as e:
        print(f"❌ [DB] Erreur add_riddle_participant: {e}")

def get_riddle_participants(channel_id: int) -> List[int]:
    """Récupère la liste des IDs des participants."""
    riddle = get_active_riddle(channel_id)
    if riddle:
        return riddle.get("participants", [])
    return []


def add_riddle_winner(channel_id: int, user_id: int):
    """Ajoute un gagnant à l'énigme active."""
    try:
        riddle = get_active_riddle(channel_id)
        if not riddle: 
            print(f"⚠️ [DB] add_riddle_winner: Pas d'énigme pour {channel_id}")
            return
        
        winners = riddle.get("winners", [])
        if user_id not in winners:
            winners.append(user_id)
            
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE riddles SET winners = ? WHERE channel_id = ?", (json.dumps(winners), channel_id))
            conn.commit()
            conn.close()
            print(f"✅ [DB] Gagnant ajouté: {user_id} (Total: {len(winners)})")
        else:
            print(f"ℹ️ [DB] Gagnant {user_id} déjà présent.")
    except Exception as e:
        print(f"❌ [DB] Erreur add_riddle_winner: {e}")

def get_riddle_winners(channel_id: int) -> List[int]:
    """Récupère la liste des IDs des gagnants."""
    riddle = get_active_riddle(channel_id)
    if riddle:
        return riddle.get("winners", [])
    return []



# GESTION DES UTILISATEURS

def get_or_create_user(user_id: int, username: str, display_name: str = None) -> Dict:
    """Récupère ou crée un utilisateur."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    now = datetime.now().isoformat()
    
    if user is None:
        try:
            # Utiliser INSERT OR IGNORE pour éviter les crashs si le user existe déjà (race condition)
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, display_name, first_interaction, last_interaction, total_interactions)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (user_id, username, display_name or username, now, now))
            
            # Créer aussi une entrée de réputation (si elle n'existe pas déjà)
            cursor.execute("INSERT OR IGNORE INTO reputation (user_id, points) VALUES (?, 0)", (user_id,))
            conn.commit()
        except Exception as e:
            print(f"⚠️ [DATABASE] Erreur lors de la création du user {user_id}: {e}")
        
        # Re-sélectionner après insertion
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    else:
        # Mettre à jour last_interaction et total_interactions
        try:
            cursor.execute("""
                UPDATE users SET last_interaction = ?, total_interactions = total_interactions + 1
                WHERE user_id = ?
            """, (now, user_id))
            conn.commit()
        except Exception as e:
            print(f"⚠️ [DATABASE] Erreur lors de l'update du user {user_id}: {e}")
    
    conn.close()
    
    # Si user est toujours None (ex: échec d'insertion mystérieux), renvoyer une structure par défaut pour éviter le crash
    if user is None:
        return {
            "user_id": user_id, 
            "username": username, 
            "display_name": display_name or username,
            "total_interactions": 1,
            "reputation": 0
        }
        
    return dict(user)


def has_user_interacted(user_id: int) -> bool:
    """Vérifie si un utilisateur a déjà interagi avec les bots."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_user_interactions(user_id: int) -> List[Dict]:
    """Récupère les interactions d'un utilisateur."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM interactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 50", (user_id,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def log_interaction(user_id: int, bot_name: str, interaction_type: str = "message"):
    """Enregistre une interaction."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO interactions (user_id, bot_name, interaction_type, timestamp)
        VALUES (?, ?, ?, ?)
    """, (user_id, bot_name, interaction_type, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# GESTION DE LA RÉPUTATION

def get_reputation(user_id: int) -> Dict:
    """Récupère la réputation d'un utilisateur."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reputation WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return dict(result)
    return {"user_id": user_id, "points": 0, "level": "Inconnu"}


def add_reputation(user_id: int, points: int, reason: str = None) -> int:
    """Ajoute ou retire des points de réputation."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # S'assurer que l'utilisateur existe
    cursor.execute("SELECT points FROM reputation WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if result is None:
        cursor.execute("INSERT INTO reputation (user_id, points) VALUES (?, ?)", (user_id, points))
        new_points = points
    else:
        new_points = result[0] + points
        cursor.execute("""
            UPDATE reputation SET points = ?, last_gain = ?, level = ?
            WHERE user_id = ?
        """, (new_points, datetime.now().isoformat(), get_reputation_level(new_points), user_id))
    
    conn.commit()
    conn.close()
    return new_points


def get_reputation_level(points: int) -> str:
    """Détermine le niveau de réputation (avec Emoji)."""
    if points < 0:
        return "Paria 🐀"
    elif points < 50:
        return "Vagabond 🍃"
    elif points < 150:
        return "Apprenti 🕯️"
    elif points < 300:
        return "Initié 📜"
    elif points < 600:
        return "Adepte 🔮"
    elif points < 1000:
        return "Érudit 📚"
    elif points < 2000:
        return "Maître 🧙‍♂️"
    elif points < 5000:
        return "Champion 🏆"
    else:
        return "Demi-Prince 👑"

def get_next_rank_info(points: int) -> Tuple[int, str]:
    """Retourne (points_requis, prochain_rang)."""
    if points < 0: return (0, "Vagabond 🍃")
    elif points < 50: return (50, "Apprenti 🕯️")
    elif points < 150: return (150, "Initié 📜")
    elif points < 300: return (300, "Adepte 🔮")
    elif points < 600: return (600, "Érudit 📚")
    elif points < 1000: return (1000, "Maître 🧙‍♂️")
    elif points < 2000: return (2000, "Champion 🏆")
    elif points < 5000: return (5000, "Demi-Prince 👑")
    else: return (999999, "Divinité 🌌")


def add_riddle_streak(user_id: int) -> int:
    """Incrémente la série de victoires aux énigmes."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT riddle_streak FROM reputation WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    new_streak = 1
    if result:
        new_streak = (result[0] or 0) + 1
        cursor.execute("UPDATE reputation SET riddle_streak = ? WHERE user_id = ?", (new_streak, user_id))
    else:
        # Should normally exist if user played
        cursor.execute("UPDATE reputation SET riddle_streak = ? WHERE user_id = ?", (new_streak, user_id))
        
    conn.commit()
    conn.close()
    return new_streak

def reset_riddle_streak(user_id: int):
    """Réinitialise la série de victoires."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE reputation SET riddle_streak = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_riddle_streak(user_id: int) -> int:
    """Récupère la série actuelle."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT riddle_streak FROM reputation WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0


def get_reputation_leaderboard(limit: int = 10) -> List[Dict]:
    """Récupère le classement de réputation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.user_id, r.points, r.level, u.username, u.display_name
        FROM reputation r
        JOIN users u ON r.user_id = u.user_id
        ORDER BY r.points DESC
        LIMIT ?
    """, (limit,))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# GESTION DES ANNIVERSAIRES

def set_birthday(user_id: int, day: int, month: int) -> bool:
    """Enregistre l'anniversaire d'un utilisateur."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO birthdays (user_id, birth_day, birth_month, registered_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, day, month, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ [BIRTHDAY] Erreur: {e}")
        conn.close()
        return False


def get_todays_birthdays() -> List[int]:
    """Récupère les utilisateurs dont c'est l'anniversaire aujourd'hui (et qui ont interagi)."""
    today = date.today()
    conn = get_connection()
    cursor = conn.cursor()
    
    # Seulement les utilisateurs qui ont interagi avec les bots
    cursor.execute("""
        SELECT b.user_id 
        FROM birthdays b
        JOIN users u ON b.user_id = u.user_id
        WHERE b.birth_day = ? AND b.birth_month = ?
        AND u.total_interactions > 0
    """, (today.day, today.month))
    
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results


# GESTION DES QUÊTES

def get_daily_quests(user_id: int) -> List[Dict]:
    """Récupère les quêtes quotidiennes d'un utilisateur."""
    today = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM quests 
        WHERE user_id = ? AND quest_date = ?
    """, (user_id, today))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def create_daily_quests(user_id: int) -> List[Dict]:
    """Crée les quêtes quotidiennes pour un utilisateur."""
    import random
    
    today = date.today().isoformat()
    
    # Vérifier si des quêtes existent déjà
    existing = get_daily_quests(user_id)
    if existing:
        return existing
    
    # Types de quêtes disponibles
    quest_types = [
        ("chat_sheogorath", 10, "Discuter avec Sheogorath"),
        ("chat_maiq", 10, "Écouter une rumeur de M'aiq"),
        ("chat_alfred", 10, "Demander un service à Alfred"),
        ("participate_game", 15, "Participer à un mini-jeu"),
        ("make_bot_laugh", 20, "Faire rire un bot"),
        ("help_someone", 15, "Aider un autre membre"),
    ]
    
    # Sélectionner 3 quêtes aléatoires
    selected = random.sample(quest_types, min(3, len(quest_types)))
    
    conn = get_connection()
    cursor = conn.cursor()
    
    for quest_type, reward, _ in selected:
        cursor.execute("""
            INSERT INTO quests (user_id, quest_type, quest_date, completed, reward)
            VALUES (?, ?, ?, 0, ?)
        """, (user_id, quest_type, today, reward))
    
    conn.commit()
    conn.close()
    
    return get_daily_quests(user_id)


def complete_quest(user_id: int, quest_type: str) -> Optional[int]:
    """Complète une quête et retourne la récompense."""
    today = date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, reward FROM quests 
        WHERE user_id = ? AND quest_type = ? AND quest_date = ? AND completed = 0
    """, (user_id, quest_type, today))
    
    result = cursor.fetchone()
    if result:
        quest_id, reward = result
        cursor.execute("UPDATE quests SET completed = 1 WHERE id = ?", (quest_id,))
        conn.commit()
        conn.close()
        
        # Ajouter la réputation
        add_reputation(user_id, reward, f"Quête complétée: {quest_type}")
        return reward
    
    conn.close()
    return None


# GESTION DE LA CONFIGURATION (MAINTENANCE, ETC.)

def get_config(key: str, default: str = None) -> Optional[str]:
    """Récupère une valeur de configuration."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else default


def set_config(key: str, value: str):
    """Définit une valeur de configuration."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO config (key, value, updated_at)
        VALUES (?, ?, ?)
    """, (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def is_maintenance_mode() -> bool:
    """Vérifie si le mode maintenance est activé."""
    return get_config("maintenance_mode", "off") == "on"


def set_maintenance_mode(enabled: bool):
    """Active ou désactive le mode maintenance."""
    set_config("maintenance_mode", "on" if enabled else "off")


# GESTION DES LOGS

def log_event(bot_name: str, level: str, message: str, user_id: int = None, channel_id: int = None):
    """Enregistre un événement dans les logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO logs (timestamp, bot_name, level, message, user_id, channel_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), bot_name, level, message, user_id, channel_id))
    conn.commit()
    conn.close()


def get_recent_logs(bot_name: str = None, limit: int = 50) -> List[Dict]:
    """Récupère les logs récents."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if bot_name:
        cursor.execute("""
            SELECT * FROM logs WHERE bot_name = ?
            ORDER BY timestamp DESC LIMIT ?
        """, (bot_name, limit))
    else:
        cursor.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# GESTION DES INTERACTIONS ENTRE BOTS (NOUVEAU)

def log_bot_interaction(bot1: str, bot2: str, channel_id: int = None, guild_id: int = None, triggered: bool = True, success: bool = True):
    """Enregistre une interaction entre deux bots (duels)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bot_interactions (bot1, bot2, channel_id, guild_id, triggered, timestamp, success)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (bot1, bot2, channel_id, guild_id, 1 if triggered else 0, datetime.now().isoformat(), 1 if success else 0))
    conn.commit()
    conn.close()


def get_bot_interaction_stats(bot_name: str = None, days: int = 7) -> Dict[str, Any]:
    """Récupère les statistiques d'interactions des bots."""
    from datetime import timedelta
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    stats = {}
    
    if bot_name:
        # Stats pour un bot spécifique
        cursor.execute("""
            SELECT bot2 as opponent, COUNT(*) as count, SUM(triggered) as triggered_count
            FROM bot_interactions
            WHERE bot1 = ? AND timestamp > ?
            GROUP BY bot2
            ORDER BY count DESC
        """, (bot_name, cutoff_date))
        
        stats['opponents'] = [dict(row) for row in cursor.fetchall()]
        
        # Total d'interactions
        cursor.execute("""
            SELECT COUNT(*) as total, SUM(triggered) as triggered
            FROM bot_interactions
            WHERE bot1 = ? AND timestamp > ?
        """, (bot_name, cutoff_date))
        
        result = cursor.fetchone()
        stats['total'] = result[0] if result else 0
        stats['triggered'] = result[1] if result else 0
    else:
        # Stats globales
        cursor.execute("""
            SELECT bot1, bot2, COUNT(*) as count
            FROM bot_interactions
            WHERE timestamp > ?
            GROUP BY bot1, bot2
            ORDER BY count DESC
            LIMIT 20
        """, (cutoff_date,))
        
        stats['top_pairs'] = [dict(row) for row in cursor.fetchall()]
        
        # Total par bot
        cursor.execute("""
            SELECT bot1, COUNT(*) as count
            FROM bot_interactions
            WHERE timestamp > ?
            GROUP BY bot1
            ORDER BY count DESC
        """, (cutoff_date,))
        
        stats['by_bot'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return stats

def log_error_event(bot_name, error_type, error_message, 
                    traceback_str=None, context=None, severity="ERROR"):
    """Enregistre un événement d'erreur pour analyse dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO error_events 
        (timestamp, bot_name, error_type, error_message, error_traceback, 
         context_json, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(), bot_name, error_type, error_message,
        traceback_str, json.dumps(context) if context else None, severity
    ))
    conn.commit()
    conn.close()

def get_error_events(bot_name=None, severity=None, resolved=None, limit=100):
    """Récupère les événements d'erreur filtrés."""
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM error_events WHERE 1=1"
    params = []
    
    if bot_name:
        query += " AND bot_name = ?"
        params.append(bot_name)
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if resolved is not None:
        query += " AND resolved = ?"
        params.append(1 if resolved else 0)
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, tuple(params))
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results

def get_conversation_stats(bot_name=None, days=7):
    """Stats des conversations depuis la table interactions."""
    from datetime import timedelta
    conn = get_connection()
    cursor = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    stats = {
        "period_days": days,
        "total_interactions": 0,
        "unique_users": 0,
        "by_bot": {},
        "by_type": {}
    }
    
    # Total
    query = "SELECT COUNT(*), COUNT(DISTINCT user_id) FROM interactions WHERE timestamp > ?"
    params = [cutoff_date]
    if bot_name:
        query += " AND bot_name = ?"
        params.append(bot_name)
        
    cursor.execute(query, tuple(params))
    total_res = cursor.fetchone()
    if total_res:
        stats["total_interactions"] = total_res[0]
        stats["unique_users"] = total_res[1]
        
    # By Bot
    cursor.execute("SELECT bot_name, COUNT(*), COUNT(DISTINCT user_id) FROM interactions WHERE timestamp > ? GROUP BY bot_name", (cutoff_date,))
    for row in cursor.fetchall():
        stats["by_bot"][row[0]] = {"messages": row[1], "unique_users": row[2]}
        
    # By Type
    cursor.execute("SELECT interaction_type, COUNT(*) FROM interactions WHERE timestamp > ? GROUP BY interaction_type", (cutoff_date,))
    for row in cursor.fetchall():
        stats["by_type"][row[0]] = row[1]
        
    conn.close()
    return stats



# FILTRES GLOBAUX (CANAUX IGNORÉS)

def is_ignored_channel(channel) -> bool:
    """
    Vérifie si le canal doit être ignoré par les bots (ex: stream, live).
    Retourne True si le bot doit se taire.
    """
    if not hasattr(channel, "name"):
        return False
    
    name = str(channel.name).lower()
    
    # Mots-clés interdits (Stream du copain)
    ignored_keywords = ["stream", "live"]
    
    return any(keyword in name for keyword in ignored_keywords)


# GESTION DES ÉNIGMES (SHARED M'AIQ/SHEOGORATH)

def set_active_riddle(channel_id: int, question: str, answers: List[str], hint: str, reward: int, message_id: int = None, is_impossible: bool = False):
    """Enregistre une énigme active."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Conversion liste -> JSON string pour stockage
    answers_json = json.dumps(answers)
    
    cursor.execute("""
        INSERT OR REPLACE INTO riddles (channel_id, question, answer, hint, reward, started_at, message_id, is_impossible)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (channel_id, question, answers_json, hint, reward, datetime.now().isoformat(), message_id, 1 if is_impossible else 0))
    
    conn.commit()
    conn.close()


def get_active_riddle(channel_id: int) -> Optional[Dict]:
    """Récupère l'énigme active d'un canal."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM riddles WHERE channel_id = ?", (channel_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        data = dict(row)
        # Parse JSON answer back to list
        try:
            data["answer"] = json.loads(data["answer"])
        except (json.JSONDecodeError, TypeError):
            data["answer"] = [data["answer"]] # Fallback

        # Parse participants
        try:
            data["participants"] = json.loads(data["participants"]) if data.get("participants") else []
        except (json.JSONDecodeError, TypeError):
            data["participants"] = []

        try:
            data["winners"] = json.loads(data["winners"]) if data.get("winners") else []
        except (json.JSONDecodeError, TypeError):
            data["winners"] = []
            
        return data
    return None


def get_all_active_riddles() -> List[Dict]:
    """Récupère TOUTES les énigmes actives (pour restart check)."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM riddles")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        data = dict(row)
        try:
            data["answer"] = json.loads(data["answer"])
        except (json.JSONDecodeError, TypeError):
            data["answer"] = [data["answer"]]
        
        try:
            data["participants"] = json.loads(data["participants"]) if data.get("participants") else []
        except (json.JSONDecodeError, TypeError):
            data["participants"] = []
            
        try:
            data["winners"] = json.loads(data["winners"]) if data.get("winners") else []
        except (json.JSONDecodeError, TypeError):
            data["winners"] = []
        
        results.append(data)
    return results


def delete_active_riddle(channel_id: int):
    """Supprime l'énigme active (résolue ou annulée)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM riddles WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()


def normalize_question(question: str) -> str:
    """Normalise une question pour le hash (minuscules, sans ponctuation)."""
    import re
    q = question.lower().strip()
    q = re.sub(r'[^a-z0-9]', '', q)
    return q

def is_riddle_duplicate(question: str, answers: List[str] = None) -> bool:
    """
    Vérifie si l'énigme a déjà été posée.
    - Vérifie le hash de la question (Exact match).
    - Vérifie si la réponse a été donnée récemment (Semantic match).
    """
    import hashlib
    q_norm = normalize_question(question)
    q_hash = hashlib.sha256(q_norm.encode()).hexdigest()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Check Hash Question
    cursor.execute("SELECT 1 FROM riddle_history WHERE question_hash = ?", (q_hash,))
    if cursor.fetchone():
        conn.close()
        return True
        
    # 2. Check Answer (Last 10)
    if answers:
        try:
            # Get last 10 answers
            cursor.execute("SELECT answer FROM riddle_history ORDER BY id DESC LIMIT 10")
            rows = cursor.fetchall()
            
            new_answers_norm = [normalize_question(a) for a in answers]
            
            for row in rows:
                if not row[0]: continue
                try:
                    hist_answers = json.loads(row[0])
                    # Normalize history answers
                    hist_answers_norm = [normalize_question(a) for a in hist_answers]
                    
                    # Check intersection (Any new answer matches any historic answer)
                    for new_a in new_answers_norm:
                        if new_a in hist_answers_norm:
                            conn.close()
                            return True
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception as e:
            print(f"⚠️ Error checking duplicate answer: {e}")

    conn.close()
    
    return False

def add_to_riddle_history(question: str, answers: List[str] = None):
    """Ajoute une énigme à l'historique."""
    import hashlib
    q_norm = normalize_question(question)
    q_hash = hashlib.sha256(q_norm.encode()).hexdigest()
    
    answers_json = json.dumps(answers) if answers else None
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO riddle_history (question_hash, question, answer, timestamp)
            VALUES (?, ?, ?, ?)
        """, (q_hash, question, answers_json, datetime.now().isoformat()))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Déjà présent
    conn.close()


def get_game_cooldown(user_id: int, game_key: str, bot_name: str) -> float | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT last_reward_time FROM game_cooldowns 
        WHERE user_id = ? AND game_key = ? AND bot_name = ?
    """, (user_id, game_key, bot_name))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_game_cooldown(user_id: int, game_key: str, bot_name: str, ts: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO game_cooldowns (user_id, game_key, bot_name, last_reward_time)
        VALUES (?, ?, ?, ?)
    """, (user_id, game_key, bot_name, ts))
    conn.commit()
    conn.close()

def get_game_daily_points(user_id: int, date_str: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT points FROM game_daily_caps 
        WHERE user_id = ? AND date_str = ?
    """, (user_id, date_str))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def add_game_daily_points(user_id: int, date_str: str, points: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT points FROM game_daily_caps WHERE user_id = ? AND date_str = ?", (user_id, date_str))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("""
            INSERT INTO game_daily_caps (user_id, date_str, points)
            VALUES (?, ?, ?)
        """, (user_id, date_str, points))
    else:
        cursor.execute("""
            UPDATE game_daily_caps SET points = ?
            WHERE user_id = ? AND date_str = ?
        """, (row[0] + points, user_id, date_str))
    conn.commit()
    conn.close()

def get_game_pvp_cooldown(pair_key: str) -> float | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_reward_time FROM game_pvp_cooldowns WHERE pair_key = ?", (pair_key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_game_pvp_cooldown(pair_key: str, ts: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO game_pvp_cooldowns (pair_key, last_reward_time)
        VALUES (?, ?)
    """, (pair_key, ts))
    conn.commit()
    conn.close()


# Initialiser la base au chargement du module
init_database()
