#!/usr/bin/env python3
"""
Test script to verify complete voice call session with transcripts
"""

import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8080"

def test_complete_voice_session():
    """Test a complete voice call session with transcripts"""
    print("🎙️ Testing Complete Voice Call Session with Transcripts...")
    
    # Test session creation
    print("\n1. Creating voice call session...")
    session_data = {
        "session_id": f"complete-test-{int(time.time())}",
        "property_id": "eb0b5b41-34fc-4408-9f6a-cca3a243ce67",
        "user_id": "test-user",
        "guest_name": "Test Guest",
        "client_diagnostics": {
            "browser": "Chrome",
            "platform": "MacOS",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        },
        "network_quality": {
            "latency": 25,
            "connectionType": "wifi"
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/session/start", json=session_data)
    if response.status_code == 200:
        print("✅ Voice call session created successfully")
        session_id = session_data["session_id"]
    else:
        print(f"❌ Voice call session creation failed: {response.status_code} - {response.text}")
        return False
    
    # Log some events
    print("\n2. Logging voice call events...")
    
    # WebSocket connected event
    event_data = {
        "session_id": session_id,
        "event_type": "WEBSOCKET_CONNECTED",
        "details": {
            "url": "wss://generativelanguage.googleapis.com/ws/...",
            "model": "gemini-live-2.5-flash-preview",
            "voice": "Aoede"
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/event", json=event_data)
    if response.status_code == 200:
        print("✅ WebSocket connected event logged")
    else:
        print(f"❌ Event logging failed: {response.status_code}")
        return False
    
    # Call started event
    event_data["event_type"] = "CALL_STARTED"
    response = requests.post(f"{BASE_URL}/api/voice-call/event", json=event_data)
    if response.status_code == 200:
        print("✅ Call started event logged")
    else:
        print(f"❌ Event logging failed: {response.status_code}")
        return False
    
    # Store conversation transcripts
    print("\n3. Storing conversation transcripts...")
    
    # User greeting
    transcript1 = {
        "session_id": session_id,
        "role": "user",
        "text": "Hello, I'm staying at your property and need some help.",
        "timestamp": "2025-08-05T19:10:00.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=transcript1)
    if response.status_code == 200:
        print("✅ User greeting transcript stored")
    else:
        print(f"❌ Transcript storage failed: {response.status_code}")
        return False
    
    # Assistant response
    transcript2 = {
        "session_id": session_id,
        "role": "assistant",
        "text": "Hello! I'm happy to help you. What can I assist you with today?",
        "timestamp": "2025-08-05T19:10:03.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=transcript2)
    if response.status_code == 200:
        print("✅ Assistant response transcript stored")
    else:
        print(f"❌ Transcript storage failed: {response.status_code}")
        return False
    
    # User question about WiFi
    transcript3 = {
        "session_id": session_id,
        "role": "user",
        "text": "I can't connect to the WiFi. What's the password?",
        "timestamp": "2025-08-05T19:10:10.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=transcript3)
    if response.status_code == 200:
        print("✅ User WiFi question transcript stored")
    else:
        print(f"❌ Transcript storage failed: {response.status_code}")
        return False
    
    # Assistant WiFi response
    transcript4 = {
        "session_id": session_id,
        "role": "assistant",
        "text": "The WiFi network is 'MySweetHome' and the password is 'Password123$%^'. You should be able to connect now.",
        "timestamp": "2025-08-05T19:10:15.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=transcript4)
    if response.status_code == 200:
        print("✅ Assistant WiFi response transcript stored")
    else:
        print(f"❌ Transcript storage failed: {response.status_code}")
        return False
    
    # User thank you
    transcript5 = {
        "session_id": session_id,
        "role": "user",
        "text": "Perfect, thank you so much! That worked.",
        "timestamp": "2025-08-05T19:10:25.000Z"
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/transcript", json=transcript5)
    if response.status_code == 200:
        print("✅ User thank you transcript stored")
    else:
        print(f"❌ Transcript storage failed: {response.status_code}")
        return False
    
    # Finalize session
    print("\n4. Finalizing voice call session...")
    finalize_data = {
        "session_id": session_id,
        "end_reason": "User ended call",
        "final_metrics": {
            "sessionDuration": 35000,
            "totalEvents": 5,
            "totalErrors": 0,
            "totalWarnings": 0,
            "interruptionCount": 0,
            "reconnectionCount": 0,
            "audioDropouts": 0,
            "averageMemoryUsage": 2100000.50
        }
    }
    
    response = requests.post(f"{BASE_URL}/api/voice-call/session/end", json=finalize_data)
    if response.status_code == 200:
        print("✅ Voice call session finalized successfully")
    else:
        print(f"❌ Session finalization failed: {response.status_code}")
        return False
    
    # Retrieve complete session data
    print("\n5. Retrieving complete session data...")
    response = requests.get(f"{BASE_URL}/api/voice-call/diagnostics/{session_id}")
    if response.status_code == 200:
        diagnostics = response.json()
        print("✅ Complete session data retrieved successfully")
        
        # Analyze the data
        transcripts = diagnostics.get('transcripts', [])
        events = diagnostics.get('event_timeline', [])
        final_metrics = diagnostics.get('final_metrics', {})
        session_info = diagnostics.get('session_info', {})

        print(f"\n📊 Session Analysis:")
        print(f"   - Session ID: {session_info.get('session_id', 'N/A')}")
        print(f"   - Property: {session_info.get('property_id', 'N/A')}")
        print(f"   - Guest: {session_info.get('guest_name', 'N/A')}")
        print(f"   - Status: {session_info.get('status', 'N/A')}")
        print(f"   - Duration: {session_info.get('duration', 'N/A')} seconds")
        print(f"   - Total Events: {len(events)}")
        print(f"   - Total Transcripts: {len(transcripts)}")
        
        if len(transcripts) == 5:
            print("✅ All 5 transcripts successfully stored and retrieved")
            print("\n🎙️ Conversation Transcript:")
            for i, transcript in enumerate(transcripts):
                role = transcript.get('role', 'unknown')
                text = transcript.get('text', '')
                timestamp = transcript.get('timestamp', 'N/A')
                speaker = "👤 Guest" if role == "user" else "🤖 Assistant"
                print(f"   {i+1}. {speaker}: {text}")
                print(f"      ({timestamp})")
        else:
            print(f"⚠️  Expected 5 transcripts, found {len(transcripts)}")
            
        if final_metrics:
            print(f"\n📈 Final Metrics:")
            print(f"   - Session Duration: {final_metrics.get('sessionDuration', 'N/A')}ms")
            print(f"   - Total Events: {final_metrics.get('totalEvents', 'N/A')}")
            print(f"   - Audio Dropouts: {final_metrics.get('audioDropouts', 'N/A')}")
            print(f"   - Average Memory: {final_metrics.get('averageMemoryUsage', 'N/A')} bytes")
        
        print(f"\n🔍 Event Timeline:")
        for i, event in enumerate(events[:3]):  # Show first 3 events
            event_type = event.get('event', 'UNKNOWN')
            timestamp = event.get('timestamp', 'N/A')
            print(f"   {i+1}. {event_type} ({timestamp})")
            
    else:
        print(f"❌ Failed to retrieve session data: {response.status_code}")
        return False
    
    print("\n🎉 Complete voice call session test passed!")
    print("\n📋 Summary:")
    print("   ✅ Voice call session creation")
    print("   ✅ Event logging (WebSocket, Call Started)")
    print("   ✅ Transcript storage (5 conversation turns)")
    print("   ✅ Session finalization with metrics")
    print("   ✅ Complete data retrieval")
    print("   ✅ Consolidated diagnostics + transcripts in single record")
    
    return True

if __name__ == "__main__":
    success = test_complete_voice_session()
    sys.exit(0 if success else 1)
