#!/usr/bin/env python3
"""
Debug script to test system prompt and AI processing.
"""

import sys
import os
import json
from pprint import pprint

# Add the concierge directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'concierge'))

def test_property_context():
    """Test property context retrieval"""
    print("=== TESTING PROPERTY CONTEXT ===")
    
    from concierge.utils.firestore_client import get_property
    
    property_id = '614a339c-8bd2-4f97-9f62-6a6f7a013bf0'
    
    print(f"Getting property data for: {property_id}")
    property_data = get_property(property_id)
    
    if property_data:
        print("Property data found:")
        pprint(property_data)
        
        print(f"\nWiFi details check:")
        print(f"- wifiNetwork: {property_data.get('wifiNetwork')}")
        print(f"- wifiPassword: {property_data.get('wifiPassword')}")
        print(f"- wifiDetails: {property_data.get('wifiDetails')}")
        
        return property_data
    else:
        print("❌ Property data not found!")
        return None

def test_knowledge_items():
    """Test knowledge items retrieval"""
    print("\n=== TESTING KNOWLEDGE ITEMS ===")
    
    from concierge.utils.firestore_client import list_knowledge_items_by_property
    
    property_id = '614a339c-8bd2-4f97-9f62-6a6f7a013bf0'
    
    print(f"Getting knowledge items for: {property_id}")
    knowledge_items = list_knowledge_items_by_property(property_id)
    
    if knowledge_items:
        print(f"Found {len(knowledge_items)} knowledge items:")
        for i, item in enumerate(knowledge_items):
            print(f"{i+1}. Type: {item.get('type', 'Unknown')}")
            print(f"   Content: {item.get('content', 'No content')[:100]}...")
            print()
        
        return knowledge_items
    else:
        print("❌ No knowledge items found!")
        return []

def test_rag_query():
    """Test RAG query processing"""
    print("\n=== TESTING RAG QUERY ===")
    
    from concierge.utils.ai_helpers import get_relevant_context
    
    property_id = '614a339c-8bd2-4f97-9f62-6a6f7a013bf0'
    query = "What is the WiFi password?"
    
    print(f"Testing RAG query: '{query}'")
    print(f"Property ID: {property_id}")
    
    rag_results = get_relevant_context(query, property_id)
    
    print(f"RAG results:")
    pprint(rag_results)
    
    return rag_results

def test_ai_processing():
    """Test full AI processing pipeline"""
    print("\n=== TESTING AI PROCESSING ===")
    
    from concierge.utils.ai_helpers import process_query_with_rag
    
    property_id = '614a339c-8bd2-4f97-9f62-6a6f7a013bf0'
    query = "What is the WiFi password?"
    
    # Get property context
    property_context = test_property_context()
    
    # Create a simple system prompt
    system_prompt = """You are a helpful property assistant for Eastside Best Day Townhouse in Milwaukee, Wisconsin. 
You help guests with information about the property, amenities, WiFi, location, and house rules.
Be friendly and provide specific, helpful information about the property.

PROPERTY INFORMATION:
- Name: Eastside Best Day Townhouse
- Location: Milwaukee, Wisconsin, United States
- WiFi Network: cvnghjjdth
- WiFi Password: dgjghgjtjg%^897y
"""
    
    print(f"Testing AI processing with:")
    print(f"- Query: '{query}'")
    print(f"- Property ID: {property_id}")
    print(f"- System prompt length: {len(system_prompt)}")
    print(f"- Property context available: {bool(property_context)}")
    
    try:
        result = process_query_with_rag(
            query,
            property_id,
            property_context,
            conversation_history=[],
            system_prompt=system_prompt
        )
        
        print(f"\n✅ AI Response:")
        print(f"Response: {result.get('response', 'No response')}")
        print(f"Has context: {result.get('has_context', False)}")
        print(f"Context used: {len(result.get('context_used', []))} items")
        
        return result
        
    except Exception as e:
        print(f"❌ AI processing failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🔍 DEBUGGING SYSTEM PROMPT AND AI PROCESSING")
    print("=" * 50)
    
    # Test each component
    property_data = test_property_context()
    knowledge_items = test_knowledge_items()
    rag_results = test_rag_query()
    ai_result = test_ai_processing()
    
    print("\n" + "=" * 50)
    print("📋 SUMMARY:")
    print(f"✅ Property data: {'Found' if property_data else 'Missing'}")
    print(f"✅ Knowledge items: {len(knowledge_items) if knowledge_items else 0} found")
    print(f"✅ RAG results: {'Working' if rag_results and rag_results.get('found') else 'Not working'}")
    print(f"✅ AI processing: {'Working' if ai_result and ai_result.get('response') else 'Not working'}") 