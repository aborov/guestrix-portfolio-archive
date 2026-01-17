#!/usr/bin/env python3
"""
Debug script to test the chat API and see what's happening.
"""

import sys
import os

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

def test_process_query_with_rag():
    """Test the process_query_with_rag function directly."""
    print("🔍 Testing process_query_with_rag function directly...")
    
    try:
        from concierge.utils.firestore_ai_helpers import process_query_with_rag
        from concierge.utils.firestore_client import get_property
        
        property_id = "c42198de-2ca4-45f7-b699-a05c2eac5990"
        
        # Get property data
        print(f"📋 Getting property data for {property_id}...")
        property_data = get_property(property_id)
        
        if not property_data:
            print("❌ Property not found")
            return False
        
        print(f"✅ Property found: {property_data.get('name', 'Unknown')}")
        
        # Test the RAG function
        print("🤖 Testing RAG function...")
        result = process_query_with_rag(
            user_query="hello",
            property_id=property_id,
            property_context=property_data,
            conversation_history=[]
        )
        
        print("✅ RAG function completed successfully")
        print(f"📨 Response: {result.get('response', 'No response')}")
        print(f"📊 Has Context: {result.get('has_context', False)}")
        print(f"📊 Context Used: {len(result.get('context_used', []))} items")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing RAG function: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🚀 DEBUG CHAT API")
    print("=" * 50)
    
    success = test_process_query_with_rag()
    
    if success:
        print("\n🎉 RAG function is working correctly!")
        print("The issue might be in the API route or server configuration.")
    else:
        print("\n❌ RAG function has issues")
        print("Check the error messages above for details.")

if __name__ == "__main__":
    main()
