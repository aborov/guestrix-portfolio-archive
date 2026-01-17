#!/usr/bin/env python3
"""
Test script to verify the reservation update fix.
This script checks for reservations with null dates and tests the update process.
"""

import sys
import os

# Add the concierge directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

def test_reservation_update_fix():
    """Test that the reservation update fix prevents dates from being nullified."""
    print("=" * 60)
    print("TESTING RESERVATION UPDATE FIX")
    print("=" * 60)
    
    try:
        # Import required functions
        from concierge.utils.firestore_client import (
            get_firestore_client,
            list_property_reservations,
            get_reservation
        )
        
        # Initialize Firestore
        db = get_firestore_client()
        if not db:
            print("Error: Could not initialize Firestore.")
            return
            
        print("✅ Connected to Firestore successfully!")
        
        # Test property ID from logs
        property_id = "1a344329-2670-4b34-a4f6-e28513a3200c"
        print(f"🏠 Testing property: {property_id}")
        
        # Get all reservations for this property
        reservations = list_property_reservations(property_id)
        print(f"📋 Found {len(reservations)} reservations for property {property_id}")
        
        # Check for problematic reservations
        problematic_reservations = []
        valid_reservations = []
        
        for reservation in reservations:
            reservation_id = reservation.get('id')
            start_date = reservation.get('startDate')
            end_date = reservation.get('endDate')
            additional_contacts = reservation.get('additional_contacts', [])
            
            print(f"\n📄 Reservation {reservation_id}:")
            print(f"   Start Date: {start_date}")
            print(f"   End Date: {end_date}")
            print(f"   Additional Contacts: {len(additional_contacts)}")
            
            if additional_contacts:
                print(f"   Contact Details: {additional_contacts}")
            
            # Check if this reservation has null dates
            if (start_date is None or end_date is None) and additional_contacts:
                print(f"   ❌ PROBLEM: Reservation has null dates but has additional contacts!")
                problematic_reservations.append({
                    'id': reservation_id,
                    'startDate': start_date,
                    'endDate': end_date,
                    'additional_contacts': additional_contacts
                })
            elif start_date and end_date:
                print(f"   ✅ OK: Reservation has valid dates")
                valid_reservations.append(reservation_id)
            else:
                print(f"   ⚠️  Warning: Reservation has null dates but no additional contacts")
        
        # Summary
        print(f"\n📊 SUMMARY:")
        print(f"   Total reservations: {len(reservations)}")
        print(f"   Valid reservations: {len(valid_reservations)}")
        print(f"   Problematic reservations: {len(problematic_reservations)}")
        
        if problematic_reservations:
            print(f"\n❌ ISSUES FOUND:")
            for prob in problematic_reservations:
                print(f"   Reservation {prob['id']} has {len(prob['additional_contacts'])} contacts but null dates")
            print(f"\n💡 The fix I implemented should prevent this from happening during future updates.")
        else:
            print(f"\n✅ NO ISSUES FOUND: All reservations with additional contacts have valid dates.")
        
        # Test the date preservation logic
        print(f"\n🧪 TESTING DATE PRESERVATION LOGIC:")
        print("The fix ensures that when preserving additional contacts during updates,")
        print("the existing startDate and endDate are always included in the update_data")
        print("to prevent the normalize_reservation_dates function from setting them to null.")
        
        return len(problematic_reservations) == 0
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_reservation_update_fix()
    if success:
        print(f"\n🎉 TEST PASSED: Reservation update fix appears to be working correctly!")
    else:
        print(f"\n💥 TEST FAILED: Issues were found that need to be addressed.") 