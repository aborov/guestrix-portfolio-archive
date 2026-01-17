#!/usr/bin/env python3
"""
Test script to verify voice call diagnostics system works end-to-end
"""

import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8080"

def test_voice_diagnostics():
    """Test the complete voice call diagnostics flow"""
    print("🧪 Testing Voice Call Diagnostics System...")
    
    # Test session creation
    print("\n1. Testing session creation...")
    session_data = {
        "session_id": f"test-{int(time.time())}",
        "property_id": "eb0b5b41-34fc-4408-9f6a-cca3a243ce67",
        "user_id": "test-user"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/session/start", json=session_data)
    if response.status_code == 200:
        print("✅ Session creation successful")
    else:
        print(f"❌ Session creation failed: {response.status_code} - {response.text}")
        return False
    
    # Test event logging
    print("\n2. Testing event logging...")
    event_data = {
        "session_id": session_data["session_id"],
        "event_type": "CALL_STARTED",
        "details": {
            "model": "gemini-live-2.5-flash-preview",
            "voice": "Aoede",
            "language": "en-US"
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/event", json=event_data)
    if response.status_code == 200:
        print("✅ Event logging successful")
    else:
        print(f"❌ Event logging failed: {response.status_code} - {response.text}")
        return False
    
    # Test session finalization with float metrics
    print("\n3. Testing session finalization with float metrics...")
    finalize_data = {
        "session_id": session_data["session_id"],
        "end_reason": "User ended call",
        "final_metrics": {
            "sessionDuration": 15000,
            "totalEvents": 5,
            "totalErrors": 0,
            "totalWarnings": 1,
            "averageMemoryUsage": 1234567.89,  # This is a float that should be converted
            "interruptionCount": 2,
            "reconnectionCount": 0,
            "audioDropouts": 1,
            "networkLatency": 45.67  # Another float
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/session/end", json=finalize_data)
    if response.status_code == 200:
        print("✅ Session finalization successful")
        print("✅ Float to Decimal conversion working properly")
    else:
        print(f"❌ Session finalization failed: {response.status_code} - {response.text}")
        return False
    
    # Test diagnostics retrieval
    print("\n4. Testing diagnostics retrieval...")
    response = requests.get(f"{BASE_URL}/api/voice-call/diagnostics/{session_data['session_id']}")
    if response.status_code == 200:
        diagnostics = response.json()
        print("✅ Diagnostics retrieval successful")
        print(f"   - Session ID: {diagnostics.get('SessionId', 'N/A')}")
        print(f"   - Status: {diagnostics.get('Status', 'N/A')}")
        print(f"   - Events: {len(diagnostics.get('EventTimeline', []))}")
        print(f"   - Final Metrics: {bool(diagnostics.get('FinalMetrics'))}")
    else:
        print(f"❌ Diagnostics retrieval failed: {response.status_code} - {response.text}")
        return False
    
    print("\n🎉 All tests passed! Voice call diagnostics system is working properly.")
    return True

if __name__ == "__main__":
    success = test_voice_diagnostics()
    sys.exit(0 if success else 1)
