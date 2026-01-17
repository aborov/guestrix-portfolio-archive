import os
import boto3
from dotenv import load_dotenv
import traceback
from datetime import timedelta
import google.generativeai as genai
from botocore.exceptions import ClientError
from apscheduler.schedulers.background import BackgroundScheduler

# Get the directory of the current file (config.py)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from .env file in the concierge directory
env_path = os.path.join(current_dir, '.env')
print(f"Loading environment variables from: {env_path}")
load_dotenv(dotenv_path=env_path)

# AWS Configuration
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', os.getenv('AWS_REGION', 'us-east-2'))
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
# DEPRECATED: ConciergeTable is no longer used - data migrated to Firestore
# DynamoDB is only used for conversations and websocket connections (separate tables)
# DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME', 'ConciergeTable')

# Initialize AWS resources for specific services (conversations, websockets)
try:
    dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
    dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
    # DYNAMODB_TABLE = dynamodb_resource.Table(DYNAMODB_TABLE_NAME) if DYNAMODB_TABLE_NAME else None
except Exception as e:
    print(f"Error initializing DynamoDB client: {e}")
    traceback.print_exc()
    dynamodb_client = None
    dynamodb_resource = None
    # DYNAMODB_TABLE = None

# Lambda Configuration - Removed ingestion lambda (no longer needed with Firestore)
try:
    LAMBDA_CLIENT = boto3.client('lambda', region_name=AWS_REGION)
except Exception as e:
    print(f"Error initializing Lambda client: {e}")
    traceback.print_exc()
    LAMBDA_CLIENT = None

# Application Configuration
DEBUG = os.getenv('FLASK_ENV') == 'development'
SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'default-dev-key-change-me')

# Gemini Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
GEMINI_ENABLED = bool(GEMINI_API_KEY) and os.getenv('GEMINI_ENABLED', 'True').lower() == 'true'

# Google API Configuration
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY') or GEMINI_API_KEY  # Use Gemini key as fallback

# Temporary Firebase Configuration (for transition period)
FIREBASE_API_KEY = os.getenv('FIREBASE_API_KEY')
FIREBASE_AUTH_DOMAIN = os.getenv('FIREBASE_AUTH_DOMAIN')
FIREBASE_PROJECT_ID = os.getenv('FIREBASE_PROJECT_ID')

# File Upload Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}
ALLOWED_MIME_TYPES = {
    'text/plain',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
}

# Session Configuration
SESSION_COOKIE_SECURE = os.getenv('FLASK_ENV') == 'production'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30  # 30 days in seconds

# Reservation Parsing Configuration
MAX_RESERVATION_PARSE_DAYS = int(os.getenv('MAX_RESERVATION_PARSE_DAYS', '365'))

# Print config summary for debugging
print(f"=== Configuration Summary ===")
print(f"AWS Region: {AWS_REGION}")
print(f"Primary Database: Firestore (users, properties, knowledge, reservations)")
print(f"DynamoDB: Only for conversations and websocket connections")
print(f"Lambda Client Initialized: {LAMBDA_CLIENT is not None}")
print(f"Debug Mode: {DEBUG}")
print(f"Gemini Enabled: {GEMINI_ENABLED}")
print(f"Upload Folder: {UPLOAD_FOLDER}")
print(f"Firebase API Key: {'Set' if FIREBASE_API_KEY else 'Not Set'} (temporary)")
print(f"==============================")

# --- Gemini Configuration ---
GEMINI_MODEL = None

if not GEMINI_API_KEY:
    print("WARNING: config.py - GEMINI_API_KEY environment variable not set. Q&A generation will be disabled.")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Initialize the model here if it's relatively lightweight to do so
        # Using gemini-2.5-flash-lite for better free tier limits (1000 vs 200 requests/day)
        GEMINI_MODEL = genai.GenerativeModel('gemini-2.5-flash-lite')
        print("config.py - Gemini API configured and Model initialized successfully.")
        GEMINI_ENABLED = True
    except Exception as e:
        print(f"ERROR: config.py - Could not configure Gemini API or Model: {e}")
        GEMINI_ENABLED = False

# --- APScheduler Initialization ---
# Initialize the scheduler object here, but configure jobs elsewhere (e.g., tasks module or app.py)
SCHEDULER = BackgroundScheduler(daemon=True)
print("config.py - APScheduler BackgroundScheduler initialized.")
