#!/usr/bin/env python3
"""
Script to check for orphaned data in Firestore.
Identifies:
- Properties that belong to non-existing users
- Knowledge items that belong to non-existing properties  
- Reservations that belong to non-existing properties
"""

import os
import sys
import logging
import argparse
from typing import List, Dict, Set, Tuple
from datetime import datetime

# Add the concierge directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'concierge'))

from utils.firestore_client import initialize_firebase, get_firestore_db

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_orphaned_properties() -> Tuple[List[Dict], Set[str]]:
    """
    Check for properties that belong to non-existing users.
    
    Returns:
        Tuple of (orphaned_properties, existing_user_ids)
    """
    logger.info("Checking for orphaned properties...")
    
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return [], set()
    
    db = get_firestore_db()
    
    # Get all users
    users_ref = db.collection('users')
    users = list(users_ref.stream())
    existing_user_ids = {user.id for user in users}
    logger.info(f"Found {len(existing_user_ids)} existing users")
    
    # Get all properties
    properties_ref = db.collection('properties')
    properties = list(properties_ref.stream())
    logger.info(f"Found {len(properties)} properties")
    
    orphaned_properties = []
    for prop in properties:
        prop_data = prop.to_dict()
        host_id = prop_data.get('hostId') or prop_data.get('host_id')
        
        if host_id and host_id not in existing_user_ids:
            orphaned_properties.append({
                'property_id': prop.id,
                'host_id': host_id,
                'property_name': prop_data.get('name', 'Unknown'),
                'created_at': prop_data.get('createdAt'),
                'updated_at': prop_data.get('updatedAt')
            })
    
    logger.info(f"Found {len(orphaned_properties)} orphaned properties")
    return orphaned_properties, existing_user_ids

def check_orphaned_knowledge_items(existing_property_ids: Set[str]) -> List[Dict]:
    """
    Check for knowledge items that belong to non-existing properties.
    
    Args:
        existing_property_ids: Set of existing property IDs
        
    Returns:
        List of orphaned knowledge items
    """
    logger.info("Checking for orphaned knowledge items...")
    
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return []
    
    db = get_firestore_db()
    
    # Get all knowledge items
    knowledge_items_ref = db.collection('knowledge_items')
    knowledge_items = list(knowledge_items_ref.stream())
    logger.info(f"Found {len(knowledge_items)} knowledge items")
    
    orphaned_knowledge_items = []
    for item in knowledge_items:
        item_data = item.to_dict()
        property_id = item_data.get('propertyId') or item_data.get('property_id')
        
        if property_id and property_id not in existing_property_ids:
            orphaned_knowledge_items.append({
                'item_id': item.id,
                'property_id': property_id,
                'content_preview': item_data.get('content', '')[:100] + '...' if item_data.get('content') else 'No content',
                'type': item_data.get('type', 'Unknown'),
                'status': item_data.get('status', 'Unknown'),
                'created_at': item_data.get('createdAt'),
                'updated_at': item_data.get('updatedAt')
            })
    
    logger.info(f"Found {len(orphaned_knowledge_items)} orphaned knowledge items")
    return orphaned_knowledge_items

def check_orphaned_reservations(existing_property_ids: Set[str]) -> List[Dict]:
    """
    Check for reservations that belong to non-existing properties.
    
    Args:
        existing_property_ids: Set of existing property IDs
        
    Returns:
        List of orphaned reservations
    """
    logger.info("Checking for orphaned reservations...")
    
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return []
    
    db = get_firestore_db()
    
    # Get all reservations
    reservations_ref = db.collection('reservations')
    reservations = list(reservations_ref.stream())
    logger.info(f"Found {len(reservations)} reservations")
    
    orphaned_reservations = []
    for reservation in reservations:
        reservation_data = reservation.to_dict()
        property_id = reservation_data.get('propertyId') or reservation_data.get('property_id')
        
        if property_id and property_id not in existing_property_ids:
            orphaned_reservations.append({
                'reservation_id': reservation.id,
                'property_id': property_id,
                'guest_name': reservation_data.get('guestName', 'Unknown'),
                'start_date': reservation_data.get('startDate'),
                'end_date': reservation_data.get('endDate'),
                'phone': reservation_data.get('phone'),
                'created_at': reservation_data.get('createdAt'),
                'updated_at': reservation_data.get('updatedAt')
            })
    
    logger.info(f"Found {len(orphaned_reservations)} orphaned reservations")
    return orphaned_reservations

def get_existing_property_ids() -> Set[str]:
    """
    Get all existing property IDs.
    
    Returns:
        Set of existing property IDs
    """
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return set()
    
    db = get_firestore_db()
    
    # Get all properties
    properties_ref = db.collection('properties')
    properties = list(properties_ref.stream())
    existing_property_ids = {prop.id for prop in properties}
    logger.info(f"Found {len(existing_property_ids)} existing properties")
    
    return existing_property_ids

def print_orphaned_data_summary(orphaned_properties: List[Dict], 
                              orphaned_knowledge_items: List[Dict], 
                              orphaned_reservations: List[Dict]):
    """
    Print a summary of all orphaned data.
    
    Args:
        orphaned_properties: List of orphaned properties
        orphaned_knowledge_items: List of orphaned knowledge items
        orphaned_reservations: List of orphaned reservations
    """
    print("\n" + "="*80)
    print("ORPHANED DATA SUMMARY")
    print("="*80)
    
    print(f"\n📊 SUMMARY:")
    print(f"   • Orphaned Properties: {len(orphaned_properties)}")
    print(f"   • Orphaned Knowledge Items: {len(orphaned_knowledge_items)}")
    print(f"   • Orphaned Reservations: {len(orphaned_reservations)}")
    
    if orphaned_properties:
        print(f"\n🏠 ORPHANED PROPERTIES ({len(orphaned_properties)}):")
        for prop in orphaned_properties:
            print(f"   • Property ID: {prop['property_id']}")
            print(f"     Host ID: {prop['host_id']}")
            print(f"     Name: {prop['property_name']}")
            print(f"     Created: {prop['created_at']}")
            print()
    
    if orphaned_knowledge_items:
        print(f"\n📚 ORPHANED KNOWLEDGE ITEMS ({len(orphaned_knowledge_items)}):")
        for item in orphaned_knowledge_items:
            print(f"   • Item ID: {item['item_id']}")
            print(f"     Property ID: {item['property_id']}")
            print(f"     Type: {item['type']}")
            print(f"     Status: {item['status']}")
            print(f"     Content: {item['content_preview']}")
            print()
    
    if orphaned_reservations:
        print(f"\n📅 ORPHANED RESERVATIONS ({len(orphaned_reservations)}):")
        for reservation in orphaned_reservations:
            print(f"   • Reservation ID: {reservation['reservation_id']}")
            print(f"     Property ID: {reservation['property_id']}")
            print(f"     Guest: {reservation['guest_name']}")
            print(f"     Dates: {reservation['start_date']} to {reservation['end_date']}")
            print(f"     Phone: {reservation['phone']}")
            print()

def save_orphaned_data_report(orphaned_properties: List[Dict], 
                            orphaned_knowledge_items: List[Dict], 
                            orphaned_reservations: List[Dict]):
    """
    Save the orphaned data report to a file.
    
    Args:
        orphaned_properties: List of orphaned properties
        orphaned_knowledge_items: List of orphaned knowledge items
        orphaned_reservations: List of orphaned reservations
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"orphaned_firestore_data_{timestamp}.txt"
    
    with open(filename, 'w') as f:
        f.write("ORPHANED FIRESTORE DATA REPORT\n")
        f.write("="*50 + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        
        f.write(f"SUMMARY:\n")
        f.write(f"  • Orphaned Properties: {len(orphaned_properties)}\n")
        f.write(f"  • Orphaned Knowledge Items: {len(orphaned_knowledge_items)}\n")
        f.write(f"  • Orphaned Reservations: {len(orphaned_reservations)}\n\n")
        
        if orphaned_properties:
            f.write("ORPHANED PROPERTIES:\n")
            f.write("-" * 20 + "\n")
            for prop in orphaned_properties:
                f.write(f"Property ID: {prop['property_id']}\n")
                f.write(f"Host ID: {prop['host_id']}\n")
                f.write(f"Name: {prop['property_name']}\n")
                f.write(f"Created: {prop['created_at']}\n\n")
        
        if orphaned_knowledge_items:
            f.write("ORPHANED KNOWLEDGE ITEMS:\n")
            f.write("-" * 25 + "\n")
            for item in orphaned_knowledge_items:
                f.write(f"Item ID: {item['item_id']}\n")
                f.write(f"Property ID: {item['property_id']}\n")
                f.write(f"Type: {item['type']}\n")
                f.write(f"Status: {item['status']}\n")
                f.write(f"Content: {item['content_preview']}\n\n")
        
        if orphaned_reservations:
            f.write("ORPHANED RESERVATIONS:\n")
            f.write("-" * 22 + "\n")
            for reservation in orphaned_reservations:
                f.write(f"Reservation ID: {reservation['reservation_id']}\n")
                f.write(f"Property ID: {reservation['property_id']}\n")
                f.write(f"Guest: {reservation['guest_name']}\n")
                f.write(f"Dates: {reservation['start_date']} to {reservation['end_date']}\n")
                f.write(f"Phone: {reservation['phone']}\n\n")
    
    logger.info(f"Report saved to: {filename}")

def delete_orphaned_reservations(orphaned_reservations: List[Dict]) -> int:
    """Delete orphaned reservations from Firestore.

    Args:
        orphaned_reservations: List of orphaned reservation dicts from check.

    Returns:
        Count of successfully deleted reservations.
    """
    if not orphaned_reservations:
        logger.info("No orphaned reservations to delete.")
        return 0
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase for deletion")
        return 0
    db = get_firestore_db()
    deleted = 0
    for res in orphaned_reservations:
        res_id = res.get('reservation_id')
        if not res_id:
            continue
        try:
            db.collection('reservations').document(res_id).delete()
            deleted += 1
            logger.info(f"Deleted orphaned reservation: {res_id}")
        except Exception as e:
            logger.error(f"Failed to delete orphaned reservation {res_id}: {e}")
    logger.info(f"Deleted {deleted}/{len(orphaned_reservations)} orphaned reservations")
    return deleted

def main():
    """Main function to check for orphaned data and optionally delete orphaned reservations."""
    parser = argparse.ArgumentParser(description="Check and clean orphaned Firestore data")
    parser.add_argument("--delete-orphaned-reservations", action="store_true", help="Delete orphaned reservations after reporting")
    parser.add_argument("--yes", action="store_true", help="Proceed without interactive confirmation")
    args = parser.parse_args()

    logger.info("Starting orphaned data check...")
    try:
        orphaned_properties, _ = check_orphaned_properties()
        existing_property_ids = get_existing_property_ids()
        orphaned_knowledge_items = check_orphaned_knowledge_items(existing_property_ids)
        orphaned_reservations = check_orphaned_reservations(existing_property_ids)

        print_orphaned_data_summary(orphaned_properties, orphaned_knowledge_items, orphaned_reservations)
        save_orphaned_data_report(orphaned_properties, orphaned_knowledge_items, orphaned_reservations)

        total_orphaned = len(orphaned_properties) + len(orphaned_knowledge_items) + len(orphaned_reservations)
        if total_orphaned > 0:
            logger.warning(f"Found {total_orphaned} total orphaned records!")
        else:
            logger.info("No orphaned data found! 🎉")

        if args.delete_orphaned_reservations:
            if not args.yes:
                logger.error("Deletion requested but --yes not provided. Aborting.")
                sys.exit(2)
            deleted = delete_orphaned_reservations(orphaned_reservations)
            logger.info(f"Cleanup complete. Deleted {deleted} orphaned reservations.")
    except Exception as e:
        logger.error(f"Error during orphaned data check: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 