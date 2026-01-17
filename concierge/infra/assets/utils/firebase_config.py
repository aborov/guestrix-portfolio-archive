import os
from dotenv import load_dotenv

# Ensure environment variables are loaded
if not os.getenv('FIREBASE_API_KEY'):
    load_dotenv()

def get_firebase_config():
    """
    Returns a dictionary with Firebase configuration for frontend.
    This is a transitional function that will be removed once
    the migration to AWS Cognito is complete.
    """
    return {
        'apiKey': os.getenv('FIREBASE_API_KEY', ''),
        'authDomain': os.getenv('FIREBASE_AUTH_DOMAIN', ''),
        'projectId': os.getenv('FIREBASE_PROJECT_ID', ''),
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', ''),
        'messagingSenderId': os.getenv('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId': os.getenv('FIREBASE_APP_ID', ''),
        'measurementId': os.getenv('FIREBASE_MEASUREMENT_ID', '')
    } 