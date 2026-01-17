"""
Firestore client utility functions for the WebSocket server.
"""

import os
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Union

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK
def initialize_firestore():
    """Initialize the Firestore client."""
    try:
        # Check if Firebase Admin SDK is already initialized
        if not firebase_admin._apps:
            # Get the path to the service account key file
            cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT_ID')
            
            if cred_path and os.path.exists(cred_path):
                # Initialize with service account credentials
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred, {
                    'projectId': project_id
                })
                logger.info(f"Initialized Firebase Admin SDK with service account credentials")
            else:
                # Initialize with default credentials (for local development)
                firebase_admin.initialize_app()
                logger.info(f"Initialized Firebase Admin SDK with default credentials")
        
        # Get Firestore client
        db = firestore.client()
        logger.info(f"Successfully initialized Firestore client")
        return db
    except Exception as e:
        logger.error(f"Error initializing Firestore client: {e}")
        return None

# Firestore client singleton
_firestore_client = None

def get_firestore_client():
    """Get the Firestore client singleton."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = initialize_firestore()
    return _firestore_client

def list_reservations_by_phone(phone_number: str) -> List[Dict]:
    """
    List all reservations for a phone number.
    
    Args:
        phone_number: The phone number to search for.
        
    Returns:
        A list of reservation dictionaries.
    """
    db = get_firestore_client()
    if not db:
        logger.error("Firestore client not initialized")
        return []
    
    reservations = []
    
    try:
        # Get current date in ISO format for filtering active reservations
        now = datetime.now(timezone.utc).isoformat()
        
        # Query reservations where this phone is the primary guest phone
        logger.info(f"Querying reservations for phone {phone_number} as primary guest")
        primary_query = (
            db.collection('reservations')
            .where(filter=FieldFilter('guestPhoneNumber', '==', phone_number))
            .where(filter=FieldFilter('endDate', '>=', now))
        )
        
        primary_docs = primary_query.stream()
        for doc in primary_docs:
            reservation = doc.to_dict()
            reservation['id'] = doc.id
            reservations.append(reservation)
        
        logger.info(f"Found {len(reservations)} reservations where {phone_number} is primary guest")
        
        # Query reservations where this phone is in the additional contacts
        logger.info(f"Querying reservations for phone {phone_number} in additional contacts")
        
        # Unfortunately, we can't directly query for a value in an array of objects in Firestore
        # So we need to get all active reservations and filter them in code
        active_query = (
            db.collection('reservations')
            .where(filter=FieldFilter('endDate', '>=', now))
        )
        
        active_docs = active_query.stream()
        for doc in active_docs:
            reservation = doc.to_dict()
            
            # Skip if we already have this reservation (it was a primary guest match)
            if any(r.get('id') == doc.id for r in reservations):
                continue
                
            # Check if phone number is in additional contacts
            additional_contacts = reservation.get('additionalContacts', [])
            if additional_contacts:
                for contact in additional_contacts:
                    contact_phone = contact.get('phone')
                    if contact_phone == phone_number:
                        reservation['id'] = doc.id
                        reservations.append(reservation)
                        logger.info(f"Found reservation {doc.id} where {phone_number} is an additional contact")
                        break
        
        logger.info(f"Found total of {len(reservations)} reservations for phone {phone_number}")
        
        # Get property details for each reservation
        for reservation in reservations:
            property_id = reservation.get('propertyId')
            if property_id:
                property_data = get_property(property_id)
                if property_data:
                    reservation['property'] = property_data
        
        return reservations
    except Exception as e:
        logger.error(f"Error querying reservations for phone {phone_number}: {e}")
        return []

def get_property(property_id: str) -> Optional[Dict]:
    """
    Get a property by ID.
    
    Args:
        property_id: The property ID.
        
    Returns:
        The property dictionary or None if not found.
    """
    db = get_firestore_client()
    if not db:
        logger.error("Firestore client not initialized")
        return None
    
    try:
        doc_ref = db.collection('properties').document(property_id)
        doc = doc_ref.get()
        
        if doc.exists:
            property_data = doc.to_dict()
            property_data['id'] = doc.id
            return property_data
        else:
            logger.warning(f"Property {property_id} not found")
            return None
    except Exception as e:
        logger.error(f"Error getting property {property_id}: {e}")
        return None
