import os
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Client
from dotenv import load_dotenv

def init_firestore():
    """Initialize Firestore client and create necessary collections."""
    # Load environment variables
    load_dotenv()
    
    # Initialize Firebase Admin SDK
    cred_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
    if not cred_path:
        raise ValueError("FIREBASE_SERVICE_ACCOUNT_PATH environment variable is not set")
    
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    
    # Get Firestore client
    db = firestore.client()
    
    # Create collections if they don't exist
    collections = [
        'reservations',
        'knowledge_base',
        'vector_embeddings',
        'users'
    ]
    
    for collection in collections:
        # Create a dummy document to ensure collection exists
        doc_ref = db.collection(collection).document('_init')
        doc_ref.set({
            'created_at': firestore.SERVER_TIMESTAMP,
            'status': 'initialized'
        })
        print(f"Created collection: {collection}")

if __name__ == "__main__":
    try:
        init_firestore()
        print("Database initialization completed successfully!")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        exit(1) 