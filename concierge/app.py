import os
import datetime
import traceback
from functools import wraps
from dotenv import load_dotenv
import uuid
import queue
import threading
import subprocess
import sys
import json
from datetime import datetime, timezone, timedelta, date
import requests
from icalendar import Calendar, Event
import re # For extracting phone number
import logging

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, g, flash
from flask_socketio import SocketIO, emit, disconnect
from markupsafe import Markup # May be needed for templates
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from concierge.auth.utils import login_required

# --- NEW: APScheduler Imports & Setup ---
from apscheduler.schedulers.background import BackgroundScheduler
from concierge.utils.reservations import update_all_reservations
import atexit
# --- End APScheduler Imports & Setup ---

# File processing imports
import os
from werkzeug.utils import secure_filename
import magic # python-magic
import pypdf # pypdf
import docx # python-docx

# --- NEW: Import Gemini Configuration ---
from concierge.utils.gemini_config import genai_enabled, gemini_model
# --- End Gemini Import ---

# --- NEW: Import Voice Call Diagnostics ---
from concierge.utils.dynamodb_client import (
    create_voice_call_diagnostics_session,
    log_voice_call_event,
    update_voice_call_metrics,
    update_voice_call_config,
    finalize_voice_call_session,
    force_finalize_voice_call_session,
    get_voice_call_diagnostics
)
# --- End Voice Call Diagnostics Import ---

# --- NEW: Boto3 Import for Lambda Invocation ---
import boto3
from botocore.exceptions import ClientError # Import ClientError
# --- End Boto3 Import ---

# --- NEW: Import DynamoDB Client ---
# from concierge.utils.dynamodb_client import initialize_dynamodb, get_table
# --- End DynamoDB Import ---

# --- Ensure load_dotenv() is called VERY early ---
# Load .env from the correct location
load_dotenv('.env')
# --- End Early load_dotenv() ---

# --- Initialize DynamoDB ---
# NOTE: DynamoDB is no longer used for main data operations (users, properties, knowledge)
# Only kept for conversations and websocket connections (separate tables)
# try:
#     initialize_dynamodb() # Initialize DynamoDB client
#     db = get_table() # Get the table instance
#     print("app.py - DynamoDB initialized and table client obtained.")
# except Exception as e:
#     print(f"FATAL: app.py - Could not initialize DynamoDB: {e}")
#     db = None # Ensure db is None on failure
# --- End DynamoDB Initialization ---

print("app.py - Using Firestore as primary database for users, properties, knowledge, and reservations")

app = Flask(__name__)
# Import and register Blueprints
from concierge.auth.routes import auth_bp
from concierge.views.routes import views_bp
from concierge.api.routes import api_bp
from concierge.api.rag_routes import rag_bp
from concierge.api.search_routes import search_bp
from concierge.api.profile import profile_bp
from concierge.magic.routes import magic_bp
from concierge.sockets.handlers import register_socketio_handlers

app.register_blueprint(auth_bp, url_prefix='/auth') # Register with '/auth' prefix
app.register_blueprint(views_bp) # No prefix needed for main views usually
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(rag_bp, url_prefix='/api/rag')
app.register_blueprint(search_bp, url_prefix='/api/search')
app.register_blueprint(profile_bp, url_prefix='/api/profile')
app.register_blueprint(magic_bp) # No prefix needed for magic link routes

# Initialize SocketIO with threading mode for both development and production
# Threading mode is reliable across all platforms and sufficient for micro instance performance
socketio = SocketIO(
    app, 
    async_mode='threading', 
    manage_session=True, 
    cors_allowed_origins="*", 
    logger=True, 
    engineio_logger=True,
    # Resource-friendly settings for all environments
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1024*1024,  # 1MB limit
    # Additional reliability settings
    always_connect=False,
    upgrade_timeout=30
)

# Initialize SocketIO handlers
register_socketio_handlers(socketio)

app.secret_key = os.getenv('FLASK_SECRET_KEY', 'a_default_dev_secret_key_change_me')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.permanent_session_lifetime = timedelta(days=30) # Set session lifetime globally

# --- Config for Firebase (to be removed later) ---
# Firebase config is now loaded securely via API endpoints
# from concierge.utils.firebase_config import get_firebase_config
# firebase_config = get_firebase_config()
# --- End Firebase Config ---

# --- NEW: Boto3 Lambda Client Initialization (for other Lambda functions) ---
# Initialize boto3 client (can be done globally or within the function)
# Ensure your Flask app's execution environment has AWS credentials configured
# (e.g., via instance profile, environment variables, or ~/.aws/credentials)
lambda_client = None
try:
    # Use AWS_DEFAULT_REGION to match the variable in our .env file
    region_name = os.getenv("AWS_DEFAULT_REGION", os.getenv("AWS_REGION", "us-east-2"))
    lambda_client = boto3.client('lambda', region_name=region_name)
    print(f"Boto3 Lambda client initialized using region: {region_name}")
except Exception as e:
    print(f"ERROR: Could not initialize Boto3 Lambda client: {e}")
# --- End Boto3 Lambda Client Initialization ---

# Store config values in Flask app for use in other parts of the application
app.config['LAMBDA_CLIENT'] = lambda_client

# Firebase config is now loaded securely via API endpoints, not injected globally
# @app.context_processor
# def inject_firebase_config():
#     return dict(firebase_config=firebase_config)

from flask import request  # Add this import at the top if not present

@app.route('/')
def index():
    if 'user_id' in session:
        # Prevent redirect loop: if already on /dashboard, do not redirect again
        if request.path == url_for('views.dashboard'):
            app.logger.debug("User already on dashboard, not redirecting.")
            return ""
        app.logger.debug(f"User in session, redirecting to dashboard from {request.path}")
        return redirect(url_for('views.dashboard'))
    app.logger.debug(f"No user in session, redirecting to login from {request.path}")
    return redirect(url_for('auth.login'))

active_streams = {}

# === API Endpoints ===

# === API Endpoint for Deleting All Knowledge === #
@app.route('/api/properties/<string:property_id>/knowledge', methods=['DELETE'])
@login_required
def delete_all_knowledge(property_id):
    """Deletes all knowledge sources and Q&A items for a property."""
    user_id = session.get('user_id')
    user_role = session.get('role')

    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    # --- Authorization Check --- (Same as other sensitive property actions)
    try:
        # Get property from Firestore
        from concierge.utils.firestore_client import get_property
        property_data = get_property(property_id)

        if not property_data:
            return jsonify({"error": "Property not found"}), 404

        property_host_id = property_data.get('hostId')

        # Ensure only the owner host or higher roles can delete all knowledge
        if property_host_id != user_id and user_role not in ['superhost', 'admin']:
            print(f"[delete_all_knowledge] Unauthorized attempt by user {user_id} (role: {user_role}) for property {property_id}.")
            return jsonify({"error": "Unauthorized"}), 403
    except Exception as e:
        print(f"[delete_all_knowledge] Error checking authorization for property {property_id}: {e}")
        return jsonify({"error": "Error checking property ownership"}), 500
    # --- End Authorization Check ---

    print(f"[delete_all_knowledge] User {user_id} authorized. Proceeding with deletion for property {property_id}.")

    # Use Firestore for all knowledge management
    try:
        # Import the delete_all_knowledge function from firestore_client
        from concierge.utils.firestore_client import delete_all_knowledge as delete_all_knowledge_fs

        # Call the Firestore function to delete all knowledge items
        result = delete_all_knowledge_fs(property_id)

        if not result:
            return jsonify({"error": "Failed to delete knowledge from Firestore database"}), 500

        # Return success
        return jsonify({
            "success": True,
            "message": f'Successfully deleted all knowledge data for property {property_id}.'
        }), 200

    except Exception as e:
        print(f"[delete_all_knowledge] Error during deletion process for property {property_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f'An internal server error occurred during deletion: {e}'}), 500
# --- End NEW: API Endpoint for Deleting All Knowledge --- #

# --- API Endpoint for Host Properties ---
@app.route('/api/host/properties', methods=['GET'])
@login_required
def get_host_properties():
    user_id = session.get('user_id')
    user_role = session.get('user_role')

    if not user_id:
        return jsonify({"error": "User not logged in"}), 401
    if user_role != 'host':
        return jsonify({"error": "User is not a host"}), 403

    try:
        print(f"Fetching properties for host dashboard from Firestore, user: {user_id}")

        # Import list_properties_by_host from firestore_client
        from concierge.utils.firestore_client import list_properties_by_host

        # Call the function to get properties for this host from Firestore
        properties_list = list_properties_by_host(user_id)

        # Format properties for better client-side handling
        formatted_properties = []
        for prop in properties_list:
            # Firestore already includes 'id' field
            property_id = prop.get('id', '')
            if not property_id:
                continue

            formatted_prop = {
                'id': property_id,
                'name': prop.get('name', 'Unnamed Property'),
                'address': prop.get('address', ''),
                'description': prop.get('description', ''),
                'status': prop.get('status', 'active'),
                'icalUrl': prop.get('icalUrl', ''),
                'checkInTime': prop.get('checkInTime', '15:00'),
                'checkOutTime': prop.get('checkOutTime', '11:00'),
                'wifiDetails': prop.get('wifiDetails', {}),
                'hostId': prop.get('hostId', ''),
                'createdAt': prop.get('createdAt'),
                'updatedAt': prop.get('updatedAt')
            }
            formatted_properties.append(formatted_prop)

        print(f"Fetched and formatted {len(formatted_properties)} properties from Firestore for host dashboard user {user_id}")
        return jsonify(formatted_properties)

    except Exception as e:
        print(f"Error fetching properties from Firestore for host {user_id}: {e}")
        # Log the full error for debugging
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"An internal error occurred: {e}"}), 500

# File Upload Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_MIME_TYPES = {
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Import the allowed_file function from the utils module
from concierge.utils.file_helpers import allowed_file

# --- NEW: Initialize Scheduler ---
scheduler = BackgroundScheduler(daemon=True)

# --- Start Scheduler with Firestore DB check ---
try:
    # Test Firestore connection by trying to initialize it
    from concierge.utils.firestore_client import initialize_firebase
    if initialize_firebase():
        print("Firestore connection successful, starting background scheduler...")
        # Schedule the job to run on a regular interval and once on startup

        # Run every 6 hours
        scheduler.add_job(
            func=update_all_reservations,
            trigger='interval',
            hours=6,
            id='update_reservations_job',
            name='Update Reservations Every 6 Hours',
            replace_existing=True
        )

        # Schedule magic link expiration cleanup (run daily)
        from concierge.utils.firestore_client import expire_old_magic_links
        scheduler.add_job(
            func=expire_old_magic_links,
            trigger='interval',
            hours=24,
            id='expire_magic_links_job',
            name='Expire Old Magic Links Daily',
            replace_existing=True
        )

        # === NEW: Hourly missing conversation summaries job ===
        from concierge.utils.dynamodb_client import run_missing_conversation_summaries_job
        scheduler.add_job(
            func=lambda: run_missing_conversation_summaries_job(max_items=60),
            trigger='interval',
            hours=1,
            id='generate_missing_conversation_summaries_job',
            name='Generate Missing Conversation Summaries Hourly',
            replace_existing=True
        )

        # TEMPORARILY DISABLED: Run once immediately on startup with a 10-second delay to ensure DB connections are ready
        # This was causing worker timeouts during development
        # scheduler.add_job(
        #     func=update_all_reservations,
        #     trigger='date',
        #     run_date=datetime.now() + timedelta(seconds=10),
        #     id='update_reservations_startup_job',
        #     name='Update Reservations on Startup',
        #     replace_existing=True
        # )

        # Start the scheduler
        scheduler.start()

        # Shut down the scheduler when exiting the app
        atexit.register(lambda: scheduler.shutdown())
        print("Background scheduler started with reservation sync jobs.")
    else:
        print("WARNING: Firestore initialization failed. Background scheduler (e.g., for reservations) will NOT run.")
except Exception as e:
    print(f"ERROR: Could not initialize Firestore for scheduler: {e}")
    print("WARNING: Background scheduler (e.g., for reservations) will NOT run.")
# --- End Conditional Scheduler Start ---

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler('concierge.log')  # Log to file
    ]
)
# Set more verbose logging for AI operations (previously LanceDB)
logging.getLogger('concierge.utils.ai_helpers').setLevel(logging.DEBUG)

# --- API Endpoint for Property Amenities ---
@app.route('/api/properties/<string:property_id>/amenities', methods=['PUT'])
@login_required
def update_property_amenities(property_id):
    """Update amenities for a property."""
    user_id = session.get('user_id')
    user_role = session.get('user_role')

    if not user_id:
        return jsonify({"error": "User not logged in"}), 401
    if user_role != 'host':
        return jsonify({"error": "User is not a host"}), 403

    try:
        # Get the amenities data from request
        data = request.get_json()
        if not data or 'amenities' not in data:
            return jsonify({"error": "Amenities data is required"}), 400

        amenities = data['amenities']

        # Import necessary functions
        from concierge.utils.firestore_client import get_property, update_property

        # Get the current property to verify ownership
        property_data = get_property(property_id)
        if not property_data:
            return jsonify({"error": "Property not found"}), 404

        # Verify the user owns this property
        if property_data.get('hostId') != user_id:
            return jsonify({"error": "You don't have permission to modify this property"}), 403

        # Update the amenities in the property data
        property_data['amenities'] = amenities

        # Save back to Firestore
        success = update_property(property_id, property_data)
        if not success:
            return jsonify({"error": "Failed to update property amenities"}), 500

        return jsonify({
            "success": True,
            "message": "Amenities updated successfully",
            "amenities": amenities
        })

    except Exception as e:
        print(f"[update_property_amenities] Error updating amenities for property {property_id}: {e}")
        traceback.print_exc()
        return jsonify({"error": f'An internal server error occurred: {e}'}), 500

# === NEW: Manual trigger endpoint for testing missing summaries job ===
@app.route('/api/conversations/summaries/run-missing', methods=['POST'])
@login_required
def api_run_missing_summaries():
    try:
        from concierge.utils.dynamodb_client import run_missing_conversation_summaries_job
        payload = request.get_json() or {}
        max_items = int(payload.get('max_items', 40))
        results = run_missing_conversation_summaries_job(max_items=max_items)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# Add CORS headers to all responses
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.route('/health')
def health_check():
    """Health check endpoint for Elastic Beanstalk."""
    return jsonify({"status": "healthy"}), 200

# === VOICE CALL DIAGNOSTICS API ENDPOINTS ===

def check_voice_call_auth():
    """Check authentication for voice call endpoints - similar to other API endpoints"""
    user_id = session.get('user_id')
    magic_link_session = request.cookies.get('magicLinkSession')

    # Allow access for regular authenticated users or magic link users
    if not user_id and not magic_link_session:
        return None, jsonify({"error": "Authentication required"}), 401

    # Validate magic link session if present
    if magic_link_session and not user_id:
        try:
            from concierge.utils.session_manager import validate_session
            is_valid, temp_user_id, reason = validate_session(magic_link_session)
            if not is_valid:
                return None, jsonify({"error": "Invalid session"}), 401
            user_id = temp_user_id  # Use temporary user ID
        except Exception as e:
            print(f"Error validating magic link session: {e}")
            return None, jsonify({"error": "Session validation error"}), 401

    return user_id, None, None


@app.route('/api/voice-call/session/start', methods=['POST'])
def start_voice_diagnostics_session():
    """Initialize voice call diagnostics tracking"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()

        # Validate required fields
        required_fields = ['session_id', 'property_id', 'user_id']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        session_id = data['session_id']
        property_id = data['property_id']
        user_id = data['user_id']

        # Optional fields
        client_diagnostics = data.get('client_diagnostics', {})
        network_quality = data.get('network_quality', {})
        guest_name = data.get('guest_name')
        reservation_id = data.get('reservation_id')

        # Create the diagnostics session
        success = create_voice_call_diagnostics_session(
            property_id=property_id,
            user_id=user_id,
            session_id=session_id,
            client_diagnostics=client_diagnostics,
            network_quality=network_quality,
            guest_name=guest_name,
            reservation_id=reservation_id
        )

        if success:
            # Log the session start event
            log_voice_call_event(
                session_id=session_id,
                event_type='SESSION_INITIALIZED',
                details={
                    'property_id': property_id,
                    'user_id': user_id,
                    'guest_name': guest_name,
                    'reservation_id': reservation_id,
                    'client_info': {
                        'user_agent': client_diagnostics.get('userAgent', 'unknown'),
                        'browser': client_diagnostics.get('browserName', 'unknown'),
                        'platform': client_diagnostics.get('platform', 'unknown')
                    }
                }
            )

            return jsonify({'success': True, 'session_id': session_id})
        else:
            return jsonify({'error': 'Failed to create diagnostics session'}), 500

    except Exception as e:
        print(f"Error starting voice diagnostics session: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/event', methods=['POST'])
def log_voice_call_event_endpoint():
    """Log a voice call event with precise timestamp"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()

        # Validate required fields
        if 'session_id' not in data or 'event_type' not in data:
            return jsonify({'error': 'Missing required fields: session_id, event_type'}), 400

        session_id = data['session_id']
        event_type = data['event_type']
        details = data.get('details', {})
        error_info = data.get('error_info')
        warning_info = data.get('warning_info')

        # Log the event
        success = log_voice_call_event(
            session_id=session_id,
            event_type=event_type,
            details=details,
            error_info=error_info,
            warning_info=warning_info
        )

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to log event'}), 500

    except Exception as e:
        print(f"Error logging voice call event: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/metrics/update', methods=['POST'])
def update_voice_call_metrics_endpoint():
    """Update voice call quality metrics in real-time"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()

        if 'session_id' not in data or 'metrics' not in data:
            return jsonify({'error': 'Missing required fields: session_id, metrics'}), 400

        session_id = data['session_id']
        metrics = data['metrics']

        success = update_voice_call_metrics(session_id, metrics)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to update metrics'}), 500

    except Exception as e:
        print(f"Error updating voice call metrics: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/config/update', methods=['POST'])
def update_voice_call_config_endpoint():
    """Update voice call technical configuration"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()

        if 'session_id' not in data or 'config' not in data:
            return jsonify({'error': 'Missing required fields: session_id, config'}), 400

        session_id = data['session_id']
        config = data['config']

        success = update_voice_call_config(session_id, config)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to update config'}), 500

    except Exception as e:
        print(f"Error updating voice call config: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/session/end', methods=['POST'])
def end_voice_call_session():
    """Finalize voice call session with end time and final metrics"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()

        if 'session_id' not in data or 'end_reason' not in data:
            return jsonify({'error': 'Missing required fields: session_id, end_reason'}), 400

        session_id = data['session_id']
        end_reason = data['end_reason']
        final_metrics = data.get('final_metrics', {})

        # Log the session end event first
        log_voice_call_event(
            session_id=session_id,
            event_type='SESSION_ENDING',
            details={
                'end_reason': end_reason,
                'final_metrics': final_metrics
            }
        )

        # Finalize the session
        success = finalize_voice_call_session(session_id, end_reason, final_metrics)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to finalize session'}), 500

    except Exception as e:
        print(f"Error ending voice call session: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/session/finalize', methods=['POST'])
def force_finalize_voice_call_session_endpoint():
    """Guaranteed finalize endpoint: sets Status=COMPLETED and EndTime immediately.

    Intended to be called by the client right after the user presses End Call,
    before any heavier processing kicks in.
    """
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json() or {}
        session_id = data.get('session_id')
        end_reason = data.get('end_reason') or 'user_ended'
        if not session_id:
            return jsonify({'error': 'Missing required field: session_id'}), 400

        success = force_finalize_voice_call_session(session_id, end_reason)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Failed to force-finalize session'}), 500
    except Exception as e:
        print(f"Error force-finalizing voice call session: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/voice-call/get-current-time', methods=['POST'])
def get_current_time_endpoint():
    """Get current time for voice call function calling"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json() or {}
        property_context = data.get('property_context', {})
        
        # Import the get_current_time function
        from concierge.utils.ai_helpers import get_current_time
        
        # Call the function with property context
        time_result = get_current_time(property_context)
        
        return jsonify(time_result)
        
    except Exception as e:
        print(f"Error getting current time: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/voice-call/transcript', methods=['POST'])
def store_voice_transcript():
    """Store a voice call transcript"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()
        session_id = data.get('session_id')
        role = data.get('role')  # 'user' or 'assistant'
        text = data.get('text')
        timestamp = data.get('timestamp')

        if not session_id or not role or not text:
            return jsonify({'error': 'Session ID, role, and text are required'}), 400

        from concierge.utils.dynamodb_client import store_voice_call_transcript
        success = store_voice_call_transcript(session_id, role, text, timestamp)

        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to store transcript'}), 500

    except Exception as e:
        print(f"Error storing voice transcript: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/diagnostics/<session_id>')
def get_voice_call_diagnostics_endpoint(session_id):
    """Get comprehensive diagnostics for a voice call session"""
    try:
        # Try to get property_id from query parameter if provided
        property_id = request.args.get('property_id')
        diagnostics_data = get_voice_call_diagnostics(session_id, property_id)

        if not diagnostics_data:
            return jsonify({'error': 'Session not found'}), 404

        # Format the response for better client consumption
        response_data = {
            'session_info': {
                'session_id': session_id,
                'property_id': diagnostics_data.get('PropertyId'),
                'user_id': diagnostics_data.get('UserId'),
                'guest_name': diagnostics_data.get('GuestName'),
                'reservation_id': diagnostics_data.get('ReservationId'),
                'start_time': diagnostics_data.get('StartTime'),
                'end_time': diagnostics_data.get('EndTime'),
                'duration': diagnostics_data.get('Duration'),
                'status': diagnostics_data.get('Status'),
                'end_reason': diagnostics_data.get('EndReason')
            },
            'transcripts': diagnostics_data.get('Transcripts', []),
            'client_diagnostics': diagnostics_data.get('ClientDiagnostics', {}),
            'network_quality': diagnostics_data.get('NetworkQuality', {}),
            'quality_metrics': diagnostics_data.get('QualityMetrics', {}),
            'technical_config': diagnostics_data.get('TechnicalConfig', {}),
            'event_timeline': diagnostics_data.get('EventTimeline', []),
            'errors': diagnostics_data.get('Errors', []),
            'warnings': diagnostics_data.get('Warnings', []),
            'health_checks': diagnostics_data.get('HealthChecks', []),
            'final_metrics': diagnostics_data.get('FinalMetrics', {})
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"Error fetching diagnostics for session {session_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/session/fallback', methods=['POST'])
def create_fallback_voice_session():
    """Create a fallback voice call session when normal initialization fails"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()

        # Extract session data
        session_id = data.get('sessionId')
        property_id = data.get('propertyId')
        user_id = data.get('userId')
        guest_name = data.get('guestName')
        reservation_id = data.get('reservationId')
        client_diagnostics = data.get('clientDiagnostics', {})
        network_quality = data.get('networkQuality', {})
        initialization_errors = data.get('initializationErrors', [])

        if not session_id or not property_id or not user_id:
            return jsonify({'error': 'Missing required fields: sessionId, propertyId, userId'}), 400

        # Create a fallback session with special status
        from concierge.utils.dynamodb_client import create_fallback_voice_session
        success = create_fallback_voice_session(
            property_id=property_id,
            user_id=user_id,
            session_id=session_id,
            client_diagnostics=client_diagnostics,
            network_quality=network_quality,
            guest_name=guest_name,
            reservation_id=reservation_id,
            initialization_errors=initialization_errors
        )

        if success:
            return jsonify({'success': True, 'session_id': session_id, 'fallback': True})
        else:
            return jsonify({'error': 'Failed to create fallback session'}), 500

    except Exception as e:
        print(f"Error creating fallback voice session: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/voice-call/session/fallback-upload', methods=['POST'])
def upload_fallback_session_data():
    """Upload complete fallback session data including events and metrics"""
    try:
        # Check authentication
        auth_user_id, error_response, error_code = check_voice_call_auth()
        if error_response:
            return error_response, error_code

        data = request.get_json()

        session_id = data.get('sessionId')
        if not session_id:
            return jsonify({'error': 'Missing sessionId'}), 400

        # Update or create the session with all the fallback data
        from concierge.utils.dynamodb_client import update_fallback_voice_session
        success = update_fallback_voice_session(
            session_id=session_id,
            fallback_data=data
        )

        if success:
            return jsonify({'success': True, 'session_id': session_id})
        else:
            return jsonify({'error': 'Failed to upload fallback session data'}), 500

    except Exception as e:
        print(f"Error uploading fallback session data: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/test/voice-diagnostics')
def test_voice_diagnostics():
    """Test page for voice call diagnostics system"""
    return render_template('test_voice_diagnostics.html')


@app.route('/favicon.ico')
def favicon():
    """Serve favicon.ico from static directory."""
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.static_folder, 'images'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    print("For development, use: gunicorn -c gunicorn-dev.conf.py concierge.app:app")
    print("For production, use: gunicorn -c gunicorn.conf.py concierge.app:app")
    print("Starting Flask-SocketIO server with basic settings as fallback...")
    
    # Fallback for direct python execution (not recommended for production)
    debug_mode = os.getenv('FLASK_ENV') == 'development'
    port = int(os.getenv('PORT', 8081))  # Default to 8081 instead of 8082
    print(f"Using port: {port}")
    print("Using threading mode for reliable cross-platform compatibility")
    
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode, allow_unsafe_werkzeug=True)
    # For production deployment, you'd typically use Gunicorn with threading workers:
    # gunicorn --worker-class gevent -w 1 concierge.app:app
