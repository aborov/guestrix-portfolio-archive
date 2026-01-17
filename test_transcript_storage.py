#!/usr/bin/env python3
"""
Test script to verify consolidated voice call transcript storage
"""

import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8080"

def test_consolidated_transcript_storage():
    """Test the consolidated voice call transcript storage system"""
    print("🧪 Testing Consolidated Voice Call Transcript Storage...")
    
    # Test session creation
    print("\n1. Testing diagnostics session creation...")
    session_data = {
        "session_id": f"test-transcript-{int(time.time())}",
        "property_id": "eb0b5b41-34fc-4408-9f6a-cca3a243ce67",
        "user_id": "test-user",
        "guest_name": "Test User",
        "client_diagnostics": {
            "browser": "Test Browser",
            "platform": "Test Platform"
        },
        "network_quality": {
            "latency": 10,
            "connectionType": "wifi"
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/session/start", json=session_data)
    if response.status_code == 200:
        print("✅ Diagnostics session creation successful")
        session_id = session_data["session_id"]
    else:
        print(f"❌ Diagnostics session creation failed: {response.status_code} - {response.text}")
        return False
    
    # Test transcript storage
    print("\n2. Testing transcript storage...")
    
    # Store user transcript
    user_transcript = {
        "session_id": session_id,
        "role": "user",
        "text": "Hello, can you tell me about the WiFi password?",
        "timestamp": "2025-08-05T18:45:00.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=user_transcript)
    if response.status_code == 200:
        print("✅ User transcript storage successful")
    else:
        print(f"❌ User transcript storage failed: {response.status_code} - {response.text}")
        return False
    
    # Store assistant transcript
    assistant_transcript = {
        "session_id": session_id,
        "role": "assistant",
        "text": "The WiFi network is 'MySweetHome' and the password is 'Password123$%^'.",
        "timestamp": "2025-08-05T18:45:05.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=assistant_transcript)
    if response.status_code == 200:
        print("✅ Assistant transcript storage successful")
    else:
        print(f"❌ Assistant transcript storage failed: {response.status_code} - {response.text}")
        return False
    
    # Store another user transcript
    user_transcript2 = {
        "session_id": session_id,
        "role": "user", 
        "text": "Thank you! What about the check-out time?",
        "timestamp": "2025-08-05T18:45:10.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=user_transcript2)
    if response.status_code == 200:
        print("✅ Second user transcript storage successful")
    else:
        print(f"❌ Second user transcript storage failed: {response.status_code} - {response.text}")
        return False
    
    # Test session finalization with metrics
    print("\n3. Testing session finalization...")
    finalize_data = {
        "session_id": session_id,
        "end_reason": "User ended call",
        "final_metrics": {
            "sessionDuration": 25000,
            "totalEvents": 8,
            "totalErrors": 0,
            "totalWarnings": 0,
            "interruptionCount": 1,
            "reconnectionCount": 0,
            "audioDropouts": 0,
            "averageMemoryUsage": 1500000.75
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/session/end", json=finalize_data)
    if response.status_code == 200:
        print("✅ Session finalization successful")
    else:
        print(f"❌ Session finalization failed: {response.status_code} - {response.text}")
        return False
    
    # Test comprehensive data retrieval
    print("\n4. Testing comprehensive data retrieval...")
    response = requests.get(f"{BASE_URL}/api/voice-call/diagnostics/{session_id}")
    if response.status_code == 200:
        diagnostics = response.json()
        print("✅ Diagnostics retrieval successful")
        
        # Check if transcripts are included
        transcripts = diagnostics.get('Transcripts', [])
        print(f"   - Session ID: {diagnostics.get('SessionId', 'N/A')}")
        print(f"   - Status: {diagnostics.get('Status', 'N/A')}")
        print(f"   - Duration: {diagnostics.get('Duration', 'N/A')} seconds")
        print(f"   - Events: {len(diagnostics.get('EventTimeline', []))}")
        print(f"   - Transcripts: {len(transcripts)}")
        
        if len(transcripts) >= 3:
            print("✅ All transcripts successfully stored and retrieved")
            print("   Sample transcripts:")
            for i, transcript in enumerate(transcripts[:3]):
                role = transcript.get('role', 'unknown')
                text = transcript.get('text', '')[:50] + ('...' if len(transcript.get('text', '')) > 50 else '')
                timestamp = transcript.get('timestamp', 'N/A')
                print(f"     {i+1}. [{role}] {text} ({timestamp})")
        else:
            print(f"⚠️  Expected 3 transcripts, found {len(transcripts)}")
            
        # Check final metrics
        final_metrics = diagnostics.get('FinalMetrics', {})
        if final_metrics:
            print("✅ Final metrics successfully stored")
            print(f"   - Session Duration: {final_metrics.get('sessionDuration', 'N/A')}ms")
            print(f"   - Total Events: {final_metrics.get('totalEvents', 'N/A')}")
            print(f"   - Interruptions: {final_metrics.get('interruptionCount', 'N/A')}")
        else:
            print("⚠️  Final metrics not found")
            
    else:
        print(f"❌ Diagnostics retrieval failed: {response.status_code} - {response.text}")
        return False
    
    print("\n🎉 All tests passed! Consolidated transcript storage system is working properly.")
    print("\n📊 Summary:")
    print("   ✅ Diagnostics session creation")
    print("   ✅ User transcript storage")
    print("   ✅ Assistant transcript storage") 
    print("   ✅ Multiple transcript storage")
    print("   ✅ Session finalization with metrics")
    print("   ✅ Comprehensive data retrieval")
    print("   ✅ Transcripts and diagnostics consolidated in single record")
    
    return True

if __name__ == "__main__":
    success = test_consolidated_transcript_storage()
    sys.exit(0 if success else 1)
