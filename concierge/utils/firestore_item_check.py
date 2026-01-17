"""
Utility functions for checking knowledge items in Firestore.
These functions replace the LanceDB-related functions in ai_helpers.py.
"""

import os
import logging
import traceback
from typing import Dict, List, Any, Optional, Union, Tuple

# Import Firestore client functions
try:
    from utils.firestore_client import (
        initialize_firebase, get_firestore_client
    )
except ImportError:
    # For Lambda environment where relative imports might work differently
    try:
        from concierge.utils.firestore_client import (
            initialize_firebase, get_firestore_client
        )
    except ImportError:
        logging.warning("Could not import firestore_client, item check functionality will be disabled")
        initialize_firebase = None
        get_firestore_client = None

def check_item_in_firestore(property_id: str, item_id: str) -> bool:
    """
    Checks if a specific knowledge item exists in Firestore for the given property_id.
    
    Args:
        property_id (str): The ID of the property.
        item_id (str): The ID of the knowledge item.
        
    Returns:
        bool: True if the item exists, False otherwise.
    """
    try:
        # Initialize Firebase if needed
        if not initialize_firebase:
            logging.error("Firebase initialization function not available")
            return False
        
        if not initialize_firebase():
            logging.error("Failed to initialize Firebase")
            return False
        
        # Get Firestore client
        db = get_firestore_client()
        if not db:
            logging.error("Failed to get Firestore client")
            return False
        
        # Check if the item exists
        doc_ref = db.collection('knowledge_items').document(item_id)
        doc = doc_ref.get()
        
        if doc.exists:
            # Verify it belongs to the specified property
            doc_data = doc.to_dict()
            if doc_data.get('propertyId') == property_id:
                return True
        
        return False
    
    except Exception as e:
        logging.error(f"Error checking item '{item_id}' for property '{property_id}' in Firestore: {e}")
        traceback.print_exc()
        return False

def check_item_in_firestore_with_content(property_id: str, item_id: str, 
                                        question: str = None, answer: str = None) -> Dict:
    """
    Checks if a specific knowledge item exists in Firestore and verifies content match.
    
    Args:
        property_id (str): The ID of the property.
        item_id (str): The ID of the knowledge item.
        question (str, optional): The question text to compare against.
        answer (str, optional): The answer text to compare against.
        
    Returns:
        dict: A dictionary containing:
            - 'exists' (bool): True if the item exists in Firestore
            - 'content_match' (bool): True if content matches (or None if item doesn't exist)
            - 'details' (dict): Details about content mismatches if any
    """
    result = {
        'exists': False,
        'content_match': None,
        'details': {}
    }
    
    try:
        # Initialize Firebase if needed
        if not initialize_firebase:
            logging.error("Firebase initialization function not available")
            result['details']['error'] = "Firebase initialization function not available"
            return result
        
        if not initialize_firebase():
            logging.error("Failed to initialize Firebase")
            result['details']['error'] = "Failed to initialize Firebase"
            return result
        
        # Get Firestore client
        db = get_firestore_client()
        if not db:
            logging.error("Failed to get Firestore client")
            result['details']['error'] = "Failed to get Firestore client"
            return result
        
        # Check if the item exists
        doc_ref = db.collection('knowledge_items').document(item_id)
        doc = doc_ref.get()
        
        if doc.exists:
            # Get the document data
            doc_data = doc.to_dict()
            
            # Verify it belongs to the specified property
            if doc_data.get('propertyId') == property_id:
                result['exists'] = True
                
                # If we have question and answer, check content match
                if question is not None and answer is not None:
                    # Get content from the document
                    firestore_content = doc_data.get('content', '')
                    
                    # For backward compatibility, check if we have question/answer fields
                    firestore_question = doc_data.get('question', '')
                    firestore_answer = doc_data.get('answer', '')
                    
                    # Check content match
                    if firestore_question and firestore_answer:
                        # Check question/answer match
                        question_match = question.strip() == firestore_question.strip()
                        answer_match = answer.strip() == firestore_answer.strip()
                        
                        result['content_match'] = question_match and answer_match
                        
                        # Add details if content doesn't match
                        if not result['content_match']:
                            result['details']['mismatches'] = {
                                'question_match': question_match,
                                'answer_match': answer_match
                            }
                            
                            if not question_match:
                                result['details']['firestore_question'] = firestore_question
                                
                            if not answer_match:
                                result['details']['firestore_answer'] = firestore_answer
                    elif firestore_content:
                        # Check if content contains the question and answer
                        combined_text = f"Question: {question}\nAnswer: {answer}"
                        content_match = combined_text.strip() == firestore_content.strip()
                        
                        result['content_match'] = content_match
                        
                        if not content_match:
                            result['details']['mismatches'] = {
                                'content_match': content_match
                            }
                            result['details']['firestore_content'] = firestore_content
        
        return result
    
    except Exception as e:
        logging.error(f"Error checking item '{item_id}' for property '{property_id}' in Firestore: {e}")
        traceback.print_exc()
        result['details']['error'] = str(e)
        return result

def batch_check_items_in_firestore(property_id: str, items: List[Dict]) -> Dict:
    """
    Efficiently checks multiple knowledge items in Firestore.
    
    Args:
        property_id (str): The ID of the property.
        items (list): List of dictionaries containing knowledge items.
        
    Returns:
        dict: A dictionary mapping item IDs to their Firestore status:
            {
                'item_id': {
                    'exists': bool,
                    'content_match': bool or None,
                    'details': dict with any mismatch details
                },
                ...
            }
    """
    results = {}
    
    # Initialize all items with default values
    for item in items:
        item_id = item.get('SK', '').split('#')[-1] if item.get('SK') else ''
        if not item_id:
            continue
            
        results[item_id] = {
            'exists': False,
            'content_match': None,
            'details': {}
        }
    
    try:
        # Initialize Firebase if needed
        if not initialize_firebase:
            logging.error("Firebase initialization function not available")
            return results
        
        if not initialize_firebase():
            logging.error("Failed to initialize Firebase")
            return results
        
        # Get Firestore client
        db = get_firestore_client()
        if not db:
            logging.error("Failed to get Firestore client")
            return results
        
        # Get all knowledge items for the property
        docs = db.collection('knowledge_items').where('propertyId', '==', property_id).stream()
        
        # Create a map of document IDs to documents
        firestore_items = {}
        for doc in docs:
            firestore_items[doc.id] = doc.to_dict()
        
        # Check each item
        for item in items:
            item_id = item.get('SK', '').split('#')[-1] if item.get('SK') else ''
            if not item_id:
                continue
                
            if item_id in firestore_items:
                results[item_id]['exists'] = True
                
                # Check content match if we have question and answer
                question = item.get('Question', '')
                answer = item.get('Answer', '')
                
                if question and answer:
                    firestore_item = firestore_items[item_id]
                    
                    # Get content from the document
                    firestore_content = firestore_item.get('content', '')
                    
                    # For backward compatibility, check if we have question/answer fields
                    firestore_question = firestore_item.get('question', '')
                    firestore_answer = firestore_item.get('answer', '')
                    
                    # Check content match
                    if firestore_question and firestore_answer:
                        # Check question/answer match
                        question_match = question.strip() == firestore_question.strip()
                        answer_match = answer.strip() == firestore_answer.strip()
                        
                        results[item_id]['content_match'] = question_match and answer_match
                        
                        # Add details if content doesn't match
                        if not results[item_id]['content_match']:
                            results[item_id]['details']['mismatches'] = {
                                'question_match': question_match,
                                'answer_match': answer_match
                            }
                    elif firestore_content:
                        # Check if content contains the question and answer
                        combined_text = f"Question: {question}\nAnswer: {answer}"
                        content_match = combined_text.strip() == firestore_content.strip()
                        
                        results[item_id]['content_match'] = content_match
        
        return results
    
    except Exception as e:
        logging.error(f"Error batch checking items for property '{property_id}' in Firestore: {e}")
        traceback.print_exc()
        return results
