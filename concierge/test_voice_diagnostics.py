#!/usr/bin/env python3
"""
Test script for voice call diagnostics system
"""

import json
import uuid
from datetime import datetime, timezone
from utils.dynamodb_client import (
    create_voice_call_diagnostics_session,
    log_voice_call_event,
    update_voice_call_metrics,
    update_voice_call_config,
    finalize_voice_call_session,
    get_voice_call_diagnostics
)

def test_voice_call_diagnostics():
    """Test the complete voice call diagnostics workflow"""
    print("Testing Voice Call Diagnostics System")
    print("=" * 50)
    
    # Test data
    session_id = str(uuid.uuid4())
    property_id = "test-property-123"
    user_id = "test-user-456"
    guest_name = "Test Guest"
    reservation_id = "test-reservation-789"
    
    client_diagnostics = {
        "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "browserName": "Chrome",
        "browserVersion": "120",
        "platform": "MacIntel",
        "language": "en-US",
        "mediaDevices": {"supported": True, "getUserMedia": True},
        "audioContext": {"supported": True},
        "webSocket": {"supported": True},
        "screen": {"width": 1920, "height": 1080},
        "memory": 8,
        "hardwareConcurrency": 8,
        "timezone": "America/New_York"
    }
    
    network_quality = {
        "latency": 45.2,
        "connectionType": "4g",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    print(f"1. Creating diagnostics session: {session_id}")
    
    # Test 1: Create diagnostics session
    success = create_voice_call_diagnostics_session(
        property_id=property_id,
        user_id=user_id,
        session_id=session_id,
        client_diagnostics=client_diagnostics,
        network_quality=network_quality,
        guest_name=guest_name,
        reservation_id=reservation_id
    )
    
    if success:
        print("✅ Session created successfully")
    else:
        print("❌ Failed to create session")
        return False
    
    print("\n2. Logging various voice call events")
    
    # Test 2: Log various events
    events_to_test = [
        ("SESSION_INITIALIZED", {"property_id": property_id, "user_id": user_id}, None, None),
        ("WEBSOCKET_CONNECTED", {"url": "wss://example.com", "model": "gemini-live-2.5"}, None, None),
        ("CALL_STARTED", {"voice": "Aoede", "language": "en-US"}, None, None),
        ("USER_INTERRUPTION", {"interruption_count": 1}, None, None),
        ("AUDIO_QUALITY_WARNING", {"silence_ratio": 0.85}, None, "High silence ratio detected"),
        ("WEBSOCKET_ERROR", {"error_type": "connection_error"}, {"message": "Connection failed"}, None),
        ("RECONNECTION_ATTEMPT", {"attempt_number": 1}, None, None),
        ("CALL_ENDING", {"reason": "user_ended_call"}, None, None)
    ]

    for event_type, details, error_info, warning_info in events_to_test:
        success = log_voice_call_event(
            session_id=session_id,
            event_type=event_type,
            details=details,
            error_info=error_info,
            warning_info={"message": warning_info} if warning_info else None
        )
        
        if success:
            print(f"✅ Logged event: {event_type}")
        else:
            print(f"❌ Failed to log event: {event_type}")
    
    print("\n3. Updating quality metrics")
    
    # Test 3: Update metrics
    metrics_update = {
        "QualityMetrics": {
            "ConnectionLatency": [45.2, 52.1, 38.9],
            "AudioDropouts": 2,
            "TranscriptionErrors": 1,
            "InterruptionCount": 3,
            "ReconnectionCount": 1,
            "AverageResponseTime": [1200, 1350, 980],
            "AudioQualityIssues": [
                {
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "silenceRatio": 0.85,
                    "energyLevel": 150.5,
                    "clippingDetected": False
                }
            ],
            "WebSocketEvents": [
                {
                    "timestamp": datetime.now(timezone.utc).timestamp(),
                    "readyState": 1,
                    "bufferedAmount": 0
                }
            ]
        }
    }
    
    success = update_voice_call_metrics(session_id, metrics_update)
    if success:
        print("✅ Metrics updated successfully")
    else:
        print("❌ Failed to update metrics")
    
    print("\n4. Updating technical configuration")
    
    # Test 4: Update config
    config_update = {
        "TechnicalConfig": {
            "GeminiModel": "gemini-live-2.5-flash-preview",
            "VoiceSettings": {"voice": "Aoede", "language": "en-US"},
            "AudioSettings": {"sampleRate": 16000, "bufferSize": 4096},
            "WebSocketUrl": "wss://generativelanguage.googleapis.com/ws/...",
            "ApiKeyType": "ephemeral"
        }
    }
    
    success = update_voice_call_config(session_id, config_update)
    if success:
        print("✅ Configuration updated successfully")
    else:
        print("❌ Failed to update configuration")
    
    print("\n5. Finalizing session")
    
    # Test 5: Finalize session
    final_metrics = {
        "total_events": 8,
        "total_errors": 1,
        "total_warnings": 1,
        "session_duration": 125000,  # 125 seconds
        "interruption_count": 3,
        "reconnection_count": 1,
        "audio_dropouts": 2
    }
    
    success = finalize_voice_call_session(session_id, "user_ended_call", final_metrics)
    if success:
        print("✅ Session finalized successfully")
    else:
        print("❌ Failed to finalize session")
    
    print("\n6. Retrieving diagnostics data")
    
    # Test 6: Retrieve diagnostics
    diagnostics_data = get_voice_call_diagnostics(session_id)
    if diagnostics_data:
        print("✅ Diagnostics data retrieved successfully")
        print(f"   - Session ID: {diagnostics_data.get('SessionId')}")
        print(f"   - Property ID: {diagnostics_data.get('PropertyId')}")
        print(f"   - Status: {diagnostics_data.get('Status')}")
        print(f"   - Duration: {diagnostics_data.get('Duration')} seconds")
        print(f"   - Events: {len(diagnostics_data.get('EventTimeline', []))}")
        print(f"   - Errors: {len(diagnostics_data.get('Errors', []))}")
        print(f"   - Warnings: {len(diagnostics_data.get('Warnings', []))}")
        
        # Print some sample events
        events = diagnostics_data.get('EventTimeline', [])
        if events:
            print(f"   - Sample events:")
            for event in events[:3]:  # Show first 3 events
                print(f"     * {event.get('timestamp')}: {event.get('event')}")
    else:
        print("❌ Failed to retrieve diagnostics data")
    
    print("\n" + "=" * 50)
    print("Voice Call Diagnostics Test Complete!")
    
    return True

if __name__ == "__main__":
    test_voice_call_diagnostics()
