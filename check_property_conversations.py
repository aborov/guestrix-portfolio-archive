#!/usr/bin/env python3
"""
Script to check detailed conversations for a specific property in DynamoDB.
Shows conversation details, messages, and flow.
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

def get_property_conversations(table, property_id):
    """Get all conversations for a specific property."""
    print(f"\nScanning for conversations for property: {property_id}")
    
    conversations = []
    total_scanned = 0
    
    try:
        # Query by property ID using PK
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                  Key('SK').begins_with("CONVERSATION#"),
            Select='ALL_ATTRIBUTES'
        )
        
        items = response.get('Items', [])
        total_scanned += len(items)
        conversations.extend(items)
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            print(f"Continuing query... Found {len(conversations)} conversations so far")
            response = table.query(
                KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                      Key('SK').begins_with("CONVERSATION#"),
                Select='ALL_ATTRIBUTES',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items = response.get('Items', [])
            total_scanned += len(items)
            conversations.extend(items)
        
        print(f"Query complete. Total conversations found: {len(conversations)}")
        
        return conversations
        
    except Exception as e:
        print(f"✗ Error querying conversations for property {property_id}: {e}")
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

def display_property_conversations(conversations, property_id):
    """Display detailed conversation information for a property."""
    if not conversations:
        print(f"\n❌ No conversations found for property: {property_id}")
        return
    
    print(f"\n📊 DETAILED CONVERSATIONS FOR PROPERTY: {property_id}")
    print("=" * 80)
    print(f"Total conversations: {len(conversations)}")
    
    # Sort conversations by start time
    conversations.sort(key=lambda x: x.get('StartTime', ''))
    
    # Group by user
    user_stats = {}
    channel_stats = {}
    time_stats = {}
    
    for conv in conversations:
        user_id = conv.get('UserId', 'Unknown')
        channel = conv.get('Channel', 'Unknown')
        start_time = conv.get('StartTime')
        guest_name = conv.get('GuestName', 'Unknown')
        
        # User stats
        if user_id not in user_stats:
            user_stats[user_id] = {
                'count': 0,
                'channels': set(),
                'guests': set(),
                'conversations': []
            }
        user_stats[user_id]['count'] += 1
        user_stats[user_id]['channels'].add(channel)
        user_stats[user_id]['guests'].add(guest_name)
        user_stats[user_id]['conversations'].append(conv)
        
        # Channel stats
        if channel not in channel_stats:
            channel_stats[channel] = 0
        channel_stats[channel] += 1
        
        # Time stats
        if start_time:
            try:
                if start_time.endswith('Z'):
                    start_time = start_time.replace('Z', '+00:00')
                dt = datetime.fromisoformat(start_time)
                hour = dt.hour
                if hour not in time_stats:
                    time_stats[hour] = 0
                time_stats[hour] += 1
            except:
                pass
    
    # Display summary statistics
    print(f"\n📈 SUMMARY STATISTICS:")
    print("-" * 40)
    print(f"Unique users: {len(user_stats)}")
    print(f"Channels used: {', '.join(channel_stats.keys())}")
    print(f"Total conversations: {len(conversations)}")
    
    # Display user breakdown
    print(f"\n👥 USER BREAKDOWN:")
    print("-" * 40)
    for user_id, stats in user_stats.items():
        print(f"User: {user_id}")
        print(f"  Conversations: {stats['count']}")
        print(f"  Channels: {', '.join(stats['channels'])}")
        print(f"  Guest names: {', '.join(stats['guests'])}")
        print()
    
    # Display channel breakdown
    print(f"\n📞 CHANNEL BREAKDOWN:")
    print("-" * 40)
    for channel, count in channel_stats.items():
        print(f"{channel}: {count} conversations")
    
    # Display time distribution
    if time_stats:
        print(f"\n⏰ TIME DISTRIBUTION (by hour UTC):")
        print("-" * 40)
        for hour in sorted(time_stats.keys()):
            count = time_stats[hour]
            print(f"  {hour:02d}:00 - {hour:02d}:59: {count} conversations")
    
    # Display detailed conversation list
    print(f"\n📋 DETAILED CONVERSATION LIST:")
    print("-" * 80)
    for i, conv in enumerate(conversations, 1):
        conversation_id = conv.get('ConversationId', 'Unknown')
        user_id = conv.get('UserId', 'Unknown')
        guest_name = conv.get('GuestName', 'Unknown')
        channel = conv.get('Channel', 'Unknown')
        start_time = format_timestamp(conv.get('StartTime'))
        last_update = format_timestamp(conv.get('LastUpdateTime'))
        message_count = conv.get('MessageCount', 0)
        reservation_id = conv.get('ReservationId', 'None')
        phone = conv.get('GuestPhone', 'None')
        
        print(f"{i:2d}. Conversation: {conversation_id}")
        print(f"     User: {user_id}")
        print(f"     Guest: {guest_name}")
        print(f"     Channel: {channel}")
        print(f"     Start Time: {start_time}")
        print(f"     Last Update: {last_update}")
        print(f"     Messages: {message_count}")
        print(f"     Reservation: {reservation_id}")
        print(f"     Phone: {phone}")
        
        # Display messages if available
        messages = conv.get('Messages', [])
        if messages:
            print(f"     Messages:")
            for j, msg in enumerate(messages, 1):
                role = msg.get('role', 'unknown')
                text = msg.get('text', '')
                timestamp = format_timestamp(msg.get('timestamp'))
                print(f"       {j}. [{role.upper()}] {timestamp}: {text[:100]}{'...' if len(text) > 100 else ''}")
        
        print()

def get_conversation_messages(table, property_id, conversation_id):
    """Get detailed messages for a specific conversation."""
    try:
        response = table.get_item(
            Key={
                'PK': f"PROPERTY#{property_id}",
                'SK': f"CONVERSATION#{conversation_id}"
            }
        )
        
        item = response.get('Item')
        if not item:
            print(f"❌ Conversation {conversation_id} not found")
            return None
        
        return item
    except Exception as e:
        print(f"✗ Error getting conversation {conversation_id}: {e}")
        return None

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Check detailed conversations for a specific property')
    parser.add_argument('property_id', type=str, help='Property ID to check')
    parser.add_argument('--conversation', type=str, help='Specific conversation ID to examine')
    parser.add_argument('--json', action='store_true', help='Output raw JSON data')
    args = parser.parse_args()
    
    # Setup DynamoDB
    table = setup_dynamodb()
    if not table:
        sys.exit(1)
    
    # Get conversations for the property
    conversations = get_property_conversations(table, args.property_id)
    
    if args.conversation:
        # Get specific conversation details
        conversation = get_conversation_messages(table, args.property_id, args.conversation)
        if conversation:
            if args.json:
                print(json.dumps(conversation, indent=2, default=str))
            else:
                print(f"\n📋 DETAILED CONVERSATION: {args.conversation}")
                print("=" * 80)
                print(json.dumps(conversation, indent=2, default=str))
    else:
        # Display all conversations for the property
        if args.json:
            print(json.dumps(conversations, indent=2, default=str))
        else:
            display_property_conversations(conversations, args.property_id)

if __name__ == "__main__":
    main() 