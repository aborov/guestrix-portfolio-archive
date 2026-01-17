#!/usr/bin/env python3
"""
Test script to verify Firestore security rules are working
"""
import os
import sys
from firebase_admin import credentials, firestore, initialize_app
from google.cloud.exceptions import Forbidden

def test_rules():
    """Test if security rules are active by trying to access Firestore"""
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    # Initialize Firebase Admin SDK
    cred_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
    if not cred_path:
        print("❌ FIREBASE_SERVICE_ACCOUNT_PATH not set")
        return False
    
    try:
        cred = credentials.Certificate(cred_path)
        app = initialize_app(cred)
        
        # Test default database
        print("🔍 Testing (default) database...")
        db_default = firestore.client(app=app, database='(default)')
        
        # Try to read a document (should work with test mode rules)
        try:
            doc = db_default.collection('users').document('test').get()
            print("✅ (default) database: Rules allow read access (test mode)")
        except Forbidden:
            print("❌ (default) database: Rules blocking access (unexpected)")
        except Exception as e:
            print(f"ℹ️  (default) database: {type(e).__name__} - {e}")
        
        # Test development database
        print("🔍 Testing development database...")
        db_dev = firestore.client(app=app, database='development')
        
        # Try to read a document (should be blocked without proper auth)
        try:
            doc = db_dev.collection('users').document('test').get()
            print("⚠️  development database: Rules allow read access (might be too permissive)")
        except Forbidden:
            print("✅ development database: Rules blocking access (security rules active)")
        except Exception as e:
            print(f"ℹ️  development database: {type(e).__name__} - {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error initializing Firebase: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Firestore Security Rules...")
    test_rules()











