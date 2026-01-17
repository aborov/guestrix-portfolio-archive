import os
import boto3
import logging
import uuid
import traceback
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr
from typing import Dict, List, Optional, Any, Union
from botocore.exceptions import ClientError
from decimal import Decimal
import json

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize global variables
dynamodb_client = None
dynamodb_resource = None
# DEPRECATED: ConciergeTable is no longer used - data migrated to Firestore
# DynamoDB is now only used for conversations and websocket connections
conversations_table = None
conversations_table_name = os.environ.get('CONVERSATIONS_TABLE_NAME', 'Conversations')

def initialize_dynamodb():
    """Initialize the DynamoDB client and resource for conversations only."""
    global dynamodb_client, dynamodb_resource, conversations_table

    if dynamodb_client is None:
        try:
            # Initialize both client and resource interfaces
            dynamodb_client = boto3.client('dynamodb')
            dynamodb_resource = boto3.resource('dynamodb')

            # Initialize conversations table only
            try:
                conversations_table = dynamodb_resource.Table(conversations_table_name)
                logger.info(f"DynamoDB initialized with conversations table: {conversations_table_name}")
            except Exception as conv_err:
                logger.error(f"Failed to initialize conversations table: {conv_err}")
                # Continue even if conversations table initialization fails
                # We'll create it later if needed

            return True
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB: {e}")
            return False
    return True

def store_feedback(feedback_record):
    """Store guest feedback in DynamoDB Conversations table with proper keys.

    Expected input keys (from frontend):
    - enjoyment (0-3)
    - accuracy (1-5)
    - userId
    - propertyId
    - sessionId (optional)
    - feedbackId (pre-generated in API)
    """
    try:
        initialize_dynamodb()

        if not conversations_table:
            logger.error("Conversations table not initialized")
            return False

        # Prepare canonical item with proper key schema and attribute casing
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()

        # Map incoming keys to canonical keys
        enjoyment = feedback_record.get('enjoyment')
        accuracy = feedback_record.get('accuracy')
        user_id = feedback_record.get('userId') or feedback_record.get('UserId')
        property_id = feedback_record.get('propertyId') or feedback_record.get('PropertyId')
        session_id = feedback_record.get('sessionId') or feedback_record.get('SessionId')
        feedback_id = feedback_record.get('feedbackId') or feedback_record.get('FeedbackId')

        if not property_id and session_id:
            # If only session provided, we can still write under VOICE_SESSION#
            pk = f"VOICE_SESSION#{session_id}"
            sk = f"FEEDBACK#{timestamp}"
        else:
            # Default: attach feedback to property partition
            pk = f"PROPERTY#{property_id}"
            sk = f"FEEDBACK#{timestamp}"

        item = {
            'PK': pk,
            'SK': sk,
            'EntityType': 'FEEDBACK',
            'FeedbackId': feedback_id or f"feedback_{timestamp}",
            'PropertyId': property_id,
            'UserId': user_id or 'unknown',
            'SessionId': session_id,
            'EnjoymentRating': enjoyment,
            'AccuracyRating': accuracy,
            'CreatedAt': timestamp,
            'LastUpdateTime': timestamp,
        }

        # Add a GSI to enable lookups by user
        if user_id:
            item['GSI1PK'] = f"USER#{user_id}"
            item['GSI1SK'] = timestamp

        # Optional: include original record fields for auditing
        item['RawFeedback'] = {
            k: v for k, v in feedback_record.items() if k not in ('PK', 'SK')
        }

        # Convert any float values to Decimal for DynamoDB compatibility
        item = convert_floats_to_decimal(item)

        # Store feedback record
        conversations_table.put_item(Item=item)

        logger.info(f"Feedback stored successfully: {item['FeedbackId']} under {item['PK']}|{item['SK']}")
        return True

    except Exception as e:
        logger.error(f"Error storing feedback: {e}")
        traceback.print_exc()
        return False


def attach_feedback_to_voice_session(property_id: str, session_id: str, feedback: dict) -> bool:
    """Attach feedback fields to an existing voice diagnostics session item.

    PK=PROPERTY#<property_id>, SK=VOICE_DIAGNOSTICS#<session_id>
    Adds/updates fields: FeedbackId, FeedbackEnjoymentRating, FeedbackAccuracyRating, FeedbackSubmittedAt
    """
    if not property_id or not session_id:
        return False

    if not initialize_dynamodb():
        return False

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        from datetime import datetime, timezone
        submitted_at = datetime.now(timezone.utc).isoformat()

        # Build partial update expression based on provided fields
        expr = ["#FeedbackId = :fid", "#FeedbackSubmittedAt = :ts", "#LastUpdateTime = :ts"]
        values = {':fid': feedback.get('feedbackId'), ':ts': submitted_at}
        names = {'#FeedbackId': 'FeedbackId', '#FeedbackSubmittedAt': 'FeedbackSubmittedAt', '#LastUpdateTime': 'LastUpdateTime'}
        if 'enjoyment' in feedback and feedback.get('enjoyment') is not None:
            expr.append("#FeedbackEnjoymentRating = :enjoy")
            values[':enjoy'] = feedback.get('enjoyment')
            names['#FeedbackEnjoymentRating'] = 'FeedbackEnjoymentRating'
        if 'accuracy' in feedback and feedback.get('accuracy') is not None:
            expr.append("#FeedbackAccuracyRating = :acc")
            values[':acc'] = feedback.get('accuracy')
            names['#FeedbackAccuracyRating'] = 'FeedbackAccuracyRating'

        conversations_table.update_item(
            Key={'PK': f"PROPERTY#{property_id}", 'SK': f"VOICE_DIAGNOSTICS#{session_id}"},
            UpdateExpression="SET " + ", ".join(expr),
            ExpressionAttributeValues=values,
            ExpressionAttributeNames=names
        )
        logger.info(f"Attached feedback to voice session {session_id} for property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error attaching feedback to voice session {session_id}: {e}")
        return False


def attach_feedback_to_latest_conversation(user_id: str, property_id: str, feedback: dict) -> bool:
    """Attach feedback to the most recent conversation for a user, optionally filtered by property."""
    if not user_id:
        return False


def attach_feedback_to_conversation(property_id: str, conversation_id: str, feedback: dict) -> bool:
    """Attach feedback directly to a specific conversation record.

    PK=PROPERTY#<property_id>, SK=CONVERSATION#<conversation_id>
    Adds/updates: FeedbackId, FeedbackEnjoymentRating, FeedbackAccuracyRating, FeedbackSubmittedAt
    """
    if not property_id or not conversation_id:
        return False

    if not initialize_dynamodb():
        return False

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        from datetime import datetime, timezone
        submitted_at = datetime.now(timezone.utc).isoformat()

        # Build partial update expression based on provided fields
        expr = ["#FeedbackId = :fid", "#FeedbackSubmittedAt = :ts", "#LastUpdateTime = :ts"]
        values = {':fid': feedback.get('feedbackId'), ':ts': submitted_at}
        names = {'#FeedbackId': 'FeedbackId', '#FeedbackSubmittedAt': 'FeedbackSubmittedAt', '#LastUpdateTime': 'LastUpdateTime'}
        if 'enjoyment' in feedback and feedback.get('enjoyment') is not None:
            expr.append("#FeedbackEnjoymentRating = :enjoy")
            values[':enjoy'] = feedback.get('enjoyment')
            names['#FeedbackEnjoymentRating'] = 'FeedbackEnjoymentRating'
        if 'accuracy' in feedback and feedback.get('accuracy') is not None:
            expr.append("#FeedbackAccuracyRating = :acc")
            values[':acc'] = feedback.get('accuracy')
            names['#FeedbackAccuracyRating'] = 'FeedbackAccuracyRating'

        conversations_table.update_item(
            Key={'PK': f"PROPERTY#{property_id}", 'SK': f"CONVERSATION#{conversation_id}"},
            UpdateExpression="SET " + ", ".join(expr),
            ExpressionAttributeValues=values,
            ExpressionAttributeNames=names
        )
        logger.info(f"Attached feedback to conversation {conversation_id} for property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error attaching feedback to conversation {conversation_id}: {e}")
        return False

    if not initialize_dynamodb():
        return False

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        # Query by GSI1 for latest conversations for the user
        response = conversations_table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key('GSI1PK').eq(f"USER#{user_id}"),
            Limit=25,
            ScanIndexForward=False
        )
        items = response.get('Items', [])

        # Choose the latest conversation, preferably matching propertyId if provided
        target = None
        if property_id:
            for item in items:
                if item.get('EntityType') == 'CONVERSATION' and item.get('PropertyId') == property_id:
                    target = item
                    break
        if target is None:
            for item in items:
                if item.get('EntityType') == 'CONVERSATION':
                    target = item
                    break

        if not target:
            logger.warning(f"No recent conversation found for user {user_id} to attach feedback")
            return False

        pk = target['PK']
        sk = target['SK']

        from datetime import datetime, timezone
        submitted_at = datetime.now(timezone.utc).isoformat()

        conversations_table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression=(
                "SET FeedbackId = :fid, "
                "FeedbackEnjoymentRating = :enjoy, "
                "FeedbackAccuracyRating = :acc, "
                "FeedbackSubmittedAt = :ts, "
                "LastUpdateTime = :ts"
            ),
            ExpressionAttributeValues={
                ':fid': feedback.get('feedbackId'),
                ':enjoy': feedback.get('enjoyment'),
                ':acc': feedback.get('accuracy'),
                ':ts': submitted_at,
            }
        )
        logger.info(f"Attached feedback to conversation {sk} under {pk}")
        return True
    except Exception as e:
        logger.error(f"Error attaching feedback to latest conversation for user {user_id}: {e}")
        return False

def get_conversations_table():
    """Get the DynamoDB conversations table resource."""
    if conversations_table is None:
        initialize_dynamodb()
    return conversations_table

# === DEPRECATED FUNCTIONS ===
# The following functions have been migrated to Firestore and are no longer used.
# They are kept here temporarily for reference during the migration period.

def get_user(uid: str) -> Optional[Dict]:
    """DEPRECATED: Use Firestore for user operations."""
    logger.warning("get_user() is deprecated - use Firestore for user operations")
    return None

def create_user(uid: str, user_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for user operations."""
    logger.warning("create_user() is deprecated - use Firestore for user operations")
    return False

def update_user(uid: str, update_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for user operations."""
    logger.warning("update_user() is deprecated - use Firestore for user operations")
    return False

def get_user_by_phone(phone_number: str) -> Optional[Dict]:
    """DEPRECATED: Use Firestore for user operations."""
    logger.warning("get_user_by_phone() is deprecated - use Firestore for user operations")
    return None

def get_property(property_id: str) -> Optional[Dict]:
    """DEPRECATED: Use Firestore for property operations."""
    logger.warning("get_property() is deprecated - use Firestore for property operations")
    return None

def list_all_properties() -> List[Dict]:
    """DEPRECATED: Use Firestore for property operations."""
    logger.warning("list_all_properties() is deprecated - use Firestore for property operations")
    return []

def list_properties_by_host(host_id: str) -> List[Dict]:
    """DEPRECATED: Use Firestore for property operations."""
    logger.warning("list_properties_by_host() is deprecated - use Firestore for property operations")
    return []

def create_property(property_id: str, property_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for property operations."""
    logger.warning("create_property() is deprecated - use Firestore for property operations")
    return False

def update_property(property_id: str, update_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for property operations."""
    logger.warning("update_property() is deprecated - use Firestore for property operations")
    return False

def delete_property(property_id: str) -> bool:
    """DEPRECATED: Use Firestore for property operations."""
    logger.warning("delete_property() is deprecated - use Firestore for property operations")
    return False

def create_knowledge_source(source_id: str, source_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("create_knowledge_source() is deprecated - use Firestore for knowledge operations")
    return False

def list_knowledge_sources(property_id: str) -> List[Dict]:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("list_knowledge_sources() is deprecated - use Firestore for knowledge operations")
    return []

def get_knowledge_source(source_id: str) -> Optional[Dict]:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("get_knowledge_source() is deprecated - use Firestore for knowledge operations")
    return None

def update_knowledge_source(source_id: str, update_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("update_knowledge_source() is deprecated - use Firestore for knowledge operations")
    return False

def delete_knowledge_source(source_id: str) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("delete_knowledge_source() is deprecated - use Firestore for knowledge operations")
    return False

def create_knowledge_item(item_id: str, item_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("create_knowledge_item() is deprecated - use Firestore for knowledge operations")
    return False

def list_knowledge_items_by_source(source_id: str) -> List[Dict]:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("list_knowledge_items_by_source() is deprecated - use Firestore for knowledge operations")
    return []

def list_knowledge_items_by_property(property_id: str) -> List[Dict]:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("list_knowledge_items_by_property() is deprecated - use Firestore for knowledge operations")
    return []

def delete_all_knowledge(property_id: str) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("delete_all_knowledge() is deprecated - use Firestore for knowledge operations")
    return False

def create_reservation(reservation_data: Dict) -> Optional[str]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("create_reservation() is deprecated - use Firestore for reservation operations")
    return None

def get_reservation(reservation_id: str) -> Optional[Dict]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("get_reservation() is deprecated - use Firestore for reservation operations")
    return None

def list_property_reservations(property_id: str) -> List[Dict]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("list_property_reservations() is deprecated - use Firestore for reservation operations")
    return []

def list_user_reservations(user_id: str) -> List[Dict]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("list_user_reservations() is deprecated - use Firestore for reservation operations")
    return []

def list_reservations_by_phone(phone_number: str) -> List[Dict]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("list_reservations_by_phone() is deprecated - use Firestore for reservation operations")
    return []

def get_user_reservations(user_id: str, phone_number: str = None) -> List[Dict]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("get_user_reservations() is deprecated - use Firestore for reservation operations")
    return []

def list_active_reservations() -> List[Dict]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("list_active_reservations() is deprecated - use Firestore for reservation operations")
    return []

def update_reservation_phone(reservation_id: str, phone_number: str) -> bool:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("update_reservation_phone() is deprecated - use Firestore for reservation operations")
    return False

def get_knowledge_item(item_id: str) -> Optional[Dict]:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("get_knowledge_item() is deprecated - use Firestore for knowledge operations")
    return None

def update_knowledge_item_status(item_id: str, status: str, error_message: str = None) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("update_knowledge_item_status() is deprecated - use Firestore for knowledge operations")
    return False

def update_knowledge_item(item_id: str, update_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("update_knowledge_item() is deprecated - use Firestore for knowledge operations")
    return False

def delete_knowledge_item(item_id: str) -> bool:
    """DEPRECATED: Use Firestore for knowledge operations."""
    logger.warning("delete_knowledge_item() is deprecated - use Firestore for knowledge operations")
    return False

def update_property_knowledge_status(property_id: str, status: str) -> bool:
    """DEPRECATED: Use Firestore for property operations."""
    logger.warning("update_property_knowledge_status() is deprecated - use Firestore for property operations")
    return False

def update_reservation_contacts(reservation_id: str, contacts: List[Dict]) -> bool:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("update_reservation_contacts() is deprecated - use Firestore for reservation operations")
    return False

def scan_all_reservations() -> List[Dict]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("scan_all_reservations() is deprecated - use Firestore for reservation operations")
    return []

def create_test_reservation_for_guest(phone_number: str, guest_name: str = None) -> Optional[str]:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("create_test_reservation_for_guest() is deprecated - use Firestore for reservation operations")
    return None

def update_reservation(reservation_id: str, update_data: Dict) -> bool:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("update_reservation() is deprecated - use Firestore for reservation operations")
    return False

def delete_reservation(reservation_id: str) -> bool:
    """DEPRECATED: Use Firestore for reservation operations."""
    logger.warning("delete_reservation() is deprecated - use Firestore for reservation operations")
    return False

# === ACTIVE CONVERSATION FUNCTIONS ===
# These functions remain active as conversations are still stored in DynamoDB

def create_conversation_session(property_id: str, user_id: str, guest_name: str = None, reservation_id: str = None, phone_number: str = None, channel: str = 'text_chat') -> str:
    """Create a new conversation session and return the session ID.
    
    Args:
        property_id: The property ID this conversation is for
        user_id: The user ID of the person having the conversation
        guest_name: Optional guest name (if not provided, defaults to 'Guest')
        reservation_id: Optional reservation ID to associate with this conversation
        phone_number: Optional phone number for the guest
        channel: Communication channel (default: 'text_chat')
    
    Returns:
        The conversation ID if successful, None otherwise
    """
    if not initialize_dynamodb():
        return None

    # Generate a unique conversation ID
    conversation_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info(f"Creating conversation session: property_id={property_id}, user_id={user_id}, guest_name={guest_name}, reservation_id={reservation_id}, phone_number={phone_number}")

    # Create the conversation session item
    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"CONVERSATION#{conversation_id}",
        'GSI1PK': f"USER#{user_id}",
        'GSI1SK': timestamp,
        'EntityType': 'CONVERSATION',
        'ConversationId': conversation_id,
        'PropertyId': property_id,
        'UserId': user_id,
        'GuestName': guest_name or 'Guest',
        'StartTime': timestamp,
        'CreatedAt': timestamp,
        'LastUpdateTime': timestamp,
        'Channel': channel,
        'MessageCount': 0,
        'Messages': []  # Will store the most recent messages inline
    }

    # Add reservation ID if provided
    if reservation_id:
        item['ReservationId'] = reservation_id

    # Add phone number if provided
    if phone_number:
        item['GuestPhone'] = phone_number

    try:
        conversations_table = get_conversations_table()
        if conversations_table:
            conversations_table.put_item(Item=item)
            logger.info(f"Created conversation session {conversation_id} for property {property_id}, user {user_id}, guest {item['GuestName']}, reservation {reservation_id}, phone {phone_number}")
            return conversation_id
        else:
            logger.error("Conversations table not available")
            return None
    except Exception as e:
        logger.error(f"Error creating conversation session: {e}")
        return None

def add_message_to_conversation(conversation_id: str, property_id: str, message_data: Dict) -> bool:
    """Add a message to an existing conversation.
    
    Args:
        conversation_id: The ID of the conversation to add the message to
        property_id: The property ID (needed for the DynamoDB key)
        message_data: Dict containing message info:
            - role: 'user' or 'assistant'
            - text: The message text
            - phone_number: Optional phone number for user messages
            - context_used: Optional context used for assistant responses
    
    Returns:
        True if successful, False otherwise
    """
    if not initialize_dynamodb():
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    # Import Decimal for DynamoDB compatibility
    from decimal import Decimal

    # Create the message item
    message = {
        'role': message_data.get('role'),  # 'user' or 'assistant'
        'text': message_data.get('text'),
        'timestamp': timestamp
    }

    # Add phone number if this is a user message and it's available
    if message.get('role') == 'user' and message_data.get('phone_number'):
        message['phone_number'] = message_data.get('phone_number')

    # Add context used if this is an assistant response
    if message.get('role') == 'assistant' and message_data.get('context_used'):
        # Convert any float values to Decimal for DynamoDB compatibility
        context_used = []
        for item in message_data.get('context_used', []):
            # Create a new dict with Decimal values instead of floats
            processed_item = {}
            for key, value in item.items():
                if isinstance(value, float):
                    processed_item[key] = Decimal(str(value))
                else:
                    processed_item[key] = value
            context_used.append(processed_item)

        message['context_used'] = context_used

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return False

        # Update the conversation with the new message
        response = conversations_table.update_item(
            Key={
                'PK': f"PROPERTY#{property_id}",
                'SK': f"CONVERSATION#{conversation_id}"
            },
            UpdateExpression=(
                "SET Messages = list_append(if_not_exists(Messages, :empty_list), :new_message), "
                "LastUpdateTime = :timestamp, "
                "MessageCount = if_not_exists(MessageCount, :zero) + :one, "
                "ConversationId = if_not_exists(ConversationId, :conversation_id), "
                "EntityType = if_not_exists(EntityType, :entity_type), "
                "PropertyId = if_not_exists(PropertyId, :property_id), "
                "UserId = if_not_exists(UserId, :user_id), "
                "GuestName = if_not_exists(GuestName, :guest_name), "
                "Channel = if_not_exists(Channel, :channel), "
                "StartTime = if_not_exists(StartTime, :start_time), "
                "CreatedAt = if_not_exists(CreatedAt, :start_time)"
            ),
            ExpressionAttributeValues={
                ':empty_list': [],
                ':new_message': [message],
                ':timestamp': timestamp,
                ':zero': 0,
                ':one': 1,
                ':conversation_id': conversation_id,
                ':entity_type': 'CONVERSATION',
                ':property_id': property_id,
                ':user_id': 'unknown',
                ':guest_name': 'Guest',
                ':channel': 'text_chat',
                ':start_time': timestamp
            },
            ReturnValues="UPDATED_NEW"
        )

        logger.info(f"Added message to conversation {conversation_id}, new count: {response.get('Attributes', {}).get('MessageCount', 'unknown')}")
        return True
    except Exception as e:
        logger.error(f"Error adding message to conversation {conversation_id}: {e}")
        return False

def get_conversation(conversation_id: str, property_id: str) -> Optional[Dict]:
    """Get a conversation by ID."""
    if not initialize_dynamodb():
        return None

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return None

        response = conversations_table.get_item(
            Key={
                'PK': f"PROPERTY#{property_id}",
                'SK': f"CONVERSATION#{conversation_id}"
            }
        )

        if 'Item' in response:
            return response['Item']

        logger.warning(f"Conversation {conversation_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error getting conversation {conversation_id}: {e}")
        return None

def list_property_conversations(property_id: str, limit: int = 100) -> List[Dict]:
    """List all conversations for a property."""
    if not initialize_dynamodb():
        return []

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return []

        response = conversations_table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                  Key('SK').begins_with("CONVERSATION#"),
            Limit=limit,
            ScanIndexForward=False  # Sort by most recent first
        )

        conversations = response.get('Items', [])
        logger.info(f"Retrieved {len(conversations)} conversations for property {property_id}")
        return conversations
    except Exception as e:
        logger.error(f"Error listing conversations for property {property_id}: {e}")
        return []

def list_user_conversations(user_id: str, limit: int = 100) -> List[Dict]:
    """List all conversations for a user using GSI1."""
    if not initialize_dynamodb():
        return []

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return []

        response = conversations_table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key('GSI1PK').eq(f"USER#{user_id}"),
            Limit=limit,
            ScanIndexForward=False  # Sort by most recent first
        )

        conversations = response.get('Items', [])
        logger.info(f"Retrieved {len(conversations)} conversations for user {user_id}")
        return conversations
    except Exception as e:
        logger.error(f"Error listing conversations for user {user_id}: {e}")
        return []

def update_conversation(property_id: str, conversation_id: str, update_data: Dict) -> bool:
    """Update a conversation with new data."""
    if not initialize_dynamodb():
        return False

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return False

        # Build update expression using ExpressionAttributeNames to avoid reserved keywords
        update_expression_parts = []
        expression_attribute_values = {}
        expression_attribute_names = {}

        def _name_for(attr: str) -> str:
            placeholder = f"#{attr}"
            expression_attribute_names[placeholder] = attr
            return placeholder

        for key, value in update_data.items():
            name_placeholder = _name_for(key)
            value_placeholder = f":{key.lower()}"
            update_expression_parts.append(f"{name_placeholder} = {value_placeholder}")
            expression_attribute_values[value_placeholder] = value

        # Add LastUpdateTime to the update
        name_placeholder = _name_for('LastUpdateTime')
        update_expression_parts.append(f"{name_placeholder} = :last_update_time")
        expression_attribute_values[":last_update_time"] = datetime.now(timezone.utc).isoformat()

        # Build the final update expression
        update_expression = "SET " + ", ".join(update_expression_parts)

        # Update the conversation
        response = conversations_table.update_item(
            Key={
                'PK': f"PROPERTY#{property_id}",
                'SK': f"CONVERSATION#{conversation_id}"
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues="UPDATED_NEW"
        )

        logger.info(f"Updated conversation {conversation_id} with new data: {update_data.keys()}")
        return True
    except Exception as e:
        logger.error(f"Error updating conversation {conversation_id}: {e}")
        return False

def store_conversation(conversation_data: Dict) -> Optional[str]:
    """Store a conversation in DynamoDB."""
    if not initialize_dynamodb():
        return None

    conversation_id = conversation_data.get('conversation_id')
    if not conversation_id:
        import uuid
        conversation_id = str(uuid.uuid4())

    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        'PK': f"CONVERSATION#{conversation_id}",
        'SK': f"SESSION#{timestamp}",
        'ConversationId': conversation_id,
        'PropertyId': conversation_data.get('property_id'),
        'UserId': conversation_data.get('user_id'),
        'Messages': conversation_data.get('messages', []),
        'CreatedAt': timestamp,
        'UpdatedAt': timestamp,
        'EntityType': 'CONVERSATION'
    }

    # Add optional fields
    if conversation_data.get('guest_name'):
        item['GuestName'] = conversation_data['guest_name']
    if conversation_data.get('reservation_id'):
        item['ReservationId'] = conversation_data['reservation_id']
    if conversation_data.get('phone_number'):
        item['PhoneNumber'] = conversation_data['phone_number']

    try:
        conversations_table = get_conversations_table()
        if conversations_table:
            conversations_table.put_item(Item=item)
            logger.info(f"Stored conversation {conversation_id}")
            return conversation_id
        else:
            logger.error("Conversations table not available")
        return None
    except Exception as e:
        logger.error(f"Error storing conversation: {e}")
        return None


# === HELPER FUNCTIONS FOR DYNAMODB ===

def convert_floats_to_decimal(obj):
    """Convert float values to Decimal for DynamoDB compatibility"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    else:
        return obj

# In-memory cache for voice call sessions to reduce DynamoDB scans
_voice_session_cache = {}

def _cache_voice_session(session_id: str, pk: str, sk: str):
    """Cache voice session keys for faster lookups"""
    _voice_session_cache[session_id] = {'PK': pk, 'SK': sk}

def _get_cached_voice_session(session_id: str):
    """Get cached voice session keys"""
    return _voice_session_cache.get(session_id)


# === VOICE CALL DIAGNOSTICS FUNCTIONS ===

def _write_voice_session_pointer(session_id: str, target_pk: str, target_sk: str) -> None:
    """Persist a lightweight pointer item to quickly resolve session keys without scans.

    PK:  VOICE_SESSION#<session_id>
    SK:  POINTER
    Fields: TargetPK, TargetSK
    """
    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return

        timestamp = datetime.now(timezone.utc).isoformat()
        pointer_item = {
            'PK': f"VOICE_SESSION#{session_id}",
            'SK': 'POINTER',
            'EntityType': 'VOICE_SESSION_POINTER',
            'SessionId': session_id,
            'TargetPK': target_pk,
            'TargetSK': target_sk,
            'CreatedAt': timestamp,
            'LastUpdateTime': timestamp,
        }

        # Store pointer (best-effort)
        conversations_table.put_item(Item=convert_floats_to_decimal(pointer_item))
    except Exception as e:
        logger.warning(f"Failed to write session pointer for {session_id}: {e}")

def create_voice_call_diagnostics_session(property_id: str, user_id: str, session_id: str,
                                         client_diagnostics: dict = None, network_quality: dict = None,
                                         guest_name: str = None, reservation_id: str = None) -> bool:
    """Create a voice call diagnostics session record with comprehensive tracking"""
    if not initialize_dynamodb():
        logger.error("Failed to initialize DynamoDB for voice diagnostics session")
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    # Store in your existing conversations table with enhanced structure
    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"VOICE_DIAGNOSTICS#{session_id}",
        'GSI1PK': f"USER#{user_id}",
        'GSI1SK': timestamp,
        'EntityType': 'VOICE_CALL_DIAGNOSTICS',

        # Session Info
        'SessionId': session_id,
        'PropertyId': property_id,
        'UserId': user_id,
        'GuestName': guest_name or 'Guest',
        'ReservationId': reservation_id,
        'StartTime': timestamp,
        'EndTime': None,
        'Duration': None,
        'Status': 'INITIALIZING',
        'Channel': 'voice_call',

        # Client Diagnostics (stored as nested JSON) - convert floats to Decimal
        'ClientDiagnostics': convert_floats_to_decimal(client_diagnostics or {}),
        'NetworkQuality': convert_floats_to_decimal(network_quality or {}),

        # Quality Metrics (will be updated during call)
        'QualityMetrics': {
            'ConnectionLatency': [],
            'AudioDropouts': 0,
            'TranscriptionErrors': 0,
            'InterruptionCount': 0,
            'ReconnectionCount': 0,
            'AverageResponseTime': [],
            'AudioQualityIssues': [],
            'WebSocketEvents': [],
            'MemoryUsage': [],
            'BufferUnderruns': 0,
            'BufferOverruns': 0
        },

        # Event Timeline - Critical for debugging
        'EventTimeline': [{
            'timestamp': timestamp,
            'event': 'SESSION_CREATED',
            'details': {
                'property_id': property_id,
                'user_id': user_id,
                'guest_name': guest_name,
                'reservation_id': reservation_id
            }
        }],

        # Error Tracking
        'Errors': [],
        'Warnings': [],
        'HealthChecks': [],

        # Technical Configuration
        'TechnicalConfig': {
            'GeminiModel': None,  # Will be set when call starts
            'VoiceSettings': {},
            'AudioSettings': {},
            'WebSocketUrl': None,
            'ApiKeyType': None  # 'ephemeral' or 'direct'
        },

        # Metadata
        'CreatedAt': timestamp,
        'LastUpdateTime': timestamp,
        'MessageCount': 0
    }

    try:
        conversations_table = get_conversations_table()
        if conversations_table:
            conversations_table.put_item(Item=item)
            # Cache the session keys for faster lookups
            _cache_voice_session(session_id, item['PK'], item['SK'])
            # Also persist a pointer to avoid scans in subsequent updates
            _write_voice_session_pointer(session_id, item['PK'], item['SK'])
            logger.info(f"Created voice call diagnostics session {session_id} for property {property_id}")
            return True
        else:
            logger.error("Conversations table not available for voice diagnostics")
            return False
    except Exception as e:
        logger.error(f"Error creating voice diagnostics session {session_id}: {e}")
        return False


def log_voice_call_event(session_id: str, event_type: str, details: dict = None,
                        error_info: dict = None, warning_info: dict = None) -> bool:
    """Log a voice call event with precise timestamp - ensures data is saved even if session fails"""
    if not initialize_dynamodb():
        logger.error(f"Failed to initialize DynamoDB for voice event logging: {event_type}")
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available for voice event logging")
            return False

        # Create the event record - convert floats to Decimal
        event_record = {
            'timestamp': timestamp,
            'event': event_type,
            'details': convert_floats_to_decimal(details or {})
        }

        # Prepare update expression components
        update_expressions = []
        expression_values = {}

        # Always update the event timeline
        update_expressions.append("EventTimeline = list_append(if_not_exists(EventTimeline, :empty_list), :new_event)")
        expression_values[':empty_list'] = []
        expression_values[':new_event'] = [event_record]

        # Update last update time
        update_expressions.append("LastUpdateTime = :timestamp")
        expression_values[':timestamp'] = timestamp

        # Handle errors
        if error_info:
            error_record = {
                'timestamp': timestamp,
                'event': event_type,
                'error': convert_floats_to_decimal(error_info)
            }
            update_expressions.append("Errors = list_append(if_not_exists(Errors, :empty_list), :new_error)")
            expression_values[':new_error'] = [error_record]

        # Handle warnings
        if warning_info:
            warning_record = {
                'timestamp': timestamp,
                'event': event_type,
                'warning': convert_floats_to_decimal(warning_info)
            }
            update_expressions.append("Warnings = list_append(if_not_exists(Warnings, :empty_list), :new_warning)")
            expression_values[':new_warning'] = [warning_record]

        # Update status based on event type
        if event_type in ['CALL_STARTED', 'WEBSOCKET_CONNECTED']:
            update_expressions.append("#status = :active_status")
            expression_values[':active_status'] = 'ACTIVE'
        elif event_type in ['CALL_ENDED', 'CALL_FAILED', 'WEBSOCKET_CLOSED_UNEXPECTED']:
            update_expressions.append("#status = :ended_status")
            if event_type == 'CALL_FAILED':
                expression_values[':ended_status'] = 'FAILED'
            else:
                expression_values[':ended_status'] = 'ENDED'

            # Set end time
            update_expressions.append("EndTime = :timestamp")

        # Try to find and update the diagnostics record
        # First check cache, then fall back to scan if needed
        try:
            cached_keys = _get_cached_voice_session(session_id)

            if cached_keys:
                # Use cached keys for direct access
                pk = cached_keys['PK']
                sk = cached_keys['SK']
                response = {'Items': [{'PK': pk, 'SK': sk}]}
            else:
                # Fall back to scan (with reduced frequency)
                response = conversations_table.scan(
                    FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
                    Limit=50  # Reduced limit to save throughput
                )

                # Cache the result if found
                if response['Items']:
                    item = response['Items'][0]
                    _cache_voice_session(session_id, item['PK'], item['SK'])

            if response['Items']:
                item = response['Items'][0]
                pk = item['PK']
                sk = item['SK']

                # Build the update expression
                update_expression = "SET " + ", ".join(update_expressions)
                expression_attribute_names = {}
                if '#status' in update_expression:
                    expression_attribute_names['#status'] = 'Status'

                # Perform the update
                update_params = {
                    'Key': {'PK': pk, 'SK': sk},
                    'UpdateExpression': update_expression,
                    'ExpressionAttributeValues': expression_values
                }

                # Only add ExpressionAttributeNames if we have any
                if expression_attribute_names:
                    update_params['ExpressionAttributeNames'] = expression_attribute_names

                conversations_table.update_item(**update_params)

                logger.info(f"Logged voice call event {event_type} for session {session_id}")
                return True
            else:
                logger.warning(f"Voice diagnostics session {session_id} not found for event {event_type}")
                # Create a minimal record to ensure we don't lose the event
                return create_minimal_voice_session_record(session_id, event_type, event_record, error_info, warning_info)

        except Exception as query_error:
            logger.error(f"Error querying for voice session {session_id}: {query_error}")
            # Try to create a minimal record as fallback
            return create_minimal_voice_session_record(session_id, event_type, event_record, error_info, warning_info)

    except Exception as e:
        logger.error(f"Error logging voice call event {event_type} for session {session_id}: {e}")
        return False


def create_minimal_voice_session_record(session_id: str, event_type: str, event_record: dict,
                                       error_info: dict = None, warning_info: dict = None) -> bool:
    """Create a minimal voice session record when the main session doesn't exist - ensures no data loss"""
    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        timestamp = datetime.now(timezone.utc).isoformat()

        # Create minimal record to preserve the event
        minimal_item = {
            'PK': f"VOICE_SESSION#{session_id}",
            'SK': f"MINIMAL_RECORD#{timestamp}",
            'GSI1PK': f"SESSION#{session_id}",
            'GSI1SK': timestamp,
            'EntityType': 'VOICE_CALL_MINIMAL',
            'SessionId': session_id,
            'Status': 'UNKNOWN',
            'StartTime': timestamp,
            'EventTimeline': [event_record],
            'Errors': [{'timestamp': timestamp, 'event': event_type, 'error': error_info}] if error_info else [],
            'Warnings': [{'timestamp': timestamp, 'event': event_type, 'warning': warning_info}] if warning_info else [],
            'CreatedAt': timestamp,
            'LastUpdateTime': timestamp,
            'Note': f'Minimal record created for event {event_type} - original session record not found'
        }

        conversations_table.put_item(Item=minimal_item)
        # Persist/update pointer to latest minimal record
        _write_voice_session_pointer(session_id, minimal_item['PK'], minimal_item['SK'])
        logger.warning(f"Created minimal voice session record for {session_id} due to missing main record")
        return True

    except Exception as e:
        logger.error(f"Failed to create minimal voice session record for {session_id}: {e}")
        return False


def update_voice_call_metrics(session_id: str, metrics_update: dict) -> bool:
    """Update voice call quality metrics in real-time"""
    if not initialize_dynamodb():
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        # Find the diagnostics record
        response = conversations_table.scan(
            FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS')
        )

        if not response['Items']:
            logger.warning(f"Voice diagnostics session {session_id} not found for metrics update")
            return False

        item = response['Items'][0]
        pk = item['PK']
        sk = item['SK']

        # Build update expression for metrics
        update_expressions = []
        expression_values = {}

        # Update quality metrics - convert floats to Decimal
        if 'QualityMetrics' in metrics_update:
            for metric_key, metric_value in metrics_update['QualityMetrics'].items():
                converted_value = convert_floats_to_decimal(metric_value)
                if isinstance(metric_value, list):
                    # For array metrics, append to existing
                    update_expressions.append(f"QualityMetrics.{metric_key} = list_append(if_not_exists(QualityMetrics.{metric_key}, :empty_list), :{metric_key})")
                    expression_values[f':{metric_key}'] = converted_value
                else:
                    # For scalar metrics, set value
                    update_expressions.append(f"QualityMetrics.{metric_key} = :{metric_key}")
                    expression_values[f':{metric_key}'] = converted_value

        # Add empty list default
        expression_values[':empty_list'] = []

        # Update timestamp
        update_expressions.append("LastUpdateTime = :timestamp")
        expression_values[':timestamp'] = timestamp

        # Perform the update
        update_expression = "SET " + ", ".join(update_expressions)

        conversations_table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

        logger.debug(f"Updated voice call metrics for session {session_id}")
        return True

    except Exception as e:
        logger.error(f"Error updating voice call metrics for session {session_id}: {e}")
        return False


def update_voice_call_config(session_id: str, config_update: dict) -> bool:
    """Update voice call technical configuration"""
    if not initialize_dynamodb():
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        # Helper to build update expression values
        def _build_update_parts(cfg: dict):
            update_expressions_local = []
            expression_values_local = {}
            # Accept either { 'TechnicalConfig': {...} } or a flat config dict
            effective_cfg = cfg.get('TechnicalConfig') if isinstance(cfg, dict) and 'TechnicalConfig' in cfg else cfg
            if isinstance(effective_cfg, dict):
                for config_key, config_value in effective_cfg.items():
                    update_expressions_local.append(f"TechnicalConfig.{config_key} = :{config_key}")
                    expression_values_local[f":{config_key}"] = convert_floats_to_decimal(config_value)
            update_expressions_local.append("LastUpdateTime = :timestamp")
            expression_values_local[":timestamp"] = timestamp
            return update_expressions_local, expression_values_local

        # Try pointer, then cache, then scan for VOICE_CALL_DIAGNOSTICS
        pk = sk = None
        try:
            # 1) Try persistent pointer (fast get_item)
            try:
                ptr_resp = conversations_table.get_item(
                    Key={'PK': f"VOICE_SESSION#{session_id}", 'SK': 'POINTER'}
                )
                ptr = ptr_resp.get('Item')
                if ptr and ptr.get('TargetPK') and ptr.get('TargetSK'):
                    pk = ptr['TargetPK']
                    sk = ptr['TargetSK']
            except Exception as pointer_err:
                logger.debug(f"No pointer for session {session_id} or pointer lookup failed: {pointer_err}")

            # 2) Fallback to in-memory cache
            cached_keys = _get_cached_voice_session(session_id)
            if cached_keys:
                pk = cached_keys['PK']
                sk = cached_keys['SK']
            # 3) Last resort: scan diagnostics
            if not pk or not sk:
                response = conversations_table.scan(
                    FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
                    Limit=50
                )
                if response.get('Items'):
                    item = response['Items'][0]
                    pk = item['PK']
                    sk = item['SK']
                    _cache_voice_session(session_id, pk, sk)
                    # Update pointer for next time
                    _write_voice_session_pointer(session_id, pk, sk)
        except Exception as lookup_err:
            logger.error(f"Error looking up diagnostics session {session_id}: {lookup_err}")

        if pk and sk:
            update_expressions, expression_values = _build_update_parts(config_update)
            update_expression = "SET " + ", ".join(update_expressions)
            conversations_table.update_item(
                Key={'PK': pk, 'SK': sk},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            logger.debug(f"Updated voice call config for session {session_id}")
            return True

        # Fallback: try VOICE_CALL_MINIMAL record
        try:
            response_min = conversations_table.scan(
                FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_MINIMAL'),
                Limit=50
            )
            items_min = response_min.get('Items', [])
            if items_min:
                # Pick latest by GSI1SK or CreatedAt
                latest_min = max(items_min, key=lambda it: it.get('GSI1SK', it.get('CreatedAt', '')))
                pk = latest_min['PK']
                sk = latest_min['SK']
                update_expressions, expression_values = _build_update_parts(config_update)
                update_expression = "SET " + ", ".join(update_expressions)
                conversations_table.update_item(
                    Key={'PK': pk, 'SK': sk},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values
                )
                logger.info(f"Diagnostics not found; updated minimal record with config for session {session_id}")
                return True
        except Exception as min_err:
            logger.error(f"Error updating minimal record for session {session_id}: {min_err}")

        # Last resort: create a minimal record and attach config
        try:
            event_record = {
                'timestamp': timestamp,
                'event': 'CONFIG_UPDATE',
                'details': convert_floats_to_decimal({'config_update': config_update.get('TechnicalConfig', {})})
            }
            created = create_minimal_voice_session_record(session_id, 'CONFIG_UPDATE', event_record)
            if created:
                # Find the newly created minimal record and update it
                response_min2 = conversations_table.scan(
                    FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_MINIMAL'),
                    Limit=50
                )
                items_min2 = response_min2.get('Items', [])
                if items_min2:
                    latest_min2 = max(items_min2, key=lambda it: it.get('GSI1SK', it.get('CreatedAt', '')))
                    pk = latest_min2['PK']
                    sk = latest_min2['SK']
                    update_expressions, expression_values = _build_update_parts(config_update)
                    update_expression = "SET " + ", ".join(update_expressions)
                    conversations_table.update_item(
                        Key={'PK': pk, 'SK': sk},
                        UpdateExpression=update_expression,
                        ExpressionAttributeValues=expression_values
                    )
                    logger.info(f"Created minimal record and stored config for session {session_id}")
                    return True
        except Exception as create_min_err:
            logger.error(f"Failed to create minimal record for session {session_id}: {create_min_err}")

        logger.warning(f"Voice call session {session_id} not found for config update and no minimal record present")
        return False

    except Exception as e:
        logger.error(f"Error updating voice call config for session {session_id}: {e}")
        return False


def finalize_voice_call_session(session_id: str, end_reason: str, final_metrics: dict = None) -> bool:
    """Finalize voice call session with end time, duration, and final metrics"""
    if not initialize_dynamodb():
        return False

    end_time = datetime.now(timezone.utc).isoformat()

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        # Find the diagnostics record using cache first
        cached_keys = _get_cached_voice_session(session_id)

        if cached_keys:
            # Use cached keys for direct access
            pk = cached_keys['PK']
            sk = cached_keys['SK']

            # Get the item to calculate duration
            try:
                response = conversations_table.get_item(Key={'PK': pk, 'SK': sk})
                if 'Item' not in response:
                    logger.warning(f"Voice diagnostics session {session_id} not found in cache lookup")
                    return False
                item = response['Item']
            except Exception as get_error:
                logger.error(f"Error getting cached session {session_id}: {get_error}")
                return False
        else:
            # Fall back to scan (with reduced frequency)
            response = conversations_table.scan(
                FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
                Limit=50
            )

            if not response['Items']:
                logger.warning(f"Voice diagnostics session {session_id} not found for finalization")
                return False

            item = response['Items'][0]
            pk = item['PK']
            sk = item['SK']

            # Cache for future use
            _cache_voice_session(session_id, pk, sk)

        # Calculate duration if we have start time
        duration = None
        if 'StartTime' in item:
            try:
                start_time = datetime.fromisoformat(item['StartTime'].replace('Z', '+00:00'))
                end_time_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                duration = int((end_time_dt - start_time).total_seconds())
            except Exception as duration_error:
                logger.warning(f"Could not calculate duration for session {session_id}: {duration_error}")

        # Determine final status based on end reason and session quality
        def determine_session_status(end_reason, final_metrics):
            """Determine if a session should be marked as COMPLETED or FAILED"""
            # Successful end reasons
            successful_reasons = [
                'normal',
                'User ended call',
                'user_ended',
                'completed',
                'success'
            ]

            # Check if end reason indicates success
            if end_reason.lower() in [r.lower() for r in successful_reasons]:
                # Additional quality checks from final metrics
                if final_metrics:
                    total_errors = final_metrics.get('totalErrors', final_metrics.get('total_errors', 0))
                    total_warnings = final_metrics.get('totalWarnings', final_metrics.get('total_warnings', 0))

                    # If there are no errors and minimal warnings, consider it successful
                    if total_errors == 0 and total_warnings <= 2:
                        return 'COMPLETED'
                    elif total_errors > 0:
                        return 'FAILED'
                    else:
                        return 'COMPLETED'  # Minor warnings are acceptable
                else:
                    # No metrics available, but end reason suggests success
                    return 'COMPLETED'

            # Failed end reasons
            failed_reasons = [
                'error',
                'timeout',
                'connection_lost',
                'api_error',
                'initialization_failed'
            ]

            if end_reason.lower() in [r.lower() for r in failed_reasons]:
                return 'FAILED'

            # Default to COMPLETED for unknown but non-error reasons
            return 'COMPLETED'

        final_status = determine_session_status(end_reason, final_metrics)

        # Build update expression
        update_expressions = [
            "EndTime = :end_time",
            "LastUpdateTime = :end_time",
            "#status = :final_status",
            "EndReason = :end_reason"
        ]

        expression_values = {
            ':end_time': end_time,
            ':final_status': final_status,
            ':end_reason': end_reason
        }

        expression_attribute_names = {
            '#status': 'Status'
        }

        if duration is not None:
            update_expressions.append("#duration = :duration")
            expression_values[':duration'] = duration
            expression_attribute_names['#duration'] = 'Duration'

        # Add final metrics if provided - convert floats to Decimal
        final_metrics_converted = None
        if final_metrics:
            # Set the entire FinalMetrics object at once to avoid path overlap
            final_metrics_converted = convert_floats_to_decimal(final_metrics)
            update_expressions.append("FinalMetrics = :final_metrics")
            expression_values[':final_metrics'] = final_metrics_converted

        # Add final event to timeline - use converted metrics to avoid float issues
        final_event = {
            'timestamp': end_time,
            'event': 'SESSION_FINALIZED',
            'details': {
                'end_reason': end_reason,
                'duration': duration,
                'final_metrics': final_metrics_converted or {}
            }
        }

        update_expressions.append("EventTimeline = list_append(if_not_exists(EventTimeline, :empty_list), :final_event)")
        expression_values[':empty_list'] = []
        expression_values[':final_event'] = [convert_floats_to_decimal(final_event)]

        # Perform the update
        update_expression = "SET " + ", ".join(update_expressions)

        update_params = {
            'Key': {'PK': pk, 'SK': sk},
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_values
        }

        # Only add ExpressionAttributeNames if we have any
        if expression_attribute_names:
            update_params['ExpressionAttributeNames'] = expression_attribute_names

        conversations_table.update_item(**update_params)

        logger.info(f"Finalized voice call session {session_id} with reason: {end_reason}, status: {final_status}, duration: {duration}s")
        # Trigger background summary generation (best-effort)
        try:
            generate_and_store_session_summary_async(session_id, pk, sk)
        except Exception as bg_err:
            logger.warning(f"Failed to trigger background summary generation for {session_id}: {bg_err}")
        return True

    except Exception as e:
        logger.error(f"Error finalizing voice call session {session_id}: {e}")
        return False


def force_finalize_voice_call_session(session_id: str, end_reason: str = 'user_ended') -> bool:
    """Guaranteed, minimal finalization: set Status=COMPLETED and EndTime now.

    - Computes Duration if StartTime exists
    - Appends a minimal SESSION_FINALIZED event
    - Does not attempt summary generation or heavy processing
    """
    if not initialize_dynamodb():
        return False

    end_time = datetime.now(timezone.utc).isoformat()

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return False

        # Find cached keys or scan
        cached_keys = _get_cached_voice_session(session_id)
        pk = sk = None
        item = None
        if cached_keys:
            pk = cached_keys['PK']
            sk = cached_keys['SK']
            try:
                resp = conversations_table.get_item(Key={'PK': pk, 'SK': sk})
                item = resp.get('Item')
            except Exception:
                item = None
        if not item:
            response = conversations_table.scan(
                FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
                Limit=50
            )
            if not response.get('Items'):
                logger.warning(f"Voice diagnostics session {session_id} not found for force finalization")
                return False
            item = response['Items'][0]
            pk = item['PK']
            sk = item['SK']
            _cache_voice_session(session_id, pk, sk)

        # Calculate duration if possible
        duration = None
        if 'StartTime' in item:
            try:
                start_time = datetime.fromisoformat(item['StartTime'].replace('Z', '+00:00'))
                end_time_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                duration = int((end_time_dt - start_time).total_seconds())
            except Exception:
                pass

        # Build minimal update
        update_expressions = [
            'EndTime = :end_time',
            'LastUpdateTime = :end_time',
            '#status = :completed',
            'EndReason = :end_reason'
        ]
        expr_vals = {
            ':end_time': end_time,
            ':completed': 'COMPLETED',
            ':end_reason': end_reason
        }
        expr_names = {'#status': 'Status'}
        if duration is not None:
            update_expressions.append('#duration = :duration')
            expr_vals[':duration'] = duration
            expr_names['#duration'] = 'Duration'

        # Append minimal final event
        final_event = {
            'timestamp': end_time,
            'event': 'SESSION_FINALIZED_MINIMAL',
            'details': {
                'end_reason': end_reason
            }
        }
        update_expressions.append('EventTimeline = list_append(if_not_exists(EventTimeline, :empty_list), :final_event)')
        expr_vals[':empty_list'] = []
        expr_vals[':final_event'] = [convert_floats_to_decimal(final_event)]

        update_expression = 'SET ' + ', '.join(update_expressions)
        conversations_table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expr_vals,
            ExpressionAttributeNames=expr_names
        )

        logger.info(f"Force-finalized voice session {session_id} as COMPLETED")
        return True
    except Exception as e:
        logger.error(f"Error in force-finalizing session {session_id}: {e}")
        return False

def generate_and_store_session_summary_async(session_id: str, pk: str, sk: str) -> None:
    """Spawn a background thread to generate and persist an AI summary for the session."""
    try:
        import threading

        def _worker():
            try:
                conversations_table = get_conversations_table()
                if not conversations_table:
                    return

                # Load the item
                response = conversations_table.get_item(Key={'PK': pk, 'SK': sk})
                item = response.get('Item')
                if not item:
                    return

                # Skip if already summarized
                if item.get('AISummary'):
                    return

                # Build messages list from transcripts for voice sessions
                messages = []
                transcripts = item.get('Transcripts', [])
                for t in transcripts:
                    messages.append({'role': t.get('role', ''), 'text': t.get('text', '')})

                # Fallback to Messages for text chat (defensive)
                if not messages and item.get('Messages'):
                    for m in item['Messages']:
                        messages.append({'role': m.get('role', ''), 'text': m.get('text') or m.get('content', '')})

                if not messages:
                    return

                # Optionally include property context
                property_context = None
                try:
                    from concierge.utils.firestore_client import get_property as fs_get_property
                    property_context = fs_get_property(item.get('PropertyId'))
                except Exception:
                    pass

                # Generate summary
                from concierge.utils.ai_helpers import generate_conversation_summary
                ai_summary = generate_conversation_summary(
                    messages=messages,
                    property_context=property_context,
                    reservation_info=None,
                    guest_name=item.get('GuestName')
                )

                if not ai_summary:
                    return

                # Persist summary on the session record
                conversations_table.update_item(
                    Key={'PK': pk, 'SK': sk},
                    UpdateExpression='SET AISummary = :summary, LastUpdateTime = :ts',
                    ExpressionAttributeValues={
                        ':summary': ai_summary,
                        ':ts': datetime.now(timezone.utc).isoformat()
                    }
                )
                logger.info(f"Stored AI summary for session {session_id} ({len(ai_summary)} chars)")
            except Exception as worker_err:
                logger.warning(f"AI summary generation worker failed for {session_id}: {worker_err}")

        threading.Thread(target=_worker, daemon=True).start()
    except Exception as e:
        logger.warning(f"Could not start AI summary generation thread for {session_id}: {e}")


def store_voice_call_transcript(session_id: str, role: str, text: str, timestamp: str = None) -> bool:
    """Store a voice call transcript in the diagnostics session record"""
    if not initialize_dynamodb():
        logger.error(f"Failed to initialize DynamoDB for transcript storage")
        return False

    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available for transcript storage")
            return False

        # Try cache first for session keys
        cached_keys = _get_cached_voice_session(session_id)

        if cached_keys:
            # Use cached keys for direct access
            pk = cached_keys['PK']
            sk = cached_keys['SK']
        else:
            # Fall back to scan to find the session
            response = conversations_table.scan(
                FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
                Limit=50
            )

            if not response['Items']:
                logger.warning(f"Voice diagnostics session {session_id} not found for transcript storage")

                # Try to create an automatic fallback session
                logger.info(f"Attempting to create automatic fallback session for transcript storage: {session_id}")

                # Extract property_id from session_id if it follows the temp-timestamp pattern
                # For now, we'll create a minimal session without property_id
                fallback_created = create_minimal_voice_session_record(
                    session_id=session_id,
                    event_type='TRANSCRIPT_STORAGE_ATTEMPT',
                    event_record={
                        'timestamp': timestamp,
                        'event': 'TRANSCRIPT_STORAGE_ATTEMPT',
                        'details': {'role': role, 'text': text[:100]}
                    },
                    error_info={'message': 'Session not found, creating automatic fallback'},
                    warning_info=None
                )

                if fallback_created:
                    logger.info(f"Created automatic fallback session for {session_id}")
                    # Try to find the newly created session
                    response = conversations_table.scan(
                        FilterExpression=Attr('SessionId').eq(session_id),
                        Limit=10
                    )

                    if response['Items']:
                        item = response['Items'][0]
                        pk = item['PK']
                        sk = item['SK']
                        # Cache for future use
                        _cache_voice_session(session_id, pk, sk)
                    else:
                        logger.error(f"Failed to find newly created fallback session {session_id}")
                        return False
                else:
                    logger.error(f"Failed to create automatic fallback session for {session_id}")
                    return False
            else:
                item = response['Items'][0]
                pk = item['PK']
                sk = item['SK']
                # Cache for future use
                _cache_voice_session(session_id, pk, sk)

        # Create transcript entry
        transcript_entry = {
            'role': role,
            'text': text,
            'timestamp': timestamp
        }

        # Update the session with the new transcript
        update_params = {
            'Key': {'PK': pk, 'SK': sk},
            'UpdateExpression': 'SET Transcripts = list_append(if_not_exists(Transcripts, :empty_list), :transcript)',
            'ExpressionAttributeValues': {
                ':empty_list': [],
                ':transcript': [convert_floats_to_decimal(transcript_entry)]
            }
        }

        conversations_table.update_item(**update_params)
        logger.info(f"Stored transcript for session {session_id}: {role} - {text[:50]}...")
        return True

    except Exception as e:
        logger.error(f"Error storing transcript for session {session_id}: {e}")
        return False


def get_voice_call_diagnostics(session_id: str, property_id: str = None) -> Optional[Dict]:
    """Retrieve comprehensive diagnostics for a voice call session"""
    if not initialize_dynamodb():
        return None

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            return None

        # Try cache first
        cached_keys = _get_cached_voice_session(session_id)

        if cached_keys:
            # Use cached keys for direct access
            try:
                response = conversations_table.get_item(
                    Key={'PK': cached_keys['PK'], 'SK': cached_keys['SK']}
                )
                if 'Item' in response:
                    return response['Item']
            except Exception as get_error:
                logger.error(f"Error getting cached diagnostics {session_id}: {get_error}")

        # Fall back to scan
        response = conversations_table.scan(
            FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
            Limit=50
        )

        if not response['Items']:
            # Try to construct the keys directly if we have property_id
            if property_id:
                pk = f"PROPERTY#{property_id}"
                sk = f"VOICE_DIAGNOSTICS#{session_id}"
                try:
                    response = conversations_table.get_item(Key={'PK': pk, 'SK': sk})
                    if 'Item' in response:
                        item = response['Item']
                        # Cache for future use
                        _cache_voice_session(session_id, pk, sk)
                        return item
                except Exception as direct_error:
                    logger.error(f"Error with direct key construction for {session_id}: {direct_error}")

            logger.warning(f"Voice diagnostics session {session_id} not found")
            return None

        item = response['Items'][0]
        # Cache for future use
        _cache_voice_session(session_id, item['PK'], item['SK'])
        return item

    except Exception as e:
        logger.error(f"Error retrieving voice call diagnostics for session {session_id}: {e}")
        return None

def list_conversations_by_session(session_id: str) -> List[Dict]:
    """List conversations by session ID."""
    if not initialize_dynamodb():
        return []

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return []

        response = conversations_table.query(
            KeyConditionExpression=Key('PK').eq(f"CONVERSATION#{session_id}")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing conversations for session {session_id}: {e}")
        return []

def list_conversations_by_property(property_id: str) -> List[Dict]:
    """List conversations by property ID."""
    if not initialize_dynamodb():
        return []

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return []

        response = conversations_table.scan(
            FilterExpression=Attr('PropertyId').eq(property_id)
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing conversations for property {property_id}: {e}")
        return []


def list_property_conversations_all(property_id: str, limit: int = 100, channel_filter: str = None,
                                   date_from: str = None, date_to: str = None, guest_name_filter: str = None) -> List[Dict]:
    """List all conversations and voice call sessions for a property with filtering."""
    if not initialize_dynamodb():
        return []

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return []

        all_conversations = []

        # Get regular conversations (fetch up to 1MB via pagination to ensure recency coverage)
        try:
            conversations = []
            query_kwargs = {
                'KeyConditionExpression': Key('PK').eq(f"PROPERTY#{property_id}") & Key('SK').begins_with("CONVERSATION#"),
                'ScanIndexForward': False  # Sort by sort key descending (lexicographic)
            }
            while True:
                response = conversations_table.query(**query_kwargs)
                conversations.extend(response.get('Items', []))
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
                # Safety cap to avoid excessive reads
                if len(conversations) >= max(limit * 5, 200):
                    break
            all_conversations.extend(conversations)
            logger.info(f"Retrieved {len(conversations)} regular conversations for property {property_id}")
        except Exception as e:
            logger.warning(f"Error getting regular conversations: {e}")

        # Get voice call diagnostics sessions (pagination similar to above)
        try:
            voice_sessions = []
            query_kwargs = {
                'KeyConditionExpression': Key('PK').eq(f"PROPERTY#{property_id}") & Key('SK').begins_with("VOICE_DIAGNOSTICS#"),
                'ScanIndexForward': False
            }
            while True:
                response = conversations_table.query(**query_kwargs)
                voice_sessions.extend(response.get('Items', []))
                last_evaluated_key = response.get('LastEvaluatedKey')
                if not last_evaluated_key:
                    break
                query_kwargs['ExclusiveStartKey'] = last_evaluated_key
                if len(voice_sessions) >= max(limit * 5, 200):
                    break
            all_conversations.extend(voice_sessions)
            logger.info(f"Retrieved {len(voice_sessions)} voice call sessions for property {property_id}")
        except Exception as e:
            logger.warning(f"Error getting voice call sessions: {e}")

        # Apply filters
        filtered_conversations = []

        for conv in all_conversations:
            # Channel filter
            if channel_filter:
                entity_type = conv.get('EntityType', '')
                if channel_filter == 'text_chat' and entity_type == 'VOICE_CALL_DIAGNOSTICS':
                    continue
                elif channel_filter == 'voice_call' and entity_type != 'VOICE_CALL_DIAGNOSTICS':
                    continue

            # Date filter
            if date_from or date_to:
                conv_date = conv.get('StartTime') or conv.get('CreatedAt')
                if conv_date:
                    try:
                        from datetime import datetime
                        if isinstance(conv_date, str):
                            conv_datetime = datetime.fromisoformat(conv_date.replace('Z', '+00:00'))
                        else:
                            conv_datetime = conv_date

                        if date_from:
                            from_datetime = datetime.fromisoformat(date_from)
                            if conv_datetime < from_datetime:
                                continue

                        if date_to:
                            to_datetime = datetime.fromisoformat(date_to)
                            if conv_datetime > to_datetime:
                                continue
                    except (ValueError, TypeError):
                        # Skip if date parsing fails
                        continue

            # Guest name filter
            if guest_name_filter:
                guest_name = conv.get('GuestName', '').lower()
                if guest_name_filter.lower() not in guest_name:
                    continue

            filtered_conversations.append(conv)

        # Sort by creation time (most recent first)
        filtered_conversations.sort(
            key=lambda x: x.get('StartTime') or x.get('CreatedAt') or '',
            reverse=True
        )

        # Apply limit
        result = filtered_conversations[:limit]

        logger.info(f"Returning {len(result)} filtered conversations for property {property_id}")
        return result

    except Exception as e:
        logger.error(f"Error listing all conversations for property {property_id}: {e}")
        return []


def delete_property_conversations(property_id: str) -> int:
    """Delete all conversation records (conversations and voice diagnostics) for a property.

    Args:
        property_id: ID of the property

    Returns:
        Number of deleted items.
    """
    if not initialize_dynamodb():
        return 0

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available")
            return 0

        # Collect keys via paginated queries on PK to avoid full table scan
        items_to_delete = []

        def _collect(prefix: str):
            query_kwargs = {
                'KeyConditionExpression': Key('PK').eq(f"PROPERTY#{property_id}") & Key('SK').begins_with(prefix)
            }
            while True:
                resp = conversations_table.query(**query_kwargs)
                items_to_delete.extend(resp.get('Items', []))
                lek = resp.get('LastEvaluatedKey')
                if not lek:
                    break
                query_kwargs['ExclusiveStartKey'] = lek

        # Regular conversations and voice diagnostics
        _collect("CONVERSATION#")
        _collect("VOICE_DIAGNOSTICS#")

        deleted = 0
        for item in items_to_delete:
            try:
                conversations_table.delete_item(Key={'PK': item['PK'], 'SK': item['SK']})
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete conversation item {item.get('PK')}/{item.get('SK')}: {e}")

        logger.info(f"Deleted {deleted} conversation items for property {property_id}")
        return deleted
    except Exception as e:
        logger.error(f"Error deleting conversations for property {property_id}: {e}")
        return 0

def create_fallback_voice_session(property_id: str, user_id: str, session_id: str,
                                 client_diagnostics: dict = None, network_quality: dict = None,
                                 guest_name: str = None, reservation_id: str = None,
                                 initialization_errors: list = None) -> bool:
    """Create a fallback voice call session when normal initialization fails"""
    if not initialize_dynamodb():
        logger.error("Failed to initialize DynamoDB for fallback voice session")
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    # Create a fallback session with special status and error tracking
    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"VOICE_DIAGNOSTICS#{session_id}",
        'GSI1PK': f"USER#{user_id}",
        'GSI1SK': timestamp,
        'EntityType': 'VOICE_CALL_DIAGNOSTICS',

        # Session Info
        'SessionId': session_id,
        'PropertyId': property_id,
        'UserId': user_id,
        'GuestName': guest_name or 'Guest',
        'ReservationId': reservation_id,
        'StartTime': timestamp,
        'EndTime': None,
        'Duration': None,
        'Status': 'FALLBACK_MODE',
        'Channel': 'voice_call',

        # Client Diagnostics (stored as nested JSON) - convert floats to Decimal
        'ClientDiagnostics': convert_floats_to_decimal(client_diagnostics or {}),
        'NetworkQuality': convert_floats_to_decimal(network_quality or {}),

        # Quality Metrics (will be updated during call)
        'QualityMetrics': {
            'ConnectionLatency': [],
            'AudioDropouts': 0,
            'TranscriptionErrors': 0,
            'InterruptionCount': 0,
            'ReconnectionCount': 0,
            'AverageResponseTime': [],
            'AudioQualityIssues': [],
            'WebSocketEvents': [],
            'MemoryUsage': [],
            'BufferUnderruns': 0,
            'BufferOverruns': 0
        },

        # Event Timeline - Critical for debugging
        'EventTimeline': [{
            'timestamp': timestamp,
            'event': 'FALLBACK_SESSION_CREATED',
            'details': {
                'property_id': property_id,
                'user_id': user_id,
                'guest_name': guest_name,
                'reservation_id': reservation_id,
                'initialization_errors': initialization_errors or [],
                'reason': 'Normal session initialization failed'
            }
        }],

        # Error Tracking - Include initialization errors
        'Errors': [{'timestamp': timestamp, 'event': 'INITIALIZATION_FAILED', 'errors': initialization_errors or []}] if initialization_errors else [],
        'Warnings': [{'timestamp': timestamp, 'event': 'FALLBACK_MODE_ENABLED', 'message': 'Session created in fallback mode due to initialization failure'}],
        'HealthChecks': [],

        # Technical Configuration
        'TechnicalConfig': {
            'GeminiModel': None,  # Will be set when call starts
            'VoiceSettings': {},
            'AudioSettings': {},
            'WebSocketUrl': None,
            'ApiKeyType': None,
            'FallbackMode': True
        },

        # Metadata
        'CreatedAt': timestamp,
        'LastUpdateTime': timestamp,
        'MessageCount': 0,
        'InitializationErrors': initialization_errors or []
    }

    try:
        conversations_table = get_conversations_table()
        if conversations_table:
            conversations_table.put_item(Item=item)
            # Cache the session keys for faster lookups
            _cache_voice_session(session_id, item['PK'], item['SK'])
            logger.info(f"Created fallback voice call session {session_id} for property {property_id}")
            return True
        else:
            logger.error("Conversations table not available for fallback voice session")
            return False
    except Exception as e:
        logger.error(f"Error creating fallback voice session {session_id}: {e}")
        return False


def update_fallback_voice_session(session_id: str, fallback_data: dict) -> bool:
    """Update a fallback voice session with complete data from frontend"""
    if not initialize_dynamodb():
        logger.error("Failed to initialize DynamoDB for fallback session update")
        return False

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available for fallback session update")
            return False

        # Find the session
        cached_keys = _get_cached_voice_session(session_id)

        if cached_keys:
            pk = cached_keys['PK']
            sk = cached_keys['SK']
        else:
            # Fall back to scan
            response = conversations_table.scan(
                FilterExpression=Attr('SessionId').eq(session_id) & Attr('EntityType').eq('VOICE_CALL_DIAGNOSTICS'),
                Limit=50
            )

            if not response['Items']:
                logger.warning(f"Fallback session {session_id} not found for update")
                return False

            item = response['Items'][0]
            pk = item['PK']
            sk = item['SK']
            # Cache for future use
            _cache_voice_session(session_id, pk, sk)

        # Update the session with all fallback data
        update_params = {
            'Key': {'PK': pk, 'SK': sk},
            'UpdateExpression': 'SET #status = :status, EndTime = :end_time, #duration = :duration, EventTimeline = :events, QualityMetrics = :metrics, LastUpdateTime = :update_time, FinalMetrics = :final_metrics',
            'ExpressionAttributeNames': {
                '#status': 'Status',
                '#duration': 'Duration'  # Duration is a reserved keyword
            },
            'ExpressionAttributeValues': {
                ':status': 'FALLBACK_COMPLETED',
                ':end_time': fallback_data.get('endTime', timestamp),
                ':duration': fallback_data.get('duration', 0),
                ':events': convert_floats_to_decimal(fallback_data.get('events', [])),
                ':metrics': convert_floats_to_decimal(fallback_data.get('metrics', {})),
                ':update_time': timestamp,
                ':final_metrics': convert_floats_to_decimal({
                    'sessionDuration': fallback_data.get('duration', 0),
                    'totalEvents': len(fallback_data.get('events', [])),
                    'fallbackMode': True,
                    'initializationErrors': fallback_data.get('initializationErrors', [])
                })
            }
        }

        conversations_table.update_item(**update_params)
        logger.info(f"Updated fallback voice session {session_id} with complete data")
        return True

    except Exception as e:
        logger.error(f"Error updating fallback voice session {session_id}: {e}")
        return False


# Initialize DynamoDB client at module load time
initialize_dynamodb()


def set_voice_session_summary(property_id: str, session_id: str, ai_summary: str) -> bool:
    """Persist an AI summary on a voice diagnostics session record.

    Uses the composite key PK=PROPERTY#<property_id>, SK=VOICE_DIAGNOSTICS#<session_id>.
    """
    if not initialize_dynamodb():
        logger.error("Failed to initialize DynamoDB for setting voice session summary")
        return False


def run_missing_conversation_summaries_job(max_items: int = 50) -> dict:
    """Scan for conversations/sessions missing AISummary and generate them.

    Returns a dict with counts: {"processed": int, "skipped": int, "errors": int}
    """
    results = {"processed": 0, "skipped": 0, "errors": 0}
    if not initialize_dynamodb():
        logger.error("Failed to initialize DynamoDB for missing summaries job")
        return results

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available for missing summaries job")
            return results

        # Scan the table (1MB pages). We'll post-filter items missing AISummary and with messages.
        scan_kwargs = {
            'ProjectionExpression': 'PK, SK, EntityType, PropertyId, ConversationId, SessionId, GuestName, Messages, Transcripts, AISummary'
        }

        from concierge.utils.rate_limiter import get_gemini_rate_limiter
        rate_limiter = get_gemini_rate_limiter()

        def build_messages(item: dict) -> list:
            msgs = []
            if item.get('EntityType') == 'VOICE_CALL_DIAGNOSTICS':
                for t in item.get('Transcripts', []) or []:
                    msgs.append({'role': t.get('role', ''), 'text': t.get('text', '')})
            else:
                for m in item.get('Messages', []) or []:
                    msgs.append({'role': m.get('role', ''), 'text': m.get('text') or m.get('content', '')})
            return [m for m in msgs if (m.get('text') or '').strip()]

        processed = 0
        last_evaluated_key = None
        while True:
            if last_evaluated_key:
                scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
            response = conversations_table.scan(**scan_kwargs)
            items = response.get('Items', [])

            for item in items:
                if processed >= max_items:
                    break

                if item.get('AISummary'):
                    results['skipped'] += 1
                    continue

                messages = build_messages(item)
                if not messages:
                    results['skipped'] += 1
                    continue

                try:
                    # Rate limit Gemini calls
                    rate_limiter.wait_if_needed()

                    # Best-effort property context for better summaries
                    property_context = None
                    try:
                        from concierge.utils.firestore_client import get_property as fs_get_property
                        if item.get('PropertyId'):
                            property_context = fs_get_property(item['PropertyId'])
                    except Exception:
                        pass

                    from concierge.utils.ai_helpers import generate_conversation_summary as gen_sum
                    summary_text = gen_sum(messages=messages, property_context=property_context, guest_name=item.get('GuestName'))
                    if not summary_text:
                        results['skipped'] += 1
                        continue

                    # Persist
                    if item.get('EntityType') == 'VOICE_CALL_DIAGNOSTICS':
                        session_id = item.get('SessionId') or (item.get('SK', '').split('#')[1] if '#' in item.get('SK', '') else None)
                        if session_id and item.get('PropertyId'):
                            ok = set_voice_session_summary(item['PropertyId'], session_id, summary_text)
                            if ok:
                                processed += 1
                                results['processed'] += 1
                            else:
                                results['errors'] += 1
                    else:
                        conversation_id = item.get('ConversationId') or (item.get('SK', '').split('#')[1] if '#' in item.get('SK', '') else None)
                        if conversation_id and item.get('PropertyId'):
                            ok = update_conversation(item['PropertyId'], conversation_id, {'AISummary': summary_text})
                            if ok:
                                processed += 1
                                results['processed'] += 1
                            else:
                                results['errors'] += 1
                except Exception as e:
                    logger.warning(f"Failed to summarize item {item.get('SK')}: {e}")
                    results['errors'] += 1

            if processed >= max_items:
                break

            last_evaluated_key = response.get('LastEvaluatedKey')
            if not last_evaluated_key:
                break

        logger.info(f"Missing summaries job complete: {results}")
        return results
    except Exception as e:
        logger.error(f"Error in missing summaries job: {e}")
        return results

    if not ai_summary:
        return False

    try:
        conversations_table = get_conversations_table()
        if not conversations_table:
            logger.error("Conversations table not available for setting voice session summary")
            return False

        pk = f"PROPERTY#{property_id}"
        sk = f"VOICE_DIAGNOSTICS#{session_id}"

        conversations_table.update_item(
            Key={'PK': pk, 'SK': sk},
            UpdateExpression='SET AISummary = :summary, LastUpdateTime = :ts',
            ExpressionAttributeValues={
                ':summary': ai_summary,
                ':ts': datetime.now(timezone.utc).isoformat()
            }
        )
        logger.info(f"Stored AI summary for voice session {session_id} (property {property_id})")
        return True
    except Exception as e:
        logger.error(f"Error setting voice session summary {session_id}: {e}")
        return False