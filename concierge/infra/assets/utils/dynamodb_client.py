import os
import boto3
import logging
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key, Attr
from typing import Dict, List, Optional, Any, Union
from botocore.exceptions import ClientError

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

def get_conversations_table():
    """Get the DynamoDB conversations table resource."""
    if conversations_table is None:
        initialize_dynamodb()
    return conversations_table

# === User Operations ===

def get_user(uid: str) -> Optional[Dict]:
    """Get a user by their UID."""
    if not initialize_dynamodb():
        return None

    try:
        response = table.get_item(
            Key={
                'PK': f"USER#{uid}",
                'SK': "PROFILE"
            }
        )
        if 'Item' in response:
            return response['Item']
        return None
    except Exception as e:
        logger.error(f"Error getting user {uid}: {e}")
        return None

def create_user(uid: str, user_data: Dict) -> bool:
    """Create a new user in DynamoDB."""
    if not initialize_dynamodb():
        return False

    timestamp = datetime.now(timezone.utc).isoformat()
    phone_number = user_data.get('phone_number')

    item = {
        'PK': f"USER#{uid}",
        'SK': 'PROFILE',
        'EntityType': 'USER',
        'Email': user_data.get('email'),
        'DisplayName': user_data.get('display_name', user_data.get('displayName')),
        'Role': user_data.get('role', 'guest'),
        'CreatedAt': timestamp,
        'LastLogin': timestamp,
    }

    # Add phone number and GSI attributes if available
    if phone_number:
        item['PhoneNumber'] = phone_number
        item['GSI1PK'] = f"PHONE#{phone_number}"
        item['GSI1SK'] = f"USER#{uid}"

    try:
        table.put_item(Item=item)
        logger.info(f"Created user {uid}")
        return True
    except Exception as e:
        logger.error(f"Error creating user {uid}: {e}")
        return False

def update_user(uid: str, update_data: Dict) -> bool:
    """Update a user in DynamoDB."""
    if not initialize_dynamodb():
        return False

    # Map Firestore field names to DynamoDB field names
    field_mapping = {
        'displayName': 'DisplayName',
        'phoneNumber': 'PhoneNumber',
        'email': 'Email',
        'role': 'Role',
        'lastLogin': 'LastLogin'
    }

    # Build update expression and attribute values
    update_expression_parts = ["set UpdatedAt = :updated_at"]
    expression_attr_values = {
        ':updated_at': datetime.now(timezone.utc).isoformat()
    }

    # Process each field in the update data
    for key, value in update_data.items():
        if key in field_mapping:
            ddb_key = field_mapping[key]
            expression_key = f":{key.replace('.', '_')}"
            update_expression_parts.append(f"{ddb_key} = {expression_key}")
            expression_attr_values[expression_key] = value

    # Handle phone number specially for GSI updates
    if 'phoneNumber' in update_data or 'phone_number' in update_data:
        phone_number = update_data.get('phoneNumber', update_data.get('phone_number'))
        if phone_number:
            update_expression_parts.append("GSI1PK = :gsi1pk")
            update_expression_parts.append("GSI1SK = :gsi1sk")
            expression_attr_values[':gsi1pk'] = f"PHONE#{phone_number}"
            expression_attr_values[':gsi1sk'] = f"USER#{uid}"

    # Build final update expression
    update_expression = " , ".join(update_expression_parts)

    try:
        table.update_item(
            Key={
                'PK': f"USER#{uid}",
                'SK': 'PROFILE'
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attr_values
        )
        logger.info(f"Updated user {uid}")
        return True
    except Exception as e:
        logger.error(f"Error updating user {uid}: {e}")
        return False

def get_user_by_phone(phone_number: str) -> Optional[Dict]:
    """Get a user by their phone number using GSI3 (with fallback to scan).

    This function checks both PhoneNumber and AuthPhoneNumber fields to support
    the phone number swap scenario where users log in with one number but use
    another for business logic.
    """
    if not initialize_dynamodb():
        return None

    try:
        # First try to find by AuthPhoneNumber (for login purposes)
        logger.info(f"Looking up user by AuthPhoneNumber {phone_number}")
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('USER') &
                           Attr('AuthPhoneNumber').eq(phone_number)
        )

        items = response.get('Items', [])
        if items:
            logger.info(f"Found user with AuthPhoneNumber {phone_number}")
            return items[0]

        # If not found by AuthPhoneNumber, try regular PhoneNumber
        try:
            # Try to use GSI3 for phone lookups
            logger.info(f"Looking up user by PhoneNumber {phone_number} using GSI3")
            response = table.query(
                IndexName="GSI3",
                KeyConditionExpression=Key('PhoneNumber').eq(phone_number)
            )

            items = response.get('Items', [])
            if items:
                # Return the first user found with this phone number
                logger.info(f"Found user with PhoneNumber {phone_number} using GSI3")
                return items[0]
        except Exception as gsi_error:
            logger.error(f"Error looking up user by phone using GSI3 (may not exist yet): {gsi_error}")
            # Fall back to scan if GSI3 not yet available
            logger.info(f"Falling back to scan for user with PhoneNumber {phone_number}")
            response = table.scan(
                FilterExpression=Attr('EntityType').eq('USER') &
                               Attr('PhoneNumber').eq(phone_number)
            )

            items = response.get('Items', [])
            if items:
                logger.info(f"Found user with PhoneNumber {phone_number} using scan")
                return items[0]

        return None
    except Exception as e:
        logger.error(f"Error looking up user by phone: {e}")
        return None

# === Property Operations ===

def get_property(property_id: str) -> Optional[Dict]:
    """Get a property by ID."""
    if not initialize_dynamodb():
        return None

    try:
        response = table.get_item(
            Key={
                'PK': f"PROPERTY#{property_id}",
                'SK': "METADATA"
            }
        )
        if 'Item' in response:
            return response['Item']
        return None
    except Exception as e:
        logger.error(f"Error getting property {property_id}: {e}")
        return None

def list_all_properties() -> List[Dict]:
    """List all properties in the system."""
    if not initialize_dynamodb():
        return []

    try:
        # Use GSI2 to efficiently query all properties
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('PROPERTY') & Attr('SK').eq('METADATA')
        )
        properties = response.get('Items', [])
        logger.info(f"Retrieved {len(properties)} properties from DynamoDB")

        # Paginate if there are more results
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('EntityType').eq('PROPERTY') & Attr('SK').eq('METADATA'),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            properties.extend(response.get('Items', []))
            logger.info(f"Retrieved additional {len(response.get('Items', []))} properties (total: {len(properties)})")

        return properties
    except Exception as e:
        logger.error(f"Error listing all properties: {e}")
        return []

def list_properties_by_host(host_id: str) -> List[Dict]:
    """List all properties for a host."""
    if not initialize_dynamodb():
        return []

    try:
        logger.info(f"Listing properties for host {host_id} using GSI1 index")

        # Use GSI1 index for host lookups
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key('GSI1PK').eq(f"HOST#{host_id}")
        )

        properties = response.get('Items', [])
        logger.info(f"Found {len(properties)} properties for host {host_id}")

        # If no properties found, add a sample property for testing
        if not properties:
            logger.info(f"No properties found for host {host_id}, adding sample property")
            mock_property = {
                'PK': f"PROPERTY#sample-property-123",
                'SK': 'METADATA',
                'EntityType': 'PROPERTY',
                'HostId': host_id,
                'Name': 'Sample Beach House',
                'Address': '123 Ocean Drive, Malibu, CA',
                'Description': 'A beautiful beach house for testing purposes',
                'CreatedAt': datetime.now(timezone.utc).isoformat(),
                'GSI1PK': f"HOST#{host_id}",
                'GSI1SK': f"PROPERTY#sample-property-123"
            }
            properties.append(mock_property)

            # Also try to write this to DynamoDB for future requests
            try:
                table.put_item(Item=mock_property)
                logger.info(f"Added sample property to DynamoDB for host {host_id}")
            except Exception as write_err:
                logger.error(f"Error writing sample property to DynamoDB: {write_err}")

        # Log property details for debugging
        for i, prop in enumerate(properties):
            logger.info(f"Property {i+1}: ID={prop.get('PK', 'unknown')}, Name={prop.get('Name', 'unknown')}")

        return properties
    except Exception as e:
        logger.error(f"Error listing properties for host {host_id} using GSI1: {e}")
        # Fall back to scan if the index query fails
        try:
            logger.info(f"Falling back to scan operation for host {host_id}")
            response = table.scan(
                FilterExpression=Attr('EntityType').eq('PROPERTY') &
                               Attr('HostId').eq(host_id)
            )
            return response.get('Items', [])
        except Exception as scan_error:
            logger.error(f"Fallback scan also failed: {scan_error}")
            return []

def create_property(property_id: str, property_data: Dict) -> bool:
    """Create a new property with the given ID."""
    if not initialize_dynamodb():
        return False

    host_id = property_data.get('hostId')

    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': 'METADATA',
        'EntityType': 'PROPERTY',
        'HostId': host_id,
        'Name': property_data.get('name'),
        'Address': property_data.get('address'),
        'Description': property_data.get('description'),
        'ICalUrl': property_data.get('ical_url'),
        'CreatedAt': timestamp,
        'UpdatedAt': timestamp,
    }

    # Add GSI for host lookup
    if host_id:
        item['GSI1PK'] = f"HOST#{host_id}"
        item['GSI1SK'] = f"PROPERTY#{property_id}"

    # Add WiFi details if available
    wifi_details = property_data.get('wifiDetails')
    if wifi_details and isinstance(wifi_details, dict):
        item['WifiDetails'] = wifi_details

    try:
        table.put_item(Item=item)
        logger.info(f"Created property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating property: {e}")
        return False

def update_property(property_id: str, update_data: Dict) -> bool:
    """Update a property in DynamoDB."""
    if not initialize_dynamodb():
        return False

    # Map Firestore field names to DynamoDB field names
    field_mapping = {
        'name': 'Name',
        'address': 'Address',
        'description': 'Description',
        'ical_url': 'ICalUrl',
        'wifiDetails': 'WifiDetails',
        'checkInTime': 'CheckInTime',
        'checkOutTime': 'CheckOutTime',
        'rules': 'Rules'
    }

    # Build update expression and attribute values
    update_expression_parts = ["set #updated_at = :updated_at"]
    expression_attr_values = {
        ':updated_at': datetime.now(timezone.utc).isoformat()
    }

    # Build expression attribute names to handle reserved words
    expression_attr_names = {
        '#updated_at': 'UpdatedAt'
    }

    # Process each field in the update data
    for key, value in update_data.items():
        if key in field_mapping:
            ddb_key = field_mapping[key]
            expression_key = f":{key.replace('.', '_')}"

            # Use expression attribute name to avoid reserved keyword issues
            name_placeholder = f"#{key.replace('.', '_')}"
            update_expression_parts.append(f"{name_placeholder} = {expression_key}")

            # Add the attribute name mapping
            expression_attr_names[name_placeholder] = ddb_key

            # Add the attribute value
            expression_attr_values[expression_key] = value

    # Build final update expression
    update_expression = " , ".join(update_expression_parts)

    logger.info(f"Update expression: {update_expression}")
    logger.info(f"Expression attribute names: {expression_attr_names}")
    logger.info(f"Expression attribute values: {expression_attr_values}")

    try:
        table.update_item(
            Key={
                'PK': f"PROPERTY#{property_id}",
                'SK': 'METADATA'
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attr_names,
            ExpressionAttributeValues=expression_attr_values
        )
        logger.info(f"Updated property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating property {property_id}: {e}")
        return False

def delete_property(property_id: str) -> bool:
    """Delete a property from DynamoDB."""
    if not initialize_dynamodb():
        return False

    try:
        # Delete the main property record
        table.delete_item(
            Key={
                'PK': f"PROPERTY#{property_id}",
                'SK': 'METADATA'
            }
        )

        # Delete all related knowledge items
        delete_all_knowledge(property_id)

        # Delete all related reservations
        try:
            # First query all reservations for this property
            reservations = list_property_reservations(property_id)

            # Delete each reservation
            for reservation in reservations:
                reservation_id = reservation.get('PK', '').replace('RESERVATION#', '')
                if reservation_id:
                    table.delete_item(
                        Key={
                            'PK': f"RESERVATION#{reservation_id}",
                            'SK': 'METADATA'
                        }
                    )
                    logger.info(f"Deleted reservation {reservation_id} for property {property_id}")

            logger.info(f"Deleted {len(reservations)} reservations for property {property_id}")
        except Exception as e:
            logger.error(f"Error deleting reservations for property {property_id}: {e}")
            # Continue with deletion even if reservation deletion fails

        # LanceDB table deletion removed - migrated to Firestore with vector embeddings
        # Knowledge data is now stored in Firestore and managed through Firestore operations

        logger.info(f"Deleted property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting property {property_id}: {e}")
        return False

# === Knowledge Base Operations ===

def create_knowledge_source(source_id: str, source_data: Dict) -> bool:
    """Create a new knowledge source with the given ID."""
    if not initialize_dynamodb():
        return False

    property_id = source_data.get('propertyId')
    host_id = source_data.get('hostId')

    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"SOURCE#{source_id}",
        'EntityType': 'KNOWLEDGE_SOURCE',
        'SourceType': source_data.get('sourceType') or source_data.get('type', 'unknown'),
        'Status': source_data.get('status', 'processing_extraction'),
        'HostId': host_id,
        'CreatedAt': timestamp,
        'UpdatedAt': timestamp,
    }

    # Add extracted text if available
    extracted_text = source_data.get('extractedText') or source_data.get('content')
    if extracted_text:
        item['Content'] = extracted_text

    # Add filename if available
    file_name = source_data.get('fileName') or source_data.get('name')
    if file_name:
        item['FileName'] = file_name

    # Add file path if available
    file_path = source_data.get('filePath')
    if file_path:
        item['FilePath'] = file_path

    # Add GSI for source lookups
    item['GSI1PK'] = f"SOURCE#{source_id}"
    item['GSI1SK'] = f"PROPERTY#{property_id}"

    try:
        table.put_item(Item=item)
        logger.info(f"Created knowledge source {source_id} for property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating knowledge source: {e}")
        return False

def list_knowledge_sources(property_id: str) -> List[Dict]:
    """List all knowledge sources for a property."""
    if not initialize_dynamodb():
        return []

    try:
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                 Key('SK').begins_with("SOURCE#")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing knowledge sources for property {property_id}: {e}")
        return []

def get_knowledge_source(source_id: str) -> Optional[Dict]:
    """Get a knowledge source by ID."""
    if not initialize_dynamodb():
        return None

    try:
        # Use scan with filter since we don't know the property ID
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('KNOWLEDGE_SOURCE') &
                           Attr('SK').eq(f"SOURCE#{source_id}")
        )

        items = response.get('Items', [])
        if not items:
            logger.warning(f"Knowledge source {source_id} not found")
            return None

        return items[0]

    except Exception as e:
        logger.error(f"Error getting knowledge source {source_id}: {e}")
        return None

def update_knowledge_source(source_id: str, update_data: Dict) -> bool:
    """Update a knowledge source."""
    if not initialize_dynamodb():
        return False

    try:
        # First get the source to get its PK and property ID
        source_data = get_knowledge_source(source_id)
        if not source_data:
            logger.error(f"Knowledge source {source_id} not found for update")
            return False

        # Extract PK and SK
        pk = source_data.get('PK')
        sk = source_data.get('SK')

        if not pk or not sk:
            logger.error(f"Knowledge source {source_id} missing PK or SK")
            return False

        # Build update expression and attribute values
        update_expression_parts = ["set UpdatedAt = :updated_at"]
        expression_attr_values = {
            ':updated_at': datetime.now(timezone.utc).isoformat()
        }

        # Build expression attribute names to handle reserved words
        expression_attr_names = {}

        # Process each field in the update data
        for key, value in update_data.items():
            # Use expression attribute name to avoid reserved keyword issues
            name_placeholder = f"#{key}"
            update_expression_parts.append(f"{name_placeholder} = :{key}")

            # Add the attribute name mapping
            expression_attr_names[name_placeholder] = key

            # Add the attribute value
            expression_attr_values[f":{key}"] = value

        # Build final update expression
        update_expression = " , ".join(update_expression_parts)

        logger.info(f"Update expression for source {source_id}: {update_expression}")

        table.update_item(
            Key={
                'PK': pk,
                'SK': sk
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attr_names,
            ExpressionAttributeValues=expression_attr_values
        )

        logger.info(f"Updated knowledge source {source_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating knowledge source {source_id}: {e}")
        return False

def delete_knowledge_source(source_id: str) -> bool:
    """Delete a knowledge source and all its associated items."""
    if not initialize_dynamodb():
        return False

    try:
        # First get the source to get its PK and property ID
        source_data = get_knowledge_source(source_id)
        if not source_data:
            logger.error(f"Knowledge source {source_id} not found for deletion")
            return False

        # Extract PK, SK and property ID
        pk = source_data.get('PK')
        sk = source_data.get('SK')
        property_id = None

        if pk and pk.startswith('PROPERTY#'):
            property_id = pk.replace('PROPERTY#', '')

        if not pk or not sk:
            logger.error(f"Knowledge source {source_id} missing PK or SK")
            return False

        # First delete all associated knowledge items
        items = list_knowledge_items_by_source(source_id)
        for item in items:
            item_sk = item.get('SK', '')
            if item_sk and '#' in item_sk:
                item_id = item_sk.split('#')[-1]
                try:
                    delete_knowledge_item(item_id)
                except Exception as e:
                    logger.error(f"Error deleting knowledge item {item_id}: {e}")
                    # Continue with other deletions even if one fails

        # Now delete the source
        table.delete_item(
            Key={
                'PK': pk,
                'SK': sk
            }
        )

        # Delete the file if there's a file path
        file_path = source_data.get('FilePath')
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted file {file_path}")
            except Exception as e:
                logger.error(f"Error deleting file {file_path}: {e}")
                # Continue even if file deletion fails

        logger.info(f"Deleted knowledge source {source_id} and its items")
        return True
    except Exception as e:
        logger.error(f"Error deleting knowledge source {source_id}: {e}")
        return False

def create_knowledge_item(item_id: str, item_data: Dict) -> bool:
    """Create a new knowledge item (Q&A pair) with the given ID."""
    if not initialize_dynamodb():
        return False

    property_id = item_data.get('propertyId')
    source_id = item_data.get('sourceId')
    host_id = item_data.get('hostId')

    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"ITEM#{source_id}#{item_id}",
        'EntityType': 'KNOWLEDGE_ITEM',
        'SourceId': source_id,
        'Question': item_data.get('question'),
        'Answer': item_data.get('answer'),
        'Status': item_data.get('status', 'pending'),
        'HostId': host_id,
        'CreatedAt': timestamp,
    }

    # Add GSI for source lookups
    item['GSI1PK'] = f"SOURCE#{source_id}"
    item['GSI1SK'] = f"ITEM#{item_id}"

    try:
        table.put_item(Item=item)
        logger.info(f"Created knowledge item {item_id} for source {source_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating knowledge item: {e}")
        return False

def list_knowledge_items_by_source(source_id: str) -> List[Dict]:
    """List all knowledge items for a specific source."""
    if not initialize_dynamodb():
        return []

    try:
        # Use GSI1 for efficient query by source ID
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key('GSI1PK').eq(f"SOURCE#{source_id}")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing knowledge items for source {source_id}: {e}")
        # Fall back to scan if the index query fails
        try:
            response = table.scan(
                FilterExpression=Attr('EntityType').eq('KNOWLEDGE_ITEM') &
                               Attr('SourceId').eq(source_id)
            )
            return response.get('Items', [])
        except Exception as scan_error:
            logger.error(f"Fallback scan also failed: {scan_error}")
            return []

def list_knowledge_items_by_property(property_id: str) -> List[Dict]:
    """List all knowledge items for a property."""
    if not initialize_dynamodb():
        return []

    try:
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                 Key('SK').begins_with("ITEM#")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing knowledge items for property {property_id}: {e}")
        return []

def delete_all_knowledge(property_id: str) -> bool:
    """
    Delete all knowledge sources and items for a property from both DynamoDB and LanceDB.
    This function handles cleaning up data in both databases.
    """
    if not initialize_dynamodb():
        return False

    try:
        # Get all items to delete (sources and items)
        source_query = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                 Key('SK').begins_with("SOURCE#")
        )

        item_query = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                 Key('SK').begins_with("ITEM#")
        )

        # Collect all items to delete
        items_to_delete = source_query.get('Items', []) + item_query.get('Items', [])

        # LanceDB table deletion removed - migrated to Firestore with vector embeddings
        # Knowledge data is now stored in Firestore and managed through Firestore operations

        # DynamoDB doesn't support batch deletes directly, so we do them one by one
        for item in items_to_delete:
            table.delete_item(
                Key={
                    'PK': item['PK'],
                    'SK': item['SK']
                }
            )

        logger.info(f"Deleted {len(items_to_delete)} knowledge items/sources for property {property_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting knowledge for property {property_id}: {e}")
        return False

# === Reservation Operations ===

def create_reservation(reservation_data: Dict) -> Optional[str]:
    """Create a new reservation and return its ID."""
    if not initialize_dynamodb():
        return None

    # Generate a unique ID
    import uuid
    reservation_id = str(uuid.uuid4())
    property_id = reservation_data.get('propertyId')
    guest_phone = reservation_data.get('guestPhoneNumber')

    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"RESERVATION#{reservation_id}",
        'EntityType': 'RESERVATION',
        'StartDate': reservation_data.get('startDate'),
        'EndDate': reservation_data.get('endDate'),
        'GuestName': reservation_data.get('guestName'),
        'GuestPhoneNumber': guest_phone,
        'GuestPhoneLast4': reservation_data.get('guestPhoneLast4'),
        'Summary': reservation_data.get('summary'),
        'Description': reservation_data.get('description'),
        'CreatedAt': timestamp,
        'UpdatedAt': timestamp,
    }

    # Add GSI for phone lookups
    if guest_phone:
        item['GSI1PK'] = f"PHONE#{guest_phone}"
        item['GSI1SK'] = f"RESERVATION#{reservation_id}"

    # Add GSI2 for listing all reservations by date
    item['GSI2PK'] = "RESERVATION"
    item['GSI2SK'] = reservation_data.get('startDate')

    # Add additional contacts if available
    additional_contacts = reservation_data.get('additional_contacts')
    if additional_contacts:
        item['AdditionalContacts'] = additional_contacts

    try:
        # Create the main reservation
        table.put_item(Item=item)

        # Create user lookup entries if user ID is known (optional)
        user_id = reservation_data.get('userId')
        if user_id:
            lookup_item = {
                'PK': f"USER#{user_id}",
                'SK': f"RESERVATION#{reservation_id}",
                'EntityType': 'USER_RESERVATION',
                'ReservationId': reservation_id,
                'PropertyId': property_id,
                'StartDate': reservation_data.get('startDate'),
                'EndDate': reservation_data.get('endDate'),
                'GSI1PK': f"RESERVATION#{reservation_id}",
                'GSI1SK': f"USER#{user_id}"
            }
            table.put_item(Item=lookup_item)

        logger.info(f"Created reservation {reservation_id} for property {property_id}")
        return reservation_id
    except Exception as e:
        logger.error(f"Error creating reservation: {e}")
        return None

def list_property_reservations(property_id: str) -> List[Dict]:
    """List all reservations for a property."""
    if not initialize_dynamodb():
        return []

    try:
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                 Key('SK').begins_with("RESERVATION#")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing reservations for property {property_id}: {e}")
        return []

def list_user_reservations(user_id: str) -> List[Dict]:
    """List all reservations for a user."""
    if not initialize_dynamodb():
        return []

    try:
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"USER#{user_id}") &
                                 Key('SK').begins_with("RESERVATION#")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing reservations for user {user_id}: {e}")
        return []

def list_reservations_by_phone(phone_number: str) -> List[Dict]:
    """
    List all reservations for a phone number.

    This function checks for reservations associated with the given phone number,
    which is important for the phone call functionality to identify the caller's
    active reservations.
    """
    if not initialize_dynamodb():
        return []

    try:
        # Query reservations where this phone is the primary guest phone using GSI1
        logger.info(f"Querying reservations for phone {phone_number} using GSI1")
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key('GSI1PK').eq(f"PHONE#{phone_number}")
        )
        primary_reservations = response.get('Items', [])
        logger.info(f"Found {len(primary_reservations)} reservations where {phone_number} is primary guest")

        # Now query reservations where this phone is in the additional contacts
        # This still requires a scan as we can't index the nested AdditionalContacts
        all_reservations_response = table.scan(
            FilterExpression=Attr('EntityType').eq('RESERVATION')
        )
        all_reservations = all_reservations_response.get('Items', [])
        logger.info(f"Scanning {len(all_reservations)} total reservations for additional contacts")

        # Examine and log the structure of AdditionalContacts in a few reservations
        contact_formats_found = False
        for i, res in enumerate(all_reservations[:5]):  # Check first 5 for debugging
            additional_contacts = res.get('AdditionalContacts', [])
            if additional_contacts:
                contact_formats_found = True
                # Log the structure of AdditionalContacts for debugging
                logger.info(f"AdditionalContacts structure in reservation {i}: {additional_contacts}")
                # Check what fields exist in the first contact
                if additional_contacts and len(additional_contacts) > 0:
                    first_contact = additional_contacts[0]
                    logger.info(f"First contact fields: {list(first_contact.keys())}")
                    if 'phoneNumber' in first_contact:
                        logger.info(f"Contact uses 'phoneNumber' field: {first_contact['phoneNumber']}")
                    elif 'phone' in first_contact:
                        logger.info(f"Contact uses 'phone' field: {first_contact['phone']}")

        if not contact_formats_found:
            logger.info("No reservations with AdditionalContacts found in the first 5 reservations")

        # Filter for reservations where this phone appears in AdditionalContacts
        additional_reservations = []
        for res in all_reservations:
            additional_contacts = res.get('AdditionalContacts', [])

            # Skip if already found as primary guest
            if res in primary_reservations:
                continue

            # Check if this phone is in any of the additional contacts
            for contact in additional_contacts:
                # Check both potential field names for phone number
                contact_phone = contact.get('phone') or contact.get('phoneNumber') or contact.get('PhoneNumber')
                if contact_phone and contact_phone == phone_number:
                    additional_reservations.append(res)
                    logger.info(f"Found reservation {res.get('ReservationId', 'unknown')} where {phone_number} is an additional contact")
                    break

        # Combine both lists
        combined_reservations = primary_reservations + additional_reservations
        logger.info(f"Found total of {len(combined_reservations)} reservations for phone {phone_number}")
        return combined_reservations
    except Exception as e:
        logger.error(f"Error querying reservations for phone {phone_number} using GSI1: {e}")
        # Fall back to scan if index query fails
        try:
            logger.info(f"Falling back to scan for phone {phone_number}")
            response = table.scan(
                FilterExpression=Attr('EntityType').eq('RESERVATION') &
                               Attr('GuestPhoneNumber').eq(phone_number)
            )
            primary_reservations = response.get('Items', [])
            return primary_reservations
        except Exception as scan_error:
            logger.error(f"Fallback scan also failed: {scan_error}")
            return []

def get_user_reservations(user_id: str, phone_number: str = None) -> List[Dict]:
    """
    Get all reservations for a user, checking both their user ID and phone number.

    Args:
        user_id: The user ID to look up reservations for
        phone_number: Optional phone number to check for additional reservations

    Returns:
        A combined list of reservations from both sources
    """
    if not initialize_dynamodb():
        return []

    # Get direct user reservations
    user_reservations = list_user_reservations(user_id)

    # Get phone-based reservations if phone is provided
    phone_reservations = []
    if phone_number:
        phone_reservations = list_reservations_by_phone(phone_number)

    # Combine both lists
    combined_reservations = user_reservations + phone_reservations

    # Remove duplicates if any (based on reservation ID)
    seen_ids = set()
    unique_reservations = []
    for res in combined_reservations:
        # Extract the reservation ID from different possible fields
        res_id = res.get('ReservationId')
        if not res_id and res.get('SK', '').startswith('RESERVATION#'):
            res_id = res.get('SK', '').replace('RESERVATION#', '')

        # Only add if we haven't seen this ID before
        if res_id and res_id not in seen_ids:
            seen_ids.add(res_id)
            unique_reservations.append(res)

    logger.info(f"Found {len(unique_reservations)} total reservations for user {user_id}")
    return unique_reservations

def list_active_reservations() -> List[Dict]:
    """List all currently active reservations."""
    if not initialize_dynamodb():
        return []

    # Get the current date
    now = datetime.now(timezone.utc).isoformat()

    try:
        # Use GSI2 to query for all reservations efficiently
        logger.info("Querying all reservations using GSI2")
        response = table.query(
            IndexName="GSI2",
            KeyConditionExpression=Key('EntityType').eq('RESERVATION')
        )

        # Then filter client-side for active reservations
        reservations = response.get('Items', [])
        active_reservations = [
            res for res in reservations
            if res.get('StartDate') and res.get('EndDate') and
               res.get('StartDate') <= now and res.get('EndDate') >= now
        ]

        logger.info(f"Found {len(active_reservations)} active reservations out of {len(reservations)} total")
        return active_reservations
    except Exception as e:
        logger.error(f"Error querying reservations using GSI2: {e}")
        # Fall back to scan if the index query fails
        try:
            logger.info("Falling back to scan operation for active reservations")
            response = table.scan(
                FilterExpression=Attr('EntityType').eq('RESERVATION') &
                                Attr('StartDate').lte(now) &
                                Attr('EndDate').gte(now)
            )
            return response.get('Items', [])
        except Exception as scan_error:
            logger.error(f"Fallback scan also failed: {scan_error}")
            return []

# === Conversation Operations ===

def store_conversation(conversation_data: Dict) -> Optional[str]:
    """Store a conversation message."""
    if not initialize_dynamodb():
        return None

    # Generate a unique ID
    import uuid
    conversation_id = str(uuid.uuid4())
    property_id = conversation_data.get('propertyId')
    session_id = conversation_data.get('sessionId')
    timestamp = conversation_data.get('timestamp', datetime.now(timezone.utc).isoformat())
    user_id = conversation_data.get('userId')

    item = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"CONVERSATION#{timestamp}#{conversation_id}",
        'EntityType': 'CONVERSATION',
        'ReservationId': conversation_data.get('reservationId'),
        'Role': conversation_data.get('role'),
        'Text': conversation_data.get('text'),
        'Channel': conversation_data.get('channel', 'voice_call'),
        'SessionId': session_id,
        'Timestamp': timestamp,
    }

    # Add context used if this is an assistant response
    context_used = conversation_data.get('contextUsed')
    if context_used:
        item['ContextUsed'] = context_used

    # Add GSI for session lookups
    if session_id:
        item['GSI1PK'] = f"SESSION#{session_id}"
        item['GSI1SK'] = timestamp

    # Add GSI2 for listing all conversations
    item['GSI2PK'] = "CONVERSATION"
    item['GSI2SK'] = timestamp

    # Add user ID and user lookup if available
    if user_id:
        item['UserId'] = user_id

        # Create a corresponding user-conversation entry
        user_item = {
            'PK': f"USER#{user_id}",
            'SK': f"CONVERSATION#{timestamp}#{conversation_id}",
            'EntityType': 'USER_CONVERSATION',
            'ConversationId': conversation_id,
            'PropertyId': property_id,
            'Text': conversation_data.get('text'),
            'Role': conversation_data.get('role'),
            'Timestamp': timestamp,
            'GSI1PK': f"CONVERSATION#{conversation_id}",
            'GSI1SK': f"USER#{user_id}"
        }
        table.put_item(Item=user_item)

    try:
        table.put_item(Item=item)
        logger.info(f"Stored conversation {conversation_id} for property {property_id}")
        return conversation_id
    except Exception as e:
        logger.error(f"Error storing conversation: {e}")
        return None

def list_conversations_by_session(session_id: str) -> List[Dict]:
    """List all conversations for a session."""
    if not initialize_dynamodb():
        return []

    try:
        # Use GSI1 for session lookups
        response = table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key('GSI1PK').eq(f"SESSION#{session_id}")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing conversations for session {session_id} using GSI1: {e}")
        # Fall back to scan if the index query fails
        try:
            response = table.scan(
                FilterExpression=Attr('EntityType').eq('CONVERSATION') &
                               Attr('SessionId').eq(session_id)
            )
            return response.get('Items', [])
        except Exception as scan_error:
            logger.error(f"Fallback scan also failed: {scan_error}")
            return []

def list_conversations_by_property(property_id: str) -> List[Dict]:
    """List all conversations for a property."""
    if not initialize_dynamodb():
        return []

    try:
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f"PROPERTY#{property_id}") &
                                 Key('SK').begins_with("CONVERSATION#")
        )
        return response.get('Items', [])
    except Exception as e:
        logger.error(f"Error listing conversations for property {property_id}: {e}")
        return []

# Add the missing function to update reservation phone
def update_reservation_phone(reservation_id: str, phone_number: str) -> bool:
    """Update the phone number for a reservation."""
    if not initialize_dynamodb():
        return False

    try:
        # First get the reservation to ensure it exists, using scan with filter
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('RESERVATION') &
                           Attr('ReservationId').eq(reservation_id)
        )

        items = response.get('Items', [])
        if not items:
            logger.error(f"Reservation {reservation_id} not found for phone update")
            return False

        # Get the primary PK/SK for the reservation
        reservation_item = items[0]
        pk = reservation_item.get('PK')
        sk = reservation_item.get('SK')

        # Update the reservation with the new phone number
        table.update_item(
            Key={
                'PK': pk,
                'SK': sk
            },
            UpdateExpression="SET GuestPhoneNumber = :phone, UpdatedAt = :timestamp",
            ExpressionAttributeValues={
                ':phone': phone_number,
                ':timestamp': datetime.now(timezone.utc).isoformat()
            }
        )

        # We're not using GSI lookups anymore so we don't need to update those
        logger.info(f"Updated phone number for reservation {reservation_id} to {phone_number}")
        return True

    except Exception as e:
        logger.error(f"Error updating phone for reservation {reservation_id}: {e}")
        return False

# Add function to get a knowledge item by ID
def get_knowledge_item(item_id: str) -> Optional[Dict]:
    """Get a knowledge item by ID."""
    if not initialize_dynamodb():
        return None

    try:
        # Use scan with filter instead of GSI1 index
        # The item ID is at the end of the SK field in the format "ITEM#source_id#item_id"
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('KNOWLEDGE_ITEM') &
                           Attr('SK').contains(item_id)
        )

        items = response.get('Items', [])
        if not items:
            logger.warning(f"Knowledge item {item_id} not found")
            return None

        return items[0]

    except Exception as e:
        logger.error(f"Error getting knowledge item {item_id}: {e}")
        return None

# Add function to update knowledge item status
def update_knowledge_item_status(item_id: str, status: str, error_message: str = None) -> bool:
    """Update the status of a knowledge item."""
    if not initialize_dynamodb():
        return False

    try:
        # First get the item to ensure it exists and get its PK/SK
        item_data = get_knowledge_item(item_id)
        if not item_data:
            logger.error(f"Knowledge item {item_id} not found for status update")
            return False

        # Get the primary PK/SK for the item
        pk = item_data.get('PK')
        sk = item_data.get('SK')

        update_expression = "SET #status = :status, UpdatedAt = :timestamp"
        expression_attribute_names = {
            '#status': 'Status'
        }
        expression_attribute_values = {
            ':status': status,
            ':timestamp': datetime.now(timezone.utc).isoformat()
        }

        # Add error message if provided
        if error_message:
            update_expression += ", ErrorMessage = :error"
            expression_attribute_values[':error'] = error_message

        # Update the item
        table.update_item(
            Key={
                'PK': pk,
                'SK': sk
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )

        logger.info(f"Updated status of knowledge item {item_id} to '{status}'")
        return True

    except Exception as e:
        logger.error(f"Error updating status for knowledge item {item_id}: {e}")
        return False

# Add function to update knowledge item
def update_knowledge_item(item_id: str, update_data: Dict) -> bool:
    """Update a knowledge item with new data."""
    if not initialize_dynamodb():
        return False

    try:
        # First get the item to ensure it exists and get its PK/SK
        item_data = get_knowledge_item(item_id)
        if not item_data:
            logger.error(f"Knowledge item {item_id} not found for update")
            return False

        # Get the primary PK/SK for the item
        pk = item_data.get('PK')
        sk = item_data.get('SK')

        # Build update expression and attribute values
        update_parts = []
        expression_attribute_names = {}
        expression_attribute_values = {
            ':timestamp': datetime.now(timezone.utc).isoformat()
        }

        # Add UpdatedAt timestamp
        update_parts.append("UpdatedAt = :timestamp")

        # Update Question if provided
        if 'Question' in update_data:
            update_parts.append("#question = :question")
            expression_attribute_names['#question'] = 'Question'
            expression_attribute_values[':question'] = update_data['Question']

        # Update Answer if provided
        if 'Answer' in update_data:
            update_parts.append("#answer = :answer")
            expression_attribute_names['#answer'] = 'Answer'
            expression_attribute_values[':answer'] = update_data['Answer']

        # Update Status if provided
        if 'Status' in update_data:
            update_parts.append("#status = :status")
            expression_attribute_names['#status'] = 'Status'
            expression_attribute_values[':status'] = update_data['Status']

        # Add ErrorMessage if provided
        if 'ErrorMessage' in update_data:
            update_parts.append("ErrorMessage = :error")
            expression_attribute_values[':error'] = update_data['ErrorMessage']

        # Create the full update expression
        update_expression = "SET " + ", ".join(update_parts)

        # Update the item
        table.update_item(
            Key={
                'PK': pk,
                'SK': sk
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )

        logger.info(f"Updated knowledge item {item_id}")
        return True

    except Exception as e:
        logger.error(f"Error updating knowledge item {item_id}: {e}")
        return False

# Add function to delete a knowledge item
def delete_knowledge_item(item_id: str) -> bool:
    """Delete a knowledge item by ID."""
    if not initialize_dynamodb():
        return False

    try:
        # First get the item to ensure it exists and get its PK/SK
        item_data = get_knowledge_item(item_id)
        if not item_data:
            logger.error(f"Knowledge item {item_id} not found for deletion")
            return False

        # Get the primary PK/SK for the item
        pk = item_data.get('PK')
        sk = item_data.get('SK')
        property_id = None

        # Extract property_id from PK (format: "PROPERTY#property_id")
        if pk and pk.startswith('PROPERTY#'):
            property_id = pk.replace('PROPERTY#', '')

        # Delete from LanceDB if applicable
        try:
            # Only try to delete from LanceDB if it was successfully ingested there
            if item_data.get('Status') == 'ingested' and item_data.get('lancedb_status') == 'ingested':
                # Try to import lancedb here to avoid dependency issues
                import lancedb
                from concierge.config import LANCEDB_PATH

                # Get the table name - either from the item or construct default
                lancedb_table_name = item_data.get('lancedb_table')
                if not lancedb_table_name and property_id:
                    lancedb_table_name = f"knowledge_{property_id}"

                if LANCEDB_PATH and lancedb_table_name:
                    logger.info(f"Connecting to LanceDB at {LANCEDB_PATH} to delete item {item_id}")
                    db = lancedb.connect(LANCEDB_PATH)

                    if lancedb_table_name in db.table_names():
                        lancedb_table = db.open_table(lancedb_table_name)
                        lancedb_table.delete(f"id = '{item_id}'")
                        logger.info(f"Deleted item {item_id} from LanceDB table {lancedb_table_name}")
                    else:
                        logger.warning(f"LanceDB table {lancedb_table_name} not found, skipping LanceDB deletion")
        except Exception as e:
            logger.error(f"Error deleting item {item_id} from LanceDB: {e}")
            # Continue with DynamoDB deletion even if LanceDB deletion fails

        # Delete the item from DynamoDB
        table.delete_item(
            Key={
                'PK': pk,
                'SK': sk
            }
        )

        logger.info(f"Deleted knowledge item {item_id} from DynamoDB")
        return True

    except Exception as e:
        logger.error(f"Error deleting knowledge item {item_id}: {e}")
        return False

# Add function to update property knowledge status
def update_property_knowledge_status(property_id: str, status: str) -> bool:
    """Update the knowledge status of a property."""
    if not initialize_dynamodb():
        return False

    try:
        # Get the property's PK/SK
        property_pk = f"PROPERTY#{property_id}"
        property_sk = "METADATA"

        # Update the property's knowledge status
        table.update_item(
            Key={
                'PK': property_pk,
                'SK': property_sk
            },
            UpdateExpression="SET KnowledgeStatus = :status, UpdatedAt = :timestamp",
            ExpressionAttributeValues={
                ':status': status,
                ':timestamp': datetime.now(timezone.utc).isoformat()
            }
        )

        logger.info(f"Updated knowledge status of property {property_id} to '{status}'")
        return True

    except Exception as e:
        logger.error(f"Error updating knowledge status for property {property_id}: {e}")
        return False

# Add function to update reservation contacts
def update_reservation_contacts(reservation_id: str, contacts: List[Dict]) -> bool:
    """Update the contacts for a reservation."""
    if not initialize_dynamodb():
        return False

    try:
        # Skip the GSI query since the index doesn't exist, directly use scan
        logger.info(f"Using scan to find reservation {reservation_id}")
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('RESERVATION') &
                          Attr('ReservationId').eq(reservation_id)
        )
        items = response.get('Items', [])

        if not items:
            # Try one more approach - scan with SK containing reservation ID
            logger.info(f"Trying SK scan approach for reservation {reservation_id}")
            response = table.scan(
                FilterExpression=Attr('SK').contains(reservation_id)
            )
            items = response.get('Items', [])

        if not items:
            logger.error(f"Reservation {reservation_id} not found for contacts update")
            return False

        # Get the primary PK/SK for the reservation
        reservation_item = items[0]
        pk = reservation_item.get('PK')
        sk = reservation_item.get('SK')

        logger.info(f"Found reservation with PK={pk}, SK={sk}")

        # Update the reservation with the new contacts
        table.update_item(
            Key={
                'PK': pk,
                'SK': sk
            },
            UpdateExpression="SET AdditionalContacts = :contacts, UpdatedAt = :timestamp",
            ExpressionAttributeValues={
                ':contacts': contacts,
                ':timestamp': datetime.now(timezone.utc).isoformat()
            }
        )

        logger.info(f"Updated contacts for reservation {reservation_id}")
        return True

    except Exception as e:
        logger.error(f"Error updating contacts for reservation {reservation_id}: {e}")
        return False

# Add function to scan all reservations for debugging purposes
def scan_all_reservations() -> List[Dict]:
    """Scan all reservations in the system for debugging purposes."""
    if not initialize_dynamodb():
        return []

    try:
        # Use scan with filter for reservations
        response = table.scan(
            FilterExpression=Attr('EntityType').eq('RESERVATION')
        )
        reservations = response.get('Items', [])
        logger.info(f"Found {len(reservations)} total reservations in the system")
        return reservations
    except Exception as e:
        logger.error(f"Error scanning all reservations: {e}")
        return []

# Add function to create a test reservation for a guest to help with debugging
def create_test_reservation_for_guest(phone_number: str, guest_name: str = None) -> Optional[str]:
    """
    Creates a test reservation for a guest to help with debugging.
    This is intended for development/testing purposes only.

    Args:
        phone_number: The phone number of the guest
        guest_name: Optional name of the guest, defaults to "Test Guest"

    Returns:
        The reservation ID if creation was successful, None otherwise
    """
    if not initialize_dynamodb():
        return None

    if not phone_number:
        logger.error("Cannot create test reservation: phone number is required")
        return None

    # Generate a unique ID for the reservation
    import uuid
    reservation_id = str(uuid.uuid4())

    # Generate a unique ID for the property if needed
    property_id = "test-property-123"

    # Get dates for reservation (current date +/- 3 days)
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=3)).isoformat()
    end_date = (now + timedelta(days=3)).isoformat()

    # Create the reservation
    reservation_data = {
        'PK': f"PROPERTY#{property_id}",
        'SK': f"RESERVATION#{reservation_id}",
        'EntityType': 'RESERVATION',
        'ReservationId': reservation_id,
        'PropertyId': property_id,
        'PropertyName': 'Test Beach House',
        'PropertyAddress': '123 Ocean Drive, Malibu, CA',
        'StartDate': start_date,
        'EndDate': end_date,
        'GuestName': guest_name or "Test Guest",
        'GuestPhoneNumber': phone_number,
        'GuestPhoneLast4': phone_number[-4:] if len(phone_number) >= 4 else phone_number,
        'AdditionalContacts': [
            {
                'name': 'Additional Guest',
                'phone': phone_number,
                'relationship': 'Family'
            }
        ],
        'Summary': 'Test reservation for debugging',
        'CreatedAt': now.isoformat(),
        'UpdatedAt': now.isoformat(),
    }

    # Add GSIs for querying
    reservation_data['GSI1PK'] = f"PHONE#{phone_number}"
    reservation_data['GSI1SK'] = f"RESERVATION#{reservation_id}"
    reservation_data['GSI2PK'] = "RESERVATION"
    reservation_data['GSI2SK'] = start_date

    try:
        table.put_item(Item=reservation_data)
        logger.info(f"Created test reservation {reservation_id} for guest with phone {phone_number}")
        return reservation_id
    except Exception as e:
        logger.error(f"Error creating test reservation: {e}")
        return None

# Add function to update reservation
def update_reservation(reservation_id: str, update_data: Dict) -> bool:
    """Update a reservation with new data."""
    if not initialize_dynamodb():
        return False

    try:
        # First we need to find the reservation to get its PK and SK
        response = table.scan(
            FilterExpression=Attr('SK').eq(f"RESERVATION#{reservation_id}")
        )

        items = response.get('Items', [])
        if not items:
            logger.error(f"Reservation {reservation_id} not found for update")
            return False

        # Get the primary keys
        reservation_item = items[0]
        pk = reservation_item.get('PK')
        sk = reservation_item.get('SK')

        # Build update expression and attribute values
        update_expression_parts = ["set #updated_at = :updated_at"]
        expression_attr_values = {
            ':updated_at': datetime.now(timezone.utc).isoformat()
        }

        # Build expression attribute names to handle reserved words
        expression_attr_names = {
            '#updated_at': 'UpdatedAt'
        }

        # Process each field in the update data
        for key, value in update_data.items():
            # Skip UpdatedAt as it's already handled
            if key == 'UpdatedAt':
                continue

            # Use expression attribute name to avoid reserved keyword issues
            name_placeholder = f"#{key}"
            update_expression_parts.append(f"{name_placeholder} = :{key}")

            # Add the attribute name mapping
            expression_attr_names[name_placeholder] = key

            # Add the attribute value
            expression_attr_values[f":{key}"] = value

        # Build final update expression
        update_expression = " , ".join(update_expression_parts)

        logger.info(f"Update expression for reservation {reservation_id}: {update_expression}")

        # Execute the update
        table.update_item(
            Key={
                'PK': pk,
                'SK': sk
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attr_names,
            ExpressionAttributeValues=expression_attr_values
        )

        logger.info(f"Updated reservation {reservation_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating reservation {reservation_id}: {e}")
        return False

# Add function to delete reservation
def delete_reservation(reservation_id: str) -> bool:
    """Delete a reservation by ID."""
    if not initialize_dynamodb():
        return False

    try:
        # First we need to find the reservation to get its PK and SK
        response = table.scan(
            FilterExpression=Attr('SK').eq(f"RESERVATION#{reservation_id}")
        )

        items = response.get('Items', [])
        if not items:
            logger.error(f"Reservation {reservation_id} not found for deletion")
            return False

        # Get the primary keys
        reservation_item = items[0]
        pk = reservation_item.get('PK')
        sk = reservation_item.get('SK')

        # Delete the reservation
        table.delete_item(
            Key={
                'PK': pk,
                'SK': sk
            }
        )

        logger.info(f"Deleted reservation {reservation_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting reservation {reservation_id}: {e}")
        return False

# Initialize DynamoDB client at module load time
initialize_dynamodb()