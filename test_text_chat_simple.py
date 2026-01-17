#!/usr/bin/env python3
"""
Simple test script to debug text chat issues without external dependencies.
"""

import requests
import json
import time

# Configuration
BASE_URL = "http://localhost:8080"

def test_health_endpoint():
    """Test if the server is responding"""
    print("🔍 Testing server health...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Server is healthy")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Server health check failed: {e}")
        return False

def test_api_endpoints():
    """Test relevant API endpoints"""
    print("\n🔍 Testing API endpoints...")
    
    # Test chat query endpoint
    try:
        test_data = {
            'query': 'Hello, this is a test',
            'propertyId': 'test-property-123',
            'conversationHistory': []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/chat/query",
            json=test_data,
            timeout=10
        )
        
        print(f"📊 Chat API Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Chat query API endpoint working")
            result = response.json()
            print(f"📨 API Response: {result.get('response', 'No response')}")
        else:
            print(f"❌ Chat query API failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Chat query API test failed: {e}")

def test_authentication_flow():
    """Test the authentication flow"""
    print("\n🔍 Testing authentication flow...")
    
    # Test if we can access the login page
    try:
        response = requests.get(f"{BASE_URL}/auth/login", timeout=5)
        print(f"📊 Login page status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Login page accessible")
        else:
            print(f"❌ Login page not accessible: {response.status_code}")
    except Exception as e:
        print(f"❌ Login page test failed: {e}")

def test_guest_dashboard_access():
    """Test guest dashboard access"""
    print("\n🔍 Testing guest dashboard access...")
    
    try:
        # Test if we can access the guest dashboard (will redirect to login if not authenticated)
        response = requests.get(f"{BASE_URL}/guest", timeout=5, allow_redirects=False)
        print(f"📊 Guest dashboard status: {response.status_code}")
        
        if response.status_code == 302:
            print("✅ Guest dashboard redirects to login (expected for unauthenticated)")
        elif response.status_code == 200:
            print("✅ Guest dashboard accessible")
        else:
            print(f"❌ Guest dashboard access issue: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Guest dashboard test failed: {e}")

def main():
    """Main test function"""
    print("🚀 Starting text chat debugging...")
    print(f"Testing against: {BASE_URL}")
    
    # Run tests
    health_ok = test_health_endpoint()
    if not health_ok:
        print("\n❌ Server is not responding. Please start the server first.")
        return
    
    test_authentication_flow()
    test_guest_dashboard_access()
    test_api_endpoints()
    
    print("\n🏁 Debugging complete!")
    print("\n📋 Common text chat issues and solutions:")
    print("1. Authentication: Make sure you're logged in or using a valid magic link")
    print("2. Property ID: Ensure the property ID is correctly set in the dashboard")
    print("3. Socket.IO Connection: Check browser console for connection errors")
    print("4. Server Logs: Check server logs for detailed error messages")
    print("5. Network: Ensure WebSocket connections are not blocked by firewall/proxy")

if __name__ == "__main__":
    main()
