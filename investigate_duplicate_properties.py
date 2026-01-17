#!/usr/bin/env python3
"""
Script to investigate duplicate properties in Firestore.
"""

import sys
import os
import json
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

from concierge.utils.firestore_client import initialize_firebase, get_firestore_db, get_property

def investigate_properties():
    """Investigate the three duplicate properties."""
    
    # Initialize Firestore
    if not initialize_firebase():
        print("❌ Failed to initialize Firebase")
        return
    
    db = get_firestore_db()
    if not db:
        print("❌ Failed to get Firestore database")
        return
    
    print("✅ Connected to Firestore")
    print("=" * 80)
    
    # Property IDs to investigate
    property_ids = [
        "83ed9ba9-d4ca-4f65-bd57-296a9a585402",
        "9684d928-f1e9-41fd-875c-77fa57e837cb", 
        "ce7679be-9e96-47ab-b047-606c8d4baa81"
    ]
    
    properties_data = []
    
    for property_id in property_ids:
        print(f"\n🔍 Investigating Property: {property_id}")
        print("-" * 60)
        
        property_data = get_property(property_id)
        if property_data:
            properties_data.append(property_data)
            
            # Extract key information
            created_at = property_data.get('createdAt')
            updated_at = property_data.get('updatedAt')
            airbnb_url = property_data.get('airbnbListingUrl', 'N/A')
            name = property_data.get('name', 'N/A')
            address = property_data.get('address', 'N/A')
            host_id = property_data.get('hostId', 'N/A')
            status = property_data.get('status', 'N/A')
            new_flag = property_data.get('new', 'N/A')
            
            print(f"📝 Name: {name}")
            print(f"📍 Address: {address}")
            print(f"🔗 Airbnb URL: {airbnb_url}")
            print(f"👤 Host ID: {host_id}")
            print(f"📊 Status: {status}")
            print(f"🆕 New Flag: {new_flag}")
            print(f"📅 Created: {created_at}")
            print(f"🔄 Updated: {updated_at}")
            
            # Check for setup progress
            setup_progress = property_data.get('setupProgress', {})
            if setup_progress:
                print(f"⚙️ Setup Progress: {setup_progress}")
            
            # Check for house rules
            house_rules = property_data.get('houseRules', [])
            print(f"🏠 House Rules: {len(house_rules)} items")
            
            # Check for emergency info
            emergency_info = property_data.get('emergencyInfo', [])
            print(f"🚨 Emergency Info: {len(emergency_info)} items")
            
            # Check for property facts
            property_facts = property_data.get('propertyFacts', [])
            print(f"📋 Property Facts: {len(property_facts)} items")
            
        else:
            print(f"❌ Property {property_id} not found")
    
    # Compare properties
    print("\n" + "=" * 80)
    print("🔍 COMPARISON ANALYSIS")
    print("=" * 80)
    
    if len(properties_data) > 1:
        # Check for same Airbnb URL
        airbnb_urls = [p.get('airbnbListingUrl') for p in properties_data]
        unique_urls = set(filter(None, airbnb_urls))
        
        print(f"\n🔗 Airbnb URLs found: {len(unique_urls)}")
        for url in unique_urls:
            matching_properties = [p['id'] for p in properties_data if p.get('airbnbListingUrl') == url]
            print(f"   URL: {url}")
            print(f"   Properties: {matching_properties}")
        
        # Check creation times
        print(f"\n📅 Creation Timeline:")
        sorted_properties = sorted(properties_data, key=lambda x: x.get('createdAt', datetime.min))
        for i, prop in enumerate(sorted_properties, 1):
            created = prop.get('createdAt', 'Unknown')
            print(f"   {i}. {prop['id']} - {created}")
        
        # Check for differences in key fields
        print(f"\n📊 Key Differences:")
        fields_to_compare = ['name', 'address', 'hostId', 'status', 'new']
        
        for field in fields_to_compare:
            values = [p.get(field) for p in properties_data]
            unique_values = set(filter(lambda x: x is not None, values))
            if len(unique_values) > 1:
                print(f"   {field}: DIFFERENT VALUES - {unique_values}")
            else:
                print(f"   {field}: Same - {list(unique_values)[0] if unique_values else 'N/A'}")
    
    # Query for all properties with the same Airbnb URL
    print(f"\n🔍 Searching for ALL properties with Airbnb URL...")
    target_url = "https://www.airbnb.com/rooms/700299802944952028"
    
    try:
        query = db.collection('properties').where('airbnbListingUrl', '==', target_url)
        all_matching = []
        
        for doc in query.stream():
            prop_data = doc.to_dict()
            prop_data['id'] = doc.id
            all_matching.append(prop_data)
        
        print(f"📊 Found {len(all_matching)} properties with URL: {target_url}")
        
        for prop in all_matching:
            created = prop.get('createdAt', 'Unknown')
            status = prop.get('status', 'Unknown')
            print(f"   - {prop['id']} (Created: {created}, Status: {status})")
            
    except Exception as e:
        print(f"❌ Error querying properties by URL: {e}")

if __name__ == "__main__":
    investigate_properties()
