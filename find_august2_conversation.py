#!/usr/bin/env python3
"""
Script to find the problematic conversation from August 2nd around 3 PM Chicago time.
The user was in Pakistan, so we need to account for timezone differences.
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

def get_august2_date_range():
    """Get the date range for August 2nd, 2025 with timezone considerations."""
    # August 2nd, 2025
    august2 = datetime(2025, 8, 2, tzinfo=timezone.utc)
    
    # Chicago is UTC-5 (CDT) or UTC-6 (CST) - using CDT for August
    # Pakistan is UTC+5
    # So 3 PM Chicago time = 8 PM Pakistan time = 8 PM UTC (since Pakistan is UTC+5)
    # But the user was in Pakistan, so the timestamp might be saved in Pakistan time
    
    # Create a wide range to account for timezone confusion
    # 3 PM Chicago = 8 PM UTC = 1 AM next day Pakistan time
    # But if saved in Pakistan time, it could be 3 PM Pakistan = 10 AM UTC
    
    # Let's search a wider range to be safe
    start_of_day = august2.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = august2.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    print(f"Searching for conversations on: {start_of_day.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Date range: {start_of_day.isoformat()} to {end_of_day.isoformat()}")
    print("Note: 3 PM Chicago time = 8 PM UTC = 1 AM next day Pakistan time")
    print("If saved in Pakistan time, 3 PM Pakistan = 10 AM UTC")
    
    return start_of_day, end_of_day

def scan_august2_conversations(table, start_date, end_date):
    """Scan for conversations on August 2nd."""
    print(f"\nScanning for conversations between {start_date.isoformat()} and {end_date.isoformat()}")
    
    conversations = []
    total_scanned = 0
    
    try:
        # Use scan with filter expression to find August 2nd conversations
        # Check multiple possible timestamp fields based on the schema
        filter_expression = None
        
        # Check for StartTime field (from create_conversation_session)
        start_time_filter = (Attr('StartTime').gte(start_date.isoformat()) & 
                           Attr('StartTime').lte(end_date.isoformat()))
        
        # Check for LastUpdateTime field
        update_time_filter = (Attr('LastUpdateTime').gte(start_date.isoformat()) & 
                            Attr('LastUpdateTime').lte(end_date.isoformat()))
        
        # Check for Timestamp field (from store_conversation_entry)
        timestamp_filter = (Attr('Timestamp').gte(start_date.isoformat()) & 
                          Attr('Timestamp').lte(end_date.isoformat()))
        
        # Combine filters with OR logic
        filter_expression = start_time_filter | update_time_filter | timestamp_filter
        
        # Also filter for conversation entities only
        entity_filter = Attr('EntityType').eq('CONVERSATION')
        final_filter = filter_expression & entity_filter
        
        # Perform scan
        response = table.scan(
            FilterExpression=final_filter,
            Select='ALL_ATTRIBUTES'
        )
        
        items = response.get('Items', [])
        total_scanned += len(items)
        conversations.extend(items)
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            print(f"Continuing scan... Found {len(conversations)} conversations so far")
            response = table.scan(
                FilterExpression=final_filter,
                Select='ALL_ATTRIBUTES',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items = response.get('Items', [])
            total_scanned += len(items)
            conversations.extend(items)
        
        print(f"Scan complete. Total items scanned: {total_scanned}")
        print(f"Conversations found on August 2nd: {len(conversations)}")
        
        return conversations
        
    except Exception as e:
        print(f"✗ Error scanning conversations: {e}")
        return []

def format_timestamp(timestamp_str):
    """Format timestamp for display."""
    if not timestamp_str:
        return "N/A"
    
    try:
        # Handle different timestamp formats
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str.replace('Z', '+00:00')
        
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except:
        return timestamp_str

def analyze_conversation_flow(conversation_id, property_id, table):
    """Analyze the complete flow of a conversation by getting all related messages."""
    print(f"\n🔍 ANALYZING CONVERSATION FLOW")
    print(f"Conversation ID: {conversation_id}")
    print(f"Property ID: {property_id}")
    print("=" * 60)
    
    try:
        # Query for all messages in this conversation
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                  Key('SK').begins_with(f"CONVERSATION#"),
            FilterExpression=Attr('ConversationId').eq(conversation_id)
        )
        
        messages = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                      Key('SK').begins_with(f"CONVERSATION#"),
                FilterExpression=Attr('ConversationId').eq(conversation_id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            messages.extend(response.get('Items', []))
        
        # Sort messages by timestamp
        messages.sort(key=lambda x: x.get('Timestamp', ''))
        
        print(f"Found {len(messages)} messages in conversation")
        print()
        
        # Display conversation flow
        for i, message in enumerate(messages, 1):
            timestamp = format_timestamp(message.get('Timestamp'))
            role = message.get('Role', 'Unknown')
            text = message.get('Text', 'No text')
            session_id = message.get('SessionId', 'Unknown')
            channel = message.get('Channel', 'Unknown')
            
            print(f"{i:2d}. [{timestamp}] {role.upper()}")
            print(f"     Session: {session_id}")
            print(f"     Channel: {channel}")
            print(f"     Text: {text[:200]}{'...' if len(text) > 200 else ''}")
            
            # Show context used for assistant messages
            if role == 'assistant' and message.get('ContextUsed'):
                context_used = message.get('ContextUsed')
                print(f"     Context Used: {len(context_used)} items")
            
            print()
        
        return messages
        
    except Exception as e:
        print(f"✗ Error analyzing conversation flow: {e}")
        return []

def display_conversations(conversations, table):
    """Display conversation details in a formatted way."""
    if not conversations:
        print("\n❌ No conversations found for August 2nd.")
        return
    
    print(f"\n📊 CONVERSATION SUMMARY FOR AUGUST 2ND")
    print("=" * 60)
    print(f"Total conversations: {len(conversations)}")
    
    # Group by property
    property_stats = {}
    user_stats = {}
    time_distribution = {}
    
    for conv in conversations:
        property_id = conv.get('PropertyId', 'Unknown')
        user_id = conv.get('UserId', 'Unknown')
        guest_name = conv.get('GuestName', 'Unknown')
        channel = conv.get('Channel', 'Unknown')
        start_time = conv.get('StartTime')
        last_update = conv.get('LastUpdateTime')
        conversation_id = conv.get('ConversationId', 'Unknown')
        reservation_id = conv.get('ReservationId', 'None')
        phone = conv.get('GuestPhone', 'None')
        
        # Property stats
        if property_id not in property_stats:
            property_stats[property_id] = {
                'count': 0,
                'users': set(),
                'channels': set(),
                'conversations': []
            }
        property_stats[property_id]['count'] += 1
        property_stats[property_id]['users'].add(user_id)
        property_stats[property_id]['channels'].add(channel)
        property_stats[property_id]['conversations'].append({
            'id': conversation_id,
            'user': user_id,
            'guest': guest_name,
            'channel': channel,
            'start_time': start_time,
            'reservation': reservation_id,
            'phone': phone
        })
        
        # User stats
        if user_id not in user_stats:
            user_stats[user_id] = {
                'count': 0,
                'properties': set(),
                'guests': set()
            }
        user_stats[user_id]['count'] += 1
        user_stats[user_id]['properties'].add(property_id)
        user_stats[user_id]['guests'].add(guest_name)
        
        # Time distribution (by hour)
        if start_time:
            try:
                if start_time.endswith('Z'):
                    start_time = start_time.replace('Z', '+00:00')
                dt = datetime.fromisoformat(start_time)
                hour = dt.hour
                if hour not in time_distribution:
                    time_distribution[hour] = 0
                time_distribution[hour] += 1
            except:
                pass
    
    # Display property summary
    print(f"\n🏠 PROPERTY BREAKDOWN:")
    print("-" * 40)
    for prop_id, stats in property_stats.items():
        print(f"Property: {prop_id}")
        print(f"  Conversations: {stats['count']}")
        print(f"  Unique users: {len(stats['users'])}")
        print(f"  Channels: {', '.join(stats['channels'])}")
        print()
    
    # Display user summary
    print(f"\n👥 USER BREAKDOWN:")
    print("-" * 40)
    for user_id, stats in user_stats.items():
        print(f"User: {user_id}")
        print(f"  Conversations: {stats['count']}")
        print(f"  Properties: {', '.join(stats['properties'])}")
        print(f"  Guest names: {', '.join(stats['guests'])}")
        print()
    
    # Display time distribution
    if time_distribution:
        print(f"\n⏰ TIME DISTRIBUTION (by hour UTC):")
        print("-" * 40)
        for hour in sorted(time_distribution.keys()):
            count = time_distribution[hour]
            # Convert UTC to Chicago time for reference
            chicago_hour = (hour - 5) % 24  # CDT is UTC-5
            print(f"  {hour:02d}:00 UTC ({chicago_hour:02d}:00 Chicago) - {count} conversations")
    
    # Display detailed conversation list
    print(f"\n📋 DETAILED CONVERSATION LIST:")
    print("-" * 60)
    for i, conv in enumerate(conversations, 1):
        property_id = conv.get('PropertyId', 'Unknown')
        user_id = conv.get('UserId', 'Unknown')
        guest_name = conv.get('GuestName', 'Unknown')
        channel = conv.get('Channel', 'Unknown')
        start_time = format_timestamp(conv.get('StartTime'))
        last_update = format_timestamp(conv.get('LastUpdateTime'))
        conversation_id = conv.get('ConversationId', 'Unknown')
        reservation_id = conv.get('ReservationId', 'None')
        phone = conv.get('GuestPhone', 'None')
        message_count = conv.get('MessageCount', 0)
        
        print(f"{i:2d}. Conversation: {conversation_id}")
        print(f"     Property: {property_id}")
        print(f"     User: {user_id}")
        print(f"     Guest: {guest_name}")
        print(f"     Channel: {channel}")
        print(f"     Start Time: {start_time}")
        print(f"     Last Update: {last_update}")
        print(f"     Messages: {message_count}")
        print(f"     Reservation: {reservation_id}")
        print(f"     Phone: {phone}")
        print()
        
        # If this looks like the problematic conversation, analyze its flow
        if channel == 'voice_call' or 'voice' in channel.lower():
            print(f"     ⚠️  This appears to be a voice conversation - analyzing flow...")
            analyze_conversation_flow(conversation_id, property_id, table)

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Find August 2nd conversations in DynamoDB')
    parser.add_argument('--json', action='store_true', help='Output raw JSON data')
    parser.add_argument('--analyze-all', action='store_true', help='Analyze flow for all conversations')
    args = parser.parse_args()
    
    # Setup DynamoDB
    table = setup_dynamodb()
    if not table:
        sys.exit(1)
    
    # Get date range for August 2nd
    start_date, end_date = get_august2_date_range()
    
    # Scan for conversations
    conversations = scan_august2_conversations(table, start_date, end_date)
    
    if args.json:
        # Output raw JSON
        print(json.dumps(conversations, indent=2, default=str))
    else:
        # Display formatted results
        display_conversations(conversations, table)

if __name__ == "__main__":
    main() 