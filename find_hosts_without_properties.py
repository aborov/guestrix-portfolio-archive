#!/usr/bin/env python3
"""
Script to find Firebase host users that don't have properties related to their account.
This helps identify hosts who may need to set up their properties or have incomplete accounts.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

from concierge.utils.firestore_client import get_firestore_client, initialize_firebase
from concierge.utils.role_helpers import has_role, normalize_user_roles
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_all_host_users():
    """Get all users with host role from Firestore."""
    if not initialize_firebase():
        logger.error("Failed to initialize Firebase")
        return []
    
    db = get_firestore_client()
    if not db:
        logger.error("Failed to get Firestore client")
        return []
    
    host_users = []
    
    try:
        # Get all users from the users collection
        users_ref = db.collection('users')
        users_docs = users_ref.stream()
        
        for doc in users_docs:
            user_data = doc.to_dict()
            user_data['id'] = doc.id
            
            # Check if user has host role
            if has_role(user_data, 'host'):
                host_users.append(user_data)
        
        logger.info(f"Found {len(host_users)} users with host role")
        return host_users
        
    except Exception as e:
        logger.error(f"Error getting host users: {e}")
        return []

def get_properties_for_host(host_id):
    """Get all properties for a specific host."""
    if not initialize_firebase():
        return []
    
    db = get_firestore_client()
    if not db:
        return []
    
    try:
        # Query properties where hostId matches
        query = db.collection('properties').where('hostId', '==', host_id)
        properties = []
        
        for doc in query.stream():
            property_data = doc.to_dict()
            property_data['id'] = doc.id
            properties.append(property_data)
        
        return properties
        
    except Exception as e:
        logger.error(f"Error getting properties for host {host_id}: {e}")
        return []

def find_hosts_without_properties():
    """Find all host users that don't have any properties."""
    logger.info("🔍 Starting analysis of host users without properties...")
    
    # Get all host users
    host_users = get_all_host_users()
    
    if not host_users:
        logger.info("No host users found")
        return []
    
    hosts_without_properties = []
    hosts_with_properties = []
    
    for user in host_users:
        user_id = user.get('id')
        display_name = user.get('displayName', 'Unknown')
        phone_number = user.get('phoneNumber', 'No phone')
        roles = normalize_user_roles(user)
        
        logger.info(f"Checking properties for host: {display_name} ({user_id})")
        
        # Get properties for this host
        properties = get_properties_for_host(user_id)
        
        if not properties:
            # Host has no properties
            hosts_without_properties.append({
                'user_id': user_id,
                'display_name': display_name,
                'phone_number': phone_number,
                'roles': roles,
                'created_at': user.get('createdAt'),
                'last_login': user.get('lastLoginAt'),
                'is_temporary': user.get('isTemporary', False),
                'account_type': user.get('accountType', 'unknown')
            })
            logger.info(f"❌ Host {display_name} has NO properties")
        else:
            # Host has properties
            hosts_with_properties.append({
                'user_id': user_id,
                'display_name': display_name,
                'phone_number': phone_number,
                'roles': roles,
                'property_count': len(properties),
                'properties': [p.get('name', 'Unnamed') for p in properties]
            })
            logger.info(f"✅ Host {display_name} has {len(properties)} properties")
    
    return hosts_without_properties, hosts_with_properties

def print_results(hosts_without_properties, hosts_with_properties):
    """Print the results in a formatted way."""
    print("\n" + "="*80)
    print("🏠 HOST USERS ANALYSIS REPORT")
    print("="*80)
    
    print(f"\n📊 SUMMARY:")
    print(f"  Total host users found: {len(hosts_without_properties) + len(hosts_with_properties)}")
    print(f"  Hosts WITH properties: {len(hosts_with_properties)}")
    print(f"  Hosts WITHOUT properties: {len(hosts_without_properties)}")
    
    if hosts_without_properties:
        print(f"\n❌ HOSTS WITHOUT PROPERTIES ({len(hosts_without_properties)}):")
        print("-" * 80)
        for i, host in enumerate(hosts_without_properties, 1):
            print(f"{i}. {host['display_name']}")
            print(f"   User ID: {host['user_id']}")
            print(f"   Phone: {host['phone_number']}")
            print(f"   Roles: {', '.join(host['roles'])}")
            print(f"   Account Type: {host['account_type']}")
            print(f"   Temporary: {host['is_temporary']}")
            print(f"   Created: {host['created_at']}")
            print(f"   Last Login: {host['last_login']}")
            print()
    
    if hosts_with_properties:
        print(f"\n✅ HOSTS WITH PROPERTIES ({len(hosts_with_properties)}):")
        print("-" * 80)
        for i, host in enumerate(hosts_with_properties, 1):
            print(f"{i}. {host['display_name']}")
            print(f"   User ID: {host['user_id']}")
            print(f"   Phone: {host['phone_number']}")
            print(f"   Properties: {host['property_count']} ({', '.join(host['properties'])})")
            print(f"   Roles: {', '.join(host['roles'])}")
            print()
    
    print("="*80)

def export_results_to_file(hosts_without_properties, hosts_with_properties, filename="host_analysis_report.txt"):
    """Export results to a text file."""
    with open(filename, 'w') as f:
        f.write("HOST USERS ANALYSIS REPORT\n")
        f.write("="*50 + "\n\n")
        
        f.write(f"SUMMARY:\n")
        f.write(f"  Total host users: {len(hosts_without_properties) + len(hosts_with_properties)}\n")
        f.write(f"  Hosts WITH properties: {len(hosts_with_properties)}\n")
        f.write(f"  Hosts WITHOUT properties: {len(hosts_without_properties)}\n\n")
        
        if hosts_without_properties:
            f.write("HOSTS WITHOUT PROPERTIES:\n")
            f.write("-" * 30 + "\n")
            for host in hosts_without_properties:
                f.write(f"Name: {host['display_name']}\n")
                f.write(f"User ID: {host['user_id']}\n")
                f.write(f"Phone: {host['phone_number']}\n")
                f.write(f"Roles: {', '.join(host['roles'])}\n")
                f.write(f"Account Type: {host['account_type']}\n")
                f.write(f"Temporary: {host['is_temporary']}\n")
                f.write(f"Created: {host['created_at']}\n")
                f.write(f"Last Login: {host['last_login']}\n")
                f.write("\n")
        
        if hosts_with_properties:
            f.write("HOSTS WITH PROPERTIES:\n")
            f.write("-" * 30 + "\n")
            for host in hosts_with_properties:
                f.write(f"Name: {host['display_name']}\n")
                f.write(f"User ID: {host['user_id']}\n")
                f.write(f"Phone: {host['phone_number']}\n")
                f.write(f"Properties: {host['property_count']} ({', '.join(host['properties'])})\n")
                f.write(f"Roles: {', '.join(host['roles'])}\n")
                f.write("\n")
    
    logger.info(f"📄 Results exported to {filename}")

def main():
    """Main function to run the analysis."""
    logger.info("🚀 Starting host users analysis...")
    
    try:
        # Find hosts without properties
        hosts_without_properties, hosts_with_properties = find_hosts_without_properties()
        
        # Print results
        print_results(hosts_without_properties, hosts_with_properties)
        
        # Export to file
        export_results_to_file(hosts_without_properties, hosts_with_properties)
        
        # Summary for action items
        if hosts_without_properties:
            print(f"\n🎯 ACTION ITEMS:")
            print(f"  • {len(hosts_without_properties)} hosts need to set up properties")
            print(f"  • Consider reaching out to these hosts to complete their setup")
            print(f"  • Check if these are test accounts that should be cleaned up")
        
        logger.info("✅ Analysis complete!")
        
    except Exception as e:
        logger.error(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 