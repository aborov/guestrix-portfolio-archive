#!/usr/bin/env python3
"""
Script to analyze voice conversation messages by querying the connections table.
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
        # Initialize DynamoDB resource with correct region
        dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
        
        # Get table name from environment or use default
        table_name = os.environ.get('CONVERSATIONS_TABLE_NAME', 'Conversations')
        connections_table_name = os.environ.get('CONNECTIONS_TABLE_NAME', 'InfraStack-connections')
        
        conversations_table = dynamodb.Table(table_name)
        connections_table = dynamodb.Table(connections_table_name)
        
        print(f"✓ Connected to DynamoDB tables:")
        print(f"  - Conversations: {table_name}")
        print(f"  - Connections: {connections_table_name}")
        return conversations_table, connections_table
    except Exception as e:
        print(f"✗ Error connecting to DynamoDB: {e}")
        return None, None

def find_connection_for_conversation(conversation_id, property_id, connections_table):
    """Find the connection record that contains the conversation history."""
    try:
        # Scan the connections table for entries with this conversation_id
        response = connections_table.scan(
            FilterExpression=Attr('conversation_id').eq(conversation_id)
        )
        
        connections = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = connections_table.scan(
                FilterExpression=Attr('conversation_id').eq(conversation_id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            connections.extend(response.get('Items', []))
        
        return connections
    except Exception as e:
        print(f"✗ Error finding connection for conversation {conversation_id}: {e}")
        return []

def analyze_conversation_messages(conversation_id, property_id, user_id, guest_name, start_time):
    """Analyze the actual conversation messages from the connections table."""
    print(f"\n🔍 ANALYZING VOICE CONVERSATION MESSAGES")
    print(f"Conversation ID: {conversation_id}")
    print(f"Property ID: {property_id}")
    print(f"User ID: {user_id}")
    print(f"Guest Name: {guest_name}")
    print(f"Start Time: {start_time}")
    print("=" * 80)
    
    conversations_table, connections_table = setup_dynamodb()
    if not connections_table:
        return None
    
    # Find connection records for this conversation
    connections = find_connection_for_conversation(conversation_id, property_id, connections_table)
    
    if not connections:
        print("❌ No connection records found for this conversation")
        return None
    
    print(f"Found {len(connections)} connection records")
    print()
    
    for i, connection in enumerate(connections, 1):
        connection_id = connection.get('connectionId', 'Unknown')
        property_id_conn = connection.get('property_id', 'Unknown')
        guest_name_conn = connection.get('guest_name', 'Unknown')
        conversation_history = connection.get('conversation_history', [])
        
        print(f"📞 CONNECTION {i}: {connection_id}")
        print(f"  Property ID: {property_id_conn}")
        print(f"  Guest Name: {guest_name_conn}")
        print(f"  Conversation History Length: {len(conversation_history)}")
        print()
        
        if conversation_history:
            print(f"💬 CONVERSATION MESSAGES:")
            print("-" * 60)
            
            for j, message in enumerate(conversation_history, 1):
                role = message.get('role', 'Unknown')
                text = message.get('text', 'No text')
                timestamp = message.get('timestamp', 'No timestamp')
                
                print(f"{j:2d}. [{timestamp}] {role.upper()}")
                print(f"     Text: {text}")
                print()
        else:
            print("❌ No conversation history found in this connection")
        
        print("=" * 60)
    
    return connections

def analyze_problematic_conversations():
    """Analyze the specific conversations that match the problematic criteria."""
    # The conversations that match the 3 PM Chicago time criteria
    target_conversations = [
        {
            'id': 'de1305d6-d3f3-4023-84df-e16168f9fcdc',
            'property_id': 'c2d26719-5654-45ee-aa2c-8fbafa637fb4',
            'user_id': 'yP3ZwJohaxU7No1mPPK1dFiuTIg1',
            'guest_name': 'Salma',
            'start_time': '2025-08-02T20:02:01.973186+00:00',
            'message_count': 23
        },
        {
            'id': 'c85c69af-fdfc-4687-85a1-9e5fa37cfba4',
            'property_id': 'c2d26719-5654-45ee-aa2c-8fbafa637fb4',
            'user_id': 'yP3ZwJohaxU7No1mPPK1dFiuTIg1',
            'guest_name': 'Salma',
            'start_time': '2025-08-02T20:12:06.156962+00:00',
            'message_count': 2
        },
        {
            'id': 'f4a74bcf-2bfa-4f62-906c-3b0b6dd8d913',
            'property_id': 'c2d26719-5654-45ee-aa2c-8fbafa637fb4',
            'user_id': 'yP3ZwJohaxU7No1mPPK1dFiuTIg1',
            'guest_name': 'Salma',
            'start_time': '2025-08-02T20:13:21.885343+00:00',
            'message_count': 5
        }
    ]
    
    print("🎯 ANALYZING VOICE CONVERSATION MESSAGES")
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
        
        # Analyze the conversation messages
        connections = analyze_conversation_messages(
            conv['id'], 
            conv['property_id'], 
            conv['user_id'], 
            conv['guest_name'], 
            conv['start_time']
        )
        
        if connections:
            print(f"✅ Found {len(connections)} connection records")
        else:
            print(f"❌ No connection records found")
        
        print("\n" + "="*80 + "\n")

def main():
    """Main function."""
    analyze_problematic_conversations()

if __name__ == "__main__":
    main() 