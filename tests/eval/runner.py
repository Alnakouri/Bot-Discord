import os
import sys
import asyncio
from pathlib import Path
from groq import Groq
from mistralai import Mistral
from openai import OpenAI

# Injection du répertoire racine au sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from shared.secure_env import load_secure_env
from shared.api_manager import MultiAPIKeyManager
from shared.smart_router import RequestType
from shared.llm_cascade import generate_response
from tests.eval.persona_loader import load_persona

# Charger les variables d'environnement à partir de JohnnyBot (qui contient .env.encrypted et .master_key)
johnny_dir = Path(root_dir) / "JohnnyBot"
try:
    load_secure_env(johnny_dir)
except Exception as e:
    print(f"Avertissement lors du chargement de secure_env depuis JohnnyBot : {e}")

# Clés d'API
GEMINI_API_KEYS = [
    os.getenv("GEMINI_KEY_1"),
    os.getenv("GEMINI_KEY_2"),
    os.getenv("GEMINI_KEY_3"),
    os.getenv("GEMINI_KEY_4"),
]
GEMINI_API_KEYS = [k for k in GEMINI_API_KEYS if k]

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Clients
key_manager = MultiAPIKeyManager()
key_manager.register_api("gemini", GEMINI_API_KEYS)
key_manager.register_api("groq", [GROQ_API_KEY] if GROQ_API_KEY else [])
key_manager.register_api("mistral", [MISTRAL_API_KEY] if MISTRAL_API_KEY else [])
key_manager.register_api("openrouter", [OPENROUTER_API_KEY] if OPENROUTER_API_KEY else [])

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
mistral_client = Mistral(api_key=MISTRAL_API_KEY) if MISTRAL_API_KEY else None
openrouter_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1"
) if OPENROUTER_API_KEY else None

async def run_scenario_for_bot(bot_id: str, scenario: dict) -> list[str]:
    """
    Exécute un scénario (pouvant comporter plusieurs tours) pour un bot donné.
    Retourne la liste des réponses générées par le bot.
    """
    persona = load_persona(bot_id)
    system_prompt = persona["system_prompt"]
    bot_label = persona["bot_label"]
    
    conversation_history = []
    responses = []
    
    # Scénario info
    user_messages = scenario.get("user_messages", [])
    initial_transcript = scenario.get("transcript", "")
    
    for user_msg in user_messages:
        # Construction du transcript pour les modèles non-Gemini
        transcript_lines = []
        if initial_transcript:
            transcript_lines.append(initial_transcript)
            
        for h_msg in conversation_history:
            role_prefix = f"({bot_label})" if h_msg["role"] == "model" else "(User)"
            transcript_lines.append(f"{role_prefix}: {h_msg['parts'][0]}")
            
        transcript = "\n".join(transcript_lines)
        
        # Le type de requête est texte
        routing = {
            "type": RequestType.TEXT,
            "reason": f"Eval harness - Scenario {scenario.get('id')} - Bot {bot_id}"
        }
        
        # Appel de la cascade LLM
        response = await generate_response(
            routing=routing,
            system_prompt=system_prompt,
            transcript=transcript,
            user_message=user_msg,
            conversation_history=conversation_history,
            media_data=None,
            mime_type="",
            key_manager=key_manager,
            mistral_client=mistral_client,
            groq_client=groq_client,
            openrouter_client=openrouter_client,
            bot_label=bot_label,
            temperature=0.8,
            max_tokens=300
        )
        
        if response is None:
            # Fallback en cas d'échec total de la cascade
            response = "[Toute la cascade de modèles a échoué]"
            
        responses.append(response)
        
        # Mise à jour de l'historique pour le tour suivant
        conversation_history.append({"role": "user", "parts": [user_msg]})
        conversation_history.append({"role": "model", "parts": [response]})
        
    return responses
