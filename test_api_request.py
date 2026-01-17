#!/usr/bin/env python3
"""
Test the API request with detailed logging.
"""

import requests
import json
import time

def test_api_request():
    """Test the API request with detailed logging."""
    print("🚀 API REQUEST TEST")
    print("=" * 50)
    
    # Test data
    property_id = "c42198de-2ca4-45f7-b699-a05c2eac5990"
    test_message = "hello"
    
    # API endpoint
    url = "http://localhost:8080/api/chat/query"
    
    # Request payload
    payload = {
        "query": test_message,
        "propertyId": property_id,
        "conversationHistory": []
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"📤 Making request to: {url}")
    print(f"📋 Payload: {json.dumps(payload, indent=2)}")
    print(f"📋 Headers: {headers}")
    
    try:
        # Make the request
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        end_time = time.time()
        
        response_time = end_time - start_time
        
        print(f"⏱️  Response time: {response_time:.2f} seconds")
        print(f"📊 Status Code: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        # Print response body
        try:
            response_data = response.json()
            print(f"📨 Response Body: {json.dumps(response_data, indent=2)}")
        except json.JSONDecodeError:
            print(f"📨 Response Body (raw): {response.text}")
        
        if response.status_code == 200:
            print("✅ Request successful!")
            return True
        else:
            print(f"❌ Request failed with status {response.status_code}")
            return False
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Connection error - is the server running?")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def main():
    print("🚀 DETAILED API REQUEST TEST")
    print("=" * 50)
    
    success = test_api_request()
    
    if success:
        print("\n🎉 API request was successful!")
    else:
        print("\n❌ API request failed")

if __name__ == "__main__":
    main()





