"""
Helper functions for managing user roles with array support and backward compatibility.
"""

from typing import List, Union, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def normalize_user_roles(user_data: Dict[str, Any]) -> List[str]:
    """
    Normalize user roles to always return a list, handling backward compatibility.
    
    Args:
        user_data: User data dictionary from Firestore
        
    Returns:
        List of roles (e.g., ['guest'], ['host'], ['guest', 'host'])
    """
    if not user_data:
        return ['guest']  # Default role
    
    role_field = user_data.get('role', 'guest')
    
    # If role is already a list, return it
    if isinstance(role_field, list):
        return role_field if role_field else ['guest']
    
    # If role is a string, convert to list
    if isinstance(role_field, str):
        return [role_field]
    
    # Fallback to guest role
    return ['guest']

def has_role(user_data: Dict[str, Any], role: str) -> bool:
    """
    Check if user has a specific role.
    
    Args:
        user_data: User data dictionary from Firestore
        role: Role to check for (e.g., 'guest', 'host', 'property_manager')
        
    Returns:
        True if user has the role, False otherwise
    """
    roles = normalize_user_roles(user_data)
    return role in roles

def has_any_role(user_data: Dict[str, Any], roles: List[str]) -> bool:
    """
    Check if user has any of the specified roles.
    
    Args:
        user_data: User data dictionary from Firestore
        roles: List of roles to check for
        
    Returns:
        True if user has any of the roles, False otherwise
    """
    user_roles = normalize_user_roles(user_data)
    return any(role in user_roles for role in roles)

def get_primary_role(user_data: Dict[str, Any]) -> str:
    """
    Get the primary role for a user. Host takes precedence over guest.
    
    Args:
        user_data: User data dictionary from Firestore
        
    Returns:
        Primary role string
    """
    roles = normalize_user_roles(user_data)
    
    # Priority order: host > property_manager > guest
    if 'host' in roles:
        return 'host'
    elif 'property_manager' in roles:
        return 'property_manager'
    else:
        return 'guest'

def add_role(user_data: Dict[str, Any], new_role: str) -> Dict[str, Any]:
    """
    Add a role to user data, converting single role to array if needed.
    
    Args:
        user_data: User data dictionary from Firestore
        new_role: Role to add
        
    Returns:
        Updated user data dictionary
    """
    if not user_data:
        user_data = {}
    
    current_roles = normalize_user_roles(user_data)
    
    # Add role if not already present
    if new_role not in current_roles:
        current_roles.append(new_role)
    
    # Update user data with array of roles
    user_data['role'] = current_roles
    return user_data

def remove_role(user_data: Dict[str, Any], role_to_remove: str) -> Dict[str, Any]:
    """
    Remove a role from user data.
    
    Args:
        user_data: User data dictionary from Firestore
        role_to_remove: Role to remove
        
    Returns:
        Updated user data dictionary
    """
    if not user_data:
        return user_data
    
    current_roles = normalize_user_roles(user_data)
    
    # Remove role if present
    if role_to_remove in current_roles:
        current_roles.remove(role_to_remove)
    
    # Ensure at least one role remains
    if not current_roles:
        current_roles = ['guest']
    
    # Update user data
    user_data['role'] = current_roles
    return user_data

def get_default_dashboard_path(user_data: Dict[str, Any]) -> str:
    """
    Get the default dashboard path for a user based on their roles.
    Hosts always default to /dashboard, others to /guest.
    
    Args:
        user_data: User data dictionary from Firestore
        
    Returns:
        Dashboard path string
    """
    if has_role(user_data, 'host') or has_role(user_data, 'property_manager'):
        return '/dashboard'
    else:
        return '/guest'

def can_access_host_dashboard(user_data: Dict[str, Any]) -> bool:
    """
    Check if user can access the host dashboard.
    
    Args:
        user_data: User data dictionary from Firestore
        
    Returns:
        True if user can access host dashboard, False otherwise
    """
    return has_any_role(user_data, ['host', 'property_manager'])

def can_access_guest_dashboard(user_data: Dict[str, Any]) -> bool:
    """
    Check if user can access the guest dashboard.
    All users can access guest dashboard, hosts get guest role added automatically.
    
    Args:
        user_data: User data dictionary from Firestore
        
    Returns:
        True (all users can access guest dashboard)
    """
    return True  # All users can access guest dashboard

def ensure_guest_role(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure user has guest role, adding it if they don't.
    Used when hosts access guest dashboard.
    
    Args:
        user_data: User data dictionary from Firestore
        
    Returns:
        Updated user data dictionary with guest role added
    """
    return add_role(user_data, 'guest') 