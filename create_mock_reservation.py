#!/usr/bin/env python3
"""
Script to create a mock reservation in Firestore development database.
Creates a reservation with propertyID 707f2656-c6b4-4c0a-a67d-f6bc272114cd
and endDate one year from now.
"""

import sys
import os
from datetime import datetime, timezone, timedelta
import uuid

# Add the concierge directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

from concierge.utils.firestore_client import initialize_firebase, get_firestore_db, create_reservation

def create_mock_reservation():
    """Create a mock reservation with the specified parameters."""
    
    # Initialize Firebase
    if not initialize_firebase():
        print("Failed to initialize Firebase")
        return None
    
    # Get Firestore database instance
    db = get_firestore_db()
    if not db:
        print("Failed to get Firestore database")
        return None
    
    # Calculate dates
    now = datetime.now(timezone.utc)
    start_date = (now + timedelta(days=7)).strftime('%Y-%m-%d')  # Start in 7 days
    end_date = (now + timedelta(days=365)).strftime('%Y-%m-%d')  # End in 1 year
    
    # Create mock reservation data
    reservation_data = {
        'propertyId': '707f2656-c6b4-4c0a-a67d-f6bc272114cd',
        'startDate': start_date,
        'endDate': end_date,
        'guestName': 'Mock Guest',
        'guestPhoneNumber': '+15551234567',
        'guestPhoneLast4': '4567',
        'summary': 'Mock reservation for testing purposes',
        'description': 'This is a mock reservation created for development and testing. It has an end date one year from now.',
        'status': 'active',
        'additionalContacts': [
            {
                'name': 'Additional Guest',
                'phone': '+15551234567',
                'relationship': 'Family Member'
            }
        ]
    }
    
    try:
        # Create the reservation
        reservation_id = create_reservation(reservation_data)
        
        if reservation_id:
            print(f"✅ Successfully created mock reservation!")
            print(f"   Reservation ID: {reservation_id}")
            print(f"   Property ID: {reservation_data['propertyId']}")
            print(f"   Start Date: {start_date}")
            print(f"   End Date: {end_date}")
            print(f"   Guest: {reservation_data['guestName']}")
            print(f"   Phone: {reservation_data['guestPhoneNumber']}")
            print(f"   Status: {reservation_data['status']}")
            
            # Verify the reservation was created by fetching it
            doc_ref = db.collection('reservations').document(reservation_id)
            doc = doc_ref.get()
            
            if doc.exists:
                created_data = doc.to_dict()
                print(f"\n📋 Verification - Retrieved reservation data:")
                print(f"   Document ID: {doc.id}")
                print(f"   Created At: {created_data.get('createdAt')}")
                print(f"   Updated At: {created_data.get('updatedAt')}")
                print(f"   All fields: {list(created_data.keys())}")
            else:
                print("⚠️  Warning: Could not verify reservation creation")
                
            return reservation_id
        else:
            print("❌ Failed to create reservation")
            return None
            
    except Exception as e:
        print(f"❌ Error creating reservation: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main function to create the mock reservation."""
    print("🚀 Creating mock reservation in Firestore development database...")
    print(f"   Target Property ID: 707f2656-c6b4-4c0a-a67d-f6bc272114cd")
    print(f"   End Date: One year from now")
    print("-" * 60)
    
    reservation_id = create_mock_reservation()
    
    if reservation_id:
        print("-" * 60)
        print("🎉 Mock reservation created successfully!")
        print(f"   You can now use reservation ID: {reservation_id}")
        print(f"   for testing and development purposes.")
    else:
        print("-" * 60)
        print("💥 Failed to create mock reservation.")
        print("   Please check your Firebase configuration and try again.")

if __name__ == "__main__":
    main()


