#!/usr/bin/env python3
"""
Test Firestore connection for magic links.
"""

import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_firestore_connection():
    """Test basic Firestore connectivity."""
    print("🧪 Testing Firestore Connection...")
    
    try:
        from concierge.utils.firestore_client import initialize_firebase, db
        
        # Test initialization
        if initialize_firebase():
            print("✅ Firestore initialized successfully")
            
            # Test basic read operation
            try:
                # Try to read from a collection (this will work even if empty)
                test_collection = db.collection('magic_links')
                docs = list(test_collection.limit(1).stream())
                print(f"✅ Firestore read test successful (found {len(docs)} documents)")
                
                # Test write operation
                test_doc_ref = db.collection('magic_links').document('test-connection')
                test_doc_ref.set({
                    'test': True,
                    'timestamp': 'test-connection-check'
                })
                print("✅ Firestore write test successful")
                
                # Clean up test document
                test_doc_ref.delete()
                print("✅ Firestore delete test successful")
                
                return True
                
            except Exception as e:
                print(f"❌ Firestore operation failed: {e}")
                return False
                
        else:
            print("❌ Firestore initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Firestore connection error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_magic_link_token_operations():
    """Test magic link token operations without database."""
    print("\n🧪 Testing Magic Link Token Operations...")
    
    try:
        from concierge.utils.firestore_client import (
            generate_magic_link_token, hash_magic_link_token, generate_magic_link_url
        )
        
        # Test token generation
        token = generate_magic_link_token()
        print(f"✅ Token generated: {token[:8]}...")
        
        # Test token hashing
        token_hash = hash_magic_link_token(token)
        print(f"✅ Token hashed: {token_hash[:8]}...")
        
        # Test URL generation
        url = generate_magic_link_url(token)
        print(f"✅ URL generated: {url}")
        
        # Verify URL format
        if "localhost:5001" in url:
            print("✅ URL format correct for local development")
        else:
            print("❌ URL format incorrect for local development")
            
        return True
        
    except Exception as e:
        print(f"❌ Token operation error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Firestore Connection Test\n")
    
    # Test basic operations
    token_test = test_magic_link_token_operations()
    
    # Test Firestore connection
    firestore_test = test_firestore_connection()
    
    print(f"\n📊 Results:")
    print(f"Token operations: {'✅ PASS' if token_test else '❌ FAIL'}")
    print(f"Firestore connection: {'✅ PASS' if firestore_test else '❌ FAIL'}")
    
    if not firestore_test:
        print(f"\n💡 If Firestore connection failed:")
        print(f"1. Check your Firebase credentials in .env file")
        print(f"2. Make sure GOOGLE_APPLICATION_CREDENTIALS points to valid JSON file")
        print(f"3. Verify your Firebase project settings")
    
    if token_test and firestore_test:
        print(f"\n🎉 All tests passed! Magic link system should work.")
    else:
        print(f"\n❌ Some tests failed. Check the errors above.")
