#!/usr/bin/env python3
"""
Debug script to test magic link creation and retrieval.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_magic_link_creation():
    """Test creating and retrieving a magic link."""
    print("🧪 Testing Magic Link Creation and Retrieval...")
    
    try:
        from concierge.utils.firestore_client import (
            create_magic_link, get_magic_link_by_token, generate_magic_link_url,
            hash_magic_link_token
        )
        
        # Test with a fake reservation ID
        test_reservation_id = "test-reservation-123"
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

def test_existing_token():
    """Test the specific token you're having issues with."""
    print("\n🔍 Testing Your Specific Token...")
    
    token = "c36BTOEIdFVfXwHeNIbI6nLUco8odVx61UX1E1lp9HY"
    
    try:
        from concierge.utils.firestore_client import (
            get_magic_link_by_token, hash_magic_link_token
        )
        
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
            
    except Exception as e:
        print(f"❌ Error testing token: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Magic Link Creation Debug\n")
    
    # Test creation process
    result = test_magic_link_creation()
    
    # Test your specific token
    test_existing_token()
    
    print(f"\n📝 Summary:")
    if result:
        print(f"✅ Magic link creation works")
        print(f"🔗 Test this link: {result['magic_link_url']}")
    else:
        print(f"❌ Magic link creation failed")
    
    print(f"\n💡 Next steps:")
    print(f"1. Check the debug output above")
    print(f"2. Visit: http://localhost:5001/magic/debug/c36BTOEIdFVfXwHeNIbI6nLUco8odVx61UX1E1lp9HY")
    print(f"3. Check your Flask server logs for detailed error messages")
