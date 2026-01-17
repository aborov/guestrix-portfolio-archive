"""
Constants used throughout the Concierge application.
"""

import os

# --- Vector Search Constants (Firestore) ---
# LanceDB constants removed - migrated to Firestore for vector search
EMBEDDING_DIMENSION = 768  # Gemini embedding dimension

# --- Gemini API Constants ---
GEMINI_EMBEDDING_MODEL = 'models/text-embedding-004'
GEMINI_EMBEDDING_TASK_TYPE = "RETRIEVAL_QUERY"  # For queries
GEMINI_EMBEDDING_DOC_TASK_TYPE = "RETRIEVAL_DOCUMENT"  # For documents

# --- Other Constants ---
MAX_RESULTS = 5  # Maximum number of results to retrieve
SIMILARITY_THRESHOLD = 0.7  # Minimum similarity score (0-1)