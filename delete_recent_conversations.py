#!/usr/bin/env python3
"""
Script to delete conversation records from DynamoDB created in the last three days.

This script will:
1. Connect to the Conversations DynamoDB table
2. Scan for records created in the last 3 days
3. Delete those records in batches
4. Provide progress updates and summary

Usage: python delete_recent_conversations.py [--dry-run] [--days=3]
"""

import os
import sys
import boto3
import argparse
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
import time

# Add the project root to the path so we can import from concierge
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_dynamodb():
    """Initialize DynamoDB connection."""
    try:
        # Use the same region as configured in the project
        region = os.environ.get('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-2'))
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb', region_name=region)
        
        # Get table name from environment or use default
        table_name = os.environ.get('CONVERSATIONS_TABLE_NAME', 'Conversations')
        
        # Get the table
        table = dynamodb.Table(table_name)
        
        # Test connection
        table.load()
        
        print(f"✓ Connected to DynamoDB table: {table_name} in region: {region}")
        return table
        
    except Exception as e:
        print(f"✗ Error connecting to DynamoDB: {e}")
        return None

def get_cutoff_date(days_back=3):
    """Get the cutoff date for deletion (X days ago)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    return cutoff

def scan_recent_conversations(table, cutoff_date, dry_run=True):
    """Scan for conversations created after the cutoff date."""
    print(f"Scanning for conversations created after: {cutoff_date.isoformat()}")
    
    conversations_to_delete = []
    total_scanned = 0
    
    try:
        # Use scan with filter expression to find recent conversations
        # We need to check multiple possible timestamp fields based on the schema
        filter_expression = None
        
        # Check for StartTime field (from create_conversation_session)
        start_time_filter = Attr('StartTime').gte(cutoff_date.isoformat())
        
        # Check for LastUpdateTime field
        update_time_filter = Attr('LastUpdateTime').gte(cutoff_date.isoformat())
        
        # Check for Timestamp field (from store_conversation_entry)
        timestamp_filter = Attr('Timestamp').gte(cutoff_date.isoformat())
        
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
        conversations_to_delete.extend(items)
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            print(f"Continuing scan... Found {len(conversations_to_delete)} conversations so far")
            response = table.scan(
                FilterExpression=final_filter,
                Select='ALL_ATTRIBUTES',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items = response.get('Items', [])
            total_scanned += len(items)
            conversations_to_delete.extend(items)
        
        print(f"Scan complete. Total items scanned: {total_scanned}")
        print(f"Conversations to delete: {len(conversations_to_delete)}")
        
        if conversations_to_delete and not dry_run:
            print("\nSample conversations found:")
            for i, conv in enumerate(conversations_to_delete[:5]):  # Show first 5
                print(f"  {i+1}. PK: {conv.get('PK', 'N/A')}, SK: {conv.get('SK', 'N/A')}")
                print(f"      StartTime: {conv.get('StartTime', 'N/A')}")
                print(f"      Guest: {conv.get('GuestName', 'N/A')}")
                print(f"      Channel: {conv.get('Channel', 'N/A')}")
                print()
        
        return conversations_to_delete
        
    except Exception as e:
        print(f"✗ Error scanning conversations: {e}")
        return []

def delete_conversations_batch(table, conversations, dry_run=True):
    """Delete conversations in batches."""
    if not conversations:
        print("No conversations to delete.")
        return True
    
    if dry_run:
        print(f"DRY RUN: Would delete {len(conversations)} conversations")
        return True
    
    print(f"Deleting {len(conversations)} conversations...")
    
    # DynamoDB batch_writer can handle up to 25 items per batch
    batch_size = 25
    deleted_count = 0
    failed_count = 0
    
    try:
        with table.batch_writer() as batch:
            for i, conversation in enumerate(conversations):
                try:
                    # Extract primary key
                    pk = conversation.get('PK')
                    sk = conversation.get('SK')
                    
                    if not pk or not sk:
                        print(f"Warning: Skipping conversation with missing keys: PK={pk}, SK={sk}")
                        failed_count += 1
                        continue
                    
                    # Delete the item
                    batch.delete_item(Key={'PK': pk, 'SK': sk})
                    deleted_count += 1
                    
                    # Progress update every 25 items
                    if (i + 1) % batch_size == 0:
                        print(f"Progress: {i + 1}/{len(conversations)} conversations processed")
                        time.sleep(0.1)  # Small delay to avoid throttling
                        
                except Exception as e:
                    print(f"Error deleting conversation {conversation.get('PK', 'N/A')}/{conversation.get('SK', 'N/A')}: {e}")
                    failed_count += 1
                    continue
        
        print(f"✓ Deletion complete!")
        print(f"  Successfully deleted: {deleted_count}")
        print(f"  Failed: {failed_count}")
        
        return failed_count == 0
        
    except Exception as e:
        print(f"✗ Error during batch deletion: {e}")
        return False

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Delete recent conversation records from DynamoDB')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--days', type=int, default=3,
                       help='Number of days back to delete (default: 3)')
    parser.add_argument('--confirm', action='store_true',
                       help='Skip confirmation prompt (use with caution)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DynamoDB Conversations Cleanup Script")
    print("=" * 60)
    
    # Setup DynamoDB connection
    table = setup_dynamodb()
    if not table:
        sys.exit(1)
    
    # Get cutoff date
    cutoff_date = get_cutoff_date(args.days)
    print(f"Deleting conversations created after: {cutoff_date.isoformat()}")
    print(f"Days back: {args.days}")
    print(f"Dry run: {'Yes' if args.dry_run else 'No'}")
    print()
    
    # Scan for conversations to delete
    conversations = scan_recent_conversations(table, cutoff_date, args.dry_run)
    
    if not conversations:
        print("No conversations found to delete.")
        return
    
    # Confirmation prompt (unless --confirm is used)
    if not args.dry_run and not args.confirm:
        print(f"\n⚠️  WARNING: This will permanently delete {len(conversations)} conversation records!")
        print("This action cannot be undone.")
        response = input("Are you sure you want to continue? (type 'DELETE' to confirm): ")
        if response != 'DELETE':
            print("Operation cancelled.")
            return
    
    # Perform deletion
    success = delete_conversations_batch(table, conversations, args.dry_run)
    
    if success:
        print("\n✓ Operation completed successfully!")
    else:
        print("\n✗ Operation completed with errors.")
        sys.exit(1)

if __name__ == '__main__':
    main()
