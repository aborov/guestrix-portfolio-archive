#!/usr/bin/env python3
"""
Script to analyze specific conversations from August 2nd that match the problematic conversation criteria.
"""

import os
import sys
import boto3
import argparse
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr
from typing import Dict, List, Optional
import json

def setup_dynamodb():
    """Initialize DynamoDB connection."""
    try:
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb')
        
        # Get table name from environment or use default
        table_name = os.environ.get('CONVERSATIONS_TABLE_NAME', 'Conversations')
        table = dynamodb.Table(table_name)
        
        print(f"✓ Connected to DynamoDB table: {table_name}")
        return table
    except Exception as e:
        print(f"✗ Error connecting to DynamoDB: {e}")
        return None

def get_conversation_details(conversation_id, property_id, table):
    """Get detailed information about a specific conversation."""
    print(f"\n🔍 DETAILED ANALYSIS FOR CONVERSATION")
    print(f"Conversation ID: {conversation_id}")
    print(f"Property ID: {property_id}")
    print("=" * 80)
    
    try:
        # First, get the conversation session record
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                  Key('SK').begins_with("CONVERSATION#"),
            FilterExpression=Attr('ConversationId').eq(conversation_id)
        )
        
        session_records = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                      Key('SK').begins_with("CONVERSATION#"),
                FilterExpression=Attr('ConversationId').eq(conversation_id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            session_records.extend(response.get('Items', []))
        
        if session_records:
            session_record = session_records[0]
            print(f"📋 CONVERSATION SESSION DETAILS:")
            print(f"  Property ID: {session_record.get('PropertyId', 'Unknown')}")
            print(f"  User ID: {session_record.get('UserId', 'Unknown')}")
            print(f"  Guest Name: {session_record.get('GuestName', 'Unknown')}")
            print(f"  Channel: {session_record.get('Channel', 'Unknown')}")
            print(f"  Start Time: {session_record.get('StartTime', 'Unknown')}")
            print(f"  Last Update: {session_record.get('LastUpdateTime', 'Unknown')}")
            print(f"  Message Count: {session_record.get('MessageCount', 0)}")
            print(f"  Reservation ID: {session_record.get('ReservationId', 'None')}")
            print(f"  Phone: {session_record.get('GuestPhone', 'None')}")
            print()
        
        # Now get all individual messages for this conversation
        print(f"💬 INDIVIDUAL MESSAGES:")
        print("-" * 80)
        
        # Query for all messages with this conversation ID
        messages_response = table.scan(
            FilterExpression=Attr('ConversationId').eq(conversation_id)
        )
        
        messages = messages_response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in messages_response:
            messages_response = table.scan(
                FilterExpression=Attr('ConversationId').eq(conversation_id),
                ExclusiveStartKey=messages_response['LastEvaluatedKey']
            )
            messages.extend(messages_response.get('Items', []))
        
        # Sort messages by timestamp
        messages.sort(key=lambda x: x.get('Timestamp', ''))
        
        print(f"Found {len(messages)} individual messages")
        print()
        
        for i, message in enumerate(messages, 1):
            timestamp = message.get('Timestamp', 'N/A')
            role = message.get('Role', 'Unknown')
            text = message.get('Text', 'No text')
            session_id = message.get('SessionId', 'Unknown')
            channel = message.get('Channel', 'Unknown')
            
            print(f"{i:2d}. [{timestamp}] {role.upper()}")
            print(f"     Session: {session_id}")
            print(f"     Channel: {channel}")
            print(f"     Text: {text}")
            
            # Show context used for assistant messages
            if role == 'assistant' and message.get('ContextUsed'):
                context_used = message.get('ContextUsed')
                print(f"     Context Used: {len(context_used)} items")
                for j, context_item in enumerate(context_used[:3], 1):  # Show first 3 items
                    print(f"       {j}. {context_item.get('content', 'No content')[:100]}...")
                if len(context_used) > 3:
                    print(f"       ... and {len(context_used) - 3} more items")
            
            print()
        
        return {
            'session_record': session_record if session_records else None,
            'messages': messages
        }
        
    except Exception as e:
        print(f"✗ Error analyzing conversation: {e}")
        return None

def analyze_problematic_conversations():
    """Analyze the specific conversations that match the problematic criteria."""
    table = setup_dynamodb()
    if not table:
        sys.exit(1)
    
    # The conversations that match the 3 PM Chicago time criteria
    target_conversations = [
        {
            'id': 'de1305d6-d3f3-4023-84df-e16168f9fcdc',
            'property_id': 'c2d26719-5654-45ee-aa2c-8fbafa637fb4',
            'user_id': 'yP3ZwJohaxU7No1mPPK1dFiuTIg1',
            'guest_name': 'Salma',
            'start_time': '2025-08-02 20:02:01 UTC',
            'message_count': 23
        },
        {
            'id': 'c85c69af-fdfc-4687-85a1-9e5fa37cfba4',
            'property_id': 'c2d26719-5654-45ee-aa2c-8fbafa637fb4',
            'user_id': 'yP3ZwJohaxU7No1mPPK1dFiuTIg1',
            'guest_name': 'Salma',
            'start_time': '2025-08-02 20:12:06 UTC',
            'message_count': 2
        },
        {
            'id': 'f4a74bcf-2bfa-4f62-906c-3b0b6dd8d913',
            'property_id': 'c2d26719-5654-45ee-aa2c-8fbafa637fb4',
            'user_id': 'yP3ZwJohaxU7No1mPPK1dFiuTIg1',
            'guest_name': 'Salma',
            'start_time': '2025-08-02 20:13:21 UTC',
            'message_count': 5
        }
    ]
    
    print("🎯 ANALYZING POTENTIALLY PROBLEMATIC CONVERSATIONS")
    print("=" * 80)
    print("These conversations match the criteria:")
    print("- August 2nd, 2025")
    print("- Around 3 PM Chicago time (8 PM UTC)")
    print("- Voice calls")
    print("- User from Pakistan")
    print()
    
    for conv in target_conversations:
        print(f"📞 CONVERSATION: {conv['id']}")
        print(f"   Property: {conv['property_id']}")
        print(f"   User: {conv['user_id']}")
        print(f"   Guest: {conv['guest_name']}")
        print(f"   Start Time: {conv['start_time']}")
        print(f"   Message Count: {conv['message_count']}")
        print()
        
        # Get detailed analysis
        details = get_conversation_details(conv['id'], conv['property_id'], table)
        
        if details and details['messages']:
            print(f"✅ Found {len(details['messages'])} messages in conversation")
        else:
            print(f"❌ No messages found for this conversation")
        
        print("\n" + "="*80 + "\n")

def main():
    """Main function."""
    analyze_problematic_conversations()

if __name__ == "__main__":
    main() 