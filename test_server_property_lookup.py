#!/usr/bin/env python3
"""
Test property lookup from the server's perspective.
"""

import requests
import json

def test_server_property_lookup():
    """Test if the server can find the property."""
    print("🔍 Testing server property lookup...")
    
    # Try to get property details via the API
    property_id = "c42198de-2ca4-45f7-b699-a05c2eac5990"
    
    # Try the property endpoint
    url = f"http://localhost:8080/api/property/{property_id}"
    
    print(f"📤 Making request to: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ Property found via API:")
                print(f"   Name: {data.get('property', {}).get('name', 'Unknown')}")
                print(f"   ID: {data.get('property', {}).get('id', 'Unknown')}")
                return True
            except json.JSONDecodeError:
                print(f"📨 Response: {response.text}")
                return False
        else:
            print(f"❌ Property not found via API: {response.status_code}")
            print(f"📨 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("🚀 SERVER PROPERTY LOOKUP TEST")
    print("=" * 50)
    
    success = test_server_property_lookup()
    
    if success:
        print("\n🎉 Server can find the property!")
        print("The issue might be in the chat API route specifically.")
    else:
        print("\n❌ Server cannot find the property")
        print("There might be a database or configuration issue.")

if __name__ == "__main__":
    main()





