"""
Caching utilities to reduce S3 requests when interacting with LanceDB.
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

class LanceDBCache:
    """
    A memory-efficient cache for LanceDB query results with time-based expiration.
    Optimized to reduce S3 requests by caching both query results and table schemas.
    """

    def __init__(self, max_cache_size=200, ttl_seconds=1800):
        """
        Initialize the cache with configuration parameters.

        Args:
            max_cache_size: Maximum number of items to store in the cache (default: 200)
            ttl_seconds: Time-to-live in seconds for cache entries (default: 30 minutes)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._table_cache: Dict[str, Dict[str, Any]] = {}  # Cache for table schemas
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
        logging.info("LanceDB cache enabled")

    def disable(self):
        """Disable the cache. All operations will bypass cache when disabled."""
        self._enabled = False
        logging.info("LanceDB cache disabled")

    def _load_env_settings(self):
        """Load cache settings from environment variables if available."""
        import os

        # Override cache size if environment variable is set
        env_cache_size = os.environ.get('LANCEDB_CACHE_SIZE')
        if env_cache_size and env_cache_size.isdigit():
            self._max_cache_size = int(env_cache_size)
            logging.info(f"Set cache size from environment: {self._max_cache_size}")

        # Override TTL if environment variable is set
        env_ttl = os.environ.get('LANCEDB_CACHE_TTL')
        if env_ttl and env_ttl.isdigit():
            self._ttl_seconds = int(env_ttl)
            logging.info(f"Set cache TTL from environment: {self._ttl_seconds} seconds")

    def clear(self):
        """Clear all items from the cache."""
        self._cache.clear()
        self._table_cache.clear()
        logging.info("LanceDB cache cleared")

    def _generate_key(self, property_id: str, query_text: str, table_name: str) -> str:
        """
        Generate a deterministic cache key from the input parameters.

        Args:
            property_id: The property ID
            query_text: The user's query text
            table_name: The LanceDB table name

        Returns:
            A string key for the cache
        """
        # Combine all parameters and hash them for a consistent key
        key_components = f"{property_id}:{query_text}:{table_name}"
        return hashlib.md5(key_components.encode('utf-8')).hexdigest()

    def get(self, property_id: str, query_text: str, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached results for the given parameters if available and not expired.

        Args:
            property_id: The property ID
            query_text: The user's query text
            table_name: The LanceDB table name

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

    def set(self, property_id: str, query_text: str, table_name: str, results: Dict[str, Any]) -> None:
        """
        Store results in the cache.

        Args:
            property_id: The property ID
            query_text: The user's query text
            table_name: The LanceDB table name
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
lancedb_cache = LanceDBCache()

def batch_query_lancedb(db, table_name, query_vectors, property_id=None, limit=3):
    """
    Perform a batch query to LanceDB to reduce S3 requests.

    Args:
        db: LanceDB connection
        table_name: Name of the table to query
        query_vectors: List of query vectors
        property_id: Optional property ID to filter by
        limit: Maximum number of results per query

    Returns:
        Dictionary mapping query index to results
    """
    if not db or not query_vectors:
        return {}

    results = {}

    try:
        # Open the table once for all queries
        table = db.open_table(table_name)

        # Process each query vector
        for i, vector in enumerate(query_vectors):
            try:
                # Build the query
                query = table.search(vector)

                # Add property filter if provided
                if property_id:
                    query = query.where(f"property_id = '{property_id}'")

                # Set limit and execute
                query_results = query.limit(limit).to_pandas()

                # Store results
                results[i] = query_results

            except Exception as e:
                logging.error(f"Error processing query {i}: {e}")
                results[i] = None

    except Exception as e:
        logging.error(f"Error opening table {table_name}: {e}")

    return results

def batch_check_items_existence(db, table_name, item_ids, max_batch_size=50):
    """
    Efficiently check if multiple items exist in a LanceDB table with a single query.
    This is optimized to reduce S3 requests when checking many items.

    Args:
        db: LanceDB connection
        table_name: Name of the table to query
        item_ids: List of item IDs to check
        max_batch_size: Maximum number of IDs to check in a single query

    Returns:
        Dictionary mapping item IDs to boolean existence status
    """
    if not db or not item_ids:
        return {}

    results = {item_id: False for item_id in item_ids}

    try:
        # Open the table once for all checks
        table = db.open_table(table_name)

        # Process in batches to avoid query size limits
        for i in range(0, len(item_ids), max_batch_size):
            batch_ids = item_ids[i:i+max_batch_size]

            # Build a WHERE clause for this batch
            where_clause = " OR ".join([f"id = '{item_id}'" for item_id in batch_ids])

            # Execute query for this batch
            logging.info(f"Executing batch existence check ({i//max_batch_size + 1}/{(len(item_ids) + max_batch_size - 1)//max_batch_size}) with {len(batch_ids)} IDs")

            try:
                query_result = table.search().where(where_clause).to_pandas()

                if not query_result.empty:
                    # Update results for found items
                    for _, row in query_result.iterrows():
                        item_id = row.get('id')
                        if item_id in results:
                            results[item_id] = True
            except Exception as batch_err:
                logging.error(f"Error in batch {i//max_batch_size + 1}: {batch_err}")
                # Continue with next batch even if this one fails
                continue

        # Log summary
        found_count = sum(1 for exists in results.values() if exists)
        logging.info(f"Batch existence check summary: {found_count}/{len(item_ids)} items found in table '{table_name}'")

        return results

    except Exception as e:
        logging.error(f"Error in batch check for table {table_name}: {e}")
        import traceback
        traceback.print_exc()
        return results

# Global connection cache
_connection_cache = {}

def cached_connection(uri: str, connection_timeout: int = 30) -> Optional[Any]:
    """
    Cache the LanceDB connection to avoid repeatedly establishing new connections.
    Uses a global connection cache to reuse connections across function calls.

    Args:
        uri: The LanceDB URI
        connection_timeout: Connection timeout in seconds

    Returns:
        LanceDB connection object or None if failed
    """
    import lancedb
    global _connection_cache

    # Check if we already have a cached connection for this URI
    if uri in _connection_cache:
        logging.debug(f"Using cached LanceDB connection for {uri}")
        return _connection_cache[uri]

    # No cached connection, create a new one
    try:
        logging.info(f"Creating new LanceDB connection for {uri}")
        connection = lancedb.connect(uri)
        # Cache the connection for future use
        _connection_cache[uri] = connection
        return connection
    except Exception as e:
        logging.error(f"Error connecting to LanceDB: {e}")
        return None