#!/usr/bin/env python3
"""
Test the scan functionality directly
"""

from utils.dynamodb_client import get_conversations_table
from boto3.dynamodb.conditions import Attr

def test_scan():
    """Test scanning for a specific session"""
    session_id = "2eb94a8b-2620-4bf5-8b64-f262c2e16091"
    
    print(f"Testing scan for session: {session_id}")
    
    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            print("❌ Could not get conversations table")
            return
        
        print("✅ Got conversations table")
        
        # Test the exact same scan logic used in our functions
        print("Trying scan with limit=1...")
        response = conversations_table.scan(
            FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
            Limit=1
        )

        print(f"Scan response (limited): Count={response.get('Count')}, ScannedCount={response.get('ScannedCount')}")

        items = response.get('Items', [])
        print(f"Found {len(items)} items with limit=1")

        if not items:
            print("Trying scan without limit...")
            response = conversations_table.scan(
                FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS')
            )

            print(f"Scan response (no limit): Count={response.get('Count')}, ScannedCount={response.get('ScannedCount')}")
            items = response.get('Items', [])
            print(f"Found {len(items)} items without limit")
        
        if items:
            item = items[0]
            print(f"Found item:")
            print(f"  PK: {item['PK']}")
            print(f"  SK: {item['SK']}")
            print(f"  SessionId: {item.get('SessionId')}")
            print(f"  EntityType: {item.get('EntityType')}")
            return True
        else:
            print("❌ No items found")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_scan()
