"""
Utility functions for batch operations with Firestore.
These functions replace the LanceDB-related batch functions.
"""

import os
import time
import random
import logging
import traceback
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timezone

# Import Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError as e:
    logging.warning(f"Error importing firebase_admin: {e}")
    firebase_admin = None

def initialize_firebase():
    """Initialize Firebase if not already initialized."""
    try:
        # Check if Firebase Admin SDK is available
        if firebase_admin is None:
            logging.critical("Firebase Admin SDK not available")
            return False

        # Check if Firebase app is already initialized
        try:
            firebase_admin.get_app()
            logging.info("Firebase app already initialized")
            return True
        except ValueError:
            # Initialize Firebase app
            cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            if not cred_path:
                logging.critical("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
                return False

            try:
                # Initialize with credentials file
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logging.info("Firebase app initialized with credentials file")
                return True
            except Exception as cred_err:
                logging.error(f"Error initializing Firebase with credentials file: {cred_err}")
                # Try default credentials as fallback
                try:
                    firebase_admin.initialize_app()
                    logging.info("Firebase app initialized with default credentials")
                    return True
                except Exception as default_err:
                    logging.critical(f"Error initializing Firebase with default credentials: {default_err}")
                    return False

    except Exception as e:
        logging.critical(f"Firebase initialization failed: {e}")
        traceback.print_exc()
        return False

def get_firestore_db():
    """Get Firestore database client."""
    if not initialize_firebase():
        return None
    
    try:
        # Use central Firestore client to ensure environment-aware database selection
        try:
            from concierge.utils.firestore_client import get_firestore_client as _central_get_client
            db = _central_get_client()
        except Exception:
            db = firestore.client()
        return db
    except Exception as e:
        logging.error(f"Error getting Firestore client: {e}")
        return None

def upsert_batch_to_firestore(items: List[Dict[str, Any]], embeddings: List[List[float]]) -> Dict:
    """
    Upsert a batch of knowledge items into Firestore.
    
    Args:
        items: List of items to upsert
        embeddings: List of embedding vectors for each item
        
    Returns:
        Dict with statistics about the operation
    """
    db = get_firestore_db()
    if not db:
        logging.critical("Firestore database not initialized")
        return {"success": 0, "failed": len(items)}
    
    if not items:
        logging.warning("No items to upsert")
        return {"success": 0, "failed": 0}
    
    if len(items) != len(embeddings):
        logging.error(f"Number of items ({len(items)}) does not match number of embeddings ({len(embeddings)})")
        return {"success": 0, "failed": len(items)}
    
    # Process each item individually
    success_count = 0
    failed_items = []
    normalized_id_mapping = {}  # Map to track original to normalized IDs
    
    # Function to perform Firestore operations with retry logic
    def perform_with_retry(operation_func, max_retries=3, initial_backoff=1):
        """Execute an operation with retry logic and exponential backoff."""
        retries = 0
        last_exception = None
        
        while retries < max_retries:
            try:
                return operation_func()
            except Exception as e:
                last_exception = e
                retries += 1
                if retries >= max_retries:
                    logging.error(f"Operation failed after {max_retries} retries: {e}")
                    break
                
                # Calculate backoff time with exponential increase and some randomness
                backoff_time = initial_backoff * (2 ** (retries - 1)) * (0.5 + random.random())
                logging.warning(f"Operation failed (attempt {retries}), retrying in {backoff_time:.2f} seconds: {e}")
                time.sleep(backoff_time)
        
        # If we get here, all retries failed
        raise last_exception
    
    # Process in batches
    batch = db.batch()
    batch_size = 0
    max_batch_size = 500  # Firestore batch size limit
    
    for i, item in enumerate(items):
        # Get required fields
        item_id = item.get('id') or item.get('qna_id')
        property_id = item.get('property_id') or item.get('propertyId')
        question = item.get('question', '')
        answer = item.get('answer', '')
        content = item.get('content', '')
        
        # Skip items with missing required fields
        if not item_id or not property_id:
            logging.warning(f"Skipping item {i} due to missing required fields")
            failed_items.append(item_id if item_id else f"item_{i}")
            continue
        
        # Normalize the ID - extract just the UUID part if it contains a prefix
        normalized_id = item_id
        if '#' in item_id:
            # Extract the UUID part (last part after #)
            normalized_id = item_id.split('#')[-1]
            logging.info(f"Normalized ID from '{item_id}' to '{normalized_id}'")
        
        # Track the mapping for DynamoDB updates later
        normalized_id_mapping[normalized_id] = item_id
        
        # Determine content to use
        if not content and question and answer:
            content = f"Question: {question}\nAnswer: {answer}"
        
        # Create data for Firestore
        data = {
            "propertyId": property_id,
            "content": content,
            "embedding": embeddings[i],
            "updatedAt": firestore.SERVER_TIMESTAMP
        }
        
        # Add question/answer fields for backward compatibility
        if question and answer:
            data["question"] = question
            data["answer"] = answer
        
        # Add to batch
        doc_ref = db.collection('knowledge_items').document(normalized_id)
        batch.set(doc_ref, data)
        batch_size += 1
        
        # If batch is full, commit it
        if batch_size >= max_batch_size:
            try:
                # Commit batch with retry
                def commit_operation():
                    batch.commit()
                    return batch_size
                
                # Execute with retry
                perform_with_retry(commit_operation)
                success_count += batch_size
                logging.info(f"Successfully committed batch of {batch_size} items to Firestore")
                
                # Reset batch
                batch = db.batch()
                batch_size = 0
            except Exception as batch_err:
                logging.error(f"Error committing batch to Firestore: {batch_err}")
                # Count all items in the failed batch as failed
                failed_items.extend([items[j].get('id', items[j].get('qna_id', f"item_{j}")) for j in range(i-batch_size+1, i+1)])
                
                # Reset batch
                batch = db.batch()
                batch_size = 0
    
    # Commit any remaining items in the batch
    if batch_size > 0:
        try:
            # Commit batch with retry
            def commit_operation():
                batch.commit()
                return batch_size
            
            # Execute with retry
            perform_with_retry(commit_operation)
            success_count += batch_size
            logging.info(f"Successfully committed final batch of {batch_size} items to Firestore")
        except Exception as batch_err:
            logging.error(f"Error committing final batch to Firestore: {batch_err}")
            # Count all items in the failed batch as failed
            failed_items.extend([items[j].get('id', items[j].get('qna_id', f"item_{j}")) for j in range(len(items)-batch_size, len(items))])
    
    # Return statistics
    return {
        "success": success_count,
        "failed": len(items) - success_count,
        "normalized_ids": normalized_id_mapping
    }
