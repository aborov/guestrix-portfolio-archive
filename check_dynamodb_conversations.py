#!/usr/bin/env python3
"""
Script to check DynamoDB Conversations table for records related to a specific property ID.
"""

import sys
import os
import boto3
from datetime import datetime
import json

# Add the concierge directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

from concierge.infra.assets.utils.dynamodb_client import initialize_dynamodb, get_conversations_table

def check_property_conversations(property_id: str):
    """Check DynamoDB Conversations table for records related to a specific property."""
    
    print(f"🔍 Checking DynamoDB Conversations table for property: {property_id}")
    print("-" * 80)
    
    # Initialize DynamoDB
    if not initialize_dynamodb():
        print("❌ Failed to initialize DynamoDB")
        return
    
    # Get the table
    table = get_conversations_table()
    if not table:
        print("❌ Failed to get DynamoDB table")
        return
    
    try:
        # Query for conversations with this property ID
        # The PK format is typically PROPERTY#{property_id}
        pk = f"PROPERTY#{property_id}"
        
        print(f"📋 Querying with Partition Key: {pk}")
        
        # Query the table
        response = table.query(
            KeyConditionExpression='PK = :pk',
            ExpressionAttributeValues={
                ':pk': pk
            }
        )
        
        conversations = response.get('Items', [])
        
        if not conversations:
            print("📭 No conversations found for this property ID")
            return
        
        print(f"✅ Found {len(conversations)} conversation(s) for property {property_id}")
        print("-" * 80)
        
        # Process each conversation
        for i, conversation in enumerate(conversations, 1):
            print(f"\n🗣️  Conversation {i}:")
            print(f"   SK: {conversation.get('SK', 'N/A')}")
            print(f"   EntityType: {conversation.get('EntityType', 'N/A')}")
            print(f"   CreatedAt: {conversation.get('CreatedAt', 'N/A')}")
            print(f"   UpdatedAt: {conversation.get('UpdatedAt', 'N/A')}")
            
            # Show all available fields
            print(f"   All fields: {list(conversation.keys())}")
            
            # Show some key data if available
            if 'GuestName' in conversation:
                print(f"   Guest: {conversation['GuestName']}")
            if 'GuestPhoneNumber' in conversation:
                print(f"   Phone: {conversation['GuestPhoneNumber']}")
            if 'Summary' in conversation:
                print(f"   Summary: {conversation['Summary'][:100]}...")
            
            # If there are more fields, show them in a structured way
            additional_fields = {k: v for k, v in conversation.items() 
                               if k not in ['PK', 'SK', 'EntityType', 'CreatedAt', 'UpdatedAt']}
            if additional_fields:
                print(f"   Additional data:")
                for field, value in additional_fields.items():
                    if isinstance(value, str) and len(value) > 100:
                        print(f"     {field}: {value[:100]}...")
                    else:
                        print(f"     {field}: {value}")
        
        # Check if there are more results (pagination)
        while 'LastEvaluatedKey' in response:
            print(f"\n📄 Fetching more results...")
            response = table.query(
                KeyConditionExpression='PK = :pk',
                ExpressionAttributeValues={
                    ':pk': pk
                },
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            
            additional_conversations = response.get('Items', [])
            if additional_conversations:
                conversations.extend(additional_conversations)
                print(f"📈 Found {len(additional_conversations)} more conversations")
                
                # Process additional conversations
                for i, conversation in enumerate(additional_conversations, len(conversations) - len(additional_conversations) + 1):
                    print(f"\n🗣️  Conversation {i}:")
                    print(f"   SK: {conversation.get('SK', 'N/A')}")
                    print(f"   EntityType: {conversation.get('EntityType', 'N/A')}")
                    print(f"   CreatedAt: {conversation.get('CreatedAt', 'N/A')}")
                    print(f"   UpdatedAt: {conversation.get('UpdatedAt', 'N/A')}")
                    
                    # Show all available fields
                    print(f"   All fields: {list(conversation.keys())}")
        
        print(f"\n📊 Summary:")
        print(f"   Total conversations found: {len(conversations)}")
        print(f"   Property ID: {property_id}")
        print(f"   Query completed at: {datetime.now().isoformat()}")
        
        # Save results to a JSON file for further analysis
        output_file = f"property_conversations_{property_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump({
                'query_info': {
                    'property_id': property_id,
                    'query_time': datetime.now().isoformat(),
                    'total_conversations': len(conversations)
                },
                'conversations': conversations
            }, f, indent=2, default=str)
        
        print(f"💾 Results saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error querying DynamoDB: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function to check property conversations."""
    property_id = "73ed39fb-2c98-41c3-bb06-ffcfee086ed0"
    
    print("🚀 DynamoDB Conversations Table Query Tool")
    print(f"   Target Property ID: {property_id}")
    print("=" * 80)
    
    check_property_conversations(property_id)
    
    print("\n" + "=" * 80)
    print("🏁 Query completed!")

if __name__ == "__main__":
    main()
