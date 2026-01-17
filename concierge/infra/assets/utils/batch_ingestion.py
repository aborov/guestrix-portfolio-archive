#!/usr/bin/env python3
"""
Batch Ingestion Utility for LanceDB

This script provides utilities for batch ingestion of knowledge items into LanceDB
to reduce the number of S3 requests and improve ingestion efficiency.
"""

import os
import sys
import json
import time
import logging
import argparse
from typing import List, Dict, Any, Optional
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Try to import required modules
try:
    import lancedb
    import google.genai as genai
except ImportError as e:
    logging.error(f"Required module not found: {e}")
    logging.error("Please install required modules: pip install lancedb google-genai")
    sys.exit(1)

# Constants
DEFAULT_BATCH_SIZE = 10
DEFAULT_TABLE_NAME = os.environ.get('LANCEDB_TABLE_NAME', 'knowledge_base')
DEFAULT_S3_URI = os.environ.get('LANCEDB_S3_URI', 's3://guestrix-lancedb-storage/lancedb')
GEMINI_EMBEDDING_MODEL = 'text-embedding-004'
GEMINI_EMBEDDING_TASK_TYPE = "RETRIEVAL_DOCUMENT"

def configure_gemini() -> bool:
    """
    Configure the Gemini API with the API key from environment.

    Returns:
        bool: True if configuration was successful, False otherwise
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        logging.error("GEMINI_API_KEY environment variable not set")
        return False

    try:
        # Test creating a client with the new SDK
        client = genai.Client(api_key=api_key)
        logging.info("Gemini API configured successfully")
        return True
    except Exception as e:
        logging.error(f"Error configuring Gemini API: {e}")
        return False

def generate_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for a batch of texts.

    Args:
        texts: List of texts to generate embeddings for

    Returns:
        List of embedding vectors (or None for failed embeddings)
    """
    if not texts:
        return []

    embeddings = []

    try:
        # Create client with the new SDK
        api_key = os.environ.get('GEMINI_API_KEY')
        client = genai.Client(api_key=api_key)
        
        # Generate embeddings in a single API call
        embedding_result = client.models.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            contents=texts,
            config={
                'task_type': GEMINI_EMBEDDING_TASK_TYPE
            }
        )

        # Check if we got embeddings back
        if (hasattr(embedding_result, 'embeddings') and
            embedding_result.embeddings and
            len(embedding_result.embeddings) > 0):
            # Extract all embedding values
            embeddings = [emb.values for emb in embedding_result.embeddings]
            logging.info(f"Successfully generated {len(embeddings)} embeddings")
        else:
            logging.error(f"Unexpected response format from Gemini embedding API: {embedding_result}")
            # Return a list of None values
            embeddings = [None] * len(texts)
    except Exception as e:
        logging.error(f"Error generating embeddings: {e}")
        # Return a list of None values
        embeddings = [None] * len(texts)

    return embeddings

def batch_ingest_items(items: List[Dict[str, Any]], lancedb_uri: str, table_name: str, batch_size: int = DEFAULT_BATCH_SIZE) -> Dict[str, Any]:
    """
    Batch ingest items into LanceDB.

    Args:
        items: List of items to ingest
        lancedb_uri: URI of the LanceDB database
        table_name: Name of the table to ingest into
        batch_size: Number of items to process in each batch

    Returns:
        Dictionary with ingestion statistics
    """
    stats = {
        'total_items': len(items),
        'successful': 0,
        'failed': 0,
        'batches': 0,
        'embedding_failures': 0,
        'ingestion_failures': 0
    }

    if not items:
        logging.warning("No items to ingest")
        return stats

    # Connect to LanceDB
    try:
        logging.info(f"Connecting to LanceDB at {lancedb_uri}")
        db = lancedb.connect(lancedb_uri)
        logging.info("Connected to LanceDB successfully")
    except Exception as e:
        logging.error(f"Error connecting to LanceDB: {e}")
        stats['failed'] = len(items)
        return stats

    # Check if table exists
    table_names = db.table_names()
    if table_name not in table_names:
        logging.warning(f"Table '{table_name}' does not exist, creating it")
        try:
            # Create a dummy table with the expected schema
            dummy_data = [{
                'vector': [0.0] * 768,  # Gemini embedding dimension
                'text': 'dummy',
                'qna_id': 'dummy',
                'property_id': 'dummy'
            }]
            db.create_table(table_name, data=dummy_data)
            logging.info(f"Created table '{table_name}'")

            # Open the table
            table = db.open_table(table_name)

            # Delete the dummy data
            table.delete("qna_id = 'dummy'")
            logging.info("Removed dummy data from table")
        except Exception as e:
            logging.error(f"Error creating table: {e}")
            stats['failed'] = len(items)
            return stats

    # Open the table
    try:
        table = db.open_table(table_name)
        logging.info(f"Opened table '{table_name}'")
    except Exception as e:
        logging.error(f"Error opening table: {e}")
        stats['failed'] = len(items)
        return stats

    # Process items in batches
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        stats['batches'] += 1

        logging.info(f"Processing batch {stats['batches']} ({len(batch)} items)")

        # Prepare texts for embedding
        texts = []
        for item in batch:
            question = item.get('question', '')
            answer = item.get('answer', '')
            if question and answer:
                text = f"Q: {question}\nA: {answer}"
                texts.append(text)
            else:
                texts.append('')  # Placeholder for invalid items

        # Generate embeddings for the batch
        embeddings = generate_embeddings_batch(texts)

        # Prepare data for LanceDB
        data_to_add = []
        for j, item in enumerate(batch):
            if not embeddings[j]:
                logging.warning(f"Failed to generate embedding for item {item.get('qna_id', 'unknown')}")
                stats['embedding_failures'] += 1
                stats['failed'] += 1
                continue

            # Get required fields
            qna_id = item.get('qna_id')
            property_id = item.get('property_id')
            question = item.get('question', '')
            answer = item.get('answer', '')

            if not qna_id or not property_id or not question or not answer:
                logging.warning(f"Missing required fields for item {qna_id}")
                stats['failed'] += 1
                continue

            # Add to batch
            data_to_add.append({
                'vector': embeddings[j],
                'text': texts[j],
                'qna_id': qna_id,
                'property_id': property_id,
                'question': question,
                'answer': answer
            })

        # Skip if no valid data
        if not data_to_add:
            logging.warning("No valid data in batch, skipping")
            continue

        # Ingest the batch
        try:
            table.merge(data=data_to_add, key_column='qna_id')
            logging.info(f"Successfully ingested {len(data_to_add)} items")
            stats['successful'] += len(data_to_add)
        except Exception as e:
            logging.error(f"Error ingesting batch: {e}")
            stats['ingestion_failures'] += 1
            stats['failed'] += len(data_to_add)

    return stats

def load_items_from_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Load items from a JSON or CSV file.

    Args:
        file_path: Path to the file

    Returns:
        List of items
    """
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return []

    try:
        # Determine file type from extension
        _, ext = os.path.splitext(file_path)

        if ext.lower() == '.json':
            # Load JSON file
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Handle different JSON formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'items' in data:
                return data['items']
            else:
                logging.error(f"Unsupported JSON format in {file_path}")
                return []

        elif ext.lower() == '.csv':
            # Load CSV file
            df = pd.read_csv(file_path)

            # Convert to list of dictionaries
            items = df.to_dict(orient='records')
            return items

        else:
            logging.error(f"Unsupported file format: {ext}")
            return []

    except Exception as e:
        logging.error(f"Error loading items from {file_path}: {e}")
        return []

def main():
    """Main function to run the batch ingestion utility."""
    parser = argparse.ArgumentParser(description='Batch Ingestion Utility for LanceDB')
    parser.add_argument('--file', type=str, help='Path to JSON or CSV file with items to ingest')
    parser.add_argument('--uri', type=str, help='LanceDB URI')
    parser.add_argument('--table', type=str, help='LanceDB table name')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE, help='Batch size for ingestion')

    args = parser.parse_args()

    # Check required arguments
    if not args.file:
        parser.print_help()
        sys.exit(1)

    # Determine LanceDB URI
    lancedb_uri = args.uri or DEFAULT_S3_URI

    # Determine table name
    table_name = args.table or DEFAULT_TABLE_NAME

    # Configure Gemini
    if not configure_gemini():
        logging.error("Failed to configure Gemini API, exiting")
        sys.exit(1)

    # Load items from file
    items = load_items_from_file(args.file)
    if not items:
        logging.error("No items to ingest, exiting")
        sys.exit(1)

    logging.info(f"Loaded {len(items)} items from {args.file}")

    # Batch ingest items
    start_time = time.time()
    stats = batch_ingest_items(items, lancedb_uri, table_name, args.batch_size)
    end_time = time.time()

    # Print statistics
    print("\n===== Batch Ingestion Statistics =====")
    print(f"Total items: {stats['total_items']}")
    print(f"Successful: {stats['successful']}")
    print(f"Failed: {stats['failed']}")
    print(f"Batches: {stats['batches']}")
    print(f"Embedding failures: {stats['embedding_failures']}")
    print(f"Ingestion failures: {stats['ingestion_failures']}")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print("=====================================\n")

if __name__ == "__main__":
    main()
