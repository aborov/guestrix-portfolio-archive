#!/usr/bin/env python3
"""
Migration script to update all knowledge items with "pending_review" status to "pending".
This script unifies the status naming across the application.

Usage:
    python scripts/migrate_pending_status.py [--dry-run]
    
Options:
    --dry-run    Show what would be updated without making changes
"""

import sys
import os
import argparse
from typing import List, Dict

# Add the parent directory to the path so we can import from concierge
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from concierge.utils.firestore_client import initialize_firebase, get_firestore_client
from google.cloud import firestore

def get_all_knowledge_items_with_pending_review() -> List[Dict]:
    """
    Get all knowledge items with 'pending_review' status from Firestore.
    
    Returns:
        List of knowledge items with pending_review status
    """
    if not initialize_firebase():
        print("❌ Failed to initialize Firebase")
        return []
    
    db = get_firestore_client()
    if not db:
        print("❌ Failed to get Firestore client")
        return []
    
    try:
        # Query all knowledge items with pending_review status
        query = db.collection('knowledge_items').where('status', '==', 'pending_review')
        docs = query.stream()
        
        items = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            items.append(data)
        
        return items
    
    except Exception as e:
        print(f"❌ Error querying knowledge items: {e}")
        return []

def update_knowledge_item_status(item_id: str, dry_run: bool = False) -> bool:
    """
    Update a knowledge item's status from 'pending_review' to 'pending'.
    
    Args:
        item_id: ID of the knowledge item to update
        dry_run: If True, don't actually update, just show what would be done
        
    Returns:
        True if successful (or would be successful in dry-run), False otherwise
    """
    if dry_run:
        print(f"  🔄 Would update item {item_id}: pending_review → pending")
        return True
    
    if not initialize_firebase():
        return False
    
    db = get_firestore_client()
    if not db:
        return False
    
    try:
        # Update the status field
        doc_ref = db.collection('knowledge_items').document(item_id)
        doc_ref.update({
            'status': 'pending',
            'updated_at': firestore.SERVER_TIMESTAMP
        })
        
        print(f"  ✅ Updated item {item_id}: pending_review → pending")
        return True
    
    except Exception as e:
        print(f"  ❌ Failed to update item {item_id}: {e}")
        return False

def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description='Migrate pending_review status to pending')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be updated without making changes')
    
    args = parser.parse_args()
    
    print("🔧 KNOWLEDGE ITEM STATUS MIGRATION")
    print("=" * 50)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
    print()
    
    # Get all items with pending_review status
    print("📋 Finding knowledge items with 'pending_review' status...")
    items = get_all_knowledge_items_with_pending_review()
    
    if not items:
        print("✅ No knowledge items found with 'pending_review' status")
        print("   Migration not needed - all items already use unified status naming")
        return
    
    print(f"📊 Found {len(items)} knowledge items with 'pending_review' status")
    print()
    
    # Show summary of items to be updated
    print("📝 Items to be updated:")
    for item in items:
        property_id = item.get('property_id', 'unknown')
        item_type = item.get('type', 'unknown')
        tags = item.get('tags', [])
        tag_str = ', '.join(tags[:2]) + ('...' if len(tags) > 2 else '')
        print(f"  • {item['id'][:8]}... (Property: {property_id[:8]}..., Type: {item_type}, Tags: {tag_str})")
    
    print()
    
    if args.dry_run:
        print("🔍 DRY RUN - No changes will be made")
    else:
        # Confirm before proceeding
        response = input(f"❓ Update {len(items)} items from 'pending_review' to 'pending'? (y/N): ")
        if response.lower() != 'y':
            print("❌ Migration cancelled by user")
            return
    
    print()
    print("🔄 Processing items...")
    
    # Update each item
    success_count = 0
    for item in items:
        if update_knowledge_item_status(item['id'], dry_run=args.dry_run):
            success_count += 1
    
    print()
    print("📊 MIGRATION SUMMARY")
    print("-" * 30)
    print(f"Total items found: {len(items)}")
    print(f"Successfully {'would be ' if args.dry_run else ''}updated: {success_count}")
    print(f"Failed: {len(items) - success_count}")
    
    if args.dry_run:
        print()
        print("💡 To perform the actual migration, run:")
        print("   python scripts/migrate_pending_status.py")
    else:
        print()
        if success_count == len(items):
            print("✅ Migration completed successfully!")
            print("   All knowledge items now use unified 'pending' status")
        else:
            print("⚠️  Migration completed with some failures")
            print("   Check the error messages above for details")

if __name__ == '__main__':
    main()
