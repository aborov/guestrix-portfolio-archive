#!/usr/bin/env python3
"""
Test the exact logic from the API route to see what's happening.
"""

import sys
import os

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

def test_api_route_logic():
    """Test the exact logic from the API route."""
    print("🔍 Testing API route logic...")
    
    try:
        from concierge.utils.firestore_client import get_property
        from concierge.utils.firestore_ai_helpers import process_query_with_rag
        
        # Simulate the API route logic
        data = {
            "query": "hello",
            "propertyId": "c42198de-2ca4-45f7-b699-a05c2eac5990",
            "conversationHistory": []
        }
        
        query = data.get('query')
        property_id = data.get('propertyId')
        conversation_history = data.get('conversationHistory', [])
        
        print(f"📋 Query: {query}")
        print(f"📋 Property ID: {property_id}")
        print(f"📋 Conversation History: {len(conversation_history)} messages")
        
        if not query:
            print("❌ Query is required")
            return False
        
        if not property_id:
            print("❌ Property ID is required")
            return False
        
        # Get property context
        print("🔍 Getting property data...")
        property_data = get_property(property_id)
        if not property_data:
            print("❌ Property not found")
            return False
        
        print(f"✅ Property found: {property_data.get('name', 'Unknown')}")
        
        # Process the query with RAG
        print("🤖 Processing query with RAG...")
        result = process_query_with_rag(
            user_query=query,
            property_id=property_id,
            property_context=property_data,
            conversation_history=conversation_history
        )
        
        print("✅ RAG processing completed")
        print(f"📨 Response: {result.get('response', 'No response')}")
        print(f"📊 Has Context: {result.get('has_context', False)}")
        print(f"📊 Context Used: {len(result.get('context_used', []))} items")
        
        # Return the response (simulate API response)
        response_data = {
            "success": True,
            "response": result.get('response', ''),
            "has_context": result.get('has_context', False),
            "context_used": result.get('context_used', [])
        }
        
        print("✅ API route logic completed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error in API route logic: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 API ROUTE LOGIC TEST")
    print("=" * 50)
    
    success = test_api_route_logic()
    
    if success:
        print("\n🎉 API route logic is working correctly!")
        print("The issue might be in the Flask request handling or server context.")
    else:
        print("\n❌ API route logic has issues")

if __name__ == "__main__":
    main()





