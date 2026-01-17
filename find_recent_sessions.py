#!/usr/bin/env python3
"""
Script to find recent voice call sessions from DynamoDB
"""

import sys
import os
sys.path.append('/Users/aborov/Workspace/concierge/concierge')

from concierge.utils.dynamodb_client import get_conversations_table
from boto3.dynamodb.conditions import Attr
from datetime import datetime, timezone, timedelta
import json

def find_recent_voice_sessions():
    """Find recent voice call sessions"""
    print("🔍 Finding Recent Voice Call Sessions...")
    
    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            print("❌ Could not access conversations table")
            return False
        
        # Look for voice call diagnostics sessions from the last hour
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
        cutoff_time_str = cutoff_time.isoformat()
        
        print(f"   Looking for sessions created after: {cutoff_time_str}")
        
        # Scan for recent voice call diagnostics sessions
        response = conversations_table.scan(
            FilterExpression=Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS') & 
                           Attr('StartTime').gt(cutoff_time_str),
            Limit=10
        )
        
        sessions = response.get('Items', [])
        print(f"   Found {len(sessions)} recent voice call sessions")
        
        if not sessions:
            print("   No recent sessions found")
            return True
        
        # Sort by start time (most recent first)
        sessions.sort(key=lambda x: x.get('StartTime', ''), reverse=True)
        
        print("\n📋 Recent Voice Call Sessions:")
        for i, session in enumerate(sessions):
            session_id = session.get('SessionId', 'N/A')
            start_time = session.get('StartTime', 'N/A')
            end_time = session.get('EndTime', 'N/A')
            status = session.get('Status', 'N/A')
            guest_name = session.get('GuestName', 'N/A')
            transcripts = session.get('Transcripts', [])
            events = session.get('EventTimeline', [])
            
            print(f"\n   {i+1}. Session: {session_id}")
            print(f"      Guest: {guest_name}")
            print(f"      Status: {status}")
            print(f"      Started: {start_time}")
            print(f"      Ended: {end_time}")
            print(f"      Transcripts: {len(transcripts)}")
            print(f"      Events: {len(events)}")
            
            if transcripts:
                print(f"      Sample transcripts:")
                for j, transcript in enumerate(transcripts[:3]):
                    role = transcript.get('role', 'unknown')
                    text = transcript.get('text', '')[:50] + ('...' if len(transcript.get('text', '')) > 50 else '')
                    timestamp = transcript.get('timestamp', 'N/A')
                    speaker = "👤 Guest" if role == "user" else "🤖 Assistant"
                    print(f"        {j+1}. {speaker}: {text}")
        
        # Return the most recent session ID for detailed analysis
        if sessions:
            most_recent_session_id = sessions[0].get('SessionId')
            print(f"\n🎯 Most recent session ID: {most_recent_session_id}")
            return most_recent_session_id
        
        return True
        
    except Exception as e:
        print(f"❌ Error finding recent sessions: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = find_recent_voice_sessions()
    if isinstance(result, str):
        # Return the session ID
        print(f"\nSession ID: {result}")
    sys.exit(0 if result else 1)
