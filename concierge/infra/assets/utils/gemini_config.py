import os
import google.generativeai as genai
from dotenv import load_dotenv
import numpy as np

# Load environment variables from .env file
load_dotenv('./concierge/.env')

# --- Check for Gemini API Key ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY environment variable not set. Q&A generation will be disabled.")
    genai_enabled = False
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        print("Gemini API configured successfully.")
        genai_enabled = True
    except Exception as e:
        print(f"ERROR: Could not configure Gemini API: {e}")
        genai_enabled = False

# --- Gemini Model Initialization (can be done once) ---
# Using a recent model. Consider making this configurable.
gemini_model = None
if genai_enabled:
    try:
        # Initialize the generative model for text generation
        gemini_model = genai.GenerativeModel('gemini-2.0-flash')
        print("Gemini Generative Model initialized.")
        
        # Note: Gemini API doesn't have a separate EmbeddingModel class
        # Embeddings are generated using the embed_content method directly
        print("Gemini Embedding functionality available.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Gemini Models: {e}")
        genai_enabled = False # Disable if model init fails

# Function to generate embeddings using the Gemini API
def generate_embedding(text, task_type="retrieval_query"):
    """Generate embeddings using the Gemini API."""
    if not genai_enabled:
        raise ValueError("Gemini API is not enabled. Check your API key configuration.")
    
    try:
        # Use the embed_content method directly from the genai module
        # Make sure to use the correct model name format with 'models/' prefix
        embedding = genai.embed_content(
            model="models/embedding-001",  # Corrected model name format
            content=text,
            task_type=task_type
        )
        
        # Get the actual values by calling the values() function
        if embedding is not None:
            # Get the values and convert them to a list
            values = list(embedding.values())
            if values:
                # Get the first element since values() returns a list of embeddings
                embedding_values = values[0]
                # Convert the embedding values to a numpy array and then to a list
                embedding_array = np.array(embedding_values, dtype=np.float32)
                return embedding_array.tolist()
        
        raise ValueError("No embedding values returned from the API")
    except Exception as e:
        print(f"ERROR: Failed to generate embedding: {e}")
        raise 