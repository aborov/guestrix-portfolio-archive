#!/usr/bin/env python3
"""
Test script to verify the text chat backend is working correctly.
"""

import requests
import json
import sys
import os

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

BASE_URL = "http://localhost:8080"

def test_chat_api_directly():
    """Test the chat API directly with the same property ID from the logs"""
    print("🔍 Testing chat API with the property ID from your session...")
    
    # Use the valid property ID we found
    property_id = "cf5e9984-bfee-4fed-b5e2-69d3af873489"
    
    test_data = {
        'query': 'hi there',
        'propertyId': property_id,
        'conversationHistory': []
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat/query",
            json=test_data,
            timeout=15
        )
        
        print(f"📊 Chat API Status: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Chat API working correctly")
            print(f"📨 Response: {result.get('response', 'No response')}")
            print(f"📊 Has Context: {result.get('has_context', False)}")
            print(f"📊 Context Used: {len(result.get('context_used', []))} items")
            return True
        else:
            print(f"❌ Chat API failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Chat API test failed: {e}")
        return False

def test_property_exists():
    """Test if the property exists in the database"""
    print("\n🔍 Testing if property exists...")
    
    try:
        from concierge.utils.firestore_client import get_property
        
        property_id = "c42198de-2ca4-45f7-b699-a05c2eac5990"
        property_data = get_property(property_id)
        
        if property_data:
            print("✅ Property exists in database")
            print(f"📋 Property Name: {property_data.get('name', 'No name')}")
            print(f"📋 Property Address: {property_data.get('address', 'No address')}")
            return True
        else:
            print("❌ Property not found in database")
            return False
            
    except Exception as e:
        print(f"❌ Error checking property: {e}")
        return False

def test_rag_processing():
    """Test RAG processing directly"""
    print("\n🔍 Testing RAG processing...")
    
    try:
        from concierge.utils.ai_helpers import process_query_with_rag
        from concierge.utils.firestore_client import get_property
        
        property_id = "c42198de-2ca4-45f7-b699-a05c2eac5990"
        
        # Get property data
        property_data = get_property(property_id)
        if not property_data:
            print("❌ Cannot test RAG - property not found")
            return False
        
        print(f"📋 Testing RAG with property: {property_data.get('name', 'No name')}")
        
        # Test RAG processing
        result = process_query_with_rag(
            user_query="hi there",
            property_id=property_id,
            property_context=property_data,
            conversation_history=[]
        )
        
        print("✅ RAG processing successful")
        print(f"📨 Response: {result.get('response', 'No response')}")
        print(f"📊 Has Context: {result.get('has_context', False)}")
        print(f"📊 Context Used: {len(result.get('context_used', []))} items")
        
        return True
        
    except Exception as e:
        print(f"❌ RAG processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 TEXT CHAT BACKEND DIAGNOSTIC")
    print("=" * 50)
    print(f"Testing with property ID: c42198de-2ca4-45f7-b699-a05c2eac5990")
    
    # Run tests
    tests_passed = 0
    total_tests = 3
    
    if test_property_exists():
        tests_passed += 1
    
    if test_rag_processing():
        tests_passed += 1
    
    if test_chat_api_directly():
        tests_passed += 1
    
    # Summary
    print(f"\n📊 BACKEND DIAGNOSTIC SUMMARY:")
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("🎉 Backend is working correctly!")
        print("💡 The issue might be in the Socket.IO message handling or response emission.")
    elif tests_passed >= 2:
        print("⚠️  Backend mostly working. Check the failing test above.")
    else:
        print("❌ Backend has issues. Check the errors above.")
    
    print("\n🔧 NEXT STEPS:")
    print("1. If backend tests pass, the issue is in Socket.IO message handling")
    print("2. Check server console for any error messages")
    print("3. Verify the Socket.IO response emission is working")
    print("4. Check if there are any authentication issues with the Socket.IO handler")

if __name__ == "__main__":
    main()
