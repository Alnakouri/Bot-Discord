
# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from pathlib import Path
from shared.shared_database import add_riddle_participant, get_active_riddle, get_connection

DB_PATH = Path(__file__).parent / "bots_database.db"

def check_schema():
    conn = get_connection()
    cursor = conn.cursor()
    print(f"Checking DB at: {DB_PATH}")
    
    # Check riddles columns
    try:
        cursor.execute("PRAGMA table_info(riddles)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Columns in 'riddles': {columns}")
        
        if "participants" not in columns:
            print("❌ 'participants' column MISSING!")
        else:
            print("✅ 'participants' column FOUND!")
            
    except Exception as e:
        print(f"Error checking schema: {e}")
    conn.close()

def test_add_participant():
    # Find an active riddle
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id FROM riddles LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print("No active riddle found to test.")
        return
        
    channel_id = row[0]
    user_id = 123456789 # Fake user
    
    print(f"Testing add_riddle_participant for channel {channel_id}, user {user_id}")
    try:
        add_riddle_participant(channel_id, user_id)
        
        # Verify
        riddle = get_active_riddle(channel_id)
        participants = riddle.get("participants", [])
        print(f"Participants after add: {participants}")
        
        if user_id in participants:
            print("✅ SUCCESS: Participant added.")
        else:
            print("❌ FAILURE: Participant NOT added.")
            
    except Exception as e:
        print(f"❌ ERROR during test: {e}")

if __name__ == "__main__":
    check_schema()
    test_add_participant()
