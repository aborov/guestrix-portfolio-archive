#!/usr/bin/env python3
"""
Debug script to check what's actually stored in DynamoDB for transcript storage
"""

import sys
import os
sys.path.append('/Users/aborov/Workspace/concierge/concierge')

from concierge.utils.dynamodb_client import get_voice_call_diagnostics, store_voice_call_transcript, create_voice_call_diagnostics_session
import json

def debug_transcript_storage():
    """Debug the transcript storage system"""
    print("🔍 Debugging Voice Call Transcript Storage...")
    
    # Create a test session
    session_id = "debug-session-12345"
    print(f"\n1. Creating test session: {session_id}")
    
    success = create_voice_call_diagnostics_session(
        session_id=session_id,
        property_id="eb0b5b41-34fc-4408-9f6a-cca3a243ce67",
        user_id="debug-user",
        guest_name="Debug User",
        client_diagnostics={"browser": "Debug Browser"},
        network_quality={"latency": 5}
    )
    
    if success:
        print("✅ Test session created successfully")
    else:
        print("❌ Failed to create test session")
        return False
    
    # Store a test transcript
    print("\n2. Storing test transcript...")
    transcript_success = store_voice_call_transcript(
        session_id=session_id,
        role="user",
        text="This is a test transcript message",
        timestamp="2025-08-05T19:00:00.000Z"
    )
    
    if transcript_success:
        print("✅ Test transcript stored successfully")
    else:
        print("❌ Failed to store test transcript")
        return False
    
    # Retrieve the session data
    print("\n3. Retrieving session data...")
    session_data = get_voice_call_diagnostics(session_id)
    
    if session_data:
        print("✅ Session data retrieved successfully")
        print(f"   - Session ID: {session_data.get('SessionId', 'N/A')}")
        print(f"   - Property ID: {session_data.get('PropertyId', 'N/A')}")
        print(f"   - User ID: {session_data.get('UserId', 'N/A')}")
        print(f"   - Status: {session_data.get('Status', 'N/A')}")
        
        # Check for transcripts
        transcripts = session_data.get('Transcripts', [])
        print(f"   - Transcripts found: {len(transcripts)}")
        
        if transcripts:
            print("   - Transcript details:")
            for i, transcript in enumerate(transcripts):
                print(f"     {i+1}. Role: {transcript.get('role', 'N/A')}")
                print(f"        Text: {transcript.get('text', 'N/A')}")
                print(f"        Timestamp: {transcript.get('timestamp', 'N/A')}")
        else:
            print("   ⚠️  No transcripts found in session data")
            
        # Show all keys in the session data
        print(f"\n   - All keys in session data: {list(session_data.keys())}")
        
        # Show raw data structure (first 500 chars)
        raw_data = json.dumps(session_data, indent=2, default=str)
        print(f"\n   - Raw data structure (first 500 chars):")
        print(raw_data[:500] + "..." if len(raw_data) > 500 else raw_data)
        
    else:
        print("❌ Failed to retrieve session data")
        return False
    
    return True

if __name__ == "__main__":
    success = debug_transcript_storage()
    sys.exit(0 if success else 1)
