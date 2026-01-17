from flask import Blueprint, jsonify, request, session, current_app, abort, g
import json
import traceback
import os
from datetime import datetime, timezone, timedelta # Import datetime for ISO format conversion

# --- Imports from our modules ---
from concierge.auth.utils import login_required # Get decorator
from concierge.api.utils import generate_qna_with_gemini # Import Gemini Q&A generation function
from concierge.utils.reservations import update_all_reservations, fetch_and_parse_ical

# Import Firestore client functions
from concierge.utils.firestore_client import (
    get_user, get_property, list_properties_by_host, update_property,
    create_property, delete_property, update_user,
    create_knowledge_source, list_knowledge_sources,
    create_knowledge_item, list_knowledge_items_by_property, list_knowledge_items_by_source,
    get_knowledge_item, update_knowledge_item, update_knowledge_item_status,
    delete_knowledge_item, find_similar_knowledge_items, generate_embedding,
    list_property_reservations, update_reservation_phone,
    create_magic_link, list_magic_links_by_reservation, revoke_magic_link,
    get_reservation, generate_magic_link_url, record_data_access_consent, get_user_consents,
    get_property_magic_link_token, create_property_magic_link
)

# Import Firestore AI helpers
from concierge.utils.firestore_ai_helpers import (
    process_query_with_rag, process_query_with_tools
)

# Import Airbnb scraper utilities
from concierge.utils.airbnb_scraper import AirbnbScraper
from concierge.utils.airbnb_integration import preview_airbnb_properties
# Import specific config variables or the whole config module
from concierge.config import LAMBDA_CLIENT
# Import Gemini variables from utils.gemini_config
from concierge.utils.gemini_config import genai_enabled, gemini_model
from concierge.utils.rate_limiter import get_gemini_rate_limiter

def normalize_airbnb_url_for_duplicate_check(url: str) -> str:
    """
    Normalize Airbnb URL for duplicate checking by removing query parameters.
    This should match the normalization done in the scraper.
    """
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Reconstruct URL without query parameters and fragments
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Remove trailing slash if present
        if normalized.endswith('/'):
            normalized = normalized[:-1]

        return normalized

    except Exception as e:
        current_app.logger.warning(f"Failed to normalize URL {url}: {e}")
        return url  # Return original if normalization fails

# --- Temporary: Define helper functions here if not imported ---
# TODO: Move these function definitions to appropriate util files (e.g., utils/file_processing.py, utils/ai_helpers.py, utils/aws.py)

def extract_text_from_file(file_path):
    # Placeholder implementation - Copy the actual logic from app.py
    print(f"Placeholder: Extracting text from {file_path}")
    _, file_extension = os.path.splitext(file_path)
    if file_extension.lower() == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif file_extension.lower() in ['.pdf', '.docx']:
         # Add actual pdf/docx extraction logic here (using PyPDF2, python-docx)
         print(f"Warning: PDF/DOCX extraction logic not implemented in placeholder for {file_path}")
         return f"Extracted text from {os.path.basename(file_path)}" # Dummy text
    else:
        print(f"Unsupported file type for text extraction: {file_extension}")
        return None

def generate_qna(knowledge_base_text):
    # Placeholder implementation - Copy the actual logic from app.py
    print(f"Placeholder: Generating Q&A for text length: {len(knowledge_base_text)}")
    if not genai_enabled or not gemini_model:
        print("Gemini not enabled or model not initialized.")
        return [] # Return empty list or raise error

    prompt = f"""
    Generate a list of question and answer pairs based on the following text. The questions should be things a guest might ask, and the answers should be directly derived from the text. Format the output as a JSON list of objects, where each object has a "question" and "answer" key.

    Text:
    {knowledge_base_text}

    JSON Output:
    """
    try:
        response = gemini_model.generate_content(prompt)
        # Basic cleanup attempt
        cleaned_response = response.text.strip().lstrip('```json').rstrip('```')
        qna_list = json.loads(cleaned_response)
        if not isinstance(qna_list, list):
             raise ValueError("Generated response is not a JSON list.")
        # Further validation could be added here (check for question/answer keys)
        print(f"Generated {len(qna_list)} Q&A pairs.")
        return qna_list
    except json.JSONDecodeError as e:
        print(f"Error decoding Gemini JSON response: {e}\nRaw response:\n{response.text}")
        return [{"question": "Error generating Q&A", "answer": "Could not parse the AI response."}]
    except Exception as e:
        print(f"Error generating Q&A with Gemini: {e}")
        # Log traceback for detailed debugging
        traceback.print_exc()
        return [{"question": "Error generating Q&A", "answer": f"An error occurred: {e}"}]

# --- End Temporary Helper Functions ---


# Create Blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# In-memory tracking for long-running import jobs that can be canceled from the UI
# Structure: { job_id: { 'canceled': bool, 'started_at': datetime } }
IMPORT_JOBS = {}

@api_bp.route('/gemini-voice-config', methods=['GET'])
def get_gemini_voice_config():
    """Provides configuration needed for Gemini Voice frontend, including the API key."""
    # Check if user is authenticated via regular login or magic link session
    user_id = session.get('user_id')
    magic_link_session = request.cookies.get('magicLinkSession')

    # Allow access for regular authenticated users or magic link users
    if not user_id and not magic_link_session:
        current_app.logger.error("Gemini voice config requested without authentication")
        return jsonify({"error": "Authentication required"}), 401

    # Validate magic link session if present
    if magic_link_session and not user_id:
        try:
            from concierge.utils.session_manager import validate_session
            is_valid, temp_user_id, reason = validate_session(magic_link_session)
            if not is_valid:
                current_app.logger.error(f"Invalid magic link session for voice config: {reason}")
                return jsonify({"error": "Invalid session"}), 401
            user_id = temp_user_id  # Use temporary user ID
            current_app.logger.info(f"Magic link user {temp_user_id} requesting voice config")
        except Exception as e:
            current_app.logger.error(f"Error validating magic link session: {e}")
            return jsonify({"error": "Session validation error"}), 401

    api_key = os.getenv('GEMINI_API_KEY')

    if not api_key:
        current_app.logger.error(f"User {user_id} requested Gemini voice config, but GEMINI_API_KEY is not set on the server.")
        return jsonify({"error": "Voice service configuration missing on server."}), 500

    # Return only the necessary config (just the key for now)
    return jsonify({
        "apiKey": api_key
        # Add any other necessary config here in the future
    })

@api_bp.route('/user/profile', methods=['GET'])
def get_user_profile_universal():
    """Gets the profile of the currently logged-in user (supports both regular and magic link sessions)."""
    # Check if user is authenticated via regular login or magic link session
    user_id = session.get('user_id')
    magic_link_session = request.cookies.get('magicLinkSession')

    # Allow access for regular authenticated users or magic link users
    if not user_id and not magic_link_session:
        current_app.logger.error("User profile requested without authentication")
        return jsonify({"error": "Authentication required"}), 401

    # Validate magic link session if present
    if magic_link_session and not user_id:
        try:
            from concierge.utils.session_manager import validate_session
            is_valid, temp_user_id, reason = validate_session(magic_link_session)
            if not is_valid:
                current_app.logger.error(f"Invalid magic link session for profile: {reason}")
                return jsonify({"error": "Invalid session"}), 401
            user_id = temp_user_id  # Use temporary user ID
            current_app.logger.info(f"Magic link user {temp_user_id} requesting profile")
        except Exception as e:
            current_app.logger.error(f"Error validating magic link session: {e}")
            return jsonify({"error": "Session validation error"}), 401

    try:
        # Check if this is a temporary user
        if user_id.startswith('temp_magic_'):
            # Get temporary user data
            from concierge.utils.firestore_client import get_temporary_user
            temp_user = get_temporary_user(user_id)

            if temp_user:
                # Return temporary user profile data
                profile_data = {
                    'displayName': temp_user.get('displayName', ''),
                    'email': temp_user.get('email', ''),
                    'phoneNumber': f"***-***-{temp_user.get('phoneNumberLast4', '****')}",
                    'language': temp_user.get('language', 'en-US'),
                    'role': 'temporary_guest',
                    'isTemporary': True
                }

                return jsonify({
                    "success": True,
                    "user": profile_data
                })
            else:
                return jsonify({"error": "Temporary user profile not found"}), 404
        else:
            # Regular user - get from Firestore
            from concierge.utils.firestore_client import get_user
            user_data = get_user(user_id)

            if user_data:
                # Return only safe profile data
                profile_data = {
                    'displayName': user_data.get('displayName') or user_data.get('DisplayName') or '',
                    'email': user_data.get('email') or user_data.get('Email') or '',
                    'phoneNumber': user_data.get('phoneNumber') or user_data.get('PhoneNumber') or '',
                    'language': user_data.get('language', 'en-US'),
                    'role': user_data.get('role', 'guest'),
                    'airbnbUserLink': user_data.get('airbnbUserLink', ''),
                    'timezone': user_data.get('timezone', ''),
                    'defaultCheckInTime': user_data.get('defaultCheckInTime', '15:00'),
                    'defaultCheckOutTime': user_data.get('defaultCheckOutTime', '11:00'),
                    'isTemporary': False
                }

                return jsonify({
                    "success": True,
                    "user": profile_data
                })
            else:
                return jsonify({"error": "User profile not found"}), 404

    except Exception as e:
        print(f"Error fetching profile for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error fetching profile: {e}"}), 500

@api_bp.route('/profile', methods=['PUT'])
def update_profile_universal():
    """Updates the profile of the currently logged-in user (supports both regular and magic link sessions)."""
    # Check if user is authenticated via regular login or magic link session
    user_id = session.get('user_id')
    magic_link_session = request.cookies.get('magicLinkSession')

    # Allow access for regular authenticated users or magic link users
    if not user_id and not magic_link_session:
        current_app.logger.error("Profile update requested without authentication")
        return jsonify({"error": "Authentication required"}), 401

    # Validate magic link session if present
    if magic_link_session and not user_id:
        try:
            from concierge.utils.session_manager import validate_session
            is_valid, temp_user_id, reason = validate_session(magic_link_session)
            if not is_valid:
                current_app.logger.error(f"Invalid magic link session for profile update: {reason}")
                return jsonify({"error": "Invalid session"}), 401
            user_id = temp_user_id  # Use temporary user ID
            current_app.logger.info(f"Magic link user {temp_user_id} updating profile")
        except Exception as e:
            current_app.logger.error(f"Error validating magic link session: {e}")
            return jsonify({"error": "Session validation error"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    try:
        # Check if this is a temporary user
        if user_id.startswith('temp_magic_'):
            # Handle temporary user profile update
            from concierge.utils.firestore_client import get_temporary_user, update_temporary_user_name

            # For temporary users, enforce phone number requirement when adding email
            email_provided = 'email' in data and data['email']
            phone_number_provided = 'phoneNumber' in data and data['phoneNumber']
            display_name_provided = 'displayName' in data and data['displayName']
            language_provided = 'language' in data and data['language']

            # If user is trying to add email without phone number, require both
            if email_provided and not phone_number_provided:
                return jsonify({
                    "error": "Phone number is required when adding email to temporary account",
                    "validation_error": "phone_required_with_email"
                }), 400

            # Allow display name updates without requiring phone/email
            update_data = {}

            if display_name_provided:
                update_data['displayName'] = data['displayName']

            if email_provided:
                update_data['email'] = data['email']

            if language_provided:
                update_data['language'] = data['language']

            if update_data:
                # Update temporary user data
                temp_user = get_temporary_user(user_id)
                if temp_user:
                    # Update the temporary user document using the dedicated function
                    if 'displayName' in update_data:
                        print(f"Profile update API: Updating temporary user {user_id} displayName to: {update_data['displayName']}")
                        # Note: user_data may not be in scope here; logging limited info only
                        print(f"Profile update API: Updating name for temporary user {user_id}")
                        
                        success = update_temporary_user_name(user_id, update_data['displayName'])
                        if not success:
                            print(f"Profile update API: Failed to update temporary user name for {user_id}")
                            return jsonify({"error": "Failed to update temporary user name"}), 500
                        else:
                            print(f"Profile update API: Successfully updated temporary user name for {user_id}")
                            
                            # Verify the update by fetching the user data again
                            updated_user_data = get_temporary_user(user_id)
                            if updated_user_data:
                                print(f"Profile update API: Verification - updated displayName: {updated_user_data.get('displayName', 'not found')}")
                            else:
                                print(f"Profile update API: Verification failed - could not fetch updated user data")
                    else:
                        print(f"Profile update API: No displayName in update_data, skipping name update")
                    
                    # For other fields, update directly using the general update function
                    if len(update_data) > 1 or 'displayName' not in update_data:
                        from concierge.utils.firestore_client import update_user
                        success = update_user(user_id, update_data)
                        if not success:
                            return jsonify({"error": "Failed to update temporary user profile"}), 500

                    response_data = {
                        "success": True,
                        "message": "Profile updated successfully",
                        "updated_fields": list(update_data.keys())
                    }
                    
                    # If phone number was provided, indicate that OTP verification is needed
                    if phone_number_provided:
                        response_data["phone_verification_required"] = True
                        response_data["phone_number"] = data['phoneNumber']
                    
                    return jsonify(response_data)
                else:
                    return jsonify({"error": "Temporary user not found"}), 404
            elif phone_number_provided:
                # Only phone number provided, return success and indicate OTP verification needed
                return jsonify({
                    "success": True,
                    "message": "Phone verification required",
                    "phone_verification_required": True,
                    "phone_number": data['phoneNumber'],
                    "updated_fields": []
                })
            else:
                return jsonify({"error": "No valid fields to update"}), 400
        else:
            # Regular user - update in Firestore
            from concierge.utils.firestore_client import update_user

            # Prepare update data
            update_data = {}

            if 'displayName' in data:
                update_data['displayName'] = data['displayName']

            if 'email' in data:
                update_data['email'] = data['email']

            if 'phoneNumber' in data:
                update_data['phoneNumber'] = data['phoneNumber']

            if 'language' in data:
                update_data['language'] = data['language']

            if 'airbnbUserLink' in data:
                update_data['airbnbUserLink'] = data['airbnbUserLink']

            if 'timezone' in data:
                update_data['timezone'] = data['timezone']

            if 'defaultCheckInTime' in data:
                update_data['defaultCheckInTime'] = data['defaultCheckInTime']

            if 'defaultCheckOutTime' in data:
                update_data['defaultCheckOutTime'] = data['defaultCheckOutTime']

            if update_data:
                # Update the user's profile in Firestore
                success = update_user(user_id, update_data)

                if success:
                    # Update session data if display name was changed
                    if 'displayName' in update_data:
                        session['guest_name'] = update_data['displayName']

                    return jsonify({
                        "success": True,
                        "message": "Profile updated successfully",
                        "updated_fields": list(update_data.keys())
                    })
                else:
                    return jsonify({"error": "Failed to update profile"}), 500
            else:
                return jsonify({"error": "No valid fields to update"}), 400

    except Exception as e:
        print(f"Error updating profile for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error updating profile: {e}"}), 500

@api_bp.route('/firebase-config', methods=['GET'])
def get_firebase_config():
    """Provides Firebase configuration (public endpoint for login functionality)."""
    try:
        # DEBUG: Log that this endpoint is being called without authentication
        current_app.logger.info("Firebase config endpoint called - NO LOGIN REQUIRED")
        
        # Get Firebase configuration from environment variables
        firebase_config = {
            "apiKey": os.getenv('FIREBASE_API_KEY'),
            "authDomain": os.getenv('FIREBASE_AUTH_DOMAIN'),  
            "projectId": os.getenv('FIREBASE_PROJECT_ID'),
            "storageBucket": os.getenv('FIREBASE_STORAGE_BUCKET'),
            "messagingSenderId": os.getenv('FIREBASE_MESSAGING_SENDER_ID'),
            "appId": os.getenv('FIREBASE_APP_ID'),
            "measurementId": os.getenv('FIREBASE_MEASUREMENT_ID', '')
        }
        
        # Check that required fields are present
        required_fields = ['apiKey', 'authDomain', 'projectId', 'storageBucket', 'messagingSenderId', 'appId']
        missing_fields = [field for field in required_fields if not firebase_config.get(field)]
        
        if missing_fields:
            current_app.logger.error(f"Missing Firebase config fields: {missing_fields}")
            return jsonify({"error": "Firebase configuration incomplete on server."}), 500
            
        return jsonify({
            "success": True,
            "config": firebase_config
        })
        
    except Exception as e:
        current_app.logger.error(f"Error providing Firebase config: {e}")
        return jsonify({"error": "Failed to retrieve Firebase configuration."}), 500

@api_bp.route('/ephemeral-token', methods=['POST'])
@login_required  
def get_ephemeral_token():
    """Generates an ephemeral token for the user."""
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        # Generate a new ephemeral token
        from concierge.utils.firestore_client import create_ephemeral_token
        token = create_ephemeral_token(user_id)

        if token:
            return jsonify({
                "success": True,
                "token": token
            })
        else:
            return jsonify({"error": "Failed to generate ephemeral token"}), 500

    except Exception as e:
        print(f"Error generating ephemeral token: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500

# === Current API Routes ===

@api_bp.route('/generate-qna', methods=['POST'])
@login_required
def generate_qna_route():
    """Generates Q&A pairs from provided text using Gemini."""
    if not genai_enabled:
        return jsonify({"error": "Q&A generation feature is disabled."}), 503

    data = request.get_json()
    knowledge_base_text = data.get('text')

    if not knowledge_base_text:
         return jsonify({"error": "No text provided for Q&A generation."}), 400

    try:
        qna_list = generate_qna(knowledge_base_text) # Use the helper
        return jsonify({"success": True, "qna": qna_list})
    except Exception as e:
        print(f"Error in /generate-qna route: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to generate Q&A: {e}"}), 500

@api_bp.route('/user-property')
@login_required
def get_user_property():
    """Gets the first property associated with the logged-in user."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore
    try:
        # First try to get properties from Firestore
        properties = list_properties_by_host(user_id)

        if properties:
            print(f"Found property for user {user_id} in Firestore: {properties[0].get('id')}") # DEBUG
            return jsonify({"success": True, "property": properties[0]})
        else:
            print(f"No properties found for user {user_id} in Firestore") # DEBUG
            # It's not necessarily an error if a user has no properties yet
            return jsonify({"success": True, "property": None, "message": "No property found for this user."})
    except Exception as e:
        print(f"Error fetching property for user {user_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Server error fetching property: {e}"}), 500

@api_bp.route('/user-properties')
@login_required
def get_user_properties():
    """Gets all properties associated with the logged-in user."""
    user_id = g.user_id
    print(f"Fetching properties for host dashboard, user: {user_id}")
    # No need to check for database availability since we're using Firestore
    try:
        # First try to get properties from Firestore
        raw_properties = list_properties_by_host(user_id)

        # Process properties to make them easier to work with in the frontend
        processed_properties = []
        for prop in raw_properties:
            # Firestore already includes 'id' field
            property_id = prop.get('id', '')

            processed_prop = {
                'id': property_id,
                'name': prop.get('name', 'Unnamed Property'),
                'description': prop.get('description', ''),
                'address': prop.get('address', ''),
                'icalUrl': prop.get('icalUrl', ''),
                'status': prop.get('status', 'active'),
                'new': prop.get('new', False),  # Include the new flag for setup workflow
                'checkInTime': prop.get('checkInTime', '15:00'),
                'checkOutTime': prop.get('checkOutTime', '11:00'),
                'wifiDetails': prop.get('wifiDetails', {}),
                'amenities': prop.get('amenities', {'basic': [], 'appliances': []}),  # Include amenities data
                'houseRules': prop.get('houseRules', []),  # Include house rules
                'safetyInfo': prop.get('safetyInfo', []),  # Include safety info
                'hostId': prop.get('hostId', ''),
                'createdAt': prop.get('createdAt'),
                'updatedAt': prop.get('updatedAt')
            }
            processed_properties.append(processed_prop)

        print(f"Found {len(processed_properties)} properties for user {user_id} in Firestore") # DEBUG

        # All properties are now stored in Firestore only

        return jsonify({"success": True, "properties": processed_properties})
    except Exception as e:
        print(f"Error fetching properties for user {user_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Server error fetching properties: {e}"}), 500

@api_bp.route('/property/<property_id>', methods=['PUT'])
@login_required
def update_property_endpoint(property_id):
    """Updates details for a specific property."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore

    data = request.get_json()
    if not data:
        return jsonify({"error": "No update data provided"}), 400

    # Get the property from Firestore to check ownership
    property_item = get_property(property_id)

    try:
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            return jsonify({"error": "Unauthorized - you do not own this property"}), 403

        # Update the property using Firestore update_property function
        success = update_property(property_id, data)

        if success:
            return jsonify({"success": True, "message": "Property updated successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to update property"}), 500

    except Exception as e:
        print(f"Error updating property {property_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Server error updating property: {e}"}), 500

@api_bp.route('/property/<property_id>', methods=['DELETE'])
@login_required
def delete_property_api(property_id):
    """Deletes a specific property."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore

    try:
        # Get the property from Firestore to check ownership
        property_item = get_property(property_id)

        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            return jsonify({"error": "Unauthorized - you do not own this property"}), 403

        # Delete the property using Firestore delete_property function
        success = delete_property(property_id)

        if success:
            return jsonify({"success": True, "message": "Property deleted successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to delete property"}), 500

    except Exception as e:
        print(f"Error deleting property {property_id}: {e}")
        return jsonify({"success": False, "error": f"Server error deleting property: {e}"}), 500

@api_bp.route('/property/<property_id>/knowledge-base', methods=['POST'])
@login_required
def upload_knowledge_base(property_id):
    """Handles file upload for a property's knowledge base."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore

    if 'knowledgeFile' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['knowledgeFile']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Import the functions we need
    from werkzeug.utils import secure_filename

    # 1. Security Check: Verify property ownership
    try:
        property_item = get_property(property_id)
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        if property_item.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted upload for property {property_id} owned by {property_item.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403
    except Exception as e:
        print(f"Error verifying property ownership for {property_id}: {e}")
        return jsonify({"error": f"Server error checking property: {e}"}), 500

    # 2. Save File Temporarily
    upload_folder = current_app.config.get('UPLOAD_FOLDER', '/tmp/concierge_uploads')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    filename = secure_filename(f"{property_id}_{file.filename}")
    file_path = os.path.join(upload_folder, filename)

    try:
        file.save(file_path)
        print(f"File temporarily saved to {file_path}")

        # 3. Extract Text (Using helper)
        knowledge_base_text = extract_text_from_file(file_path)
        if knowledge_base_text is None:
             # Clean up saved file before returning error
             os.remove(file_path)
             return jsonify({"error": "Unsupported file type or error during text extraction."}), 400

        # 4. Prepare Payload for Lambda
        payload = {
            "property_id": property_id,
            "user_id": user_id,
            "text_content": knowledge_base_text,
        }

        # 5. Update Property in Firestore
        update_property(property_id, {'knowledgeStatus': 'processing'})

        return jsonify({"success": True, "message": "Knowledge base received and processing started."})

    except Exception as e:
        print(f"Error processing knowledge base upload for property {property_id}: {e}")
        traceback.print_exc()
        # Clean up if file was saved
        if os.path.exists(file_path):
             try:
                  os.remove(file_path)
                  print(f"Cleaned up temporary file {file_path} after error.")
             except OSError as remove_err:
                  print(f"Error removing temporary file {file_path} after error: {remove_err}")
        return jsonify({"error": f"Server error during upload processing: {e}"}), 500


@api_bp.route('/property/<property_id>/reservations')
@login_required
def get_reservations(property_id):
    """Gets reservations for a specific property."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore

    try:
        # Get property to verify ownership
        property_item = get_property(property_id)
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted GET reservations for property {property_id} owned by {property_item.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Fetch reservations linked to this property
        reservations = list_property_reservations(property_id)

        print(f"Found {len(reservations)} reservations for property {property_id}") # DEBUG
        return jsonify({"success": True, "reservations": reservations})

    except Exception as e:
        print(f"Error fetching reservations for property {property_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error fetching reservations: {e}"}), 500

@api_bp.route('/knowledge/<item_id>/update', methods=['PUT'])
@login_required
def update_knowledge_item_route(item_id):
    """Update a knowledge item using Firestore with the new schema."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore

    # Get the JSON data
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    try:
        # Extract fields from request
        item_type = data.get('type')
        tags = data.get('tags', [])
        content = data.get('content')

        # Validate required fields
        if not content:
            return jsonify({"success": False, "error": "Content is required"}), 400

        if not item_type:
            return jsonify({"success": False, "error": "Type is required"}), 400

        # Get the knowledge item
        item_data = get_knowledge_item(item_id)
        if not item_data:
            return jsonify({"success": False, "error": "Knowledge item not found"}), 404

        # Get property ID from the item
        property_id = item_data.get('propertyId')
        if not property_id:
            return jsonify({"success": False, "error": "Invalid knowledge item (missing property ID)"}), 400

        # Get property data to check ownership
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"success": False, "error": "Property not found"}), 404

        # Check if the user is authorized to update this item
        if property_data.get('hostId') != user_id:
            print(f"Unauthorized attempt to update knowledge item {item_id} by user {user_id}")
            return jsonify({"success": False, "error": "You don't have permission to update this item"}), 403

        # Prepare the update data
        update_data = {
            'type': item_type,
            'tags': tags,
            'content': content,
            'updatedAt': datetime.now(timezone.utc)
        }

        # If status is provided and valid, update it
        status = data.get('status')
        valid_statuses = ['pending_review', 'approved', 'rejected']
        if status and status in valid_statuses:
            update_data['status'] = status

        # Update the item
        success = update_knowledge_item(item_id, update_data)
        if success:
            print(f"Knowledge item {item_id} updated by user {user_id}")

            # Generate new embedding if content changed
            if content != item_data.get('content'):
                try:
                    embedding = generate_embedding(content)
                    if embedding:
                        update_knowledge_item(item_id, {'embedding': embedding})
                        print(f"Generated new embedding for knowledge item {item_id}")
                except Exception as embed_err:
                    print(f"Warning: Failed to generate embedding for item {item_id}: {embed_err}")
                    # Continue even if embedding generation fails

            return jsonify({"success": True, "message": "Knowledge item updated successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to update knowledge item"}), 500

    except Exception as e:
        print(f"Error updating knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500

@api_bp.route('/knowledge/<item_id>/delete', methods=['DELETE'])
@login_required
def delete_knowledge_item_route(item_id):
    """Delete a knowledge item."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore

    try:
        # Get the knowledge item
        item_data = get_knowledge_item(item_id)
        if not item_data:
            return jsonify({"success": False, "error": "Knowledge item not found"}), 404

        # Get property ID from the item
        property_id = item_data.get('propertyId')
        if not property_id:
            return jsonify({"success": False, "error": "Invalid knowledge item (missing property ID)"}), 400

        # Get property data to check ownership
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"success": False, "error": "Property not found"}), 404

        # Check if the user is authorized to delete this item
        if property_data.get('hostId') != user_id:
            print(f"Unauthorized attempt to delete knowledge item {item_id} by user {user_id}")
            return jsonify({"success": False, "error": "You don't have permission to delete this item"}), 403

        # Delete the item
        success = delete_knowledge_item(item_id)
        if success:
            print(f"Knowledge item {item_id} deleted by user {user_id}")
            return jsonify({"success": True, "message": "Knowledge item deleted successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to delete knowledge item"}), 500

    except Exception as e:
        print(f"Error deleting knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500

@api_bp.route('/knowledge/<item_id>/generate-embedding', methods=['POST'])
@login_required
def generate_item_embedding(item_id):
    """Generate or regenerate embedding for a knowledge item."""
    user_id = g.user_id
    # No need to check for database availability since we're using Firestore

    try:
        # Get the knowledge item
        item_data = get_knowledge_item(item_id)
        if not item_data:
            return jsonify({"success": False, "error": "Knowledge item not found"}), 404

        # Get property ID from the item
        property_id = item_data.get('propertyId')
        if not property_id:
            return jsonify({"success": False, "error": "Invalid knowledge item (missing property ID)"}), 400

        # Get property data to check ownership
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"success": False, "error": "Property not found"}), 404

        # Check if the user is authorized to update this item
        if property_data.get('hostId') != user_id:
            print(f"Unauthorized attempt to update knowledge item {item_id} by user {user_id}")
            return jsonify({"success": False, "error": "You don't have permission to update this item"}), 403

        # Get content from the item
        content = item_data.get('content')
        if not content:
            return jsonify({"success": False, "error": "Item has no content to generate embedding from"}), 400

        # Generate embedding
        embedding = generate_embedding(content)
        if not embedding:
            return jsonify({"success": False, "error": "Failed to generate embedding"}), 500

        # Update the item with the new embedding
        update_data = {
            'embedding': embedding,
            'updatedAt': datetime.now(timezone.utc)
        }

        success = update_knowledge_item(item_id, update_data)
        if success:
            print(f"Generated embedding for knowledge item {item_id}")
            return jsonify({"success": True, "message": "Embedding generated successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to update knowledge item with new embedding"}), 500

    except Exception as e:
        print(f"Error generating embedding for knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"An error occurred: {str(e)}"}), 500

@api_bp.route('/properties/<property_id>/knowledge/generate-all-embeddings', methods=['POST'])
@login_required
def generate_all_embeddings(property_id):
    """
    Trigger embedding generation for all knowledge items for a property that:
    1. Are missing embeddings
    2. Have outdated content (content changed but embedding not updated)

    Uses batch processing to improve performance.
    """
    print(f"Embedding generation request for all knowledge items of property {property_id}")

    # Get user ID from session
    user_id = g.user_id
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    # Define batch size for processing
    BATCH_SIZE = 5  # Process 5 items per batch

    try:
        # Get the property
        property_data = get_property(property_id)

        if not property_data:
            return jsonify({'error': 'Property not found'}), 404

        if property_data.get('hostId') != user_id:
            return jsonify({'error': 'You do not have permission to manage this property'}), 403

        # Get all knowledge items for this property
        all_items = list_knowledge_items_by_property(property_id)

        if not all_items:
            return jsonify({
                'success': True,
                'message': 'No knowledge items found for this property',
                'total_items': 0,
                'missing_embeddings': 0,
                'outdated_embeddings': 0
            })

        print(f"Found {len(all_items)} knowledge items for property {property_id}")

        # Identify items that need embedding generation
        items_needing_embedding = []
        missing_embeddings = 0
        outdated_embeddings = 0

        for item in all_items:
            if not item.get('embedding'):
                items_needing_embedding.append(item['id'])
                missing_embeddings += 1
            elif item.get('contentUpdatedAt') and item.get('embeddingUpdatedAt'):
                # Check if content was updated after embedding was generated
                content_updated = item['contentUpdatedAt']
                embedding_updated = item['embeddingUpdatedAt']
                if content_updated > embedding_updated:
                    items_needing_embedding.append(item['id'])
                    outdated_embeddings += 1

        if not items_needing_embedding:
            return jsonify({
                'success': True,
                'message': 'All knowledge items already have up-to-date embeddings',
                'total_items': len(all_items),
                'missing_embeddings': 0,
                'outdated_embeddings': 0
            })

        # Process items in batches
        batch_count = (len(items_needing_embedding) + BATCH_SIZE - 1) // BATCH_SIZE  # Ceiling division

        # Start processing in the background (this would typically be done by a worker)
        # For now, we'll just return success and let the client poll for status
        return jsonify({
            'success': True,
            'message': f'Embedding generation started for {len(items_needing_embedding)} items',
            'total_items': len(all_items),
            'missing_embeddings': missing_embeddings,
            'outdated_embeddings': outdated_embeddings,
            'batch_size': BATCH_SIZE,
            'batch_count': batch_count
        })

    except Exception as e:
        print(f"Error during embedding generation: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Failed to process embedding generation: {str(e)}'}), 500

@api_bp.route('/property/<property_id>/reservations/<reservation_id>/phone', methods=['PUT'])
@login_required
def update_reservation_phone(property_id, reservation_id):
    """Updates the guest phone number for a specific reservation."""
    user_id = g.user_id # Host's user ID from session
    # No need to check for database availability since we're using Firestore

    data = request.get_json()
    phone_number = data.get('phone_number')

    if not phone_number: # Add validation for phone format if needed
        return jsonify({"error": "Phone number is required."}), 400

    try:
        # Verify the property exists and user is the owner
        property_item = get_property(property_id)
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to modify reservation for property {property_id} owned by {property_item.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Update the reservation with the new phone number
        success = update_reservation_phone(reservation_id, phone_number)

        if success:
            print(f"User {user_id} updated phone for reservation {reservation_id} to {phone_number}")
            return jsonify({"success": True, "message": "Phone number updated successfully"})
        else:
            return jsonify({"error": "Failed to update phone number"}), 500

    except Exception as e:
        print(f"Error updating phone for reservation {reservation_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error during update: {e}"}), 500

@api_bp.route('/property/<property_id>/reservations/<reservation_id>/contacts', methods=['PUT'])
@login_required
def update_reservation_contacts_api(property_id, reservation_id):
    """Updates the additional contacts for a specific reservation."""
    user_id = g.user_id # Host's user ID from session
    # No need to check for database availability since we're using Firestore

    # Import the update_reservation_contacts function
    from concierge.utils.firestore_client import update_reservation_contacts

    data = request.get_json()
    contacts = data.get('contacts')

    if contacts is None:
        return jsonify({"error": "Contacts data is required."}), 400

    try:
        # Verify the property exists and user is the owner
        property_item = get_property(property_id)
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to modify reservation contacts for property {property_id} owned by {property_item.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Validate contacts format
        if not isinstance(contacts, list):
            return jsonify({"error": "Contacts must be an array"}), 400

        for contact in contacts:
            if not isinstance(contact, dict) or 'name' not in contact or 'phone' not in contact:
                return jsonify({"error": "Each contact must have name and phone"}), 400

        # Update the reservation with the new contacts
        success = update_reservation_contacts(reservation_id, contacts)

        if success:
            print(f"User {user_id} updated contacts for reservation {reservation_id}")
            return jsonify({"success": True, "message": "Contacts updated successfully"})
        else:
            return jsonify({"error": "Failed to update contacts"}), 500

    except Exception as e:
        print(f"Error updating contacts for reservation {reservation_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error during update: {e}"}), 500

@api_bp.route('/property/<property_id>/reservations/<reservation_id>', methods=['PUT'])
@login_required
def update_reservation_details(property_id, reservation_id):
    """Updates comprehensive reservation details including guest info, dates, times, and notes."""
    user_id = g.user_id

    # Import required functions
    from concierge.utils.firestore_client import update_reservation, get_reservation

    data = request.get_json()
    if not data:
        return jsonify({"error": "No update data provided"}), 400

    try:
        # Verify the property exists and user is the owner
        property_item = get_property(property_id)
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to modify reservation for property {property_id} owned by {property_item.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Verify reservation exists and belongs to this property
        reservation = get_reservation(reservation_id)
        if not reservation:
            return jsonify({"error": "Reservation not found"}), 404

        if reservation.get('propertyId') != property_id:
            return jsonify({"error": "Reservation doesn't belong to this property"}), 403

        # Prepare update data with validation
        update_data = {}

        # Guest information
        if 'guestName' in data:
            guest_name = data['guestName'].strip() if data['guestName'] else ''
            if guest_name:
                update_data['guestName'] = guest_name

        if 'guestPhoneNumber' in data:
            phone_number = data['guestPhoneNumber'].strip() if data['guestPhoneNumber'] else ''
            if phone_number:
                update_data['guestPhoneNumber'] = phone_number

        # Dates
        if 'startDate' in data:
            start_date = data['startDate']
            if start_date:
                update_data['startDate'] = start_date

        if 'endDate' in data:
            end_date = data['endDate']
            if end_date:
                update_data['endDate'] = end_date

        # Check-in/out times
        if 'checkinTime' in data:
            checkin_time = data['checkinTime']
            if checkin_time:
                update_data['checkinTime'] = checkin_time

        if 'checkoutTime' in data:
            checkout_time = data['checkoutTime']
            if checkout_time:
                update_data['checkoutTime'] = checkout_time

        # Notes and summary
        if 'summary' in data:
            summary = data['summary']
            if summary is not None:  # Allow empty string
                update_data['summary'] = summary

        if 'hostNotes' in data:
            host_notes = data['hostNotes']
            if host_notes is not None:  # Allow empty string
                update_data['hostNotes'] = host_notes

        # Additional contacts
        if 'additionalContacts' in data:
            contacts = data['additionalContacts']
            if isinstance(contacts, list):
                # Validate contacts format
                valid_contacts = []
                for contact in contacts:
                    if isinstance(contact, dict) and contact.get('name') and contact.get('phone'):
                        valid_contacts.append({
                            'name': contact['name'].strip(),
                            'phone': contact['phone'].strip()
                        })
                update_data['additional_contacts'] = valid_contacts

        # If no valid updates, return error
        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        # Update the reservation
        success = update_reservation(reservation_id, update_data)

        if success:
            print(f"User {user_id} updated reservation {reservation_id} with fields: {list(update_data.keys())}")
            return jsonify({
                "success": True,
                "message": "Reservation updated successfully",
                "updated_fields": list(update_data.keys())
            })
        else:
            return jsonify({"error": "Failed to update reservation"}), 500

    except Exception as e:
        print(f"Error updating reservation {reservation_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error during update: {e}"}), 500

@api_bp.route('/property/<property_id>/reservations/<reservation_id>/email/<email_type>', methods=['POST'])
@login_required
def send_reservation_email(property_id, reservation_id, email_type):
    """Send different types of emails to guests for a reservation."""
    user_id = g.user_id

    # Import required functions
    from concierge.utils.firestore_client import get_reservation

    try:
        # Verify the property exists and user is the owner
        property_item = get_property(property_id)
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to send email for property {property_id} owned by {property_item.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Verify reservation exists and belongs to this property
        reservation = get_reservation(reservation_id)
        if not reservation:
            return jsonify({"error": "Reservation not found"}), 404

        if reservation.get('propertyId') != property_id:
            return jsonify({"error": "Reservation doesn't belong to this property"}), 403

        # Validate email type
        valid_email_types = ['welcome', 'checkin_reminder', 'review_request']
        if email_type not in valid_email_types:
            return jsonify({"error": f"Invalid email type. Must be one of: {', '.join(valid_email_types)}"}), 400

        # Get guest information
        guest_name = reservation.get('guestName') or 'Guest'
        guest_phone = reservation.get('guestPhoneNumber') or ''
        property_name = property_item.get('name') or 'Property'

        # For now, return success with placeholder functionality
        # TODO: Implement actual email sending with templates
        email_templates = {
            'welcome': f'Welcome to {property_name}! We\'re excited to host you.',
            'checkin_reminder': f'Reminder: Your check-in at {property_name} is coming up soon.',
            'review_request': f'Thank you for staying at {property_name}! We\'d love your feedback.'
        }

        email_subject = {
            'welcome': f'Welcome to {property_name}!',
            'checkin_reminder': f'Check-in Reminder - {property_name}',
            'review_request': f'How was your stay at {property_name}?'
        }

        # Log the email that would be sent
        print(f"Email would be sent to {guest_name} ({guest_phone}) for reservation {reservation_id}")
        print(f"Subject: {email_subject[email_type]}")
        print(f"Content: {email_templates[email_type]}")

        # TODO: Implement actual email sending here
        # This could use AWS SES, SendGrid, or another email service

        return jsonify({
            "success": True,
            "message": f"{email_type.replace('_', ' ').title()} email sent successfully",
            "email_type": email_type,
            "recipient": guest_name,
            "subject": email_subject[email_type]
        })

    except Exception as e:
        print(f"Error sending {email_type} email for reservation {reservation_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error sending email: {e}"}), 500

@api_bp.route('/property/<property_id>/reservations/<reservation_id>/email-schedule', methods=['POST'])
@login_required
def schedule_reservation_emails(property_id, reservation_id):
    """Schedule automated emails for a reservation based on check-in/out dates."""
    user_id = g.user_id

    # Import required functions
    from concierge.utils.firestore_client import get_reservation, update_reservation

    data = request.get_json()
    if not data:
        return jsonify({"error": "No schedule data provided"}), 400

    try:
        # Verify the property exists and user is the owner
        property_item = get_property(property_id)
        if not property_item:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_item.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to schedule emails for property {property_id} owned by {property_item.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Verify reservation exists and belongs to this property
        reservation = get_reservation(reservation_id)
        if not reservation:
            return jsonify({"error": "Reservation not found"}), 404

        if reservation.get('propertyId') != property_id:
            return jsonify({"error": "Reservation doesn't belong to this property"}), 403

        # Get schedule preferences from request
        schedule_welcome = data.get('scheduleWelcome', True)
        schedule_checkin_reminder = data.get('scheduleCheckinReminder', True)
        schedule_review_request = data.get('scheduleReviewRequest', True)

        # Days before/after for scheduling
        welcome_days_before = data.get('welcomeDaysBefore', 3)
        checkin_reminder_hours_before = data.get('checkinReminderHoursBefore', 24)
        review_request_days_after = data.get('reviewRequestDaysAfter', 2)

        # Calculate schedule dates
        start_date = datetime.fromisoformat(reservation.get('startDate', '').replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(reservation.get('endDate', '').replace('Z', '+00:00'))

        scheduled_emails = []

        if schedule_welcome:
            welcome_date = start_date - timedelta(days=welcome_days_before)
            scheduled_emails.append({
                'type': 'welcome',
                'scheduled_date': welcome_date.isoformat(),
                'status': 'scheduled'
            })

        if schedule_checkin_reminder:
            reminder_date = start_date - timedelta(hours=checkin_reminder_hours_before)
            scheduled_emails.append({
                'type': 'checkin_reminder',
                'scheduled_date': reminder_date.isoformat(),
                'status': 'scheduled'
            })

        if schedule_review_request:
            review_date = end_date + timedelta(days=review_request_days_after)
            scheduled_emails.append({
                'type': 'review_request',
                'scheduled_date': review_date.isoformat(),
                'status': 'scheduled'
            })

        # Update reservation with scheduled emails
        update_data = {
            'scheduledEmails': scheduled_emails,
            'emailScheduleUpdated': datetime.now(timezone.utc).isoformat()
        }

        success = update_reservation(reservation_id, update_data)

        if success:
            print(f"User {user_id} scheduled {len(scheduled_emails)} emails for reservation {reservation_id}")
            return jsonify({
                "success": True,
                "message": f"Scheduled {len(scheduled_emails)} automated emails",
                "scheduled_emails": scheduled_emails
            })
        else:
            return jsonify({"error": "Failed to schedule emails"}), 500

    except Exception as e:
        print(f"Error scheduling emails for reservation {reservation_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error scheduling emails: {e}"}), 500

@api_bp.route('/knowledge-items/<item_id>/approve', methods=['POST'])
@login_required
def approve_knowledge_item(item_id):
    """Approve a knowledge item for use by the AI assistant."""
    user_id = g.user_id

    try:
        # Get the knowledge item to verify ownership
        knowledge_item = get_knowledge_item(item_id)
        if not knowledge_item:
            return jsonify({"error": "Knowledge item not found"}), 404

        # Get the property to verify user ownership
        property_id = knowledge_item.get('propertyId')
        if not property_id:
            return jsonify({"error": "Knowledge item has no associated property"}), 400

        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Associated property not found"}), 404

        # Check if the user owns this property
        if property_data.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to approve knowledge item for property {property_id} owned by {property_data.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Update the knowledge item status to approved
        success = update_knowledge_item_status(item_id, 'approved')

        if success:
            print(f"User {user_id} approved knowledge item {item_id}")
            return jsonify({
                "success": True,
                "message": "Knowledge item approved successfully"
            })
        else:
            return jsonify({"error": "Failed to approve knowledge item"}), 500

    except Exception as e:
        print(f"Error approving knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error approving knowledge item: {e}"}), 500

@api_bp.route('/knowledge-items/<item_id>/reject', methods=['POST'])
@login_required
def reject_knowledge_item(item_id):
    """Reject a knowledge item."""
    user_id = g.user_id

    try:
        # Get the knowledge item to verify ownership
        knowledge_item = get_knowledge_item(item_id)
        if not knowledge_item:
            return jsonify({"error": "Knowledge item not found"}), 404

        # Get the property to verify user ownership
        property_id = knowledge_item.get('propertyId')
        if not property_id:
            return jsonify({"error": "Knowledge item has no associated property"}), 400

        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Associated property not found"}), 404

        # Check if the user owns this property
        if property_data.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to reject knowledge item for property {property_id} owned by {property_data.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Update the knowledge item status to rejected
        success = update_knowledge_item_status(item_id, 'rejected')

        if success:
            print(f"User {user_id} rejected knowledge item {item_id}")
            return jsonify({
                "success": True,
                "message": "Knowledge item rejected successfully"
            })
        else:
            return jsonify({"error": "Failed to reject knowledge item"}), 500

    except Exception as e:
        print(f"Error rejecting knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error rejecting knowledge item: {e}"}), 500

@api_bp.route('/knowledge-items/<item_id>', methods=['DELETE'])
@login_required
def delete_knowledge_item_api(item_id):
    """Delete a knowledge item permanently."""
    user_id = g.user_id

    try:
        # Get the knowledge item to verify ownership
        knowledge_item = get_knowledge_item(item_id)
        if not knowledge_item:
            return jsonify({"error": "Knowledge item not found"}), 404

        # Get the property to verify user ownership
        property_id = knowledge_item.get('propertyId')
        if not property_id:
            return jsonify({"error": "Knowledge item has no associated property"}), 400

        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Associated property not found"}), 404

        # Check if the user owns this property
        if property_data.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to delete knowledge item for property {property_id} owned by {property_data.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Delete the knowledge item
        success = delete_knowledge_item(item_id)

        if success:
            print(f"User {user_id} deleted knowledge item {item_id}")
            return jsonify({
                "success": True,
                "message": "Knowledge item deleted successfully"
            })
        else:
            return jsonify({"error": "Failed to delete knowledge item"}), 500

    except Exception as e:
        print(f"Error deleting knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error deleting knowledge item: {e}"}), 500

@api_bp.route('/knowledge-items/<item_id>', methods=['PUT'])
@login_required
def update_knowledge_item_api(item_id):
    """Update a knowledge item's content, type, and tags."""
    user_id = g.user_id

    try:
        # Get the knowledge item to verify ownership
        knowledge_item = get_knowledge_item(item_id)
        if not knowledge_item:
            return jsonify({"error": "Knowledge item not found"}), 404

        # Get the property to verify user ownership
        property_id = knowledge_item.get('propertyId')
        if not property_id:
            return jsonify({"error": "Knowledge item has no associated property"}), 400

        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Associated property not found"}), 404

        # Check if the user owns this property
        if property_data.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to update knowledge item for property {property_id} owned by {property_data.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Get update data from request
        update_data = request.get_json()
        if not update_data:
            return jsonify({"error": "No update data provided"}), 400

        # Validate and sanitize update data
        allowed_fields = {'type', 'tags', 'content'}
        sanitized_data = {}

        for field, value in update_data.items():
            if field in allowed_fields:
                if field == 'tags':
                    # Ensure tags is a list
                    if isinstance(value, list):
                        sanitized_data[field] = [str(tag).strip() for tag in value if str(tag).strip()]
                    elif isinstance(value, str):
                        sanitized_data[field] = [tag.strip() for tag in value.split(',') if tag.strip()]
                    else:
                        sanitized_data[field] = []
                else:
                    sanitized_data[field] = str(value).strip() if value is not None else ''

        if not sanitized_data:
            return jsonify({"error": "No valid fields to update"}), 400

        # Update the knowledge item
        success = update_knowledge_item(item_id, sanitized_data)

        if success:
            print(f"User {user_id} updated knowledge item {item_id} with fields: {list(sanitized_data.keys())}")
            return jsonify({
                "success": True,
                "message": "Knowledge item updated successfully",
                "updated_fields": list(sanitized_data.keys())
            })
        else:
            return jsonify({"error": "Failed to update knowledge item"}), 500

    except Exception as e:
        print(f"Error updating knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error updating knowledge item: {e}"}), 500

@api_bp.route('/knowledge-items/<item_id>/disapprove', methods=['POST'])
@login_required
def disapprove_knowledge_item_api(item_id):
    """Disapprove a knowledge item (change status to pending)."""
    user_id = g.user_id

    try:
        # Get the knowledge item to verify ownership
        knowledge_item = get_knowledge_item(item_id)
        if not knowledge_item:
            return jsonify({"error": "Knowledge item not found"}), 404

        # Get the property to verify user ownership
        property_id = knowledge_item.get('propertyId')
        if not property_id:
            return jsonify({"error": "Knowledge item has no associated property"}), 400

        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Associated property not found"}), 404

        # Check if the user owns this property
        if property_data.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to disapprove knowledge item for property {property_id} owned by {property_data.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Update the knowledge item status to pending
        success = update_knowledge_item(item_id, {'status': 'pending'})

        if success:
            print(f"User {user_id} disapproved knowledge item {item_id}")
            return jsonify({
                "success": True,
                "message": "Knowledge item disapproved successfully"
            })
        else:
            return jsonify({"error": "Failed to disapprove knowledge item"}), 500

    except Exception as e:
        print(f"Error disapproving knowledge item {item_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error disapproving knowledge item: {e}"}), 500

@api_bp.route('/properties/<property_id>', methods=['GET'])
@login_required
def get_property_api(property_id):
    """Get property details."""
    user_id = g.user_id

    try:
        # Get the property to verify ownership
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Property not found"}), 404

        # Verify ownership
        if property_data.get('hostId') != user_id:
            return jsonify({"error": "Access denied"}), 403

        return jsonify({
            "success": True,
            "property": property_data
        })

    except Exception as e:
        current_app.logger.error(f"Error fetching property {property_id}: {e}")
        return jsonify({"error": "Failed to fetch property"}), 500

@api_bp.route('/properties/<property_id>', methods=['PUT'])
@login_required
def update_property_api(property_id):
    """Update property details."""
    user_id = g.user_id

    try:
        # Get the property to verify ownership
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Property not found"}), 404

        # Check if the user owns this property
        if property_data.get('hostId') != user_id:
            print(f"Security Alert: User {user_id} attempted to update property {property_id} owned by {property_data.get('hostId')}")
            return jsonify({"error": "Permission denied"}), 403

        # Get update data from request
        update_data = request.get_json()
        if not update_data:
            return jsonify({"error": "No update data provided"}), 400

        # Validate and sanitize update data
        allowed_fields = {
            'name', 'address', 'description', 'status',
            'checkInTime', 'checkOutTime', 'wifiDetails', 'icalUrl'
        }

        sanitized_data = {}
        for field, value in update_data.items():
            if field in allowed_fields:
                if field == 'wifiDetails' and isinstance(value, dict):
                    # Handle nested wifiDetails object
                    sanitized_data[field] = {
                        'network': str(value.get('network', '')).strip(),
                        'password': str(value.get('password', '')).strip()
                    }
                else:
                    # Handle simple string fields
                    sanitized_data[field] = str(value).strip() if value is not None else ''

        if not sanitized_data:
            return jsonify({"error": "No valid fields to update"}), 400

        # Update the property
        success = update_property(property_id, sanitized_data)

        if success:
            print(f"User {user_id} updated property {property_id} with fields: {list(sanitized_data.keys())}")
            return jsonify({
                "success": True,
                "message": "Property updated successfully",
                "updated_fields": list(sanitized_data.keys())
            })
        else:
            return jsonify({"error": "Failed to update property"}), 500

    except Exception as e:
        print(f"Error updating property {property_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error updating property: {e}"}), 500



@api_bp.route('/users/by-phone/<phone_number>', methods=['GET'])
@login_required
def get_user_by_phone(phone_number):
    """Gets user data by phone number."""
    current_user_id = g.user_id

    try:
        # Import functions from firestore_client
        from concierge.utils.firestore_client import find_user_by_phone

        # Find user by phone number
        user_data = find_user_by_phone(phone_number)

        if user_data:
            # For security, only return limited user data
            safe_user_data = {
                'displayName': user_data.get('displayName') or user_data.get('name') or 'Guest',
                'phoneNumber': phone_number,
                'id': user_data.get('id') or user_data.get('uid')
            }
            return jsonify({"success": True, "user": safe_user_data})
        else:
            # Try to find a reservation with this phone number to get the guest name
            from concierge.utils.firestore_client import find_reservation_by_phone

            reservation = find_reservation_by_phone(phone_number)
            if reservation:
                guest_name = reservation.get('guestName') or 'Guest'
                return jsonify({
                    "success": True,
                    "user": {
                        'displayName': guest_name,
                        'phoneNumber': phone_number,
                        'id': None
                    }
                })

            return jsonify({"success": False, "error": "User not found"}), 404
    except Exception as e:
        print(f"Error finding user by phone {phone_number}: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/reservations', methods=['GET'])
@login_required
def get_reservations_by_phone():
    """Gets all reservations for a phone number (query parameter)."""
    current_user_id = g.user_id

    # Get phone number from query parameter
    phone_number = request.args.get('phone')
    if not phone_number:
        return jsonify({"error": "Phone number is required"}), 400

    # Import functions from firestore_client
    from concierge.utils.firestore_client import list_reservations_by_phone, get_firestore_db

    try:
        # Check if Firestore is properly initialized
        db = get_firestore_db()
        if not db:
            print(f"Error: Firestore database not initialized properly")
            return jsonify({
                "success": False,
                "error": "Database connection error. Please refresh the page and try again.",
                "firebase_error": True
            }), 500

        print(f"Fetching reservations for phone number: {phone_number}")

        # Get all reservations for this phone number
        reservations_list = list_reservations_by_phone(phone_number)
        print(f"Found {len(reservations_list)} reservations for phone: {phone_number}")

        # Return the reservations
        return jsonify({
            "success": True,
            "reservations": reservations_list,
            "count": len(reservations_list)
        })

    except Exception as e:
        print(f"Error fetching reservations for phone {phone_number}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Server error: {e}"
        }), 500

@api_bp.route('/feedback/submit', methods=['POST'])
def submit_feedback():
    """Submit guest feedback for a session."""
    from flask import request, jsonify
    from datetime import datetime, timezone
    import traceback
    
    try:
        # Get feedback data from request
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        # Validate required fields (allow partial ratings: at least one of enjoyment/accuracy)
        base_required = ['userId', 'propertyId']
        for field in base_required:
            if field not in data:
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400
        if 'enjoyment' not in data and 'accuracy' not in data:
            return jsonify({"success": False, "error": "At least one of 'enjoyment' or 'accuracy' must be provided"}), 400
        
        # Validate rating values
        enjoyment = data.get('enjoyment')
        accuracy = data.get('accuracy')
        
        if enjoyment is not None:
            if not isinstance(enjoyment, int) or enjoyment < 0 or enjoyment > 3:
                return jsonify({"success": False, "error": "Enjoyment rating must be 0-3"}), 400
        if accuracy is not None:
            if not isinstance(accuracy, int) or accuracy < 1 or accuracy > 5:
                return jsonify({"success": False, "error": "Accuracy rating must be 1-5"}), 400
        
        # Prepare feedback record (flat keys expected by store_feedback)
        feedback_record = {
            'feedbackId': f"feedback_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{data['userId'][:8]}",
            'userId': data['userId'],
            'propertyId': data['propertyId'],
            'sessionId': data.get('sessionId'),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'feedbackType': 'guest_session_feedback'
        }
        if enjoyment is not None:
            feedback_record['enjoyment'] = enjoyment
        if accuracy is not None:
            feedback_record['accuracy'] = accuracy
        
        # Store feedback in DynamoDB
        from concierge.utils.dynamodb_client import attach_feedback_to_voice_session, attach_feedback_to_latest_conversation, attach_feedback_to_conversation

        # First, try to attach feedback directly to voice diagnostics session if sessionId present
        attached = False
        if feedback_record.get('sessionId') and data.get('propertyId'):
            try:
                attached = attach_feedback_to_voice_session(data['propertyId'], feedback_record['sessionId'], feedback_record)
            except Exception:
                attached = False

        # If not attached to voice session, try attaching to the specific conversation if provided
        if not attached and data.get('conversationId') and data.get('propertyId'):
            try:
                attached = attach_feedback_to_conversation(data['propertyId'], data['conversationId'], feedback_record)
            except Exception:
                attached = False

        # If not attached to specific conversation, try attaching to latest conversation for this user
        if not attached:
            try:
                attached = attach_feedback_to_latest_conversation(data.get('userId'), data.get('propertyId'), feedback_record)
            except Exception:
                attached = False

        # Store feedback only within session/conversation records (no standalone items)
        success = attached or False
        
        if success:
            return jsonify({
                "success": True,
                "feedbackId": feedback_record['feedbackId']
            })
        else:
            return jsonify({"success": False, "error": "Failed to store feedback"}), 500
            
    except Exception as e:
        print(f"Error submitting feedback: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": "Server error processing feedback"}), 500

@api_bp.route('/reservations/<user_id>', methods=['GET'])
def get_user_reservations(user_id):
    """Gets all reservations for a user by their phone number (supports magic link sessions)."""
    from flask import session, request
    from datetime import datetime, timezone
    
    # Define current time for expiration checks
    now = datetime.now(timezone.utc)
    
    # Check authentication - support both regular login and magic link sessions
    # Priority: Use the session that matches the requested user_id to prevent conflicts
    regular_user_id = session.get('user_id')
    magic_link_session = request.cookies.get('magicLinkSession')
    authenticated_user_id = None

    # Validate magic link session first to get the magic link user_id
    magic_link_user_id = None
    if magic_link_session:
        try:
            from concierge.utils.session_manager import validate_session
            is_valid, temp_user_id, reason = validate_session(magic_link_session)
            if is_valid and temp_user_id:
                magic_link_user_id = temp_user_id
        except Exception as e:
            current_app.logger.error(f"Error validating magic link session: {e}")

    # Choose authentication method based on which user matches the requested user_id
    if user_id == regular_user_id and regular_user_id:
        # Requested user matches regular session
        authenticated_user_id = regular_user_id
        current_app.logger.info(f"Regular user {regular_user_id} accessing own reservations")
    elif user_id == magic_link_user_id and magic_link_user_id:
        # Requested user matches magic link session
        authenticated_user_id = magic_link_user_id
        current_app.logger.info(f"Magic link user {magic_link_user_id} accessing reservations")
    elif regular_user_id and not magic_link_user_id:
        # Only regular session exists
        authenticated_user_id = regular_user_id
    elif magic_link_user_id and not regular_user_id:
        # Only magic link session exists
        authenticated_user_id = magic_link_user_id
    else:
        return jsonify({"error": "Authentication required"}), 401

    # Allow users to view only their own reservations (security check)
    if user_id != authenticated_user_id:
        print(f"Security Alert: User {authenticated_user_id} attempted to access reservations for user {user_id}")
        return jsonify({"error": "Permission denied"}), 403

    # Import functions from firestore_client
    from concierge.utils.firestore_client import get_user, list_reservations_by_phone, get_firestore_db

    try:
        # Check if Firestore is properly initialized
        db = get_firestore_db()
        if not db:
            print(f"Error: Firestore database not initialized properly")
            return jsonify({
                "success": False,
                "error": "Database connection error. Please refresh the page and try again.",
                "firebase_error": True
            }), 500

        # Get user info from Firestore
        user_data = get_user(user_id)
        if not user_data:
            print(f"User {user_id} not found in Firestore")

            # Attempt to get the user from Firebase Auth as fallback
            try:
                print(f"Attempting to get user from Firebase Auth: {user_id}")
                from firebase_admin import auth
                auth_user = auth.get_user(user_id)
                if auth_user:
                    print(f"Found user in Firebase Auth: {auth_user.uid}, Phone: {auth_user.phone_number}")
                    user_data = {
                        'uid': auth_user.uid,
                        'phoneNumber': auth_user.phone_number,
                        'displayName': auth_user.display_name
                    }
            except Exception as auth_error:
                print(f"Error getting user from Firebase Auth: {auth_error}")
                # Continue with the flow even if this fails

        # If we still don't have user data
        if not user_data:
            print(f"No user data found in Firestore or Auth for {user_id}")
            # Check if we have a phone number in the request or session to use as fallback
            fallback_phone = request.args.get('phone') or session.get('phone_number')
            if fallback_phone:
                print(f"Using fallback phone number from request/session: {fallback_phone}")
                user_data = {'phoneNumber': fallback_phone}
            else:
                # Create minimal user data to continue
                user_data = {'uid': user_id}

        # Get phone number from user data - handle both camelCase and snake_case
        user_phone_number = user_data.get('phoneNumber') or user_data.get('phone_number')
        print(f"Fetching reservations for phone number: {user_phone_number}")

        # Get all reservations for this user by phone number
        reservations_list = []
        if user_phone_number:
            # Get reservations by exact phone number match
            reservations_list = list_reservations_by_phone(user_phone_number)
            # Add source tracking for phone-matched reservations
            for res in reservations_list:
                res['_source'] = 'phone_exact_match'
            print(f"Found {len(reservations_list)} reservations for exact phone match: {user_phone_number}")

            # If no reservations found, try matching by last 4 digits
            if not reservations_list and len(user_phone_number) >= 4:
                # Get the last 4 digits of the phone number
                last_four_digits = user_phone_number[-4:]
                print(f"No reservations found for exact match, trying last 4 digits: {last_four_digits}")

                # Get all reservations from Firestore
                from concierge.utils.firestore_client import get_firestore_db
                db = get_firestore_db()
                if db:
                    # Query all reservations
                    all_reservations_query = db.collection('reservations').stream()
                    all_reservations = [doc.to_dict() for doc in all_reservations_query]
                    print(f"Retrieved {len(all_reservations)} total reservations from Firestore")

                    # Examine a sample reservation to debug
                    if all_reservations and len(all_reservations) > 0:
                        sample = all_reservations[0]
                        print(f"Sample reservation structure: {sample.keys()}")

                        # Check for phone fields in the sample
                        for field in ['guestPhoneNumber', 'GuestPhoneNumber', 'guest_phone_number', 'guestPhone']:
                            if field in sample:
                                print(f"Found phone field in sample: {field} = {sample[field]}")

                        # Check for additional contacts
                        for field in ['additionalContacts', 'AdditionalContacts', 'additional_contacts']:
                            if field in sample and sample[field]:
                                print(f"Found additional contacts in sample: {field} = {sample[field]}")

                    # Filter reservations by last 4 digits of phone number
                    for res in all_reservations:
                        # Add document ID to the reservation data
                        res_id = res.get('id')
                        if not res_id:
                            # If the reservation doesn't have an ID field, try to get it from the document reference
                            for doc in all_reservations_query:
                                if doc.to_dict() == res:
                                    res['id'] = doc.id
                                    break

                        # Check primary guest phone number
                        guest_phone = res.get('guestPhoneNumber')
                        if guest_phone and guest_phone.endswith(last_four_digits):
                            res['_source'] = 'phone_last4_primary'
                            reservations_list.append(res)
                            print(f"Found reservation with last 4 digits match in primary phone: {guest_phone}")
                            continue

                        # Check guestPhoneLast4 field specifically
                        guest_phone_last4 = res.get('guestPhoneLast4')
                        if guest_phone_last4 == last_four_digits:
                            res['_source'] = 'phone_last4_field'
                            reservations_list.append(res)
                            print(f"Found reservation with matching guestPhoneLast4: {guest_phone_last4}")
                            continue

                        # Check additional contacts
                        additional_contacts = res.get('additional_contacts', [])
                        for contact in additional_contacts:
                            contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('phone_number')
                            if contact_phone and contact_phone.endswith(last_four_digits):
                                res['_source'] = 'phone_last4_additional_contact'
                                reservations_list.append(res)
                                print(f"Found reservation with last 4 digits match in additional contact: {contact_phone}")
                                break

                    print(f"Found {len(reservations_list)} reservations for last 4 digits match: {last_four_digits}")

        # Check user's reservationIds field for direct reservation references
        invalid_reservation_ids = []
        reservations_from_user_profile = []
        if user_data and 'reservationIds' in user_data and user_data['reservationIds']:
            print(f"Checking user's reservationIds: {user_data['reservationIds']}")
            for reservation_id in user_data['reservationIds']:
                try:
                    # Get reservation by ID
                    reservation_doc = db.collection('reservations').document(reservation_id).get()
                    if reservation_doc.exists:
                        reservation_data = reservation_doc.to_dict()
                        reservation_data['id'] = reservation_doc.id
                        reservation_data['_source'] = 'user_profile_reservationIds'  # Track source
                        
                        # Check if reservation is expired (past checkout date + 30 days grace period)
                        end_date = reservation_data.get('endDate')
                        if end_date:
                            try:
                                from datetime import datetime, timedelta
                                if isinstance(end_date, str):
                                    checkout_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                                else:
                                    checkout_date = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date
                                
                                # 3 day grace period after checkout
                                expiry_date = checkout_date + timedelta(days=3)
                                if now > expiry_date:
                                    print(f"Reservation {reservation_id} expired on {expiry_date}, removing from user profile")
                                    invalid_reservation_ids.append(reservation_id)
                                    continue
                            except Exception as date_error:
                                print(f"Error parsing reservation date for {reservation_id}: {date_error}")
                        
                        # Check if not already in list
                        if not any(r.get('id') == reservation_id for r in reservations_list):
                            reservations_list.append(reservation_data)
                            reservations_from_user_profile.append(reservation_id)
                            print(f"Added reservation from reservationIds: {reservation_id}")
                    else:
                        print(f"WARNING: Invalid reservation ID in user profile: {reservation_id}")
                        invalid_reservation_ids.append(reservation_id)
                except Exception as e:
                    print(f"Error fetching reservation {reservation_id}: {e}")
                    invalid_reservation_ids.append(reservation_id)
            
            # Clean up invalid reservation IDs from user profile
            if invalid_reservation_ids:
                try:
                    valid_reservation_ids = [rid for rid in user_data['reservationIds'] if rid not in invalid_reservation_ids]
                    from concierge.utils.firestore_client import update_user
                    update_user(user_id, {'reservationIds': valid_reservation_ids})
                    print(f"Cleaned up {len(invalid_reservation_ids)} invalid/expired reservation IDs from user {user_id}")
                except Exception as cleanup_error:
                    print(f"Error cleaning up invalid reservation IDs: {cleanup_error}")

        # If we still don't have reservations, try a direct Firestore query by user ID
        if not reservations_list:
            print(f"No reservations found by phone, trying direct query by user ID: {user_id}")
            try:
                user_reservations_query = db.collection('reservations').where('userId', '==', user_id)
                user_reservations = [doc.to_dict() for doc in user_reservations_query.stream()]

                # Add doc ID if missing
                for res in user_reservations:
                    if 'id' not in res:
                        for doc in user_reservations_query.stream():
                            if doc.to_dict() == res:
                                res['id'] = doc.id
                                break

                # Add to our list
                reservations_list.extend(user_reservations)
                print(f"Found {len(user_reservations)} reservations by direct user ID query")

                # Try another query format
                guest_id_query = db.collection('reservations').where('guestId', '==', user_id)
                guest_id_reservations = [doc.to_dict() for doc in guest_id_query.stream()]

                # Add doc ID if missing
                for res in guest_id_reservations:
                    if 'id' not in res and not any(r.get('id') == res.get('id') for r in reservations_list):
                        for doc in guest_id_query.stream():
                            if doc.to_dict() == res:
                                res['id'] = doc.id
                                break

                # Add to our list
                for res in guest_id_reservations:
                    if not any(r.get('id') == res.get('id') for r in reservations_list):
                        reservations_list.append(res)

                print(f"Found {len(guest_id_reservations)} additional reservations by guest ID query")
            except Exception as query_error:
                print(f"Error during direct user ID query: {query_error}")

        # No test reservations should be created in production
        # Users with no reservations should see the proper empty state

        # Sort reservations by date - active first, then upcoming, then past

        def get_reservation_order(res):
            # Support both field naming conventions (camelCase and snake_case)
            start = res.get('startDate') or res.get('checkInDate') or res.get('check_in_date')
            end = res.get('endDate') or res.get('checkOutDate') or res.get('check_out_date')

            # Convert ISO strings to datetime for comparison if needed
            if isinstance(start, str):
                try:
                    start = datetime.fromisoformat(start.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    start = now  # Fallback
            elif start and hasattr(start, 'replace') and start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)

            if isinstance(end, str):
                try:
                    end = datetime.fromisoformat(end.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    end = now  # Fallback
            elif end and hasattr(end, 'replace') and end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)

            # Check for None values before comparison
            if start is None or end is None:
                return 3  # Missing dates - lowest priority

            # Determine status for sorting
            if start <= now <= end:
                return 0  # Active - highest priority
            elif start > now:
                return 1  # Upcoming - second priority
            else:
                return 2  # Past - lowest priority

        # Sort reservations using a try-except block to handle potential errors
        try:
            sorted_reservations = sorted(reservations_list, key=get_reservation_order)
        except Exception as sort_error:
            print(f"Error sorting reservations: {sort_error}")
            # Return unsorted reservations if sorting fails
            sorted_reservations = reservations_list

        # Standardize field names for frontend
        for res in sorted_reservations:
            # Ensure all reservations have these fields with consistent naming
            # If the ID is not in the data, use the document ID
            if 'id' not in res:
                print(f"Warning: Reservation missing 'id' field: {res}")

            # Extract property ID if needed
            property_id = res.get('propertyId')
            if not property_id and res.get('PK', '').startswith('PROPERTY#'):
                property_id = res.get('PK', '').replace('PROPERTY#', '')
                res['propertyId'] = property_id

            # Import date utilities for consistent date formatting
            from concierge.utils.date_utils import ensure_date_only_format

            # Standardize field names and ensure dates are in date-only format
            res['id'] = res.get('id', '')
            res['propertyId'] = property_id or res.get('propertyId', '')

            # Normalize dates to ensure consistent formatting across all clients
            start_date_raw = res.get('startDate') or res.get('StartDate') or res.get('checkInDate') or res.get('CheckInDate')
            end_date_raw = res.get('endDate') or res.get('EndDate') or res.get('checkOutDate') or res.get('CheckOutDate')

            res['startDate'] = ensure_date_only_format(start_date_raw) or ''
            res['endDate'] = ensure_date_only_format(end_date_raw) or ''

            res['guestName'] = res.get('guestName') or res.get('GuestName') or ''
            res['guestPhoneNumber'] = res.get('guestPhoneNumber') or res.get('GuestPhoneNumber') or res.get('guest_phone') or ''
            res['additionalContacts'] = res.get('additional_contacts') or res.get('additionalContacts') or res.get('AdditionalContacts') or []

            # Make sure propertyName and propertyAddress are set
            if not res.get('propertyName') and property_id:
                # Use the property ID as a fallback name
                res['propertyName'] = f"Beach House {property_id[-4:]}"

            # Add address if missing
            if not res.get('propertyAddress') and property_id:
                # Use a fallback address
                res['propertyAddress'] = "123 Beach Avenue"

            # These are now standardized field names in the response
            # Even if the database has different casing or field names
            # The frontend will look for these specific fields

        print(f"Returning {len(sorted_reservations)} standardized reservations")
        
        # Debug: Show source breakdown
        print("\n=== RESERVATION SOURCE BREAKDOWN ===")
        for i, res in enumerate(sorted_reservations):
            source = res.get('_source', 'unknown')
            res_id = res.get('id', 'no-id')
            property_id = res.get('propertyId', 'no-property')
            print(f"  {i+1}. {res_id} (property: {property_id[-8:]}) - Source: {source}")
        if reservations_from_user_profile:
            print(f"User's reservationIds field contained: {reservations_from_user_profile}")
        print("=====================================\n")
        
        # Remove _source field before returning (internal use only)
        for res in sorted_reservations:
            res.pop('_source', None)
        
        return jsonify({
            "success": True,
            "reservations": sorted_reservations
        })

    except Exception as e:
        print(f"Error fetching reservations for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/properties/<property_id>/knowledge/reingest-all', methods=['POST'])
@login_required
def reingest_all_knowledge(property_id):
    """
    Legacy endpoint for re-ingestion - no longer needed with Firestore migration.
    Knowledge items are now processed directly in Firestore with vector embeddings.
    """
    print(f"Legacy re-ingestion request for property {property_id} - no longer needed with Firestore")

    # Get user ID from session
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    return jsonify({
        'success': True,
        'message': 'Re-ingestion no longer needed - knowledge items are processed directly in Firestore with vector embeddings',
        'migration_note': 'This endpoint is deprecated. Knowledge items are automatically processed when created/updated in Firestore.'
    })

@api_bp.route('/knowledge-items', methods=['GET'])
def get_knowledge_items():
    """
    Get knowledge items for a property.

    Query parameters:
    - propertyId: ID of the property to get knowledge items for
    - status: (optional) Filter by status (e.g., 'approved')
    """
    property_id = request.args.get('propertyId')
    status = request.args.get('status')

    if not property_id:
        return jsonify({"error": "Property ID is required"}), 400

    try:
        # Get knowledge items from Firestore
        if status:
            items = list_knowledge_items_by_property(property_id, status)
        else:
            items = list_knowledge_items_by_property(property_id)

        # Filter out items without embeddings if needed for RAG
        items_with_embeddings = [item for item in items if item.get('embedding')]

        # Log the results
        print(f"Found {len(items)} knowledge items for property {property_id}")
        print(f"{len(items_with_embeddings)} items have embeddings")

        # Return the items
        return jsonify({
            "success": True,
            "items": items,
            "total": len(items),
            "with_embeddings": len(items_with_embeddings)
        })

    except Exception as e:
        print(f"Error getting knowledge items: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Failed to get knowledge items: {str(e)}"}), 500


@api_bp.route('/properties/<property_id>/knowledge/pending-count', methods=['GET'])
@login_required
def get_pending_knowledge_items_count(property_id):
    """
    Get the count of pending knowledge items for a property.
    Used to validate property activation and setup completion.
    """
    user_id = g.user_id
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    try:
        # Get the property to verify ownership
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({'error': 'Property not found'}), 404

        if property_data.get('hostId') != user_id:
            return jsonify({'error': 'You do not have permission to access this property'}), 403

        # Get pending knowledge items for this property
        pending_items = list_knowledge_items_by_property(property_id, 'pending')
        pending_count = len(pending_items)

        return jsonify({
            'success': True,
            'pending_count': pending_count,
            'has_pending_items': pending_count > 0
        })

    except Exception as e:
        print(f"Error getting pending knowledge items count for property {property_id}: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Failed to get pending items count: {str(e)}'}), 500

@api_bp.route('/chat/query', methods=['POST'])
def process_chat_query():
    """
    Process a chat query using RAG with Firestore.

    Request body:
    - query: The user's query
    - propertyId: ID of the property to search in
    - conversationHistory: (optional) Previous messages in the conversation
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    query = data.get('query')
    property_id = data.get('propertyId')
    conversation_history = data.get('conversationHistory', [])

    if not query:
        return jsonify({"error": "Query is required"}), 400

    if not property_id:
        return jsonify({"error": "Property ID is required"}), 400

    try:
        # Get property context
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Property not found"}), 404

        # Process the query with RAG
        result = process_query_with_rag(
            user_query=query,
            property_id=property_id,
            property_context=property_data,
            conversation_history=conversation_history
        )

        # Return the response
        return jsonify({
            "success": True,
            "response": result.get('response', ''),
            "has_context": result.get('has_context', False),
            "context_used": result.get('context_used', [])
        })

    except Exception as e:
        print(f"Error processing chat query: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Failed to process query: {str(e)}"}), 500

@login_required
def get_knowledge_item_status(item_id):
    """
    Get the current status of a knowledge item.
    Used to check if ingestion has completed successfully.
    """
    # Get user ID from session
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Authentication required'}), 401

    # Import the DynamoDB functions we need
    from concierge.utils.dynamodb_client import get_knowledge_item, get_property

    try:
        # Get the knowledge item
        item_data = get_knowledge_item(item_id)

        if not item_data:
            return jsonify({'error': 'Knowledge item not found'}), 404

        property_id = item_data.get('PropertyId')

        if not property_id:
            # Check if property_id is in the PK field
            pk = item_data.get('PK', '')
            if pk and pk.startswith('PROPERTY#'):
                property_id = pk.replace('PROPERTY#', '')
            else:
                return jsonify({'error': 'Invalid knowledge item (missing property ID)'}), 400

        # Check if user has access to this property
        property_data = get_property(property_id)

        if not property_data:
            return jsonify({'error': 'Property not found'}), 404

        if property_data.get('hostId') != user_id:
            return jsonify({'error': 'You do not have permission to access this knowledge item'}), 403

        # Return the current status and other relevant info
        status = item_data.get('Status', 'unknown')
        error_message = item_data.get('ErrorMessage', None)

        return jsonify({
            'success': True,
            'status': status,
            'error': error_message,
            'last_updated': item_data.get('UpdatedAt', None),
            'migration_note': 'LanceDB status no longer tracked - using Firestore with vector embeddings'
        })

    except Exception as e:
        print(f"Error getting knowledge item status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to get knowledge item status: {str(e)}'}), 500

@api_bp.route('/property/<property_id>')
def get_property_by_id(property_id):
    """Gets property details by ID (accessible to both hosts and guests)."""
    try:
        # Special handling for test property IDs
        if property_id == 'test-property-123':
            print(f"Returning mock data for test property ID: {property_id}")

            # Mock property data for testing
            mock_property = {
                "success": True,
                "property": {
                    "id": property_id,
                    "propertyId": property_id,
                    "name": "Beach House -123 (Test Property)",
                    "address": "123 Beach Avenue",
                    "description": "This is a test property for development purposes.",
                    "wifiNetwork": "TestWiFi",
                    "wifiPassword": "password123",
                    "checkInTime": "3:00 PM",
                    "checkOutTime": "11:00 AM",
                    "hostName": "Test Host",
                    "rules": "No pets. No smoking. Quiet hours from 10pm to 8am.",
                    "hostId": "test-host-123"
                }
            }

            return jsonify(mock_property)

        # Get property details from Firestore
        property_data = get_property(property_id)
        print(f"Property data from Firestore for {property_id}: {property_data}")

        if not property_data:
            return jsonify({"success": False, "error": "Property not found"}), 404

        # Extract WiFi details if available
        wifi_network = ""
        wifi_password = ""

        # Check for wifiDetails field
        if 'wifiDetails' in property_data:
            wifi = property_data.get('wifiDetails', {})
            if isinstance(wifi, dict):
                wifi_network = wifi.get('network', '')
                wifi_password = wifi.get('password', '')

        # Check for direct WiFi fields (support both camelCase and PascalCase)
        if 'wifiNetwork' in property_data:
            wifi_network = property_data.get('wifiNetwork', '')
        elif 'WifiNetwork' in property_data:
            wifi_network = property_data.get('WifiNetwork', '')

        if 'wifiPassword' in property_data:
            wifi_password = property_data.get('wifiPassword', '')
        elif 'WifiPassword' in property_data:
            wifi_password = property_data.get('WifiPassword', '')

        # Get host name from host ID if available (support both camelCase and PascalCase)
        host_name = property_data.get('hostName', property_data.get('HostName', 'Your Host'))
        host_id = property_data.get('hostId', property_data.get('HostId', ''))

        if host_id:
            try:
                # Get the host's user profile
                host_data = get_user(host_id)
                if host_data:
                    # Try different possible field names for the host's name
                    host_name = host_data.get('name',
                                host_data.get('displayName',
                                host_data.get('fullName', 'Your Host')))
                    print(f"Retrieved host name from user profile: {host_name}")
            except Exception as user_err:
                print(f"Error retrieving host name for host ID {host_id}: {user_err}")
                # Fall back to generic name or existing hostName
                host_name = property_data.get('hostName', property_data.get('HostName', 'Your Host'))

        # Return property details with ALL fields needed for host dashboard
        response_data = {
            "success": True,
            "property": {
                "id": property_id,
                "propertyId": property_id,  # Add this for consistency
                "name": property_data.get('name', property_data.get('Name', 'Unknown Property')),
                "address": property_data.get('address', property_data.get('Address', 'No address available')),
                "description": property_data.get('description', property_data.get('Description', '')),
                "status": property_data.get('status', property_data.get('Status', 'active')),
                "icalUrl": property_data.get('icalUrl', property_data.get('ICalUrl', '')),
                "wifiDetails": property_data.get('wifiDetails', property_data.get('WifiDetails', {})),
                "wifiNetwork": wifi_network,  # Keep for backward compatibility
                "wifiPassword": wifi_password,  # Keep for backward compatibility
                "checkInTime": property_data.get('checkInTime', property_data.get('CheckInTime', '15:00')),
                "checkOutTime": property_data.get('checkOutTime', property_data.get('CheckOutTime', '11:00')),
                "hostName": host_name,
                "rules": property_data.get('rules', property_data.get('Rules', '')),
                "hostId": host_id,  # Include the host ID for reference
                "amenities": property_data.get('amenities', {'basic': [], 'appliances': []}),  # Include amenities data
                "houseRules": property_data.get('houseRules', []),  # Include structured house rules
                "emergencyInfo": property_data.get('emergencyInfo', []),  # Include emergency information
                "propertyFacts": property_data.get('propertyFacts', []),  # Include property facts (other information)
                "createdAt": property_data.get('createdAt', property_data.get('CreatedAt')),
                "updatedAt": property_data.get('updatedAt', property_data.get('UpdatedAt'))
            }
        }

        print(f"Returning property details for {property_id}: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        print(f"Error fetching property {property_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Server error: {str(e)}"}), 500

@api_bp.route('/user/role', methods=['PUT'])
@login_required
def update_user_role():
    """Updates the roles of the currently logged-in user."""
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request data is required"}), 400

    # Support both old single role format and new multiple roles format
    if 'role' in data:
        # Legacy single role update
        new_role = data['role']
        if new_role not in ['guest', 'host', 'property_manager']:
            return jsonify({"error": "Invalid role. Must be 'guest', 'host', or 'property_manager'"}), 400
        
        # Convert single role to array format
        from concierge.utils.firestore_client import get_user
        from concierge.utils.role_helpers import add_role, normalize_user_roles
        from concierge.auth.utils import update_session_roles
        
        try:
            user_data = get_user(user_id)
            if not user_data:
                return jsonify({"error": "User not found"}), 404
            
            # Add the new role (this handles conversion to array)
            updated_user_data = add_role(user_data, new_role)
            
            # Update in Firestore
            success = update_user(user_id, {'role': updated_user_data['role']})
            
            if success:
                # Update session with new roles
                update_session_roles(updated_user_data)
                roles = normalize_user_roles(updated_user_data)
                primary_role = session.get('user_role')
                
                return jsonify({
                    "success": True, 
                    "message": f"Role '{new_role}' added successfully", 
                    "role": primary_role,
                    "roles": roles
                })
            else:
                return jsonify({"error": "Failed to update role"}), 500
                
        except Exception as e:
            print(f"Error updating role for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Server error updating role: {e}"}), 500
    
    elif 'roles' in data:
        # New multiple roles format
        new_roles = data['roles']
        if not isinstance(new_roles, list):
            return jsonify({"error": "Roles must be an array"}), 400
        
        # Validate all roles
        valid_roles = ['guest', 'host', 'property_manager']
        for role in new_roles:
            if role not in valid_roles:
                return jsonify({"error": f"Invalid role '{role}'. Must be one of: {valid_roles}"}), 400
        
        if not new_roles:
            return jsonify({"error": "At least one role is required"}), 400
        
        try:
            from concierge.auth.utils import update_session_roles
            
            # Update user's roles in Firestore
            success = update_user(user_id, {'role': new_roles})
            
            if success:
                # Update session with new roles
                from concierge.utils.firestore_client import get_user
                user_data = get_user(user_id)
                if user_data:
                    update_session_roles(user_data)
                    primary_role = session.get('user_role')
                    
                    return jsonify({
                        "success": True, 
                        "message": "Roles updated successfully", 
                        "role": primary_role,
                        "roles": new_roles
                    })
                else:
                    return jsonify({"error": "Failed to retrieve updated user data"}), 500
            else:
                return jsonify({"error": "Failed to update roles"}), 500
                
        except Exception as e:
            print(f"Error updating roles for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Server error updating roles: {e}"}), 500
    
    else:
        return jsonify({"error": "Either 'role' or 'roles' is required"}), 400

@api_bp.route('/user/profile', methods=['GET'])
@login_required
def get_user_profile():
    """Gets the profile of the currently logged-in user."""
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401

    try:
        # Get user data from Firestore
        user_data = get_user(user_id)

        if user_data:
            # Get roles using the new role helper functions
            from concierge.utils.role_helpers import normalize_user_roles, get_primary_role
            
            roles = normalize_user_roles(user_data)
            primary_role = get_primary_role(user_data)
            
            # Return only safe profile data
            profile_data = {
                'displayName': user_data.get('displayName') or user_data.get('DisplayName') or '',
                'email': user_data.get('email') or user_data.get('Email') or '',
                'phoneNumber': user_data.get('phoneNumber') or user_data.get('PhoneNumber') or '',
                'role': primary_role,  # Primary role for backward compatibility
                'roles': roles,       # Array of all roles
                'airbnbUserLink': user_data.get('airbnbUserLink', ''),
                'timezone': user_data.get('timezone', ''),
                'defaultCheckInTime': user_data.get('defaultCheckInTime', '15:00'),
                'defaultCheckOutTime': user_data.get('defaultCheckOutTime', '11:00')
            }

            return jsonify({
                "success": True,
                "user": profile_data
            })
        else:
            return jsonify({"error": "User profile not found"}), 404

    except Exception as e:
        print(f"Error fetching profile for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error fetching profile: {e}"}), 500

@api_bp.route('/change-pin', methods=['POST'])
@login_required
def change_pin():
    """Change user's PIN without requiring current PIN."""
    user_id = g.user_id
    if not user_id:
        return jsonify({"error": "User not authenticated"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    new_pin = data.get('newPin')

    # Validation
    if not new_pin or len(str(new_pin)) != 4:
        return jsonify({"error": "New PIN must be exactly 4 digits"}), 400

    try:
        # Validate PIN contains only digits
        if not str(new_pin).isdigit():
            return jsonify({"error": "PIN must contain only numbers"}), 400

        # Update the user's PIN in Firestore
        from concierge.utils.firestore_client import update_user
        
        success = update_user(user_id, {"customPin": new_pin})

        if success:
            return jsonify({
                "success": True,
                "message": "PIN changed successfully"
            })
        else:
            return jsonify({"error": "Failed to update PIN"}), 500

    except Exception as e:
        print(f"Error changing PIN for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error changing PIN: {e}"}), 500

@api_bp.route('/conversation-history/<user_id>/<property_id>', methods=['GET'])
def get_conversation_history(user_id, property_id):
    """Get recent conversation history for a user and property within the last 24 hours."""
    try:
        from concierge.utils.dynamodb_client import list_user_conversations, get_conversation

        # Get recent conversations (last 24 hours)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
        conversations = list_user_conversations(user_id, limit=50)

        recent_messages = []

        for conversation in conversations:
            # Check if conversation is recent and for the correct property
            if (conversation.get('PropertyId') == property_id and
                conversation.get('LastUpdateTime')):

                # Parse the timestamp
                try:
                    last_update = datetime.fromisoformat(conversation['LastUpdateTime'].replace('Z', '+00:00'))
                    if last_update >= cutoff_time:
                        # Get full conversation details
                        full_conversation = get_conversation(conversation['ConversationId'], property_id)
                        if full_conversation and full_conversation.get('Messages'):
                            # Extract messages that are within the time window
                            for message in full_conversation['Messages']:
                                try:
                                    msg_time = datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00'))
                                    if msg_time >= cutoff_time:
                                        recent_messages.append({
                                            'role': message['role'],
                                            'text': message['text'],
                                            'timestamp': message['timestamp'],
                                            'conversation_id': conversation['ConversationId'],
                                            'channel': conversation.get('Channel', 'text_chat')
                                        })
                                except (ValueError, KeyError):
                                    continue
                except (ValueError, KeyError):
                    continue

        # Sort messages by timestamp
        recent_messages.sort(key=lambda x: x['timestamp'])

        return jsonify({
            'success': True,
            'messages': recent_messages,
            'count': len(recent_messages)
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving conversation history for user {user_id}, property {property_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve conversation history',
            'messages': []
        }), 500

# === Conversation Management Endpoints ===

@api_bp.route('/conversations/create', methods=['POST'])
def create_conversation_session():
    """Create a new conversation session for voice calls or text chat."""
    # Check if user is authenticated via regular login or magic link session
    user_id = session.get('user_id')
    magic_link_session = request.cookies.get('magicLinkSession')

    # Allow access for regular authenticated users or magic link users
    if not user_id and not magic_link_session:
        current_app.logger.error("Conversation create requested without authentication")
        return jsonify({"error": "Authentication required"}), 401

    # Validate magic link session if present
    temp_user_id = None
    if magic_link_session and not user_id:
        try:
            from concierge.utils.session_manager import validate_session
            is_valid, temp_user_id, reason = validate_session(magic_link_session)
            if not is_valid:
                current_app.logger.error(f"Invalid magic link session for conversation create: {reason}")
                return jsonify({"error": "Invalid session"}), 401
            current_app.logger.info(f"Magic link user {temp_user_id} creating conversation session")
        except Exception as e:
            current_app.logger.error(f"Error validating magic link session: {e}")
            return jsonify({"error": "Session validation failed"}), 401

    try:
        data = request.get_json()
        property_id = data.get('property_id')
        request_user_id = data.get('user_id') or user_id or temp_user_id
        guest_name = data.get('guest_name')
        phone_number = data.get('phone_number')
        channel = data.get('channel', 'text_chat')  # Default to text_chat
        reservation_id = data.get('reservation_id')

        if not property_id:
            return jsonify({"error": "Property ID is required"}), 400

        # Import DynamoDB conversation functions
        from concierge.utils.dynamodb_client import create_conversation_session

        conversation_id = create_conversation_session(
            property_id=property_id,
            user_id=request_user_id,
            guest_name=guest_name,
            reservation_id=reservation_id,
            phone_number=phone_number,
            channel=channel
        )

        if conversation_id:
            return jsonify({
                "success": True,
                "conversation_id": conversation_id
            })
        else:
            return jsonify({"error": "Failed to create conversation session"}), 500

    except Exception as e:
        print(f"Error creating conversation session: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500

@api_bp.route('/conversations/message', methods=['POST'])
def add_conversation_message():
    """Add a message to an existing conversation."""
    # Check if user is authenticated via regular login or magic link session
    user_id = session.get('user_id')
    magic_link_session = request.cookies.get('magicLinkSession')

    # Allow access for regular authenticated users or magic link users
    if not user_id and not magic_link_session:
        current_app.logger.error("Conversation message requested without authentication")
        return jsonify({"error": "Authentication required"}), 401

    # Validate magic link session if present
    if magic_link_session and not user_id:
        try:
            from concierge.utils.session_manager import validate_session
            is_valid, temp_user_id, reason = validate_session(magic_link_session)
            if not is_valid:
                current_app.logger.error(f"Invalid magic link session for conversation message: {reason}")
                return jsonify({"error": "Invalid session"}), 401
        except Exception as e:
            current_app.logger.error(f"Error validating magic link session: {e}")
            return jsonify({"error": "Session validation failed"}), 401

    try:
        data = request.get_json()
        conversation_id = data.get('conversation_id')
        property_id = data.get('property_id')
        message_data = data.get('message')

        if not conversation_id or not property_id or not message_data:
            return jsonify({"error": "Conversation ID, property ID, and message data are required"}), 400

        # Import DynamoDB conversation functions
        from concierge.utils.dynamodb_client import add_message_to_conversation

        success = add_message_to_conversation(
            conversation_id=conversation_id,
            property_id=property_id,
            message_data=message_data
        )

        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to add message to conversation"}), 500

    except Exception as e:
        print(f"Error adding message to conversation: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500

@api_bp.route('/conversations/<conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    """Get conversation details and messages."""
    try:
        property_id = request.args.get('property_id')

        if not property_id:
            return jsonify({"error": "Property ID is required"}), 400

        # Import DynamoDB conversation functions
        from concierge.utils.dynamodb_client import get_conversation

        conversation = get_conversation(conversation_id, property_id)

        if conversation:
            return jsonify({
                "success": True,
                "conversation": conversation
            })
        else:
            return jsonify({"error": "Conversation not found"}), 404

    except Exception as e:
        print(f"Error getting conversation: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500


@api_bp.route('/conversations/property/<property_id>', methods=['GET'])
@login_required
def get_property_conversations(property_id):
    """Get all conversations (text chat and voice calls) for a property."""
    try:
        # Import required functions
        from concierge.utils.dynamodb_client import list_property_conversations_all
        from concierge.utils.firestore_client import get_property

        # Verify property ownership
        user_id = session.get('user_id')
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"error": "Unauthorized access to property"}), 403

        # Get pagination parameters
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Get filter parameters
        channel_filter = request.args.get('channel')  # 'text_chat', 'voice_call', or None for all
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        guest_name_filter = request.args.get('guest_name')

        # Get all conversations for the property
        conversations = list_property_conversations_all(
            property_id=property_id,
            limit=limit + offset,  # Get more to handle offset
            channel_filter=channel_filter,
            date_from=date_from,
            date_to=date_to,
            guest_name_filter=guest_name_filter
        )

        # Apply offset and limit
        paginated_conversations = conversations[offset:offset + limit]

        # Do NOT generate summaries inline. If missing, return immediately and let
        # background jobs or explicit bulk-generation fill them asynchronously.

        # Format conversations for the frontend
        formatted_conversations = []
        for conv in paginated_conversations:
            formatted_conv = format_conversation_for_list(conv)
            formatted_conversations.append(formatted_conv)

        return jsonify({
            "success": True,
            "conversations": formatted_conversations,
            "total": len(conversations),
            "limit": limit,
            "offset": offset,
            "has_more": len(conversations) > offset + limit
        })

    except Exception as e:
        current_app.logger.error(f"Error getting property conversations: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500


@api_bp.route('/conversations/details/<conversation_id>', methods=['GET'])
@login_required
def get_conversation_details(conversation_id):
    """Get detailed conversation data including full transcript."""
    try:
        property_id = request.args.get('property_id')
        conversation_type = request.args.get('type', 'conversation')  # 'conversation' or 'voice_diagnostics'

        if not property_id:
            return jsonify({"error": "Property ID is required"}), 400

        # Import required functions
        from concierge.utils.dynamodb_client import get_conversation, get_voice_call_diagnostics
        from concierge.utils.firestore_client import get_property

        # Verify property ownership
        user_id = session.get('user_id')
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"error": "Unauthorized access to property"}), 403

        conversation = None

        if conversation_type == 'voice_diagnostics':
            # Get voice call diagnostics session (pass property_id for direct key lookup fallback)
            conversation = get_voice_call_diagnostics(conversation_id, property_id)
        else:
            # Get regular conversation
            conversation = get_conversation(conversation_id, property_id)

        if conversation:
            # Format the conversation for detailed view
            formatted_conversation = format_conversation_details(conversation, conversation_type)

            # Normalize status in details view too
            try:
                entity_type = 'VOICE_CALL_DIAGNOSTICS' if conversation_type == 'voice_diagnostics' else 'CONVERSATION'
                def _parse_iso(ts: str):
                    try:
                        if not ts:
                            return None
                        s = ts.replace('Z', '+00:00')
                        return datetime.fromisoformat(s)
                    except Exception:
                        return None
                def _norm(entity: str, raw: str, start_ts: str, end_ts: str) -> str:
                    rawl = (raw or '').lower()
                    sd = _parse_iso(start_ts)
                    ed = _parse_iso(end_ts)
                    if entity == 'VOICE_CALL_DIAGNOSTICS':
                        if ed is not None:
                            return 'completed'
                        if rawl in {'completed','fallback_completed'}:
                            return 'completed'
                        if rawl in {'failed','error'}:
                            return 'failed'
                        if rawl in {'initializing','pending','fallback_mode'}:
                            return 'pending'
                        try:
                            if sd is not None and (datetime.now(timezone.utc)-sd).total_seconds()>2*3600:
                                return 'completed'
                        except Exception:
                            pass
                        return 'active'
                    if rawl in {'completed','closed'}:
                        return 'completed'
                    if rawl in {'failed','error'}:
                        return 'failed'
                    if rawl in {'initializing','pending'}:
                        return 'pending'
                    return rawl if rawl else 'active'
                # Apply normalized status
                formatted_conversation['status'] = _norm(
                    entity_type,
                    conversation.get('Status'),
                    formatted_conversation.get('start_time'),
                    formatted_conversation.get('end_time')
                )
            except Exception:
                pass
            return jsonify({
                "success": True,
                "conversation": formatted_conversation
            })
        else:
            return jsonify({"error": "Conversation not found"}), 404

    except Exception as e:
        current_app.logger.error(f"Error getting conversation details: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500


def format_conversation_for_list(conversation):
    """Format conversation data for list display."""
    entity_type = conversation.get('EntityType', '')

    # Normalize status for display
    def _parse_iso(ts: str):
        try:
            if not ts:
                return None
            s = ts.replace('Z', '+00:00')
            return datetime.fromisoformat(s)
        except Exception:
            return None

    def _normalize_status(entity: str, raw_status: str, start_ts: str, end_ts: str) -> str:
        raw = (raw_status or '').lower()
        start_dt = _parse_iso(start_ts)
        end_dt = _parse_iso(end_ts)
        if entity == 'VOICE_CALL_DIAGNOSTICS':
            if end_dt is not None:
                return 'completed'
            if raw in {'completed', 'fallback_completed'}:
                return 'completed'
            if raw in {'failed', 'error'}:
                return 'failed'
            if raw in {'initializing', 'pending', 'fallback_mode'}:
                return 'pending'
            try:
                if start_dt is not None and (datetime.now(timezone.utc) - start_dt).total_seconds() > 2 * 3600:
                    return 'completed'
            except Exception:
                pass
            return 'active'
        # Text chat
        if raw in {'completed', 'closed'}:
            return 'completed'
        if raw in {'failed', 'error'}:
            return 'failed'
        if raw in {'initializing', 'pending'}:
            return 'pending'
        return raw if raw else 'active'

    if entity_type == 'VOICE_CALL_DIAGNOSTICS':
        # Voice call session
        ai_summary = conversation.get('AISummary')
        status = _normalize_status(entity_type, conversation.get('Status'), conversation.get('StartTime') or conversation.get('CreatedAt'), conversation.get('EndTime'))
        return {
            'id': conversation.get('SessionId'),
            'type': 'voice_call',
            'guest_name': conversation.get('GuestName', 'Unknown'),
            'start_time': conversation.get('StartTime') or conversation.get('CreatedAt'),
            'end_time': conversation.get('EndTime'),
            'duration': conversation.get('Duration'),
            'status': status,
            'channel': 'voice_call',
            'message_count': len(conversation.get('Transcripts', [])),
            'summary': ai_summary if ai_summary else 'Summary for this conversation is coming soon.',
            'reservation_id': conversation.get('ReservationId'),
            'property_id': conversation.get('PropertyId')
        }
    else:
        # Regular text conversation
        messages = conversation.get('Messages', [])
        ai_summary = conversation.get('AISummary')
        status = _normalize_status(entity_type, conversation.get('Status'), conversation.get('StartTime') or conversation.get('CreatedAt'), conversation.get('LastUpdateTime'))
        return {
            'id': conversation.get('ConversationId'),
            'type': 'text_chat',
            'guest_name': conversation.get('GuestName', 'Unknown'),
            'start_time': conversation.get('StartTime') or conversation.get('CreatedAt'),
            'end_time': conversation.get('LastUpdateTime'),
            'duration': None,
            'status': status,
            'channel': 'text_chat',
            'message_count': len(messages),
            'summary': ai_summary if ai_summary else 'Summary for this conversation is coming soon.',
            'reservation_id': conversation.get('ReservationId'),
            'property_id': conversation.get('PropertyId')
        }


@api_bp.route('/conversations/summaries/bulk-generate', methods=['POST'])
@login_required
def bulk_generate_conversation_summaries():
    """Trigger background AI summary generation for a list of conversations/sessions.
    Accepts both text_chat (ConversationId) and voice_call (SessionId)."""
    try:
        data = request.get_json() or {}
        items = data.get('conversations', [])

        if not isinstance(items, list) or len(items) == 0:
            return jsonify({"success": False, "error": "No conversations provided"}), 400

        # For voice_call items, we can directly request details to warm cache and let finalize/background pick up
        # For text_chat items, if we later store summaries, a similar background worker can be implemented
        triggered = 0
        from concierge.utils.dynamodb_client import get_voice_call_diagnostics, get_conversation, update_conversation
        from concierge.utils.ai_helpers import generate_conversation_summary

        for item in items:
            conv_type = item.get('type')
            conv_id = item.get('id')
            property_id = item.get('property_id')
            if not conv_type or not conv_id:
                continue

            if conv_type == 'voice_call':
                # Touch the record to ensure it exists; background generation occurs on finalize.
                try:
                    _ = get_voice_call_diagnostics(conv_id, property_id)
                except Exception:
                    pass
                triggered += 1
            else:
                # Text chat: fetch conversation and generate/store AISummary immediately
                try:
                    conv = get_conversation(conv_id, property_id)
                    if conv and not conv.get('AISummary'):
                        messages = conv.get('Messages', [])
                        # Optionally include property context (best-effort)
                        property_context = None
                        try:
                            from concierge.utils.firestore_client import get_property as fs_get_property
                            property_context = fs_get_property(property_id)
                        except Exception:
                            pass
                        ai_summary = generate_conversation_summary(
                            messages=messages,
                            property_context=property_context,
                            reservation_info=None,
                            guest_name=conv.get('GuestName')
                        )
                        if ai_summary:
                            update_conversation(property_id, conv_id, {'AISummary': ai_summary})
                    triggered += 1
                except Exception:
                    # Continue; best-effort
                    triggered += 1

        return jsonify({"success": True, "triggered": triggered})
    except Exception as e:
        current_app.logger.error(f"Error in bulk summary generation request: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def format_conversation_details(conversation, conversation_type):
    """Format conversation data for detailed modal view."""
    if conversation_type == 'voice_diagnostics':
        # Voice call session details
        transcripts = conversation.get('Transcripts', [])
        events = conversation.get('EventTimeline', [])

        # Extract feedback if present on the record
        feedback = None
        try:
            enjoyment = conversation.get('FeedbackEnjoymentRating')
            accuracy = conversation.get('FeedbackAccuracyRating')
            fid = conversation.get('FeedbackId')
            submitted_at = conversation.get('FeedbackSubmittedAt')
            if enjoyment is not None or accuracy is not None or fid is not None:
                feedback = {
                    'enjoyment': enjoyment,
                    'accuracy': accuracy,
                    'id': fid,
                    'submitted_at': submitted_at
                }
        except Exception:
            pass

        return {
            'id': conversation.get('SessionId'),
            'type': 'voice_call',
            'guest_name': conversation.get('GuestName', 'Unknown'),
            'start_time': conversation.get('StartTime') or conversation.get('CreatedAt'),
            'end_time': conversation.get('EndTime'),
            'duration': conversation.get('Duration'),
            'status': conversation.get('Status', 'Unknown'),
            'channel': 'voice_call',
            'reservation_id': conversation.get('ReservationId'),
            'property_id': conversation.get('PropertyId'),
            'transcripts': transcripts,
            'events': events,
            'quality_metrics': conversation.get('QualityMetrics', {}),
            'feedback': feedback,
            'technical_config': conversation.get('TechnicalConfig', {}),
            'client_diagnostics': conversation.get('ClientDiagnostics', {}),
            'network_quality': conversation.get('NetworkQuality', {}),
            'errors': conversation.get('Errors', []),
            'warnings': conversation.get('Warnings', [])
        }
    else:
        # Regular text conversation details
        messages = conversation.get('Messages', [])

        # Extract feedback if present on the text conversation record
        feedback = None
        try:
            enjoyment = conversation.get('FeedbackEnjoymentRating')
            accuracy = conversation.get('FeedbackAccuracyRating')
            fid = conversation.get('FeedbackId')
            submitted_at = conversation.get('FeedbackSubmittedAt')
            if enjoyment is not None or accuracy is not None or fid is not None:
                feedback = {
                    'enjoyment': enjoyment,
                    'accuracy': accuracy,
                    'id': fid,
                    'submitted_at': submitted_at
                }
        except Exception:
            pass

        return {
            'id': conversation.get('ConversationId'),
            'type': 'text_chat',
            'guest_name': conversation.get('GuestName', 'Unknown'),
            'start_time': conversation.get('CreatedAt'),
            'end_time': conversation.get('LastUpdateTime'),
            'duration': None,
            'status': conversation.get('Status', 'Active'),
            'channel': 'text_chat',
            'reservation_id': conversation.get('ReservationId'),
            'property_id': conversation.get('PropertyId'),
            'messages': messages,
            'feedback': feedback,
            'phone_number': conversation.get('PhoneNumber'),
            'user_id': conversation.get('UserId')
        }


def generate_voice_call_summary(conversation):
    """Generate a summary for voice call sessions."""
    transcripts = conversation.get('Transcripts', [])
    guest_name = conversation.get('GuestName', 'Guest')

    if not transcripts:
        return f"{guest_name} had a voice call with no recorded conversation."

    # Get user messages (questions/requests)
    user_messages = [t for t in transcripts if t.get('role') == 'user']

    if not user_messages:
        return f"{guest_name} had a voice call session."

    # Create summary based on first user message
    first_message = user_messages[0].get('text', '')
    if len(first_message) > 60:
        first_message = first_message[:60] + "..."

    return f"{guest_name} asked: \"{first_message}\""


def generate_text_chat_summary(messages):
    """Generate a summary for text chat conversations."""
    if not messages:
        return "No messages in conversation."

    # Get the first user message
    user_messages = [m for m in messages if m.get('role') == 'user']

    if not user_messages:
        return "Conversation with no user messages."

    first_message = user_messages[0].get('content', '')
    if len(first_message) > 60:
        first_message = first_message[:60] + "..."

    return f"Started with: \"{first_message}\""


def generate_conversation_summary_for_any(conversation):
    """Unified summarization using Gemini-backed helper for both voice and text.

    Falls back to lightweight heuristics if helper fails or no messages.
    """
    try:
        from concierge.utils.ai_helpers import generate_conversation_summary as gen_sum

        messages = []
        if conversation.get('EntityType') == 'VOICE_CALL_DIAGNOSTICS':
            for t in conversation.get('Transcripts', []) or []:
                messages.append({'role': t.get('role', ''), 'text': t.get('text', '')})
        else:
            for m in conversation.get('Messages', []) or []:
                messages.append({'role': m.get('role', ''), 'text': m.get('text') or m.get('content', '')})

        if not messages:
            return 'No messages in conversation.'

        # Optional property context (best-effort)
        property_context = None
        try:
            from concierge.utils.firestore_client import get_property as fs_get_property
            pid = conversation.get('PropertyId')
            if pid:
                property_context = fs_get_property(pid)
        except Exception:
            pass

        guest_name = conversation.get('GuestName')
        summary = gen_sum(messages=messages, property_context=property_context, guest_name=guest_name)
        return summary or 'Summary unavailable.'
    except Exception:
        # Fallbacks
        if conversation.get('EntityType') == 'VOICE_CALL_DIAGNOSTICS':
            return generate_voice_call_summary(conversation)
        return generate_text_chat_summary(conversation.get('Messages', []))

# === End Conversation Management Endpoints ===


# === Magic Link Management Endpoints ===

@api_bp.route('/property/<property_id>/reservations/<reservation_id>/magic-link', methods=['POST'])
@login_required
def generate_magic_link_for_reservation(property_id, reservation_id):
    """Generate a new magic link for a reservation."""
    try:
        from datetime import datetime, timezone, timedelta

        # Verify user has access to this property
        user_id = g.user_id
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"error": "Property not found or access denied."}), 404

        # Get reservation to verify it exists and belongs to this property
        reservation = get_reservation(reservation_id)
        if not reservation or reservation.get('propertyId') != property_id:
            return jsonify({"error": "Reservation not found or doesn't belong to this property."}), 404

        # Calculate expiration time (checkout date + 24 hours)
        checkout_date = reservation.get('endDate')
        if checkout_date:
            if isinstance(checkout_date, str):
                checkout_datetime = datetime.fromisoformat(checkout_date.replace('Z', '+00:00'))
            else:
                checkout_datetime = checkout_date
            expires_at = checkout_datetime + timedelta(hours=24)
        else:
            # Default to 7 days from now if no checkout date
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        # Get current request's base URL for proper domain/port sync
        base_url = request.url_root.rstrip('/')
        
        # Create magic link with current base URL
        raw_token = create_magic_link(reservation_id, expires_at, base_url)
        if not raw_token:
            return jsonify({"error": "Failed to create magic link."}), 500

        # Generate full URL with current base URL
        magic_link_url = generate_magic_link_url(raw_token, base_url)

        # Get the last 4 digits for verification (for the host's reference)
        phone_number = reservation.get('guestPhoneNumber') or reservation.get('GuestPhoneNumber')
        guest_phone_last4 = reservation.get('guestPhoneLast4') or reservation.get('GuestPhoneLast4')
        
        # Extract last 4 digits from full phone number or use stored last 4
        last_4_digits = None
        if phone_number and len(phone_number) >= 4:
            last_4_digits = phone_number[-4:]
        elif guest_phone_last4:
            last_4_digits = guest_phone_last4

        return jsonify({
            "success": True,
            "magic_link_url": magic_link_url,
            "expires_at": expires_at.isoformat(),
            "verification_last_4_digits": last_4_digits
        })

    except Exception as e:
        current_app.logger.error(f"Error generating magic link: {e}")
        return jsonify({"error": "An error occurred while generating the magic link."}), 500

@api_bp.route('/property/<property_id>/reservations/<reservation_id>/magic-links', methods=['GET'])
@login_required
def list_magic_links_for_reservation(property_id, reservation_id):
    """List all magic links for a reservation."""
    try:
        # Verify user has access to this property
        user_id = g.user_id
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"error": "Property not found or access denied."}), 404

        # Get magic links for this reservation
        magic_links = list_magic_links_by_reservation(reservation_id)

        # URLs are now stored in the magic link documents
        # No need to modify the URL field as it's already included

        return jsonify({
            "success": True,
            "magic_links": magic_links
        })

    except Exception as e:
        current_app.logger.error(f"Error listing magic links: {e}")
        return jsonify({"error": "An error occurred while listing magic links."}), 500

@api_bp.route('/property/<property_id>/reservations/<reservation_id>/magic-links/<link_id>/revoke', methods=['POST'])
@login_required
def revoke_magic_link_for_reservation(property_id, reservation_id, link_id):
    """Revoke a magic link."""
    try:
        # Verify user has access to this property
        user_id = g.user_id
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"error": "Property not found or access denied."}), 404

        # Revoke the magic link using the link_id (which is the token_hash)
        from concierge.utils.firestore_client import update_magic_link
        success = update_magic_link(link_id, {
            'is_active': False,
            'status': 'revoked'
        })

        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to revoke magic link."}), 500

    except Exception as e:
        current_app.logger.error(f"Error revoking magic link: {e}")
        return jsonify({"error": "An error occurred while revoking the magic link."}), 500

# === System Cleanup Endpoints ===

@api_bp.route('/system/cleanup', methods=['POST'])
@login_required
def manual_system_cleanup():
    """Manually trigger system cleanup tasks."""
    try:
        # Check if user has admin privileges (you might want to add role checking here)
        user_id = g.user_id
        
        # Import cleanup functions
        from concierge.utils.firestore_client import perform_daily_cleanup
        
        # Perform cleanup
        cleanup_results = perform_daily_cleanup()
        
        return jsonify({
            "success": True,
            "message": "System cleanup completed successfully",
            "results": cleanup_results
        })

    except Exception as e:
        current_app.logger.error(f"Error during manual system cleanup: {e}")
        return jsonify({"error": "An error occurred during system cleanup."}), 500

@api_bp.route('/system/cleanup/status', methods=['GET'])
@login_required
def get_cleanup_status():
    """Get status of items that would be cleaned up."""
    try:
        from concierge.utils.firestore_client import initialize_firebase, get_firestore_client
        from datetime import datetime, timezone
        
        if not initialize_firebase():
            return jsonify({"error": "Database initialization failed"}), 500
        
        db = get_firestore_client()
        now = datetime.now(timezone.utc)
        
        # Count expired magic links
        expired_magic_links_query = db.collection('magic_links').where('expires_at', '<', now).where('is_active', '==', True)
        expired_magic_links_count = len(list(expired_magic_links_query.stream()))
        
        # Count expired temporary users
        expired_temp_users_query = db.collection('users').where('isTemporary', '==', True).where('expiresAt', '<', now)
        expired_temp_users_count = len(list(expired_temp_users_query.stream()))
        
        return jsonify({
            "success": True,
            "status": {
                "expired_magic_links": expired_magic_links_count,
                "expired_temp_users": expired_temp_users_count,
                "total_items_to_cleanup": expired_magic_links_count + expired_temp_users_count
            }
        })

    except Exception as e:
        current_app.logger.error(f"Error getting cleanup status: {e}")
        return jsonify({"error": "An error occurred while getting cleanup status."}), 500

# === End Magic Link Management Endpoints ===


# === Property Setup / Airbnb Integration Endpoints ===

@api_bp.route('/record-consent', methods=['POST'])
def record_consent():
    """
    Record user's data access consent with timestamp.
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        data = request.get_json()
        consent_type = data.get('consent_type', 'airbnb_data_access')

        # Collect additional consent details
        consent_details = {
            'ipAddress': request.environ.get('REMOTE_ADDR'),
            'userAgent': request.headers.get('User-Agent'),
            'url': data.get('url'),  # The URL they're consenting to access
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        # Record the consent
        success = record_data_access_consent(user_id, consent_type, consent_details)

        if success:
            current_app.logger.info(f"Recorded {consent_type} consent for user {user_id}")
            return jsonify({"success": True, "message": "Consent recorded successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to record consent"}), 500

    except Exception as e:
        current_app.logger.error(f"Error recording consent: {e}")
        return jsonify({"success": False, "error": "Failed to record consent"}), 500

@api_bp.route('/user-consents', methods=['GET'])
@login_required
def get_user_consents_api():
    """
    Get all consent records for the current user.
    """
    try:
        user_id = g.user_id
        consents = get_user_consents(user_id)

        return jsonify({
            "success": True,
            "consents": consents,
            "total": len(consents)
        })

    except Exception as e:
        current_app.logger.error(f"Error getting user consents: {e}")
        return jsonify({"success": False, "error": "Failed to get consents"}), 500

@api_bp.route('/property-setup/process-url', methods=['POST'])
def process_airbnb_url():
    """
    Process an Airbnb URL (listing or user profile) and extract user profile URL.
    Supports internal editor URLs, public listing URLs, and user profile URLs.
    Also records user consent for data access.
    """
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        url = data.get('url', '').strip()
        consent_given = data.get('consent_given', False)

        if not url:
            return jsonify({"success": False, "error": "URL is required"}), 400

        # Check for consent
        if not consent_given:
            return jsonify({"success": False, "error": "Data access consent is required"}), 400

        # Record consent if user is authenticated
        if user_id:
            consent_details = {
                'ipAddress': request.environ.get('REMOTE_ADDR'),
                'userAgent': request.headers.get('User-Agent'),
                'url': url,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            record_data_access_consent(user_id, 'airbnb_data_access', consent_details)

        scraper = AirbnbScraper(use_selenium=False)

        # Use enhanced URL validation and normalization
        validation = scraper._validate_airbnb_url(url)

        if not validation['is_valid']:
            return jsonify({
                "success": False,
                "error": validation['error_message']
            }), 400

        # Use the normalized URL
        normalized_url = validation['normalized_url']
        url_type = validation['url_type']

        current_app.logger.info(f"Processing URL: {url} -> {normalized_url} (type: {url_type})")

        if url_type == 'listing':
            # It's a listing URL, extract user profile
            user_url = scraper.extract_user_from_listing(normalized_url)
            if not user_url:
                # Try with Selenium as fallback
                current_app.logger.info("Trying with Selenium as fallback for user profile extraction")
                try:
                    selenium_scraper = AirbnbScraper(use_selenium=True)
                    user_url = selenium_scraper.extract_user_from_listing(normalized_url)
                except Exception as e:
                    current_app.logger.error(f"Selenium fallback failed: {e}")

                if not user_url:
                    return jsonify({"success": False, "error": "Could not extract user profile from listing URL. Please try entering the host's profile URL directly."}), 400
        elif url_type == 'profile':
            # It's already a user profile URL
            user_url = normalized_url
        else:
            return jsonify({"success": False, "error": "Please check if the URL is correct. Supported formats: listing pages or user profiles."}), 400

        return jsonify({
            "success": True,
            "user_url": user_url,
            "url_type": url_type,
            "original_url": url,
            "normalized_url": normalized_url
        })

    except Exception as e:
        current_app.logger.error(f"Error processing Airbnb URL: {e}")
        return jsonify({"success": False, "error": "Failed to process URL"}), 500


@api_bp.route('/property-setup/check-duplicates', methods=['POST'])
def check_duplicate_listings():
    """
    Check if any of the provided listing URLs already exist as properties.
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        data = request.get_json()
        listing_urls = data.get('listing_urls', [])

        if not listing_urls:
            return jsonify({"success": True, "duplicates": []})

        # Get properties from database for current user only to check for duplicates
        from concierge.utils.firestore_client import get_firestore_db

        duplicates = []
        existing_urls = set()

        # Get Firestore database
        db = get_firestore_db()
        if db:
            try:
                # Get only current user's properties with airbnbListingUrl field
                user_properties_query = db.collection('properties').where('hostId', '==', user_id).where('airbnbListingUrl', '!=', '')
                user_properties = list(user_properties_query.stream())

                # Collect existing normalized URLs from user's properties only
                for prop_doc in user_properties:
                    prop_data = prop_doc.to_dict()
                    airbnb_url = prop_data.get('airbnbListingUrl', '')
                    if airbnb_url:
                        existing_urls.add(airbnb_url)  # These should already be normalized

            except Exception as e:
                current_app.logger.error(f"Error fetching user properties for duplicate check: {e}")
                # Fallback to alternative user-only check if query fails
                user_properties = list_properties_by_host(user_id)
                for property_data in user_properties:
                    airbnb_url = property_data.get('airbnbListingUrl', '')
                    if airbnb_url:
                        existing_urls.add(airbnb_url)

        # Check each listing URL after normalizing it
        for url in listing_urls:
            # Normalize the URL for comparison (remove query parameters)
            normalized_url = normalize_airbnb_url_for_duplicate_check(url)

            if normalized_url in existing_urls:
                # Find which property has this URL to provide better error message
                duplicate_message = 'You have already imported this property'

                if db:
                    try:
                        # Query only current user's properties since we're doing user-scoped duplicate checking
                        existing_query = db.collection('properties').where('hostId', '==', user_id).where('airbnbListingUrl', '==', normalized_url).limit(1)
                        existing_props = list(existing_query.stream())

                        if existing_props:
                            existing_prop = existing_props[0].to_dict()
                            existing_name = existing_prop.get('name', 'Unknown Property')
                            duplicate_message = f'You have already imported this property: "{existing_name}"'
                    except Exception as e:
                        current_app.logger.warning(f"Error getting duplicate property details: {e}")

                duplicates.append({
                    'url': url,  # Return original URL for frontend reference
                    'normalized_url': normalized_url,  # Include normalized for debugging
                    'message': duplicate_message
                })
                current_app.logger.info(f"Duplicate detected for user {user_id}: {url} -> {normalized_url}")
            else:
                current_app.logger.debug(f"No duplicate for: {url} -> {normalized_url}")

        return jsonify({
            "success": True,
            "duplicates": duplicates,
            "total_checked": len(listing_urls),
            "duplicates_found": len(duplicates)
        })

    except Exception as e:
        current_app.logger.error(f"Error checking duplicates: {e}")
        return jsonify({"success": False, "error": "Failed to check for duplicates"}), 500


@api_bp.route('/property-setup/get-listings', methods=['POST'])
def get_airbnb_listings():
    """
    Get all listings for an Airbnb user profile.
    """
    try:
        data = request.get_json()
        user_url = data.get('user_url', '').strip()

        if not user_url:
            return jsonify({"success": False, "error": "User URL is required"}), 400

        # Validate user URL format
        if '/users/show/' not in user_url:
            return jsonify({"success": False, "error": "Invalid user profile URL"}), 400

        # Save user_url and host info if not already saved
        user_id = session.get('user_id')
        if user_id:
            user_data = get_user(user_id)
            update_data = {}

            if not user_data.get('airbnbUserLink'):
                update_data['airbnbUserLink'] = user_url

                # Extract host information - try Selenium first
                try:
                    selenium_scraper = AirbnbScraper(use_selenium=True)
                    host_info = selenium_scraper.extract_host_info(user_url)

                    # If Selenium didn't get good data, try regular scraper
                    if not host_info.get('name'):
                        current_app.logger.info("Selenium didn't extract host name, trying regular scraper")
                        regular_scraper = AirbnbScraper(use_selenium=False)
                        host_info = regular_scraper.extract_host_info(user_url)

                    if host_info.get('name'):
                        update_data['displayName'] = host_info['name']
                        current_app.logger.info(f"Extracted host name: {host_info['name']}")
                    if host_info.get('location'):
                        update_data['hostLocation'] = host_info['location']
                        current_app.logger.info(f"Extracted host location: {host_info['location']}")
                except Exception as e:
                    current_app.logger.error(f"Error extracting host info: {e}")

            # Update user profile if we have data to update
            if update_data:
                try:
                    update_user(user_id, update_data)
                    current_app.logger.info(f"Updated user profile with: {update_data}")
                except Exception as e:
                    current_app.logger.error(f"Error updating user profile: {e}")

        # Try Selenium first for better dynamic content handling
        current_app.logger.info("Trying Selenium scraper first for better data extraction")
        listings = []

        try:
            selenium_scraper = AirbnbScraper(use_selenium=True)
            listings = selenium_scraper.extract_user_listings(user_url)
            current_app.logger.info(f"Selenium scraper found {len(listings)} listings")

            # Check if we got actual data or just fallback data
            has_real_data = any(listing.get('title') and listing.get('title') != 'Location to be determined'
                              and not listing.get('title').startswith('Property ') for listing in listings)

            if not has_real_data:
                current_app.logger.info("Selenium returned only fallback data, trying regular scraper")
                raise Exception("No real data from Selenium")

        except Exception as e:
            current_app.logger.error(f"Selenium scraper failed: {e}")
            current_app.logger.info("Falling back to regular scraper")

            scraper = AirbnbScraper(use_selenium=False)
            listings = scraper.extract_user_listings(user_url)

        if not listings:
            return jsonify({"success": False, "error": "No listings found for this user"}), 400

        # Format listings for frontend display
        formatted_listings = []
        for listing in listings:
            # Debug: Log the raw listing data
            current_app.logger.info(f"Raw listing data: {listing}")

            # Handle different possible data structures for images
            first_image = ''

            # Check if there's a direct 'image' field (new format)
            if listing.get('image'):
                first_image = listing.get('image')
            else:
                # Fallback to 'images' array (old format)
                images = listing.get('images', [])
                if images and len(images) > 0:
                    if isinstance(images[0], dict):
                        first_image = images[0].get('url', '')
                    elif isinstance(images[0], str):
                        first_image = images[0]

            reviews = listing.get('reviews', {})
            rating = None
            review_count = 0
            if isinstance(reviews, dict):
                rating = reviews.get('rating')
                review_count = reviews.get('count', 0)

            formatted_listing = {
                'url': listing.get('url', ''),
                'title': listing.get('title', '') or listing.get('name', '') or 'Untitled Property',
                'location': listing.get('location', '') or listing.get('address', '') or 'Location not available',
                'image': first_image,
                'property_type': listing.get('property_type', '') or listing.get('type', ''),
                'rating': rating,
                'review_count': review_count
            }

            current_app.logger.info(f"Formatted listing: {formatted_listing}")
            formatted_listings.append(formatted_listing)

        return jsonify({
            "success": True,
            "listings": formatted_listings,
            "user_url": user_url
        })

    except Exception as e:
        current_app.logger.error(f"Error getting Airbnb listings: {e}")
        return jsonify({"success": False, "error": "Failed to fetch listings"}), 500


@api_bp.route('/property-setup/import-properties', methods=['POST'])
def import_selected_properties():
    """
    Import selected Airbnb listings as properties.
    """
    try:
        # Get current user
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        data = request.get_json()
        selected_listings = data.get('selected_listings', [])
        user_url = data.get('user_url', '')
        job_id = data.get('job_id')

        if not selected_listings:
            return jsonify({"success": False, "error": "No listings selected"}), 400

        if not user_url:
            return jsonify({"success": False, "error": "User URL is required"}), 400

        # Save user_url to user profile and extract host info if not already saved
        user_data = get_user(user_id)
        update_data = {}

        if not user_data.get('airbnbUserLink'):
            update_data['airbnbUserLink'] = user_url

            # Extract host information
            try:
                host_info = scraper.extract_host_info(user_url)
                if host_info.get('name'):
                    update_data['displayName'] = host_info['name']
                    current_app.logger.info(f"Extracted host name: {host_info['name']}")
                if host_info.get('location'):
                    update_data['hostLocation'] = host_info['location']
            except Exception as e:
                current_app.logger.error(f"Error extracting host info: {e}")

        # Update user profile if we have data to update
        if update_data:
            try:
                update_user(user_id, update_data)
                current_app.logger.info(f"Updated user profile with: {update_data}")
            except Exception as e:
                current_app.logger.error(f"Error updating user profile: {e}")

        # Initialize (or reinitialize) the job state if job_id provided
        if job_id:
            IMPORT_JOBS[job_id] = {
                'canceled': False,
                'started_at': datetime.now(timezone.utc)
            }

        created_properties = []
        scraper = AirbnbScraper(use_selenium=False)

        for listing_url in selected_listings:
            # Check for client-requested cancellation between items
            if job_id and IMPORT_JOBS.get(job_id, {}).get('canceled'):
                current_app.logger.info(f"Import job {job_id} was canceled by client; returning partial results")
                break
            try:
                # Get basic listing information
                listing_details = scraper.extract_listing_details(listing_url)

                if not listing_details:
                    current_app.logger.warning(f"Could not extract basic details for listing: {listing_url}")
                    continue

                # Perform deep extraction using integrated scraper methods
                current_app.logger.info(f"Starting deep extraction for: {listing_url}")
                try:
                    extracted_data = scraper.extract_deep_property_data(listing_url)
                except Exception as e:
                    # Normalize known transient failures (e.g., 503) into a clear JSON error
                    current_app.logger.error(f"Deep extraction failed for {listing_url}: {e}")
                    return jsonify({
                        "success": False,
                        "error": f"Deep extraction failed for {listing_url}: {str(e)}"
                    }), 502

                # Create property with extracted data using integrated scraper method
                property_id = scraper.create_property_from_extraction(
                    user_id, listing_details, extracted_data
                )

                if property_id:
                    created_properties.append({
                        'id': property_id,
                        'name': listing_details.get('title', 'Imported Property'),
                        'address': listing_details.get('location', ''),
                        'status': 'inactive',  # New properties start inactive
                        'new': True  # Flag for setup requirement
                    })
                    current_app.logger.info(f"Successfully imported property with deep extraction: {property_id}")
                else:
                    current_app.logger.error(f"Failed to create property for listing: {listing_url}")

            except Exception as e:
                current_app.logger.error(f"Error importing listing {listing_url}: {e}")
                continue

        # Cleanup job tracking if present
        if job_id and job_id in IMPORT_JOBS:
            # Keep the canceled flag to let client know; remove later if desired
            canceled = IMPORT_JOBS[job_id].get('canceled', False)
            # Remove tracking entry to prevent buildup
            try:
                del IMPORT_JOBS[job_id]
            except Exception:
                pass
        else:
            canceled = False

        return jsonify({
            "success": True,
            "created_properties": created_properties,
            "total_imported": len(created_properties),
            "canceled": canceled
        })

    except Exception as e:
        current_app.logger.error(f"Error importing properties: {e}")
        return jsonify({"success": False, "error": "Failed to import properties"}), 500


@api_bp.route('/property-setup/import-properties/cancel', methods=['POST'])
def cancel_import_properties():
    """
    Cancel a running property import job. The client should pass the job_id it started.
    The import loop checks this flag between items and returns early with partial results.
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        data = request.get_json() or {}
        job_id = data.get('job_id')
        if not job_id:
            return jsonify({"success": False, "error": "job_id required"}), 400

        if job_id not in IMPORT_JOBS:
            # If the job is already finished or unknown, treat as no-op success
            return jsonify({"success": True, "message": "No active job found; nothing to cancel."})

        IMPORT_JOBS[job_id]['canceled'] = True
        current_app.logger.info(f"Marked import job {job_id} as canceled")
        return jsonify({"success": True})
    except Exception as e:
        current_app.logger.error(f"Error canceling import job: {e}")
        return jsonify({"success": False, "error": "Failed to cancel import"}), 500


@api_bp.route('/properties/<property_id>/setup-progress', methods=['POST'])
def save_setup_progress(property_id):
    """
    Save progress for a specific step in the property setup process.
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        data = request.get_json()

        step = data.get('step')
        step_data = data.get('data', {})

        if not step:
            return jsonify({"success": False, "error": "Step number required"}), 400

        # Get the property to verify ownership
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"success": False, "error": "Property not found or access denied"}), 404

        # Update the property with step data
        update_data = {}

        if step == 1:  # Basic Information
            # Only update address if it's likely a real street address. Avoid overwriting with imported neighborhood.
            import re
            def _looks_like_neighborhood_only(addr: str) -> bool:
                val = (addr or '').strip()
                if not val:
                    return True
                lower = val.lower()
                placeholder_signals = [
                    'neighborhood', 'district', 'area', 'vicinity',
                    'near', 'around', 'close to', 'united states'
                ]
                if any(sig in lower for sig in placeholder_signals):
                    if re.match(r"^\s*\d{1,6}\s+[A-Za-z0-9 .'-]+", val):
                        return False
                    return True
                if re.match(r"^\s*\d{1,6}\s+[A-Za-z0-9 .'-]{3,}", val):
                    return False
                has_number = re.search(r"\b\d{1,6}\b", val) is not None
                street_types = [
                    'st', 'str', 'street', 'ave', 'avenue', 'blvd', 'boulevard',
                    'rd', 'road', 'dr', 'drive', 'ln', 'lane', 'way', 'trail',
                    'ct', 'court', 'pkwy', 'parkway', 'terrace', 'ter', 'pl', 'place',
                    'hwy', 'highway', 'cir', 'circle'
                ]
                has_street_type = any(re.search(fr"\\b{t}\\b", val, re.IGNORECASE) for t in street_types)
                return not (has_number and has_street_type)

            update_data.update({
                'name': step_data.get('name', ''),
                'description': step_data.get('description', ''),
                'icalUrl': step_data.get('icalUrl', ''),
                'checkInTime': step_data.get('checkInTime', '15:00'),
                'checkOutTime': step_data.get('checkOutTime', '11:00'),
                'wifiDetails': step_data.get('wifiDetails', {}),
                'setupProgress.step1_basic': True
            })

            if 'address' in step_data:
                addr = (step_data.get('address') or '').strip()
                if addr and not _looks_like_neighborhood_only(addr):
                    update_data['address'] = addr
                else:
                    current_app.logger.info(f"Ignoring empty or non-street address for property {property_id}: '{addr}'")

            # Save amenities if provided
            if 'amenities' in step_data:
                amenities_data = step_data['amenities']
                current_app.logger.info(f"Saving amenities data: {amenities_data}")
                update_data['amenities'] = amenities_data
        elif step == 2:  # House Rules
            if 'houseRules' in step_data:
                house_rules_data = step_data['houseRules']
                current_app.logger.info(f"Saving house rules data: {house_rules_data}")
                update_data['houseRules'] = house_rules_data
            update_data['setupProgress.step2_rules'] = True
        elif step == 3:  # Emergency Information
            if 'emergencyInfo' in step_data:
                emergency_info_data = step_data['emergencyInfo']
                current_app.logger.info(f"Saving emergency information data: {emergency_info_data}")

                # Store emergency information as knowledge items
                from concierge.utils.firestore_client import create_knowledge_item
                import uuid

                # Clear existing emergency knowledge items for this property
                from concierge.utils.firestore_client import list_knowledge_items_by_property, delete_knowledge_item
                existing_items = list_knowledge_items_by_property(property_id)
                for item in existing_items:
                    if item.get('type') == 'emergency' and 'setup_wizard' in item.get('tags', []):
                        delete_knowledge_item(item['id'])

                # Create new emergency knowledge items
                for emergency_info in emergency_info_data:
                    if emergency_info.get('enabled', False):
                        item_id = str(uuid.uuid4())

                        # Build content
                        content = emergency_info.get('title', '')
                        if emergency_info.get('instructions'):
                            content += f"\n\nInstructions: {emergency_info['instructions']}"
                        if emergency_info.get('location'):
                            content += f"\n\nLocation: {emergency_info['location']}"

                        item_data = {
                            'propertyId': property_id,
                            'type': 'emergency',
                            'tags': ['emergency', 'safety', 'setup_wizard'],
                            'content': content,
                            'status': 'approved',
                            'source': 'property_setup',
                            'createdAt': datetime.now().isoformat(),
                            'updatedAt': datetime.now().isoformat()
                        }

                        create_knowledge_item(item_id, item_data)
                        current_app.logger.info(f"Created emergency knowledge item: {emergency_info.get('title')}")

                # Also store in property data for easy access
                update_data['emergencyInfo'] = emergency_info_data

            update_data['setupProgress.step3_emergency'] = True
        elif step == 4:  # Property Facts
            property_facts = step_data.get('propertyFacts', [])

            # Save property facts as knowledge items directly
            if property_facts:
                from concierge.utils.firestore_client import create_knowledge_item, list_knowledge_items_by_property, delete_knowledge_item
                import uuid

                # Clear existing property facts knowledge items from setup
                existing_items = list_knowledge_items_by_property(property_id)
                for item in existing_items:
                    if item.get('type') == 'information' and 'setup_wizard' in item.get('tags', []):
                        delete_knowledge_item(item['id'])

                # Create new knowledge items from property facts
                for fact in property_facts:
                    if fact.get('answer') and fact.get('answer').strip():
                        item_id = str(uuid.uuid4())

                        # For custom facts, use the answer as content directly
                        # For predefined questions, use Q&A format
                        if fact.get('question'):
                            content = f"Q: {fact.get('question')}\nA: {fact.get('answer')}"
                        else:
                            content = fact.get('answer')

                        item_data = {
                            'id': item_id,
                            'propertyId': property_id,
                            'type': 'information',
                            'content': content,
                            'tags': ['setup_wizard', 'property_facts'],
                            'status': 'approved',  # Auto-approve setup wizard items
                            'createdAt': datetime.now(timezone.utc),
                            'updatedAt': datetime.now(timezone.utc)
                        }

                        try:
                            create_knowledge_item(item_id, item_data)
                            current_app.logger.info(f"Created property fact knowledge item: {fact.get('question', 'Custom fact')[:50]}...")
                        except Exception as e:
                            current_app.logger.error(f"Failed to create knowledge item for fact: {e}")

            update_data['propertyFacts'] = property_facts
            update_data['setupProgress.step4_facts'] = True
        elif step == 5:  # Review and Approve
            update_data['setupProgress.step5_review'] = True

        # Add timestamp
        update_data['updatedAt'] = datetime.now().isoformat()

        # Update the property
        if update_property(property_id, update_data):
            current_app.logger.info(f"Setup progress saved for property {property_id}, step {step}")
            return jsonify({"success": True, "message": f"Step {step} saved successfully"})
        else:
            return jsonify({"success": False, "error": "Failed to save progress"}), 500

    except Exception as e:
        current_app.logger.error(f"Error saving setup progress: {e}")
        return jsonify({"success": False, "error": "Failed to save setup progress"}), 500


@api_bp.route('/properties/<property_id>/complete-setup', methods=['POST'])
def complete_property_setup(property_id):
    """
    Complete the property setup process and activate the property.
    Creates knowledge items from property facts and finalizes setup.
    """
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        # Get the property to verify ownership
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"success": False, "error": "Property not found or access denied"}), 404

        # Get setup data from request
        setup_data = request.get_json() or {}

        # Import required modules
        from concierge.utils.firestore_client import (
            create_knowledge_item,
            list_knowledge_items_by_property,
            delete_knowledge_item,
            update_knowledge_item,
        )
        import uuid

        # Build a lookup of pending items to convert instead of duplicating on completion
        pending_items = list_knowledge_items_by_property(property_id, status='pending') or []
        used_pending_ids = set()

        def _normalize_text(text: str) -> str:
            try:
                import re as _re
                t = (text or '').lower().strip()
                t = _re.sub(r"\b(q:|a:)\b", "", t)
                t = _re.sub(r"\s+", " ", t)
                t = _re.sub(r"[^a-z0-9 \n]+", "", t)
                return t.strip()
            except Exception:
                return (text or '').lower().strip()

        def _try_approve_matching_pending(target_content: str, suggested_tags: list, *, title: str = '', body: str = '', required_type: str = None) -> bool:
            # Build multiple match candidates to account for formatting differences
            candidates = set()
            candidates.add(_normalize_text(target_content))
            if ':' in target_content:
                candidates.add(_normalize_text(target_content.split(':', 1)[1]))
            if title:
                candidates.add(_normalize_text(title))
            if body:
                candidates.add(_normalize_text(body))

            for item in pending_items:
                item_id = item.get('id')
                if not item_id or item_id in used_pending_ids:
                    continue
                if required_type and item.get('type') != required_type:
                    continue
                norm_item = _normalize_text(item.get('content', ''))
                if norm_item in candidates:
                    # Approve this pending item and merge tags
                    existing_tags = (item.get('tags', []) or [])
                    # Remove 'imported' if present; add setup_wizard and suggested
                    merged = [t for t in existing_tags if t != 'imported'] + ['setup_wizard'] + (suggested_tags or [])
                    new_tags = list(dict.fromkeys(merged))
                    update_knowledge_item(item_id, {
                        'status': 'approved',
                        'tags': new_tags,
                        # Ensure content is standardized to the richer target_content
                        'content': target_content
                    })
                    used_pending_ids.add(item_id)
                    return True
            return False

        # Process house rules and create or convert knowledge items
        house_rules = setup_data.get('houseRules', [])
        current_app.logger.info(f"Processing {len(house_rules)} house rules for property {property_id}")
        if house_rules:
            # Clear existing house rules knowledge items from setup
            existing_items = list_knowledge_items_by_property(property_id)
            for item in existing_items:
                if item.get('type') == 'rule' and 'setup_wizard' in item.get('tags', []):
                    delete_knowledge_item(item['id'])

            # Create new knowledge items from house rules or convert matching pending items
            for i, rule in enumerate(house_rules):
                body = (rule.get('content') or rule.get('description') or '').strip()
                current_app.logger.info(
                    f"House rule {i}: title='{rule.get('title')}', body='{body[:120]}', has_both={bool(rule.get('title') and body)}"
                )
                if rule.get('title') and body:
                    content = f"{rule.get('title')}: {body}"
                    # Prefer converting a matching pending item if present
                    if not _try_approve_matching_pending(content, ['house_rules'], title=rule.get('title', ''), body=body, required_type='rule'):
                        item_id = str(uuid.uuid4())
                        item_data = {
                            'id': item_id,
                            'propertyId': property_id,
                            'type': 'rule',
                            'content': content,
                            'tags': ['setup_wizard', 'house_rules'],
                            'status': 'approved',  # Auto-approve setup wizard items
                            'createdAt': datetime.now(timezone.utc),
                            'updatedAt': datetime.now(timezone.utc)
                        }

                        try:
                            create_knowledge_item(item_id, item_data)
                            current_app.logger.info(f"Created house rule knowledge item: {rule.get('title')[:50]}...")
                        except Exception as e:
                            current_app.logger.error(f"Failed to create knowledge item for house rule: {e}")
                else:
                    current_app.logger.warning(f"Skipping house rule {i} - missing title or content")

        # Process emergency information and create knowledge items
        emergency_info = setup_data.get('emergencyInfo', [])
        if emergency_info:
            # Clear existing emergency knowledge items from setup
            existing_items = list_knowledge_items_by_property(property_id)
            for item in existing_items:
                if item.get('type') == 'emergency' and 'setup_wizard' in item.get('tags', []):
                    delete_knowledge_item(item['id'])

            # Create new knowledge items from emergency information or convert matching pending items
            for info in emergency_info:
                if info.get('title'):
                    # Build content
                    content = info.get('title', '')
                    if info.get('instructions'):
                        content += f"\n\nInstructions: {info['instructions']}"
                    if info.get('location'):
                        content += f"\n\nLocation: {info['location']}"

                    if not _try_approve_matching_pending(content, ['emergency', 'safety'], title=info.get('title', ''), required_type='emergency'):
                        item_id = str(uuid.uuid4())
                        item_data = {
                            'id': item_id,
                            'propertyId': property_id,
                            'type': 'emergency',
                            'content': content,
                            'tags': ['setup_wizard', 'emergency', 'safety'],
                            'status': 'approved',  # Auto-approve setup wizard items
                            'createdAt': datetime.now(timezone.utc),
                            'updatedAt': datetime.now(timezone.utc)
                        }

                        try:
                            create_knowledge_item(item_id, item_data)
                            current_app.logger.info(f"Created emergency info knowledge item: {info.get('title')[:50]}...")
                        except Exception as e:
                            current_app.logger.error(f"Failed to create knowledge item for emergency info: {e}")

        # Process property facts and create knowledge items
        property_facts = setup_data.get('propertyFacts', [])
        if property_facts:

            # Clear existing property facts knowledge items from setup
            existing_items = list_knowledge_items_by_property(property_id)
            for item in existing_items:
                if item.get('type') == 'information' and 'setup_wizard' in item.get('tags', []):
                    delete_knowledge_item(item['id'])

            # Create new knowledge items from property facts or convert matching pending items
            for fact in property_facts:
                if fact.get('answer') and fact.get('answer').strip():
                    content = f"Q: {fact.get('question')}\nA: {fact.get('answer')}"
                    if not _try_approve_matching_pending(content, ['property_facts'], title=fact.get('question', ''), required_type='information'):
                        item_id = str(uuid.uuid4())
                        item_data = {
                            'id': item_id,
                            'propertyId': property_id,
                            'type': 'information',
                            'content': content,
                            'tags': ['setup_wizard', 'property_facts'],
                            'status': 'approved',  # Auto-approve setup wizard items
                            'createdAt': datetime.now(timezone.utc),
                            'updatedAt': datetime.now(timezone.utc)
                        }

                        try:
                            create_knowledge_item(item_id, item_data)
                            current_app.logger.info(f"Created property fact knowledge item: {fact.get('question')[:50]}...")
                        except Exception as e:
                            current_app.logger.error(f"Failed to create knowledge item for fact: {e}")

        # Generate magic link for the property when it's first activated
        from concierge.utils.firestore_client import create_property_magic_link
        magic_link_token = create_property_magic_link(property_id)
        if not magic_link_token:
            current_app.logger.warning(f"Failed to create magic link for property {property_id}")

        # Mark property as active and setup complete
        update_data = {
            'status': 'active',
            'new': False,  # No longer a new property
            'setupProgress.step5_review': True,
            'setupCompletedAt': datetime.now().isoformat(),
            'updatedAt': datetime.now().isoformat()
        }

        # Clear structured fields after converting to knowledge items to avoid duplication
        # Data is now available only through knowledge items for consistent management
        update_data['houseRules'] = []
        update_data['emergencyInfo'] = []
        update_data['propertyFacts'] = []

        # Store final setup data in property for reference
        if setup_data:
            update_data['finalSetupData'] = setup_data

        # Update the property
        if update_property(property_id, update_data):
            current_app.logger.info(f"Property setup completed for {property_id}")

            # Try to automatically sync reservations if property has an iCal URL
            reservations_sync_result = None
            try:
                property_data = get_property(property_id)  # Get fresh property data
                if property_data and property_data.get('icalUrl'):
                    current_app.logger.info(f"Automatically syncing reservations for property {property_id}")
                    from concierge.utils.reservations import sync_property_reservations
                    reservations_sync_result = sync_property_reservations(property_id)
                    if reservations_sync_result.get('success'):
                        stats = reservations_sync_result.get('stats', {})
                        current_app.logger.info(f"Reservations synced successfully: {stats.get('added', 0)} added, {stats.get('updated', 0)} updated")
                    else:
                        current_app.logger.warning(f"Reservations sync failed: {reservations_sync_result.get('error', 'Unknown error')}")
                else:
                    current_app.logger.info(f"Property {property_id} has no iCal URL, skipping reservations sync")
            except Exception as e:
                current_app.logger.warning(f"Error during automatic reservations sync for property {property_id}: {e}")

            # Calculate total knowledge items created
            house_rules_count = len([r for r in house_rules if r.get('title') and (r.get('content') or r.get('description'))])
            emergency_info_count = len([e for e in emergency_info if e.get('title')])
            property_facts_count = len([f for f in property_facts if f.get('answer') and f.get('answer').strip()])
            total_knowledge_items = house_rules_count + emergency_info_count + property_facts_count

            # Build response with optional reservations sync info
            response_data = {
                "success": True,
                "message": "Property setup completed successfully",
                "property_id": property_id,
                "knowledge_items_created": total_knowledge_items,
                "breakdown": {
                    "house_rules": house_rules_count,
                    "emergency_info": emergency_info_count,
                    "property_facts": property_facts_count
                }
            }
            
            # Add reservations sync info if it was attempted
            if reservations_sync_result:
                response_data["reservations_sync"] = reservations_sync_result

            return jsonify(response_data)
        else:
            return jsonify({"success": False, "error": "Failed to complete setup"}), 500

    except Exception as e:
        current_app.logger.error(f"Error completing property setup: {e}")
        return jsonify({"success": False, "error": "Failed to complete setup"}), 500

# === Property Magic Link Endpoints ===

@api_bp.route('/properties/<property_id>/magic-link', methods=['GET'])
@login_required
def get_property_magic_link(property_id):
    """
    Get the magic link for a property.
    """
    try:
        user_id = g.user_id

        # Get the property to verify ownership
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"success": False, "error": "Property not found or access denied"}), 404

        # Get or create magic link token
        magic_link_token = get_property_magic_link_token(property_id)
        if not magic_link_token:
            # Create magic link if it doesn't exist
            magic_link_token = create_property_magic_link(property_id)
            if not magic_link_token:
                return jsonify({"success": False, "error": "Failed to create magic link"}), 500

        # Generate the full magic link URL
        base_url = request.url_root.rstrip('/')
        magic_link_url = f"{base_url}/magic/{magic_link_token}"

        return jsonify({
            "success": True,
            "magicLinkUrl": magic_link_url,
            "token": magic_link_token
        })

    except Exception as e:
        current_app.logger.error(f"Error getting property magic link: {e}")
        return jsonify({"success": False, "error": "Failed to get magic link"}), 500

@api_bp.route('/properties/<property_id>/magic-link/qr', methods=['GET'])
@login_required
def generate_property_qr_code(property_id):
    """
    Generate and return a QR code for the property's magic link.
    """
    try:
        user_id = g.user_id

        # Get the property to verify ownership
        property_data = get_property(property_id)
        if not property_data or property_data.get('hostId') != user_id:
            return jsonify({"success": False, "error": "Property not found or access denied"}), 404

        # Get or create magic link token
        magic_link_token = get_property_magic_link_token(property_id)
        if not magic_link_token:
            magic_link_token = create_property_magic_link(property_id)
            if not magic_link_token:
                return jsonify({"success": False, "error": "Failed to create magic link"}), 500

        # Generate the full magic link URL
        base_url = request.url_root.rstrip('/')
        magic_link_url = f"{base_url}/magic/{magic_link_token}"

        # Generate QR code
        import qrcode
        from io import BytesIO
        import base64

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(magic_link_url)
        qr.make(fit=True)

        # Create QR code image
        qr_image = qr.make_image(fill_color="black", back_color="white")

        # Convert to base64 for download
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        buffer.seek(0)

        # Create response with image
        from flask import send_file
        import re

        # Clean property name for filename (remove special characters)
        property_name = property_data.get('name', 'Property')
        clean_name = re.sub(r'[^\w\s-]', '', property_name).strip()
        clean_name = re.sub(r'[-\s]+', '_', clean_name)
        filename = f"{clean_name}_QR_Code.png"

        return send_file(
            buffer,
            mimetype='image/png',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Error generating QR code: {e}")
        return jsonify({"success": False, "error": "Failed to generate QR code"}), 500

# === End Property Magic Link Endpoints ===

# === End Property Setup Endpoints ===

@api_bp.route('/gemini-rate-limit-status')
@login_required
def get_gemini_rate_limit_status():
    """Get current Gemini API rate limiting status for monitoring."""
    try:
        rate_limiter = get_gemini_rate_limiter()
        status = rate_limiter.get_status()
        
        return jsonify({
            "success": True,
            "rate_limit_status": status,
            "message": f"Using {status['current_requests']}/{status['limit']} requests per minute"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Failed to get rate limit status: {str(e)}"
        }), 500