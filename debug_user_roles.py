#!/usr/bin/env python3
"""
Quick debug script to check user roles
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'concierge'))

from concierge.utils.firestore_client import get_user
from concierge.utils.role_helpers import normalize_user_roles, has_role, get_primary_role

def check_user_roles(user_id):
    """Check and display user roles"""
    print(f"Checking roles for user: {user_id}")
    
    user_data = get_user(user_id)
    if not user_data:
        print("❌ User not found")
        return
    
    print(f"✅ User found")
    print(f"Raw role field: {repr(user_data.get('role'))}")
    
    roles = normalize_user_roles(user_data)
    print(f"Normalized roles: {roles}")
    
    primary_role = get_primary_role(user_data)
    print(f"Primary role: {primary_role}")
    
    print(f"Has guest role: {has_role(user_data, 'guest')}")
    print(f"Has host role: {has_role(user_data, 'host')}")
    
    # Show reservation IDs if any
    reservation_ids = user_data.get('reservationIds', [])
    print(f"Attached reservations: {reservation_ids}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python debug_user_roles.py <user_id>")
        sys.exit(1)
    
    user_id = sys.argv[1]
    check_user_roles(user_id) 