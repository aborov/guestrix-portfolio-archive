#!/usr/bin/env python3
"""
Script to generate a magic link for a specific property.
"""

import os
import sys
import argparse
from datetime import datetime, timezone

# Add the concierge directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

from concierge.utils.firestore_client import (
    create_property_magic_link, 
    get_property_magic_link_token,
    generate_magic_link_url,
    get_property
)

def generate_magic_link_for_property(property_id: str, base_url: str = None):
    """Generate a magic link for a property."""
    
    print(f"Generating magic link for property: {property_id}")
    
    # First, check if the property exists
    property_data = get_property(property_id)
    if not property_data:
        print(f"❌ Property {property_id} not found")
        return None
    
    print(f"✓ Property found: {property_data.get('name', 'Unknown')}")
    
    # Get existing magic link token or create a new one
    magic_link_token = get_property_magic_link_token(property_id)
    if not magic_link_token:
        print("Creating new magic link token...")
        magic_link_token = create_property_magic_link(property_id)
        if not magic_link_token:
            print("❌ Failed to create magic link token")
            return None
        print("✓ Magic link token created")
    else:
        print("✓ Using existing magic link token")
    
    # Generate the full magic link URL
    if base_url:
        magic_link_url = f"{base_url}/magic/{magic_link_token}"
    else:
        # Use the generate_magic_link_url function to get the proper URL
        magic_link_url = generate_magic_link_url(magic_link_token)
    
    print(f"\n🎯 MAGIC LINK GENERATED")
    print("=" * 50)
    print(f"Property: {property_data.get('name', 'Unknown')}")
    print(f"Property ID: {property_id}")
    print(f"Token: {magic_link_token}")
    print(f"URL: {magic_link_url}")
    print("=" * 50)
    
    return {
        'property_id': property_id,
        'property_name': property_data.get('name', 'Unknown'),
        'token': magic_link_token,
        'url': magic_link_url
    }

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Generate a magic link for a property')
    parser.add_argument('property_id', type=str, help='Property ID to generate magic link for')
    parser.add_argument('--base-url', type=str, help='Base URL for the magic link (optional)')
    parser.add_argument('--json', action='store_true', help='Output in JSON format')
    args = parser.parse_args()
    
    # Generate the magic link
    result = generate_magic_link_for_property(args.property_id, args.base_url)
    
    if result and args.json:
        import json
        print(json.dumps(result, indent=2))
    elif result:
        print(f"\n📋 Magic link is ready to use!")
        print(f"Share this URL with guests: {result['url']}")

if __name__ == "__main__":
    main() 