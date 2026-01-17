#!/usr/bin/env python3
"""
Script to create a test magic link with a valid property ID.
"""

import sys
import os

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

def create_test_magic_link():
    """Create a magic link for the valid property."""
    print("🔗 Creating test magic link...")
    
    try:
        from concierge.utils.firestore_client import create_property_magic_link
        
        # Use the production property ID that exists
        property_id = "c42198de-2ca4-45f7-b699-a05c2eac5990"
        
        print(f"Creating magic link for property: {property_id}")
        
        # Create the magic link
        token = create_property_magic_link(property_id)
        
        if token:
            # Generate the URL
            base_url = "http://localhost:8080"
            magic_link_url = f"{base_url}/magic/{token}/guest"
            
            print(f"✅ Magic link created successfully!")
            print(f"🔗 Magic Link URL: {magic_link_url}")
            print(f"📋 Token: {token}")
            print(f"🏠 Property ID: {property_id}")
            
            return magic_link_url
        else:
            print("❌ Failed to create magic link")
            return None
            
    except Exception as e:
        print(f"❌ Error creating magic link: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🚀 CREATE TEST MAGIC LINK")
    print("=" * 50)
    
    magic_link_url = create_test_magic_link()
    
    if magic_link_url:
        print("\n" + "=" * 50)
        print("🎉 SUCCESS!")
        print("You can now test the text chat using this magic link:")
        print(f"   {magic_link_url}")
        print("\nThe text chat should work properly with this valid property ID.")
    else:
        print("\n" + "=" * 50)
        print("❌ FAILED to create magic link")
        print("Check the error messages above for details.")
