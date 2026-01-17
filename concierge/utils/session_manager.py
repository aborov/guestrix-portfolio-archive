"""
Session management utilities for magic link authentication.
Handles session creation, validation, and device fingerprinting.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from flask import request, make_response

logger = logging.getLogger(__name__)

# Session duration (4 hours)
SESSION_DURATION_HOURS = 4

def generate_device_fingerprint() -> str:
    """
    Generate a device fingerprint based on request headers.
    
    Returns:
        Device fingerprint hash
    """
    try:
        # Collect device characteristics
        user_agent = request.headers.get('User-Agent', '')
        accept_language = request.headers.get('Accept-Language', '')
        accept_encoding = request.headers.get('Accept-Encoding', '')
        
        # Create fingerprint string
        fingerprint_data = f"{user_agent}|{accept_language}|{accept_encoding}"
        
        # Hash the fingerprint
        fingerprint_hash = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
        
        return fingerprint_hash
        
    except Exception as e:
        logger.error(f"Error generating device fingerprint: {e}")
        return "unknown"

def create_session_data(user_id: str) -> Dict:
    """
    Create session data for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        Session data dictionary
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=SESSION_DURATION_HOURS)
    
    session_data = {
        'userId': user_id,
        'lastVerified': now.isoformat(),
        'expiresAt': expires_at.isoformat(),
        'deviceFingerprint': generate_device_fingerprint(),
        'createdAt': now.isoformat()
    }
    
    return session_data

def validate_session(session_cookie: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate a session cookie.
    
    Args:
        session_cookie: Session cookie value
        
    Returns:
        Tuple of (is_valid, user_id, reason)
    """
    try:
        if not session_cookie:
            return False, None, 'no_session'
        
        # Decode session data
        session_data = json.loads(session_cookie)
        
        # Check expiration
        expires_at = datetime.fromisoformat(session_data.get('expiresAt', ''))
        if expires_at < datetime.now(timezone.utc):
            return False, None, 'expired'
        
        # Check device fingerprint
        current_fingerprint = generate_device_fingerprint()
        stored_fingerprint = session_data.get('deviceFingerprint', '')
        
        if current_fingerprint != stored_fingerprint:
            return False, None, 'device_mismatch'
        
        # Session is valid
        user_id = session_data.get('userId')
        return True, user_id, 'valid'
        
    except Exception as e:
        logger.error(f"Error validating session: {e}")
        return False, None, 'invalid'

def create_session_cookie(user_id: str) -> str:
    """
    Create a session cookie for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        Session cookie value
    """
    session_data = create_session_data(user_id)
    return json.dumps(session_data)

def set_session_cookie(response, user_id: str) -> None:
    """
    Set session cookie on response.
    
    Args:
        response: Flask response object
        user_id: User ID
    """
    try:
        session_cookie = create_session_cookie(user_id)
        
        # Set cookie with security options
        response.set_cookie(
            'magicLinkSession',
            session_cookie,
            max_age=SESSION_DURATION_HOURS * 3600,  # 4 hours in seconds
            httponly=True,  # Prevent JavaScript access
            secure=False,   # Set to True in production with HTTPS
            samesite='Lax'  # CSRF protection
        )
        
        logger.info(f"Session cookie set for user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error setting session cookie: {e}")

def clear_session_cookie(response) -> None:
    """
    Clear session cookie from response.
    
    Args:
        response: Flask response object
    """
    try:
        response.set_cookie(
            'magicLinkSession',
            '',
            expires=0,
            httponly=True,
            secure=False,
            samesite='Lax'
        )
        
        logger.info("Session cookie cleared")
        
    except Exception as e:
        logger.error(f"Error clearing session cookie: {e}")

def get_session_from_request() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Get and validate session from current request.
    
    Returns:
        Tuple of (is_valid, user_id, reason)
    """
    try:
        session_cookie = request.cookies.get('magicLinkSession')
        return validate_session(session_cookie)
        
    except Exception as e:
        logger.error(f"Error getting session from request: {e}")
        return False, None, 'error'

def is_session_expired(session_cookie: str) -> bool:
    """
    Check if a session is expired.
    
    Args:
        session_cookie: Session cookie value
        
    Returns:
        True if expired, False otherwise
    """
    try:
        if not session_cookie:
            return True
        
        session_data = json.loads(session_cookie)
        expires_at = datetime.fromisoformat(session_data.get('expiresAt', ''))
        
        return expires_at < datetime.now(timezone.utc)
        
    except Exception:
        return True

def extend_session(user_id: str) -> str:
    """
    Extend session for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        New session cookie value
    """
    return create_session_cookie(user_id)

def get_session_info(session_cookie: str) -> Optional[Dict]:
    """
    Get session information.
    
    Args:
        session_cookie: Session cookie value
        
    Returns:
        Session information dictionary or None
    """
    try:
        if not session_cookie:
            return None
        
        session_data = json.loads(session_cookie)
        
        # Add human-readable expiration
        expires_at = datetime.fromisoformat(session_data.get('expiresAt', ''))
        session_data['expiresAtHuman'] = expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')
        session_data['isExpired'] = expires_at < datetime.now(timezone.utc)
        
        return session_data
        
    except Exception as e:
        logger.error(f"Error getting session info: {e}")
        return None
