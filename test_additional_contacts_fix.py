#!/usr/bin/env python3
"""
Test script to verify that additional contacts are preserved during iCal sync.
"""

import sys
import os

# Add the concierge directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

def test_additional_contacts_preservation():
    """Test that additional contacts are preserved during sync."""
    print("=" * 60)
    print("TESTING ADDITIONAL CONTACTS PRESERVATION AFTER FIX")
    print("=" * 60)
    
    try:
        # Import required functions
        from concierge.utils.firestore_client import (
            get_firestore_client, 
            list_property_reservations,
            update_reservation
        )
        from concierge.utils.reservations import update_all_reservations
        
        # Initialize Firestore
        db = get_firestore_client()
        if not db:
            print("Error: Could not initialize Firestore.")
            return
            
        print("✅ Connected to Firestore successfully!")
        
        # Test property ID
        property_id = "1a344329-2670-4b34-a4f6-e28513a3200c"
        
        # Get initial reservations state
        initial_reservations = list_property_reservations(property_id)
        print(f"📋 Found {len(initial_reservations)} reservations for property {property_id}")
        
        # Find reservations with additional contacts
        reservations_with_contacts = []
        for reservation in initial_reservations:
            additional_contacts = (
                reservation.get('additional_contacts') or
                reservation.get('additionalContacts') or
                reservation.get('AdditionalContacts') or
                []
            )
            if additional_contacts:
                reservations_with_contacts.append({
                    'id': reservation.get('id'),
                    'contacts': additional_contacts,
                    'contact_count': len(additional_contacts)
                })
                print(f"📞 Reservation {reservation.get('id')} has {len(additional_contacts)} additional contacts")
        
        # If no reservations have contacts, add some test contacts
        if not reservations_with_contacts and initial_reservations:
            print("🔧 No reservations with additional contacts found. Adding test contacts...")
            
            test_reservation = initial_reservations[0]
            reservation_id = test_reservation.get('id')
            
            test_contacts = [
                {"name": "Test Contact 1", "phone": "+17738377523"},
                {"name": "Test Contact 2", "phone": "+15551234567"}
            ]
            
            update_data = {
                'additional_contacts': test_contacts
            }
            
            success = update_reservation(reservation_id, update_data)
            
            if success:
                print(f"✅ Added {len(test_contacts)} test contacts to reservation {reservation_id}")
                reservations_with_contacts = [{
                    'id': reservation_id,
                    'contacts': test_contacts,
                    'contact_count': len(test_contacts)
                }]
            else:
                print("❌ Failed to add test contacts")
                return
        
        if not reservations_with_contacts:
            print("❌ No reservations with additional contacts to test")
            return
        
        print(f"🧪 Testing preservation for {len(reservations_with_contacts)} reservations with contacts")
        
        # Run the iCal sync
        print("-" * 40)
        print("🔄 Running iCal sync...")
        update_all_reservations()
        print("✅ iCal sync completed")
        print("-" * 40)
        
        # Check if contacts were preserved
        updated_reservations = list_property_reservations(property_id)
        
        all_preserved = True
        
        for original in reservations_with_contacts:
            reservation_id = original['id']
            original_count = original['contact_count']
            
            # Find the updated reservation
            updated_reservation = None
            for res in updated_reservations:
                if res.get('id') == reservation_id:
                    updated_reservation = res
                    break
            
            if not updated_reservation:
                print(f"❌ FAILURE: Reservation {reservation_id} not found after sync!")
                all_preserved = False
                continue
            
            # Check preserved contacts
            preserved_contacts = (
                updated_reservation.get('additional_contacts') or
                updated_reservation.get('additionalContacts') or
                updated_reservation.get('AdditionalContacts') or
                []
            )
            
            preserved_count = len(preserved_contacts)
            
            if preserved_count == original_count:
                print(f"✅ SUCCESS: Reservation {reservation_id} preserved {preserved_count} contacts")
                for contact in preserved_contacts:
                    print(f"   📞 {contact.get('name', 'Unknown')}: {contact.get('phone', 'Unknown')}")
            else:
                print(f"❌ FAILURE: Reservation {reservation_id} lost contacts! Had {original_count}, now has {preserved_count}")
                all_preserved = False
        
        print("-" * 40)
        if all_preserved:
            print("🎉 ALL TESTS PASSED: Additional contacts were preserved during sync!")
        else:
            print("💥 SOME TESTS FAILED: Additional contacts were not properly preserved!")
        print("-" * 40)
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_additional_contacts_preservation() 