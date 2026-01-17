"""
Firestore client utility functions for Concierge application.
Provides functions to interact with Firestore collections for users, properties,
knowledge sources, knowledge items, reservations, and magic links.
"""

import os
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Union
import traceback
import warnings
import hashlib
import secrets
import json
import base64

# Load environment variables early
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, continue with existing env vars
from firebase_admin import firestore, credentials, initialize_app
import firebase_admin
from google.cloud import firestore_v1 as gc_firestore
from google.cloud.firestore import Query
from google.cloud.exceptions import NotFound

# Suppress the warning about using positional arguments in where() method
warnings.filterwarnings("ignore", message="Detected filter using positional arguments")

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore, auth
from google.cloud.firestore_v1.base_query import FieldFilter, Or, And
from google.cloud.firestore_v1 import vector
# Vector class is now accessed as vector.Vector

# Import Gemini - Updated to use new google-genai SDK
try:
    import google.genai as genai
    # Keep legacy import for backward compatibility
    import google.generativeai as legacy_genai
except ImportError:
    genai = None
    legacy_genai = None
    logging.warning("google.genai module not imported - embedding generation will fail!")

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global variables
db = None
firebase_app = None
gen_ai_client = None
gemini_configured = False

# Constants
EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_TASK_TYPE = "retrieval_document"
EMBEDDING_DIMENSION = 768  # Gemini embedding dimension

def _determine_firestore_database_id() -> str:
    """Determine Firestore database ID for current environment.

    production -> '(default)'; otherwise -> 'development'.
    """
    deployment_env = os.environ.get('DEPLOYMENT_ENV', '').lower()
    if deployment_env == 'production':
        return '(default)'
    return 'development'

def _create_firestore_client_for_database(database_id: str):
    """Create a Firestore client targeting a specific database ID using Admin app creds."""
    try:
        if not firebase_admin._apps:
            return None
        app = firebase_admin.get_app()
        credentials_obj = app.credential.get_credential()
        project_id = (
            app.project_id
            or os.environ.get('FIREBASE_PROJECT_ID')
            or os.environ.get('GOOGLE_CLOUD_PROJECT')
            or os.environ.get('GOOGLE_CLOUD_PROJECT_ID')
        )
        if not project_id:
            logger.error("Unable to resolve project ID for Firestore client")
            return None
        return gc_firestore.Client(project=project_id, credentials=credentials_obj, database=database_id)
    except Exception as e:
        logger.error(f"Failed to create Firestore client for database '{database_id}': {e}")
        return None

def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized."""
    global db, firebase_app

    # Check if Firebase is already initialized and working
    if firebase_admin._apps:
        try:
            # Test if the existing app is working
            test_db = firestore.client()
            # If we get here, Firebase is already properly initialized
            return True
        except Exception as e:
            logger.warning(f"Existing Firebase app not working, reinitializing: {e}")
            # Clean up broken apps
            apps_to_delete = list(firebase_admin._apps.values())
            for app in apps_to_delete:
                try:
                    firebase_admin.delete_app(app)
                    logger.info(f"Deleted existing Firebase app: {app.name}")
                except Exception as e:
                    logger.warning(f"Error deleting Firebase app: {e}")
            firebase_admin._apps.clear()

    if not firebase_admin._apps:
        try:
            # First try to use GOOGLE_APPLICATION_CREDENTIALS environment variable
            google_creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if google_creds_path and os.path.exists(google_creds_path):
                cred = credentials.Certificate(google_creds_path)
                firebase_admin.initialize_app(cred)
                logger.info(f"Firebase Admin initialized with GOOGLE_APPLICATION_CREDENTIALS: {google_creds_path}")
                return True

            # Check for service account key file - try multiple possible paths
            service_account_paths = [
                'concierge/credentials/clean-art-454915-d9-firebase-adminsdk-fbsvc-9e1734f79e.json',
                'credentials/clean-art-454915-d9-firebase-adminsdk-fbsvc-9e1734f79e.json',
                'concierge/credentials/serviceAccountKey.json',
                'credentials/serviceAccountKey.json',
                # Server paths (for staging/production deployment)
                '/app/dashboard/concierge/credentials/serviceAccountKey.json',
                '/app/dashboard/credentials/serviceAccountKey.json',
                '/app/dashboard/concierge/credentials/clean-art-454915-d9-firebase-adminsdk-fbsvc-9e1734f79e.json',
                '/app/dashboard/credentials/clean-art-454915-d9-firebase-adminsdk-fbsvc-9e1734f79e.json'
            ]

            cred = None
            for service_account_path in service_account_paths:
                if os.path.exists(service_account_path):
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    logger.info(f"Firebase Admin initialized with service account key: {service_account_path}")
                    break

            if cred is None:
                # Fall back to default credentials (for production)
                firebase_admin.initialize_app()
                logger.info("Firebase Admin initialized with default credentials")



            return True
        except Exception as e:
            logger.error(f"Error initializing Firebase: {e}")
            return False
    return True

# Initialize Firebase when module is imported
firebase_init_success = initialize_firebase()

# Get Firestore client (environment-aware database selection)
try:
    if firebase_init_success:
        _db_id = _determine_firestore_database_id()
        db = _create_firestore_client_for_database(_db_id)
        if db:
            logger.info(f"Firestore client initialized for database '{_db_id}'")
        else:
            logger.error("Failed to initialize Firestore client for selected database")
    else:
        logger.error("Firebase initialization failed, Firestore client not available")
        db = None
except Exception as e:
    logger.error(f"Error creating Firestore client: {e}")
    db = None

def get_firestore_client():
    """Get the Firestore client instance."""
    global db
    if not initialize_firebase():
        logger.error("Firebase initialization failed in get_firestore_client()")
        return None
    
    if db is None:
        try:
            _db_id = _determine_firestore_database_id()
            db = _create_firestore_client_for_database(_db_id)
            if db is None:
                logger.error("Failed to create Firestore client instance for selected database")
                return None
            logger.info(f"Created new Firestore client instance for database '{_db_id}'")
        except Exception as e:
            logger.error(f"Error creating Firestore client in get_firestore_client(): {e}")
            return None
    
    return db

def get_firestore_db():
    """Get the Firestore database instance."""
    if not initialize_firebase():
        return None
    return get_firestore_client()

def configure_gemini():
    """
    Configure Gemini for embedding generation using the new google-genai SDK.
    """
    global gemini_configured

    if genai is None:
        logger.error("google.genai module not available")
        return False

    try:
        # With the new SDK, we don't need global configuration
        # API key is passed when creating the client
        api_key = os.environ.get('GEMINI_API_KEY')
        if api_key:
            logger.info("Gemini API key available for new SDK")
            gemini_configured = True
            return True
        else:
            logger.error("GEMINI_API_KEY environment variable not set")
            return False
    except Exception as e:
        logger.error(f"Error configuring Gemini: {e}")
        return False

def generate_embedding(text, task_type="RETRIEVAL_QUERY"):
    """
    Generate embeddings for text using Gemini with the new google-genai SDK.

    Args:
        text (str): Text to generate embeddings for
        task_type (str): Type of task for embedding generation

    Returns:
        List[float]: Embedding vector or None if failed
    """
    try:
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding generation")
            return None

        if genai is None:
            logger.error("google.genai module not available")
            return None

        # Check if Gemini is configured
        if not gemini_configured:
            if not configure_gemini():
                logger.error("Failed to configure Gemini")
                return None

        # Create client with the new SDK
        client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))

        # Generate embedding using the new SDK syntax
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[text],  # Changed from 'content' to 'contents'
            config={
                'task_type': task_type
            }
        )

        # Extract embedding from result
        if (hasattr(result, 'embeddings') and
            result.embeddings and
            len(result.embeddings) > 0):
            embedding = result.embeddings[0].values
            logger.debug(f"Generated embedding of dimension {len(embedding)}")
            return embedding
        else:
            logger.error(f"No embedding in response: {result}")
            return None

    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        import traceback
        traceback.print_exc()
        return None

# === User Functions ===

def get_user(user_id: str) -> Optional[Dict]:
    """Get a user by ID."""
    if not initialize_firebase():
        return None

    try:
        doc_ref = db.collection('users').document(user_id)
        doc = doc_ref.get()

        if doc.exists:
            user_data = doc.to_dict()
            user_data['uid'] = doc.id  # Add uid to the data
            return user_data
        else:
            logger.warning(f"User {user_id} not found")
            return None
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {e}")
        return None

def create_user(user_id: str, user_data: Dict) -> bool:
    """Create a new user with the given ID."""
    if not initialize_firebase():
        return False

    try:
        # Add timestamps
        timestamp = datetime.now(timezone.utc)
        user_data['createdAt'] = timestamp
        user_data['updatedAt'] = timestamp

        # Set the document with merge=True to update if it exists
        db.collection('users').document(user_id).set(user_data, merge=True)
        logger.info(f"User {user_id} created/updated successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return False

def update_user(user_id: str, user_data: Dict) -> bool:
    """
    Update an existing user in Firestore.

    Args:
        user_id: The ID of the user to update
        user_data: Dictionary containing user data to update

    Returns:
        True if update was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Add updated timestamp
        user_data['updatedAt'] = datetime.now(timezone.utc)

        # Check if user exists first
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            # Update the document
            user_ref.update(user_data)
            logger.info(f"User {user_id} updated successfully in Firestore")
            return True
        else:
            # Create the user if it doesn't exist
            user_data['createdAt'] = datetime.now(timezone.utc)
            user_ref.set(user_data)
            logger.info(f"User {user_id} created in Firestore (didn't exist during update)")
            return True
    except Exception as e:
        logger.error(f"Error updating user {user_id} in Firestore: {e}")
        return False

def find_user_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Find a user by their phone number.
    
    Args:
        phone_number: Phone number to search for (should be cleaned format)
        
    Returns:
        User data dictionary if found, None otherwise
    """
    try:
        # Query users collection by phone number
        users_ref = db.collection('users')
        query = users_ref.where('phoneNumber', '==', phone_number).limit(1)
        results = query.get()
        
        if results:
            user_doc = results[0]
            user_data = user_doc.to_dict()
            user_data['id'] = user_doc.id
            return user_data
        
        return None

    except Exception as e:
        logger.error(f"Error finding user by phone {phone_number}: {e}")
        return None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Find a user by their email address.

    Args:
        email: Email address to search for

    Returns:
        User data dictionary if found, None otherwise
    """
    try:
        # Query users collection by email address
        users_ref = db.collection('users')
        query = users_ref.where('email', '==', email).limit(1)
        results = query.get()

        if results:
            user_doc = results[0]
            user_data = user_doc.to_dict()
            user_data['id'] = user_doc.id
            return user_data

        return None

    except Exception as e:
        logger.error(f"Error finding user by email {email}: {e}")
        return None

def find_users_by_phone_flexible(phone_number: str) -> List[Dict]:
    """
    Find users by phone number with flexible matching (handles different formats).

    Args:
        phone_number: Phone number to search for

    Returns:
        List of user data dictionaries
    """
    if not initialize_firebase():
        return []

    try:
        from concierge.utils.phone_utils import generate_phone_variations
        
        # Generate phone number variations for flexible matching
        phone_variations = generate_phone_variations(phone_number)
        logger.info(f"Searching for users with phone variations: {phone_variations}")

        users_by_id = {}  # Deduplicate by user ID

        # Search for each phone variation
        for phone_variation in phone_variations:
            users_query = db.collection('users').where('phoneNumber', '==', phone_variation)
            for user_doc in users_query.stream():
                user_data = user_doc.to_dict()
                user_data['id'] = user_doc.id
                users_by_id[user_doc.id] = user_data

        users_list = list(users_by_id.values())
        logger.info(f"Found {len(users_list)} users with phone variations of {phone_number}")
        return users_list

    except Exception as e:
        logger.error(f"Error finding users by phone number {phone_number}: {e}")
        return []

def check_magic_link_session(token: str, session_user_id: str) -> Dict[str, any]:
    """
    Check if current session is valid for the given magic link token.
    
    Args:
        token: Magic link token
        session_user_id: User ID from current session
        
    Returns:
        Dictionary with session status and user info
    """
    try:
        # Get magic link data
        magic_link_data = get_magic_link_by_token(token)
        if not magic_link_data:
            return {
                'valid': False,
                'reason': 'invalid_token',
                'action': 'show_pin_screen'
            }
        
        # Check if session user matches any user associated with this magic link
        associated_users = []
        
        # Check temp users created from this magic link
        if magic_link_data.get('temp_user_id'):
            associated_users.append(magic_link_data['temp_user_id'])
            
        # Check permanent users who verified via this magic link
        if magic_link_data.get('verified_user_id'):
            associated_users.append(magic_link_data['verified_user_id'])
            
        # Check migrated users
        migrated_users = magic_link_data.get('migrated_users', [])
        associated_users.extend(migrated_users)
        
        if session_user_id in associated_users:
            return {
                'valid': True,
                'user_id': session_user_id,
                'action': 'dashboard_access'
            }
        else:
            return {
                'valid': False,
                'reason': 'session_user_mismatch',
                'action': 'show_pin_screen'
            }
            
    except Exception as e:
        logger.error(f"Error checking magic link session: {e}")
        return {
            'valid': False,
            'reason': 'error',
            'action': 'show_pin_screen'
        }

def enhanced_user_detection(reservation_phone: str, entered_pin: str, magic_link_token: str) -> Dict[str, any]:
    """
    Enhanced user detection with multiple strategies for magic link authentication.
    
    Args:
        reservation_phone: Phone number from reservation
        entered_pin: PIN entered by user
        magic_link_token: Magic link token
        
    Returns:
        Dictionary with detection results and next action
    """
    try:
        from concierge.utils.phone_utils import normalize_phone_number, get_phone_last_4
        
        # Normalize the reservation phone number
        normalized_phone = normalize_phone_number(reservation_phone)
        phone_last_4 = get_phone_last_4(normalized_phone)
        
        logger.info(f"Enhanced user detection for phone {reservation_phone} (normalized: {normalized_phone}), PIN: {entered_pin}")
        
        # Get magic link data to check for existing temp users
        # Try property-based magic link first, then fall back to reservation-based
        property_data = get_property_by_magic_link_token(magic_link_token)
        if property_data:
            # Property-based magic link - create minimal magic_link_data structure
            magic_link_data = {
                'property_id': property_data.get('id'),
                'property_name': property_data.get('name'),
                'is_property_based': True,
                'is_active': True,
                'status': 'active'
            }
        else:
            # Try reservation-based magic link
            magic_link_data = get_magic_link_by_token(magic_link_token)
            if not magic_link_data:
                return {
                    'status': 'error',
                    'message': 'Invalid magic link'
                }
        
        # Check if user rejected confirmation and wants new temp user
        # BUT only if there's an existing migrated temp user with a name
        if magic_link_data.get('force_new_temp_user'):
            logger.info(f"Force new temp user flag detected for token {magic_link_token[:8]}...")
            
            # Check if there's an existing temp user to understand context
            token_hash = hash_magic_link_token(magic_link_token)
            temp_user_id = f"temp_magic_{token_hash[:12]}"
            existing_temp_user = get_temporary_user(temp_user_id)
            
            # Only force new temp user if the existing one has migrated AND has a name
            if (existing_temp_user and 
                existing_temp_user.get('migration_status') == 'migrated' and 
                existing_temp_user.get('displayName')):
                logger.info(f"Forcing new temp user because existing user {existing_temp_user.get('displayName')} has migrated")
                if entered_pin == phone_last_4:
                    return {
                        'status': 'create_new_temp_user',
                        'message': 'Creating new temporary account as requested'
                    }
                else:
                    return {
                        'status': 'verification_failed',
                        'message': 'Incorrect PIN'
                    }
            else:
                logger.info(f"Clearing force_new_temp_user flag - no migrated user with name exists")
                # Clear the flag and continue with normal detection logic (only for reservation-based magic links)
                if not magic_link_data.get('is_property_based'):
                    update_magic_link(hash_magic_link_token(magic_link_token), {
                        'force_new_temp_user': False
                    })
        
        # Check for existing temp user from this magic link with matching PIN
        token_hash = hash_magic_link_token(magic_link_token)
        temp_user_id = f"temp_magic_{token_hash[:12]}"
        existing_temp_user = get_temporary_user(temp_user_id)
        
        logger.info(f"Looking for temp user: {temp_user_id}")
        logger.info(f"Existing temp user found: {bool(existing_temp_user)}")
        if existing_temp_user:
            logger.info(f"Temp user data: {existing_temp_user}")
        
        if existing_temp_user:
            stored_pin = existing_temp_user.get('pinCode')
            migration_status = existing_temp_user.get('migration_status', 'active')
            access_disabled = existing_temp_user.get('access_disabled', False)
            temp_user_name = existing_temp_user.get('displayName')
            migrated_to_user_id = existing_temp_user.get('migrated_to_user_id')
            
            logger.info(f"Temp user PIN check: stored={stored_pin}, entered={entered_pin}, migration_status={migration_status}, access_disabled={access_disabled}")
            
            # Handle migrated users first - check if this is a migrated user with a name
            if (migration_status == 'migrated' or access_disabled) and temp_user_name:
                logger.info(f"Migrated user detected: temp_user_name='{temp_user_name}', migrated_to={migrated_to_user_id}")
                
                # For migrated users, check if PIN is valid (either default or stored custom PIN)
                pin_is_valid = (entered_pin == phone_last_4 or entered_pin == stored_pin)
                
                if pin_is_valid:
                    logger.info(f"Returning migrated_user_confirmation for user {temp_user_name} (PIN valid: entered={entered_pin}, stored={stored_pin}, phone_last_4={phone_last_4})")
                    return {
                        'status': 'migrated_user_confirmation',
                        'permanent_user_id': migrated_to_user_id,  # May be None, but that's handled later
                        'temp_user_name': temp_user_name,
                        'message': f"This magic link was previously used by {temp_user_name}. Are you {temp_user_name}?"
                    }
                else:
                    logger.info(f"PIN invalid for migrated user {temp_user_name}: stored={stored_pin}, entered={entered_pin}, phone_last_4={phone_last_4}")
                    return {
                        'status': 'verification_failed',
                        'message': f'This magic link was used by {temp_user_name}. Please enter either your custom PIN or the default PIN ({phone_last_4}).'
                    }
            
            # Handle active temp users
            elif stored_pin == entered_pin or (entered_pin == phone_last_4 and stored_pin == phone_last_4):
                if migration_status == 'migrated' or access_disabled:
                    # This shouldn't happen given the logic above, but handle as fallback
                    if migrated_to_user_id and temp_user_name:
                        logger.info(f"Returning migrated_user_confirmation for user {temp_user_name} (fallback)")
                        return {
                            'status': 'migrated_user_confirmation',
                            'permanent_user_id': migrated_to_user_id,
                            'temp_user_name': temp_user_name,
                            'message': f"This magic link was previously used by {temp_user_name}. Are you {temp_user_name}?"
                        }
                    else:
                        return {
                            'status': 'error',
                            'message': 'Migration data incomplete'
                        }
                else:
                    # Active temp user - allow access and use existing user
                    logger.info(f"Reusing existing temp user {temp_user_id} with name: {temp_user_name}")
                    return {
                        'status': 'temp_user_access',
                        'user_id': temp_user_id,
                        'message': 'Access granted to existing temporary account',
                        'existing_name': temp_user_name
                    }
        
        # No existing temp user with matching PIN
        # Check if PIN matches phone last-4 (default PIN)
        logger.info(f"No existing temp user found or PIN mismatch. Checking default PIN: entered={entered_pin}, phone_last_4={phone_last_4}")
        if entered_pin == phone_last_4:
            logger.info("Creating new temp user - PIN matches phone last-4")
            return {
                'status': 'new_temp_user_needed',
                'message': 'Create new temporary user'
            }
        
        # PIN doesn't match default - verification failed
        return {
            'status': 'verification_failed',
            'message': 'Incorrect PIN'
        }
        
    except Exception as e:
        logger.error(f"Error in enhanced user detection: {e}")
        return {
            'status': 'error',
            'message': 'Detection failed'
        }

def attach_reservation_to_permanent_user(user_id: str, reservation_id: str, token: str = None) -> bool:
    """
    Attach a reservation to a permanent user's account.
    
    Args:
        user_id: Permanent user ID
        reservation_id: Reservation ID to attach
        token: Optional magic link token for tracking
        
    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False
        
    try:
        # Get user data
        user_doc = db.collection('users').document(user_id).get()
        if not user_doc.exists:
            logger.error(f"User {user_id} not found")
            return False
            
        user_data = user_doc.to_dict()
        current_reservations = user_data.get('reservationIds', [])
        
        # Add reservation if not already attached
        if reservation_id not in current_reservations:
            current_reservations.append(reservation_id)
            
            # Prepare update data
            update_data = {
                'reservationIds': current_reservations,
                'updatedAt': datetime.now(timezone.utc)
            }
            
            # Add token tracking if provided
            if token:
                update_data['lastMagicLinkAccess'] = hash_magic_link_token(token)
                update_data['lastMagicLinkAccessAt'] = firestore.SERVER_TIMESTAMP
            
            # Update user document
            db.collection('users').document(user_id).update(update_data)
            
            logger.info(f"Attached reservation {reservation_id} to user {user_id}")
            return True
        else:
            logger.info(f"Reservation {reservation_id} already attached to user {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error attaching reservation {reservation_id} to user {user_id}: {e}")
        return False

def create_permanent_user_from_magic_link(firebase_uid: str, user_data: Dict) -> Optional[str]:
    """
    Create a new permanent user account from magic link signup.
    If user already exists, add roles instead of overwriting.
    
    Args:
        firebase_uid: Firebase UID for the new user
        user_data: User data including name, phone, role, etc.
        
    Returns:
        User ID if successful, None otherwise
    """
    try:
        db = get_firestore_client()
        if not db:
            logger.error("Failed to get Firestore client")
            return None
        
        # Check if user already exists
        existing_user = get_user(firebase_uid)
        
        if existing_user:
            # User already exists - update their roles instead of overwriting
            logger.info(f"User {firebase_uid} already exists, updating roles instead of creating new user")
            
            from concierge.utils.role_helpers import add_role
            new_role = user_data.get('role', 'guest')
            updated_user_data = add_role(existing_user, new_role)
            
            # Update only the necessary fields, preserving existing data
            update_data = {
                'role': updated_user_data['role'],
                'lastLoginAt': firestore.SERVER_TIMESTAMP,
                'isTemporary': False  # Ensure they're marked as permanent
            }
            
            # Only update phone number if it's not already set
            if not existing_user.get('phoneNumber') and user_data.get('phoneNumber'):
                update_data['phoneNumber'] = user_data['phoneNumber']
            
            # Update the user document
            success = update_user(firebase_uid, update_data)
            
            if success:
                logger.info(f"Successfully updated existing user {firebase_uid} with role {new_role}")
                return firebase_uid
            else:
                logger.error(f"Failed to update existing user {firebase_uid}")
                return None
        
        else:
            # User doesn't exist - create new user
            logger.info(f"Creating new permanent user {firebase_uid}")
            
            # Prepare user document data
            user_doc_data = {
                'uid': firebase_uid,
                'phoneNumber': user_data.get('phoneNumber', ''),
                'displayName': user_data.get('displayName', 'New User'),
                'email': user_data.get('email', ''),
                'role': user_data.get('role', 'guest'),
                'isTemporary': False,
                'createdAt': firestore.SERVER_TIMESTAMP,
                'lastLoginAt': firestore.SERVER_TIMESTAMP,
                'accessLevel': 'full_access',
                'accountType': 'permanent',
                'createdFromMagicLink': user_data.get('createdFromMagicLink'),
                'reservationIds': [],
                'propertyIds': []
            }
            
            # Create the user document
            db.collection('users').document(firebase_uid).set(user_doc_data)
            
            logger.info(f"Created new permanent user {firebase_uid} from magic link")
            return firebase_uid
        
    except Exception as e:
        logger.error(f"Error creating/updating permanent user from magic link: {e}")
        return None

def create_permanent_user_from_temp(firebase_uid: str, firebase_phone: str, guest_name: str, temp_user_id: str, token: str, email: str = '') -> Optional[str]:
    """
    Create a permanent user account from temporary user upgrade.
    
    Args:
        firebase_uid: Firebase UID for the new user
        firebase_phone: Verified phone number
        guest_name: Display name
        temp_user_id: ID of the temporary user being upgraded
        token: Magic link token
        email: Optional email address
        
    Returns:
        User ID if successful, None otherwise
    """
    try:
        db = get_firestore_client()
        if not db:
            logger.error("Failed to get Firestore client")
            return None
        
        # Get temporary user data
        temp_user = get_temporary_user(temp_user_id)
        if not temp_user:
            logger.error(f"Temporary user {temp_user_id} not found")
            return None
        
        # Check if permanent user already exists (e.g., host using magic link)
        existing_user = get_user(firebase_uid)
        if existing_user and not existing_user.get('isTemporary', False):
            current_role = existing_user.get('role')
            logger.info(f"Permanent user {firebase_uid} already exists with role {current_role}. Updating phone number and ensuring guest role.")
            
            # User already exists as permanent - update phone number and ensure they have guest role
            from google.cloud import firestore
            from concierge.utils.role_helpers import ensure_guest_role
            
            # Update basic info
            update_data = {
                'phoneNumber': firebase_phone,
                'lastLoginAt': firestore.SERVER_TIMESTAMP
            }
            
            # Ensure user has guest role in addition to their existing role(s)
            # This allows hosts to see their reservations when using magic links
            from concierge.utils.role_helpers import has_role
            
            # Check if user has guest role BEFORE any modifications
            user_had_guest_role_originally = has_role(existing_user, 'guest')
            logger.info(f"ROLE DEBUG: Raw user data role field BEFORE modification: {repr(existing_user.get('role'))}")
            logger.info(f"ROLE DEBUG: User had guest role originally: {user_had_guest_role_originally}")
            
            # Now modify the user data to add guest role
            updated_user_data = ensure_guest_role(existing_user)
            logger.info(f"ROLE DEBUG: User data role field AFTER ensure_guest_role: {repr(updated_user_data.get('role'))}")
            
            # FORCE role update if user didn't have guest role originally
            if not user_had_guest_role_originally:
                # Update roles - force the update
                if 'role' in updated_user_data:
                    update_data['role'] = updated_user_data['role']
                if 'roles' in updated_user_data:
                    update_data['roles'] = updated_user_data['roles']
                logger.info(f"FORCING guest role update for user {firebase_uid}. New role: {updated_user_data.get('role')}")
            else:
                logger.info(f"User {firebase_uid} already had guest role originally, no role update needed")
            
            update_success = update_user(firebase_uid, update_data)
            if update_success:
                logger.info(f"Updated existing permanent user {firebase_uid} phone number to {firebase_phone}")
                return firebase_uid
            else:
                logger.error(f"Failed to update existing permanent user {firebase_uid}")
                return None
        
        # Prepare permanent user data (for new users or temporary user upgrades)
        permanent_user_data = {
            'uid': firebase_uid,
            'phoneNumber': firebase_phone,
            'displayName': guest_name or temp_user.get('displayName', 'Guest'),
            'email': email or temp_user.get('email', ''),
            'role': 'guest',
            'isTemporary': False,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'lastLoginAt': firestore.SERVER_TIMESTAMP,
            'accessLevel': 'full_access',
            'accountType': 'permanent',
            # Preserve reservation associations
            'reservationIds': temp_user.get('reservationIds', []),
            'propertyIds': temp_user.get('propertyIds', []),
            # Preserve PIN from temporary user
            'pinCode': temp_user.get('pinCode'),
            'pinSetAt': firestore.SERVER_TIMESTAMP,
            # Migration metadata
            'migratedFromTempUser': temp_user_id,
            'migrationDate': firestore.SERVER_TIMESTAMP,
            'createdFromMagicLink': hash_magic_link_token(token)
        }
        
        # Create permanent user in Firestore
        db.collection('users').document(firebase_uid).set(permanent_user_data)
        
        # Mark temporary user as migrated
        disable_temp_user_access(temp_user_id)
        
        logger.info(f"Successfully created permanent user {firebase_uid} from temp user {temp_user_id}")
        return firebase_uid
        
    except Exception as e:
        logger.error(f"Error creating permanent user from temp: {e}")
        return None

def disable_temp_user_access(temp_user_id: str) -> bool:
    """
    Disable access to a temporary user account after migration.
    
    Args:
        temp_user_id: Temporary user ID to disable
        
    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False
        
    try:
        db.collection('users').document(temp_user_id).update({
            'migration_status': 'migrated',
            'access_disabled': True,
            'disabled_at': datetime.now(timezone.utc),
            'updatedAt': datetime.now(timezone.utc)
        })
        
        logger.info(f"Disabled access to temporary user {temp_user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error disabling temp user {temp_user_id}: {e}")
        return False

def has_user_activity_beyond_initial_setup(user_id: str) -> bool:
    """
    Check if a user has activity beyond initial account setup.
    
    Args:
        user_id: User ID to check
        
    Returns:
        True if user has activity, False otherwise
    """
    if not initialize_firebase():
        return False
        
    try:
        user_doc = db.collection('users').document(user_id).get()
        if not user_doc.exists:
            return False
            
        user_data = user_doc.to_dict()
        
        # Check various activity indicators
        activity_indicators = [
            user_data.get('pinChangedAt'),  # User explicitly changed PIN
            user_data.get('profileCompleted'),  # User completed profile
            user_data.get('lastActiveAt'),  # User has been active
            len(user_data.get('reservationIds', [])) > 1,  # Multiple reservations
            user_data.get('conversationHistory'),  # Has conversation history
        ]
        
        return any(activity_indicators)
        
    except Exception as e:
        logger.error(f"Error checking user activity for {user_id}: {e}")
        return False

def find_reservations_by_phone(phone_number: str) -> List[Dict]:
    """
    Find reservations by phone number.

    Args:
        phone_number: The phone number to search for

    Returns:
        List of reservation dictionaries
    """
    if not initialize_firebase():
        return []

    try:
        # Clean the phone number (remove non-digits)
        clean_number = ''.join(filter(str.isdigit, phone_number))

        # Create different versions of the phone number for matching
        phone_versions = [
            phone_number,  # Original format
            clean_number,  # Digits only
            f"+{clean_number}",  # With + prefix
            clean_number[-10:] if len(clean_number) >= 10 else clean_number  # Last 10 digits
        ]

        # Extract last 4 digits for partial matching
        last_four_digits = clean_number[-4:] if len(clean_number) >= 4 else clean_number

        logger.info(f"Looking for reservations with phone number versions: {phone_versions}")
        logger.info(f"Last 4 digits for partial matching: {last_four_digits}")

        # Debug: Count total reservations
        total_reservations = len(list(db.collection('reservations').stream()))
        logger.info(f"Total reservations in database: {total_reservations}")

        # Dictionary to store found reservations (keyed by ID to avoid duplicates)
        reservations_by_id = {}

        # Check all versions of the phone number for exact matches in primary phone fields
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

        # Get all reservations once to check additional contacts and last 4 digits
        # This is more efficient than multiple queries
        logger.info("Checking all reservations for additional contacts and last 4 digit matches")
        all_reservations_query = db.collection('reservations').stream()

        for doc in all_reservations_query:
            logger.info(f"Checking reservation {doc.id}")

            if doc.id in reservations_by_id:
                logger.info(f"  Skipping {doc.id} - already found via exact primary phone match")
                continue  # Skip if already found via exact primary phone match

            reservation_data = doc.to_dict()
            reservation_data['id'] = doc.id

            # Check additional contacts for exact phone matches
            additional_contacts = reservation_data.get('additional_contacts', [])
            logger.info(f"  Checking additional contacts: {len(additional_contacts)} contacts")
            for contact in additional_contacts:
                contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')
                if contact_phone in phone_versions:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation {doc.id} with exact phone match in additional contact: {contact_phone}")
                    break

            # Always check last 4 digits regardless of exact matches (only if we have enough digits)
            # This ensures we find ALL reservations that match either exactly OR by last 4 digits
            if doc.id not in reservations_by_id and len(clean_number) >= 4:
                logger.info(f"  Checking last 4 digits for {doc.id}")

                # Check primary guest phone number for last 4 digits
                guest_phone = reservation_data.get('guestPhoneNumber')
                if guest_phone and len(guest_phone) >= 4 and guest_phone[-4:] == last_four_digits:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation {doc.id} with matching last 4 digits in primary phone: {guest_phone}")
                    continue

                # Check guestPhoneLast4 field specifically
                guest_phone_last4 = reservation_data.get('guestPhoneLast4')
                logger.info(f"  guestPhoneLast4: {guest_phone_last4}, looking for: {last_four_digits}")
                if guest_phone_last4 == last_four_digits:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation {doc.id} with matching guestPhoneLast4: {guest_phone_last4}")
                    continue

                # Check additional contacts for last 4 digit matches
                for contact in additional_contacts:
                    contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')
                    if contact_phone and len(contact_phone) >= 4 and contact_phone[-4:] == last_four_digits:
                        reservations_by_id[doc.id] = reservation_data
                        logger.info(f"Found reservation {doc.id} with matching last 4 digits in additional contact: {contact_phone}")
                        break
            else:
                if doc.id in reservations_by_id:
                    logger.info(f"  {doc.id} already found via exact match")
                else:
                    logger.info(f"  Skipping last 4 check for {doc.id} - not enough digits")

        # Return the list of reservations
        return list(reservations_by_id.values())
    except Exception as e:
        logger.error(f"Error finding reservations by phone number {phone_number}: {e}")
        logger.error(traceback.format_exc())
        return []

# === Property Functions ===

def get_property(property_id: str) -> Optional[Dict]:
    """Get a property by ID."""
    if not initialize_firebase():
        return None

    try:
        doc_ref = db.collection('properties').document(property_id)
        doc = doc_ref.get()

        if doc.exists:
            property_data = doc.to_dict()
            property_data['id'] = doc.id  # Add id to the data
            return property_data
        else:
            logger.warning(f"Property {property_id} not found")
            return None
    except Exception as e:
        logger.error(f"Error getting property {property_id}: {e}")
        return None

def create_property(property_id: str, property_data: Dict) -> bool:
    """Create a new property with the given ID."""
    if not initialize_firebase():
        return False

    try:
        # Add timestamps
        timestamp = datetime.now(timezone.utc)
        property_data['createdAt'] = timestamp
        property_data['updatedAt'] = timestamp

        # Ensure the property ID is included in the document data
        property_data['id'] = property_id

        # Set the document with merge=True to update if it exists
        db.collection('properties').document(property_id).set(property_data, merge=True)
        logger.info(f"Property {property_id} created/updated successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating property {property_id}: {e}")
        return False

def update_property(property_id: str, property_data: Dict) -> bool:
    """Update an existing property."""
    if not initialize_firebase():
        return False

    try:
        # Add updated timestamp
        property_data['updatedAt'] = datetime.now(timezone.utc)

        # Ensure the property ID is included in the document data
        property_data['id'] = property_id

        # Update the document
        db.collection('properties').document(property_id).update(property_data)
        logger.info(f"Property {property_id} updated successfully")
        return True
    except Exception as e:
        logger.error(f"Error updating property {property_id}: {e}")
        return False

def list_properties_by_host(host_id: str) -> List[Dict]:
    """List all properties for a specific host."""
    if not initialize_firebase():
        return []

    try:
        query = db.collection('properties').where('hostId', '==', host_id)
        properties = []

        for doc in query.stream():
            property_data = doc.to_dict()
            property_data['id'] = doc.id
            properties.append(property_data)

        return properties
    except Exception as e:
        logger.error(f"Error listing properties for host {host_id}: {e}")
        return []

def delete_property(property_id: str) -> bool:
    """Delete a property by ID and all related data."""
    if not initialize_firebase():
        return False

    try:
        # First delete all knowledge items and sources for this property
        knowledge_deleted = delete_all_knowledge(property_id)
        if not knowledge_deleted:
            logger.warning(f"Failed to delete all knowledge for property {property_id}, continuing with property deletion")

        # Delete reservations for this property
        try:
            deleted_res_count = 0
            for res_doc in db.collection('reservations').where('propertyId', '==', property_id).stream():
                db.collection('reservations').document(res_doc.id).delete()
                deleted_res_count += 1
            logger.info(f"Deleted {deleted_res_count} reservations for property {property_id}")
        except Exception as e:
            logger.warning(f"Failed to delete reservations for property {property_id}: {e}")

        # Also cascade delete conversation/session data from DynamoDB Conversations table
        try:
            from concierge.utils.dynamodb_client import delete_property_conversations
            deleted_conv = delete_property_conversations(property_id)
            logger.info(f"Deleted {deleted_conv} DynamoDB conversation items for property {property_id}")
        except Exception as e:
            logger.warning(f"Failed to delete DynamoDB conversations for property {property_id}: {e}")

        # Delete the property document
        db.collection('properties').document(property_id).delete()
        logger.info(f"Property {property_id} and related data deleted successfully")
        return True
    except Exception as e:
        logger.error(f"Error deleting property {property_id}: {e}")
        return False

# === Knowledge Source Functions ===

def create_knowledge_source(source_id: str, source_data: Dict) -> bool:
    """
    Create a new knowledge source with the given ID.

    Args:
        source_id: ID for the knowledge source
        source_data: Dictionary containing knowledge source data

    Returns:
        True if creation was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Add timestamps if not provided
        timestamp = datetime.now(timezone.utc)
        if 'createdAt' not in source_data:
            source_data['createdAt'] = timestamp
        if 'updatedAt' not in source_data:
            source_data['updatedAt'] = timestamp

        # Set the document
        db.collection('knowledge_sources').document(source_id).set(source_data)
        logger.info(f"Knowledge source {source_id} created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating knowledge source: {e}")
        return False

def list_knowledge_sources(property_id: str = None) -> List[Dict]:
    """List all knowledge sources, optionally filtered by property ID."""
    if not initialize_firebase():
        return []

    try:
        if property_id:
            query = db.collection('knowledge_sources').where('propertyId', '==', property_id)
        else:
            query = db.collection('knowledge_sources')

        sources = []
        for doc in query.stream():
            source_data = doc.to_dict()
            source_data['id'] = doc.id
            sources.append(source_data)

        return sources
    except Exception as e:
        logger.error(f"Error listing knowledge sources: {e}")
        return []

def update_knowledge_source(source_id: str, source_data: Dict) -> bool:
    """
    Update an existing knowledge source.

    Args:
        source_id: ID of the knowledge source to update
        source_data: Dictionary containing updated knowledge source data

    Returns:
        True if update was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Add updated timestamp if not provided
        if 'updatedAt' not in source_data:
            source_data['updatedAt'] = datetime.now(timezone.utc)

        # Update the document
        db.collection('knowledge_sources').document(source_id).update(source_data)
        logger.info(f"Knowledge source {source_id} updated successfully")
        return True
    except Exception as e:
        logger.error(f"Error updating knowledge source {source_id}: {e}")
        return False

# === Knowledge Item Functions ===

def create_knowledge_item(item_id: str, item_data: Dict) -> bool:
    """
    Create a new knowledge item with the new schema.

    Args:
        item_id: ID for the knowledge item
        item_data: Dictionary containing knowledge item data with the following fields:
            - sourceId: ID of the source document
            - propertyId: ID of the property
            - hostId: (optional) ID of the host
            - type: Type of knowledge item (rule, instruction, amenity, etc.)
            - tags: List of tags for the item
            - content: The actual content of the knowledge item
            - status: Status of the item (pending, approved, etc.)

    Returns:
        True if creation was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Add timestamps if not provided
        timestamp = datetime.now(timezone.utc)
        if 'createdAt' not in item_data:
            item_data['createdAt'] = timestamp
        if 'updatedAt' not in item_data:
            item_data['updatedAt'] = timestamp

        # Generate embedding if not provided
        if 'embedding' not in item_data:
            content = item_data.get('content', '')
            if content:
                embedding = generate_embedding(content)
                if embedding:
                    item_data['embedding'] = vector.Vector(embedding)
                else:
                    logger.warning(f"Failed to generate embedding for item {item_id}")
            else:
                logger.warning(f"No content provided for item {item_id}")

        # Set the document
        db.collection('knowledge_items').document(item_id).set(item_data)
        logger.info(f"Knowledge item {item_id} created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating knowledge item: {e}")
        traceback.print_exc()
        return False

def update_knowledge_item(item_id: str, item_data: Dict) -> bool:
    """
    Update an existing knowledge item.

    Args:
        item_id: ID of the knowledge item to update
        item_data: Dictionary containing updated knowledge item data

    Returns:
        True if update was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Add updated timestamp
        item_data['updatedAt'] = datetime.now(timezone.utc)

        # Regenerate embedding if content changed
        if 'content' in item_data:
            content = item_data.get('content', '')
            if content:
                embedding = generate_embedding(content)
                if embedding:
                    item_data['embedding'] = vector.Vector(embedding)
                else:
                    logger.warning(f"Failed to generate embedding for item {item_id}")

        # Update the document
        db.collection('knowledge_items').document(item_id).update(item_data)
        logger.info(f"Knowledge item {item_id} updated successfully")
        return True
    except Exception as e:
        logger.error(f"Error updating knowledge item {item_id}: {e}")
        return False

def get_knowledge_item(item_id: str) -> Optional[Dict]:
    """
    Get a knowledge item by ID.

    Args:
        item_id: ID of the knowledge item to retrieve

    Returns:
        Dictionary containing knowledge item data, or None if not found
    """
    if not initialize_firebase():
        return None

    try:
        doc_ref = db.collection('knowledge_items').document(item_id)
        doc = doc_ref.get()

        if doc.exists:
            item_data = doc.to_dict()
            item_data['id'] = doc.id  # Add id to the data
            return item_data
        else:
            logger.warning(f"Knowledge item {item_id} not found")
            return None
    except Exception as e:
        logger.error(f"Error getting knowledge item {item_id}: {e}")
        return None

def list_knowledge_items_by_property(property_id: str, status: str = None) -> List[Dict]:
    """
    List all knowledge items for a specific property, optionally filtered by status.

    Args:
        property_id: ID of the property
        status: (optional) Status to filter by (e.g., 'approved')

    Returns:
        List of knowledge items
    """
    if not initialize_firebase():
        return []

    try:
        # Start with base query
        query = db.collection('knowledge_items').where('propertyId', '==', property_id)

        # Add status filter if provided
        if status:
            query = query.where('status', '==', status)

        items = []
        for doc in query.stream():
            item_data = doc.to_dict()
            item_data['id'] = doc.id
            items.append(item_data)

        return items
    except Exception as e:
        logger.error(f"Error listing knowledge items for property {property_id}: {e}")
        return []

def check_duplicate_content(property_id: str, content: str) -> Optional[Dict]:
    """
    Check if a knowledge item with identical content already exists for this property.

    Args:
        property_id: ID of the property
        content: Content to check for duplicates

    Returns:
        The duplicate item if found, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        # Normalize content for comparison (trim whitespace, lowercase)
        normalized_content = content.strip().lower()

        # Get all knowledge items for this property
        items = list_knowledge_items_by_property(property_id)

        # Check each item for matching content
        for item in items:
            item_content = item.get('content', '').strip().lower()
            if item_content == normalized_content:
                logger.info(f"Found duplicate content in item {item.get('id')} for property {property_id}")
                return item

        return None
    except Exception as e:
        logger.error(f"Error checking for duplicate content for property {property_id}: {e}")
        return None

def list_knowledge_items_by_source(source_id: str) -> List[Dict]:
    """
    List all knowledge items for a specific source.

    Args:
        source_id: ID of the source

    Returns:
        List of knowledge items
    """
    if not initialize_firebase():
        return []

    try:
        query = db.collection('knowledge_items').where('sourceId', '==', source_id)

        items = []
        for doc in query.stream():
            item_data = doc.to_dict()
            item_data['id'] = doc.id
            items.append(item_data)

        return items
    except Exception as e:
        logger.error(f"Error listing knowledge items for source {source_id}: {e}")
        return []

def update_knowledge_item_status(item_id: str, status: str) -> bool:
    """
    Update the status of a knowledge item.

    Args:
        item_id: ID of the knowledge item
        status: New status (e.g., 'approved', 'rejected')

    Returns:
        True if update was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Update only the status field
        db.collection('knowledge_items').document(item_id).update({
            'status': status,
            'updatedAt': datetime.now(timezone.utc)
        })
        logger.info(f"Knowledge item {item_id} status updated to {status}")
        return True
    except Exception as e:
        logger.error(f"Error updating knowledge item {item_id} status: {e}")
        return False

def delete_knowledge_item(item_id: str) -> bool:
    """
    Delete a knowledge item.

    Args:
        item_id: ID of the knowledge item to delete

    Returns:
        True if deletion was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        db.collection('knowledge_items').document(item_id).delete()
        logger.info(f"Knowledge item {item_id} deleted successfully")
        return True
    except Exception as e:
        logger.error(f"Error deleting knowledge item {item_id}: {e}")
        return False

def delete_all_knowledge(property_id: str) -> bool:
    """
    Delete all knowledge items for a property from Firestore.

    Args:
        property_id: ID of the property

    Returns:
        True if deletion was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Get all knowledge items for this property
        items = list_knowledge_items_by_property(property_id)

        # Delete each item
        deleted_count = 0
        for item in items:
            item_id = item.get('id')
            if item_id:
                db.collection('knowledge_items').document(item_id).delete()
                deleted_count += 1

        # Get all knowledge sources for this property
        sources = list_knowledge_sources(property_id)

        # Delete each source
        source_count = 0
        for source in sources:
            source_id = source.get('id')
            if source_id:
                db.collection('knowledge_sources').document(source_id).delete()
                source_count += 1

        logger.info(f"Deleted {deleted_count} knowledge items and {source_count} sources for property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting all knowledge for property {property_id}: {e}")
        traceback.print_exc()
        return False

def find_similar_knowledge_items(query_text: str, property_id: str, limit: int = 5) -> List[Dict]:
    """
    Find knowledge items similar to the query text using vector search.

    Args:
        query_text: The query text to search for
        property_id: ID of the property to search within
        limit: Maximum number of results to return

    Returns:
        List of knowledge items sorted by relevance
    """
    if not initialize_firebase():
        return []

    try:
        # Generate embedding for the query text
        query_embedding = generate_embedding(query_text)
        if not query_embedding:
            logger.error("Failed to generate embedding for query text")
            return []

        # Import DistanceMeasure enum
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

        # Create vector query using filter keyword argument
        query = (db.collection('knowledge_items')
                .where('propertyId', '==', property_id)
                .where('status', '==', 'approved')
                .find_nearest(
                    vector_field='embedding',
                    query_vector=vector.Vector(query_embedding),
                    distance_measure=DistanceMeasure.COSINE,
                    limit=limit,
                    distance_result_field='similarity'
                ))

        # Execute query and process results
        results = []
        for doc in query.get():
            item_data = doc.to_dict()
            item_data['id'] = doc.id

            # Convert similarity score to a more intuitive format (0-1 where 1 is most similar)
            if 'similarity' in item_data:
                # COSINE distance is between 0-2, where 0 is most similar
                # Convert to a 0-1 scale where 1 is most similar
                item_data['similarity'] = 1 - (item_data['similarity'] / 2)

            results.append(item_data)

        return results
    except Exception as e:
        logger.error(f"Error finding similar knowledge items: {e}")
        traceback.print_exc()
        return []

# === Reservation Functions ===

def create_reservation(reservation_data: Dict) -> Optional[str]:
    """
    Create a new reservation.

    Args:
        reservation_data: Dictionary containing reservation data

    Returns:
        The ID of the created reservation, or None if creation failed
    """
    if not initialize_firebase():
        return None

    try:
        # Import date utilities for consistent formatting
        from concierge.utils.date_utils import ensure_date_only_format

        # Generate a unique ID if not provided
        reservation_id = reservation_data.get('id', str(uuid.uuid4()))

        # Ensure dates are in consistent date-only format
        start_date = ensure_date_only_format(reservation_data.get('startDate'))
        end_date = ensure_date_only_format(reservation_data.get('endDate'))

        # Create normalized reservation data
        normalized_data = reservation_data.copy()
        normalized_data['startDate'] = start_date
        normalized_data['endDate'] = end_date

        # Add timestamps
        timestamp = datetime.now(timezone.utc)
        normalized_data['createdAt'] = timestamp
        normalized_data['updatedAt'] = timestamp

        # Set the document
        db.collection('reservations').document(reservation_id).set(normalized_data)
        logger.info(f"Reservation {reservation_id} created successfully")
        return reservation_id
    except Exception as e:
        logger.error(f"Error creating reservation: {e}")
        return None

def get_reservation(reservation_id: str) -> Optional[Dict]:
    """
    Get a reservation by ID.

    Args:
        reservation_id: ID of the reservation to retrieve

    Returns:
        Dictionary containing reservation data, or None if not found
    """
    if not initialize_firebase():
        return None

    try:
        doc_ref = db.collection('reservations').document(reservation_id)
        doc = doc_ref.get()

        if doc.exists:
            reservation_data = doc.to_dict()
            reservation_data['id'] = doc.id
            return reservation_data
        else:
            logger.warning(f"Reservation {reservation_id} not found")
            return None
    except Exception as e:
        logger.error(f"Error getting reservation {reservation_id}: {e}")
        return None

def list_property_reservations(property_id: str) -> List[Dict]:
    """
    List all reservations for a specific property.

    Args:
        property_id: ID of the property

    Returns:
        List of reservations
    """
    if not initialize_firebase():
        return []

    try:
        query = db.collection('reservations').where('propertyId', '==', property_id)

        reservations = []
        for doc in query.stream():
            reservation_data = doc.to_dict()
            reservation_data['id'] = doc.id
            reservations.append(reservation_data)

        return reservations
    except Exception as e:
        logger.error(f"Error listing reservations for property {property_id}: {e}")
        return []

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

        # Get all reservations once to check additional contacts and last 4 digits
        # This is more efficient than multiple queries
        logger.info("Checking all reservations for additional contacts and last 4 digit matches")
        all_reservations_query = db.collection('reservations').stream()

        # Extract last 4 digits for partial matching
        clean_number = ''.join(filter(str.isdigit, normalized_phone))
        last_four_digits = clean_number[-4:] if len(clean_number) >= 4 else clean_number
        logger.info(f"Last 4 digits for partial matching: {last_four_digits}")

        for doc in all_reservations_query:
            if doc.id in reservations_by_id:
                continue  # Skip if already found via exact primary phone match

            reservation_data = doc.to_dict()
            reservation_data['id'] = doc.id

            # Check additional contacts for exact phone matches
            additional_contacts = reservation_data.get('additional_contacts', [])
            for contact in additional_contacts:
                contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')
                if contact_phone in phone_versions:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation {doc.id} with exact phone match in additional contact: {contact_phone}")
                    break

            # Always check last 4 digits regardless of exact matches (only if we have enough digits)
            # This ensures we find ALL reservations that match either exactly OR by last 4 digits
            if doc.id not in reservations_by_id and len(clean_number) >= 4:
                # Check primary guest phone number for last 4 digits
                guest_phone = reservation_data.get('guestPhoneNumber')
                if guest_phone and len(guest_phone) >= 4 and guest_phone[-4:] == last_four_digits:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation {doc.id} with matching last 4 digits in primary phone: {guest_phone}")
                    continue

                # Check guestPhoneLast4 field specifically
                guest_phone_last4 = reservation_data.get('guestPhoneLast4')
                if guest_phone_last4 == last_four_digits:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation {doc.id} with matching guestPhoneLast4: {guest_phone_last4}")
                    continue

                # Check additional contacts for last 4 digit matches
                for contact in additional_contacts:
                    contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')
                    if contact_phone and len(contact_phone) >= 4 and contact_phone[-4:] == last_four_digits:
                        reservations_by_id[doc.id] = reservation_data
                        logger.info(f"Found reservation {doc.id} with matching last 4 digits in additional contact: {contact_phone}")
                        break

        # Convert the dictionary values to a list
        reservations = list(reservations_by_id.values())
        logger.info(f"Found {len(reservations)} unique reservations for phone number {phone_number}")
        return reservations
    except Exception as e:
        logger.error(f"Error listing reservations for phone number {phone_number}: {e}")
        traceback.print_exc()  # Add traceback for better debugging
        return []

def find_reservation_by_phone(phone_number: str, check_last_four: bool = True) -> Optional[Dict]:
    """
    Find a reservation by guest phone number.

    Args:
        phone_number: Guest phone number to search for
        check_last_four: Whether to also check for matches on the last 4 digits

    Returns:
        Dictionary containing reservation data, or None if not found
    """
    if not initialize_firebase():
        return None

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

        # Check additional contacts for exact phone matches during exact matching phase
        if not reservations_by_id:
            for phone_version in phone_versions:
                # Get all reservations and check additional contacts manually
                all_reservations_query = db.collection('reservations').stream()
                for doc in all_reservations_query:
                    if doc.id in reservations_by_id:
                        continue  # Skip if already found

                    reservation_data = doc.to_dict()
                    reservation_data['id'] = doc.id

                    # Check additional contacts for exact phone match
                    additional_contacts = reservation_data.get('additional_contacts', [])
                    for contact in additional_contacts:
                        contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')
                        if contact_phone == phone_version:
                            reservations_by_id[doc.id] = reservation_data
                            logger.info(f"Found reservation {doc.id} with exact phone match in additional contact: {contact_phone}")
                            break

        # If no reservations found, try with last 4 digits
        if not reservations_by_id and len(normalized_phone) >= 4:
            last_four_digits = normalized_phone[-4:]
            logger.info(f"No exact phone matches found. Trying with last 4 digits: {last_four_digits}")

            # Get all reservations
            all_reservations_query = db.collection('reservations').stream()

            # Check each reservation for matching last 4 digits
            for doc in all_reservations_query:
                reservation_data = doc.to_dict()
                reservation_data['id'] = doc.id

                # Check primary guest phone number
                guest_phone = reservation_data.get('guestPhoneNumber')
                if guest_phone and len(guest_phone) >= 4 and guest_phone[-4:] == last_four_digits:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation with matching last 4 digits in primary phone: {guest_phone}")
                    continue

                # Check guestPhoneLast4 field specifically
                guest_phone_last4 = reservation_data.get('guestPhoneLast4')
                if guest_phone_last4 == last_four_digits:
                    reservations_by_id[doc.id] = reservation_data
                    logger.info(f"Found reservation with matching guestPhoneLast4: {guest_phone_last4}")
                    continue

                # Check additional contacts
                additional_contacts = reservation_data.get('additional_contacts', [])
                for contact in additional_contacts:
                    contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')
                    if contact_phone and len(contact_phone) >= 4 and contact_phone[-4:] == last_four_digits:
                        reservations_by_id[doc.id] = reservation_data
                        logger.info(f"Found reservation with matching last 4 digits in additional contact: {contact_phone}")
                        break

        # Convert the dictionary values to a list
        reservations = list(reservations_by_id.values())
        logger.info(f"Found {len(reservations)} unique reservations for phone number {phone_number}")
        return reservations[0] if reservations else None
    except Exception as e:
        logger.error(f"Error finding reservation by phone number {phone_number}: {e}")
        return None

def update_reservation(reservation_id: str, update_data: Dict) -> bool:
    """
    Update an existing reservation.

    Args:
        reservation_id: ID of the reservation to update
        update_data: Dictionary containing updated reservation data

    Returns:
        True if update was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Import normalize_reservation_dates here to avoid circular imports
        from concierge.utils.date_utils import normalize_reservation_dates

        # Normalize dates in update data to ensure consistent date-only format
        normalized_update_data = normalize_reservation_dates(update_data)

        # Add updated timestamp if not provided
        if 'updatedAt' not in normalized_update_data:
            normalized_update_data['updatedAt'] = datetime.now(timezone.utc)

        # Update the document
        db.collection('reservations').document(reservation_id).update(normalized_update_data)
        logger.info(f"Reservation {reservation_id} updated successfully")
        return True
    except Exception as e:
        logger.error(f"Error updating reservation {reservation_id}: {e}")
        return False


# === Magic Link Functions ===

def generate_magic_link_token() -> str:
    """
    Generate a cryptographically secure token for magic links.

    DEPRECATED: Use generate_property_magic_link_token() for new property-based magic links.

    Returns:
        A secure random token string
    """
    return secrets.token_urlsafe(32)

def generate_property_magic_link_token(property_id: str) -> str:
    """
    Generate a compressed magic link token for a property.
    The token length matches the property ID length for consistency.

    Args:
        property_id: The property ID to base the token on

    Returns:
        A compressed secure token string
    """
    # Generate cryptographically secure random bytes
    # Use enough bytes to ensure security even after compression
    random_bytes = secrets.token_bytes(32)

    # Create a hash that includes both random data and property ID for uniqueness
    combined_data = random_bytes + property_id.encode('utf-8')
    token_hash = hashlib.sha256(combined_data).digest()

    # Encode to base64 and remove padding/special characters
    token_b64 = base64.urlsafe_b64encode(token_hash).decode('ascii')
    token_clean = token_b64.replace('=', '').replace('-', '').replace('_', '')

    # Truncate to match property ID length (typically 36 characters for UUIDs)
    target_length = len(property_id)
    compressed_token = token_clean[:target_length]

    # Ensure we have enough characters (fallback to original method if needed)
    if len(compressed_token) < target_length:
        # Fallback: use original method and truncate
        fallback_token = secrets.token_urlsafe(32).replace('-', '').replace('_', '')
        compressed_token = fallback_token[:target_length]

    return compressed_token

def decompress_magic_link_token(compressed_token: str) -> str:
    """
    For property-based magic links, the token is already in its final form.
    This function exists for API compatibility but returns the token as-is.

    Args:
        compressed_token: The compressed token

    Returns:
        The same token (no decompression needed for property-based tokens)
    """
    return compressed_token

def hash_magic_link_token(token: str) -> str:
    """
    Hash a magic link token for secure storage.

    Args:
        token: The raw token to hash

    Returns:
        SHA-256 hash of the token
    """
    return hashlib.sha256(token.encode()).hexdigest()

def create_property_magic_link(property_id: str) -> Optional[str]:
    """
    Create a magic link token for a property and store it in the property document.

    Args:
        property_id: ID of the property to create magic link for

    Returns:
        The raw token if successful, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        # Generate compressed token for the property
        raw_token = generate_property_magic_link_token(property_id)

        # Update the property document with the magic link token
        update_data = {
            'magicLinkToken': raw_token,
            'magicLinkCreatedAt': datetime.now(timezone.utc),
            'updatedAt': datetime.now(timezone.utc)
        }

        success = update_property(property_id, update_data)
        if success:
            logger.info(f"Property magic link created for property {property_id}")
            return raw_token
        else:
            logger.error(f"Failed to update property {property_id} with magic link")
            return None

    except Exception as e:
        logger.error(f"Error creating property magic link for {property_id}: {e}")
        return None

def get_property_magic_link_token(property_id: str) -> Optional[str]:
    """
    Get the magic link token for a property.

    Args:
        property_id: ID of the property

    Returns:
        The magic link token if found, None otherwise
    """
    try:
        property_data = get_property(property_id)
        if property_data:
            return property_data.get('magicLinkToken')
        return None
    except Exception as e:
        logger.error(f"Error getting property magic link token for {property_id}: {e}")
        return None

def create_magic_link(reservation_id: str, expires_at: datetime, base_url: str = None) -> Optional[str]:
    """
    Create a new magic link for a reservation.

    Args:
        reservation_id: ID of the reservation to link to
        expires_at: When the magic link should expire
        base_url: Optional base URL to use (e.g., from current request)

    Returns:
        The raw token if successful, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        # Generate secure token
        raw_token = generate_magic_link_token()
        token_hash = hash_magic_link_token(raw_token)

        # Generate the full URL with optional base_url
        magic_link_url = generate_magic_link_url(raw_token, base_url)

        # Create magic link document
        magic_link_data = {
            'token_hash': token_hash,
            'reservation_id': reservation_id,
            'url': magic_link_url,  # Store the full URL
            'created_at': datetime.now(timezone.utc),
            'expires_at': expires_at,
            'is_active': True,
            'status': 'pending_verification',
            'access_level': 'none',
            'verified_last_4_digits': None,
            'guest_name_provided': None,
            'verification_attempts': 0
        }

        # Use token hash as document ID for easy lookup
        db.collection('magic_links').document(token_hash).set(magic_link_data)
        logger.info(f"Magic link created for reservation {reservation_id}")
        return raw_token

    except Exception as e:
        logger.error(f"Error creating magic link for reservation {reservation_id}: {e}")
        return None

def get_magic_link_by_token(token: str) -> Optional[Dict]:
    """
    Get magic link data by raw token.

    DEPRECATED: Use get_property_by_magic_link_token() for new property-based magic links.

    Args:
        token: The raw token to look up

    Returns:
        Magic link data if found and valid, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        token_hash = hash_magic_link_token(token)
        doc_ref = db.collection('magic_links').document(token_hash)
        doc = doc_ref.get()

        if doc.exists:
            magic_link_data = doc.to_dict()
            magic_link_data['id'] = doc.id

            # Check if link is still valid
            now = datetime.now(timezone.utc)
            expires_at = magic_link_data.get('expires_at')

            if expires_at and expires_at > now and magic_link_data.get('is_active', False):
                return magic_link_data
            else:
                logger.warning(f"Magic link expired or inactive: {token_hash[:8]}...")
                return None
        else:
            logger.warning(f"Magic link not found: {token_hash[:8]}...")
            return None

    except Exception as e:
        logger.error(f"Error getting magic link by token: {e}")
        return None

def get_property_by_magic_link_token(token: str) -> Optional[Dict]:
    """
    Get property data by magic link token.

    Args:
        token: The raw magic link token

    Returns:
        Property data if found and active, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        # Query properties collection for matching magic link token
        query = db.collection('properties').where('magicLinkToken', '==', token)
        results = list(query.stream())

        if results:
            property_doc = results[0]  # Should only be one match
            property_data = property_doc.to_dict()
            property_data['id'] = property_doc.id

            # Check if property is active (magic links only work for active properties)
            if property_data.get('status') == 'active':
                return property_data
            else:
                logger.warning(f"Magic link accessed for inactive property: {property_data.get('id')}")
                return None
        else:
            logger.warning(f"No property found for magic link token: {token[:8]}...")
            return None

    except Exception as e:
        logger.error(f"Error getting property by magic link token: {e}")
        return None

def find_property_reservations_by_phone(property_id: str, phone_last_4: str) -> List[Dict]:
    """
    Find active/upcoming reservations for a property matching the last 4 digits of phone number.

    Args:
        property_id: ID of the property to search reservations for
        phone_last_4: Last 4 digits of phone number

    Returns:
        List of matching reservations (may be empty or contain multiple matches)
    """
    if not initialize_firebase():
        return []

    try:
        # Get current date for filtering active/upcoming reservations
        today = datetime.now(timezone.utc).date()

        # Query reservations for this property - check both possible field names
        # Try propertyId first (camelCase)
        query = db.collection('reservations').where('propertyId', '==', property_id)
        reservations_found = False

        for doc in query.stream():
            reservations_found = True
            break

        # If no reservations found with propertyId, try property_id (snake_case)
        if not reservations_found:
            query = db.collection('reservations').where('property_id', '==', property_id)
        reservations = []

        for doc in query.stream():
            reservation_data = doc.to_dict()
            reservation_data['id'] = doc.id

            # Skip cancelled reservations
            if reservation_data.get('status') == 'cancelled':
                continue

            # Check if reservation is active/upcoming (not expired)
            # Check multiple possible date field names
            checkout_date_str = None
            date_fields = ['endDate', 'EndDate', 'checkOutDate', 'CheckOutDate', 'checkout_date', 'end_date']

            for field in date_fields:
                if reservation_data.get(field):
                    checkout_date_str = reservation_data.get(field)
                    break

            if checkout_date_str:
                try:
                    # Handle different date formats
                    if isinstance(checkout_date_str, str):
                        # Try parsing ISO format first
                        try:
                            checkout_date = datetime.fromisoformat(checkout_date_str.replace('Z', '+00:00')).date()
                        except ValueError:
                            # Try parsing date-only format
                            checkout_date = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
                    else:
                        # Assume it's already a date object
                        checkout_date = checkout_date_str

                    # Skip expired reservations
                    if checkout_date < today:
                        logger.info(f"Skipping expired reservation {doc.id} (checkout: {checkout_date})")
                        continue

                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse checkout date for reservation {doc.id}: {checkout_date_str}")
                    continue
            else:
                # If no checkout date found, include the reservation (better to be inclusive)
                logger.info(f"No checkout date found for reservation {doc.id}, including in results")

            # Check if phone number matches - check all possible phone fields
            phone_match = False

            # Check guestPhoneLast4 field first (most direct match)
            guest_phone_last4 = reservation_data.get('guestPhoneLast4')
            if guest_phone_last4 == phone_last_4:
                phone_match = True
                logger.info(f"Found reservation {doc.id} with matching guestPhoneLast4: {guest_phone_last4}")

            # Check full phone number fields if no direct match
            if not phone_match:
                phone_fields = [
                    'guestPhoneNumber',
                    'GuestPhoneNumber',
                    'guest_phone_number',
                    'guest_phone'
                ]

                for field in phone_fields:
                    guest_phone = reservation_data.get(field, '')
                    if guest_phone:
                        # Extract digits only
                        phone_digits = ''.join(filter(str.isdigit, guest_phone))
                        if len(phone_digits) >= 4 and phone_digits[-4:] == phone_last_4:
                            phone_match = True
                            logger.info(f"Found reservation {doc.id} with matching {field}: {guest_phone} (last 4: {phone_digits[-4:]})")
                            break

            if phone_match:
                reservations.append(reservation_data)

        logger.info(f"Found {len(reservations)} matching reservations for property {property_id} with phone ending {phone_last_4}")
        return reservations

    except Exception as e:
        logger.error(f"Error finding property reservations by phone: {e}")
        return []

def update_magic_link(token_hash: str, update_data: Dict) -> bool:
    """
    Update magic link data.

    Args:
        token_hash: The hashed token to update
        update_data: Data to update

    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Add updated timestamp
        update_data['updated_at'] = datetime.now(timezone.utc)

        # Update the document
        db.collection('magic_links').document(token_hash).update(update_data)
        logger.info(f"Magic link {token_hash[:8]}... updated successfully")
        return True

    except Exception as e:
        logger.error(f"Error updating magic link {token_hash[:8]}...: {e}")
        return False

def verify_magic_link_phone(token: str, last_4_digits: str) -> bool:
    """
    Verify the last 4 digits of phone number for a magic link.

    Args:
        token: The raw magic link token
        last_4_digits: Last 4 digits of phone number to verify

    Returns:
        True if verification successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Get magic link data
        magic_link_data = get_magic_link_by_token(token)
        if not magic_link_data:
            return False

        # Get reservation data to check phone number
        reservation_id = magic_link_data.get('reservation_id')
        reservation = get_reservation(reservation_id)
        if not reservation:
            logger.error(f"Reservation {reservation_id} not found for magic link verification")
            return False

        # Get phone number from reservation
        phone_number = reservation.get('guestPhoneNumber') or reservation.get('GuestPhoneNumber')
        guest_phone_last4 = reservation.get('guestPhoneLast4')

        # Use full phone number if available, otherwise use last 4 digits field
        if phone_number and len(phone_number) >= 4:
            reservation_last_4 = phone_number[-4:]
        elif guest_phone_last4:
            reservation_last_4 = guest_phone_last4
        else:
            logger.error(f"No phone number information found in reservation {reservation_id}")
            return False

        # Check if last 4 digits match
        if reservation_last_4 == last_4_digits:
            # Update magic link with successful verification
            token_hash = hash_magic_link_token(token)
            update_data = {
                'status': 'partial_verified',
                'access_level': 'limited_info_access',
                'verified_last_4_digits': last_4_digits,
                'verification_attempts': magic_link_data.get('verification_attempts', 0) + 1
            }
            return update_magic_link(token_hash, update_data)
        else:
            # Increment verification attempts
            token_hash = hash_magic_link_token(token)
            attempts = magic_link_data.get('verification_attempts', 0) + 1
            update_data = {
                'verification_attempts': attempts
            }
            update_magic_link(token_hash, update_data)
            logger.warning(f"Phone verification failed for magic link {token_hash[:8]}... (attempt {attempts})")
            return False

    except Exception as e:
        logger.error(f"Error verifying magic link phone: {e}")
        return False

def generate_magic_link_url(raw_token: str, base_url: str = None) -> str:
    """
    Generate the full magic link URL with proper host and port.

    Args:
        raw_token: The raw token to include in the URL
        base_url: Optional base URL to use (e.g., from current request)

    Returns:
        Full magic link URL
    """
    import os
    
    # If base_url is provided, use it (preferred method)
    if base_url:
        # Remove trailing slash if present
        base_url = base_url.rstrip('/')
        return f"{base_url}/magic/{raw_token}"

    # Fallback to environment-based URL generation
    # Load environment variables if not already loaded
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv not available, continue with existing env vars

    # Check environment configuration
    flask_env = os.environ.get('FLASK_ENV', '').lower()
    debug_mode = os.environ.get('DEBUG_MODE', '').lower() in ('true', '1', 'yes')
    deployment_env = os.environ.get('DEPLOYMENT_ENV', '').lower()
    
    # Priority order for environment detection:
    # 1. Explicit DEPLOYMENT_ENV setting
    # 2. FLASK_ENV and DEBUG_MODE combination
    # 3. Default to production
    
    if deployment_env == 'local' or deployment_env == 'development':
        # Local development environment
        return f"http://localhost:5001/magic/{raw_token}"
    elif deployment_env == 'staging':
        # Staging environment (dev.guestrix.ai)
        return f"https://dev.guestrix.ai/magic/{raw_token}"
    elif deployment_env == 'production':
        # Production environment (app.guestrix.ai)
        return f"https://app.guestrix.ai/magic/{raw_token}"
    else:
        # Fallback to legacy environment detection
        if flask_env == 'development' or debug_mode:
            # Use localhost for development (port 5001 since 5000 is often used by AirPlay)
            return f"http://localhost:5001/magic/{raw_token}"
        else:
            # Default to production domain
            return f"https://app.guestrix.ai/magic/{raw_token}"

def set_magic_link_guest_name(token: str, guest_name: str) -> bool:
    """
    Set the guest name for a magic link.

    Args:
        token: The raw magic link token
        guest_name: Name provided by the guest

    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        token_hash = hash_magic_link_token(token)
        update_data = {
            'guest_name_provided': guest_name.strip()
        }
        return update_magic_link(token_hash, update_data)

    except Exception as e:
        logger.error(f"Error setting guest name for magic link: {e}")
        return False

def revoke_magic_link(token: str) -> bool:
    """
    Revoke a magic link (host-initiated).

    Args:
        token: The raw magic link token to revoke

    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        token_hash = hash_magic_link_token(token)
        update_data = {
            'is_active': False,
            'status': 'revoked'
        }
        return update_magic_link(token_hash, update_data)

    except Exception as e:
        logger.error(f"Error revoking magic link: {e}")
        return False

def list_magic_links_by_reservation(reservation_id: str) -> List[Dict]:
    """
    List all magic links for a specific reservation.

    Args:
        reservation_id: ID of the reservation

    Returns:
        List of magic link data
    """
    if not initialize_firebase():
        return []

    try:
        query = db.collection('magic_links').where('reservation_id', '==', reservation_id)
        magic_links = []

        for doc in query.stream():
            magic_link_data = doc.to_dict()
            magic_link_data['id'] = doc.id
            magic_links.append(magic_link_data)

        logger.info(f"Found {len(magic_links)} magic links for reservation {reservation_id}")
        return magic_links

    except Exception as e:
        logger.error(f"Error listing magic links for reservation {reservation_id}: {e}")
        return []

def expire_old_magic_links() -> int:
    """
    Expire old magic links (for scheduled cleanup).

    Returns:
        Number of links expired
    """
    if not initialize_firebase():
        return 0

    try:
        now = datetime.now(timezone.utc)
        query = db.collection('magic_links').where('expires_at', '<', now).where('is_active', '==', True)

        expired_count = 0
        for doc in query.stream():
            doc.reference.update({
                'is_active': False,
                'status': 'expired',
                'updated_at': now
            })
            expired_count += 1

        logger.info(f"Expired {expired_count} old magic links")
        return expired_count

    except Exception as e:
        logger.error(f"Error expiring old magic links: {e}")
        return 0

def cleanup_expired_temporary_users() -> int:
    """
    Clean up expired temporary users (for scheduled cleanup).
    Removes users whose expiresAt timestamp has passed.

    Returns:
        Number of temporary users cleaned up
    """
    if not initialize_firebase():
        return 0

    try:
        now = datetime.now(timezone.utc)
        
        # Query for expired temporary users
        query = db.collection('users').where('isTemporary', '==', True).where('expiresAt', '<', now)
        
        cleanup_count = 0
        temp_users_to_cleanup = []
        
        # Collect expired temporary users
        for doc in query.stream():
            temp_user_data = doc.to_dict()
            temp_users_to_cleanup.append({
                'id': doc.id,
                'data': temp_user_data
            })
        
        # Delete expired temporary users
        for temp_user in temp_users_to_cleanup:
            user_id = temp_user['id']
            user_data = temp_user['data']
            
            try:
                # Log cleanup for audit trail
                logger.info(f"Cleaning up expired temporary user: {user_id} (expired: {user_data.get('expiresAt')})")
                
                # Delete the user document
                db.collection('users').document(user_id).delete()
                cleanup_count += 1
                
            except Exception as user_error:
                logger.error(f"Error cleaning up temporary user {user_id}: {user_error}")
                continue
        
        logger.info(f"Cleaned up {cleanup_count} expired temporary users")
        return cleanup_count

    except Exception as e:
        logger.error(f"Error during temporary user cleanup: {e}")
        return 0

def perform_daily_cleanup() -> Dict[str, int]:
    """
    Perform daily cleanup tasks for the system.
    
    Returns:
        Dictionary with cleanup counts
    """
    cleanup_results = {
        'expired_magic_links': 0,
        'expired_temp_users': 0,
        'total_cleaned': 0
    }
    
    try:
        logger.info("Starting daily cleanup tasks...")
        
        # Clean up expired magic links
        expired_links = expire_old_magic_links()
        cleanup_results['expired_magic_links'] = expired_links
        
        # Clean up expired temporary users
        expired_users = cleanup_expired_temporary_users()
        cleanup_results['expired_temp_users'] = expired_users
        
        # Calculate total
        cleanup_results['total_cleaned'] = expired_links + expired_users
        
        logger.info(f"Daily cleanup completed: {cleanup_results}")
        return cleanup_results
        
    except Exception as e:
        logger.error(f"Error during daily cleanup: {e}")
        return cleanup_results

def upgrade_magic_link_to_full_account(token: str, user_id: str) -> bool:
    """
    Mark a magic link as upgraded to full account.

    Args:
        token: The raw magic link token
        user_id: The Firebase user ID of the full account

    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        token_hash = hash_magic_link_token(token)
        update_data = {
            'status': 'upgraded_to_full_account',
            'access_level': 'full_access',
            'upgraded_user_id': user_id
        }
        return update_magic_link(token_hash, update_data)

    except Exception as e:
        logger.error(f"Error upgrading magic link to full account: {e}")
        return False

def delete_reservation(reservation_id: str) -> bool:
    """
    Delete a reservation.

    Args:
        reservation_id: ID of the reservation to delete

    Returns:
        True if deletion was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Delete the document
        db.collection('reservations').document(reservation_id).delete()
        logger.info(f"Reservation {reservation_id} deleted successfully")
        return True
    except Exception as e:
        logger.error(f"Error deleting reservation {reservation_id}: {e}")
        return False

def update_reservation_phone(reservation_id: str, phone_number: str) -> bool:
    """
    Update the phone number for a reservation.

    Args:
        reservation_id: ID of the reservation
        phone_number: New phone number

    Returns:
        True if update was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Update the phone number
        db.collection('reservations').document(reservation_id).update({
            'guestPhoneNumber': phone_number,
            'updatedAt': datetime.now(timezone.utc)
        })
        logger.info(f"Reservation {reservation_id} phone number updated to {phone_number}")
        return True
    except Exception as e:
        logger.error(f"Error updating reservation {reservation_id} phone number: {e}")
        return False

def update_reservation_contacts(reservation_id: str, contacts: List[Dict]) -> bool:
    """
    Update the additional contacts for a reservation.

    Args:
        reservation_id: ID of the reservation
        contacts: List of contact dictionaries, each with 'name' and 'phone' keys

    Returns:
        True if update was successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        # Update the additional contacts
        db.collection('reservations').document(reservation_id).update({
            'additional_contacts': contacts,
            'updatedAt': datetime.now(timezone.utc)
        })
        logger.info(f"Reservation {reservation_id} contacts updated with {len(contacts)} contacts")
        return True
    except Exception as e:
        logger.error(f"Error updating reservation {reservation_id} contacts: {e}")
        return False

# === Conversation History Functions ===

def store_conversation(conversation_data: Dict) -> Optional[str]:
    """
    Store a conversation entry.

    Args:
        conversation_data: Dictionary containing conversation data

    Returns:
        The ID of the created conversation entry, or None if creation failed
    """
    if not initialize_firebase():
        return None

    try:
        # Generate a unique ID if not provided
        conversation_id = conversation_data.get('id', str(uuid.uuid4()))

        # Add timestamp if not provided
        if 'timestamp' not in conversation_data:
            conversation_data['timestamp'] = datetime.now(timezone.utc)

        # Set the document
        db.collection('conversations').document(conversation_id).set(conversation_data)
        logger.info(f"Conversation {conversation_id} stored successfully")
        return conversation_id
    except Exception as e:
        logger.error(f"Error storing conversation: {e}")
        return None


# === Temporary User Functions for Magic Links ===

def create_temporary_user(magic_link_data: Dict, reservation: Dict, guest_name: str = None) -> Optional[str]:
    """
    Create a temporary Firebase user for magic link access.

    Args:
        magic_link_data: Magic link information
        reservation: Reservation data
        guest_name: Optional guest name

    Returns:
        Temporary user ID if successful, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        # Generate temporary user ID
        token_hash = magic_link_data.get('token_hash', magic_link_data.get('id', ''))
        temp_user_id = f"temp_magic_{token_hash[:12]}"

        # Get phone last 4 digits
        phone_last_4 = magic_link_data.get('verified_last_4_digits')
        if not phone_last_4:
            # Fallback to reservation phone data
            phone_number = reservation.get('guestPhoneNumber') or reservation.get('GuestPhoneNumber')
            guest_phone_last4 = reservation.get('guestPhoneLast4')
            if phone_number and len(phone_number) >= 4:
                phone_last_4 = phone_number[-4:]
            elif guest_phone_last4:
                phone_last_4 = guest_phone_last4
            else:
                logger.error("No phone last 4 digits available for temporary user")
                return None

        # Create temporary user data
        temp_user_data = {
            'uid': temp_user_id,
            'phoneNumberLast4': phone_last_4,
            'displayName': guest_name or 'Guest',
            'isTemporary': True,
            'magicLinkToken': token_hash,
            'reservationIds': [reservation.get('id')],
            'createdVia': 'magic_link',
            'createdAt': datetime.now(timezone.utc),
            'expiresAt': magic_link_data.get('expires_at'),
            'pinCode': phone_last_4,  # Initially same as phone last 4
            'lastVerified': datetime.now(timezone.utc),
            'status': 'verified',
            'accessLevel': 'limited_info_access'
        }

        # Save to users collection
        db.collection('users').document(temp_user_id).set(temp_user_data)
        logger.info(f"Created temporary user: {temp_user_id}")

        return temp_user_id

    except Exception as e:
        logger.error(f"Error creating temporary user: {e}")
        return None

def get_temporary_user(user_id: str) -> Optional[Dict]:
    """
    Get temporary user data.

    Args:
        user_id: Temporary user ID

    Returns:
        User data if found, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        doc_ref = db.collection('users').document(user_id)
        doc = doc_ref.get()

        if doc.exists:
            user_data = doc.to_dict()
            user_data['id'] = doc.id

            # Check if user is expired
            expires_at = user_data.get('expiresAt')
            if expires_at and expires_at < datetime.now(timezone.utc):
                logger.warning(f"Temporary user {user_id} has expired")
                return None

            return user_data
        else:
            return None

    except Exception as e:
        logger.error(f"Error getting temporary user {user_id}: {e}")
        return None

def update_temporary_user_name(user_id: str, display_name: str) -> bool:
    """
    Update the display name for a temporary user.
    
    Args:
        user_id: Temporary user ID
        display_name: New display name to set
        
    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        doc_ref = db.collection('users').document(user_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            logger.warning(f"Temporary user {user_id} not found for name update")
            return False
        
        # Update the display name and timestamp
        doc_ref.update({
            'displayName': display_name,
            'updatedAt': datetime.now(timezone.utc),
            'nameUpdatedAt': datetime.now(timezone.utc)
        })
        
        logger.info(f"Updated display name for temporary user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating temporary user name {user_id}: {e}")
        return False

def verify_user_pin(user_id: str, entered_pin: str) -> bool:
    """
    Verify a user's PIN code.
    
    Args:
        user_id: User ID to verify PIN for
        entered_pin: PIN entered by user
        
    Returns:
        True if PIN is correct, False otherwise
    """
    try:
        user_doc = db.collection('users').document(user_id).get()
        
        if not user_doc.exists:
            logger.warning(f"User {user_id} not found for PIN verification")
            return False
        
        user_data = user_doc.to_dict()
        stored_pin = user_data.get('pinCode')
        
        if not stored_pin:
            logger.warning(f"User {user_id} has no PIN set")
            return False
        
        return str(stored_pin) == str(entered_pin)
        
    except Exception as e:
        logger.error(f"Error verifying PIN for user {user_id}: {e}")
        return False

def update_user_pin(user_id: str, new_pin: str) -> bool:
    """
    Update a user's PIN code.
    
    Args:
        user_id: User ID to update PIN for
        new_pin: New PIN to set
        
    Returns:
        True if successful, False otherwise
    """
    try:
        user_ref = db.collection('users').document(user_id)
        user_ref.update({
            'pinCode': new_pin,
            'lastUpdated': datetime.now().isoformat(),
            'pinUpdatedAt': datetime.now().isoformat()
        })
        
        logger.info(f"PIN updated successfully for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating PIN for user {user_id}: {e}")
        return False

def has_default_pin(user_id: str) -> bool:
    """
    Check if a user is using the default PIN (last 4 digits of phone).
    
    Args:
        user_id: User ID to check
        
    Returns:
        True if using default PIN, False otherwise
    """
    try:
        user_doc = db.collection('users').document(user_id).get()
        
        if not user_doc.exists:
            return False
        
        user_data = user_doc.to_dict()
        phone_number = user_data.get('phoneNumber', '')
        stored_pin = user_data.get('pinCode', '')
        
        if not phone_number or not stored_pin:
            return False
        
        # Extract last 4 digits from phone number
        phone_digits = ''.join(filter(str.isdigit, phone_number))
        default_pin = phone_digits[-4:] if len(phone_digits) >= 4 else ''
        
        return str(stored_pin) == default_pin
        
    except Exception as e:
        logger.error(f"Error checking default PIN for user {user_id}: {e}")
        return False

def create_user_with_pin(user_id: str, user_data: Dict[str, Any], pin: Optional[str] = None) -> bool:
    """
    Create a new user with optional PIN.
    
    Args:
        user_id: User ID (typically Firebase UID)
        user_data: User data dictionary
        pin: Optional PIN to set (defaults to last 4 digits of phone if not provided)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Set default PIN if not provided
        if not pin and user_data.get('phoneNumber'):
            phone_digits = ''.join(filter(str.isdigit, user_data['phoneNumber']))
            pin = phone_digits[-4:] if len(phone_digits) >= 4 else '0000'
        
        # Add PIN to user data
        if pin:
            user_data['pinCode'] = pin
            user_data['pinCreatedAt'] = datetime.now().isoformat()
        
        # Add creation timestamp
        user_data['createdAt'] = datetime.now().isoformat()
        user_data['lastUpdated'] = datetime.now().isoformat()
        
        # Create user document
        db.collection('users').document(user_id).set(user_data)
        
        logger.info(f"User created successfully: {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating user {user_id}: {e}")
        return False

def get_user_auth_info(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user authentication information.
    
    Args:
        user_id: User ID to get info for
        
    Returns:
        Dictionary with auth info or None if not found
    """
    try:
        user_doc = db.collection('users').document(user_id).get()
        
        if not user_doc.exists:
            return None
        
        user_data = user_doc.to_dict()
        
        return {
            'id': user_id,
            'phoneNumber': user_data.get('phoneNumber', ''),
            'displayName': user_data.get('displayName', ''),
            'role': user_data.get('role', 'guest'),
            'accountType': user_data.get('accountType', 'temporary'),
            'isTemporary': user_data.get('isTemporary', False),
            'hasPin': bool(user_data.get('pinCode')),
            'hasDefaultPin': has_default_pin(user_id),
            'createdAt': user_data.get('createdAt', ''),
            'lastLogin': user_data.get('lastLogin', '')
        }
        
    except Exception as e:
        logger.error(f"Error getting auth info for user {user_id}: {e}")
        return None

def update_last_login(user_id: str) -> bool:
    """
    Update user's last login timestamp.

    Args:
        user_id: User ID to update

    Returns:
        True if successful, False otherwise
    """
    try:
        user_ref = db.collection('users').document(user_id)
        user_ref.update({
            'lastLogin': datetime.now().isoformat(),
            'lastUpdated': datetime.now().isoformat()
        })

        return True

    except Exception as e:
        logger.error(f"Error updating last login for user {user_id}: {e}")
        return False

def record_data_access_consent(user_id: str, consent_type: str = 'airbnb_data_access',
                              consent_details: Dict = None) -> bool:
    """
    Record user's data access consent with timestamp.

    Args:
        user_id: User ID who gave consent
        consent_type: Type of consent (e.g., 'airbnb_data_access')
        consent_details: Additional details about the consent

    Returns:
        True if successful, False otherwise
    """
    if not initialize_firebase():
        return False

    try:
        timestamp = datetime.now(timezone.utc)

        # Prepare consent record
        consent_record = {
            'type': consent_type,
            'timestamp': timestamp,
            'details': consent_details or {},
            'ipAddress': consent_details.get('ipAddress') if consent_details else None,
            'userAgent': consent_details.get('userAgent') if consent_details else None
        }

        # Update user document with consent information
        user_ref = db.collection('users').document(user_id)

        # Use array union to add consent record to consents array
        user_ref.update({
            'consents': firestore.ArrayUnion([consent_record]),
            'lastConsentAt': timestamp,
            'updatedAt': timestamp
        })

        logger.info(f"Recorded {consent_type} consent for user {user_id}")
        return True

    except Exception as e:
        logger.error(f"Error recording consent for user {user_id}: {e}")
        return False

def get_user_consents(user_id: str) -> List[Dict]:
    """
    Get all consent records for a user.

    Args:
        user_id: User ID to get consents for

    Returns:
        List of consent records
    """
    if not initialize_firebase():
        return []

    try:
        user_doc = db.collection('users').document(user_id).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return user_data.get('consents', [])
        return []

    except Exception as e:
        logger.error(f"Error getting consents for user {user_id}: {e}")
        return []

def create_temporary_firebase_token(user_id: str) -> Optional[str]:
    """
    Create a temporary Firebase custom token for a temporary user.
    This allows temporary users to authenticate with WebSocket.

    Args:
        user_id: Temporary user ID

    Returns:
        Custom token if successful, None otherwise
    """
    if not initialize_firebase():
        return None

    try:
        # Get temporary user data
        temp_user = get_temporary_user(user_id)
        if not temp_user:
            logger.error(f"Temporary user {user_id} not found for token creation")
            return None

        # Create custom claims for the temporary user
        custom_claims = {
            'isTemporary': True,
            'accessLevel': temp_user.get('accessLevel', 'limited_info_access'),
            'reservationIds': temp_user.get('reservationIds', []),
            'phoneNumberLast4': temp_user.get('phoneNumberLast4'),
            'createdVia': 'magic_link'
        }

        # Create custom token using Firebase Admin SDK
        custom_token = auth.create_custom_token(user_id, custom_claims)

        # Convert bytes to string if necessary
        if isinstance(custom_token, bytes):
            custom_token = custom_token.decode('utf-8')

        logger.info(f"Created custom token for temporary user: {user_id}")
        return custom_token

    except Exception as e:
        logger.error(f"Error creating temporary Firebase token: {e}")
        return None

def create_temporary_id_token(user_id: str) -> Optional[str]:
    """
    Create a mock ID token for temporary users that mimics Firebase ID token structure.
    This is used for WebSocket authentication.

    Args:
        user_id: Temporary user ID

    Returns:
        Mock ID token if successful, None otherwise
    """
    try:
        import json
        import base64
        from datetime import datetime, timezone, timedelta

        # Get temporary user data
        temp_user = get_temporary_user(user_id)
        if not temp_user:
            logger.error(f"Temporary user {user_id} not found for ID token creation")
            return None

        # Create JWT header
        header = {
            "alg": "RS256",
            "typ": "JWT",
            "kid": "temp_magic_link"
        }

        # Create JWT payload that mimics Firebase ID token
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=4)  # Match session duration

        payload = {
            "iss": "https://securetoken.google.com/clean-art-454915-d9",
            "aud": "clean-art-454915-d9",
            "auth_time": int(now.timestamp()),
            "user_id": user_id,
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "firebase": {
                "identities": {},
                "sign_in_provider": "magic_link"
            },
            "isTemporary": True,
            "accessLevel": temp_user.get('accessLevel', 'limited_info_access'),
            "reservationIds": temp_user.get('reservationIds', []),
            "phoneNumberLast4": temp_user.get('phoneNumberLast4'),
            "displayName": temp_user.get('displayName', 'Guest')
        }

        # Encode header and payload
        header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')

        # Create a mock signature (not cryptographically valid, but sufficient for our use case)
        signature = base64.urlsafe_b64encode(f"temp_signature_{user_id}".encode()).decode().rstrip('=')

        # Combine into JWT format
        mock_token = f"{header_encoded}.{payload_encoded}.{signature}"

        logger.info(f"Created mock ID token for temporary user: {user_id}")
        return mock_token

    except Exception as e:
        logger.error(f"Error creating temporary ID token: {e}")
        return None

def create_ephemeral_token(user_id: str) -> Optional[str]:
    """
    Create a legitimate ephemeral token for voice call authentication using Google's API.
    This provides a secure, temporary token that can be used for Gemini Live API access.
    
    Args:
        user_id: User ID for whom to create the token
        
    Returns:
        Ephemeral token if successful, None otherwise
    """
    try:
        import os
        from datetime import datetime, timezone, timedelta
        
        # Get the Gemini API key from environment
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.error("GEMINI_API_KEY not found in environment variables")
            return None

        # Get user data for logging purposes
        user_data = get_user_auth_info(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found for ephemeral token creation")
            return None

        # Import the Google GenAI SDK
        import google.genai as genai
        
        # Create client with v1alpha API version (required for auth_tokens.create())
        client = genai.Client(
            api_key=api_key,
            http_options={'api_version': 'v1alpha'}
        )
        
        # Calculate expiration times
        now = datetime.now(timezone.utc)
        expire_time = now + timedelta(minutes=30)  # 30 minute expiration
        new_session_expire_time = now + timedelta(minutes=1)  # 1 minute for new sessions
        
        logger.info(f"Creating ephemeral token for user {user_id} (expires: {expire_time})")
        
        # Create ephemeral token with Live API constraints
        token = client.auth_tokens.create(
            config={
                'uses': 10,  # Allow multiple uses for WebSocket connection
                'expire_time': expire_time,
                'new_session_expire_time': new_session_expire_time,
                'live_connect_constraints': {
                    'model': 'models/gemini-live-2.5-flash-preview',
                    'config': {
                        'session_resumption': {},
                        'temperature': 0.7,
                        'response_modalities': ['AUDIO', 'TEXT']
                    }
                },
                'http_options': {'api_version': 'v1alpha'},
            }
        )
        
        # Extract the token name (this is what we use for authentication)
        token_name = token.name
        if not token_name:
            logger.error("Failed to get token name from created ephemeral token")
            return None
            
        logger.info(f"Successfully created ephemeral token for user {user_id}: {token_name[:20]}...")
        return token_name

    except ImportError as e:
        logger.error(f"Failed to import google-genai SDK: {e}. Install with: pip install google-genai")
        return None
    except Exception as e:
        logger.error(f"Error creating ephemeral token for user {user_id}: {e}")
        return None

