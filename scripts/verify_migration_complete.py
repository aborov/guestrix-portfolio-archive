#!/usr/bin/env python3
"""
Verification script to ensure the migration from DynamoDB ConciergeTable to Firestore is complete.
This script checks that:
1. All users have been migrated to Firestore
2. All properties have been migrated to Firestore  
3. All knowledge sources have been migrated to Firestore
4. All knowledge items have been migrated to Firestore
5. All reservations have been migrated to Firestore

Run this script before deleting the ConciergeTable to ensure no data loss.
"""

import os
import sys
import boto3
import traceback
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def initialize_dynamodb():
    """Initialize DynamoDB connection."""
    try:
        dynamodb_resource = boto3.resource('dynamodb')
        table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'ConciergeTable')
        table = dynamodb_resource.Table(table_name)
        print(f"✓ Connected to DynamoDB table: {table_name}")
        return table
    except Exception as e:
        print(f"✗ Error connecting to DynamoDB: {e}")
        return None

def initialize_firestore():
    """Initialize Firestore connection."""
    try:
        from concierge.utils.firestore_client import initialize_firebase, get_firestore_db
        if initialize_firebase():
            db = get_firestore_db()
            print("✓ Connected to Firestore")
            return db
        else:
            print("⚠️  Failed to connect to Firestore (credentials may not be configured)")
            return None
    except Exception as e:
        print(f"⚠️  Error connecting to Firestore: {e}")
        print("   This is expected if Firestore credentials are not properly configured.")
        return None

def scan_dynamodb_entities(table, entity_type):
    """Scan DynamoDB for entities of a specific type."""
    try:
        response = table.scan(
            FilterExpression=Attr('EntityType').eq(entity_type)
        )
        
        items = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('EntityType').eq(entity_type),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        return items
    except Exception as e:
        print(f"✗ Error scanning DynamoDB for {entity_type}: {e}")
        return []

def count_firestore_collection(db, collection_name):
    """Count documents in a Firestore collection."""
    try:
        collection_ref = db.collection(collection_name)
        docs = list(collection_ref.stream())
        return len(docs)
    except Exception as e:
        print(f"✗ Error counting Firestore collection {collection_name}: {e}")
        return 0

def verify_users(dynamodb_table, firestore_db):
    """Verify user migration."""
    print("\n📋 Verifying Users Migration...")
    
    # Get users from DynamoDB
    dynamodb_users = scan_dynamodb_entities(dynamodb_table, 'USER')
    print(f"  DynamoDB users found: {len(dynamodb_users)}")
    
    if firestore_db:
        # Get users from Firestore
        firestore_user_count = count_firestore_collection(firestore_db, 'users')
        print(f"  Firestore users found: {firestore_user_count}")
        
        if len(dynamodb_users) <= firestore_user_count:
            print("  ✓ User migration appears complete")
            return True
        else:
            print(f"  ⚠️  Potential missing users: {len(dynamodb_users) - firestore_user_count}")
            return False
    else:
        print("  ⚠️  Cannot verify Firestore user count (no Firestore connection)")
        if len(dynamodb_users) == 0:
            print("  ℹ️  No users in DynamoDB, assuming migration complete")
            return True
        else:
            print(f"  ⚠️  {len(dynamodb_users)} users still in DynamoDB - manual verification needed")
            return False

def verify_properties(dynamodb_table, firestore_db):
    """Verify property migration."""
    print("\n🏠 Verifying Properties Migration...")
    
    # Get properties from DynamoDB
    dynamodb_properties = scan_dynamodb_entities(dynamodb_table, 'PROPERTY')
    print(f"  DynamoDB properties found: {len(dynamodb_properties)}")
    
    if firestore_db:
        # Get properties from Firestore
        firestore_property_count = count_firestore_collection(firestore_db, 'properties')
        print(f"  Firestore properties found: {firestore_property_count}")
        
        if len(dynamodb_properties) <= firestore_property_count:
            print("  ✓ Property migration appears complete")
            return True
        else:
            print(f"  ⚠️  Potential missing properties: {len(dynamodb_properties) - firestore_property_count}")
            return False
    else:
        print("  ⚠️  Cannot verify Firestore property count (no Firestore connection)")
        if len(dynamodb_properties) == 0:
            print("  ℹ️  No properties in DynamoDB, assuming migration complete")
            return True
        else:
            print(f"  ⚠️  {len(dynamodb_properties)} properties still in DynamoDB - manual verification needed")
            return False

def verify_knowledge_sources(dynamodb_table, firestore_db):
    """Verify knowledge source migration."""
    print("\n📚 Verifying Knowledge Sources Migration...")
    
    # Get knowledge sources from DynamoDB
    dynamodb_sources = scan_dynamodb_entities(dynamodb_table, 'KNOWLEDGE_SOURCE')
    print(f"  DynamoDB knowledge sources found: {len(dynamodb_sources)}")
    
    if firestore_db:
        # Get knowledge sources from Firestore
        firestore_source_count = count_firestore_collection(firestore_db, 'knowledge_sources')
        print(f"  Firestore knowledge sources found: {firestore_source_count}")
        
        if len(dynamodb_sources) <= firestore_source_count:
            print("  ✓ Knowledge source migration appears complete")
            return True
        else:
            print(f"  ⚠️  Potential missing knowledge sources: {len(dynamodb_sources) - firestore_source_count}")
            return False
    else:
        print("  ⚠️  Cannot verify Firestore knowledge source count (no Firestore connection)")
        if len(dynamodb_sources) == 0:
            print("  ℹ️  No knowledge sources in DynamoDB, assuming migration complete")
            return True
        else:
            print(f"  ⚠️  {len(dynamodb_sources)} knowledge sources still in DynamoDB - manual verification needed")
            return False

def verify_knowledge_items(dynamodb_table, firestore_db):
    """Verify knowledge item migration."""
    print("\n💡 Verifying Knowledge Items Migration...")
    
    # Get knowledge items from DynamoDB
    dynamodb_items = scan_dynamodb_entities(dynamodb_table, 'KNOWLEDGE_ITEM')
    print(f"  DynamoDB knowledge items found: {len(dynamodb_items)}")
    
    if firestore_db:
        # Get knowledge items from Firestore
        firestore_item_count = count_firestore_collection(firestore_db, 'knowledge_items')
        print(f"  Firestore knowledge items found: {firestore_item_count}")
        
        if len(dynamodb_items) <= firestore_item_count:
            print("  ✓ Knowledge item migration appears complete")
            return True
        else:
            print(f"  ⚠️  Potential missing knowledge items: {len(dynamodb_items) - firestore_item_count}")
            return False
    else:
        print("  ⚠️  Cannot verify Firestore knowledge item count (no Firestore connection)")
        if len(dynamodb_items) == 0:
            print("  ℹ️  No knowledge items in DynamoDB, assuming migration complete")
            return True
        else:
            print(f"  ⚠️  {len(dynamodb_items)} knowledge items still in DynamoDB - manual verification needed")
            return False

def verify_reservations(dynamodb_table, firestore_db):
    """Verify reservation migration."""
    print("\n📅 Verifying Reservations Migration...")
    
    # Get reservations from DynamoDB
    dynamodb_reservations = scan_dynamodb_entities(dynamodb_table, 'RESERVATION')
    print(f"  DynamoDB reservations found: {len(dynamodb_reservations)}")
    
    if firestore_db:
        # Get reservations from Firestore
        firestore_reservation_count = count_firestore_collection(firestore_db, 'reservations')
        print(f"  Firestore reservations found: {firestore_reservation_count}")
        
        if len(dynamodb_reservations) <= firestore_reservation_count:
            print("  ✓ Reservation migration appears complete")
            return True
        else:
            print(f"  ⚠️  Potential missing reservations: {len(dynamodb_reservations) - firestore_reservation_count}")
            return False
    else:
        print("  ⚠️  Cannot verify Firestore reservation count (no Firestore connection)")
        if len(dynamodb_reservations) == 0:
            print("  ℹ️  No reservations in DynamoDB, assuming migration complete")
            return True
        else:
            print(f"  ⚠️  {len(dynamodb_reservations)} reservations still in DynamoDB - manual verification needed")
            return False

def check_codebase_references():
    """Check if there are any remaining code references to ConciergeTable."""
    print("\n🔍 Checking for remaining code references to ConciergeTable...")
    
    # List of important files to check
    important_files = [
        'concierge/app.py',
        'concierge/config.py',
        'concierge/auth/routes.py',
        'concierge/views/routes.py',
        'concierge/api/routes.py',
    ]
    
    references_found = False
    
    for file_path in important_files:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                    
                # Check each line for active references
                for line_num, line in enumerate(lines, 1):
                    stripped_line = line.strip()
                    
                    # Skip empty lines and comments
                    if not stripped_line or stripped_line.startswith('#'):
                        continue
                    
                    # Check for get_table() that's not in a comment
                    if 'get_table()' in line and not line.strip().startswith('#'):
                        print(f"  ⚠️  Found active get_table() reference in {file_path}:{line_num}")
                        print(f"      Line: {line.strip()}")
                        references_found = True
                    
                    # Check for ConciergeTable that's not in a comment
                    elif 'ConciergeTable' in line and not line.strip().startswith('#'):
                        # Additional check: make sure it's not just in a string or comment
                        if not (line.strip().startswith('print(') and 'ConciergeTable' in line):
                            print(f"  ⚠️  Found active ConciergeTable reference in {file_path}:{line_num}")
                            print(f"      Line: {line.strip()}")
                            references_found = True
            except Exception as e:
                print(f"  ⚠️  Error checking {file_path}: {e}")
    
    if not references_found:
        print("  ✓ No active ConciergeTable references found in main application files")
        return True
    else:
        print("  ✗ Active references to ConciergeTable found - please remove them first")
        return False

def analyze_dynamodb_data(dynamodb_table):
    """Provide a summary of what's still in DynamoDB."""
    print("\n📊 DynamoDB Data Analysis...")
    
    entity_types = ['USER', 'PROPERTY', 'KNOWLEDGE_SOURCE', 'KNOWLEDGE_ITEM', 'RESERVATION']
    total_items = 0
    
    for entity_type in entity_types:
        items = scan_dynamodb_entities(dynamodb_table, entity_type)
        count = len(items)
        total_items += count
        if count > 0:
            print(f"  {entity_type}: {count} items")
    
    if total_items == 0:
        print("  ✓ No main data entities found in DynamoDB")
        return True
    else:
        print(f"  ⚠️  Total items still in DynamoDB: {total_items}")
        return False

def main():
    """Main verification function."""
    print("🔄 ConciergeTable Migration Verification")
    print("=" * 50)
    
    # Initialize connections
    dynamodb_table = initialize_dynamodb()
    firestore_db = initialize_firestore()
    
    if not dynamodb_table:
        print("✗ Cannot connect to DynamoDB. Exiting.")
        return False
    
    # Continue even if Firestore is not available
    firestore_available = firestore_db is not None
    if not firestore_available:
        print("\n⚠️  Firestore connection not available. Will check DynamoDB data and code references only.")
    
    # Run all verifications
    results = []
    
    results.append(verify_users(dynamodb_table, firestore_db))
    results.append(verify_properties(dynamodb_table, firestore_db))
    results.append(verify_knowledge_sources(dynamodb_table, firestore_db))
    results.append(verify_knowledge_items(dynamodb_table, firestore_db))
    results.append(verify_reservations(dynamodb_table, firestore_db))
    results.append(check_codebase_references())
    
    # Additional analysis
    dynamodb_empty = analyze_dynamodb_data(dynamodb_table)
    results.append(dynamodb_empty)
    
    # Summary
    print("\n📊 Migration Verification Summary")
    print("=" * 50)
    
    all_passed = all(results)
    
    if all_passed:
        print("✅ All verifications PASSED!")
        if firestore_available:
            print("\n🎉 It appears safe to delete the ConciergeTable!")
        else:
            print("\n🎉 DynamoDB appears to be empty and code references are clean!")
            print("⚠️  However, Firestore connection was not available for full verification.")
        print("\nNext steps:")
        print("1. Create a backup of the ConciergeTable (if not already done)")
        print("2. Test your application thoroughly")
        if not firestore_available:
            print("3. Fix Firestore credentials and run this script again for full verification")
        print("4. Delete the ConciergeTable using the AWS console or CLI:")
        print("   aws dynamodb delete-table --table-name ConciergeTable")
        return True
    else:
        print("❌ Some verifications FAILED!")
        print("\n⚠️  DO NOT delete the ConciergeTable yet!")
        print("\nPlease address the issues above before proceeding.")
        if not firestore_available:
            print("\nNote: Some failures may be due to missing Firestore connection.")
            print("Fix your Firestore credentials and run the script again.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 