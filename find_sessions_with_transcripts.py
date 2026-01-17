#!/usr/bin/env python3
"""
Find voice call sessions that have transcripts
"""

import sys
import os
sys.path.append('/Users/aborov/Workspace/concierge/concierge')

import boto3
from boto3.dynamodb.conditions import Attr
import json

def find_sessions_with_transcripts():
    """Find voice call sessions that have transcripts"""
    print("🔍 Looking for voice call sessions with transcripts...")
    
    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
        table = dynamodb.Table('Conversations')
        
        print(f"   Table: {table.table_name}")
        print(f"   Region: us-east-2")
        
        # Scan for voice call diagnostics sessions
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
            Limit=50
        )
        
        sessions = response.get('Items', [])
        print(f"   Found {len(sessions)} voice call diagnostics sessions")
        
        if not sessions:
            print("   No voice call diagnostics sessions found")
            return None
        
        # Filter sessions that have transcripts
        sessions_with_transcripts = []
        for session in sessions:
            transcripts = session.get('Transcripts', [])
            if transcripts:
                sessions_with_transcripts.append(session)
        
        print(f"   Found {len(sessions_with_transcripts)} sessions with transcripts")
        
        if sessions_with_transcripts:
            # Sort by start time (most recent first)
            sessions_with_transcripts.sort(key=lambda x: x.get('StartTime', ''), reverse=True)
            
            print("\n📋 Sessions with Transcripts:")
            for i, session in enumerate(sessions_with_transcripts):
                session_id = session.get('SessionId', 'N/A')
                start_time = session.get('StartTime', 'N/A')
                end_time = session.get('EndTime', 'N/A')
                guest_name = session.get('GuestName', 'N/A')
                status = session.get('Status', 'N/A')
                transcripts = session.get('Transcripts', [])
                
                print(f"\n   {i+1}. Session ID: {session_id}")
                print(f"      Guest: {guest_name}")
                print(f"      Status: {status}")
                print(f"      Transcripts: {len(transcripts)}")
                print(f"      Started: {start_time}")
                print(f"      Ended: {end_time}")
                
                # Show first few transcripts
                if transcripts:
                    print(f"      Sample transcripts:")
                    for j, transcript in enumerate(transcripts[:3]):
                        role = transcript.get('role', 'unknown')
                        text = transcript.get('text', '')[:50] + ('...' if len(transcript.get('text', '')) > 50 else '')
                        timestamp = transcript.get('timestamp', 'N/A')
                        speaker = "👤 Guest" if role == "user" else "🤖 Assistant"
                        print(f"        {j+1}. {speaker}: {text}")
            
            # Return the most recent session with transcripts
            most_recent = sessions_with_transcripts[0].get('SessionId')
            return most_recent
        else:
            print("   No sessions with transcripts found")
            return None
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    session_id = find_sessions_with_transcripts()
    if session_id:
        print(f"\n🎯 Most recent session with transcripts: {session_id}")
    else:
        print("\n❌ No sessions with transcripts found")
    sys.exit(0 if session_id else 1)
