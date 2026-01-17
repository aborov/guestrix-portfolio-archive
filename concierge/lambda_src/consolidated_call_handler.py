import json
import os
import telnyx
import traceback
import google.generativeai as genai
# import lancedb  # Removed - migrated to Firestore for vector search
import boto3
import asyncio
import base64
import time
import logging
import sys
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr

# Add the utils directory to the path for importing ai_helpers
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import RAG functionality with fallback
rag_available = False
try:
    # Try to import the RAG functions from utils.ai_helpers
    from utils.ai_helpers import process_query_with_rag, get_relevant_context, create_base_prompt
    rag_available = True
    logger.info("Successfully imported RAG utilities from utils.ai_helpers")
except ImportError:
    # Try relative import
    try:
        from concierge.utils.ai_helpers import process_query_with_rag, get_relevant_context, create_base_prompt
        rag_available = True
        logger.info("Successfully imported RAG utilities via relative path")
    except ImportError as e:
        logger.error(f"Failed to import RAG utilities: {e}")
        logger.error("RAG functionality will be disabled")
        rag_available = False

# --- Global State Management ---
# DynamoDB tables
dynamodb_client = None
dynamodb_initialized = False
connections_table = None
connections_table_name = os.environ.get('CONNECTIONS_TABLE_NAME')

# Gemini configuration
gemini_initialized = False
GEMINI_MODEL = 'gemini-2.0-flash'

# LanceDB connection removed - migrated to Firestore for vector search
# _lancedb_connection = None
# LANCEDB_URI = os.environ.get("LANCEDB_S3_URI", "/tmp/lancedb")
# TABLE_NAME = os.environ.get("LANCEDB_TABLE_NAME", "knowledge_base")

# Active calls tracking
active_calls = {}  # Key: connection_id/stream_id -> Value: call state

# --- Telnyx Configuration ---
def configure_telnyx():
    api_key = os.environ.get('TELNYX_API_KEY')
    if api_key:
        telnyx.api_key = api_key
        logger.info("Telnyx API Key configured.")
        return True
    else:
        logger.error("TELNYX_API_KEY environment variable not set.")
        return False

# --- Gemini Configuration ---
def configure_gemini():
    global gemini_initialized
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if gemini_api_key:
        try:
            genai.configure(api_key=gemini_api_key)
            logger.info("Gemini API Key configured.")
            gemini_initialized = True
            return True
        except Exception as e:
            logger.error(f"Error configuring Gemini: {e}")
            traceback.print_exc()
            gemini_initialized = False
            return False
    else:
        logger.error("GEMINI_API_KEY environment variable not set.")
        gemini_initialized = False
        return False

# --- DynamoDB Initialization ---
def initialize_dynamodb():
    global dynamodb_client, dynamodb_initialized
    if not dynamodb_initialized:
        logger.info("Initializing DynamoDB client...")
        try:
            # Get the table name from environment variable
            table_name = os.environ.get('DYNAMODB_TABLE_NAME')
            if not table_name:
                logger.error("DYNAMODB_TABLE_NAME environment variable not set.")
                return False

            # Initialize DynamoDB client
            dynamodb_client = boto3.resource('dynamodb')
            logger.info(f"Successfully initialized DynamoDB client for table: {table_name}")
            dynamodb_initialized = True
            return True
        except Exception as e:
            logger.error(f"Unexpected error during DynamoDB setup: {e}")
            traceback.print_exc()
            dynamodb_client = None
            dynamodb_initialized = False
            return False
    else:
        # If already initialized, ensure dynamodb_client is set
        if not dynamodb_client:
            try:
                dynamodb_client = boto3.resource('dynamodb')
                logger.info("Re-initialized DynamoDB client on warm start.")
                return True
            except Exception as e:
                logger.error(f"Error re-initializing DynamoDB client on warm start: {e}")
                dynamodb_client = None
                dynamodb_initialized = False
                return False
        return True

# --- Initialize WebSocket Connections Table ---
def initialize_connections_table():
    global connections_table
    if connections_table_name:
        try:
            connections_table = boto3.resource('dynamodb').Table(connections_table_name)
            # Optional: Make a simple call to check if table exists/is accessible
            connections_table.load()
            logger.info(f"Successfully connected to DynamoDB connections table: {connections_table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to DynamoDB connections table '{connections_table_name}': {e}")
            connections_table = None
            return False
    else:
        logger.error("CONNECTIONS_TABLE_NAME environment variable not set.")
        connections_table = None
        return False

# --- Initialize All Resources ---
def initialize_resources():
    # Initialize Gemini
    configure_gemini()

    # Initialize DynamoDB
    initialize_dynamodb()

    # Initialize WebSocket connections table
    initialize_connections_table()

    # Initialize Firebase
    initialize_firebase()

# --- Event Type Detection ---
def detect_event_type(event):
    """Detect the type of event (Telnyx webhook or WebSocket)"""
    # First, check if this is a Telnyx webhook event
    if 'body' in event and isinstance(event['body'], str):
        try:
            body = json.loads(event['body'])
            if 'data' in body and 'event_type' in body.get('data', {}):
                logger.info(f"Detected Telnyx event with event_type: {body.get('data', {}).get('event_type')}")
                return 'telnyx'
        except (json.JSONDecodeError, TypeError):
            pass

    # Then check if this is a WebSocket event
    if 'requestContext' in event and 'connectionId' in event['requestContext'] and 'routeKey' in event['requestContext']:
        logger.info(f"Detected WebSocket event with routeKey: {event['requestContext'].get('routeKey')}")
        return 'websocket'

    # Log the event structure for debugging
    logger.warning(f"Could not determine event type. Event keys: {list(event.keys())}")
    if 'requestContext' in event:
        logger.warning(f"requestContext keys: {list(event['requestContext'].keys())}")

    return 'unknown'

# --- Main Lambda Handler ---
def lambda_handler(event, context):
    """
    Consolidated Lambda handler for both Telnyx webhooks and WebSocket events.
    """
    logger.info("Received event:")
    logger.debug(json.dumps(event))

    # Initialize resources
    initialize_resources()

    # Detect event type
    event_type = detect_event_type(event)
    logger.info(f"Detected event type: {event_type}")

    if event_type == 'telnyx':
        return handle_telnyx_event(event, context)
    elif event_type == 'websocket':
        return handle_websocket_event(event, context)
    else:
        logger.error(f"Unknown event type: {event_type}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Unsupported event type'})
        }

# --- Telnyx Event Handler ---
def handle_telnyx_event(event, context):
    """Handle Telnyx webhook events"""
    # Configure Telnyx (essential)
    if not configure_telnyx():
        return {'statusCode': 500, 'body': json.dumps('Internal Server Error: Telnyx not configured')}

    try:
        # Parse the event body
        if 'body' in event and isinstance(event['body'], str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
            if not isinstance(body, dict):
                body = {}

        event_data = body.get('data', {})
        event_type = event_data.get('event_type')
        payload = event_data.get('payload', {})
        call_control_id = payload.get('call_control_id')

        logger.info(f"Telnyx Event Type: {event_type}")
        logger.info(f"Call Control ID: {call_control_id}")

        # Handle different Telnyx event types
        if event_type == 'call.initiated' and payload.get('direction') == 'incoming':
            return handle_call_initiated(call_control_id, payload)
        elif event_type == 'call.answered':
            return handle_call_answered(call_control_id, payload)
        elif event_type == 'call.hangup':
            return handle_call_hangup(call_control_id, payload)
        elif event_type == 'call.cost':
            return handle_call_cost(call_control_id, payload)
        elif event_type == 'message.received':
            return handle_message_received(event_data, payload)
        else:
            logger.info(f"Received unhandled Telnyx event type: {event_type}")

        # Always return 200 OK to Telnyx to acknowledge receipt of the webhook
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Webhook received successfully"})
        }
    except Exception as e:
        logger.error(f"Error processing Telnyx event: {e}")
        traceback.print_exc()
        return {
            "statusCode": 200,  # Still return 200 to Telnyx
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Error processing webhook, but acknowledged"})
        }

def handle_call_answered(call_control_id, _):
    """Handle call.answered event from Telnyx"""
    logger.info(f"Call {call_control_id} answered. Bidirectional stream established.")

    # Update call state if it exists
    if call_control_id in active_calls:
        active_calls[call_control_id]["status"] = "answered"
        active_calls[call_control_id]["answered_timestamp"] = time.time()

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": "Call answered event acknowledged"})
    }

def handle_call_hangup(call_control_id, payload):
    """Handle call.hangup event from Telnyx"""
    hangup_cause = payload.get('hangup_cause', 'N/A')
    hangup_source = payload.get('hangup_source', 'N/A')
    logger.info(f"Call {call_control_id} hung up. Cause: {hangup_cause}, Source: {hangup_source}")

    # Clean up call state
    if call_control_id in active_calls:
        del active_calls[call_control_id]
        logger.info(f"Removed call state for {call_control_id}")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": "Call hangup event acknowledged"})
    }

def handle_call_cost(call_control_id, _):
    """Handle call.cost event from Telnyx"""
    logger.info(f"Received call.cost event for {call_control_id}.")

    # No special handling needed for cost events
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": "Call cost event acknowledged"})
    }

def handle_message_received(event_data, payload):
    """Handle message.received event from Telnyx (SMS)"""
    # Extract sender's phone number, handling both formats
    sender_number = None
    from_value = payload.get('from')
    if isinstance(from_value, str):
        sender_number = from_value
    elif isinstance(from_value, dict) and 'phone_number' in from_value:
        sender_number = from_value.get('phone_number')

    # Telnyx 'to' is a list, get the first entry
    to_entry = payload.get('to', [{}])[0]
    telnyx_to_number = None
    if isinstance(to_entry, str):
        telnyx_to_number = to_entry
    elif isinstance(to_entry, dict) and 'phone_number' in to_entry:
        telnyx_to_number = to_entry.get('phone_number')

    message_text = payload.get('text')
    message_id = event_data.get('id')  # Message ID is often outside payload

    logger.info(f"SMS From: {sender_number}, To: {telnyx_to_number}, Text: '{message_text}', Message ID: {message_id}")

    # Basic validation
    if not sender_number or not message_text:
        logger.error("Error: Missing sender number or message text in payload.")
        return {'statusCode': 400, 'body': json.dumps('Bad Request: Missing sender or text')}

    telnyx_sms_number = os.environ.get('TELNYX_SMS_NUMBER')
    if not telnyx_sms_number:
        logger.error("Error: TELNYX_SMS_NUMBER environment variable not set. Cannot send reply.")
        return {'statusCode': 500, 'body': json.dumps('Internal Server Error: Sending number not configured')}

    # Process the message with RAG and Gemini
    # This would be a good place to implement the RAG pipeline
    # For now, just send a simple response
    try:
        response_text = "Thank you for your message. We'll get back to you shortly."

        # Send response via Telnyx SMS
        telnyx.Message.create(
            to=sender_number,
            from_=telnyx_sms_number,
            text=response_text
        )
        logger.info("SMS reply sent successfully.")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Message processed and reply sent"})
        }
    except Exception as e:
        logger.error(f"Error sending Telnyx SMS reply: {e}")
        traceback.print_exc()
        return {
            "statusCode": 200,  # Still return 200 to Telnyx
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Error sending reply, but message acknowledged"})
        }

# --- WebSocket Event Handler ---
def handle_websocket_event(event, context):
    """Handle WebSocket API Gateway events"""
    # Check if connections table is available
    if connections_table is None:
        logger.error("DynamoDB connections table is not available. Cannot process WebSocket event.")
        route_key = event.get('requestContext', {}).get('routeKey')
        status_code = 200 if route_key == '$disconnect' else 500
        return {'statusCode': status_code, 'body': 'Internal server configuration error.'}

    # Use asyncio.run to handle the async logic
    return asyncio.run(_process_websocket_event(event, context))

async def _process_websocket_event(event, _):
    """Asynchronous handler for processing WebSocket events."""
    connection_id = event['requestContext'].get('connectionId')
    route_key = event['requestContext'].get('routeKey')

    # Basic check for essential context
    if not connection_id or not route_key:
        logger.error("Missing connectionId or routeKey in requestContext.")
        return {'statusCode': 400, 'body': 'Bad request: Missing connectionId or routeKey.'}

    # Get API details for response messages
    api_id = event['requestContext'].get('apiId')
    stage = event['requestContext'].get('stage')
    region = os.environ.get('AWS_REGION', 'us-east-2')  # Default to us-east-2 if not set

    # Define endpoint URL for responding to clients
    endpoint_url = f"https://{api_id}.execute-api.{region}.amazonaws.com/{stage}"

    logger.info(f"Received WebSocket event for route: {route_key} from connection: {connection_id}")

    try:
        if route_key == '$connect':
            # Extract query string parameters if any
            query_params = event.get('queryStringParameters', {}) or {}
            if query_params:
                logger.info(f"Connect query parameters: {query_params}")

            # Register the connection in DynamoDB
            try:
                connections_table.put_item(
                    Item={'connectionId': connection_id}
                )
                logger.info(f"Connection {connection_id} registered successfully.")
            except Exception as conn_err:
                logger.error(f"Failed to register connection {connection_id}: {str(conn_err)}")
                logger.error(traceback.format_exc())
                return {'statusCode': 500, 'body': 'Failed to register connection.'}

            # Successfully connected
            return {'statusCode': 200, 'body': 'Connected.'}

        elif route_key == '$disconnect':
            # Deregister the connection from DynamoDB
            try:
                connections_table.delete_item(
                    Key={'connectionId': connection_id}
                )
                logger.info(f"Connection {connection_id} deregistered successfully.")
            except Exception as del_err:
                logger.error(f"Error deregistering connection {connection_id}: {str(del_err)}")
                # Still return 200 since client is already disconnected

            return {'statusCode': 200, 'body': 'Disconnected.'}

        elif route_key == '$default':
            # Handle incoming messages from the client
            body = event.get('body', '{}')
            logger.info(f"Received message from {connection_id}: {body}")

            try:
                # Parse the message JSON
                message_data = json.loads(body)
                message_type = message_data.get('type', '')
                payload = message_data.get('payload', {})

                # Create API Gateway management client for responses
                apigw_management = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)

                # Handle different message types
                if message_type == 'auth':
                    return await handle_websocket_auth(connection_id, payload, apigw_management, message_data)
                elif message_type == 'message':
                    return await handle_websocket_message(connection_id, payload, apigw_management, message_data)
                elif message_type == 'start_call':
                    return await handle_websocket_start_call(connection_id, payload, apigw_management, message_data)
                else:
                    # Unknown message type
                    logger.warning(f"Unknown message type: {message_type}")
                    apigw_management.post_to_connection(
                        ConnectionId=connection_id,
                        Data=json.dumps({
                            "type": "error",
                            "payload": {"message": f"Unknown message type: {message_type}"},
                            "timestamp": message_data.get('timestamp', 0)
                        }).encode('utf-8')
                    )

            except json.JSONDecodeError:
                logger.error(f"Failed to parse message JSON: {body}")
                return {'statusCode': 400, 'body': 'Invalid JSON in message'}

            except Exception as e:
                logger.error(f"Error processing message: {str(e)}", exc_info=True)
                return {'statusCode': 500, 'body': f'Error processing message: {str(e)}'}

            return {'statusCode': 200, 'body': 'Message processed.'}

        else:
            logger.warning(f"Unhandled route key: {route_key}")
            return {'statusCode': 400, 'body': 'Unsupported route.'}

    except Exception as e:
        # Generic error handling for unexpected issues
        logger.error(f"Unhandled exception processing route {route_key} for connection {connection_id}: {e}", exc_info=True)
        # Return 500 for connect/default, 200 for disconnect
        status_code = 200 if route_key == '$disconnect' else 500
        return {'statusCode': status_code, 'body': f'Internal server error processing {route_key}.'}

async def handle_websocket_auth(connection_id, payload, apigw_management, message_data):
    """Handle authentication messages from WebSocket clients."""
    token = payload.get('token', '')
    property_id = payload.get('property_id', '')
    guest_name = payload.get('guest_name', '')

    logger.info(f"Auth request received with token length: {len(token) if token else 0}, property_id: {property_id}, guest_name present: {'Yes' if guest_name else 'No'}")

    # Basic validation: Check if token is present
    if not token:
        logger.warning("Auth message received without a token.")
        return {'statusCode': 401, 'body': 'Auth token missing.'}

    # Store token, property_id, and guest_name in DynamoDB
    update_expression = "set authenticated = :auth, #tkn = :token"
    expression_values = {
        ':auth': True,
        ':token': token[:20] + '...' if len(token) > 20 else token  # Truncate for security
    }

    # Define expression attribute names for reserved keywords
    expression_attribute_names = {
        '#tkn': 'token'  # Use #tkn to refer to "token" attribute
    }

    # Only add property_id if it exists in the payload
    if property_id:
        update_expression += ", property_id = :pid"
        expression_values[':pid'] = property_id

    # Add guest_name if it exists in the payload
    if guest_name:
        update_expression += ", guest_name = :gname"
        expression_values[':gname'] = guest_name

    try:
        connections_table.update_item(
            Key={'connectionId': connection_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_attribute_names
        )
        logger.info(f"Updated connection {connection_id} with auth status, property_id, and guest_name: {property_id}, {guest_name}")
    except Exception as db_err:
        logger.error(f"Failed to update DynamoDB for connection {connection_id}: {db_err}")
        traceback.print_exc()
        return {'statusCode': 500, 'body': 'Failed to store authentication details.'}

    # Send authentication success response
    apigw_management.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps({
            "type": "auth_success",
            "payload": {"message": "Authentication successful"},
            "timestamp": message_data.get('timestamp', 0)
        }).encode('utf-8')
    )
    logger.info(f"Sent auth_success to {connection_id}")

    return {'statusCode': 200, 'body': 'Authentication successful.'}

async def fetch_property_info(property_id):
    """
    Fetch property information from DynamoDB.

    Args:
        property_id (str): The ID of the property

    Returns:
        dict: Property information or None if not found
    """
    try:
        # Validate property_id
        if not property_id:
            logger.error("No property_id provided to fetch_property_info")
            return None

        # Get the DynamoDB table name from environment variable
        table_name = os.environ.get('DYNAMODB_TABLE_NAME')
        if not table_name:
            logger.error("DYNAMODB_TABLE_NAME environment variable not set. Cannot fetch property info.")
            return None

        # Initialize DynamoDB resource and table
        dynamodb_resource = boto3.resource('dynamodb')
        properties_table = dynamodb_resource.Table(table_name)

        # Query DynamoDB for property info using the correct composite key structure
        try:
            # Use the correct key structure for DynamoDB
            response = properties_table.get_item(
                Key={
                    'PK': f"PROPERTY#{property_id}",
                    'SK': "METADATA"
                }
            )
            logger.info(f"Queried DynamoDB for property {property_id} with PK=PROPERTY#{property_id}, SK=METADATA")
        except Exception as db_err:
            logger.error(f"Error querying DynamoDB for property {property_id}: {db_err}")
            traceback.print_exc()
            return None

        # Check if item exists
        if 'Item' not in response:
            logger.warning(f"Property {property_id} not found in DynamoDB")
            return None

        # Get property data
        property_data = response['Item']
        logger.info(f"Retrieved property data for {property_id}")

        # Create a comprehensive context dict with all needed fields
        # Map DynamoDB field names to the expected property context field names
        property_context = {
            'name': property_data.get('Name', f'Property {property_id}'),
            'property_id': property_id  # Always include the property_id
        }

        # Get host information - first try HostName field, then try to get actual name from HostId
        host_id = property_data.get('HostId')
        if 'HostName' in property_data:
            # If HostName is directly available, use it
            property_context['hostName'] = property_data['HostName']
            logger.info(f"Using HostName directly from property data: {property_data['HostName']}")
        elif host_id:
            # If we have a host ID, try to look up the host's name from the users table
            try:
                # Get the users table name from environment variable or use the same table
                users_table_name = os.environ.get('USERS_TABLE_NAME', table_name)
                users_table = dynamodb_resource.Table(users_table_name)

                # Query for the user with this ID
                user_response = users_table.get_item(
                    Key={
                        'PK': f"USER#{host_id}",
                        'SK': "METADATA"
                    }
                )

                if 'Item' in user_response:
                    user_data = user_response['Item']
                    # Try different possible field names for the host's name
                    host_name = user_data.get('Name', user_data.get('DisplayName', user_data.get('FullName')))
                    if host_name:
                        property_context['hostName'] = host_name
                        logger.info(f"Retrieved host name from user profile: {host_name}")
                    else:
                        # If we couldn't find a name field, use a generic name instead of the ID
                        property_context['hostName'] = "Your Host"
                        logger.info(f"No name found in user profile, using generic 'Your Host'")
                else:
                    # If user not found, use a generic name
                    property_context['hostName'] = "Your Host"
                    logger.info(f"User profile not found for host ID {host_id}, using generic 'Your Host'")
            except Exception as user_err:
                logger.error(f"Error retrieving host name for host ID {host_id}: {user_err}")
                # Fall back to a generic name instead of using the ID
                property_context['hostName'] = "Your Host"
        else:
            # If no host ID available, use generic name
            property_context['hostName'] = "Your Host"
            logger.info("No host ID available, using generic 'Your Host'")

        # Add address if available
        if 'Address' in property_data:
            property_context['address'] = property_data['Address']
            property_context['location'] = property_data['Address']

        # Add description if available
        if 'Description' in property_data:
            property_context['description'] = property_data['Description']

        # Add check-in and check-out times if available
        if 'CheckInTime' in property_data:
            property_context['checkInTime'] = property_data['CheckInTime']
        if 'CheckOutTime' in property_data:
            property_context['checkOutTime'] = property_data['CheckOutTime']

        # Add WiFi details if available
        if 'WifiDetails' in property_data:
            wifi = property_data['WifiDetails']
            if isinstance(wifi, dict):
                property_context['wifiNetwork'] = wifi.get('network', '')
                property_context['wifiPassword'] = wifi.get('password', '')

        # Try alternate field names for WiFi details
        if 'wifiDetails' in property_data:
            wifi = property_data['wifiDetails']
            if isinstance(wifi, dict):
                property_context['wifiNetwork'] = wifi.get('network', '')
                property_context['wifiPassword'] = wifi.get('password', '')

        # Add any house rules if available
        if 'Rules' in property_data:
            property_context['rules'] = property_data['Rules']

        # Log the property context fields we found
        logger.info(f"Property context fields populated: {', '.join(property_context.keys())}")

        return property_context
    except Exception as e:
        logger.error(f"Error fetching property info: {e}")
        traceback.print_exc()
        return None

async def get_conversation_history(connection_id):
    """
    Retrieve conversation history for a connection from DynamoDB.

    Args:
        connection_id (str): The WebSocket connection ID

    Returns:
        list: List of conversation messages or empty list if none found
    """
    try:
        # Get conversation history from DynamoDB
        response = connections_table.get_item(
            Key={'connectionId': connection_id},
            ProjectionExpression="conversation_history"
        )

        # Check if conversation history exists
        if 'Item' in response and 'conversation_history' in response['Item']:
            history = response['Item']['conversation_history']
            logger.info(f"Retrieved {len(history)} conversation history entries for {connection_id}")
            return history
        else:
            logger.info(f"No conversation history found for {connection_id}")
            return []
    except Exception as e:
        logger.error(f"Error retrieving conversation history: {e}")
        return []

async def store_conversation_entry(connection_id, role, text, timestamp):
    """
    Store a new conversation entry in DynamoDB.

    Args:
        connection_id (str): The WebSocket connection ID
        role (str): Either 'user' or 'assistant'
        text (str): The message text
        timestamp (str): ISO format timestamp
    """
    try:
        # Create the new message entry
        new_message = {
            'role': role,
            'text': text,
            'timestamp': timestamp
        }

        # Update the connection item with the new message appended to history
        connections_table.update_item(
            Key={'connectionId': connection_id},
            UpdateExpression="SET conversation_history = list_append(if_not_exists(conversation_history, :empty_list), :new_message)",
            ExpressionAttributeValues={
                ':empty_list': [],
                ':new_message': [new_message]
            }
        )
        logger.info(f"Stored new {role} message in conversation history for {connection_id}")
    except Exception as e:
        logger.error(f"Error storing conversation entry: {e}")
        traceback.print_exc()

async def handle_websocket_message(connection_id, payload, apigw_management, message_data):
    """Handle text messages from WebSocket clients."""
    user_message = payload.get('message', '')
    property_id = payload.get('property_id', '')
    logger.info(f"Message from client: {user_message}, property_id from payload: {property_id}")

    # Get timestamp for conversation history
    timestamp = datetime.now().isoformat()

    # If property_id not in payload, try to get from stored connection data
    guest_name = ""
    if not property_id:
        try:
            # Get property_id and guest_name from DynamoDB for this connection
            response = connections_table.get_item(
                Key={'connectionId': connection_id},
                ProjectionExpression="property_id, authenticated, #tkn, guest_name",
                ExpressionAttributeNames={
                    "#tkn": "token"  # Use #tkn to refer to "token" attribute
                }
            )
            logger.info(f"Connection data from DynamoDB: {json.dumps(response.get('Item', {}))}")

            if 'Item' in response:
                if 'property_id' in response['Item']:
                    property_id = response['Item']['property_id']
                    logger.info(f"Retrieved property_id from connection record: {property_id}")
                if 'guest_name' in response['Item']:
                    guest_name = response['Item']['guest_name']
                    logger.info(f"Retrieved guest_name from connection record: {guest_name}")
            else:
                logger.warning(f"No connection data found in DynamoDB for connection {connection_id}")
        except Exception as e:
            logger.error(f"Error retrieving data from connections table: {e}")

    # Process the message with RAG if available
    if not property_id:
        response_message = "I don't have any specific information about this property yet. It seems we're missing the property ID. Please try reconnecting or contact support."
    elif gemini_initialized and rag_available:
        try:
            # Fetch property information from DynamoDB
            property_info = await fetch_property_info(property_id)

            # If we couldn't fetch property info, use a basic context
            if not property_info:
                logger.warning(f"Could not fetch property info for property_id={property_id}. Using basic context.")
                property_info = {
                    "name": f"Property {property_id}",
                    "hostName": "Your Host",
                    "property_type": "accommodation",
                    "property_id": property_id
                }

            # Log the property info we're using
            logger.info(f"Using property info with fields: {', '.join(property_info.keys())}")

            # Retrieve conversation history for this connection
            conversation_history = await get_conversation_history(connection_id)
            logger.info(f"Retrieved {len(conversation_history)} previous messages for connection {connection_id}")

            # Process with RAG
            logger.info(f"Processing message with RAG for property_id={property_id}")
            result = process_query_with_rag(user_message, property_id, property_info, conversation_history)

            # Extract the response
            if result and 'response' in result:
                response_message = result['response']
                logger.info(f"Successfully processed query with RAG: {len(response_message)} chars")

                # Log if we used context
                if result.get('has_context'):
                    logger.info(f"Used {len(result.get('context_used', []))} context items from knowledge base")
                else:
                    logger.info("No context items were used from knowledge base")
            else:
                logger.warning("process_query_with_rag returned no response, using fallback")
                response_message = f"I received your message about {property_info.get('name', 'this property')}, but I'm having trouble finding specific information. How else can I assist you?"

            # Store the conversation entries
            await store_conversation_entry(connection_id, "user", user_message, timestamp)
            await store_conversation_entry(connection_id, "assistant", response_message, datetime.now().isoformat())

        except Exception as e:
            logger.error(f"Error processing message with RAG: {e}")
            traceback.print_exc()
            response_message = "I'm sorry, I encountered an error while processing your request. Please try again later."
    elif gemini_initialized:
        # RAG not available but Gemini is
        logger.warning("RAG not available, using Gemini fallback")
        response_message = f"I received your message about property {property_id}, but I don't have specific information about this property yet. How else can I assist you?"
    else:
        # Neither RAG nor Gemini available
        response_message = "I received your message, but I'm not able to process it at the moment. Please try again later."

    # Send response back to client
    apigw_management.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps({
            "type": "message",
            "payload": {"message": response_message},
            "timestamp": message_data.get('timestamp', 0)
        }).encode('utf-8')
    )
    logger.info(f"Sent AI response to {connection_id}")

    return {'statusCode': 200, 'body': 'Message processed.'}

async def handle_websocket_start_call(connection_id, payload, apigw_management, message_data):
    """Handle start_call messages from WebSocket clients."""
    property_id = payload.get('property_id')

    logger.info(f"Received 'start_call' from connection: {connection_id}, Property: {property_id}")

    if not property_id:
        logger.error(f"Rejecting 'start_call' from {connection_id}: Missing property_id.")
        apigw_management.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps({
                "type": "call_error",
                "payload": {"error": "Property ID is required to start a call."},
                "timestamp": message_data.get('timestamp', 0)
            }).encode('utf-8')
        )
        return {'statusCode': 400, 'body': 'Property ID is required to start a call.'}

    # In a real implementation, you would start a voice call here
    # For now, just send a success response
    apigw_management.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps({
            "type": "call_started",
            "payload": {"message": "Call started successfully"},
            "timestamp": message_data.get('timestamp', 0)
        }).encode('utf-8')
    )
    logger.info(f"Sent call_started to {connection_id}")

    return {'statusCode': 200, 'body': 'Call started.'}

# --- Telnyx Event Handlers ---
def handle_call_initiated(call_control_id, payload):
    """Handle call.initiated event from Telnyx"""
    if not call_control_id:
        logger.error("Error: call_control_id missing in call.initiated payload.")
        return {'statusCode': 400, 'body': json.dumps({'error': 'Missing call_control_id'})}

    # Extract caller's phone number
    caller_number = None
    if 'from' in payload:
        from_value = payload.get('from')
        if isinstance(from_value, str):
            caller_number = from_value
        elif isinstance(from_value, dict) and 'phone_number' in from_value:
            caller_number = from_value.get('phone_number')

    logger.info(f"Caller Phone Number: {caller_number}")

    # Check if this call is already being handled (idempotency check)
    if call_control_id in active_calls:
        logger.info(f"Call {call_control_id} is already being handled. Skipping duplicate event.")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Call already being handled"})
        }

    try:
        # Get WebSocket URL from environment
        websocket_url = os.getenv('WEBSOCKET_URL')
        if not websocket_url:
            logger.error("Error: WEBSOCKET_URL environment variable not set.")
            return {'statusCode': 500, 'body': json.dumps({'error': 'WebSocket URL not configured'})}

        # Try to find property ID for the caller
        property_id = None
        if caller_number and dynamodb_initialized:
            try:
                # Get the table name from environment variable
                table_name = os.environ.get('DYNAMODB_TABLE_NAME')
                table = dynamodb_client.Table(table_name)

                # Get current time for active reservation check
                now_utc = datetime.now(timezone.utc).isoformat()

                logger.info(f"Querying reservations for phone {caller_number} active at {now_utc}")

                # Query reservations where this phone is the primary guest phone using GSI1
                response = table.query(
                    IndexName="GSI1",
                    KeyConditionExpression=Key('GSI1PK').eq(f"PHONE#{caller_number}")
                )

                # Filter for active reservations
                active_reservations = []
                for res in response.get('Items', []):
                    start_date = res.get('StartDate')
                    end_date = res.get('EndDate')

                    if start_date and end_date and start_date <= now_utc and end_date > now_utc:
                        active_reservations.append(res)

                if len(active_reservations) >= 1:
                    res_data = active_reservations[0]
                    # Extract property_id from the PK (format: PROPERTY#{property_id})
                    pk = res_data.get('PK', '')
                    property_id = pk.replace('PROPERTY#', '') if pk.startswith('PROPERTY#') else None
                    guest_name = res_data.get('GuestName')
                    logger.info(f"Found active reservation for property ID: {property_id}, Guest: {guest_name}")
            except Exception as e:
                logger.error(f"Error finding property for caller {caller_number}: {e}")
                # Continue with no property_id

        # Append caller's phone number and property_id as query parameters
        if '?' in websocket_url:
            websocket_url += f"&caller_number={caller_number}"
        else:
            websocket_url += f"?caller_number={caller_number}"

        if property_id:
            websocket_url += f"&property_id={property_id}"

        logger.info(f"WebSocket URL with parameters: {websocket_url}")

        # Store call state before answering to prevent race conditions
        call_state = {
            "call_control_id": call_control_id,
            "caller_number": caller_number,
            "property_id": property_id,
            "status": "initiating",
            "timestamp": time.time()
        }
        active_calls[call_control_id] = call_state

        # Answer the call with enhanced bidirectional streaming configuration
        logger.info(f"Answering call {call_control_id} with bidirectional OPUS@16kHz stream...")
        response = telnyx.Call.create_answer(
            call_control_id,
            stream_url=websocket_url,
            bidirectional=True,
            stream_bidirectional_codec="OPUS",
            stream_bidirectional_sampling_rate=16000,
            stream_track="both_tracks",  # Ensure we're streaming both tracks
            client_state="gemini_voice_call"  # Add client state for tracking
        )

        # Update call state
        call_state["status"] = "answering"
        logger.info(f"Call answered successfully: {response}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Call answered successfully"})
        }
    except Exception as e:
        # Check if this is a "Call has already ended" error
        if "Call has already ended" in str(e):
            logger.warning(f"Call {call_control_id} has already ended before we could answer it.")
            # Clean up the call state
            if call_control_id in active_calls:
                del active_calls[call_control_id]
        else:
            logger.error(f"Error answering call {call_control_id}: {e}")
            traceback.print_exc()

        return {
            "statusCode": 200,  # Still return 200 to Telnyx
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Error answering call, but acknowledged"})
        }
