"""
Magic link routes for guest onboarding system.
Handles magic link generation, validation, phone verification, and access management.
"""

import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, render_template, redirect, url_for, session, jsonify, flash, g, make_response
from concierge.utils.firestore_client import (
    get_magic_link_by_token, verify_magic_link_phone, set_magic_link_guest_name,
    get_reservation, generate_magic_link_url, hash_magic_link_token, update_magic_link,
    create_temporary_user, get_temporary_user, verify_user_pin, update_user,
    create_temporary_id_token, update_user_pin, get_user,
    get_property_by_magic_link_token, find_property_reservations_by_phone
)
from concierge.utils.session_manager import (
    get_session_from_request, set_session_cookie, clear_session_cookie,
    create_session_cookie, validate_session
)

# Setup logger
logger = logging.getLogger(__name__)

# Create Blueprint
magic_bp = Blueprint('magic', __name__, template_folder='../templates')

@magic_bp.route('/magic/<token>')
def magic_link_access(token):
    """
    Handle magic link access - initial landing page.

    Args:
        token: The raw magic link token from URL
    """
    try:
        logger.info(f"Magic link access attempt with token: {token[:8]}...")

        # Note: Flash message filtering is handled in templates to prevent 
        # confusing "You have been logged out" messages for fresh magic link users

        # Try new property-based magic link first
        property_data = get_property_by_magic_link_token(token)
        magic_link_data = None

        if property_data:
            # New property-based magic link
            logger.info(f"Property-based magic link accessed for property: {property_data.get('id')}")
            # Create a compatible magic_link_data structure for backward compatibility
            magic_link_data = {
                'property_id': property_data.get('id'),
                'property_name': property_data.get('name'),
                'is_property_based': True,
                'is_active': True,
                'status': 'active'
            }
        else:
            # Fallback to old reservation-based magic link
            magic_link_data = get_magic_link_by_token(token)
            logger.info(f"Legacy magic link data retrieved: {magic_link_data is not None}")
            if magic_link_data:
                magic_link_data['is_property_based'] = False

        if not magic_link_data:
            logger.warning(f"Invalid or expired magic link accessed: {token[:8]}...")
            return render_template('magic_link_error.html',
                                 error_message="This link is invalid or has expired. Please contact your host for a new link.")

        # Handle property-based vs reservation-based magic links
        reservation = None
        if magic_link_data.get('is_property_based'):
            # Property-based magic link - no reservation needed initially
            logger.info(f"Property-based magic link for property: {magic_link_data.get('property_id')}")
        else:
            # Legacy reservation-based magic link - get reservation data
            reservation_id = magic_link_data.get('reservation_id')
            logger.info(f"Looking for reservation: {reservation_id}")

            reservation = get_reservation(reservation_id)
            logger.info(f"Reservation data retrieved: {reservation is not None}")

            if not reservation:
                logger.error(f"Reservation {reservation_id} not found for magic link")
                return render_template('magic_link_error.html',
                                     error_message="Reservation not found. Please contact your host.")

        # Check for existing session first
        is_valid, user_id, reason = get_session_from_request()
        logger.info(f"Session validation: valid={is_valid}, user_id={user_id}, reason={reason}")

        if is_valid and user_id:
            # Valid session exists, but check if it's for the same magic link
            from concierge.utils.firestore_client import check_magic_link_session
            session_check = check_magic_link_session(token, user_id)
            
            if session_check['valid']:
                logger.info(f"Valid session found for user {user_id} and token {token[:8]}..., redirecting to dashboard")
                return redirect(url_for('magic.magic_link_dashboard', token=token))
            else:
                logger.info(f"Session user {user_id} not associated with token {token[:8]}..., showing PIN screen")
                # Clear the invalid session
                response = make_response(redirect(url_for('magic.magic_link_access', token=token)))
                from concierge.utils.session_manager import clear_session_cookie
                clear_session_cookie(response)
                # Continue to PIN screen

        # No valid session, need PIN verification
        # Check if magic link was previously verified (for backward compatibility)
        current_status = magic_link_data.get('status')
        logger.info(f"Magic link status: {current_status}")

        if current_status == 'partial_verified':
            # Magic link was verified but no session - need PIN re-verification
            logger.info("Magic link verified but no session, requiring PIN re-verification")

        # Handle verification context based on magic link type
        if magic_link_data.get('is_property_based'):
            # Property-based magic link - show phone input form
            logger.info(f"Property-based magic link - showing phone verification form")

            context = {
                'token': token,
                'property_name': magic_link_data.get('property_name', 'Property'),
                'is_property_based': True,
                'verification_attempts': 0,
                'max_attempts': 5
            }

            logger.info(f"Rendering verification page for property: {context['property_name']}")
            return render_template('magic_link_verify.html', **context)
        else:
            # Legacy reservation-based magic link - get phone from reservation
            phone_number = reservation.get('guestPhoneNumber') or reservation.get('GuestPhoneNumber')
            guest_phone_last4 = reservation.get('guestPhoneLast4')
            logger.info(f"Phone number found: {phone_number is not None}")
            logger.info(f"Guest phone last 4: {guest_phone_last4}")

            # Use full phone number if available, otherwise use last 4 digits field
            if phone_number and len(phone_number) >= 4:
                last_4_digits = phone_number[-4:]
                logger.info(f"Using full phone number, last 4 digits: {last_4_digits}")
            elif guest_phone_last4:
                last_4_digits = guest_phone_last4
                logger.info(f"Using guestPhoneLast4 field: {last_4_digits}")
            else:
                logger.error(f"No phone number information in reservation")
                return render_template('magic_link_error.html',
                                     error_message="Phone number not found in reservation. Please contact your host.")
            logger.info(f"Last 4 digits for verification: {last_4_digits}")

            # Prepare context for verification page
            context = {
                'token': token,
                'property_name': reservation.get('propertyName', 'Property'),
                'start_date': reservation.get('startDate'),
                'end_date': reservation.get('endDate'),
                'last_4_digits_hint': f"***-***-{last_4_digits}",
                'verification_attempts': magic_link_data.get('verification_attempts', 0),
                'max_attempts': 5,
                'is_property_based': False
            }

            logger.info(f"Rendering verification page for property: {context['property_name']}")
            return render_template('magic_link_verify.html', **context)

    except Exception as e:
        logger.error(f"Error handling magic link access: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return render_template('magic_link_error.html',
                             error_message="An error occurred. Please try again or contact your host.")

@magic_bp.route('/magic/<token>/verify', methods=['POST'])
def verify_phone(token):
    """
    Handle PIN verification for magic link (creates temporary user and session).

    Args:
        token: The raw magic link token
    """
    try:
        last_4_digits = request.form.get('last_4_digits', '').strip()

        if not last_4_digits or len(last_4_digits) != 4 or not last_4_digits.isdigit():
            flash('Please enter exactly 4 digits.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))

        # Try new property-based magic link first
        property_data = get_property_by_magic_link_token(token)
        magic_link_data = None
        reservation = None
        phone_number = None

        if property_data:
            # New property-based magic link
            logger.info(f"Property-based magic link verification for property: {property_data.get('id')}")

            # Check if user has already selected a reservation from disambiguation screen
            selected_reservation_id = session.get('selected_reservation_id')
            if selected_reservation_id:
                # Use the selected reservation
                reservation = get_reservation(selected_reservation_id)
                if reservation:
                    phone_number = reservation.get('guest_phone') or reservation.get('guestPhoneNumber') or reservation.get('GuestPhoneNumber')
                    logger.info(f"Using selected reservation: {reservation.get('id')}")
                    # Clear the selection from session
                    session.pop('selected_reservation_id', None)
                else:
                    flash('Selected reservation not found.', 'error')
                    return redirect(url_for('magic.magic_link_access', token=token))
            else:
                # Find matching reservations for this property
                matching_reservations = find_property_reservations_by_phone(property_data.get('id'), last_4_digits)

                if not matching_reservations:
                    flash('No reservations found for this property with that phone number.', 'error')
                    return redirect(url_for('magic.magic_link_access', token=token))
                elif len(matching_reservations) == 1:
                    # Single match - proceed with this reservation
                    reservation = matching_reservations[0]
                    logger.info(f"Single reservation match found: {reservation.get('id')}")
                else:
                    # Multiple matches - show disambiguation screen
                    logger.info(f"Multiple reservations found ({len(matching_reservations)}) - showing disambiguation")
                    return render_template('magic_link_disambiguation.html',
                                         token=token,
                                         reservations=matching_reservations,
                                         property_name=property_data.get('name'))

            # Create compatible magic_link_data structure
            magic_link_data = {
                'property_id': property_data.get('id'),
                'property_name': property_data.get('name'),
                'reservation_id': reservation.get('id'),
                'is_property_based': True,
                'is_active': True,
                'status': 'active'
            }
        else:
            # Fallback to old reservation-based magic link
            magic_link_data = get_magic_link_by_token(token)
            if not magic_link_data:
                flash('Invalid magic link.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))

            reservation_id = magic_link_data.get('reservation_id')
            reservation = get_reservation(reservation_id)
            if not reservation:
                flash('Reservation not found.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))

        # Extract phone number from reservation for enhanced user detection
        phone_number = None
        guest_phone_last4 = None

        if reservation:
            # Try different phone number field names
            phone_number = (reservation.get('guestPhoneNumber') or
                          reservation.get('GuestPhoneNumber') or
                          reservation.get('guest_phone'))
            guest_phone_last4 = reservation.get('guestPhoneLast4')

            # Use either full phone number or just the last 4 digits
            if phone_number:
                logger.info(f"Using full phone number for verification: {phone_number}")
            elif guest_phone_last4:
                phone_number = guest_phone_last4
                logger.info(f"Using guestPhoneLast4 for verification: {guest_phone_last4}")
            else:
                logger.error(f"No phone number found in reservation {reservation.get('id', 'unknown')}")
                flash('Phone number not found in reservation.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))
        else:
            logger.error(f"No reservation found for phone number extraction")
            flash('Reservation not found.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))

        from concierge.utils.firestore_client import enhanced_user_detection
        detection_result = enhanced_user_detection(phone_number, last_4_digits, token)
        
        logger.info(f"Enhanced user detection result: {detection_result}")
        
        if detection_result['status'] == 'temp_user_access':
            # Existing temp user - grant access
            user_id = detection_result['user_id']
            existing_name = detection_result.get('existing_name')
            
            # Update magic link status (only for reservation-based magic links)
            if not magic_link_data.get('is_property_based'):
                token_hash = hash_magic_link_token(token)
                update_magic_link(token_hash, {
                    'status': 'verified',
                    'verified_user_id': user_id,
                    'verification_method': 'temp_user_existing'
                })
            
            # Create session
            response = make_response()
            set_session_cookie(response, user_id)
            
            # If user has a name, go directly to dashboard; otherwise go to name collection
            if existing_name and existing_name.strip():
                logger.info(f"Existing temp user {user_id} has name '{existing_name}', going directly to dashboard")
                response.location = url_for('magic.magic_link_dashboard', token=token)
            else:
                logger.info(f"Existing temp user {user_id} has no name, going to name collection")
                response.location = url_for('magic.collect_name', token=token)
            
            response.status_code = 302
            return response
            
        elif detection_result['status'] == 'migrated_user_confirmation':
            # Need to confirm if user is the same person who migrated
            return render_template('magic_link_user_confirmation.html',
                                 token=token,
                                 user_name=detection_result['temp_user_name'],
                                 message=detection_result['message'])
            
        elif detection_result['status'] == 'new_temp_user_needed':
            # Create new temp user and show name collection
            pin_verified = True
            verification_method = 'phone_last_4'
            user_id = None  # Will be created below
            is_permanent_user = False
            
        elif detection_result['status'] == 'create_new_temp_user':
            # Create new temp user (different from existing migrated one)
            pin_verified = True
            verification_method = 'new_temp_after_migration'
            user_id = None  # Will be created below
            is_permanent_user = False
            
        elif detection_result['status'] == 'verification_failed':
            pin_verified = False
            
        else:
            # Error case
            flash('An error occurred during verification. Please try again.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))

        # Handle verification result
        if pin_verified:
            logger.info(f"PIN verification successful for token {token[:8]}... (method: {verification_method})")

            # Create new temporary user for name collection
            token_hash = hash_magic_link_token(token)
            
            # Generate unique temp user ID
            if verification_method == 'new_temp_after_migration':
                # Create a new unique temp user ID for users after migration
                import uuid
                unique_suffix = str(uuid.uuid4())[:8]
                temp_user_id = f"temp_magic_{token_hash[:8]}_{unique_suffix}"
            else:
                temp_user_id = f"temp_magic_{token_hash[:12]}"

            # Check if temporary user already exists
            existing_user = get_temporary_user(temp_user_id)
            if existing_user:
                logger.info(f"Using existing temporary user: {temp_user_id}")
                user_id = temp_user_id
            else:
                # Create new temporary user
                logger.info(f"Creating new temporary user for token {token[:8]}...")
                user_id = create_temporary_user(magic_link_data, reservation)
                if not user_id:
                    flash('Error creating user session. Please try again.', 'error')
                    return redirect(url_for('magic.magic_link_access', token=token))

            # Update magic link status (only for reservation-based magic links)
            if not magic_link_data.get('is_property_based'):
                update_magic_link(token_hash, {
                    'status': 'partial_verified',
                    'verified_last_4_digits': last_4_digits,
                    'temp_user_id': user_id,
                    'verification_method': verification_method
                })

            # Always redirect to name collection screen for new temp users
            response = make_response(redirect(url_for('magic.collect_name', token=token)))
            set_session_cookie(response, user_id)

            logger.info(f"Session created for temporary user {user_id}")
            return response

        else:
            # PIN verification failed
            attempts = magic_link_data.get('verification_attempts', 0) + 1

            # Update magic link status (only for reservation-based magic links)
            if not magic_link_data.get('is_property_based'):
                update_magic_link(hash_magic_link_token(token), {
                    'verification_attempts': attempts
                })

            if attempts >= 5:
                flash('Too many verification attempts. Please contact your host for assistance.', 'error')
                return render_template('magic_link_error.html',
                                     error_message="Verification failed. Too many attempts. Please contact your host.")
            else:
                flash(f'Incorrect PIN. Please try again. ({attempts}/5 attempts)', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))

    except Exception as e:
        logger.error(f"Error verifying PIN for magic link: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        flash('An error occurred during verification. Please try again.', 'error')
        return redirect(url_for('magic.magic_link_access', token=token))

@magic_bp.route('/magic/<token>/confirm-user', methods=['POST'])
def confirm_migrated_user(token):
    """
    Handle user confirmation for migrated temporary users.
    
    Args:
        token: The raw magic link token
    """
    try:
        confirmation = request.form.get('confirmation')
        
        if confirmation == 'yes':
            # User confirmed they are the same person - trigger OTP for permanent account
            # Get the permanent user ID from the detection result
            magic_link_data = get_magic_link_by_token(token)
            if not magic_link_data:
                flash('Invalid magic link.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))
            
            # Get reservation data to find phone number
            reservation_id = magic_link_data.get('reservation_id')
            reservation = get_reservation(reservation_id)
            if not reservation:
                flash('Reservation not found.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))
            
            phone_number = reservation.get('guestPhoneNumber') or reservation.get('GuestPhoneNumber')
            
            # Redirect to phone login with OTP
            return render_template('phone_login.html',
                                 token=token,
                                 phone_number=phone_number,
                                 is_magic_link=True,
                                 form_action=url_for('magic.process_phone_login', token=token),
                                 message="Please verify your phone number to access your permanent account.")
        
        elif confirmation == 'no':
            # User is someone else - create new temp user and skip PIN entry
            magic_link_data = get_magic_link_by_token(token)
            if not magic_link_data:
                flash('Invalid magic link.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))
            
            # Get reservation data for new temp user creation
            reservation_id = magic_link_data.get('reservation_id')
            reservation = get_reservation(reservation_id)
            if not reservation:
                flash('Reservation not found.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))
            
            # Create new temporary user directly (skip PIN verification)
            token_hash = hash_magic_link_token(token)
            
            # Generate unique temp user ID for users after migration rejection
            import uuid
            unique_suffix = str(uuid.uuid4())[:8]
            temp_user_id = f"temp_magic_{token_hash[:8]}_{unique_suffix}"
            
            # Create new temporary user
            user_id = create_temporary_user(magic_link_data, reservation)
            if not user_id:
                flash('Error creating user session. Please try again.', 'error')
                return redirect(url_for('magic.magic_link_access', token=token))
            
            # Update magic link status (only for reservation-based magic links)
            if not magic_link_data.get('is_property_based'):
                update_magic_link(token_hash, {
                    'status': 'partial_verified',
                    'temp_user_id': user_id,
                    'verification_method': 'new_temp_after_migration_rejection',
                    'user_confirmation': 'rejected'
                })
            
            # Set session and redirect directly to name collection
            response = make_response(redirect(url_for('magic.collect_name', token=token)))
            set_session_cookie(response, user_id)
            
            flash('Creating a new temporary account for you.', 'info')
            logger.info(f"Created new temp user {user_id} after migration rejection, skipping PIN verification")
            return response
        
        else:
            flash('Invalid confirmation response.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))
            
    except Exception as e:
        logger.error(f"Error in user confirmation: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('magic.magic_link_access', token=token))

@magic_bp.route('/magic/<token>/phone-login')
def show_phone_login(token):
    """
    Show phone login form for users with existing accounts.
    
    Args:
        token: The raw magic link token
    """
    try:
        # Validate magic link
        magic_link_data = get_magic_link_by_token(token)
        if not magic_link_data:
            flash('Invalid magic link.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))
        
        return render_template('phone_login.html',
                             token=token,
                             is_magic_link=True,
                             form_action=url_for('magic.process_phone_login', token=token),
                             message="Enter your phone number to login to your existing account.")
        
    except Exception as e:
        logger.error(f"Error showing phone login: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('magic.magic_link_access', token=token))

@magic_bp.route('/magic/<token>/process-phone-login', methods=['POST'])
def process_phone_login(token):
    """
    Process phone login from magic link.
    
    Args:
        token: The raw magic link token
    """
    try:
        phone_number = request.form.get('phone_number', '').strip()
        
        if not phone_number:
            flash('Phone number is required.', 'error')
            return redirect(url_for('magic.confirm_migrated_user', token=token))
        
        # Validate phone number format
        from concierge.utils.phone_utils import validate_phone_number, clean_phone_for_storage
        
        if not validate_phone_number(phone_number):
            flash('Please enter a valid phone number.', 'error')
            return render_template('phone_login.html',
                                 token=token,
                                 phone_number=phone_number,
                                 is_magic_link=True,
                                 form_action=url_for('magic.process_phone_login', token=token),
                                 message="Please enter a valid phone number.")
        
        # Clean phone number for lookup
        clean_phone = clean_phone_for_storage(phone_number)
        
        # Find users with this phone number
        from concierge.utils.firestore_client import find_users_by_phone_flexible
        users = find_users_by_phone_flexible(clean_phone)
        
        # Filter for permanent users only
        permanent_users = [user for user in users if not user.get('isTemporary', True)]
        
        if not permanent_users:
            # No permanent user found - redirect to phone login to continue normal signup
            flash('No account found with this phone number. Continue with phone verification to create your account.', 'info')
            # Store magic link context for later use
            session['magic_link_signup'] = {
                'token': token,
                'phone_number': clean_phone
            }
            return redirect(url_for('auth.phone_login'))
        
        # Store phone login data in session for OTP verification
        session['phone_login'] = {
            'phone_number': clean_phone,
            'token': token,
            'permanent_users': [user['id'] for user in permanent_users]
        }
        
        # Redirect to OTP verification
        return render_template('otp_verification.html',
                             token=token,
                             phone_number=clean_phone,
                             is_magic_link=True,
                             source='phone_login',
                             form_action=url_for('magic.complete_verification', token=token))
        
    except Exception as e:
        logger.error(f"Error processing phone login: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('magic.magic_link_access', token=token))

@magic_bp.route('/magic/<token>/phone-login-complete', methods=['POST'])
def phone_login_complete(token):
    """
    Complete phone login after OTP verification.
    
    Args:
        token: The raw magic link token
    """
    try:
        # Get phone login data from session
        phone_login_data = session.get('phone_login')
        if not phone_login_data:
            return jsonify({'error': 'Phone login session expired'}), 400
        
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        id_token = data.get('idToken')
        firebase_phone = data.get('phoneNumber')
        firebase_uid = data.get('uid')
        
        if not all([id_token, firebase_phone, firebase_uid]):
            return jsonify({'error': 'Missing verification data'}), 400
        
        # Verify the ID token with Firebase Admin
        try:
            from firebase_admin import auth as admin_auth
            decoded_token = admin_auth.verify_id_token(id_token, clock_skew_seconds=30)
            verified_uid = decoded_token['uid']
            verified_phone = decoded_token.get('phone_number')
            
            if verified_uid != firebase_uid or verified_phone != firebase_phone:
                return jsonify({'error': 'Token verification failed'}), 400
                
        except Exception as e:
            logger.error(f"Firebase token verification failed: {e}")
            return jsonify({'error': 'Invalid verification token'}), 400
        
        # Find the permanent user
        from concierge.utils.phone_utils import phones_match
        permanent_user_id = None
        
        for user_id in phone_login_data['permanent_users']:
            user_data = get_user(user_id)
            if user_data and phones_match(user_data.get('phoneNumber', ''), firebase_phone):
                permanent_user_id = user_id
                break
        
        if not permanent_user_id:
            return jsonify({'error': 'User account not found'}), 404
        
        # Attach reservation to permanent user (for reservation-based magic links)
        # This should happen for both profile updates and regular logins if there's a reservation
        logger.info(f"Looking up magic link data for token {token[:8]}...")
        
        # NEW: Check for preserved reservations first (supports cross-phone verification)
        preserved_reservation_ids = phone_login_data.get('preserved_reservation_ids', [])
        reservation_id = None
        
        if preserved_reservation_ids:
            # Use preserved reservation from initial 4-digit verification
            # This enables cross-phone verification for group bookings and multiple phone scenarios
            reservation_id = preserved_reservation_ids[0]  # Use first preserved reservation
            logger.info(f"Using preserved reservation {reservation_id} from initial verification (cross-phone verification enabled)")
        else:
            # Fallback to original phone-based lookup logic
            logger.info("No preserved reservations found, falling back to phone-based lookup")
            
            # Try property-based magic link first
            property_data = get_property_by_magic_link_token(token)
            
            if property_data:
                logger.info(f"Property-based magic link found for property: {property_data.get('id')}")
                # For property-based magic links, we need to find the reservation by phone number
                from concierge.utils.firestore_client import find_property_reservations_by_phone
                from concierge.utils.phone_utils import get_phone_last_4
                
                phone_last_4 = get_phone_last_4(firebase_phone)
                matching_reservations = find_property_reservations_by_phone(property_data.get('id'), phone_last_4)
                
                if matching_reservations:
                    # Use the first matching reservation (there should typically be one after verification)
                    reservation_id = matching_reservations[0].get('id')
                    logger.info(f"Found reservation {reservation_id} for property-based magic link")
                else:
                    logger.warning(f"No matching reservations found for property {property_data.get('id')} and phone ending {phone_last_4}")
            else:
                # Fallback to reservation-based magic link
                magic_link_data = get_magic_link_by_token(token)
                logger.info(f"Reservation-based magic link data found: {bool(magic_link_data)}")
                if magic_link_data:
                    logger.info(f"Magic link data keys: {list(magic_link_data.keys())}")
                    reservation_id = magic_link_data.get('reservation_id')
                    logger.info(f"Reservation ID from magic link: {reservation_id}")
                else:
                    logger.warning(f"No magic link data found for token {token[:8]}...")
        
        # Attach reservation if found
        if reservation_id:
            logger.info(f"Attaching reservation {reservation_id} to permanent user {permanent_user_id}")
            attach_success = attach_reservation_to_permanent_user(permanent_user_id, reservation_id, token)
            if attach_success:
                logger.info(f"Successfully attached reservation to user {permanent_user_id}")
            else:
                logger.error(f"Failed to attach reservation to user {permanent_user_id}")
        else:
            logger.info(f"No reservation found to attach for token {token[:8]}...")
            # For property-based magic links, provide helpful guidance
            if not preserved_reservation_ids:  # Only show this guidance if we didn't have preserved reservations
                property_data = get_property_by_magic_link_token(token)
                if property_data:
                    logger.warning(f"Property-based magic link: No reservation found for user {permanent_user_id} with phone ending {get_phone_last_4(firebase_phone)} at property {property_data.get('name')}")
                    logger.info(f"User may need to use the phone number associated with their reservation at this property")
        
        # Clear phone login session data
        session.pop('phone_login', None)
        
        # Create session for permanent user
        from concierge.utils.session_manager import set_session_cookie
        response = make_response(jsonify({
            'success': True,
            'message': 'Login successful',
            'user_id': permanent_user_id
        }))
        set_session_cookie(response, permanent_user_id)
        
        return response
        
    except Exception as e:
        logger.error(f"Error completing phone login: {e}")
        return jsonify({'error': 'Login failed'}), 500

@magic_bp.route('/magic/<token>/name')
def collect_name(token):
    """
    Optional name collection page with session validation.

    Args:
        token: The raw magic link token
    """
    try:
        # Validate session
        is_valid, user_id, reason = get_session_from_request()
        if not is_valid or not user_id:
            return redirect(url_for('magic.magic_link_access', token=token))

        # Get temporary user data
        temp_user = get_temporary_user(user_id)
        if not temp_user:
            # Clear invalid session and redirect
            response = make_response(redirect(url_for('magic.magic_link_access', token=token)))
            clear_session_cookie(response)
            return response

        # Get reservation data for context
        reservation_ids = temp_user.get('reservationIds', [])
        if reservation_ids:
            reservation = get_reservation(reservation_ids[0])
        else:
            reservation = None

        # Check if user already has a name to prepopulate
        existing_name = temp_user.get('displayName', '')
        
        context = {
            'token': token,
            'property_name': reservation.get('propertyName', 'Property') if reservation else 'Property',
            'guest_name_provided': existing_name if existing_name else '',
            'user_id': user_id,
            'prepopulate_name': existing_name if existing_name else ''
        }

        return render_template('magic_link_name.html', **context)

    except Exception as e:
        logger.error(f"Error in name collection page: {e}")
        return redirect(url_for('magic.magic_link_access', token=token))

@magic_bp.route('/magic/<token>/name', methods=['POST'])
def save_name(token):
    """
    Save guest name and optionally phone number to temporary user and proceed to dashboard.
    If phone number is provided, initiate OTP verification for permanent account creation.

    Args:
        token: The raw magic link token
    """
    try:
        # Validate session
        is_valid, user_id, reason = get_session_from_request()
        if not is_valid or not user_id:
            return redirect(url_for('magic.magic_link_access', token=token))

        guest_name = request.form.get('guest_name', '').strip()
        phone_number = request.form.get('phone_number', '').strip()

        # Save the name to temporary user if provided
        if guest_name:
            if not update_user(user_id, {'displayName': guest_name}):
                flash('Error saving name. Proceeding anyway.', 'warning')
            else:
                logger.info(f"Updated name for temporary user {user_id}: {guest_name}")

        # If phone number is provided, initiate upgrade to permanent account
        if phone_number:
            # Validate phone number format
            import re
            phone_regex = r'^\+?[\d\s\-\(\)]{10,}$'
            if not re.match(phone_regex, phone_number):
                flash('Please enter a valid phone number.', 'error')
                return render_template('magic_link_name.html',
                                     token=token,
                                     guest_name_provided=guest_name,
                                     error_message="Please enter a valid phone number.")

            # Clean phone number (remove spaces, dashes, parentheses)
            clean_phone = re.sub(r'[\s\-\(\)]', '', phone_number)
            if not clean_phone.startswith('+'):
                # Assume US number if no country code
                clean_phone = '+1' + clean_phone

            logger.info(f"Phone number provided for user {user_id}: {clean_phone}")

            # Store phone number and name in session for OTP verification
            session['otp_verification'] = {
                'phone_number': clean_phone,
                'guest_name': guest_name,
                'temp_user_id': user_id,  # Use consistent key name
                'source': 'name_collection',  # Track source
                'token': token
            }

            # Redirect to OTP verification page
            return redirect(url_for('magic.verify_otp', token=token))

        # Proceed to dashboard regardless of name/phone saving success
        return redirect(url_for('magic.magic_link_dashboard', token=token))

    except Exception as e:
        logger.error(f"Error saving guest name/phone: {e}")
        # Proceed to dashboard even if saving fails
        return redirect(url_for('magic.magic_link_dashboard', token=token))

@magic_bp.route('/magic/<token>/skip-name')
def skip_name(token):
    """
    Skip name collection and proceed to dashboard.
    If session is invalid, redirect back to PIN verification instead of creating a loop.

    Args:
        token: The raw magic link token
    """
    try:
        # Validate session
        is_valid, user_id, reason = get_session_from_request()
        if not is_valid or not user_id:
            logger.info(f"Skip name called with invalid session, redirecting to PIN verification for token {token[:8]}...")
            return redirect(url_for('magic.magic_link_access', token=token))

        # Proceed to dashboard without saving any name
        return redirect(url_for('magic.magic_link_dashboard', token=token))

    except Exception as e:
        logger.error(f"Error skipping name collection: {e}")
        # If there's an error, redirect to PIN verification instead of dashboard to avoid loops
        return redirect(url_for('magic.magic_link_access', token=token))

@magic_bp.route('/magic/<token>/verify-otp', methods=['GET', 'POST'])
def verify_otp(token):
    """
    Handle OTP verification for phone number upgrade.

    GET: Show OTP verification form
    POST: This route is now deprecated - OTP verification happens via Firebase on frontend
          and is completed via the /complete-verification endpoint

    Args:
        token: The raw magic link token
    """
    try:
        # Check if we have OTP verification data in session
        otp_data = session.get('otp_verification')
        if not otp_data:
            flash('OTP verification session expired. Please try again.', 'error')
            return redirect(url_for('magic.collect_name', token=token))

        if request.method == 'GET':
            # Show OTP verification form with Firebase integration
            return render_template('otp_verification.html',
                                 token=token,
                                 phone_number=otp_data.get('phone_number', ''),
                                 is_magic_link=True,
                                 form_action=url_for('magic.complete_verification', token=token))

        elif request.method == 'POST':
            # This POST handler is kept for backward compatibility but should not be used
            # The frontend now handles OTP verification directly with Firebase
            # and calls /complete-verification when successful

            logger.warning("Deprecated OTP verification POST route called - redirecting to Firebase flow")
            flash('Please use the verification code sent to your phone.', 'info')
            return render_template('otp_verification.html',
                                 token=token,
                                 phone_number=otp_data.get('phone_number', ''),
                                 is_magic_link=True,
                                 form_action=url_for('magic.complete_verification', token=token),
                                 error_message="Please enter the verification code sent to your phone.")

    except Exception as e:
        logger.error(f"Error in OTP verification: {e}")
        flash('An error occurred during verification. Please try again.', 'error')
        return redirect(url_for('magic.collect_name', token=token))

@magic_bp.route('/magic/<token>/profile-phone-verification', methods=['POST'])
def profile_phone_verification(token):
    """
    Handle phone verification from profile modal for temporary and permanent users.
    Sets up OTP session data and returns success for modal-based OTP verification.

    Args:
        token: The raw magic link token
    """
    try:
        # Import session utilities at the top for cross-phone verification
        from concierge.utils.session_manager import get_session_from_request
        
        # Validate session
        is_valid, user_id, _ = get_session_from_request()
        if not is_valid or not user_id:
            return jsonify({"error": "Invalid session"}), 401
        
        # Check if this is a permanent user (Firebase UID) or temporary user
        is_permanent_user = not user_id.startswith('temp_magic_')
        logger.info(f"Profile phone verification: user_id={user_id}, is_permanent_user={is_permanent_user}")
        
        if is_permanent_user:
            # Get permanent user data from Firestore
            from concierge.utils.firestore_client import get_user
            user_data = get_user(user_id)
            if not user_data:
                return jsonify({"error": "User not found"}), 404
            user_display_name = user_data.get('displayName', 'User')
            user_email = user_data.get('email', '')
        else:
            # Get temporary user data
            temp_user = get_temporary_user(user_id)
            if not temp_user:
                return jsonify({"error": "User not found"}), 404
            user_display_name = temp_user.get('displayName', 'Guest')
            user_email = temp_user.get('email', '')

        # Get phone number from request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        phone_number = data.get('phoneNumber', '').strip()
        guest_name = data.get('displayName', '').strip()
        email = data.get('email', '').strip()  # Also capture email from profile modal

        if not phone_number:
            return jsonify({"error": "Phone number is required"}), 400

        # Validate phone number format
        import re
        phone_regex = r'^\+?[\d\s\-\(\)]{10,}$'
        if not re.match(phone_regex, phone_number):
            return jsonify({"error": "Please enter a valid phone number"}), 400

        # Clean phone number (remove spaces, dashes, parentheses)
        clean_phone = re.sub(r'[\s\-\(\)]', '', phone_number)
        if not clean_phone.startswith('+'):
            # Assume US number if no country code
            clean_phone = '+1' + clean_phone

        if is_permanent_user:
            # For permanent users (hosts/existing users), set up phone login data
            # This will route to handle_phone_login_verification which preserves existing roles
            
            # Check if this permanent user accessed through a magic link with specific reservation
            is_valid, session_user_id, _ = get_session_from_request()
            preserved_reservations = []
            
            # If the permanent user is currently in a magic link session, preserve any reservation context
            if is_valid and session_user_id and session_user_id.startswith('temp_magic_'):
                # They started as temp user, now converting to permanent - preserve context
                temp_data = get_temporary_user(session_user_id)
                if temp_data:
                    preserved_reservations = temp_data.get('reservationIds', [])
                    logger.info(f"Permanent user was in temp session - preserving {len(preserved_reservations)} reservations")
            
            session_data = {
                'phone_number': clean_phone,
                'permanent_users': [user_id],  # List of user IDs to check
                'source': 'profile_modal_update',
                'token': token,
                'preserved_reservation_ids': preserved_reservations  # NEW: Preserve reservations for cross-phone verification
            }
            session['phone_login'] = session_data
            logger.info(f"Profile phone verification setup for permanent user {user_id}, phone {clean_phone}")
            logger.info(f"Set session phone_login data with {len(preserved_reservations)} preserved reservations")
        else:
            # For temporary users, set up OTP verification data for temp-to-permanent conversion
            # IMPORTANT: Preserve reservation context from temp user for cross-phone verification
            temp_user_reservations = temp_user.get('reservationIds', [])
            logger.info(f"Preserving reservation context from temp user: {temp_user_reservations}")
            
            session['otp_verification'] = {
                'phone_number': clean_phone,
                'guest_name': guest_name or user_display_name,
                'email': email,  # Preserve email for temp-to-permanent conversion
                'temp_user_id': user_id,
                'source': 'profile_modal',  # Track that this came from profile modal
                'token': token,
                'preserved_reservation_ids': temp_user_reservations  # NEW: Preserve reservations for cross-phone verification
            }
            logger.info(f"Profile phone verification setup for temporary user {user_id}, phone {clean_phone}")
            logger.info(f"Preserved {len(temp_user_reservations)} reservations for cross-phone verification")

        return jsonify({
            "success": True,
            "message": "Ready for OTP verification",
            "phoneNumber": clean_phone,
            "otpUrl": url_for('magic.verify_otp', token=token)
        })

    except Exception as e:
        logger.error(f"Error in profile phone verification: {e}")
        return jsonify({"error": "Verification setup failed"}), 500

@magic_bp.route('/magic/<token>/change-pin', methods=['POST'])
def change_pin(token):
    """
    Change PIN for magic link users (both temporary and permanent).
    Uses OTP verification instead of requiring current PIN.

    Args:
        token: The raw magic link token
    """
    try:
        # Validate session
        is_valid, user_id, _ = get_session_from_request()
        if not is_valid or not user_id:
            return jsonify({"error": "Invalid session"}), 401

        # Get PIN data from request
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        new_pin = data.get('newPin', '').strip()

        if not new_pin:
            return jsonify({"error": "New PIN is required"}), 400

        # Validation
        if len(str(new_pin)) != 4:
            return jsonify({"error": "New PIN must be exactly 4 digits"}), 400

        try:
            # Validate PIN contains only digits
            if not str(new_pin).isdigit():
                return jsonify({"error": "PIN must contain only numbers"}), 400
        except ValueError:
            return jsonify({"error": "PIN must contain only numbers"}), 400
        
        # Update the PIN
        # Note: User authentication is already confirmed through magic link and OTP verification
        success = update_user_pin(user_id, new_pin)
        
        if success:
            logger.info(f"PIN changed successfully for user {user_id} via magic link OTP verification")
            return jsonify({"success": True, "message": "PIN updated successfully"})
        else:
            logger.warning(f"PIN change failed for user {user_id}: Database update failed")
            return jsonify({"success": False, "error": "Failed to update PIN"}), 500

    except Exception as e:
        logger.error(f"Error in PIN change: {e}")
        return jsonify({"error": "PIN change failed"}), 500

@magic_bp.route('/magic/<token>/complete-verification', methods=['POST'])
def complete_verification(token):
    """
    Complete OTP verification for various sources (temp user upgrade, phone login, account creation).

    Args:
        token: The raw magic link token
    """
    try:
        # Get verification data from request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        id_token = data.get('idToken')
        firebase_phone = data.get('phoneNumber')
        firebase_uid = data.get('uid')

        if not all([id_token, firebase_phone, firebase_uid]):
            return jsonify({'error': 'Missing verification data'}), 400

        # Verify the ID token with Firebase Admin
        try:
            from firebase_admin import auth as admin_auth
            decoded_token = admin_auth.verify_id_token(id_token, clock_skew_seconds=30)
            verified_uid = decoded_token['uid']
            verified_phone = decoded_token.get('phone_number')

            if verified_uid != firebase_uid or verified_phone != firebase_phone:
                return jsonify({'error': 'Token verification failed'}), 400

        except Exception as e:
            logger.error(f"Firebase token verification failed: {e}")
            return jsonify({'error': 'Invalid verification token'}), 400

        # Handle different verification sources
        
        logger.info(f"Complete verification: checking session data for routing")
        logger.info(f"Session keys available: {list(session.keys())}")
        
        # 1. Check for account creation (new guest/host account)
        account_creation_data = session.pop('account_creation', None)
        if account_creation_data:
            logger.info(f"Routing to account creation verification")
            return handle_account_creation_verification(
                token, verified_uid, firebase_phone, account_creation_data
            )
        
        # 2. Check for phone login (existing permanent user)
        phone_login_data = session.pop('phone_login', None)
        if phone_login_data:
            logger.info(f"Routing to phone login verification: {phone_login_data}")
            return handle_phone_login_verification(
                token, verified_uid, firebase_phone, phone_login_data
            )
        
        # 3. Check for temp user upgrade (existing flow)
        otp_data = session.get('otp_verification')
        if otp_data:
            logger.info(f"Routing to temp user upgrade verification: {otp_data}")
            return handle_temp_user_upgrade_verification(
                token, verified_uid, firebase_phone, otp_data
            )
        
        # No verification context found
        logger.error(f"No verification context found in session")
        return jsonify({'error': 'No verification context found'}), 400

    except Exception as e:
        logger.error(f"Error in complete verification: {e}")
        return jsonify({'error': 'Verification failed'}), 500

def handle_account_creation_verification(token, firebase_uid, firebase_phone, creation_data):
    """Handle verification for new account creation."""
    try:
        account_type = creation_data.get('account_type', 'guest')
        
        # Check if user already exists (this is the key missing check!)
        from concierge.utils.firestore_client import get_user, update_user
        from concierge.utils.role_helpers import add_role, normalize_user_roles
        
        existing_user = get_user(firebase_uid)
        
        if existing_user:
            # User already exists - add the guest role to their existing roles
            logger.info(f"User {firebase_uid} already exists, adding {account_type} role to existing roles")
            
            # Get current roles and add the new role
            current_roles = normalize_user_roles(existing_user)
            updated_user_data = add_role(existing_user, account_type)
            
            # Update the user with the new role
            success = update_user(firebase_uid, {'role': updated_user_data['role']})
            
            if not success:
                return jsonify({'error': 'Failed to update user roles'}), 500
            
            logger.info(f"Successfully added {account_type} role to existing user {firebase_uid}")
            permanent_user_id = firebase_uid
            
        else:
            # User doesn't exist - create new user account
            from concierge.utils.firestore_client import create_permanent_user_from_magic_link
            
            user_data = {
                'displayName': f"New {account_type.title()}",
                'phoneNumber': firebase_phone,
                'role': account_type,
                'uid': firebase_uid,
                'createdFromMagicLink': hash_magic_link_token(token),
                'accountType': 'permanent'
            }
            
            # Create the user
            permanent_user_id = create_permanent_user_from_magic_link(firebase_uid, user_data)
            
            if not permanent_user_id:
                return jsonify({'error': 'Failed to create account'}), 500
        
        # Get magic link data to attach reservation if it's a guest account
        if account_type == 'guest':
            magic_link_data = get_magic_link_by_token(token)
            if magic_link_data:
                reservation_id = magic_link_data.get('reservation_id')
                if reservation_id:
                    from concierge.utils.firestore_client import attach_reservation_to_permanent_user
                    attach_reservation_to_permanent_user(permanent_user_id, reservation_id, token)
        
        # Clear any existing Flask session to prevent conflicts with magic link session
        session.clear()
        
        # Update session to use permanent user
        final_user_data = get_user(permanent_user_id)
        session['guest_name'] = final_user_data.get('displayName', 'Guest')
        session['phone_number'] = firebase_phone
        session['is_temporary_user'] = False
        
        # Create magic link session for the permanent user (like other verification handlers)
        from concierge.utils.session_manager import create_session_cookie
        new_session_token = create_session_cookie(permanent_user_id)
        
        logger.info(f"Successfully processed verification for user {firebase_uid} with {account_type} role")
        
        response_data = {
            "success": True,
            "message": "Account verification successful",
            "permanentUserId": permanent_user_id,
            "newSessionToken": new_session_token,
            "redirect": url_for('magic.magic_link_dashboard', token=token, _external=False)
        }
        
        response = jsonify(response_data)
        response.set_cookie('session_token', new_session_token, 
                          max_age=30*24*60*60, secure=True, httponly=True, samesite='Lax')
        
        return response
        
    except Exception as e:
        logger.error(f"Error in account creation verification: {e}")
        return jsonify({'error': 'Verification failed'}), 500

@magic_bp.route('/magic/<token>/select-reservation', methods=['POST'])
def select_reservation(token):
    """
    Handle reservation selection from disambiguation screen.

    Args:
        token: The raw magic link token
    """
    try:
        selected_reservation_id = request.form.get('selected_reservation')
        if not selected_reservation_id:
            flash('Please select a reservation.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))

        # Get the selected reservation
        reservation = get_reservation(selected_reservation_id)
        if not reservation:
            flash('Selected reservation not found.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))

        # Store the selected reservation in session for the verification process
        session['selected_reservation_id'] = selected_reservation_id

        # Redirect back to the phone verification with the selected reservation
        # The verification logic will pick up the selected reservation from session
        return redirect(url_for('magic.collect_name', token=token))

    except Exception as e:
        logger.error(f"Error in reservation selection: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('magic.magic_link_access', token=token))

def handle_phone_login_verification(token, firebase_uid, firebase_phone, login_data):
    """Handle verification for phone login to existing account or phone number update."""
    try:
        # Find the permanent user
        from concierge.utils.phone_utils import phones_match
        from concierge.utils.firestore_client import get_user, attach_reservation_to_permanent_user, update_user
        
        permanent_user_id = None
        is_profile_update = login_data.get('source') == 'profile_modal_update'
        
        if is_profile_update:
            # For profile updates, the user_id is directly provided (no phone matching needed)
            permanent_user_id = login_data['permanent_users'][0]
            user_data = get_user(permanent_user_id)
            if not user_data:
                return jsonify({'error': 'User account not found'}), 404
        else:
            # For regular login, find user by phone number match
            for user_id in login_data['permanent_users']:
                user_data = get_user(user_id)
                if user_data and phones_match(user_data.get('phoneNumber', ''), firebase_phone):
                    permanent_user_id = user_id
                    break
            
            if not permanent_user_id:
                return jsonify({'error': 'User account not found'}), 404
        
        # Update phone number in user profile if this is a profile update
        # AND ensure ALL users get guest role when accessing magic links
        from google.cloud import firestore
        # First, get current user data to preserve existing role
        current_user_data = get_user(permanent_user_id)
        logger.info(f"Current user data before update: role={current_user_data.get('role') if current_user_data else 'None'}")
        
        # Prepare update data
        update_data = {
            'lastLoginAt': firestore.SERVER_TIMESTAMP
        }
        
        # For profile updates, also update phone number
        if is_profile_update:
            update_data['phoneNumber'] = firebase_phone
        
        # CRITICAL FIX: Ensure ALL users (not just profile updates) have guest role 
        # when accessing magic links. This allows hosts to see their reservations.
        from concierge.utils.role_helpers import ensure_guest_role, has_role
        
        logger.info(f"ROLE DEBUG: Raw user data role field BEFORE modification: {repr(current_user_data.get('role'))}")
        
        # Check if user has guest role BEFORE any modifications
        user_had_guest_role_originally = has_role(current_user_data, 'guest')
        logger.info(f"ROLE DEBUG: User had guest role originally: {user_had_guest_role_originally}")
        
        # Now modify the user data to add guest role
        updated_user_data = ensure_guest_role(current_user_data)
        logger.info(f"ROLE DEBUG: User data role field AFTER ensure_guest_role: {repr(updated_user_data.get('role'))}")
        
        # FORCE role update if user didn't have guest role originally
        if not user_had_guest_role_originally:
            # Update roles - force the update
            if 'role' in updated_user_data:
                update_data['role'] = updated_user_data['role']
            if 'roles' in updated_user_data:
                update_data['roles'] = updated_user_data['roles']
            logger.info(f"FORCING guest role update for user {permanent_user_id}. New role: {updated_user_data.get('role')}")
            logger.info(f"ROLE DEBUG: Update data will include role field: {repr(update_data.get('role'))}")
        else:
            logger.info(f"User {permanent_user_id} already had guest role originally, no role update needed")
        
        logger.info(f"ROLE DEBUG: About to call update_user with data: {update_data}")
        update_success = update_user(permanent_user_id, update_data)
        logger.info(f"ROLE DEBUG: update_user returned: {update_success}")
        
        if not update_success:
            logger.error(f"Failed to update user {permanent_user_id}")
            return jsonify({'error': 'Failed to update user'}), 500
        
        # Verify role is preserved after update
        final_user_data = get_user(permanent_user_id)
        logger.info(f"ROLE DEBUG: Final user data after Firestore update - role field: {repr(final_user_data.get('role') if final_user_data else None)}")
        logger.info(f"ROLE DEBUG: Final user has guest role: {has_role(final_user_data, 'guest') if final_user_data else False}")
        
        if is_profile_update:
            logger.info(f"Updated phone number for user {permanent_user_id} to {firebase_phone}")
        logger.info(f"Ensured guest role for user {permanent_user_id} accessing magic link")

        # Attach reservation to permanent user (for reservation-based magic links)
        # This should happen for both profile updates and regular logins if there's a reservation
        logger.info(f"Looking up magic link data for token {token[:8]}...")
        
        # NEW: Check for preserved reservations first (supports cross-phone verification)
        preserved_reservation_ids = login_data.get('preserved_reservation_ids', [])
        reservation_id = None
        
        if preserved_reservation_ids:
            # Use preserved reservation from initial 4-digit verification
            # This enables cross-phone verification for group bookings and multiple phone scenarios
            reservation_id = preserved_reservation_ids[0]  # Use first preserved reservation
            logger.info(f"Using preserved reservation {reservation_id} from initial verification (cross-phone verification enabled)")
        else:
            # Fallback to original phone-based lookup logic
            logger.info("No preserved reservations found, falling back to phone-based lookup")
            
            # Try property-based magic link first
            property_data = get_property_by_magic_link_token(token)
            
            if property_data:
                logger.info(f"Property-based magic link found for property: {property_data.get('id')}")
                # For property-based magic links, we need to find the reservation by phone number
                from concierge.utils.firestore_client import find_property_reservations_by_phone
                from concierge.utils.phone_utils import get_phone_last_4
                
                phone_last_4 = get_phone_last_4(firebase_phone)
                matching_reservations = find_property_reservations_by_phone(property_data.get('id'), phone_last_4)
                
                if matching_reservations:
                    # Use the first matching reservation (there should typically be one after verification)
                    reservation_id = matching_reservations[0].get('id')
                    logger.info(f"Found reservation {reservation_id} for property-based magic link")
                else:
                    logger.warning(f"No matching reservations found for property {property_data.get('id')} and phone ending {phone_last_4}")
            else:
                # Fallback to reservation-based magic link
                magic_link_data = get_magic_link_by_token(token)
                logger.info(f"Reservation-based magic link data found: {bool(magic_link_data)}")
                if magic_link_data:
                    logger.info(f"Magic link data keys: {list(magic_link_data.keys())}")
                    reservation_id = magic_link_data.get('reservation_id')
                    logger.info(f"Reservation ID from magic link: {reservation_id}")
                else:
                    logger.warning(f"No magic link data found for token {token[:8]}...")
        
        # Attach reservation if found
        if reservation_id:
            logger.info(f"Attaching reservation {reservation_id} to permanent user {permanent_user_id}")
            attach_success = attach_reservation_to_permanent_user(permanent_user_id, reservation_id, token)
            if attach_success:
                logger.info(f"Successfully attached reservation to user {permanent_user_id}")
            else:
                logger.error(f"Failed to attach reservation to user {permanent_user_id}")
        else:
            logger.info(f"No reservation found to attach for token {token[:8]}...")
            # For property-based magic links, provide helpful guidance
            if not preserved_reservation_ids:  # Only show this guidance if we didn't have preserved reservations
                property_data = get_property_by_magic_link_token(token)
                if property_data:
                    logger.warning(f"Property-based magic link: No reservation found for user {permanent_user_id} with phone ending {get_phone_last_4(firebase_phone)} at property {property_data.get('name')}")
                    logger.info(f"User may need to use the phone number associated with their reservation at this property")
        
        # Clear any existing Flask session to prevent conflicts with magic link session
        session.clear()
        
        # Update session
        user_data = get_user(permanent_user_id)
        session['guest_name'] = user_data.get('displayName', 'Guest')
        session['phone_number'] = firebase_phone
        session['is_temporary_user'] = False
        
        # Create magic link session for the permanent user
        from concierge.utils.session_manager import create_session_cookie
        new_session_token = create_session_cookie(permanent_user_id)
        
        if is_profile_update:
            logger.info(f"Successfully updated phone number for user {permanent_user_id}")
            message = "Phone number updated successfully"
        else:
            logger.info(f"Successfully logged in permanent user {permanent_user_id}")
            message = "Login successful"
        
        response_data = {
            "success": True,
            "message": message,
            "permanentUserId": permanent_user_id,
            "newSessionToken": new_session_token,
            "redirect": url_for('magic.magic_link_dashboard', token=token, _external=False)  # Redirect to magic link dashboard
        }
        
        response = jsonify(response_data)
        
        # Set the magic link session cookie
        response.set_cookie(
            'magicLinkSession',
            new_session_token,
            max_age=30*24*60*60,  # 30 days
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite='Lax'
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in phone login verification: {e}")
        return jsonify({'error': 'Login failed'}), 500

def handle_temp_user_upgrade_verification(token, firebase_uid, firebase_phone, otp_data):
    """Handle verification for temp user upgrade to permanent (existing functionality)."""
    try:
        temp_user_id = otp_data.get('temp_user_id')
        guest_name = otp_data.get('guest_name', 'Guest')
        email = otp_data.get('email', '')  # Get email from OTP session
        
        if not temp_user_id:
            return jsonify({'error': 'No temporary user found'}), 400
        
        # Get temporary user data
        temp_user = get_temporary_user(temp_user_id)
        if not temp_user:
            return jsonify({'error': 'Temporary user not found'}), 404
        
        # Create permanent user account
        from concierge.utils.firestore_client import create_permanent_user_from_temp, attach_reservation_to_permanent_user
        
        permanent_user_id = create_permanent_user_from_temp(
            firebase_uid, firebase_phone, guest_name, temp_user_id, token, email
        )
        
        if not permanent_user_id:
            return jsonify({'error': 'Failed to create permanent account'}), 500
        
        # Attach reservation to permanent user (same logic as phone login verification)
        logger.info(f"Attaching reservation for temp user upgrade, token: {token[:8]}...")
        
        # NEW: Check for preserved reservations first (supports cross-phone verification)
        preserved_reservation_ids = otp_data.get('preserved_reservation_ids', [])
        reservation_id = None
        
        if preserved_reservation_ids:
            # Use preserved reservation from initial 4-digit verification
            # This enables cross-phone verification for group bookings and multiple phone scenarios
            reservation_id = preserved_reservation_ids[0]  # Use first preserved reservation
            logger.info(f"Using preserved reservation {reservation_id} from initial verification (cross-phone verification enabled)")
        else:
            # Fallback to original phone-based lookup logic
            logger.info("No preserved reservations found, falling back to phone-based lookup")
            
            # Try property-based magic link first
            property_data = get_property_by_magic_link_token(token)
            
            if property_data:
                logger.info(f"Property-based magic link found for property: {property_data.get('id')}")
                # For property-based magic links, we need to find the reservation by phone number
                from concierge.utils.firestore_client import find_property_reservations_by_phone
                from concierge.utils.phone_utils import get_phone_last_4
                
                phone_last_4 = get_phone_last_4(firebase_phone)
                matching_reservations = find_property_reservations_by_phone(property_data.get('id'), phone_last_4)
                
                if matching_reservations:
                    # Use the first matching reservation (there should typically be one after verification)
                    reservation_id = matching_reservations[0].get('id')
                    logger.info(f"Found reservation {reservation_id} for property-based magic link")
                else:
                    logger.warning(f"No matching reservations found for property {property_data.get('id')} and phone ending {phone_last_4}")
            else:
                # Fallback to reservation-based magic link
                magic_link_data = get_magic_link_by_token(token)
                logger.info(f"Reservation-based magic link data found: {bool(magic_link_data)}")
                if magic_link_data:
                    reservation_id = magic_link_data.get('reservation_id')
                    logger.info(f"Reservation ID from magic link: {reservation_id}")
                else:
                    logger.warning(f"No magic link data found for token {token[:8]}...")
        
        # Attach reservation if found
        if reservation_id:
            logger.info(f"Attaching reservation {reservation_id} to permanent user {permanent_user_id}")
            attach_success = attach_reservation_to_permanent_user(permanent_user_id, reservation_id, token)
            if attach_success:
                logger.info(f"Successfully attached reservation to user {permanent_user_id}")
            else:
                logger.error(f"Failed to attach reservation to user {permanent_user_id}")
        else:
            logger.info(f"No reservation found to attach for token {token[:8]}...")
            # For property-based magic links, provide helpful guidance
            if not preserved_reservation_ids:  # Only show this guidance if we didn't have preserved reservations
                property_data = get_property_by_magic_link_token(token)
                if property_data:
                    logger.warning(f"Property-based magic link: No reservation found for temp user upgrade with phone ending {get_phone_last_4(firebase_phone)} at property {property_data.get('name')}")
                    logger.info(f"User may need to use the phone number associated with their reservation at this property")
        
        # Clear any existing Flask session to prevent conflicts with magic link session
        session.clear()
        
        # Update Flask session
        session['guest_name'] = guest_name
        session['phone_number'] = firebase_phone
        session['is_temporary_user'] = False
        
        # IMPORTANT: Update the magic link session cookie to point to the new permanent user
        # This ensures the dashboard will recognize the user as permanent
        from concierge.utils.session_manager import create_session_cookie
        
        # Create new session for the permanent user
        new_session_token = create_session_cookie(permanent_user_id)
        
        # Prepare response with updated session cookie and correct redirect
        response_data = {
            "success": True,
            "message": "Phone verification completed successfully",
            "permanentUserId": permanent_user_id,
            "newSessionToken": new_session_token,  # Frontend can use this to update cookie
            "redirect": url_for('magic.magic_link_dashboard', token=token, _external=False)  # Redirect to magic link dashboard
        }
        
        logger.info(f"Successfully upgraded temporary user {temp_user_id} to permanent user {permanent_user_id}")
        
        response = jsonify(response_data)
        
        # Set the new session cookie in the response
        response.set_cookie(
            'magicLinkSession',
            new_session_token,
            max_age=30*24*60*60,  # 30 days
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite='Lax'
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in temp user upgrade verification: {e}")
        return jsonify({'error': 'Failed to upgrade account'}), 500

@magic_bp.route('/magic/<token>/guest')
def magic_link_dashboard(token):
    """
    Guest dashboard for magic link users with temporary user authentication.

    Args:
        token: The raw magic link token
    """
    try:
        # Validate session first
        is_valid, user_id, reason = get_session_from_request()
        logger.info(f"Dashboard session validation: valid={is_valid}, user_id={user_id}, reason={reason}")

        if not is_valid or not user_id:
            # No valid session, redirect to magic link access for PIN verification
            logger.info(f"No valid session for dashboard access, redirecting to PIN verification")
            return redirect(url_for('magic.magic_link_access', token=token))

        # Check if this is a permanent user (Firebase UID) or temporary user
        is_permanent_user = not user_id.startswith('temp_magic_')

        if is_permanent_user:
            # Get permanent user data from Firestore
            from concierge.utils.firestore_client import get_firestore_client
            db = get_firestore_client()
            user_doc = db.collection('users').document(user_id).get()

            if not user_doc.exists:
                logger.error(f"Permanent user {user_id} not found in Firestore")
                # Clear the invalid session and redirect to PIN verification
                response = make_response(redirect(url_for('magic.magic_link_access', token=token)))
                clear_session_cookie(response)
                return response

            user_data = user_doc.to_dict()
            logger.info(f"Loading dashboard for permanent user {user_id}")
        else:
            # Get temporary user data
            user_data = get_temporary_user(user_id)
            if not user_data:
                logger.error(f"Temporary user {user_id} not found, clearing session and redirecting to PIN verification")
                # Clear the invalid session and redirect to PIN verification
                response = make_response(redirect(url_for('magic.magic_link_access', token=token)))
                clear_session_cookie(response)
                return response
            
            # Check if temporary user has been disabled (migrated to permanent)
            if user_data.get('access_disabled') or user_data.get('migration_status') == 'migrated':
                logger.info(f"Temporary user {user_id} has been disabled/migrated, clearing session and redirecting to PIN verification")
                # Clear the invalid session and redirect to PIN verification to start fresh
                response = make_response(redirect(url_for('magic.magic_link_access', token=token)))
                clear_session_cookie(response)
                return response
            
            logger.info(f"Loading dashboard for temporary user {user_id}")

        # Get reservation data
        reservation_ids = user_data.get('reservationIds', [])
        if not reservation_ids:
            return render_template('magic_link_error.html',
                                 error_message="No reservations found for this user.")

        # Get the primary reservation (first one)
        reservation = get_reservation(reservation_ids[0])
        if not reservation:
            return render_template('magic_link_error.html',
                                 error_message="Reservation not found. Please contact your host.")
        
        # Prepare context for guest dashboard
        import os

        # Load environment variables if not already loaded
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass  # dotenv not available, continue with existing env vars

        # Use local WebSocket for development, production for deployment
        flask_env = os.environ.get('FLASK_ENV', '').lower()
        debug_mode = os.environ.get('DEBUG_MODE', '').lower() in ('true', '1', 'yes')

        # Use production WebSocket for both development and production
        # This ensures consistency and proper authentication
        websocket_url = "wss://rlrnx1tks4.execute-api.us-east-2.amazonaws.com/dev"
        websocket_api_url = "wss://rlrnx1tks4.execute-api.us-east-2.amazonaws.com/dev"

        # Create temporary ID token for WebSocket authentication
        temp_id_token = create_temporary_id_token(user_id)
        if not temp_id_token:
            logger.error(f"Failed to create temporary ID token for user {user_id}")
            # Continue without token - user will see auth error in chat

        # Prepare context based on user type
        if is_permanent_user:
            # Check if permanent user has a default PIN (for security warning)
            from concierge.utils.phone_utils import get_last_4_digits
            user_pin = user_data.get('pinCode')
            phone_number = user_data.get('phoneNumber', '')
            has_default_pin = False
            
            if user_pin and phone_number:
                expected_default_pin = get_last_4_digits(phone_number)
                has_default_pin = (user_pin == expected_default_pin)
                logger.info(f"Magic link user {user_id} PIN check: has PIN={bool(user_pin)}, matches default={has_default_pin}")
            
            # Permanent user context
            context = {
                'user_id': user_id,  # Firebase UID
                'property_id': reservation.get('propertyId'),
                'reservation_id': reservation_ids[0],  # Primary reservation ID
                'guest_name': user_data.get('displayName', 'Guest'),
                'guest_name_source': 'magic_link',
                'phone_number': phone_number,
                'access_level': user_data.get('accessLevel', 'full_access'),
                'magic_link_token': token,
                'reservations_data': [reservation],  # Only show current reservation
                'websocket_url': websocket_url,
                'websocket_api_url': websocket_api_url,
                'gemini_api_key': '',  # Will be populated by template if needed
                'show_upgrade_prompt': False,  # No upgrade prompt for permanent users
                'is_temporary_user': False,
                'user_has_default_pin': has_default_pin,  # Add default PIN detection
                'temp_user_data': None,
                'temp_id_token': None  # Permanent users don't need temporary tokens
            }
        else:
            # Temporary user context
            context = {
                'user_id': user_id,  # Temporary user ID
                'property_id': reservation.get('propertyId'),
                'reservation_id': reservation_ids[0],  # Primary reservation ID
                'guest_name': user_data.get('displayName', 'Guest'),
                'guest_name_source': 'magic_link',
                'phone_number': f"***-***-{user_data.get('phoneNumberLast4', '****')}",
                'access_level': user_data.get('accessLevel', 'limited_info_access'),
                'magic_link_token': token,
                'reservations_data': [reservation],  # Only show current reservation
                'websocket_url': websocket_url,
                'websocket_api_url': websocket_api_url,
                'is_temporary_user': True,
                'user_type': 'temporary',
                'temp_id_token': temp_id_token  # Add the temporary ID token
            }
            
            print(f"Dashboard route: Rendering dashboard for temporary user {user_id}")
            print(f"Dashboard route: User data displayName: {user_data.get('displayName', 'Guest')}")
            print(f"Dashboard route: User data keys: {list(user_data.keys())}")
            print(f"Dashboard route: Context guest_name: {context['guest_name']}")
            print(f"Dashboard route: Temp ID token generated: {temp_id_token is not None}")
            
            return render_template('guest_dashboard.html', **context)
        
        return render_template('guest_dashboard.html', **context)
        
    except Exception as e:
        logger.error(f"Error in magic link dashboard: {e}")
        return render_template('magic_link_error.html',
                             error_message="An error occurred loading your dashboard. Please try again.")

# Upgrade route removed - upgrades are now handled via dashboard notification/profile modal

@magic_bp.route('/magic/test')
def test_magic_link():
    """Test route to create a sample magic link for local testing."""
    try:
        from concierge.utils.firestore_client import generate_magic_link_token, generate_magic_link_url

        # Generate a test token
        test_token = generate_magic_link_token()
        test_url = generate_magic_link_url(test_token)

        return f"""
        <html>
        <head><title>Magic Link Test</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>🧪 Magic Link Test</h1>
            <p>Generated test magic link:</p>
            <p><a href="{test_url}" target="_blank" style="color: blue; text-decoration: underline;">{test_url}</a></p>
            <p><strong>Note:</strong> This is just a test link. It won't have a real reservation behind it, so you'll get an error when you click it.</p>
            <p>To test properly, generate a magic link from the host dashboard for a real reservation.</p>
            <hr>
            <h2>Testing Instructions:</h2>
            <ol>
                <li>Go to your host dashboard: <a href="http://localhost:5001/">http://localhost:5001/</a></li>
                <li>Navigate to a property's reservations page</li>
                <li>Click "Generate Guest Link" for any reservation</li>
                <li>The generated link will use localhost:5001 for local testing</li>
            </ol>
        </body>
        </html>
        """

    except Exception as e:
        return f"Error generating test link: {e}"

@magic_bp.route('/magic/test-firebase-config')
def test_firebase_config():
    """Test route to verify Firebase configuration is properly loaded."""
    try:
        from concierge.utils.firebase_config import get_firebase_config

        config = get_firebase_config()

        # Mask sensitive data for display
        masked_config = {}
        for key, value in config.items():
            if key == 'apiKey' and value:
                masked_config[key] = value[:8] + '...' + value[-4:] if len(value) > 12 else 'present'
            elif value:
                masked_config[key] = 'present'
            else:
                masked_config[key] = 'missing'

        return f"""
        <html>
        <head><title>Firebase Config Test</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>🔥 Firebase Configuration Test</h1>
            <h2>Configuration Status:</h2>
            <pre style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
{str(masked_config)}
            </pre>
            <p><strong>Note:</strong> Sensitive values are masked for security.</p>
            <hr>
            <h2>OTP Test Instructions:</h2>
            <ol>
                <li>Generate a magic link from the host dashboard</li>
                <li>Complete PIN verification to reach the name collection page</li>
                <li>Enter a phone number to trigger OTP verification</li>
                <li>Check browser console for Firebase initialization logs</li>
            </ol>
        </body>
        </html>
        """

    except Exception as e:
        import traceback
        return f"""
        <html>
        <head><title>Firebase Config Test Error</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>❌ Firebase Config Test Error</h1>
            <pre style="background: #ffe6e6; padding: 15px; border-radius: 5px;">
Error: {e}

Traceback:
{traceback.format_exc()}
            </pre>
        </body>
        </html>
        """

@magic_bp.route('/magic/logout')
def magic_logout():
    """Logout specifically for magic link users - clears both regular and magic link sessions."""
    try:
        user_id = session.get('user_id')
        
        # Get session info before clearing
        is_valid, magic_user_id, _ = get_session_from_request()
        
        logger.info(f"Magic link logout: user_id={user_id}, magic_user_id={magic_user_id}")
        
        # Clear Flask session
        session.clear()
        
        # Create response with redirect
        response = make_response(redirect('/'))
        
        # Clear magic link session cookie
        clear_session_cookie(response)
        
        logger.info(f"Magic link logout completed for user: {user_id or magic_user_id}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error during magic link logout: {e}")
        # Still try to clear sessions and redirect
        response = make_response(redirect('/'))
        clear_session_cookie(response)
        return response

@magic_bp.route('/magic/clear-session')
def clear_session():
    """Clear magic link session cookie for debugging."""
    response = make_response("""
    <html>
    <head><title>Session Cleared</title></head>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h1>✅ Session Cleared</h1>
        <p>Your magic link session cookie has been cleared.</p>
        <p>You can now try accessing your magic link again with fresh authentication.</p>
        <p><a href="javascript:history.back()">← Go Back</a></p>
    </body>
    </html>
    """)
    clear_session_cookie(response)
    return response

@magic_bp.route('/magic/debug/<token>')
def debug_magic_link(token):
    """Debug route to check magic link data."""
    try:
        from concierge.utils.firestore_client import get_magic_link_by_token, hash_magic_link_token

        # Get magic link data
        magic_link_data = get_magic_link_by_token(token)
        token_hash = hash_magic_link_token(token)

        debug_info = {
            'token_preview': token[:8] + '...',
            'token_hash': token_hash[:8] + '...',
            'magic_link_found': magic_link_data is not None,
            'magic_link_data': magic_link_data if magic_link_data else 'Not found'
        }

        if magic_link_data:
            reservation_id = magic_link_data.get('reservation_id')
            from concierge.utils.firestore_client import get_reservation
            reservation = get_reservation(reservation_id)
            debug_info['reservation_found'] = reservation is not None
            debug_info['reservation_data'] = reservation if reservation else 'Not found'

        return f"""
        <html>
        <head><title>Magic Link Debug</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>🔍 Magic Link Debug Info</h1>
            <pre style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
{str(debug_info)}
            </pre>
            <p><a href="/magic/{token}">Try the magic link</a></p>
        </body>
        </html>
        """

    except Exception as e:
        import traceback
        return f"""
        <html>
        <head><title>Magic Link Debug Error</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>❌ Debug Error</h1>
            <pre style="background: #ffe6e6; padding: 15px; border-radius: 5px;">
Error: {e}

Traceback:
{traceback.format_exc()}
            </pre>
        </body>
        </html>
        """

@magic_bp.route('/magic/<token>/create-account-from-magic-link', methods=['POST'])
def create_account_from_magic_link(token):
    """
    Create new account (guest or host) from magic link signup process.
    
    Args:
        token: The raw magic link token
    """
    try:
        # Validate magic link
        magic_link_data = get_magic_link_by_token(token)
        if not magic_link_data:
            flash('Invalid magic link.', 'error')
            return redirect(url_for('magic.magic_link_access', token=token))
        
        # Get form data
        phone_number = request.form.get('phone_number', '').strip()
        account_type = request.form.get('account_type', '').strip()
        
        if not phone_number or not account_type:
            flash('Phone number and account type are required.', 'error')
            return redirect(url_for('magic.show_phone_login', token=token))
        
        if account_type not in ['guest', 'host']:
            flash('Invalid account type selected.', 'error')
            return redirect(url_for('magic.show_phone_login', token=token))
        
        # Validate phone number format
        from concierge.utils.phone_utils import validate_phone_number, clean_phone_for_storage
        
        if not validate_phone_number(phone_number):
            flash('Please enter a valid phone number.', 'error')
            return render_template('account_type_selection.html',
                                 token=token,
                                 phone_number=phone_number,
                                 is_magic_link=True,
                                 form_action=url_for('magic.create_account_from_magic_link', token=token))
        
        # Clean phone number for storage
        clean_phone = clean_phone_for_storage(phone_number)
        
        # Store account creation data in session for OTP verification
        session['account_creation'] = {
            'phone_number': clean_phone,
            'account_type': account_type,
            'token': token,
            'source': 'magic_link_signup'
        }
        
        # Redirect to OTP verification for account creation
        return render_template('otp_verification.html',
                             token=token,
                             phone_number=clean_phone,
                             is_magic_link=True,
                             source='account_creation',
                             account_type=account_type,
                             form_action=url_for('magic.complete_verification', token=token))
        
    except Exception as e:
        logger.error(f"Error in account creation from magic link: {e}")
        flash('An error occurred during account creation. Please try again.', 'error')
        return redirect(url_for('magic.show_phone_login', token=token))
