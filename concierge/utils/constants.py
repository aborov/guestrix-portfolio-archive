"""
Constants used throughout the Concierge application.
"""

import os

# Constants for the Concierge application

# --- Database Constants ---
DEFAULT_PROPERTY_ID = 'guestrix-staging'

# --- Gemini Constants ---
DEFAULT_GEMINI_MODEL = 'gemini-2.5-flash-lite'

# --- File Processing Constants ---
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# --- Embedding Constants ---
EMBEDDING_DIMENSION = 768  # Default for text-embedding-004

# --- Cache Constants ---
DEFAULT_CACHE_TTL = 1800  # 30 minutes
DEFAULT_CACHE_SIZE = 200

# --- Gemini API Constants ---
GEMINI_EMBEDDING_MODEL = 'models/text-embedding-004'
GEMINI_EMBEDDING_TASK_TYPE = "RETRIEVAL_QUERY"  # For queries
GEMINI_EMBEDDING_DOC_TASK_TYPE = "RETRIEVAL_DOCUMENT"  # For documents

# --- Other Constants ---
MAX_RESULTS = 5  # Maximum number of results to retrieve
SIMILARITY_THRESHOLD = 0.7  # Minimum similarity score (0-1)