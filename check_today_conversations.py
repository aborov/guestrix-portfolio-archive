#!/usr/bin/env python3
"""
Script to check conversations for today (August 4) in DynamoDB.
Shows conversation count, times, users, and properties.
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

def get_today_date_range():
    """Get the date range for today (August 4, 2025)."""
    # Set to August 4, 2025
    today = datetime(2025, 8, 4, tzinfo=timezone.utc)
    start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    print(f"Checking conversations for: {start_of_day.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Date range: {start_of_day.isoformat()} to {end_of_day.isoformat()}")
    
    return start_of_day, end_of_day

def scan_today_conversations(table, start_date, end_date):
    """Scan for conversations created today."""
    print(f"\nScanning for conversations between {start_date.isoformat()} and {end_date.isoformat()}")
    
    conversations = []
    total_scanned = 0
    
    try:
        # Use scan with filter expression to find today's conversations
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
        print(f"Conversations found today: {len(conversations)}")
        
        return conversations
        
    except Exception as e:
        print(f"✗ Error scanning conversations: {e}")
        return []

def scan_all_conversations(table):
    """Scan for all conversations in the database."""
    print(f"\nScanning for ALL conversations in the database...")
    
    conversations = []
    total_scanned = 0
    
    try:
        # Scan for all conversation entities
        filter_expression = Attr('EntityType').eq('CONVERSATION')
        
        # Perform scan
        response = table.scan(
            FilterExpression=filter_expression,
            Select='ALL_ATTRIBUTES'
        )
        
        items = response.get('Items', [])
        total_scanned += len(items)
        conversations.extend(items)
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            print(f"Continuing scan... Found {len(conversations)} conversations so far")
            response = table.scan(
                FilterExpression=filter_expression,
                Select='ALL_ATTRIBUTES',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items = response.get('Items', [])
            total_scanned += len(items)
            conversations.extend(items)
        
        print(f"Scan complete. Total items scanned: {total_scanned}")
        print(f"Total conversations found: {len(conversations)}")
        
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

def display_conversations(conversations):
    """Display conversation details in a formatted way."""
    if not conversations:
        print("\n❌ No conversations found for today.")
        return
    
    print(f"\n📊 CONVERSATION SUMMARY FOR TODAY")
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
            print(f"  {hour:02d}:00 - {hour:02d}:59: {count} conversations")
    
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

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Check today\'s conversations in DynamoDB')
    parser.add_argument('--date', type=str, help='Date in YYYY-MM-DD format (default: 2025-08-04)')
    parser.add_argument('--json', action='store_true', help='Output raw JSON data')
    parser.add_argument('--all', action='store_true', help='Show all conversations regardless of date')
    args = parser.parse_args()
    
    # Setup DynamoDB
    table = setup_dynamodb()
    if not table:
        sys.exit(1)
    
    # Scan for conversations
    if args.all:
        conversations = scan_all_conversations(table)
    else:
        # Get date range
        if args.date:
            try:
                date_obj = datetime.strptime(args.date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                start_date = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = date_obj.replace(hour=23, minute=59, second=59, microsecond=999999)
            except ValueError:
                print(f"✗ Invalid date format: {args.date}. Use YYYY-MM-DD format.")
                sys.exit(1)
        else:
            start_date, end_date = get_today_date_range()
        
        conversations = scan_today_conversations(table, start_date, end_date)
    
    if args.json:
        # Output raw JSON
        print(json.dumps(conversations, indent=2, default=str))
    else:
        # Display formatted results
        display_conversations(conversations)

if __name__ == "__main__":
    main() 