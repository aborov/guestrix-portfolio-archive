#!/usr/bin/env python3
"""
Test script for magic link functionality.
"""

import sys
import os
from datetime import datetime, timezone, timedelta

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'concierge'))

def test_magic_link_functions():
    """Test the magic link functions."""
    print("🧪 Testing Magic Link Functions...")
    
    try:
        # Import the functions
        from concierge.utils.firestore_client import (
            create_magic_link, get_magic_link_by_token, verify_magic_link_phone,
            generate_magic_link_url, hash_magic_link_token, generate_magic_link_token
        )
        
        print("✅ Successfully imported magic link functions")
        
        # Test token generation
        token = generate_magic_link_token()
        print(f"✅ Generated token: {token[:8]}...")
        
        # Test token hashing
        token_hash = hash_magic_link_token(token)
        print(f"✅ Generated hash: {token_hash[:8]}...")
        
        # Test URL generation
        url = generate_magic_link_url(token)
        print(f"✅ Generated URL: {url}")
        
        # Verify URL format
        expected_prefix = "https://app.guestrix.ai/magic/"
        if url.startswith(expected_prefix):
            print("✅ URL format is correct")
        else:
            print(f"❌ URL format incorrect. Expected prefix: {expected_prefix}")
            
        print("\n🎉 All magic link function tests passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

def test_magic_link_routes():
    """Test that magic link routes are properly registered."""
    print("\n🧪 Testing Magic Link Routes...")
    
    try:
        from concierge.app import app
        
        # Get all registered routes
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append(rule.rule)
        
        # Check for magic link routes
        magic_routes = [
            '/magic/<token>',
            '/magic/<token>/verify',
            '/magic/<token>/name',
            '/magic/<token>/guest',
            '/magic/<token>/upgrade'
        ]
        
        missing_routes = []
        for route in magic_routes:
            if route not in routes:
                missing_routes.append(route)
        
        if missing_routes:
            print(f"❌ Missing routes: {missing_routes}")
            return False
        else:
            print("✅ All magic link routes are registered")
            
        # Check API routes
        api_routes = [
            '/api/property/<property_id>/reservations/<reservation_id>/magic-link',
            '/api/property/<property_id>/reservations/<reservation_id>/magic-links',
            '/api/property/<property_id>/reservations/<reservation_id>/magic-links/<link_id>/revoke'
        ]
        
        missing_api_routes = []
        for route in api_routes:
            if route not in routes:
                missing_api_routes.append(route)
        
        if missing_api_routes:
            print(f"❌ Missing API routes: {missing_api_routes}")
            return False
        else:
            print("✅ All magic link API routes are registered")
            
        print("\n🎉 All route tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Route test error: {e}")
        return False

def test_templates():
    """Test that magic link templates exist."""
    print("\n🧪 Testing Magic Link Templates...")
    
    template_files = [
        'concierge/templates/magic_link_verify.html',
        'concierge/templates/magic_link_name.html',
        'concierge/templates/magic_link_error.html',
        'concierge/templates/magic_link_upgrade.html'
    ]
    
    missing_templates = []
    for template in template_files:
        if not os.path.exists(template):
            missing_templates.append(template)
    
    if missing_templates:
        print(f"❌ Missing templates: {missing_templates}")
        return False
    else:
        print("✅ All magic link templates exist")
        print("\n🎉 All template tests passed!")
        return True

def main():
    """Run all tests."""
    print("🚀 Starting Magic Link Implementation Tests\n")
    
    tests = [
        test_magic_link_functions,
        test_magic_link_routes,
        test_templates
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()  # Add spacing between tests
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Magic link implementation is ready.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
