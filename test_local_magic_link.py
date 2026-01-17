#!/usr/bin/env python3
"""
Test script to generate a magic link for local testing.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_local_magic_link():
    """Generate a magic link for local testing."""
    print("🧪 Testing Local Magic Link Generation...")
    
    try:
        # Import the functions
        from concierge.utils.firestore_client import (
            generate_magic_link_token, generate_magic_link_url
        )
        
        # Generate a test token
        token = generate_magic_link_token()
        print(f"✅ Generated token: {token}")
        
        # Generate URL
        url = generate_magic_link_url(token)
        print(f"✅ Generated URL: {url}")
        
        # Check if it's using localhost
        if "localhost:5001" in url:
            print("✅ URL is correctly configured for local development")
            print(f"\n🎉 You can test this magic link by visiting:")
            print(f"   {url}")
            print(f"\n📝 Make sure your Flask server is running on port 5001")
            return url
        else:
            print("❌ URL is not configured for local development")
            print("   This will try to access the production domain")
            return None
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def create_test_reservation_and_magic_link():
    """Create a test reservation and magic link for full testing."""
    print("\n🧪 Creating Test Reservation and Magic Link...")
    
    try:
        from concierge.utils.firestore_client import (
            create_reservation, create_magic_link, generate_magic_link_url
        )
        
        # Create a test reservation
        test_reservation = {
            'propertyId': 'test-property-local',
            'startDate': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'endDate': (datetime.now(timezone.utc) + timedelta(days=3)).strftime('%Y-%m-%d'),
            'guestName': 'Test Guest',
            'guestPhoneNumber': '+15551234567',  # Test phone number
            'propertyName': 'Test Property for Magic Links',
            'propertyAddress': '123 Test Street, Test City'
        }
        
        print("Creating test reservation...")
        reservation_id = create_reservation(test_reservation)
        
        if reservation_id:
            print(f"✅ Created test reservation: {reservation_id}")
            
            # Create magic link
            expires_at = datetime.now(timezone.utc) + timedelta(days=1)
            raw_token = create_magic_link(reservation_id, expires_at)
            
            if raw_token:
                magic_link_url = generate_magic_link_url(raw_token)
                print(f"✅ Created magic link: {magic_link_url}")
                print(f"\n🎯 Test Instructions:")
                print(f"1. Visit: {magic_link_url}")
                print(f"2. Enter last 4 digits: 4567")
                print(f"3. Test the complete flow!")
                
                return {
                    'reservation_id': reservation_id,
                    'magic_link_url': magic_link_url,
                    'phone_last_4': '4567'
                }
            else:
                print("❌ Failed to create magic link")
        else:
            print("❌ Failed to create test reservation")
            
    except Exception as e:
        print(f"❌ Error creating test data: {e}")
        import traceback
        traceback.print_exc()
        
    return None

if __name__ == "__main__":
    print("🚀 Magic Link Local Testing\n")
    
    # Test URL generation
    url = test_local_magic_link()
    
    if url and "localhost" in url:
        # Create full test scenario
        test_data = create_test_reservation_and_magic_link()
        
        if test_data:
            print(f"\n✅ Local testing setup complete!")
            print(f"\n🔗 Magic Link: {test_data['magic_link_url']}")
            print(f"📱 Phone verification: {test_data['phone_last_4']}")
        else:
            print(f"\n⚠️  Could not create test data, but you can still test with:")
            print(f"   {url}")
    else:
        print(f"\n❌ Local testing not properly configured")
