"""
Authentication method linking utilities for adding email/phone to existing accounts.
"""

from flask import session, request, jsonify, flash, redirect, url_for
from concierge.utils.firestore_client import get_user, update_user, find_user_by_phone, get_user_by_email
from concierge.auth.utils import verify_token
import logging

logger = logging.getLogger(__name__)

def link_phone_to_account(current_user_id: str, phone_number: str, firebase_id_token: str) -> dict:
    """
    Link a phone number to an existing user account.
    
    Args:
        current_user_id: Current user's Firebase UID
        phone_number: Phone number to link (should be verified via OTP)
        firebase_id_token: Firebase ID token from phone auth
        
    Returns:
        Dict with success status and message
    """
    try:
        # Verify the Firebase token contains the phone number
        decoded_token = verify_token(firebase_id_token)
        if not decoded_token:
            return {"success": False, "error": "Invalid Firebase token"}
        
        token_phone = decoded_token.get('phone_number')
        if token_phone != phone_number:
            return {"success": False, "error": "Phone number mismatch"}
        
        # Check if phone number is already associated with another account
        existing_user = find_user_by_phone(phone_number)
        if existing_user and existing_user.get('id') != current_user_id:
            return {
                "success": False, 
                "error": "This phone number is already associated with another account"
            }
        
        # Update current user's phone number
        update_data = {
            'phoneNumber': phone_number,
            'phoneVerifiedAt': decoded_token.get('auth_time')
        }
        
        success = update_user(current_user_id, update_data)
        if success:
            logger.info(f"Successfully linked phone {phone_number} to user {current_user_id}")
            return {"success": True, "message": "Phone number linked successfully"}
        else:
            return {"success": False, "error": "Failed to update user record"}
            
    except Exception as e:
        logger.error(f"Error linking phone to account: {e}")
        return {"success": False, "error": "An unexpected error occurred"}

def link_email_to_account(current_user_id: str, email: str, firebase_id_token: str) -> dict:
    """
    Link an email address to an existing user account.
    
    Args:
        current_user_id: Current user's Firebase UID
        email: Email address to link (should be verified via email link)
        firebase_id_token: Firebase ID token from email auth
        
    Returns:
        Dict with success status and message
    """
    try:
        # Verify the Firebase token contains the email
        decoded_token = verify_token(firebase_id_token)
        if not decoded_token:
            return {"success": False, "error": "Invalid Firebase token"}
        
        token_email = decoded_token.get('email')
        if token_email != email:
            return {"success": False, "error": "Email address mismatch"}
        
        # Check if email is already associated with another account
        existing_user = get_user_by_email(email)
        if existing_user and existing_user.get('id') != current_user_id:
            return {
                "success": False, 
                "error": "This email address is already associated with another account"
            }
        
        # Update current user's email
        update_data = {
            'email': email,
            'emailVerifiedAt': decoded_token.get('auth_time')
        }
        
        success = update_user(current_user_id, update_data)
        if success:
            logger.info(f"Successfully linked email {email} to user {current_user_id}")
            return {"success": True, "message": "Email address linked successfully"}
        else:
            return {"success": False, "error": "Failed to update user record"}
            
    except Exception as e:
        logger.error(f"Error linking email to account: {e}")
        return {"success": False, "error": "An unexpected error occurred"}

def check_auth_method_availability(phone_number: str = None, email: str = None) -> dict:
    """
    Check if phone number or email is available for linking.
    
    Args:
        phone_number: Phone number to check
        email: Email address to check
        
    Returns:
        Dict with availability status
    """
    result = {"phone_available": True, "email_available": True}
    
    if phone_number:
        existing_user = find_user_by_phone(phone_number)
        if existing_user and not existing_user.get('isTemporary', False):
            result["phone_available"] = False
            result["phone_user_id"] = existing_user.get('id')
    
    if email:
        existing_user = get_user_by_email(email)
        if existing_user and not existing_user.get('isTemporary', False):
            result["email_available"] = False
            result["email_user_id"] = existing_user.get('id')
    
    return result

def get_user_auth_methods(user_id: str) -> dict:
    """
    Get the current authentication methods for a user.
    
    Args:
        user_id: User's Firebase UID
        
    Returns:
        Dict with current auth methods
    """
    user_data = get_user(user_id)
    if not user_data:
        return {"error": "User not found"}
    
    return {
        "has_phone": bool(user_data.get('phoneNumber')),
        "has_email": bool(user_data.get('email')),
        "phone_number": user_data.get('phoneNumber', ''),
        "email": user_data.get('email', ''),
        "phone_verified_at": user_data.get('phoneVerifiedAt'),
        "email_verified_at": user_data.get('emailVerifiedAt')
    }
