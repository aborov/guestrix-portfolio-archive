import os
import google.genai as genai
# Keep legacy import for backward compatibility
import google.generativeai as legacy_genai
from dotenv import load_dotenv
import numpy as np
import logging

# Load environment variables from .env file
load_dotenv('./concierge/.env')

def _select_gemini_api_key() -> str:
    """Select API key based on environment.

    - production: use GEMINI_API_KEY_PAID (fallback to GEMINI_API_KEY)
    - staging/development: use GEMINI_API_KEY (or GEMINI_API_KEY_FREE)
    """
    env = os.getenv('DEPLOYMENT_ENV', '').lower()
    if env == 'production':
        return os.getenv('GEMINI_API_KEY_PAID') or os.getenv('GEMINI_API_KEY') or ''
    # default to free/dev key
    return os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY_FREE') or ''


# --- Check for Gemini API Key ---
GEMINI_API_KEY = _select_gemini_api_key()
if not GEMINI_API_KEY:
    print("WARNING: No Gemini API key available. Set GEMINI_API_KEY_PAID for production or GEMINI_API_KEY for dev/staging.")
    genai_enabled = False
else:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("Gemini API client created successfully with new SDK.")
        genai_enabled = True
    except Exception as e:
        print(f"ERROR: Could not create Gemini API client: {e}")
        genai_enabled = False

# --- Gemini Model Initialization (can be done once) ---
# Using a recent model. Consider making this configurable.
gemini_model = None
if genai_enabled:
    try:
        # For the new SDK, we create clients per request instead of global models
        print("Gemini API functionality available with new SDK.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Gemini functionality: {e}")
        genai_enabled = False # Disable if model init fails

# --- Vector Embedding Functions ---
def get_embedding_dimension():
    """
    Get the dimension of the embeddings from the current model.
    Returns 768 for text-embedding-004 model.
    """
    return 768  # Standard dimension for text-embedding-004

def generate_embeddings(texts, task_type="RETRIEVAL_DOCUMENT"):
    """
    Generate embeddings for a list of texts using Gemini API.

    Args:
        texts (list): List of text strings to generate embeddings for
        task_type (str): Type of task for the embeddings

    Returns:
        list: List of embedding vectors (each as a list of floats)
    """
    if not genai_enabled:
        print("ERROR: Gemini API not enabled. Cannot generate embeddings.")
        return []

    embeddings = []
    try:
        # Create client for this request
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        for text in texts:
            try:
                # Generate embedding using the new SDK
                result = client.models.embed_content(
                    model="text-embedding-004",
                    contents=[text],
                    config={'task_type': task_type}
                )
                
                if result.embeddings and len(result.embeddings) > 0:
                    embeddings.append(result.embeddings[0].values)
                else:
                    print(f"Warning: No embedding generated for text: {text[:50]}...")
                    embeddings.append(None)
            except Exception as e:
                print(f"Error generating embedding for text: {e}")
                embeddings.append(None)
    except Exception as e:
        print(f"Error creating Gemini client for embeddings: {e}")

    return embeddings

# Configure the legacy SDK for backward compatibility (if needed)
def configure_legacy_gemini():
    """Configure the legacy Google Generative AI SDK if needed."""
    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if api_key and legacy_genai:
            legacy_genai.configure(api_key=api_key)
            logging.info("Legacy Gemini SDK configured")
            return True
    except Exception as e:
        logging.warning(f"Failed to configure legacy Gemini SDK: {e}")
    return False

# Try to configure legacy SDK for existing code
configure_legacy_gemini()

# Create a legacy model instance if needed
gemini_model = None
try:
    if legacy_genai:
        gemini_model = legacy_genai.GenerativeModel('gemini-2.0-flash')
        logging.info("Legacy Gemini model created")
except Exception as e:
    logging.warning(f"Failed to create legacy Gemini model: {e}")

# New SDK client factory function
def create_gemini_client():
    """Create a new Google GenAI client."""
    try:
        api_key = _select_gemini_api_key()
        if api_key and genai:
            return genai.Client(api_key=api_key)
    except Exception as e:
        logging.error(f"Failed to create Gemini client: {e}")
    return None 