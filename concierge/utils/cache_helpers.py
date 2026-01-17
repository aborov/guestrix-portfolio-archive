"""
Caching utilities for Firestore vector search.
"""

import os
import time
import json
import logging
import hashlib
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class FirestoreCache:
    """
    A memory-efficient cache for Firestore vector search results with time-based expiration.
    """

    def __init__(self, max_cache_size=200, ttl_seconds=1800):
        """
        Initialize the cache with configuration parameters.

        Args:
            max_cache_size: Maximum number of items to store in the cache (default: 200)
            ttl_seconds: Time-to-live in seconds for cache entries (default: 30 minutes)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._max_cache_size = max_cache_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0
        self._stats_last_reset = time.time()
        self._enabled = True  # Can be disabled to bypass cache

        # Load environment-specific cache settings if available
        self._load_env_settings()

    def enable(self):
        """Enable the cache."""
        self._enabled = True
        logging.info("Firestore cache enabled")

    def disable(self):
        """Disable the cache. All operations will bypass cache when disabled."""
        self._enabled = False
        logging.info("Firestore cache disabled")

    def _load_env_settings(self):
        """Load cache settings from environment variables if available."""
        import os

        # Override cache size if environment variable is set
        env_cache_size = os.environ.get('FIRESTORE_CACHE_SIZE')
        if env_cache_size and env_cache_size.isdigit():
            self._max_cache_size = int(env_cache_size)
            logging.info(f"Set cache size from environment: {self._max_cache_size}")

        # Override TTL if environment variable is set
        env_ttl = os.environ.get('FIRESTORE_CACHE_TTL')
        if env_ttl and env_ttl.isdigit():
            self._ttl_seconds = int(env_ttl)
            logging.info(f"Set cache TTL from environment: {self._ttl_seconds} seconds")

    def clear(self):
        """Clear all items from the cache."""
        self._cache.clear()
        logging.info("Firestore cache cleared")

    def _generate_key(self, property_id: str, query_text: str, table_name: str = None) -> str:
        """
        Generate a deterministic cache key from the input parameters.

        Args:
            property_id: The property ID
            query_text: The user's query text
            table_name: Optional table name (for compatibility)

        Returns:
            A string key for the cache
        """
        # Combine all parameters and hash them for a consistent key
        key_components = f"{property_id}:{query_text}"
        if table_name:
            key_components += f":{table_name}"
        return hashlib.md5(key_components.encode('utf-8')).hexdigest()

    def get(self, property_id: str, query_text: str, table_name: str = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached results for the given parameters if available and not expired.

        Args:
            property_id: The property ID
            query_text: The user's query text
            table_name: Optional table name (for compatibility)

        Returns:
            The cached results or None if not found or expired
        """
        if not self._enabled:
            self._misses += 1
            return None

        key = self._generate_key(property_id, query_text, table_name)

        if key in self._cache:
            entry = self._cache[key]

            # Check if entry is expired
            if time.time() - entry['timestamp'] > self._ttl_seconds:
                logging.info(f"Cache entry expired for key: {key[:8]}...")
                del self._cache[key]
                self._misses += 1
                return None

            # Return cached results
            self._hits += 1
            logging.info(f"Cache HIT for {property_id} with query: '{query_text[:30]}...'")
            return entry['results']

        self._misses += 1
        logging.info(f"Cache MISS for {property_id} with query: '{query_text[:30]}...'")
        return None

    def set(self, property_id: str, query_text: str, table_name: str = None, results: Dict[str, Any] = None) -> None:
        """
        Store results in the cache.

        Args:
            property_id: The property ID
            query_text: The user's query text
            table_name: Optional table name (for compatibility)
            results: The results to cache
        """
        if not self._enabled:
            return

        key = self._generate_key(property_id, query_text, table_name)

        # Evict oldest entries if cache is full
        if len(self._cache) >= self._max_cache_size:
            oldest_key = min(self._cache.items(), key=lambda x: x[1]['timestamp'])[0]
            del self._cache[oldest_key]
            logging.info(f"Cache full, evicted oldest entry: {oldest_key[:8]}...")

        # Store results with timestamp
        self._cache[key] = {
            'timestamp': time.time(),
            'results': results
        }
        logging.info(f"Cached results for {property_id} with query: '{query_text[:30]}...'")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.

        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests) * 100 if total_requests > 0 else 0

        return {
            'hits': self._hits,
            'misses': self._misses,
            'total_requests': total_requests,
            'hit_rate_percent': hit_rate,
            'cache_size': len(self._cache),
            'max_cache_size': self._max_cache_size,
            'ttl_seconds': self._ttl_seconds,
            'enabled': self._enabled,
            'stats_age_seconds': time.time() - self._stats_last_reset
        }

    def reset_stats(self) -> None:
        """Reset cache performance statistics."""
        self._hits = 0
        self._misses = 0
        self._stats_last_reset = time.time()
        logging.info("Cache statistics reset")

    def get_cached_property_queries(self, property_id: str) -> List[str]:
        """
        Get a list of queries that are cached for a specific property.

        Args:
            property_id: The property ID

        Returns:
            List of query strings
        """
        result = []

        # Extract property_id and query_text from cache keys
        for key, entry in self._cache.items():
            # This is a simplistic approach - in a real implementation,
            # you might want to store the original parameters alongside the hashed key
            if property_id in key:
                result.append(key)

        return result

    def cache_table_schema(self, table_name: str, schema: Any) -> None:
        """
        Cache a table schema to avoid repeated schema lookups.

        Args:
            table_name: The name of the LanceDB table
            schema: The table schema to cache
        """
        if not self._enabled:
            return

        key = f"schema:{table_name}"

        self._table_cache[key] = {
            'timestamp': time.time(),
            'schema': schema
        }
        logging.info(f"Cached schema for table: {table_name}")

    def get_table_schema(self, table_name: str) -> Optional[Any]:
        """
        Get a cached table schema if available and not expired.

        Args:
            table_name: The name of the LanceDB table

        Returns:
            The cached schema or None if not found or expired
        """
        if not self._enabled:
            return None

        key = f"schema:{table_name}"

        if key in self._table_cache:
            entry = self._table_cache[key]

            # Check if entry is expired
            if time.time() - entry['timestamp'] > self._ttl_seconds:
                logging.info(f"Schema cache expired for table: {table_name}")
                del self._table_cache[key]
                return None

            logging.debug(f"Using cached schema for table: {table_name}")
            return entry['schema']

        return None

    def batch_get(self, property_id: str, item_ids: List[str], table_name: str) -> Dict[str, bool]:
        """
        Batch retrieve cached existence status for multiple items.

        Args:
            property_id: The property ID
            item_ids: List of item IDs to check
            table_name: The LanceDB table name

        Returns:
            Dictionary mapping item IDs to their existence status (True/False)
            or empty dict if not in cache
        """
        if not self._enabled or not item_ids:
            return {}

        # Generate a batch key
        batch_key = f"batch:{property_id}:{table_name}"

        if batch_key in self._cache:
            entry = self._cache[batch_key]

            # Check if entry is expired
            if time.time() - entry['timestamp'] > self._ttl_seconds:
                logging.info(f"Batch cache expired for key: {batch_key}")
                del self._cache[batch_key]
                self._misses += 1
                return {}

            # Get the cached batch results
            batch_results = entry['results']

            # Check if all requested items are in the cached results
            missing_items = [item_id for item_id in item_ids if item_id not in batch_results]
            if missing_items:
                logging.info(f"Batch cache miss for {len(missing_items)} items")
                self._misses += 1
                return {}

            # Return only the requested items
            self._hits += 1
            logging.info(f"Batch cache HIT for {property_id} with {len(item_ids)} items")
            return {item_id: batch_results[item_id] for item_id in item_ids}

        self._misses += 1
        logging.info(f"Batch cache MISS for {property_id} with {len(item_ids)} items")
        return {}

    def batch_set(self, property_id: str, item_results: Dict[str, bool], table_name: str) -> None:
        """
        Store batch results in the cache.

        Args:
            property_id: The property ID
            item_results: Dictionary mapping item IDs to their existence status
            table_name: The LanceDB table name
        """
        if not self._enabled or not item_results:
            return

        # Generate a batch key
        batch_key = f"batch:{property_id}:{table_name}"

        # Check if we already have a cached entry for this property/table
        if batch_key in self._cache:
            # Update existing entry with new results
            existing_results = self._cache[batch_key]['results']
            # Merge the results, prioritizing the new results
            merged_results = {**existing_results, **item_results}

            # Update the cache entry
            self._cache[batch_key] = {
                'timestamp': time.time(),  # Reset timestamp to current time
                'results': merged_results
            }
            logging.info(f"Updated cached batch results for {property_id} with {len(item_results)} new items (total: {len(merged_results)})")
            return

        # Evict oldest entries if cache is full
        if len(self._cache) >= self._max_cache_size:
            oldest_key = min(self._cache.items(), key=lambda x: x[1]['timestamp'])[0]
            del self._cache[oldest_key]
            logging.info(f"Cache full, evicted oldest entry: {oldest_key[:8]}...")

        # Store results with timestamp
        self._cache[batch_key] = {
            'timestamp': time.time(),
            'results': item_results
        }
        logging.info(f"Cached batch results for {property_id} with {len(item_results)} items")

# Global instance for app-wide caching
firestore_cache = FirestoreCache()

# Firestore connection cache
_firestore_connection_cache = None

def get_cached_firestore_client():
    """
    Get a cached Firestore client to avoid repeatedly initializing Firebase.

    Returns:
        Firestore client or None if failed
    """
    global _firestore_connection_cache

    # Check if we already have a cached connection
    if _firestore_connection_cache is not None:
        logging.debug("Using cached Firestore client")
        return _firestore_connection_cache

    # No cached connection, create a new one
    try:
        # Import Firebase Admin SDK
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as e:
            logging.error(f"Error importing firebase_admin: {e}")
            return None

        # Initialize Firebase if not already initialized
        try:
            # Check if Firebase app is already initialized
            try:
                firebase_admin.get_app()
                logging.info("Firebase app already initialized")
            except ValueError:
                # Initialize Firebase app
                cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
                if not cred_path:
                    logging.error("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
                    return None

                # Initialize with credentials file
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logging.info("Firebase app initialized with credentials file")
        except Exception as e:
            logging.error(f"Error initializing Firebase: {e}")
            return None

        # Get Firestore client with environment-aware database selection
        try:
            # Prefer using central helper if available to ensure DB selection
            from concierge.utils.firestore_client import get_firestore_client as _central_get_client
            _firestore_connection_cache = _central_get_client()
        except Exception:
            # Fallback to default client (may hit default DB)
            _firestore_connection_cache = firestore.client()
        logging.info("Created new Firestore client (cached)")
        return _firestore_connection_cache
    except Exception as e:
        logging.error(f"Error getting Firestore client: {e}")
        return None