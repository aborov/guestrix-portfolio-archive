#!/usr/bin/env python3
"""
Script to check what properties exist in the database.
"""

import sys
import os

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

def check_properties():
    """Check what properties exist in the database."""
    print("🔍 Checking properties in the database...")
    
    try:
        from concierge.utils.firestore_client import list_properties_by_host
        
        # Try to get properties for a few common host IDs
        test_host_ids = [
            "69X7Zvv3cwVvAsbMXL4hN7SyUdC2",  # From the memory
            "temp_magic_",  # From the browser logs
            "test_host"
        ]
        
        all_properties = []
        
        for host_id in test_host_ids:
            print(f"  Checking host: {host_id}")
            properties = list_properties_by_host(host_id)
            if properties:
                print(f"    Found {len(properties)} properties for host {host_id}")
                all_properties.extend(properties)
            else:
                print(f"    No properties found for host {host_id}")
        
        if not all_properties:
            print("❌ No properties found in the database for any test hosts")
            return []
        
        print(f"\n✅ Found {len(all_properties)} total properties:")
        for i, prop in enumerate(all_properties):
            prop_id = prop.get('id', 'unknown')
            prop_name = prop.get('name', 'Unnamed Property')
            host_id = prop.get('hostId', 'unknown')
            print(f"  {i+1}. ID: {prop_id}")
            print(f"     Name: {prop_name}")
            print(f"     Host: {host_id}")
            print()
        
        return all_properties
        
    except Exception as e:
        print(f"❌ Error checking properties: {e}")
        import traceback
        traceback.print_exc()
        return []

def check_property_by_id(property_id):
    """Check if a specific property exists."""
    print(f"🔍 Checking if property {property_id} exists...")
    
    try:
        from concierge.utils.firestore_client import get_property
        
        property_data = get_property(property_id)
        
        if property_data:
            print(f"✅ Property found:")
            print(f"   ID: {property_data.get('id', 'unknown')}")
            print(f"   Name: {property_data.get('name', 'Unnamed Property')}")
            print(f"   Host: {property_data.get('hostId', 'unknown')}")
            return property_data
        else:
            print(f"❌ Property {property_id} not found")
            return None
            
    except Exception as e:
        print(f"❌ Error checking property {property_id}: {e}")
        return None

if __name__ == "__main__":
    print("🚀 PROPERTY DATABASE CHECK")
    print("=" * 50)
    
    # Check all properties
    properties = check_properties()
    
    # Check the specific property from the magic link
    print("\n" + "=" * 50)
    check_property_by_id("001eb55a-3def-41d1-85f5-e68f67d12ead")
    
    # If we found properties, suggest using one of them
    if properties:
        print("\n" + "=" * 50)
        print("💡 SUGGESTION:")
        print("Use one of the existing property IDs above for testing.")
        print("You can create a new magic link with a valid property ID.")
