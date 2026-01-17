#!/usr/bin/env python3
"""
Script to clean up orphaned data in Firestore.
Removes:
- Properties that belong to non-existing users
- Knowledge items that belong to non-existing properties  
- Reservations that belong to non-existing properties

Includes safety features:
- Confirmation prompts before deletion
- Detailed logging of all operations
- Backup of data before deletion
- Dry-run mode for testing
"""

import os
import sys
import logging
import json
from typing import List, Dict, Set, Tuple
from datetime import datetime
import argparse

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'concierge'))

from utils.firestore_client import initialize_firebase, get_firestore_db

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backup_orphaned_data(orphaned_properties: List[Dict], 
                        orphaned_knowledge_items: List[Dict], 
                        orphaned_reservations: List[Dict]) -> str:
    """
    Create a backup of orphaned data before deletion.
    
    Args:
        orphaned_properties: List of orphaned properties
        orphaned_knowledge_items: List of orphaned knowledge items
        orphaned_reservations: List of orphaned reservations
        
    Returns:
        Backup filename
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"orphaned_data_backup_{timestamp}.json"
    
    backup_data = {
        "backup_created": datetime.now().isoformat(),
        "orphaned_properties": orphaned_properties,
        "orphaned_knowledge_items": orphaned_knowledge_items,
        "orphaned_reservations": orphaned_reservations,
        "summary": {
            "orphaned_properties_count": len(orphaned_properties),
            "orphaned_knowledge_items_count": len(orphaned_knowledge_items),
            "orphaned_reservations_count": len(orphaned_reservations),
            "total_orphaned_count": len(orphaned_properties) + len(orphaned_knowledge_items) + len(orphaned_reservations)
        }
    }
    
    with open(backup_filename, 'w') as f:
        json.dump(backup_data, f, indent=2, default=str)
    
    logger.info(f"Backup created: {backup_filename}")
    return backup_filename

def delete_orphaned_properties(orphaned_properties: List[Dict], dry_run: bool = False) -> int:
    """
    Delete orphaned properties.
    
    Args:
        orphaned_properties: List of orphaned properties to delete
        dry_run: If True, only log what would be deleted without actually deleting
        
    Returns:
        Number of properties deleted
    """
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return 0
    
    db = get_firestore_db()
    deleted_count = 0
    
    for prop in orphaned_properties:
        property_id = prop['property_id']
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete orphaned property: {property_id}")
            else:
                db.collection('properties').document(property_id).delete()
                logger.info(f"Deleted orphaned property: {property_id}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"Error deleting property {property_id}: {e}")
    
    return deleted_count

def delete_orphaned_knowledge_items(orphaned_knowledge_items: List[Dict], dry_run: bool = False) -> int:
    """
    Delete orphaned knowledge items.
    
    Args:
        orphaned_knowledge_items: List of orphaned knowledge items to delete
        dry_run: If True, only log what would be deleted without actually deleting
        
    Returns:
        Number of knowledge items deleted
    """
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return 0
    
    db = get_firestore_db()
    deleted_count = 0
    
    for item in orphaned_knowledge_items:
        item_id = item['item_id']
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete orphaned knowledge item: {item_id}")
            else:
                db.collection('knowledge_items').document(item_id).delete()
                logger.info(f"Deleted orphaned knowledge item: {item_id}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"Error deleting knowledge item {item_id}: {e}")
    
    return deleted_count

def delete_orphaned_reservations(orphaned_reservations: List[Dict], dry_run: bool = False) -> int:
    """
    Delete orphaned reservations.
    
    Args:
        orphaned_reservations: List of orphaned reservations to delete
        dry_run: If True, only log what would be deleted without actually deleting
        
    Returns:
        Number of reservations deleted
    """
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return 0
    
    db = get_firestore_db()
    deleted_count = 0
    
    for reservation in orphaned_reservations:
        reservation_id = reservation['reservation_id']
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete orphaned reservation: {reservation_id}")
            else:
                db.collection('reservations').document(reservation_id).delete()
                logger.info(f"Deleted orphaned reservation: {reservation_id}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"Error deleting reservation {reservation_id}: {e}")
    
    return deleted_count

def get_user_confirmation(prompt: str) -> bool:
    """
    Get user confirmation for an action.
    
    Args:
        prompt: The prompt to show to the user
        
    Returns:
        True if user confirms, False otherwise
    """
    while True:
        response = input(f"{prompt} (y/N): ").strip().lower()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no', '']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")

def print_cleanup_summary(orphaned_properties: List[Dict], 
                         orphaned_knowledge_items: List[Dict], 
                         orphaned_reservations: List[Dict],
                         dry_run: bool = False):
    """
    Print a summary of what will be cleaned up.
    
    Args:
        orphaned_properties: List of orphaned properties
        orphaned_knowledge_items: List of orphaned knowledge items
        orphaned_reservations: List of orphaned reservations
        dry_run: Whether this is a dry run
    """
    mode = "DRY RUN" if dry_run else "CLEANUP"
    print(f"\n{'='*80}")
    print(f"{mode} SUMMARY")
    print(f"{'='*80}")
    
    print(f"\n📊 SUMMARY:")
    print(f"   • Orphaned Properties: {len(orphaned_properties)}")
    print(f"   • Orphaned Knowledge Items: {len(orphaned_knowledge_items)}")
    print(f"   • Orphaned Reservations: {len(orphaned_reservations)}")
    print(f"   • Total Records: {len(orphaned_properties) + len(orphaned_knowledge_items) + len(orphaned_reservations)}")
    
    if orphaned_properties:
        print(f"\n🏠 ORPHANED PROPERTIES TO {'DELETE' if not dry_run else 'REVIEW'} ({len(orphaned_properties)}):")
        for prop in orphaned_properties:
            print(f"   • Property ID: {prop['property_id']}")
            print(f"     Host ID: {prop['host_id']}")
            print(f"     Name: {prop['property_name']}")
            print()
    
    if orphaned_knowledge_items:
        print(f"\n📚 ORPHANED KNOWLEDGE ITEMS TO {'DELETE' if not dry_run else 'REVIEW'} ({len(orphaned_knowledge_items)}):")
        for item in orphaned_knowledge_items:
            print(f"   • Item ID: {item['item_id']}")
            print(f"     Property ID: {item['property_id']}")
            print(f"     Type: {item['type']}")
            print(f"     Status: {item['status']}")
            print()
    
    if orphaned_reservations:
        print(f"\n📅 ORPHANED RESERVATIONS TO {'DELETE' if not dry_run else 'REVIEW'} ({len(orphaned_reservations)}):")
        for reservation in orphaned_reservations:
            print(f"   • Reservation ID: {reservation['reservation_id']}")
            print(f"     Property ID: {reservation['property_id']}")
            print(f"     Guest: {reservation['guest_name']}")
            print(f"     Dates: {reservation['start_date']} to {reservation['end_date']}")
            print()

def main():
    """Main function to clean up orphaned data."""
    parser = argparse.ArgumentParser(description='Clean up orphaned Firestore data')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--no-confirm', action='store_true',
                       help='Skip confirmation prompts (use with caution)')
    parser.add_argument('--no-backup', action='store_true',
                       help='Skip creating backup before deletion')
    
    args = parser.parse_args()
    
    logger.info("Starting orphaned data cleanup...")
    
    try:
        # Import the check functions from the other script
        from check_orphaned_firestore_data import (
            check_orphaned_properties,
            check_orphaned_knowledge_items,
            check_orphaned_reservations,
            get_existing_property_ids
        )
        
        # Check for orphaned data
        logger.info("Checking for orphaned data...")
        orphaned_properties, existing_user_ids = check_orphaned_properties()
        existing_property_ids = get_existing_property_ids()
        orphaned_knowledge_items = check_orphaned_knowledge_items(existing_property_ids)
        orphaned_reservations = check_orphaned_reservations(existing_property_ids)
        
        total_orphaned = len(orphaned_properties) + len(orphaned_knowledge_items) + len(orphaned_reservations)
        
        if total_orphaned == 0:
            logger.info("No orphaned data found! Nothing to clean up.")
            return
        
        # Print summary
        print_cleanup_summary(orphaned_properties, orphaned_knowledge_items, orphaned_reservations, args.dry_run)
        
        # Create backup unless skipped
        backup_filename = None
        if not args.dry_run and not args.no_backup:
            backup_filename = backup_orphaned_data(orphaned_properties, orphaned_knowledge_items, orphaned_reservations)
        
        # Get confirmation
        if not args.dry_run and not args.no_confirm:
            confirm_prompt = f"Are you sure you want to delete {total_orphaned} orphaned records?"
            if backup_filename:
                confirm_prompt += f" (Backup saved to {backup_filename})"
            
            if not get_user_confirmation(confirm_prompt):
                logger.info("Cleanup cancelled by user.")
                return
        
        # Perform cleanup
        logger.info(f"Starting {'dry run' if args.dry_run else 'cleanup'}...")
        
        deleted_properties = delete_orphaned_properties(orphaned_properties, args.dry_run)
        deleted_knowledge_items = delete_orphaned_knowledge_items(orphaned_knowledge_items, args.dry_run)
        deleted_reservations = delete_orphaned_reservations(orphaned_reservations, args.dry_run)
        
        total_deleted = deleted_properties + deleted_knowledge_items + deleted_reservations
        
        # Print results
        print(f"\n{'='*80}")
        print(f"{'DRY RUN' if args.dry_run else 'CLEANUP'} RESULTS")
        print(f"{'='*80}")
        print(f"Properties {'processed' if args.dry_run else 'deleted'}: {deleted_properties}")
        print(f"Knowledge items {'processed' if args.dry_run else 'deleted'}: {deleted_knowledge_items}")
        print(f"Reservations {'processed' if args.dry_run else 'deleted'}: {deleted_reservations}")
        print(f"Total {'processed' if args.dry_run else 'deleted'}: {total_deleted}")
        
        if backup_filename and not args.dry_run:
            print(f"Backup saved to: {backup_filename}")
        
        if args.dry_run:
            logger.info("Dry run completed. No data was actually deleted.")
        else:
            logger.info(f"Cleanup completed successfully! Deleted {total_deleted} orphaned records.")
            
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 