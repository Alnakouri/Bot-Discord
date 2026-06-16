import os
import logging
import threading
from google import genai

logger = logging.getLogger("safe_client")

_env_lock = threading.Lock()

def get_client(api_key, http_options=None):
    """
    Creates a genai.Client while temporarily hiding Google Cloud credentials
    to prevent the SDK from defaulting to Vertex AI mode if local ADC is present but incomplete.
    
    This fixes the 'Invalid project resource name projects/' error.
    Thread-safe version using a lock to prevent race conditions.
    """
    vars_to_hide = [
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_GENAI_USE_VERTEXAI"
    ]
    
    with _env_lock:
        backup = {}
        
        # 1. Hide variables
        for var in vars_to_hide:
            if var in os.environ:
                value = os.environ[var]
                del os.environ[var]
                if value and value.strip():
                    backup[var] = value
                
        # 2. Instantiate Client
        try:
            if not http_options:
                http_options = {'api_version': 'v1beta'}
            
            client = genai.Client(api_key=api_key, http_options=http_options)
            return client
            
        except Exception as e:
            logger.error(f"❌ [SAFE_CLIENT] Failed to create genai.Client: {e}")
            raise e
            
        finally:
            # 3. Restore variables
            for var, value in backup.items():
                os.environ[var] = value
