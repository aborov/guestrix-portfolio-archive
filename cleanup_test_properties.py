#!/usr/bin/env python3
"""
Clean up test properties that are causing duplicate issues.
This script removes properties created by test users.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

from concierge.utils.firestore_client import get_firestore_db, initialize_firebase
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_test_properties():
    """Remove properties created by test users"""
    
    # Initialize Firebase
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return False
    
    db = get_firestore_db()
    if not db:
        logger.error("Failed to get Firestore client")
        return False
    
    # Test user IDs to clean up
    test_user_ids = [
        'test_host_fixes',
        'xmM4At4jH3eeNfq69WpBqPyMg952'  # Previous test user
    ]
    
    # URLs that are causing issues
    problematic_urls = [
        'https://www.airbnb.com/rooms/973815691982105805',
        'https://www.airbnb.com/rooms/50679425'
    ]
    
    logger.info("🧹 Starting cleanup of test properties...")
    
    # Clean up by test user IDs
    for user_id in test_user_ids:
        try:
            query = db.collection('properties').where('hostId', '==', user_id)
            properties = list(query.stream())
            
            logger.info(f"Found {len(properties)} properties for test user: {user_id}")
            
            for prop_doc in properties:
                prop_data = prop_doc.to_dict()
                prop_name = prop_data.get('name', 'Unknown')
                prop_url = prop_data.get('airbnbListingUrl', 'No URL')
                
                logger.info(f"  Deleting: {prop_doc.id} - {prop_name}")
                logger.info(f"    URL: {prop_url}")
                
                # Delete the property
                prop_doc.reference.delete()
                logger.info(f"  ✅ Deleted property: {prop_doc.id}")
                
        except Exception as e:
            logger.error(f"Error cleaning up properties for user {user_id}: {e}")
    
    # Clean up by problematic URLs (any user)
    for url in problematic_urls:
        try:
            query = db.collection('properties').where('airbnbListingUrl', '==', url)
            properties = list(query.stream())
            
            logger.info(f"Found {len(properties)} properties with URL: {url}")
            
            for prop_doc in properties:
                prop_data = prop_doc.to_dict()
                prop_name = prop_data.get('name', 'Unknown')
                host_id = prop_data.get('hostId', 'Unknown')
                
                # Only delete if it's a test user
                if host_id in test_user_ids:
                    logger.info(f"  Deleting: {prop_doc.id} - {prop_name} (Host: {host_id})")
                    prop_doc.reference.delete()
                    logger.info(f"  ✅ Deleted property: {prop_doc.id}")
                else:
                    logger.info(f"  Keeping: {prop_doc.id} - {prop_name} (Host: {host_id}) - Not a test user")
                
        except Exception as e:
            logger.error(f"Error cleaning up properties with URL {url}: {e}")
    
    logger.info("🎉 Cleanup completed!")
    return True

if __name__ == "__main__":
    cleanup_test_properties()
