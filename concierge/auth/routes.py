from flask import (
    Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, g, make_response
)
from datetime import datetime

# Import token verification from utils
from .utils import verify_token
# Import Firestore operations
from concierge.utils.firestore_client import get_user, create_user, update_user, find_user_by_phone, get_user_by_email

# Create Blueprint
auth_bp = Blueprint('auth', __name__, template_folder='../templates') # Point to parent templates folder

@auth_bp.route('/login', methods=['GET'])
def login():
    """Displays the login page."""
    if 'user_id' in session:
        # If user is already logged in, redirect to dashboard
        return redirect(url_for('views.dashboard')) # Assumes dashboard is in 'views' blueprint
    # Render the main index page which contains the login form
    return render_template('index.html')

@auth_bp.route('/email-link-signin', methods=['GET'])
def email_link_signin():
    """Handle email link sign-in completion."""
    # This route is called when user clicks the email link
    # The actual authentication is handled by Firebase on the client side
    # We just need to provide a page that processes the link
    return render_template('email_link_signin.html')

@auth_bp.route('/phone-login', methods=['GET', 'POST'])
def phone_login():
    """Handle standalone phone login flow."""
    if request.method == 'GET':
        # Clear any existing session data to avoid conflicts
        session.pop('phone_login_data', None)
        session.pop('signup_data', None)
        # Show phone entry form
        return render_template('phone_login.html')
    
    # Handle POST - process phone number
    try:
        # Clear any existing session data to avoid conflicts
        session.pop('phone_login_data', None)
        session.pop('signup_data', None)
        
        phone_number = request.form.get('phone_number', '').strip()
        
        if not phone_number:
            flash('Phone number is required.', 'error')
            return render_template('phone_login.html')
        
        # Validate and clean phone number
        from concierge.utils.phone_utils import validate_phone_number, clean_phone_for_storage
        
        if not validate_phone_number(phone_number):
            flash('Please enter a valid phone number.', 'error')
            return render_template('phone_login.html', phone_number=phone_number)
        
        clean_phone = clean_phone_for_storage(phone_number)
        
        # Find user by phone number
        user_data = find_user_by_phone(clean_phone)
        
        if user_data and not user_data.get('isTemporary', False):
            # Permanent user found - redirect to OTP verification directly
            # Store login data for OTP verification
            session['phone_login_data'] = {
                'phone_number': clean_phone,
                'user_id': user_data['id'],
                'step': 'otp_verification',  # Changed from pin_entry/otp_login to unified otp_verification
                'has_pin': bool(user_data.get('pinCode'))
            }
            return render_template('otp_verification.html',
                                 phone_number=clean_phone,
                                 is_existing_user=True,
                                 form_action=url_for('auth.complete_phone_auth'))
        else:
            # User Not Found → Unified Flow: OTP first, then account type selection
            session['signup_data'] = {
                'phone_number': clean_phone,
                'step': 'otp_verification'  # Changed from account_type_selection to otp_verification
            }
            return render_template('otp_verification.html',
                                 phone_number=clean_phone,
                                 is_new_user=True,
                                 form_action=url_for('auth.complete_phone_auth'))
    
    except Exception as e:
        print(f"Error in phone login: {e}")
        flash('An error occurred. Please try again.', 'error')
        return render_template('phone_login.html')

@auth_bp.route('/pin-entry', methods=['GET', 'POST'])
def pin_entry():
    """Handle PIN entry for permanent users."""
    login_data = session.get('phone_login_data')
    if not login_data or login_data.get('step') != 'pin_entry':
        return redirect(url_for('auth.phone_login'))
    
    if request.method == 'GET':
        return render_template('pin_entry.html', 
                             phone_number=login_data.get('phone_number'),
                             attempts=login_data.get('pin_attempts', 0))
    
    # Handle POST - verify PIN
    try:
        entered_pin = request.form.get('pin', '').strip()
        
        if not entered_pin or len(entered_pin) != 4 or not entered_pin.isdigit():
            flash('Please enter a 4-digit PIN.', 'error')
            return render_template('pin_entry.html', 
                                 phone_number=login_data.get('phone_number'),
                                 attempts=login_data.get('pin_attempts', 0))
        
        # Verify PIN
        from concierge.utils.firestore_client import verify_user_pin
        user_id = login_data.get('user_id')
        
        if verify_user_pin(user_id, entered_pin):
            # PIN correct - create session and redirect to dashboard
            session.pop('phone_login_data', None)
            session['user_id'] = user_id
            session['user_role'] = 'guest'  # Will be updated from user data
            flash('Login successful!', 'success')
            return redirect(url_for('views.dashboard'))
        else:
            # PIN incorrect
            attempts = login_data.get('pin_attempts', 0) + 1
            login_data['pin_attempts'] = attempts
            session['phone_login_data'] = login_data
            
            if attempts >= 3:
                # 3 attempts failed → OTP Recovery
                flash('Too many incorrect attempts. Please verify with OTP.', 'warning')
                login_data['step'] = 'otp_recovery'
                session['phone_login_data'] = login_data
                return redirect(url_for('auth.otp_recovery'))
            else:
                flash(f'Incorrect PIN. {3-attempts} attempts remaining.', 'error')
                return render_template('pin_entry.html', 
                                     phone_number=login_data.get('phone_number'),
                                     attempts=attempts)
    
    except Exception as e:
        print(f"Error in PIN entry: {e}")
        flash('An error occurred. Please try again.', 'error')
        return render_template('pin_entry.html', 
                             phone_number=login_data.get('phone_number'),
                             attempts=login_data.get('pin_attempts', 0))

@auth_bp.route('/otp-login', methods=['GET'])
def otp_login():
    """Show OTP login form for users without PIN."""
    login_data = session.get('phone_login_data')
    if not login_data or login_data.get('step') != 'otp_login':
        return redirect(url_for('auth.phone_login'))
    
    return render_template('otp_verification.html', 
                         phone_number=login_data.get('phone_number'),
                         next_step='set_pin',
                         form_action=url_for('auth.complete_phone_auth'))

@auth_bp.route('/otp-recovery', methods=['GET'])
def otp_recovery():
    """Show OTP recovery form for failed PIN attempts."""
    login_data = session.get('phone_login_data')
    if not login_data or login_data.get('step') != 'otp_recovery':
        return redirect(url_for('auth.phone_login'))
    
    return render_template('otp_verification.html', 
                         phone_number=login_data.get('phone_number'),
                         next_step='dashboard',
                         recovery_mode=True,
                         form_action=url_for('auth.complete_phone_auth'))

@auth_bp.route('/signup-choice', methods=['GET', 'POST'])
def signup_choice():
    """Handle account type selection for new users."""
    signup_data = session.get('signup_data')
    if not signup_data or signup_data.get('step') != 'account_type_selection':
        return redirect(url_for('auth.phone_login'))
    
    if request.method == 'GET':
        return render_template('account_type_selection.html', 
                             phone_number=signup_data.get('phone_number'),
                             form_action=url_for('auth.signup_choice'))
    
    # Handle POST - process account type selection
    account_type = request.form.get('account_type')
    
    if account_type == 'guest':
        # Guest Account → Show magic link prompt with option to enter link (consistent with main login flow)
        return render_template('guest_magic_link_prompt.html',
                             phone_number=signup_data.get('phone_number'))
    elif account_type == 'host':
        # Host Account → Create immediately if we have Firebase token, otherwise show error
        if signup_data.get('firebase_uid') and signup_data.get('phone_number'):
            # We have Firebase data from OTP verification - create account directly
            return create_host_account_from_signup_data(signup_data)
        else:
            flash('Session expired. Please try again.', 'error')
            return redirect(url_for('auth.phone_login'))
    else:
        flash('Please select an account type.', 'error')
        return render_template('account_type_selection.html', 
                             phone_number=signup_data.get('phone_number'),
                             form_action=url_for('auth.signup_choice'))

def create_guest_account_from_signup_data(signup_data):
    """Create guest account using signup data after OTP verification."""
    try:
        firebase_uid = signup_data.get('firebase_uid')
        phone_number = signup_data.get('phone_number')
        
        user_data = {
            'uid': firebase_uid,
            'phoneNumber': phone_number,
            'role': 'guest',
            'displayName': 'New Guest',
            'accountType': 'permanent',
            'createdAt': datetime.now().isoformat(),
            'isTemporary': False
            # No pinCode field - user hasn't set up a PIN yet
        }
        
        success = create_user(firebase_uid, user_data)
        if success:
            session.pop('signup_data', None)
            session['user_id'] = firebase_uid
            session['user_role'] = 'guest'
            
            # Check if this signup was initiated from a magic link
            magic_link_signup = session.pop('magic_link_signup', None)
            if magic_link_signup:
                # Attach reservation to the newly created permanent user
                token = magic_link_signup.get('token')
                if token:
                    try:
                        from concierge.utils.firestore_client import get_magic_link_by_token, attach_reservation_to_permanent_user
                        magic_link_data = get_magic_link_by_token(token)
                        if magic_link_data:
                            reservation_id = magic_link_data.get('reservation_id')
                            if reservation_id:
                                attach_reservation_to_permanent_user(firebase_uid, reservation_id)
                                print(f"Attached reservation {reservation_id} to new permanent user {firebase_uid}")
                    except Exception as e:
                        print(f"Error attaching reservation to new user: {e}")
                        # Don't fail the signup, just log the error
            
            flash('Guest account created successfully! You can set up a PIN later for faster access.', 'success')
            return redirect(url_for('views.dashboard'))
        else:
            flash('Failed to create account. Please try again.', 'error')
            return redirect(url_for('auth.signup_choice'))
    except Exception as e:
        print(f"Error creating guest account: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('auth.signup_choice'))

def create_host_account_from_signup_data(signup_data):
    """Create host account using signup data after OTP verification."""
    try:
        firebase_uid = signup_data.get('firebase_uid')
        phone_number = signup_data.get('phone_number')
        
        # Create default PIN from phone number
        from concierge.utils.phone_utils import get_last_4_digits
        default_pin = get_last_4_digits(phone_number) if phone_number else '0000'
        
        user_data = {
            'uid': firebase_uid,
            'phoneNumber': phone_number,
            'role': 'host',
            'displayName': 'New Host',
            'accountType': 'permanent',
            'pinCode': default_pin,
            'createdAt': datetime.now().isoformat(),
            'isTemporary': False,
            'hasDefaultPin': True
        }
        
        success = create_user(firebase_uid, user_data)
        if success:
            session.pop('signup_data', None)
            session['user_id'] = firebase_uid
            session['user_role'] = 'host'
            session['setup_property_required'] = True
            
            flash('Host account created successfully! Please set up your property and change your PIN.', 'success')
            return redirect(url_for('views.dashboard'))
        else:
            flash('Failed to create account. Please try again.', 'error')
            return redirect(url_for('auth.signup_choice'))
    except Exception as e:
        print(f"Error creating host account: {e}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('auth.signup_choice'))

@auth_bp.route('/complete-phone-auth', methods=['POST'])
def complete_phone_auth():
    """Complete phone authentication after OTP verification."""
    try:
        data = request.get_json()
        if not data:
            print("DEBUG: No JSON data provided to complete_phone_auth")
            return jsonify({'error': 'No data provided'}), 400
        
        id_token = data.get('idToken')
        firebase_phone = data.get('phoneNumber')
        firebase_uid = data.get('uid')
        
        print(f"DEBUG: complete_phone_auth received - uid: {firebase_uid}, phone: {firebase_phone}, token_present: {bool(id_token)}")
        print(f"DEBUG: Session contents: login_data={bool(session.get('phone_login_data'))}, signup_data={bool(session.get('signup_data'))}")
        if session.get('signup_data'):
            print(f"DEBUG: Signup data: {session.get('signup_data')}")
        if session.get('phone_login_data'):
            print(f"DEBUG: Login data: {session.get('phone_login_data')}")
        
        if not all([id_token, firebase_phone, firebase_uid]):
            print(f"DEBUG: Missing verification data - id_token: {bool(id_token)}, firebase_phone: {firebase_phone}, firebase_uid: {firebase_uid}")
            return jsonify({'error': 'Missing verification data'}), 400
        
        # Verify Firebase token
        from firebase_admin import auth as admin_auth
        try:
            decoded_token = admin_auth.verify_id_token(id_token, clock_skew_seconds=30)
            if decoded_token['uid'] != firebase_uid:
                return jsonify({'error': 'Token verification failed'}), 400
        except Exception as e:
            print(f"Firebase token verification failed: {e}")
            return jsonify({'error': 'Invalid verification token'}), 400
        
        # Handle different scenarios - prioritize login_data over signup_data
        login_data = session.get('phone_login_data')
        signup_data = session.get('signup_data')
        
        # Check for phone number mismatch and clear conflicting session data
        from concierge.utils.phone_utils import phones_match
        
        if login_data and not phones_match(login_data.get('phone_number', ''), firebase_phone):
            print(f"DEBUG: Phone mismatch in login_data. Expected: {login_data.get('phone_number')}, Got: {firebase_phone}. Clearing login_data.")
            session.pop('phone_login_data', None)
            login_data = None
        
        if signup_data and not phones_match(signup_data.get('phone_number', ''), firebase_phone):
            print(f"DEBUG: Phone mismatch in signup_data. Expected: {signup_data.get('phone_number')}, Got: {firebase_phone}. Clearing signup_data.")
            session.pop('signup_data', None)
            signup_data = None
        
        print(f"DEBUG: After phone validation - login_data: {bool(login_data)}, signup_data: {bool(signup_data)}")
        
        if login_data:
            # Handle existing user login
            print(f"DEBUG: Handling login completion for user: {login_data.get('user_id')}")
            return handle_login_completion(login_data, firebase_uid, firebase_phone)
        elif signup_data:
            # Handle new user signup - store Firebase data and redirect to account type selection
            print(f"DEBUG: Handling new user OTP verification - storing Firebase data")
            signup_data.update({
                'firebase_uid': firebase_uid,
                'firebase_phone': firebase_phone,
                'step': 'account_type_selection'
            })
            session['signup_data'] = signup_data
            
            return jsonify({
                'success': True,
                'message': 'Phone verification successful. Please select your account type.',
                'redirect': url_for('auth.signup_choice')
            })
        else:
            print("DEBUG: No valid authentication context found in session")
            print(f"DEBUG: Available session keys: {list(session.keys())}")
            return jsonify({'error': 'No authentication context found'}), 400
    
    except Exception as e:
        print(f"Error completing phone auth: {e}")
        return jsonify({'error': 'Authentication failed'}), 500

def handle_login_completion(login_data, firebase_uid, firebase_phone):
    """Handle completion of login flows."""
    user_id = login_data.get('user_id')
    step = login_data.get('step')
    has_pin = login_data.get('has_pin', False)
    
    if step == 'otp_verification':
        # Unified OTP verification for existing users
        from concierge.utils.firestore_client import get_user
        from concierge.auth.utils import update_session_roles
        from concierge.utils.role_helpers import get_default_dashboard_path
        
        user_data = get_user(user_id)
        
        # Check if this is an email verification for an existing logged-in user
        current_user_id = session.get('user_id')
        if not user_data and current_user_id and auth_method == 'email' and token_email:
            print(f"Email verification attempt for logged-in user {current_user_id} with email {token_email}") # DEBUG
            
            # Get the current user's data
            current_user = get_user(current_user_id)
            if current_user and current_user.get('pendingEmail') == token_email:
                print(f"Verifying pending email {token_email} for user {current_user_id}") # DEBUG
                
                # Update the current user's email verification status
                from google.cloud import firestore
                update_data = {
                    'emailVerified': True,
                    'EmailVerified': True,
                    'emailVerificationPending': False,
                    'emailAuthUID': uid,  # Store the email auth UID
                    'lastLoginAt': firestore.SERVER_TIMESTAMP
                }
                
                success = update_user(current_user_id, update_data)
                if success:
                    print(f"Email verification completed for user {current_user_id}") # DEBUG
                    
                    # Keep the user logged in with their existing session
                    user_roles = normalize_user_roles(current_user)
                    primary_role = get_primary_role(current_user)
                    
                    # Determine redirect URL based on user role
                    redirect_url = '/dashboard'  # Default for hosts
                    if primary_role == 'guest':
                        redirect_url = '/guest'
                    elif 'host' in user_roles:
                        redirect_url = '/dashboard'  # Hosts get priority over guest role
                    
                    return jsonify({
                        'success': True,
                        'message': 'Email verified successfully',
                        'redirect_url': redirect_url,
                        'user_id': current_user_id,
                        'roles': user_roles,
                        'primary_role': primary_role
                    })
        
        if not user_data:
            # User not found in our database, check for existing users with same credentials
            existing_user = None

            if auth_method == 'phone' and firebase_phone:
                print(f"No user found with UID {uid}, checking for existing user with phone {firebase_phone}") # DEBUG
                existing_user = find_user_by_phone(firebase_phone)
                credential_type = "phone number"
                credential_value = firebase_phone
            elif auth_method == 'email' and token_email:
                print(f"No user found with UID {uid}, checking for existing user with email {token_email}") # DEBUG
                existing_user = get_user_by_email(token_email)
                credential_type = "email"
                credential_value = token_email

            if existing_user and not existing_user.get('isTemporary', False):
                # Found existing permanent user with this credential - handle account linking
                existing_uid = existing_user.get('id') or existing_user.get('uid')
                print(f"Found existing permanent user {existing_uid} with {credential_type} {credential_value}") # DEBUG
                
                if auth_method == 'email' and existing_uid != uid:
                    # Email authentication with different Firebase UID - need to link accounts
                    print(f"Account linking needed: Firebase UID {uid} -> Existing user {existing_uid}") # DEBUG
                    
                    # Update the existing user's Firebase UID to the new email-based UID
                    # This allows them to use both phone and email authentication
                    from google.cloud import firestore
                    update_data = {
                        'firebaseUID': uid,  # Store the new Firebase UID
                        'emailAuthUID': uid,  # Track email-specific UID
                        'emailVerified': True,  # Mark email as verified since they used email link
                        'EmailVerified': True,
                        'lastLoginAt': firestore.SERVER_TIMESTAMP
                    }
                    
                    # If email wasn't already set, add it
                    if not existing_user.get('email') and not existing_user.get('Email'):
                        update_data['email'] = token_email
                        update_data['Email'] = token_email
                    
                    success = update_user(existing_uid, update_data)
                    if success:
                        print(f"Successfully linked email auth UID {uid} to existing user {existing_uid}") # DEBUG
                        # Use the existing user's UID for session
                        uid = existing_uid
                        user_data = existing_user
                    else:
                        print(f"Failed to link accounts, proceeding with existing user {existing_uid}") # DEBUG
                        uid = existing_uid
                        user_data = existing_user
                else:
                    print(f"Logging in existing user {existing_uid} via {auth_method} authentication") # DEBUG
                    # Use the existing user's data
                    user_data = existing_user
        
        # Clear login data from session
        session.pop('phone_login_data', None)
        
        # Set up user session with new role system
        session['user_id'] = user_id
        update_session_roles(user_data)
        
        # Check PIN status and provide appropriate response
        user_has_pin = bool(user_data.get('pinCode'))
        has_default_pin = user_data.get('hasDefaultPin', False)
        
        # Determine default dashboard path based on user roles
        default_path = get_default_dashboard_path(user_data)
        
        response_data = {
            'success': True,
            'message': 'Login successful',
            'redirect': url_for('views.dashboard') if default_path == '/dashboard' else url_for('views.guest_dashboard')
        }
        
        if not user_has_pin:
            # User has no PIN - prompt for PIN creation
            response_data.update({
                'new_permanent_user': True,
                'prompt_pin_creation': True
            })
        elif has_default_pin:
            # User has default PIN - show warning to change it
            response_data.update({
                'has_default_pin': True
            })
        
        return jsonify(response_data)
    
    elif step == 'otp_login':
        # Legacy: User logged in without PIN → Check if they should set up a PIN
        from concierge.utils.firestore_client import get_user
        from concierge.auth.utils import update_session_roles
        
        user_data = get_user(user_id)
        
        session.pop('phone_login_data', None)
        session['user_id'] = user_id
        if user_data:
            update_session_roles(user_data)
        else:
            # Fallback for missing user data
            session['user_roles'] = ['guest']
            session['user_role'] = 'guest'
        
        # Check if this user has never set up a PIN (new permanent user)
        has_pin = user_data.get('pinCode') if user_data else False
        if not has_pin:
            # This is a permanent user without any PIN → prompt for PIN creation
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'redirect': url_for('views.dashboard'),
                'new_permanent_user': True,  # Signal this is a permanent user without PIN
                'prompt_pin_creation': True  # Signal to show PIN creation prompt
            })
        else:
            # User has a PIN already, just login normally
            # The dashboard will handle showing warnings for users with default PINs
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'redirect': url_for('views.dashboard')
            })
    
    elif step == 'otp_recovery':
        # PIN recovery successful
        session.pop('phone_login_data', None)
        session['user_id'] = user_id
        session['user_role'] = 'guest'
        
        return jsonify({
            'success': True,
            'message': 'Account recovered successfully',
            'redirect': url_for('views.dashboard')
        })
    
    return jsonify({'error': 'Invalid login step'}), 400

@auth_bp.route('/logout')
def logout():
    """Logs the user out by clearing the session."""
    user_id = session.get('user_id')
    session.clear()
    print(f"User {user_id} logged out.") # DEBUG
    flash('You have been logged out.', 'info')
    
    # Also clear magic link session cookie if present
    response = make_response(redirect(url_for('auth.login')))
    
    # Clear magic link session cookie
    response.set_cookie(
        'magicLinkSession',
        '',
        expires=0,
        httponly=True,
        secure=False,
        samesite='Lax'
    )
    
    return response

@auth_bp.route('/verify-token', methods=['POST'])
def verify_token_route():
    """Verifies the authentication token received from the client."""
    id_token = request.json.get('idToken')
    auth_method = request.json.get('authMethod', 'phone')  # 'phone' or 'email'
    email = request.json.get('email')  # For email authentication

    if not id_token:
        print("Verify token request missing idToken.") # DEBUG
        return jsonify({"success": False, "error": "ID token is required."}), 400

    try:
        print(f"Received token for verification: {id_token[:10]}...") # DEBUG: Log partial token
        # Replace Firebase token verification with our new verify_token function
        decoded_token = verify_token(id_token)
        if not decoded_token:
             # verify_token logs the specific error
             print("Token verification failed (verify_token returned None).") # DEBUG
             return jsonify({"success": False, "error": "Invalid or expired token."}), 401

        uid = decoded_token['uid']
        phone_number = decoded_token.get('phone_number')
        token_email = decoded_token.get('email') or email
        print(f"Token verified successfully for UID: {uid}, auth_method: {auth_method}") # DEBUG

        # --- User Role and Profile Handling ---
        # First check if user exists by UID
        user_data = get_user(uid)
        from concierge.utils.role_helpers import normalize_user_roles, get_primary_role

        # Check if this is an email verification for an existing logged-in user
        current_user_id = session.get('user_id')
        if not user_data and current_user_id and auth_method == 'email' and token_email:
            print(f"Email verification attempt for logged-in user {current_user_id} with email {token_email}") # DEBUG
            
            # Get the current user's data
            current_user = get_user(current_user_id)
            if current_user and current_user.get('pendingEmail') == token_email:
                print(f"Verifying pending email {token_email} for user {current_user_id}") # DEBUG
                
                # Update the current user's email verification status
                from google.cloud import firestore
                update_data = {
                    'emailVerified': True,
                    'EmailVerified': True,
                    'emailVerificationPending': False,
                    'emailAuthUID': uid,  # Store the email auth UID
                    'lastLoginAt': firestore.SERVER_TIMESTAMP
                }
                
                success = update_user(current_user_id, update_data)
                if success:
                    print(f"Email verification completed for user {current_user_id}") # DEBUG
                    
                    # Keep the user logged in with their existing session
                    user_roles = normalize_user_roles(current_user)
                    primary_role = get_primary_role(current_user)
                    
                    # Determine redirect URL based on user role
                    redirect_url = '/dashboard'  # Default for hosts
                    if primary_role == 'guest':
                        redirect_url = '/guest'
                    elif 'host' in user_roles:
                        redirect_url = '/dashboard'  # Hosts get priority over guest role
                    
                    return jsonify({
                        'success': True,
                        'message': 'Email verified successfully',
                        'redirect_url': redirect_url,
                        'user_id': current_user_id,
                        'roles': user_roles,
                        'primary_role': primary_role
                    })

        if user_data:
            # User exists, get roles from Firestore
            user_roles = normalize_user_roles(user_data)
            primary_role = get_primary_role(user_data)
            print(f"Existing user {uid} found with roles: {user_roles}, primary: {primary_role}") # DEBUG
            # Update last login time
            from google.cloud import firestore
            update_user(uid, {'lastLoginAt': firestore.SERVER_TIMESTAMP})
        else:
            # User not found by UID - check if a user with this phone/email already exists
            existing_user = None

            if auth_method == 'phone' and phone_number:
                print(f"No user found with UID {uid}, checking for existing user with phone {phone_number}") # DEBUG
                existing_user = find_user_by_phone(phone_number)
                credential_type = "phone number"
                credential_value = phone_number
            elif auth_method == 'email' and token_email:
                print(f"No user found with UID {uid}, checking for existing user with email {token_email}") # DEBUG
                existing_user = get_user_by_email(token_email)
                credential_type = "email"
                credential_value = token_email

            if existing_user and not existing_user.get('isTemporary', False):
                # Found existing permanent user with this credential - handle account linking
                existing_uid = existing_user.get('id') or existing_user.get('uid')
                print(f"Found existing permanent user {existing_uid} with {credential_type} {credential_value}") # DEBUG
                
                if auth_method == 'email' and existing_uid != uid:
                    # Email authentication with different Firebase UID - need to link accounts
                    print(f"Account linking needed: Firebase UID {uid} -> Existing user {existing_uid}") # DEBUG
                    
                    # Update the existing user's Firebase UID to the new email-based UID
                    # This allows them to use both phone and email authentication
                    from google.cloud import firestore
                    update_data = {
                        'firebaseUID': uid,  # Store the new Firebase UID
                        'emailAuthUID': uid,  # Track email-specific UID
                        'emailVerified': True,  # Mark email as verified since they used email link
                        'EmailVerified': True,
                        'lastLoginAt': firestore.SERVER_TIMESTAMP
                    }
                    
                    # If email wasn't already set, add it
                    if not existing_user.get('email') and not existing_user.get('Email'):
                        update_data['email'] = token_email
                        update_data['Email'] = token_email
                    
                    success = update_user(existing_uid, update_data)
                    if success:
                        print(f"Successfully linked email auth UID {uid} to existing user {existing_uid}") # DEBUG
                        # Use the existing user's UID for session
                        uid = existing_uid
                        user_data = existing_user
                    else:
                        print(f"Failed to link accounts, proceeding with existing user {existing_uid}") # DEBUG
                        uid = existing_uid
                        user_data = existing_user
                else:
                    print(f"Logging in existing user {existing_uid} via {auth_method} authentication") # DEBUG
                    # Use the existing user's data
                    user_data = existing_user
                    uid = existing_uid  # Use the existing UID
                    
                    # Update last login time
                    from google.cloud import firestore
                    update_user(uid, {'lastLoginAt': firestore.SERVER_TIMESTAMP})
                
                # Get user roles
                user_roles = normalize_user_roles(user_data)
                primary_role = get_primary_role(user_data)
                print(f"User {uid} logged in with roles: {user_roles}, primary: {primary_role}") # DEBUG
            else:
                # New user detected - don't auto-create, redirect to account type selection
                print(f"New user detected with UID: {uid}. Redirecting to account type selection...") # DEBUG
                
                # Store signup data in session for account type selection flow
                session['signup_data'] = {
                    'firebase_uid': uid,
                    'phone_number': phone_number,
                    'email': token_email,
                    'display_name': decoded_token.get('name', 'New User'),
                    'id_token': id_token,  # Store the token for later use
                    'auth_method': auth_method,  # Store the authentication method
                    'step': 'account_type_selection'
                }
                
                return jsonify({
                    "success": False,
                    "message": "New user detected. Please select your account type.",
                    "redirect": url_for('auth.signup_choice'),
                    "new_user": True
                }), 202  # HTTP 202 Accepted (needs further action)

        # --- Session Management ---
        session.permanent = True # Use the permanent session lifetime from app config
        session['user_id'] = uid
        
        # Store roles in session using new role system
        from concierge.auth.utils import update_session_roles
        update_session_roles(user_data)
        
        g.user_id = uid # Set g.user_id for the current request context
        g.user_roles = session.get('user_roles', ['guest'])
        g.user_role = session.get('user_role', 'guest')

        # Determine redirect URL based on user role
        redirect_url = '/dashboard'  # Default for hosts
        if g.user_role == 'guest':
            redirect_url = '/guest'
        elif 'host' in g.user_roles:
            redirect_url = '/dashboard'  # Hosts get priority over guest role

        print(f"Session created for user {uid}, roles {g.user_roles}, primary {g.user_role}. Session keys: {list(session.keys())}") # DEBUG
        return jsonify({
            "success": True,
            "message": "Token verified successfully.",
            "role": g.user_role,
            "roles": g.user_roles,
            "redirect_url": redirect_url
        })

    except Exception as e:
        print(f"An unexpected error occurred during token verification: {e}") # DEBUG
        # Log the full traceback for unexpected errors
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": "An unexpected error occurred."}), 500

@auth_bp.route('/create-standalone-guest', methods=['POST'])
def create_standalone_guest():
    """Create a standalone guest account without magic link."""
    signup_data = session.get('signup_data')
    if not signup_data or signup_data.get('step') != 'account_type_selection':
        return redirect(url_for('auth.phone_login'))
    
    try:
        # Create guest account using Firebase data from OTP verification
        firebase_uid = signup_data.get('firebase_uid')
        phone_number = signup_data.get('phone_number')
        
        if not firebase_uid or not phone_number:
            flash('Session expired. Please start over.', 'error')
            return redirect(url_for('auth.phone_login'))
        
        user_data = {
            'uid': firebase_uid,
            'phoneNumber': phone_number,
            'role': 'guest',
            'displayName': 'New Guest',
            'accountType': 'permanent',
            'createdAt': datetime.now().isoformat(),
            'isTemporary': False
            # No pinCode field - user hasn't set up a PIN yet
        }
        
        success = create_user(firebase_uid, user_data)
        if success:
            session.pop('signup_data', None)
            session['user_id'] = firebase_uid
            session['user_role'] = 'guest'
            
            # Check if this signup was initiated from a magic link (legacy support)
            magic_link_signup = session.pop('magic_link_signup', None)
            if magic_link_signup:
                # Attach reservation to the newly created permanent user
                token = magic_link_signup.get('token')
                if token:
                    try:
                        from concierge.utils.firestore_client import get_magic_link_by_token, attach_reservation_to_permanent_user
                        magic_link_data = get_magic_link_by_token(token)
                        if magic_link_data:
                            reservation_id = magic_link_data.get('reservation_id')
                            if reservation_id:
                                attach_reservation_to_permanent_user(firebase_uid, reservation_id)
                                print(f"Attached reservation {reservation_id} to new permanent user {firebase_uid}")
                    except Exception as e:
                        print(f"Error attaching reservation to new user: {e}")
                        # Don't fail the signup, just log the error
            
            flash('Guest account created successfully! You can set up a PIN later for faster access.', 'success')
            return redirect(url_for('views.dashboard'))
        else:
            flash('Failed to create account. Please try again.', 'error')
            return render_template('guest_magic_link_prompt.html',
                                 phone_number=signup_data.get('phone_number'))
    
    except Exception as e:
        print(f"Error creating standalone guest account: {e}")
        flash('An error occurred. Please try again.', 'error')
        return render_template('guest_magic_link_prompt.html',
                             phone_number=signup_data.get('phone_number'))

@auth_bp.route('/process-magic-link', methods=['POST'])
def process_magic_link():
    """Process magic link entered by guest user."""
    signup_data = session.get('signup_data')
    if not signup_data or signup_data.get('step') != 'account_type_selection':
        return redirect(url_for('auth.phone_login'))
    
    magic_link_url = request.form.get('magic_link_url', '').strip()
    
    if not magic_link_url:
        flash('Please enter a magic link URL.', 'error')
        return render_template('guest_magic_link_prompt.html',
                             phone_number=signup_data.get('phone_number'))
    
    try:
        # Extract token from magic link URL
        import re
        # Match URLs like /magic/TOKEN or https://domain.com/magic/TOKEN
        token_match = re.search(r'/magic/([a-zA-Z0-9]+)', magic_link_url)
        
        if not token_match:
            flash('Invalid magic link format. Please check the link and try again.', 'error')
            return render_template('guest_magic_link_prompt.html',
                                 phone_number=signup_data.get('phone_number'))
        
        token = token_match.group(1)
        
        # Validate the magic link token
        from concierge.utils.firestore_client import get_magic_link_by_token, attach_reservation_to_permanent_user
        magic_link_data = get_magic_link_by_token(token)
        
        if not magic_link_data:
            flash('This magic link is invalid or has expired. Please contact your host for a new link.', 'error')
            return render_template('guest_magic_link_prompt.html',
                                 phone_number=signup_data.get('phone_number'))
        
        # Get reservation ID from magic link
        reservation_id = magic_link_data.get('reservation_id')
        if not reservation_id:
            flash('This magic link does not contain reservation information. Please contact your host.', 'error')
            return render_template('guest_magic_link_prompt.html',
                                 phone_number=signup_data.get('phone_number'))
        
        # Create permanent guest account - handle both main login flow (id_token) and phone login flow (firebase_uid)
        firebase_uid = signup_data.get('firebase_uid')
        phone_number = signup_data.get('phone_number')
        
        if not firebase_uid or not phone_number:
            # Check if we have data from main login flow
            if signup_data.get('id_token'):
                firebase_uid = signup_data.get('firebase_uid')
                phone_number = signup_data.get('phone_number')
            
            if not firebase_uid or not phone_number:
                flash('Authentication session expired. Please start over.', 'error')
                return redirect(url_for('auth.phone_login'))
        
        email = signup_data.get('email')
        display_name = signup_data.get('display_name', 'New Guest')
        
        user_data = {
            'uid': firebase_uid,
            'phoneNumber': phone_number,
            'email': email,
            'role': 'guest',
            'displayName': display_name,
            'accountType': 'permanent',
            'createdAt': datetime.now().isoformat(),
            'isTemporary': False,
            'reservationIds': [reservation_id]  # Include the reservation immediately
        }
        
        success = create_user(firebase_uid, user_data)
        if success:
            # Attach the reservation to the permanent user
            try:
                attach_reservation_to_permanent_user(firebase_uid, reservation_id, token)
                print(f"Created permanent guest account {firebase_uid} and attached reservation {reservation_id} via magic link token")
            except Exception as attach_error:
                print(f"Warning: Failed to attach reservation {reservation_id} to user {firebase_uid}: {attach_error}")
                # Continue anyway as the user is created and reservation is in user data
            
            # Clear signup data and create session
            session.pop('signup_data', None)
            session['user_id'] = firebase_uid
            session['user_role'] = 'guest'
            
            flash('Account created successfully with your reservation attached!', 'success')
            return redirect(url_for('views.dashboard'))
        else:
            flash('Failed to create account. Please try again.', 'error')
            return render_template('guest_magic_link_prompt.html',
                                 phone_number=signup_data.get('phone_number'))
        
    except Exception as e:
        print(f"Error processing magic link: {e}")
        flash('An error occurred processing the magic link. Please try again.', 'error')
        return render_template('guest_magic_link_prompt.html',
                             phone_number=signup_data.get('phone_number'))
