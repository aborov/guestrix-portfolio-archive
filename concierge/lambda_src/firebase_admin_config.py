import os
import json
import firebase_admin
from firebase_admin import credentials, auth, firestore
from google.cloud import firestore_v1 as gc_firestore
from pathlib import Path

db = None

def _determine_firestore_database_id() -> str:
    deployment_env = os.environ.get('DEPLOYMENT_ENV', '').lower()
    if deployment_env == 'production':
        return '(default)'
    return 'development'

def _create_firestore_client_for_database(database_id: str):
    try:
        app = firebase_admin.get_app()
        credentials_obj = app.credential.get_credential()
        project_id = (
            app.project_id
            or os.environ.get('FIREBASE_PROJECT_ID')
            or os.environ.get('GOOGLE_CLOUD_PROJECT')
            or os.environ.get('GOOGLE_CLOUD_PROJECT_ID')
        )
        if not project_id:
            print("ERROR: Could not determine project ID for Firestore client")
            return None
        return gc_firestore.Client(project=project_id, credentials=credentials_obj, database=database_id)
    except Exception as e:
        print(f"ERROR: Failed to create Firestore client for database '{database_id}': {e}")
        return None

def initialize_firebase():
    """Initializes the Firebase Admin SDK if not already initialized.

    Prioritizes initialization using FIREBASE_CREDENTIALS_JSON environment variable,
    falls back to GOOGLE_APPLICATION_CREDENTIALS path, then default credentials.
    """
    global db
    if not firebase_admin._apps:
        cred = None
        cred_json_str = os.getenv('FIREBASE_CREDENTIALS_JSON')
        cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

        try:
            if cred_json_str:
                print("Initializing Firebase using FIREBASE_CREDENTIALS_JSON...")
                cred_dict = json.loads(cred_json_str)
                cred = credentials.Certificate(cred_dict)
            elif cred_path:
                # Convert relative path to absolute path
                if not os.path.isabs(cred_path):
                    # Use the path as is since it's already set in the environment
                    print(f"DEBUG: Using credentials path: {cred_path}")
                else:
                    print(f"DEBUG: Using absolute credentials path: {cred_path}")
                
                if not os.path.exists(cred_path):
                    print(f"ERROR: Credentials file not found at {cred_path}")
                    raise FileNotFoundError(f"Credentials file not found at {cred_path}")
                
                try:
                    cred = credentials.Certificate(cred_path)
                    print(f"DEBUG: Successfully created certificate object from path: {cred_path}")
                except ValueError as ve:
                    print(f"DEBUG: ValueError loading credentials from {cred_path}: {ve}")
                    raise
                except Exception as e_inner:
                    print(f"DEBUG: Unexpected error creating certificate from path {cred_path}: {type(e_inner).__name__}: {e_inner}")
                    raise
            else:
                print("Initializing Firebase using default application credentials...")
                firebase_admin.initialize_app()
                _db_id = _determine_firestore_database_id()
                db = _create_firestore_client_for_database(_db_id)
                print(f"Firebase initialized successfully using default credentials. DB: {_db_id}")
                return

            # Initialize with specific credentials if found
            firebase_admin.initialize_app(cred)
            _db_id = _determine_firestore_database_id()
            db = _create_firestore_client_for_database(_db_id)
            print(f"Firebase initialized successfully using provided credentials. DB: {_db_id}")

        except ValueError as e:
            print(f"Error initializing Firebase: Invalid credentials format. {e}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during Firebase initialization: {e}")
            raise
    else:
        # If already initialized, ensure db is set (might happen in warm Lambda starts)
        if db is None:
            _db_id = _determine_firestore_database_id()
            db = _create_firestore_client_for_database(_db_id)
        print("Firebase already initialized.")

def verify_firebase_token(id_token):
    if not firebase_admin._apps:
        initialize_firebase() # Ensure initialized
    try:
        # Add clock_skew_seconds to tolerate minor time differences
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=10)
        return decoded_token
    except Exception as e:
        print(f"Error verifying Firebase ID token: {e}")
        return None

def get_firestore_client():
    """Returns the initialized Firestore client."""
    if db is None:
        # This shouldn't happen if initialize_firebase is called at app start,
        # but provides a safeguard.
        initialize_firebase()
    return db

def get_firebase_config():
    """Returns a dictionary with Firebase web client configuration for the frontend."""
    return {
        "apiKey": os.getenv("FIREBASE_API_KEY"),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
        "projectId": os.getenv("FIREBASE_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT_ID")), # Use GCLOUD ID as fallback
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": os.getenv("FIREBASE_APP_ID")
    }

# Make sure to load environment variables if this file is run standalone (for testing)
if __name__ == '__main__':
    # If running locally for testing, you might still need dotenv here,
    # but it's removed from the main functions used by Lambda.
    # Consider adding a try-except block for dotenv import if needed for local tests.
    # For now, assume GOOGLE_APPLICATION_CREDENTIALS is set in the local test env.
    # try:
    #     from dotenv import load_dotenv
    #     load_dotenv()
    # except ImportError:
    #     print("dotenv not installed, relying on system environment variables for local testing.")
    
    initialize_firebase()
    client = get_firestore_client()
    print(f"Firestore client: {client}")
    config = get_firebase_config()
    print(f"Firebase Web Config: {config}")
    # Example: Add a test document
    # try:
    #     doc_ref = client.collection(u'test_collection').document(u'test_doc')
    #     doc_ref.set({u'message': u'Hello from firebase_admin_config!'})
    #     print("Test document added successfully.")
    # except Exception as e:
    #     print(f"Error adding test document: {e}")
