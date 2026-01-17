#!/usr/bin/env python3
"""
Test magic link functionality with explicit credentials setup.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Set the credentials path explicitly (relative to script location)
script_dir = os.path.dirname(os.path.abspath(__file__))
credentials_path = os.path.join(script_dir, 'concierge', 'credentials', 'clean-art-454915-d9-firebase-adminsdk-fbsvc-9e1734f79e.json')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
os.environ['FLASK_ENV'] = 'development'
os.environ['DEBUG_MODE'] = 'True'

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

def test_magic_link_creation_with_explicit_credentials():
    """Test creating and retrieving a magic link with explicit credentials."""
    print("🧪 Testing Magic Link Creation with Explicit Credentials...")
    
    try:
        print(f"Credentials path: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
        print(f"File exists: {os.path.exists(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))}")
        
        from concierge.utils.firestore_client import (
            create_magic_link, get_magic_link_by_token, generate_magic_link_url,
            hash_magic_link_token, initialize_firebase
        )
        
        # Test Firebase initialization
        print("Testing Firebase initialization...")
        if initialize_firebase():
            print("✅ Firebase initialized successfully")
        else:
            print("❌ Firebase initialization failed")
            return None
        
        # Test with a fake reservation ID
        test_reservation_id = "test-reservation-magic-link-123"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        
        print(f"Creating magic link for reservation: {test_reservation_id}")
        print(f"Expires at: {expires_at}")
        
        # Create magic link
        raw_token = create_magic_link(test_reservation_id, expires_at)
        
        if raw_token:
            print(f"✅ Magic link created successfully")
            print(f"   Raw token: {raw_token}")
            
            # Generate URL
            magic_link_url = generate_magic_link_url(raw_token)
            print(f"   Magic link URL: {magic_link_url}")
            
            # Test retrieval
            print(f"\nTesting retrieval...")
            magic_link_data = get_magic_link_by_token(raw_token)
            
            if magic_link_data:
                print(f"✅ Magic link retrieved successfully")
                print(f"   Data: {magic_link_data}")
                
                # Test hash
                token_hash = hash_magic_link_token(raw_token)
                print(f"   Token hash: {token_hash}")
                
                return {
                    'raw_token': raw_token,
                    'magic_link_url': magic_link_url,
                    'magic_link_data': magic_link_data
                }
            else:
                print(f"❌ Failed to retrieve magic link")
                return None
        else:
            print(f"❌ Failed to create magic link")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_your_specific_token():
    """Test the specific token you're having issues with."""
    print("\n🔍 Testing Your Specific Token...")
    
    token = "c36BTOEIdFVfXwHeNIbI6nLUco8odVx61UX1E1lp9HY"
    
    try:
        from concierge.utils.firestore_client import (
            get_magic_link_by_token, hash_magic_link_token, initialize_firebase
        )
        
        # Ensure Firebase is initialized
        if not initialize_firebase():
            print("❌ Firebase initialization failed")
            return
        
        print(f"Token: {token}")
        
        # Test hash
        token_hash = hash_magic_link_token(token)
        print(f"Token hash: {token_hash}")
        
        # Test retrieval
        magic_link_data = get_magic_link_by_token(token)
        print(f"Magic link data: {magic_link_data}")
        
        if magic_link_data:
            print("✅ Token found in database")
            
            # Check reservation
            reservation_id = magic_link_data.get('reservation_id')
            if reservation_id:
                from concierge.utils.firestore_client import get_reservation
                reservation = get_reservation(reservation_id)
                print(f"Reservation found: {reservation is not None}")
                if reservation:
                    print(f"Reservation data: {reservation}")
                else:
                    print("❌ Reservation not found - this is likely the issue!")
            else:
                print("❌ No reservation_id in magic link data")
        else:
            print("❌ Token not found in database - this is the issue!")
            print("   This means the magic link was never saved to Firestore")
            print("   The issue is likely in the host UI magic link generation")
            
    except Exception as e:
        print(f"❌ Error testing token: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Magic Link Test with Explicit Credentials\n")
    
    # Test creation process
    result = test_magic_link_creation_with_explicit_credentials()
    
    # Test your specific token
    test_your_specific_token()
    
    print(f"\n📝 Summary:")
    if result:
        print(f"✅ Magic link creation and retrieval works!")
        print(f"🔗 Test this working link: {result['magic_link_url']}")
        print(f"\n💡 Your original token issue:")
        print(f"   The token c36BTOEIdFVfXwHeNIbI6nLUco8odVx61UX1E1lp9HY was likely")
        print(f"   generated before Firestore was properly connected, so it was")
        print(f"   never saved to the database.")
    else:
        print(f"❌ Magic link creation still failed")
    
    print(f"\n🎯 Next steps:")
    print(f"1. If creation worked, try generating a NEW magic link from the host UI")
    print(f"2. The new link should work properly now that Firestore is connected")
    print(f"3. Test the new link in your browser")
