#!/usr/bin/env python3
"""
Test property lookup to see what's happening.
"""

import sys
import os

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

def test_property_lookup():
    """Test property lookup function."""
    print("🔍 Testing property lookup...")
    
    try:
        from concierge.utils.firestore_client import get_property
        
        property_id = "c42198de-2ca4-45f7-b699-a05c2eac5990"
        
        print(f"📋 Looking up property: {property_id}")
        property_data = get_property(property_id)
        
        if property_data:
            print("✅ Property found:")
            print(f"   ID: {property_data.get('id', 'Unknown')}")
            print(f"   Name: {property_data.get('name', 'Unknown')}")
            print(f"   Host: {property_data.get('hostId', 'Unknown')}")
            return True
        else:
            print("❌ Property not found")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 PROPERTY LOOKUP TEST")
    print("=" * 50)
    
    success = test_property_lookup()
    
    if success:
        print("\n🎉 Property lookup is working correctly!")
    else:
        print("\n❌ Property lookup has issues")

if __name__ == "__main__":
    main()





