#!/usr/bin/env python3
"""
Simple test script for Gemini ephemeral token generation.

This script tests the ephemeral token creation using the official Google GenAI SDK
to understand the correct implementation before fixing the Node.js version.
"""

import os
import datetime
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_basic_token_creation():
    """Test basic ephemeral token creation using the official SDK."""
    try:
        # Import the official SDK
        import genai
        
        # Get API key from environment
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("❌ GEMINI_API_KEY not found in environment variables")
            return False
            
        print(f"✅ Found API key: {api_key[:10]}...")
        
        # Create client with v1alpha API version (required for ephemeral tokens)
        client = genai.Client(
            api_key=api_key,
            http_options={'api_version': 'v1alpha'}
        )
        
        print("✅ Created GenAI client with v1alpha API version")
        
        # Calculate expiration times
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        expire_time = now + datetime.timedelta(minutes=30)
        new_session_expire_time = now + datetime.timedelta(minutes=1)
        
        print(f"⏰ Token will expire at: {expire_time}")
        print(f"⏰ New session window expires at: {new_session_expire_time}")
        
        # Create ephemeral token with basic configuration
        print("🔄 Creating ephemeral token...")
        token = client.auth_tokens.create(
            config={
                'uses': 1,  # Single use
                'expire_time': expire_time,
                'new_session_expire_time': new_session_expire_time,
                'http_options': {'api_version': 'v1alpha'},
            }
        )
        
        print("✅ Successfully created ephemeral token!")
        print(f"📝 Token name: {token.name}")
        print(f"📝 Token type: {type(token)}")
        
        # Verify token format
        if token.name and token.name.startswith('auth_tokens/'):
            print("✅ Token has correct format (starts with 'auth_tokens/')")
        else:
            print(f"❌ Token format unexpected: {token.name}")
            
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import genai SDK: {e}")
        print("💡 Install with: pip install google-genai")
        return False
    except Exception as e:
        print(f"❌ Error creating ephemeral token: {e}")
        print(f"📝 Error type: {type(e)}")
        return False

def test_constrained_token_creation():
    """Test ephemeral token creation with Live API constraints."""
    try:
        import genai
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("❌ GEMINI_API_KEY not found")
            return False
            
        client = genai.Client(
            api_key=api_key,
            http_options={'api_version': 'v1alpha'}
        )
        
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        expire_time = now + datetime.timedelta(minutes=30)
        new_session_expire_time = now + datetime.timedelta(minutes=1)
        
        print("🔄 Creating constrained ephemeral token...")
        
        # Create token with Live API constraints
        token = client.auth_tokens.create(
            config={
                'uses': 1,
                'expire_time': expire_time,
                'new_session_expire_time': new_session_expire_time,
                'live_connect_constraints': {
                    'model': 'gemini-2.0-flash-live-001',
                    'config': {
                        'session_resumption': {},
                        'temperature': 0.7,
                        'response_modalities': ['AUDIO', 'TEXT']
                    }
                },
                'http_options': {'api_version': 'v1alpha'},
            }
        )
        
        print("✅ Successfully created constrained ephemeral token!")
        print(f"📝 Token name: {token.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating constrained token: {e}")
        return False

def test_raw_http_request():
    """Test creating ephemeral token using raw HTTP requests (like Node.js implementation)."""
    try:
        import requests
        import json
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            print("❌ GEMINI_API_KEY not found")
            return False
            
        # Calculate expiration times
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        expire_time = now + datetime.timedelta(minutes=30)
        new_session_expire_time = now + datetime.timedelta(minutes=1)
        
        # Create the request payload (corrected format)
        payload = {
            "uses": 1,
            "expireTime": expire_time.isoformat(),
            "newSessionExpireTime": new_session_expire_time.isoformat(),
            "liveConnectConstraints": {
                "model": "models/gemini-2.0-flash-live-001",
                "config": {
                    "sessionResumption": {},
                    "temperature": 0.7,
                    "responseModalities": ["AUDIO", "TEXT"]
                }
            }
        }
        
        print("🔄 Creating ephemeral token via raw HTTP request...")
        print(f"📝 Request payload: {json.dumps(payload, indent=2)}")
        
        # Make the HTTP request
        response = requests.post(
            'https://generativelanguage.googleapis.com/v1alpha/authTokens',
            headers={
                'x-goog-api-key': api_key,
                'Content-Type': 'application/json'
            },
            json=payload
        )
        
        print(f"📝 Response status: {response.status_code}")
        print(f"📝 Response headers: {dict(response.headers)}")
        
        if response.ok:
            token_data = response.json()
            print("✅ Successfully created ephemeral token via HTTP!")
            print(f"📝 Token response: {json.dumps(token_data, indent=2)}")
            return True
        else:
            print(f"❌ HTTP request failed: {response.status_code}")
            print(f"📝 Error response: {response.text}")
            return False
            
    except ImportError:
        print("❌ requests library not available. Install with: pip install requests")
        return False
    except Exception as e:
        print(f"❌ Error in HTTP request test: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Testing Ephemeral Token Implementation for Guestrix")
    print("=" * 60)
    
    # Test 1: Basic token creation
    print("\n📋 Test 1: Basic Token Creation (SDK)")
    print("-" * 40)
    success1 = test_basic_token_creation()
    
    # Test 2: Constrained token creation
    print("\n📋 Test 2: Constrained Token Creation (SDK)")
    print("-" * 40)
    success2 = test_constrained_token_creation()
    
    # Test 3: Raw HTTP request (like Node.js)
    print("\n📋 Test 3: Raw HTTP Request (Node.js style)")
    print("-" * 40)
    success3 = test_raw_http_request()
    
    # Summary
    print("\n📊 Test Results Summary")
    print("=" * 40)
    print(f"Basic Token Creation: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"Constrained Token: {'✅ PASS' if success2 else '❌ FAIL'}")
    print(f"Raw HTTP Request: {'✅ PASS' if success3 else '❌ FAIL'}")
    
    if success3:
        print("\n🎉 Raw HTTP method works! This shows us the correct format for Node.js.")
        print("💡 Now we can fix your Guestrix server implementation.")
    else:
        print("\n❌ Some tests failed. Check your API key and network connection.")

if __name__ == "__main__":
    main()
