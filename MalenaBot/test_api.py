
# INJECTION SHARED FOLDER
import sys
import os
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import os
import google.generativeai as genai
from core.secure_env import load_secure_env

print("--- DIAGNOSTIC API MALENA ---")

# 1. Load Env
try:
    env = load_secure_env()
    key = env.get("GEMINI_API_KEY")
    if not key:
        print("❌ CRITIQUE : Clé GEMINI_API_KEY introuvable dans l'environnement !")
        exit(1)
    
    print(f"🔑 Clé trouvée : {key[:10]}...{key[-5:]}")
except Exception as e:
    print(f"❌ Erreur chargement Env : {e}")
    exit(1)

# 2. Configure GenAI
try:
    genai.configure(api_key=key)
    print("✅ Configuration GenAI effectuée.")
except Exception as e:
    print(f"❌ Erreur Configuration : {e}")
    exit(1)

# 3. Test Call
try:
    print("📡 Tentative d'appel API (gemini-2.0-flash)...")
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content("Dis bonjour.")
    print(f"✅ SUCCÈS ! Réponse : {response.text}")
except Exception as e:
    print(f"❌ ÉCHEC APPEL API : {e}")
