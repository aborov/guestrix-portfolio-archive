#!/usr/bin/env python3
"""
Script to explore the connections table structure and find conversation data.
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
        connections_table_name = os.environ.get('CONNECTIONS_TABLE_NAME', 'InfraStack-connections')
        
        connections_table = dynamodb.Table(connections_table_name)
        
        print(f"✓ Connected to DynamoDB table: {connections_table_name}")
        return connections_table
    except Exception as e:
        print(f"✗ Error connecting to DynamoDB: {e}")
        return None

def explore_connections_table(table):
    """Explore the connections table to understand its structure."""
    print(f"\n🔍 EXPLORING CONNECTIONS TABLE STRUCTURE")
    print("=" * 80)
    
    try:
        # Scan the table to see what's in it
        response = table.scan(Limit=10)
        items = response.get('Items', [])
        
        print(f"Found {len(items)} items in connections table")
        print()
        
        if items:
            print("📋 SAMPLE ITEMS:")
            print("-" * 60)
            
            for i, item in enumerate(items, 1):
                print(f"Item {i}:")
                for key, value in item.items():
                    if isinstance(value, list):
                        print(f"  {key}: {len(value)} items")
                        if value:
                            print(f"    First item: {value[0]}")
                    else:
                        print(f"  {key}: {value}")
                print()
        
        # Look for items with conversation history
        print("🔍 SEARCHING FOR ITEMS WITH CONVERSATION HISTORY:")
        print("-" * 60)
        
        response = table.scan(
            FilterExpression=Attr('conversation_history').exists()
        )
        
        history_items = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('conversation_history').exists(),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            history_items.extend(response.get('Items', []))
        
        print(f"Found {len(history_items)} items with conversation history")
        print()
        
        for i, item in enumerate(history_items, 1):
            connection_id = item.get('connectionId', 'Unknown')
            property_id = item.get('property_id', 'Unknown')
            guest_name = item.get('guest_name', 'Unknown')
            conversation_history = item.get('conversation_history', [])
            
            print(f"Connection {i}: {connection_id}")
            print(f"  Property ID: {property_id}")
            print(f"  Guest Name: {guest_name}")
            print(f"  Conversation History Length: {len(conversation_history)}")
            
            if conversation_history:
                print(f"  Sample messages:")
                for j, message in enumerate(conversation_history[:3], 1):
                    role = message.get('role', 'Unknown')
                    text = message.get('text', 'No text')[:100]
                    timestamp = message.get('timestamp', 'No timestamp')
                    print(f"    {j}. [{timestamp}] {role}: {text}...")
                if len(conversation_history) > 3:
                    print(f"    ... and {len(conversation_history) - 3} more messages")
            print()
        
        return items, history_items
        
    except Exception as e:
        print(f"✗ Error exploring connections table: {e}")
        return [], []

def search_for_salma_conversations(table):
    """Search for conversations involving Salma."""
    print(f"\n🔍 SEARCHING FOR SALMA CONVERSATIONS")
    print("=" * 80)
    
    try:
        # Search for items with guest_name containing "Salma"
        response = table.scan(
            FilterExpression=Attr('guest_name').contains('Salma')
        )
        
        salma_items = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('guest_name').contains('Salma'),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            salma_items.extend(response.get('Items', []))
        
        print(f"Found {len(salma_items)} items with Salma")
        print()
        
        for i, item in enumerate(salma_items, 1):
            connection_id = item.get('connectionId', 'Unknown')
            property_id = item.get('property_id', 'Unknown')
            guest_name = item.get('guest_name', 'Unknown')
            conversation_history = item.get('conversation_history', [])
            
            print(f"Salma Connection {i}: {connection_id}")
            print(f"  Property ID: {property_id}")
            print(f"  Guest Name: {guest_name}")
            print(f"  Conversation History Length: {len(conversation_history)}")
            
            if conversation_history:
                print(f"  Messages:")
                for j, message in enumerate(conversation_history, 1):
                    role = message.get('role', 'Unknown')
                    text = message.get('text', 'No text')
                    timestamp = message.get('timestamp', 'No timestamp')
                    print(f"    {j}. [{timestamp}] {role}: {text}")
                print()
        
        return salma_items
        
    except Exception as e:
        print(f"✗ Error searching for Salma conversations: {e}")
        return []

def main():
    """Main function."""
    table = setup_dynamodb()
    if not table:
        sys.exit(1)
    
    # Explore the table structure
    items, history_items = explore_connections_table(table)
    
    # Search for Salma conversations
    salma_items = search_for_salma_conversations(table)

if __name__ == "__main__":
    main() 