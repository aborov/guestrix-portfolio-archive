"""
Authentication utilities.
"""

from functools import wraps
from flask import session, redirect, url_for, request, flash, g
from typing import Dict, Any, Optional, List
from concierge.utils.role_helpers import normalize_user_roles, get_primary_role

def flash_once(message, category='message'):
    """
    Flash a message only if it hasn't already been flashed in this session.
    Prevents duplicate flash messages.
    """
    existing_flashes = session.get('_flashes', [])
    message_already_exists = any(msg[1] == message and msg[0] == category for msg in existing_flashes)
    
    if not message_already_exists:
        flash(message, category)

def verify_token(id_token):
    """
    Verify Firebase ID token and return decoded token data.
    
    Args:
        id_token: Firebase ID token string
        
    Returns:
        Decoded token data dict or None if verification fails
    """
    try:
        # Import Firebase Admin SDK for token verification
        import firebase_admin
        from firebase_admin import auth
        
        if not firebase_admin._apps:
            # Initialize Firebase if not already initialized
            from concierge.lambda_src.firebase_admin_config import initialize_firebase
            initialize_firebase()
        
        # Verify the token with clock skew tolerance
        decoded_token = auth.verify_id_token(id_token, clock_skew_seconds=10)
        return decoded_token
        
    except Exception as e:
        print(f"Error verifying Firebase ID token: {e}")
        return None

def get_user(uid):
    """
    Gets a user from Firestore by UID.
    """
    from concierge.utils.firestore_client import get_user as firestore_get_user
    user_data = firestore_get_user(uid)

    if user_data:
        print(f"[DEBUG] auth/utils.py - User {uid} found in Firestore")
        return user_data
    else:
        print(f"[DEBUG] auth/utils.py - User {uid} not found in Firestore")
        return None


# No longer need DynamoDB table reference since we're using Firestore

# --- Authentication Decorator ---
def login_required(f):
    """
    Decorator to ensure the user is logged in via session.
    Populates g.user_id, g.user_roles, and g.user_role (primary) if logged in.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        user_roles = session.get('user_roles')
        
        if user_id is None:
            flash_once('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        
        # Handle backward compatibility - if no user_roles but has user_role
        if not user_roles:
            user_role = session.get('user_role')
            if user_role:
                user_roles = [user_role]
                session['user_roles'] = user_roles  # Update session
            else:
                # No role information, redirect to login but don't duplicate the message
                # since we might already be redirecting from the user_id check above
                # Only flash if we have a user_id but no roles (incomplete session)
                flash_once('Your session is incomplete. Please log in again.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
        
        g.user_id = user_id
        g.user_roles = user_roles
        g.user_role = get_primary_role_from_list(user_roles)  # Set primary role for backward compatibility
        return f(*args, **kwargs)
    return decorated_function

def get_primary_role_from_list(roles: List[str]) -> str:
    """
    Get primary role from a list of roles.
    
    Args:
        roles: List of roles
        
    Returns:
        Primary role string
    """
    if not roles:
        return 'guest'
    
    # Priority order: host > property_manager > guest
    if 'host' in roles:
        return 'host'
    elif 'property_manager' in roles:
        return 'property_manager'
    else:
        return 'guest'

def update_session_roles(user_data: Dict[str, Any]) -> None:
    """
    Update session with user roles from user data.
    
    Args:
        user_data: User data dictionary from Firestore
    """
    roles = normalize_user_roles(user_data)
    primary_role = get_primary_role(user_data)
    
    session['user_roles'] = roles
    session['user_role'] = primary_role  # Keep for backward compatibility

def requires_role(required_roles: List[str]):
    """
    Decorator to require specific roles for access.
    
    Args:
        required_roles: List of roles that can access the route
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            user_roles = getattr(g, 'user_roles', [])
            
            # Check if user has any of the required roles
            if not any(role in user_roles for role in required_roles):
                flash('You do not have permission to access this page.', 'error')
                # Redirect to appropriate dashboard based on user's roles
                if 'guest' in user_roles:
                    return redirect(url_for('views.guest_dashboard'))
                else:
                    return redirect(url_for('auth.login'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def requires_host_access():
    """
    Decorator to require host or property_manager access.
    """
    return requires_role(['host', 'property_manager'])

# --- Firebase Admin Initialization ---
def initialize_firebase_admin():
    """Initialize Firebase Admin SDK if not already initialized."""
    # Import firebase_admin here to avoid circular imports
    import firebase_admin
    from firebase_admin import credentials
    import os
    import json

    if not firebase_admin._apps:
        cred_dict = {}
        try:
            # Try to load from environment variable (for production)
            firebase_config = os.getenv('FIREBASE_SERVICE_ACCOUNT')
            if firebase_config:
                cred_dict = json.loads(firebase_config)
            else:
                # Fallback to service account file (for development)
                service_account_path = 'concierge/credentials/firebase-service-account.json'
                if os.path.exists(service_account_path):
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    return
                else:
                    print("Firebase service account file not found.")
                    return

            if cred_dict:
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
        except Exception as e:
            print(f"Error initializing Firebase Admin: {e}")
