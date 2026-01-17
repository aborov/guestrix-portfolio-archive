#!/usr/bin/env python3
"""
Script to check for orphaned knowledge items that belong to properties no longer in the database.
This helps maintain database integrity and identify cleanup opportunities.

Usage:
    python scripts/check_orphaned_knowledge_items.py [--cleanup] [--dry-run]
    
Options:
    --cleanup    Remove orphaned knowledge items (use with --dry-run first)
    --dry-run    Show what would be done without making changes
"""

import sys
import os
import argparse
from typing import List, Dict, Set
from collections import defaultdict

# Add the parent directory to the path so we can import from concierge
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from concierge.utils.firestore_client import initialize_firebase, get_firestore_client
from google.cloud import firestore

def get_all_property_ids() -> Set[str]:
    """
    Get all property IDs from Firestore.

    Returns:
        Set of property IDs that exist in the database
    """
    if not initialize_firebase():
        print("❌ Failed to initialize Firebase")
        return set()

    db = get_firestore_client()
    if not db:
        print("❌ Failed to get Firestore client")
        return set()

    try:
        # Query all properties from Firestore
        collection_ref = db.collection('properties')
        docs = collection_ref.stream()

        property_ids = set()
        for doc in docs:
            property_ids.add(doc.id)

        return property_ids

    except Exception as e:
        print(f"❌ Error getting properties from Firestore: {e}")
        return set()

def get_all_knowledge_items() -> List[Dict]:
    """
    Get all knowledge items from Firestore.
    
    Returns:
        List of knowledge items with their data
    """
    if not initialize_firebase():
        print("❌ Failed to initialize Firebase")
        return []
    
    db = get_firestore_client()
    if not db:
        print("❌ Failed to get Firestore client")
        return []
    
    try:
        # Query all knowledge items
        collection_ref = db.collection('knowledge_items')
        docs = collection_ref.stream()
        
        items = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            items.append(data)
        
        return items
    
    except Exception as e:
        print(f"❌ Error querying knowledge items: {e}")
        return []

def analyze_knowledge_items(knowledge_items: List[Dict], valid_property_ids: Set[str]) -> Dict:
    """
    Analyze knowledge items to find orphaned ones.
    
    Args:
        knowledge_items: List of all knowledge items
        valid_property_ids: Set of valid property IDs
        
    Returns:
        Dictionary with analysis results
    """
    orphaned_items = []
    valid_items = []
    items_by_property = defaultdict(list)
    items_by_status = defaultdict(int)
    items_by_type = defaultdict(int)
    
    for item in knowledge_items:
        # Check for both property_id and propertyId field names
        property_id = item.get('property_id') or item.get('propertyId')
        status = item.get('status', 'unknown')
        item_type = item.get('type', 'unknown')

        # Count by status and type
        items_by_status[status] += 1
        items_by_type[item_type] += 1

        if property_id:
            items_by_property[property_id].append(item)

            if property_id not in valid_property_ids:
                orphaned_items.append(item)
            else:
                valid_items.append(item)
        else:
            # Items without property_id/propertyId are also orphaned
            orphaned_items.append(item)
    
    return {
        'orphaned_items': orphaned_items,
        'valid_items': valid_items,
        'items_by_property': dict(items_by_property),
        'items_by_status': dict(items_by_status),
        'items_by_type': dict(items_by_type),
        'total_items': len(knowledge_items)
    }

def delete_knowledge_item(item_id: str, dry_run: bool = False) -> bool:
    """
    Delete a knowledge item from Firestore.
    
    Args:
        item_id: ID of the knowledge item to delete
        dry_run: If True, don't actually delete, just show what would be done
        
    Returns:
        True if successful (or would be successful in dry-run), False otherwise
    """
    if dry_run:
        print(f"  🗑️  Would delete item {item_id}")
        return True
    
    if not initialize_firebase():
        return False
    
    db = get_firestore_client()
    if not db:
        return False
    
    try:
        # Delete the item
        doc_ref = db.collection('knowledge_items').document(item_id)
        doc_ref.delete()
        
        print(f"  ✅ Deleted item {item_id}")
        return True
    
    except Exception as e:
        print(f"  ❌ Failed to delete item {item_id}: {e}")
        return False

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Check for orphaned knowledge items')
    parser.add_argument('--cleanup', action='store_true', 
                       help='Remove orphaned knowledge items')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    print("🔍 ORPHANED KNOWLEDGE ITEMS CHECK")
    print("=" * 50)
    
    if args.cleanup and not args.dry_run:
        print("⚠️  CLEANUP MODE - Items will be permanently deleted!")
    elif args.cleanup and args.dry_run:
        print("🔍 DRY RUN CLEANUP - No items will be deleted")
    else:
        print("📊 ANALYSIS MODE - No changes will be made")
    
    print()
    
    # Get all valid property IDs
    print("📋 Getting all properties from Firestore...")
    valid_property_ids = get_all_property_ids()

    if not valid_property_ids:
        print("❌ No properties found or error accessing Firestore")
        return
    
    print(f"✅ Found {len(valid_property_ids)} valid properties")
    
    # Get all knowledge items
    print("\n📋 Getting all knowledge items from Firestore...")
    knowledge_items = get_all_knowledge_items()
    
    if not knowledge_items:
        print("❌ No knowledge items found or error accessing Firestore")
        return
    
    print(f"✅ Found {len(knowledge_items)} knowledge items")
    
    # Analyze items
    print("\n🔍 Analyzing knowledge items...")
    analysis = analyze_knowledge_items(knowledge_items, valid_property_ids)
    
    # Display results
    print("\n📊 ANALYSIS RESULTS")
    print("-" * 30)
    print(f"Total knowledge items: {analysis['total_items']}")
    print(f"Valid items: {len(analysis['valid_items'])}")
    print(f"Orphaned items: {len(analysis['orphaned_items'])}")
    
    print(f"\n📈 Items by Status:")
    for status, count in sorted(analysis['items_by_status'].items()):
        print(f"  {status}: {count}")
    
    print(f"\n📈 Items by Type:")
    for item_type, count in sorted(analysis['items_by_type'].items()):
        print(f"  {item_type}: {count}")
    
    # Show orphaned items details
    if analysis['orphaned_items']:
        print(f"\n🚨 ORPHANED ITEMS DETAILS:")
        orphaned_by_property = defaultdict(list)
        
        for item in analysis['orphaned_items']:
            property_id = item.get('property_id', 'NO_PROPERTY_ID')
            orphaned_by_property[property_id].append(item)
        
        for property_id, items in orphaned_by_property.items():
            print(f"\n  Property ID: {property_id} ({len(items)} items)")
            for item in items[:5]:  # Show first 5 items
                item_type = item.get('type', 'unknown')
                tags = item.get('tags', [])
                tag_str = ', '.join(tags[:2]) + ('...' if len(tags) > 2 else '')
                print(f"    • {item['id'][:8]}... (Type: {item_type}, Tags: {tag_str})")
            
            if len(items) > 5:
                print(f"    ... and {len(items) - 5} more items")
        
        # Cleanup if requested
        if args.cleanup:
            print(f"\n🗑️  CLEANUP ORPHANED ITEMS")
            print("-" * 30)
            
            if not args.dry_run:
                response = input(f"❓ Delete {len(analysis['orphaned_items'])} orphaned items? (y/N): ")
                if response.lower() != 'y':
                    print("❌ Cleanup cancelled by user")
                    return
            
            print(f"\n🔄 Processing {len(analysis['orphaned_items'])} orphaned items...")
            
            success_count = 0
            for item in analysis['orphaned_items']:
                if delete_knowledge_item(item['id'], dry_run=args.dry_run):
                    success_count += 1
            
            print(f"\n📊 CLEANUP SUMMARY")
            print("-" * 20)
            print(f"Total orphaned items: {len(analysis['orphaned_items'])}")
            print(f"Successfully {'would be ' if args.dry_run else ''}deleted: {success_count}")
            print(f"Failed: {len(analysis['orphaned_items']) - success_count}")
            
            if args.dry_run:
                print(f"\n💡 To perform actual cleanup, run:")
                print(f"   python scripts/check_orphaned_knowledge_items.py --cleanup")
            else:
                if success_count == len(analysis['orphaned_items']):
                    print(f"\n✅ Cleanup completed successfully!")
                else:
                    print(f"\n⚠️  Cleanup completed with some failures")
    
    else:
        print(f"\n✅ No orphaned knowledge items found!")
        print(f"   All knowledge items belong to valid properties")
    
    print(f"\n🎯 Database integrity check complete!")

if __name__ == '__main__':
    main()
