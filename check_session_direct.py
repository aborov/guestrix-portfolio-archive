#!/usr/bin/env python3
"""
Direct check for voice call session in DynamoDB
"""

import sys
import os
sys.path.append('/Users/aborov/Workspace/concierge/concierge')

import boto3
from boto3.dynamodb.conditions import Attr
import json

def check_session_direct():
    """Check for the session directly in DynamoDB"""
    print("🔍 Checking DynamoDB directly for voice call sessions...")
    
    try:
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
        table = dynamodb.Table('Conversations')
        
        print(f"   Table: {table.table_name}")
        print(f"   Region: us-east-2")
        
        # First check for the specific session we just created
        pk = 'PROPERTY#eb0b5b41-34fc-4408-9f6a-cca3a243ce67'
        sk = 'VOICE_DIAGNOSTICS#test-debug-session-4'

        print(f"   Looking for specific session: PK={pk}, SK={sk}")

        try:
            response = table.get_item(Key={'PK': pk, 'SK': sk})
            if 'Item' in response:
                item = response['Item']
                print('✅ Specific session found!')
                print(f'   Session ID: {item.get("SessionId", "N/A")}')
                print(f'   Entity Type: {item.get("EntityType", "N/A")}')
                print(f'   Status: {item.get("Status", "N/A")}')
                print(f'   Transcripts: {len(item.get("Transcripts", []))}')
            else:
                print('❌ Specific session not found with direct key lookup')
        except Exception as e:
            print(f'❌ Error looking up specific session: {e}')

        # Scan for any voice call diagnostics sessions
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
            Limit=10
        )
        
        sessions = response.get('Items', [])
        print(f"   Found {len(sessions)} voice call diagnostics sessions")
        
        if sessions:
            print("\n📋 Voice Call Sessions Found:")
            for i, session in enumerate(sessions):
                session_id = session.get('SessionId', 'N/A')
                start_time = session.get('StartTime', 'N/A')
                status = session.get('Status', 'N/A')
                property_id = session.get('PropertyId', 'N/A')
                transcripts = session.get('Transcripts', [])
                
                print(f"\n   {i+1}. Session ID: {session_id}")
                print(f"      Property: {property_id}")
                print(f"      Status: {status}")
                print(f"      Start Time: {start_time}")
                print(f"      Transcripts: {len(transcripts)}")
                
                # Show keys
                print(f"      Keys: {list(session.keys())}")
        else:
            print("   No voice call diagnostics sessions found")
            
        # Also check for any recent items at all
        print(f"\n🔍 Checking for any recent items in the table...")
        response = table.scan(Limit=5)
        items = response.get('Items', [])
        print(f"   Found {len(items)} total items in table")
        
        if items:
            print("   Recent items:")
            for i, item in enumerate(items):
                entity_type = item.get('EntityType', 'N/A')
                pk = item.get('PK', 'N/A')
                sk = item.get('SK', 'N/A')
                print(f"     {i+1}. {entity_type} - PK: {pk[:50]}... SK: {sk[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking DynamoDB: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = check_session_direct()
    sys.exit(0 if success else 1)
