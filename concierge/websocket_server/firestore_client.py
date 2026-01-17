"""
Simplified Firestore client utility functions for the WebSocket server.
"""

import os
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Union

import firebase_admin
from firebase_admin import credentials, firestore

# Configure logging
logger = logging.getLogger(__name__)

# Global variables
db = None
firebase_app = None

def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized."""
    global db, firebase_app

    if not firebase_admin._apps:
        try:
            # Try to get credentials from environment variable
            cred_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
            cred_path = os.environ.get('FIREBASE_CREDENTIALS_PATH') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')

            logger.info(f"Initializing Firebase with credentials path: {cred_path}")

            if cred_json:
                # Use credentials JSON directly
                import json
                from tempfile import NamedTemporaryFile

                # Create a temporary file to store the credentials
                with NamedTemporaryFile(suffix='.json', delete=False) as temp_file:
                    temp_file.write(cred_json.encode('utf-8'))
                    temp_path = temp_file.name

                cred = credentials.Certificate(temp_path)
                os.unlink(temp_path)  # Delete the temporary file
            elif cred_path:
                # Use credentials file path
                logger.info(f"Using credentials path: {cred_path}")

                # Check if the file exists
                if not os.path.exists(cred_path):
                    logger.error(f"Credentials file not found at path: {cred_path}")
                    return False

                try:
                    cred = credentials.Certificate(cred_path)
                    logger.info(f"Successfully created certificate object from path: {cred_path}")
                except Exception as cert_error:
                    logger.error(f"Error creating certificate from path {cred_path}: {cert_error}")
                    return False
            else:
                # Use default credentials
                logger.info("No explicit credentials provided, using default credentials")
                firebase_app = firebase_admin.initialize_app()
                try:
                    from concierge.utils.firestore_client import get_firestore_client as _central_get_client
                    db = _central_get_client()
                except Exception:
                    db = firestore.client()
                logger.info("Firebase initialized with default credentials")
                return True

            # Initialize with specific credentials
            firebase_app = firebase_admin.initialize_app(cred)
            try:
                from concierge.utils.firestore_client import get_firestore_client as _central_get_client
                db = _central_get_client()
            except Exception:
                db = firestore.client()
            logger.info("Firebase initialized successfully with credentials")
            return True

        except Exception as e:
            logger.error(f"Error initializing Firebase: {e}")
            return False
    else:
        # If already initialized, ensure db is set
        if db is None:
            try:
                from concierge.utils.firestore_client import get_firestore_client as _central_get_client
                db = _central_get_client()
                logger.info("Firebase already initialized, created new Firestore client")
            except Exception as e:
                logger.error(f"Error creating Firestore client for already initialized app: {e}")
                return False
        else:
            logger.info("Firebase already initialized with existing Firestore client")
        return True

def get_firestore_db():
    """Get the Firestore database instance."""
    if not initialize_firebase():
        return None
    return db

def list_reservations_by_phone(phone_number: str, check_last_four: bool = True) -> List[Dict]:
    """
    List all reservations for a specific phone number.

    Args:
        phone_number: Phone number to search for
        check_last_four: Whether to also check for matches on the last 4 digits

    Returns:
        List of reservations
    """
    if not initialize_firebase():
        return []

    try:
        # Normalize the phone number for comparison
        normalized_phone = phone_number.strip()
        # Create alternate versions to check (with and without +)
        phone_versions = [normalized_phone]
        if normalized_phone.startswith('+'):
            phone_versions.append(normalized_phone[1:])  # Without +
        else:
            phone_versions.append(f"+{normalized_phone}")  # With +

        logger.info(f"Checking for reservations with phone versions: {phone_versions}")
        
        # Store unique reservations by ID to avoid duplicates
        reservations_by_id = {}

        # Check all versions of the phone number
        for phone_version in phone_versions:
            # Try to find reservations where this is the primary guest phone number
            # Check both camelCase and snake_case field names
            primary_queries = [
                db.collection('reservations').where('guestPhoneNumber', '==', phone_version),
                db.collection('reservations').where('GuestPhoneNumber', '==', phone_version),
                db.collection('reservations').where('guest_phone_number', '==', phone_version)
            ]
            
            for query in primary_queries:
                for doc in query.stream():
                    reservation_data = doc.to_dict()
                    reservation_data['id'] = doc.id
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation {doc.id} with primary phone {phone_version}")

            # Check for reservations where this number is in additionalPhoneNumbers array
            additional_queries = [
                db.collection('reservations').where('additionalPhoneNumbers', 'array_contains', phone_version),
                db.collection('reservations').where('AdditionalPhoneNumbers', 'array_contains', phone_version),
                db.collection('reservations').where('additional_phone_numbers', 'array_contains', phone_version)
            ]
            
            for query in additional_queries:
                for doc in query.stream():
                    if doc.id not in reservations_by_id:
                        reservation_data = doc.to_dict()
                        reservation_data['id'] = doc.id
                        reservations_by_id[doc.id] = reservation_data
                        logger.info(f"Found reservation {doc.id} with additional phone {phone_version}")

        # If no reservations found and check_last_four is True, try matching by last 4 digits
        if check_last_four and not reservations_by_id and len(normalized_phone) >= 4:
            last_four_digits = normalized_phone[-4:]
            logger.info(f"No exact matches found, checking last 4 digits: {last_four_digits}")

            # Get all reservations
            all_reservations_query = db.collection('reservations').stream()

            # Check each reservation for matching last 4 digits
            for doc in all_reservations_query:
                if doc.id in reservations_by_id:
                    continue  # Skip if already found
                    
                reservation_data = doc.to_dict()
                reservation_data['id'] = doc.id

                # Check all possible phone fields
                for field in ['guestPhoneNumber', 'GuestPhoneNumber', 'guest_phone_number', 'guest_phone']:
                    guest_phone = reservation_data.get(field)
                    if guest_phone and len(guest_phone) >= 4 and guest_phone.endswith(last_four_digits):
                        reservations_by_id[doc.id] = reservation_data
                        logger.info(f"Found reservation with last 4 digits in {field}: {guest_phone}")
                        break
                
                # If not found yet, check additional contacts
                if doc.id not in reservations_by_id:
                    # Check all possible field names for additional contacts
                    for contacts_field in ['additional_contacts', 'additionalContacts', 'AdditionalContacts']:
                        additional_contacts = reservation_data.get(contacts_field, [])
                        
                        for contact in additional_contacts:
                            # Check all possible phone field names
                            for phone_field in ['phone', 'phoneNumber', 'PhoneNumber', 'phone_number']:
                                contact_phone = contact.get(phone_field)
                                if contact_phone and len(contact_phone) >= 4 and contact_phone.endswith(last_four_digits):
                                    reservations_by_id[doc.id] = reservation_data
                                    logger.info(f"Found reservation with last 4 digits in contact {phone_field}: {contact_phone}")
                                    break
                            
                            # Break out of contacts loop if found
                            if doc.id in reservations_by_id:
                                break
                        
                        # Break out of contacts_field loop if found
                        if doc.id in reservations_by_id:
                            break

        # Convert the dictionary values to a list
        reservations = list(reservations_by_id.values())
        logger.info(f"Found {len(reservations)} unique reservations for phone number {phone_number}")
        return reservations
    except Exception as e:
        logger.error(f"Error listing reservations for phone number {phone_number}: {e}")
        return []
