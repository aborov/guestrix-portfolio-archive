#!/usr/bin/env python3
"""
Comprehensive script to diagnose and fix text chat issues in the guest dashboard.
This script will help identify and resolve the specific problems preventing text chat from working.
"""

import requests
import json
import sys
import os
from datetime import datetime

# Add the concierge directory to the path so we can import modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

BASE_URL = "http://localhost:8080"

def test_server_connectivity():
    """Test basic server connectivity"""
    print("🔍 Testing server connectivity...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and healthy")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("💡 Make sure the Flask server is running on port 8080")
        return False

def check_firestore_connection():
    """Check if Firestore is properly connected"""
    print("\n🔍 Checking Firestore connection...")
    try:
        from concierge.utils.firestore_client import get_firestore_client, initialize_firebase
        
        # Initialize Firebase
        if initialize_firebase():
            print("✅ Firebase initialized successfully")
            
            # Test Firestore connection
            db = get_firestore_client()
            if db:
                print("✅ Firestore client connected")
                return True
            else:
                print("❌ Firestore client is None")
                return False
        else:
            print("❌ Firebase initialization failed")
            return False
            
    except Exception as e:
        print(f"❌ Firestore connection error: {e}")
        return False

def check_properties_in_database():
    """Check if there are any properties in the database"""
    print("\n🔍 Checking properties in database...")
    try:
        from concierge.utils.firestore_client import list_properties_by_host
        
        # Try to list properties (this will work even if no properties exist)
        properties = list_properties_by_host("test-host-id")
        print(f"📊 Found {len(properties)} properties in database")
        
        if len(properties) > 0:
            print("✅ Properties exist in database")
            print("📋 Sample property IDs:")
            for i, prop in enumerate(properties[:3]):  # Show first 3
                prop_id = prop.get('id', 'No ID')
                prop_name = prop.get('name', 'Unnamed')
                print(f"   {i+1}. {prop_id} - {prop_name}")
            return True
        else:
            print("⚠️  No properties found in database")
            print("💡 You need to create at least one property for text chat to work")
            return False
            
    except Exception as e:
        print(f"❌ Error checking properties: {e}")
        return False

def check_users_in_database():
    """Check if there are any users in the database"""
    print("\n🔍 Checking users in database...")
    try:
        from concierge.utils.firestore_client import get_firestore_client
        
        db = get_firestore_client()
        if not db:
            print("❌ No Firestore client available")
            return False
            
        # Try to get a sample user (this is a bit tricky without knowing user IDs)
        users_ref = db.collection('users')
        users = list(users_ref.limit(5).stream())
        
        print(f"📊 Found {len(users)} users in database")
        
        if len(users) > 0:
            print("✅ Users exist in database")
            print("📋 Sample user IDs:")
            for i, user in enumerate(users[:3]):  # Show first 3
                user_id = user.id
                user_data = user.to_dict()
                display_name = user_data.get('displayName', user_data.get('DisplayName', 'No name'))
                print(f"   {i+1}. {user_id} - {display_name}")
            return True
        else:
            print("⚠️  No users found in database")
            print("💡 You need to create at least one user for authentication to work")
            return False
            
    except Exception as e:
        print(f"❌ Error checking users: {e}")
        return False

def test_authentication_flow():
    """Test the authentication flow"""
    print("\n🔍 Testing authentication flow...")
    
    # Test login page
    try:
        response = requests.get(f"{BASE_URL}/auth/login", timeout=5)
        if response.status_code == 200:
            print("✅ Login page accessible")
        else:
            print(f"❌ Login page not accessible: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Login page test failed: {e}")
        return False
    
    # Test guest dashboard (should redirect to login)
    try:
        response = requests.get(f"{BASE_URL}/guest", timeout=5, allow_redirects=False)
        if response.status_code == 302:
            print("✅ Guest dashboard properly redirects to login")
            return True
        else:
            print(f"❌ Guest dashboard access issue: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Guest dashboard test failed: {e}")
        return False

def test_chat_api_with_valid_data():
    """Test the chat API with valid data"""
    print("\n🔍 Testing chat API...")
    
    try:
        from concierge.utils.firestore_client import list_properties_by_host
        
        # Get a real property ID from the database
        properties = list_properties_by_host("test-host-id")
        if not properties:
            print("⚠️  No properties available for testing")
            return False
            
        # Use the first property
        test_property = properties[0]
        property_id = test_property.get('id')
        
        if not property_id:
            print("❌ Property has no ID")
            return False
            
        print(f"📋 Testing with property ID: {property_id}")
        
        # Test the chat API
        test_data = {
            'query': 'Hello, this is a test message',
            'propertyId': property_id,
            'conversationHistory': []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/chat/query",
            json=test_data,
            timeout=10
        )
        
        print(f"📊 Chat API Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Chat API working correctly")
            print(f"📨 Response: {result.get('response', 'No response')}")
            return True
        else:
            print(f"❌ Chat API failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Chat API test failed: {e}")
        return False

def provide_solutions():
    """Provide solutions based on the issues found"""
    print("\n🛠️  SOLUTIONS & NEXT STEPS:")
    print("=" * 50)
    
    print("\n1. 🔐 AUTHENTICATION ISSUES:")
    print("   - Make sure you're logged in to the guest dashboard")
    print("   - Use a valid magic link if testing as a guest")
    print("   - Check that your user account exists in Firestore")
    
    print("\n2. 🏠 PROPERTY SETUP:")
    print("   - Create at least one property in the host dashboard")
    print("   - Ensure the property has a valid ID and name")
    print("   - Add some knowledge/content to the property for RAG to work")
    
    print("\n3. 🔌 SOCKET.IO CONNECTION:")
    print("   - Check browser console for WebSocket connection errors")
    print("   - Verify the WebSocket URL is correctly configured")
    print("   - Ensure no firewall/proxy is blocking WebSocket connections")
    
    print("\n4. 📊 DATABASE CONNECTIVITY:")
    print("   - Verify Firestore is properly initialized")
    print("   - Check that your Firebase credentials are correct")
    print("   - Ensure the database has the required collections (users, properties)")
    
    print("\n5. 🧪 TESTING STEPS:")
    print("   - Log in to the guest dashboard")
    print("   - Verify you can see property information")
    print("   - Try sending a simple text message")
    print("   - Check browser developer tools for errors")
    
    print("\n6. 🐛 DEBUGGING:")
    print("   - Check server logs for detailed error messages")
    print("   - Use browser developer tools to inspect network requests")
    print("   - Verify that Socket.IO events are being sent and received")

def main():
    """Main diagnostic function"""
    print("🚀 TEXT CHAT DIAGNOSTIC TOOL")
    print("=" * 50)
    print(f"Testing against: {BASE_URL}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run all tests
    tests_passed = 0
    total_tests = 6
    
    if test_server_connectivity():
        tests_passed += 1
    
    if check_firestore_connection():
        tests_passed += 1
    
    if check_properties_in_database():
        tests_passed += 1
    
    if check_users_in_database():
        tests_passed += 1
    
    if test_authentication_flow():
        tests_passed += 1
    
    if test_chat_api_with_valid_data():
        tests_passed += 1
    
    # Summary
    print(f"\n📊 DIAGNOSTIC SUMMARY:")
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Text chat should be working.")
    elif tests_passed >= 4:
        print("⚠️  Most tests passed. Text chat might work with proper authentication.")
    else:
        print("❌ Multiple issues found. Text chat will not work until these are resolved.")
    
    provide_solutions()

if __name__ == "__main__":
    main()





