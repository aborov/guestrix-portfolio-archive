#!/usr/bin/env python3
"""
Debug script to check what's in the DynamoDB table
"""

import boto3
from boto3.dynamodb.conditions import Key, Attr
from utils.dynamodb_client import get_conversations_table

def debug_table():
    """Debug the DynamoDB table contents"""
    print("Debugging DynamoDB Table Contents")
    print("=" * 50)
    
    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            print("❌ Could not get conversations table")
            return
        
        print("✅ Got conversations table")
        
        # Scan for all VOICE_CALL_DIAGNOSTICS records
        print("\n1. Scanning for VOICE_CALL_DIAGNOSTICS records...")
        response = conversations_table.scan(
            FilterExpression=Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
            Limit=10
        )
        
        items = response.get('Items', [])
        print(f"Found {len(items)} VOICE_CALL_DIAGNOSTICS records")
        
        for i, item in enumerate(items):
            print(f"\nRecord {i+1}:")
            print(f"  PK: {item.get('PK')}")
            print(f"  SK: {item.get('SK')}")
            print(f"  SessionId: {item.get('SessionId')}")
            print(f"  EntityType: {item.get('EntityType')}")
            print(f"  Status: {item.get('Status')}")
            print(f"  PropertyId: {item.get('PropertyId')}")
            print(f"  UserId: {item.get('UserId')}")
            print(f"  StartTime: {item.get('StartTime')}")
        
        # Scan for all VOICE_CALL_MINIMAL records
        print("\n2. Scanning for VOICE_CALL_MINIMAL records...")
        response = conversations_table.scan(
            FilterExpression=Attr('EntityType').eq('VOICE_CALL_MINIMAL'),
            Limit=10
        )
        
        items = response.get('Items', [])
        print(f"Found {len(items)} VOICE_CALL_MINIMAL records")
        
        for i, item in enumerate(items):
            print(f"\nMinimal Record {i+1}:")
            print(f"  PK: {item.get('PK')}")
            print(f"  SK: {item.get('SK')}")
            print(f"  SessionId: {item.get('SessionId')}")
            print(f"  EntityType: {item.get('EntityType')}")
            print(f"  Status: {item.get('Status')}")
            print(f"  Note: {item.get('Note')}")
        
        # Test a specific session ID search
        print("\n3. Testing session ID search...")
        test_session_id = input("Enter a session ID to search for (or press Enter to skip): ").strip()
        
        if test_session_id:
            response = conversations_table.scan(
                FilterExpression=Attr('SessionId').eq(test_session_id),
                Limit=10
            )
            
            items = response.get('Items', [])
            print(f"Found {len(items)} records for session {test_session_id}")
            
            for i, item in enumerate(items):
                print(f"\nSession Record {i+1}:")
                print(f"  PK: {item.get('PK')}")
                print(f"  SK: {item.get('SK')}")
                print(f"  SessionId: {item.get('SessionId')}")
                print(f"  EntityType: {item.get('EntityType')}")
                print(f"  Status: {item.get('Status')}")
        
    except Exception as e:
        print(f"❌ Error debugging table: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_table()
