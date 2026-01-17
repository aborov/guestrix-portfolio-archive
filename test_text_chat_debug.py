#!/usr/bin/env python3
"""
Test script to debug text chat issues in the guest dashboard.
This script will help identify where the text chat flow is breaking.
"""

import requests
import json
import socketio
import time
import sys
from urllib.parse import urljoin

# Configuration
BASE_URL = "http://localhost:8080"
SOCKETIO_URL = "http://localhost:8080"

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

def test_socketio_connection():
    """Test Socket.IO connection"""
    print("\n🔍 Testing Socket.IO connection...")
    
    sio = socketio.Client()
    connected = False
    
    @sio.event
    def connect():
        nonlocal connected
        connected = True
        print("✅ Socket.IO connected successfully")
    
    @sio.event
    def disconnect():
        print("🔌 Socket.IO disconnected")
    
    @sio.event
    def connect_error(data):
        print(f"❌ Socket.IO connection error: {data}")
    
    @sio.event
    def text_message_from_ai(data):
        print(f"📨 Received AI response: {data}")
    
    @sio.event
    def chat_error(data):
        print(f"❌ Chat error: {data}")
    
    try:
        # Try to connect
        sio.connect(SOCKETIO_URL, wait_timeout=10)
        
        if connected:
            print("✅ Socket.IO connection established")
            
            # Test sending a message (this will likely fail due to auth, but we'll see the error)
            print("\n🔍 Testing message sending...")
            test_message = {
                'message': 'Hello, this is a test message',
                'property_id': 'test-property-123'
            }
            
            sio.emit('text_message_from_user', test_message)
            print("📤 Test message sent")
            
            # Wait for response or error
            time.sleep(3)
            
            sio.disconnect()
            return True
        else:
            print("❌ Socket.IO connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Socket.IO connection failed: {e}")
        return False

def test_authentication_flow():
    """Test the authentication flow"""
    print("\n🔍 Testing authentication flow...")
    
    # Test if we can access the login page
    try:
        response = requests.get(f"{BASE_URL}/auth/login", timeout=5)
        if response.status_code == 200:
            print("✅ Login page accessible")
        else:
            print(f"❌ Login page not accessible: {response.status_code}")
    except Exception as e:
        print(f"❌ Login page test failed: {e}")

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
        
        if response.status_code == 200:
            print("✅ Chat query API endpoint working")
            result = response.json()
            print(f"📨 API Response: {result.get('response', 'No response')}")
        else:
            print(f"❌ Chat query API failed: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Chat query API test failed: {e}")

def main():
    """Main test function"""
    print("🚀 Starting text chat debugging...")
    print(f"Testing against: {BASE_URL}")
    
    # Run tests
    health_ok = test_health_endpoint()
    if not health_ok:
        print("\n❌ Server is not responding. Please start the server first.")
        sys.exit(1)
    
    test_authentication_flow()
    test_api_endpoints()
    test_socketio_connection()
    
    print("\n🏁 Debugging complete!")
    print("\n📋 Summary of findings:")
    print("- Check server logs for detailed error messages")
    print("- Verify authentication is working properly")
    print("- Check if property IDs are being resolved correctly")
    print("- Ensure Socket.IO events are being handled properly")

if __name__ == "__main__":
    main()





