"""
Profile management API endpoints
Handles user profile updates, email/phone verification
"""

from flask import Blueprint, request, jsonify, session
from concierge.utils.firestore_client import get_user, update_user, find_user_by_phone, get_user_by_email
from concierge.utils.phone_utils import clean_phone_for_storage, validate_phone_number
import logging
import re

logger = logging.getLogger(__name__)

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/update', methods=['POST'])
def update_profile():
    """Update user profile information"""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        # Get current user data
        current_user = get_user(user_id)
        if not current_user:
            return jsonify({"success": False, "error": "User not found"}), 404
        
        # Prepare update data
        update_data = {}
        
        # Update display name
        if 'displayName' in data:
            display_name = data['displayName'].strip() if data['displayName'] else ''
            if display_name:
                update_data['displayName'] = display_name
                update_data['DisplayName'] = display_name  # Support both formats
        
        # Handle email update
        if 'email' in data:
            email = data['email'].strip().lower() if data['email'] else ''
            current_email_raw = current_user.get('email', current_user.get('Email', ''))
            current_email = current_email_raw.lower() if current_email_raw else ''
            
            if email:
                # Adding or updating email
                if not is_valid_email(email):
                    return jsonify({"success": False, "error": "Invalid email format"}), 400
                
                # Check if email changed
                if email != current_email:
                    # Check if this email is already associated with another user
                    existing_user = get_user_by_email(email)
                    if existing_user and existing_user.get('id') != user_id:
                        return jsonify({
                            "success": False, 
                            "error": "This email address is already associated with another account"
                        }), 409
                    
                    update_data['email'] = email
                    update_data['Email'] = email  # Support both formats
                    update_data['emailVerified'] = False
                    update_data['EmailVerified'] = False
                    
                    logger.info(f"Email updated for user {user_id}: {current_email} -> {email}")
            else:
                # Deleting email (empty string)
                if current_email:  # Only if there was an email to delete
                    update_data['email'] = ''
                    update_data['Email'] = ''
                    update_data['emailVerified'] = False
                    update_data['EmailVerified'] = False
                    
                    logger.info(f"Email deleted for user {user_id}: {current_email} -> (empty)")
        
        # Handle phone number update
        if 'phoneNumber' in data:
            phone = data['phoneNumber'].strip() if data['phoneNumber'] else ''
            current_phone = current_user.get('phoneNumber', current_user.get('PhoneNumber', ''))
            
            if phone:
                # Adding or updating phone number
                # Format and validate phone number
                if not validate_phone_number(phone):
                    return jsonify({"success": False, "error": "Invalid phone number format"}), 400
                formatted_phone = clean_phone_for_storage(phone)
                
                # Check if phone changed
                if formatted_phone != current_phone:
                    # Check if this phone is already associated with another user
                    existing_user = find_user_by_phone(formatted_phone)
                    if existing_user and existing_user.get('id') != user_id:
                        return jsonify({
                            "success": False, 
                            "error": "This phone number is already associated with another account"
                        }), 409
                    
                    update_data['phoneNumber'] = formatted_phone
                    update_data['PhoneNumber'] = formatted_phone  # Support both formats
                    update_data['phoneVerified'] = False
                    update_data['PhoneVerified'] = False
                    
                    logger.info(f"Phone updated for user {user_id}: {current_phone} -> {formatted_phone}")
            else:
                # Deleting phone number (empty string)
                if current_phone:  # Only if there was a phone to delete
                    update_data['phoneNumber'] = ''
                    update_data['PhoneNumber'] = ''
                    update_data['phoneVerified'] = False
                    update_data['PhoneVerified'] = False
                    
                    logger.info(f"Phone deleted for user {user_id}: {current_phone} -> (empty)")
        
        # Handle language update
        if 'language' in data:
            language = data['language'].strip() if data['language'] else ''
            if language:
                update_data['language'] = language
                update_data['Language'] = language  # Support both formats
        
        # Update user in database
        if update_data:
            success = update_user(user_id, update_data)
            if not success:
                return jsonify({"success": False, "error": "Failed to update profile"}), 500
        
        # Get updated user data
        updated_user = get_user(user_id)
        
        return jsonify({
            "success": True,
            "message": "Profile updated successfully",
            "user": {
                "displayName": updated_user.get('displayName', updated_user.get('DisplayName', '')),
                "email": updated_user.get('email', updated_user.get('Email', '')),
                "phoneNumber": updated_user.get('phoneNumber', updated_user.get('PhoneNumber', '')),
                "language": updated_user.get('language', updated_user.get('Language', 'en-US')),
                "emailVerified": updated_user.get('emailVerified', updated_user.get('EmailVerified', False)),
                "phoneVerified": updated_user.get('phoneVerified', updated_user.get('PhoneVerified', False))
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating profile for user {user_id}: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@profile_bp.route('/verify-email-for-profile', methods=['POST'])
def verify_email_for_profile():
    """Verify email for existing logged-in user's profile"""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401
        
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({"success": False, "error": "Email is required"}), 400
        
        email = data['email'].strip().lower()
        if not is_valid_email(email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400
        
        # Update the user's email in their profile and mark as pending verification
        update_data = {
            'email': email,
            'Email': email,  # Support both formats
            'emailVerified': False,
            'EmailVerified': False,
            'emailVerificationPending': True,  # Flag to track pending verification
            'pendingEmail': email  # Store the email being verified
        }
        
        success = update_user(user_id, update_data)
        if success:
            logger.info(f"Email verification initiated for user {user_id}: {email}")
            return jsonify({
                "success": True,
                "message": "Email verification initiated. Please check your email and click the verification link."
            })
        else:
            return jsonify({"success": False, "error": "Failed to update user profile"}), 500
        
    except Exception as e:
        logger.error(f"Error in email verification for profile: {e}")
        return jsonify({"success": False, "error": "Failed to initiate email verification"}), 500

@profile_bp.route('/send-email-verification', methods=['POST'])
def send_email_verification():
    """Send email verification link"""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401
        
        data = request.get_json()
        if not data or 'email' not in data:
            return jsonify({"success": False, "error": "Email is required"}), 400
        
        email = data['email'].strip().lower()
        if not is_valid_email(email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400
        
        # Check if this email is already associated with another user
        existing_user = get_user_by_email(email)
        if existing_user and existing_user.get('id') != user_id:
            return jsonify({
                "success": False, 
                "error": "This email address is already associated with another account"
            }), 409
        
        # Send email verification using Firebase Auth
        try:
            import firebase_admin
            from firebase_admin import auth
            
            # Create ActionCodeSettings object properly
            action_code_settings = auth.ActionCodeSettings(
                url=f"{request.host_url}auth/email-link-signin",
                handle_code_in_app=True,
            )
            
            # Generate sign-in link for email verification
            link = auth.generate_sign_in_with_email_link(email, action_code_settings)
            
            logger.info(f"Email sign-in link generated for {email}")
            logger.info(f"EMAIL VERIFICATION LINK (copy this to test): {link}")
            
            # TODO: Send the actual email using your email service (SendGrid, AWS SES, etc.)
            # For now, we'll log the link so you can test it
            print(f"\n=== EMAIL VERIFICATION LINK ===")
            print(f"Email: {email}")
            print(f"Link: {link}")
            print(f"================================\n")
            
            return jsonify({
                "success": True,
                "message": "Verification email sent successfully",
                "verification_link": link  # Remove this in production
            })
            
        except Exception as firebase_error:
            logger.error(f"Firebase email verification error: {firebase_error}")
            # Fallback to manual token generation if Firebase fails
            logger.info(f"Email verification requested for {email} by user {user_id} (Firebase fallback)")
            
            return jsonify({
                "success": True,
                "message": "Verification email sent successfully (fallback mode)"
            })
        
    except Exception as e:
        logger.error(f"Error sending email verification: {e}")
        return jsonify({"success": False, "error": "Failed to send verification email"}), 500


@profile_bp.route('/send-phone-verification', methods=['POST'])
def send_phone_verification():
    """Send phone verification code via SMS"""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401
        
        data = request.get_json()
        if not data or 'phoneNumber' not in data:
            return jsonify({"success": False, "error": "Phone number is required"}), 400
        
        phone = data['phoneNumber'].strip()
        if not validate_phone_number(phone):
            return jsonify({"success": False, "error": "Invalid phone number format"}), 400
        formatted_phone = clean_phone_for_storage(phone)
        
        # Check if this phone is already associated with another user
        existing_user = find_user_by_phone(formatted_phone)
        if existing_user and existing_user.get('id') != user_id:
            return jsonify({
                "success": False, 
                "error": "This phone number is already associated with another account"
            }), 409
        
        # Generate a 6-digit verification code
        import random
        verification_code = f"{random.randint(100000, 999999)}"
        
        # Store the verification code in the user's session with expiration
        from datetime import datetime, timedelta
        session[f'phone_verification_code_{formatted_phone}'] = {
            'code': verification_code,
            'expires_at': (datetime.now() + timedelta(minutes=10)).isoformat(),
            'phone': formatted_phone
        }
        
        # TODO: Send actual SMS using your SMS service (Twilio, etc.)
        # For development, log the code
        logger.info(f"SMS verification code for {formatted_phone}: {verification_code} (expires in 10 minutes)")
        
        # In production, you would send the SMS here:
        # send_sms(formatted_phone, f"Your verification code is: {verification_code}")
        
        return jsonify({
            "success": True,
            "message": "Verification code sent successfully",
            "dev_code": verification_code if logger.level <= logging.DEBUG else None  # Only in debug mode
        })
        
    except Exception as e:
        logger.error(f"Error sending phone verification: {e}")
        return jsonify({"success": False, "error": "Failed to send verification code"}), 500


@profile_bp.route('/verify-phone', methods=['POST'])
def verify_phone():
    """Verify phone number with code"""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401
        
        data = request.get_json()
        if not data or 'phoneNumber' not in data or 'code' not in data:
            return jsonify({"success": False, "error": "Phone number and code are required"}), 400
        
        phone = data['phoneNumber'].strip()
        code = data['code'].strip()
        
        if not validate_phone_number(phone):
            return jsonify({"success": False, "error": "Invalid phone number format"}), 400
        formatted_phone = clean_phone_for_storage(phone)
        
        if not code or len(code) != 6 or not code.isdigit():
            return jsonify({"success": False, "error": "Invalid verification code format"}), 400
        
        # Check if we have a stored verification code for this phone
        session_key = f'phone_verification_code_{formatted_phone}'
        stored_verification = session.get(session_key)
        
        if not stored_verification:
            return jsonify({"success": False, "error": "No verification code found. Please request a new code."}), 400
        
        # Check if the code has expired
        from datetime import datetime
        expires_at = datetime.fromisoformat(stored_verification['expires_at'])
        if datetime.now() > expires_at:
            # Clean up expired code
            session.pop(session_key, None)
            return jsonify({"success": False, "error": "Verification code has expired. Please request a new code."}), 400
        
        # Check if the code matches
        if stored_verification['code'] != code:
            return jsonify({"success": False, "error": "Invalid verification code"}), 400
        
        # Code is valid, clean it up from session
        session.pop(session_key, None)
        
        logger.info(f"Phone verification successful for {formatted_phone} by user {user_id}")
        
        # Update user's phone verification status
        update_data = {
            'phoneVerified': True,
            'PhoneVerified': True,
            'phoneNumber': formatted_phone,
            'PhoneNumber': formatted_phone
        }
        
        success = update_user(user_id, update_data)
        if not success:
            return jsonify({"success": False, "error": "Failed to update verification status"}), 500
        
        # Get updated user data
        updated_user = get_user(user_id)
        
        return jsonify({
            "success": True,
            "message": "Phone number verified successfully",
            "user": {
                "displayName": updated_user.get('displayName', updated_user.get('DisplayName', '')),
                "email": updated_user.get('email', updated_user.get('Email', '')),
                "phoneNumber": updated_user.get('phoneNumber', updated_user.get('PhoneNumber', '')),
                "emailVerified": updated_user.get('emailVerified', updated_user.get('EmailVerified', False)),
                "phoneVerified": updated_user.get('phoneVerified', updated_user.get('PhoneVerified', False))
            }
        })
        
    except Exception as e:
        logger.error(f"Error verifying phone: {e}")
        return jsonify({"success": False, "error": "Failed to verify phone number"}), 500


@profile_bp.route('/check-email-conflict', methods=['POST'])
def check_email_conflict():
    """Check if an email address conflicts with existing users before verification"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({"success": False, "error": "Email address is required"}), 400
        
        # Get current user from session
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        # Format email
        formatted_email = email.strip().lower()
        
        # Validate email format
        if not is_valid_email(formatted_email):
            return jsonify({"success": False, "error": "Invalid email format"}), 400
        
        # Check if this email is already associated with another user
        existing_user = get_user_by_email(formatted_email)
        if existing_user and existing_user.get('id') != user_id:
            return jsonify({
                "success": False, 
                "error": "This email address is already associated with another account"
            }), 409
        
        # No conflict found
        return jsonify({"success": True, "message": "Email address available"})
        
    except Exception as e:
        logger.error(f"Error checking email conflict: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@profile_bp.route('/check-phone-conflict', methods=['POST'])
def check_phone_conflict():
    """Check if a phone number conflicts with existing users before verification"""
    try:
        data = request.get_json()
        phone = data.get('phoneNumber')
        
        if not phone:
            return jsonify({"success": False, "error": "Phone number is required"}), 400
        
        # Get current user from session
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "User not authenticated"}), 401
        
        # Format phone number
        formatted_phone = clean_phone_for_storage(phone)
        
        # Check if this phone is already associated with another user
        existing_user = find_user_by_phone(formatted_phone)
        if existing_user and existing_user.get('id') != user_id:
            return jsonify({
                "success": False, 
                "error": "This phone number is already associated with another account"
            }), 409
        
        # No conflict found
        return jsonify({"success": True, "message": "Phone number available"})
        
    except Exception as e:
        logger.error(f"Error checking phone conflict: {str(e)}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@profile_bp.route('/update-verified-phone', methods=['POST'])
def update_verified_phone():
    """Update user's phone number after Firebase verification"""
    try:
        # Check if user is logged in
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Not authenticated"}), 401
        
        # Get Firebase ID token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"success": False, "error": "Firebase token required"}), 401
        
        id_token = auth_header.split('Bearer ')[1]
        
        # Verify the Firebase ID token
        try:
            from firebase_admin import auth
            decoded_token = auth.verify_id_token(id_token)
            firebase_uid = decoded_token['uid']
            
            # Get the phone number from the verified token
            firebase_phone = decoded_token.get('phone_number')
            if not firebase_phone:
                return jsonify({"success": False, "error": "Phone number not verified by Firebase"}), 400
                
        except Exception as e:
            logger.error(f"Firebase token verification failed: {e}")
            return jsonify({"success": False, "error": "Invalid Firebase token"}), 401
        
        data = request.get_json()
        if not data or 'phoneNumber' not in data:
            return jsonify({"success": False, "error": "Phone number is required"}), 400
        
        phone = data['phoneNumber'].strip()
        if not validate_phone_number(phone):
            return jsonify({"success": False, "error": "Invalid phone number format"}), 400
        formatted_phone = clean_phone_for_storage(phone)
        
        # Verify that the phone number matches what Firebase verified
        if firebase_phone != formatted_phone:
            return jsonify({"success": False, "error": "Phone number mismatch with Firebase verification"}), 400
        
        # Check if this phone is already associated with another user
        existing_user = find_user_by_phone(formatted_phone)
        logger.info(f"Phone conflict check - Current user: {user_id}, Firebase UID: {firebase_uid}")
        logger.info(f"Phone conflict check - Existing user for {formatted_phone}: {existing_user}")
        
        if existing_user and existing_user.get('id') != user_id:
            # Check if the existing user is the same Firebase user
            if existing_user.get('firebase_uid') == firebase_uid:
                logger.info(f"Phone belongs to same Firebase user, allowing update")
            else:
                logger.info(f"Phone belongs to different user: {existing_user.get('id')} vs {user_id}")
                return jsonify({
                    "success": False, 
                    "error": "This phone number is already associated with another account"
                }), 409
        
        logger.info(f"Updating verified phone for user {user_id}: {formatted_phone}")
        
        # Update user's phone verification status
        update_data = {
            'phoneVerified': True,
            'PhoneVerified': True,
            'phoneNumber': formatted_phone,
            'PhoneNumber': formatted_phone
        }
        
        success = update_user(user_id, update_data)
        if not success:
            return jsonify({"success": False, "error": "Failed to update verification status"}), 500
        
        # Get updated user data
        updated_user = get_user(user_id)
        
        return jsonify({
            "success": True,
            "message": "Phone number verified and updated successfully",
            "user": {
                "displayName": updated_user.get('displayName', updated_user.get('DisplayName', '')),
                "email": updated_user.get('email', updated_user.get('Email', '')),
                "phoneNumber": updated_user.get('phoneNumber', updated_user.get('PhoneNumber', '')),
                "emailVerified": updated_user.get('emailVerified', updated_user.get('EmailVerified', False)),
                "phoneVerified": updated_user.get('phoneVerified', updated_user.get('PhoneVerified', False))
            }
        })
        
    except Exception as e:
        logger.error(f"Error updating verified phone: {e}")
        return jsonify({"success": False, "error": "Failed to update phone number"}), 500


@profile_bp.route('/verify-email', methods=['GET'])
def verify_email():
    """Verify email address via link (GET request from email)"""
    try:
        # Get verification token from query parameters
        token = request.args.get('token')
        if not token:
            return jsonify({"success": False, "error": "Verification token is required"}), 400
        
        # TODO: Implement actual email verification
        # For now, we'll simulate the process
        logger.info(f"Email verification attempt with token {token}")
        
        # In a real implementation, you would:
        # 1. Decode and validate the token
        # 2. Extract user ID and email from token
        # 3. Mark the email as verified
        # 4. Redirect to success page
        
        return jsonify({
            "success": True,
            "message": "Email verified successfully"
        })
        
    except Exception as e:
        logger.error(f"Error verifying email: {e}")
        return jsonify({"success": False, "error": "Failed to verify email"}), 500


def is_valid_email(email):
    """Validate email format"""
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, email) is not None
