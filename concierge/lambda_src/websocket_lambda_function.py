import boto3
import os
import json
import logging
import google.genai as genai
# Keep legacy import for backward compatibility
import google.generativeai as legacy_genai
import traceback
import sys
import time
from datetime import datetime

# Add multiple potential paths to find utils
# Lambda has a different structure, so we need to be flexible
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # Try current directory too
sys.path.append('/var/task')  # Standard Lambda deployment path

# Add parent directory to sys.path to find the 'utils' package
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import RAG functionality with fallback
rag_available = False
try:
    # First try direct import (might work if utils is at same level as lambda_src)
    from utils.ai_helpers import process_query_with_rag, generate_embedding, format_prompt_with_rag
    rag_available = True
    print("Successfully imported RAG utilities from utils.ai_helpers")
except ImportError:
    # Try relative import (for when lambda_src and utils are siblings)
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from utils.ai_helpers import process_query_with_rag, generate_embedding, format_prompt_with_rag
        rag_available = True
        print("Successfully imported RAG utilities via relative path")
    except ImportError as e:
        # Try alternative import path for both Lambda handler paths
        try:
            # Try as if the handler is: lambda_src.websocket_lambda_function.lambda_handler
            import utils.ai_helpers
            process_query_with_rag = utils.ai_helpers.process_query_with_rag
            generate_embedding = utils.ai_helpers.generate_embedding
            format_prompt_with_rag = utils.ai_helpers.format_prompt_with_rag
            rag_available = True
            print("Successfully imported RAG utilities via alternative path 1")
        except ImportError:
            try:
                # Try as if we're inside the lambda_src directory
                import importlib.util
                print(f"Current working directory: {os.getcwd()}")
                print(f"Directory contents: {os.listdir('.')}")
                print(f"Parent directory contents: {os.listdir('..')}")

                # Last resort - try to construct the path manually
                if os.path.exists("../utils/ai_helpers.py"):
                    spec = importlib.util.spec_from_file_location("ai_helpers", "../utils/ai_helpers.py")
                    ai_helpers = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(ai_helpers)

                    process_query_with_rag = ai_helpers.process_query_with_rag
                    generate_embedding = ai_helpers.generate_embedding
                    format_prompt_with_rag = ai_helpers.format_prompt_with_rag
                    rag_available = True
                    print("Successfully imported RAG utilities via file location")
                else:
                    print("Could not find ai_helpers.py in expected locations")
                    rag_available = False
            except Exception as final_e:
                print(f"Final import attempt failed: {str(final_e)}")
                print(f"Current sys.path: {sys.path}")
                print("Will use fallback implementation")
                rag_available = False

# Import Firebase functionality with fallback
firebase_available = False
try:
    # First try direct import
    from utils.firestore_client import initialize_firebase, get_firestore_client
    firebase_available = True
    print("Successfully imported Firebase utilities from utils.firestore_client")
except ImportError:
    # Try relative import
    try:
        from concierge.utils.firestore_client import initialize_firebase, get_firestore_client
        firebase_available = True
        print("Successfully imported Firebase utilities via relative path")
    except ImportError as e:
        print(f"Failed to import Firebase utilities: {e}")
        firebase_available = False

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client (outside handler for potential reuse)
dynamodb = boto3.resource('dynamodb')
connections_table = None
table_name = os.getenv('CONNECTIONS_TABLE_NAME')

# Initialize Gemini configuration
gemini_initialized = False
GEMINI_MODEL = 'gemini-2.0-flash'

# Check and log environment variables
def check_env_variables():
    """Check and log status of required environment variables."""
    # List of required variables
    required_vars = [
        'CONNECTIONS_TABLE_NAME',
        'GOOGLE_APPLICATION_CREDENTIALS',
        'GEMINI_API_KEY',
        'DYNAMODB_TABLE_NAME'
    ]

    # List of optional variables with defaults
    optional_vars = {
        'GEMINI_MODEL': 'gemini-2.0-flash',  # Default model name
        'FIRESTORE_SIMILARITY_THRESHOLD': '0.7',  # Default similarity threshold for RAG
        'FIRESTORE_MAX_RESULTS': '10',       # Default max results for RAG
        'DEBUG_MODE': 'false'                # Debug mode off by default
    }

    # Check required variables
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
            logger.error(f"{var} environment variable not set.")

    # Set defaults for optional variables if not present
    for var, default in optional_vars.items():
        if not os.environ.get(var) and default is not None:
            os.environ[var] = default
            logger.info(f"Setting default value for {var}: {default}")
        elif os.environ.get(var):
            logger.info(f"{var} is set to: {os.environ.get(var)}")

    # Log the status of environment variables
    if not missing_vars:
        logger.info("All required environment variables are set.")
        return True
    else:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False

# Log environment status at module startup
env_status = check_env_variables()
if not env_status:
    logger.warning("Some required environment variables are missing - functionality may be limited")

def configure_gemini():
    global gemini_initialized
    gemini_api_key = os.environ.get('GEMINI_API_KEY')

    if gemini_api_key:
        try:
            # For the new google-genai SDK, we don't need to configure globally
            # The client is created per request with the API key
            logger.info("Gemini API Key available for new SDK.")
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

# Try to configure Gemini at module load time
configure_gemini()

if table_name:
    try:
        connections_table = dynamodb.Table(table_name)
        # Optional: Make a simple call to check if table exists/is accessible
        connections_table.load()
        logger.info(f"Successfully connected to DynamoDB table: {table_name}")
    except Exception as e:
        logger.error(f"Failed to connect to DynamoDB table '{table_name}': {e}. WebSocket functionality will be impaired.")
        connections_table = None # Ensure it's None if connection failed
else:
    logger.error("CONNECTIONS_TABLE_NAME environment variable not set. WebSocket functionality will be disabled.")

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

                # Query for the user with this host ID
                user_response = users_table.get_item(
                    Key={
                        'PK': f"USER#{host_id}",
                        'SK': "PROFILE"
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

        # Check essential fields and log their status
        has_name = property_context.get('name') != f'Property {property_id}'
        has_host = property_context.get('hostName') not in ['the host', 'Your Host']
        has_address = 'address' in property_context or 'location' in property_context
        has_wifi = 'wifiNetwork' in property_context or 'wifiPassword' in property_context

        logger.info(f"Essential fields status - Name: {has_name}, Host: {has_host}, Address: {has_address}, WiFi: {has_wifi}")

        # Log detailed field information for debugging
        for key, value in property_context.items():
            # Mask sensitive information in logs
            if key == 'wifiPassword':
                masked_value = '*' * len(str(value)) if value else 'Not set'
                logger.info(f"Field {key}={masked_value}")
            else:
                # Truncate long values
                log_value = str(value)
                if len(log_value) > 100:
                    log_value = log_value[:100] + '...'
                logger.info(f"Field {key}={log_value}")

        return property_context
    except Exception as e:
        logger.error(f"Error fetching property info: {e}")
        traceback.print_exc()
        return None

async def process_with_rag(connection_id, _, property_id, message, logger, guest_name="", system_prompt=""):
    """Process a message using the RAG system."""
    try:
        # Get timestamp for conversation history
        timestamp = datetime.now().isoformat()

        # Log RAG processing attempt
        logger.info(f"Processing message with enhanced RAG system for property_id={property_id}")

        # Fetch property information from DynamoDB
        property_info = await fetch_property_info(property_id)

        # If we couldn't fetch property info, use a basic context
        if not property_info:
            logger.warning(f"Could not fetch property info for property_id={property_id}. Using basic context.")
            property_info = {
                "name": f"Property {property_id}",
                "hostName": "Your Host",
                "property_type": "accommodation"
            }

        # Add guest name to property info if available
        if guest_name:
            property_info["guestName"] = guest_name
            logger.info(f"Added guest name to property context: {guest_name}")

        # Log the property info we're using
        logger.info(f"Using property info with fields: {', '.join(property_info.keys())}")

        # Get similarity threshold from environment variables
        similarity_threshold = float(os.environ.get('FIRESTORE_SIMILARITY_THRESHOLD', '0.7'))
        logger.info(f"Using Firestore similarity threshold: {similarity_threshold}")

        # Retrieve conversation history for this connection
        conversation_history = await get_conversation_history(connection_id)
        logger.info(f"Retrieved {len(conversation_history)} previous messages for connection {connection_id}")

        # Check if this is a simple message that doesn't need RAG
        simple_messages = ["thank you", "thanks", "ok", "okay", "got it", "bye", "goodbye", "good bye"]
        message_lower = message.lower().strip()

        # Skip RAG for simple messages
        if any(simple_message in message_lower for simple_message in simple_messages) and len(message_lower) < 20:
            logger.info(f"Skipping RAG for simple message: '{message}'")
            response = {
                'found': False,
                'context': "",
                'items': []
            }
        else:
            # Get relevant context using the RAG system
            response = await get_relevant_context(
                message,
                property_id=property_id,
                similarity_threshold=similarity_threshold,
                logger=logger
            )

        # Process the response with the language model
        ai_response = await generate_response_with_model(
            property_id, message, response, conversation_history, system_prompt)

        # Store the new conversation entries
        await store_conversation_entry(connection_id, "user", message, timestamp)
        await store_conversation_entry(connection_id, "assistant", ai_response, datetime.now().isoformat())

        return ai_response
    except Exception as e:
        logger.error(f"Error in process_with_rag: {str(e)}")
        traceback.print_exc()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Error processing message: {str(e)}"})
        }

async def get_conversation_history(connection_id):
    """
    Retrieve conversation history for a connection from DynamoDB.

    Args:
        connection_id (str): The WebSocket connection ID

    Returns:
        list: List of conversation messages in chronological order
    """
    try:
        # Get conversation history from DynamoDB
        response = connections_table.get_item(
            Key={'connectionId': connection_id},
            ProjectionExpression="conversation_history"
        )

        # Extract conversation history if it exists
        if 'Item' in response and 'conversation_history' in response['Item']:
            return response['Item']['conversation_history']
        else:
            logger.info(f"No conversation history found for connection {connection_id}")
            return []
    except Exception as e:
        logger.error(f"Error retrieving conversation history: {e}")
        traceback.print_exc()
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

async def process_with_gemini_fallback(message, conversation_history=None, property_info=None, property_id=None, system_prompt=None):
    """Process a message with Gemini as a fallback when no RAG context is available."""
    try:
        # Ensure Gemini is configured
        configure_gemini()

        # Check if genai is available
        if genai is None:
            logger.error("Gemini API not available")
            return "I'm sorry, I'm having trouble accessing my AI capabilities right now. Please try again later."

        # If we don't have property_info but have property_id, try to fetch it
        if property_info is None and property_id:
            try:
                property_info = await fetch_property_info(property_id)
                logger.info(f"Fetched property info for fallback: {len(property_info.keys()) if property_info else 'None'}")

                # Log key property information fields if available
                if property_info:
                    has_name = 'name' in property_info
                    has_host = 'hostName' in property_info and property_info['hostName'] not in ['the host', 'Your Host']
                    has_address = 'address' in property_info or 'location' in property_info
                    has_wifi = 'wifiNetwork' in property_info or 'wifiPassword' in property_info

                    logger.info(f"Fallback property info - Name: {has_name}, Host: {has_host}, Address: {has_address}, WiFi: {has_wifi}")
            except Exception as e:
                logger.warning(f"Could not fetch property info for fallback: {e}")
                # Continue with None property_info

        # Check if custom system prompt is available
        if system_prompt:
            logger.info(f"Using custom system prompt (length: {len(system_prompt)})")
            # A custom system prompt is available, use it directly
            prompt_parts = [system_prompt]

            # Add conversation history if available
            if conversation_history and len(conversation_history) > 0:
                conversation_context = "\n\nPREVIOUS CONVERSATION:\n"

                # Only include the actual conversation messages, not the system prompt
                for message_entry in conversation_history:
                    role = message_entry.get('role', '')
                    text = message_entry.get('text', '')

                    # Skip empty messages or system messages
                    if not role or not text or role.lower() == 'system':
                        continue

                    # Add the message to the conversation context
                    conversation_context += f"{role.upper()}: {text}\n"

                # Only add conversation context if there are actual messages
                if conversation_context != "\n\nPREVIOUS CONVERSATION:\n":
                    prompt_parts.append(conversation_context)

            # Add the current user message
            prompt_parts.append(f"\nUSER: {message}\nASSISTANT:")

            # Combine all prompt parts
            prompt = "\n".join(prompt_parts)
            logger.info(f"Using custom system prompt - total prompt length: {len(prompt)}")

            # Log a sample of the prompt
            if len(prompt) > 500:
                logger.info(f"Custom prompt sample: {prompt[:200]}...{prompt[-200:]}")
            else:
                logger.info(f"Custom prompt: {prompt}")
        else:
            # Use the format_fallback_prompt function from ai_helpers
            try:
                from utils.ai_helpers import format_fallback_prompt
                prompt = format_fallback_prompt(message, property_info, conversation_history)
                logger.info(f"Using ai_helpers.format_fallback_prompt - prompt length: {len(prompt)}")

                # Log a sample of the prompt
                if len(prompt) > 500:
                    logger.info(f"Fallback prompt sample: {prompt[:200]}...{prompt[-200:]}")
                else:
                    logger.info(f"Fallback prompt: {prompt}")
            except ImportError:
                # Fallback to a very basic prompt if ai_helpers is not available
                logger.warning("Could not import format_fallback_prompt from ai_helpers, using basic prompt")
                # Add guest name handling
                guest_name_instruction = ""
                if guest_name:
                    if guest_name == 'Guest' or not guest_name.strip():
                        guest_name_instruction = " The guest name is currently generic or unavailable. When appropriate during the conversation (such as during initial greetings or when it feels natural), politely ask for their name so you can address them personally. Once they provide their name, use it throughout the conversation to create a more personalized experience."
                    else:
                        guest_name_instruction = f" The guest's name is {guest_name}. Use their name naturally throughout the conversation to create a personalized experience."
                else:
                    guest_name_instruction = " The guest name is not available. When appropriate during the conversation (such as during initial greetings or when it feels natural), politely ask for their name so you can address them personally. Once they provide their name, use it throughout the conversation to create a more personalized experience."
                
                prompt_parts = [
                    "You are Staycee, a helpful concierge assistant for property guests. " +
                    "Provide a polite, helpful response to the guest." + guest_name_instruction + " " +
                    "\n\nIMPORTANT - YOUR CAPABILITIES AND LIMITATIONS: " +
                    "You are an AI assistant that can ONLY: " +
                    "- Answer questions about the property using the information provided " +
                    "- Search for local information (restaurants, attractions, services, etc.) using web search " +
                    "- Provide helpful suggestions and recommendations based on available information " +
                    "\n\nYou CANNOT: " +
                    "- Contact the host, neighbors, or any other people on behalf of the guest " +
                    "- Make reservations, bookings, or appointments " +
                    "- Control any property systems (lights, temperature, appliances, etc.) " +
                    "- Arrange services, deliveries, or maintenance " +
                    "- Take any physical actions or interventions " +
                    "- Resolve issues that require human intervention " +
                    "\n\nFor ANY situation that requires action beyond providing information, you MUST suggest that the guest contact the host directly. This includes but is not limited to: " +
                    "- Noise complaints or neighbor issues " +
                    "- Maintenance problems or repairs needed " +
                    "- Missing amenities or supplies " +
                    "- Property access issues " +
                    "- Emergency situations requiring immediate human response " +
                    "- Any requests for services or interventions " +
                    "\n\nAlways be clear that you are an informational assistant only and cannot take actions on the guest's behalf."
                ]

                # Add property info if available
                if property_info:
                    property_text = "PROPERTY INFORMATION:\n"
                    if 'name' in property_info:
                        property_text += f"Property name: {property_info['name']}\n"
                    if 'hostName' in property_info:
                        property_text += f"Host: {property_info['hostName']}\n"
                    elif 'HostId' in property_info:
                        # Use a generic host name instead of the ID
                        property_text += f"Host: Your Host\n"
                    if 'address' in property_info:
                        property_text += f"Address: {property_info['address']}\n"
                    elif 'location' in property_info:
                        property_text += f"Location: {property_info['location']}\n"
                    if 'wifiNetwork' in property_info:
                        property_text += f"WiFi Network: {property_info['wifiNetwork']}\n"
                    if 'wifiPassword' in property_info:
                        property_text += f"WiFi Password: {property_info['wifiPassword']}\n"
                    prompt_parts.append(property_text)

                # Add conversation history if available
                if conversation_history and len(conversation_history) > 0:
                    conversation_context = "PREVIOUS CONVERSATION:\n"

                    # Only include the actual conversation messages, not the system prompt
                    for message_entry in conversation_history:
                        role = message_entry.get('role', '')
                        text = message_entry.get('text', '')

                        # Skip empty messages or system messages
                        if not role or not text or role.lower() == 'system':
                            continue

                        # Add the message to the conversation context
                        conversation_context += f"{role.upper()}: {text}\n"

                    # Only add conversation context if there are actual messages
                    if conversation_context != "PREVIOUS CONVERSATION:\n":
                        prompt_parts.append(conversation_context)

                # Add the current user message
                prompt_parts.append(f"\nUSER: {message}\nASSISTANT:")

                # Combine all prompt parts
                prompt = "\n".join(prompt_parts)
                logger.info(f"Basic fallback prompt length: {len(prompt)}")

        # Generate response from Gemini with Google Search tool using new SDK
        try:
            # Create client with the new google-genai SDK
            logger.info("Initializing Google GenAI client with Google Search tool")
            
            client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
            
            # Use the new SDK syntax for Google Search
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())]
                )
            )
            
            logger.info("Successfully called Gemini with Google Search tool using new SDK")

        except Exception as tool_error:
            # Fallback to regular generation if Google Search tool fails
            logger.warning(f"Google Search tool failed: {tool_error}")
            logger.info("Falling back to regular Gemini generation")
            
            try:
                # Create client for fallback
                client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt
                )
            except Exception as fallback_error:
                logger.error(f"Fallback generation also failed: {fallback_error}")
                raise fallback_error

        # Extract text from response
        if response and hasattr(response, 'text'):
            response_text = response.text
            logger.info(f"Fallback Gemini response length: {len(response_text)}")

            # Log a preview of the response (truncated if very long)
            if len(response_text) > 500:
                logger.info(f"Fallback response (truncated): {response_text[:200]}...{response_text[-200:]}")
            else:
                logger.info(f"Fallback response: {response_text}")

            return response_text
        else:
            logger.error(f"Empty or invalid response from fallback Gemini: {response}")
            return "I'm sorry, I don't have enough information to assist with that. Is there something else I can help with?"

    except Exception as e:
        logger.error(f"Error in process_with_gemini_fallback: {e}")
        traceback.print_exc()
        return "I'm having trouble processing your request at the moment. How else can I assist you with your stay?"

# Add the missing async wrapper functions for the RAG system
async def get_relevant_context(query_text, property_id, similarity_threshold=0.25, logger=None):
    """
    Async wrapper for the synchronous get_relevant_context function from ai_helpers.

    This function specifically handles the case where the ai_helpers function is
    imported but not async-compatible with the WebSocket Lambda.
    """
    try:
        if logger is None:
            logger = logging.getLogger()

        # Import the synchronous version if available
        from utils.ai_helpers import get_relevant_context as sync_get_relevant_context

        # Log that we're using the synchronous function
        logger.info(f"Using synchronous get_relevant_context with query: '{query_text[:50]}...'")

        # Call the synchronous function
        results = sync_get_relevant_context(
            query_text=query_text,
            property_id=property_id,
            threshold=similarity_threshold
        )

        logger.info(f"Got RAG results: found={results.get('found', False)}, items={len(results.get('items', []))}")
        return results
    except Exception as e:
        logger.error(f"Error in async get_relevant_context wrapper: {e}")
        traceback.print_exc()
        return {
            'found': False,
            'context': "",
            'items': [],
            'error': str(e)
        }

async def generate_response_with_model(property_id, message, rag_results, conversation_history=None, system_prompt=None):
    """
    Generate a response using the language model with RAG results.

    This function serves as a bridge between the RAG system and the final response.
    """
    try:
        # Get the property info (may have been passed earlier)
        property_info = await fetch_property_info(property_id)

        if property_info:
            logger.info(f"Retrieved property info with {len(property_info.keys())} fields for response generation")

            # Log key information categories available
            has_name = 'name' in property_info
            has_host = 'hostName' in property_info and property_info['hostName'] not in ['the host', 'Your Host']
            has_address = 'address' in property_info or 'location' in property_info
            has_wifi = 'wifiNetwork' in property_info or 'wifiPassword' in property_info

            logger.info(f"Property info contains - Name: {has_name}, Host: {has_host}, Address: {has_address}, WiFi: {has_wifi}")
        else:
            logger.warning(f"Could not retrieve property info for property_id: {property_id}")

        # Check if we found any relevant context
        if rag_results and rag_results.get('found', False):
            logger.info(f"Using RAG context with {len(rag_results.get('items', []))} items")

            # Import the function if available
            from utils.ai_helpers import process_query_with_rag

            # Process with RAG, passing conversation history and system prompt
            result = process_query_with_rag(message, property_id, property_info, conversation_history, system_prompt)
            logger.info("Successfully processed query with RAG")

            # Extract the text response
            if result and 'response' in result:
                return result['response']
            else:
                logger.warning("process_query_with_rag returned no response, falling back to Gemini")
                return await process_with_gemini_fallback(message, conversation_history, property_info, property_id, system_prompt)
        else:
            logger.info("No RAG context found, using Gemini fallback")
            return await process_with_gemini_fallback(message, conversation_history, property_info, property_id, system_prompt)
    except Exception as e:
        logger.error(f"Error generating response with model: {e}")
        traceback.print_exc()
        return "I'm sorry, I encountered an error while processing your request. Please try again later."

def lambda_handler(event, context):
    # Check if table initialization failed earlier
    if connections_table is None:
        logger.error("DynamoDB table is not available. Cannot process WebSocket event.")
        # Return 500 for connect/default, 200 for disconnect (as client is gone anyway)
        route_key = event.get('requestContext', {}).get('routeKey')
        status_code = 200 if route_key == '$disconnect' else 500
        return {'statusCode': status_code, 'body': 'Internal server configuration error.'}

    # Use asyncio.run to handle the async logic
    import asyncio
    return asyncio.run(_process_event(event, context))

async def _process_event(event, _):
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

    logger.info(f"Received event for route: {route_key} from connection: {connection_id}")

    try:
        if route_key == '$connect':
            # Log detailed connection info for debugging
            logger.info(f"WebSocket $connect event received: {json.dumps(event)}")

            # Extract query string parameters if any
            query_params = event.get('queryStringParameters', {}) or {}
            if query_params:
                logger.info(f"Connect query parameters: {query_params}")

            # Simple connection registration - with more error handling
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
            # Simple connection deregistration
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

                # Get or set property ID in connection attributes
                property_id = None

                # Handle different message types
                if message_type == 'auth':
                    # Handle authentication message (with token)
                    token = payload.get('token', '')
                    # Get property_id directly from the payload again
                    property_id = payload.get('property_id', '')
                    # Get guest_name from payload
                    guest_name = payload.get('guest_name', '')
                    # Get system_prompt from payload
                    system_prompt = payload.get('system_prompt', '')

                    logger.info(f"Auth request received with token length: {len(token) if token else 0}, property_id: {property_id}, guest_name present: {'Yes' if guest_name else 'No'}, system_prompt length: {len(system_prompt) if system_prompt else 0}")

                    # Basic validation: Check if token and property_id are present
                    if not token:
                        logger.warning("Auth message received without a token.")
                        return {'statusCode': 401, 'body': 'Auth token missing.'}
                    if not property_id:
                        logger.warning("Auth message received without property_id.")
                        # Decide if this is acceptable. If not, return error:
                        # return {'statusCode': 400, 'body': 'Property ID missing.'}
                        pass # Allow connection even without property_id for now

                    # Store token, property_id, guest_name and system_prompt in DynamoDB
                    # Use expression attribute names to escape reserved keyword "token"
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

                    # Add system_prompt if it exists in the payload
                    if system_prompt:
                        update_expression += ", system_prompt = :sprmt"
                        expression_values[':sprmt'] = system_prompt
                        logger.info(f"Storing system prompt with length: {len(system_prompt)}")

                    try: # Keep try-except around the DB update
                        connections_table.update_item(
                            Key={'connectionId': connection_id},
                            UpdateExpression=update_expression,
                            ExpressionAttributeValues=expression_values,
                            ExpressionAttributeNames=expression_attribute_names  # Add attribute names parameter
                        )
                        logger.info(f"Updated connection {connection_id} with auth status, property_id, guest_name, and system_prompt")
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

                elif message_type == 'message':
                    # Handle regular message
                    user_message = payload.get('message', '')
                    # Try to get property_id from message payload first
                    property_id = payload.get('property_id', '')
                    logger.info(f"Message from client: {user_message}, property_id from payload: {property_id}")

                    # If property_id not in payload, try to get from stored connection data
                    guest_name = ""
                    system_prompt = ""
                    if not property_id:
                        try:
                            # Get property_id, guest_name and system_prompt from DynamoDB for this connection
                            response = connections_table.get_item(
                                Key={'connectionId': connection_id},
                                ProjectionExpression="property_id, authenticated, #tkn, guest_name, system_prompt",
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
                                if 'system_prompt' in response['Item']:
                                    system_prompt = response['Item']['system_prompt']
                                    logger.info(f"Retrieved system_prompt from connection record (length: {len(system_prompt)})")
                            else:
                                logger.warning(f"No connection data found in DynamoDB for connection {connection_id}")
                        except Exception as e:
                            logger.error(f"Error retrieving data from connections table: {e}")

                    if not property_id:
                        logger.warning("No property_id available for processing. Using fallback.")
                        # Since no property_id, create special error message for the user
                        response_message = "I don't have any specific information about this property yet. It seems we're missing the property ID. Please try reconnecting or contact support."
                    elif gemini_initialized:
                        # Log the property ID being used
                        logger.info(f"Processing message with property_id: {property_id}, guest_name: {guest_name}, system_prompt length: {len(system_prompt) if system_prompt else 0}")

                        # Try to fetch property info first for better response
                        property_info = None
                        try:
                            property_info = await fetch_property_info(property_id)
                            logger.info(f"Successfully fetched property info with {len(property_info.keys()) if property_info else 0} fields")
                        except Exception as e:
                            logger.warning(f"Could not fetch property info: {e}")

                        # Use RAG to generate a response
                        response_message = await process_with_rag(connection_id, connection_id, property_id, user_message, logger, guest_name, system_prompt)

                        # If response indicates no context, send a more helpful error
                        if isinstance(response_message, str) and "I don't have that specific information" in response_message:
                            logger.warning(f"No relevant context found for property_id: {property_id}")
                    else:
                        # Fallback if Gemini is not available
                        logger.warning("Gemini not configured, using fallback response")
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

                elif message_type == 'ping':
                    # Handle ping message (for connection keepalive)
                    logger.info(f"Received ping from {connection_id}")

                    # Send pong response to keep connection alive
                    apigw_management.post_to_connection(
                        ConnectionId=connection_id,
                        Data=json.dumps({
                            "type": "pong",
                            "payload": {"message": "Connection alive"},
                            "timestamp": message_data.get('timestamp', 0)
                        }).encode('utf-8')
                    )
                    logger.info(f"Sent pong response to {connection_id}")

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

            except apigw_management.exceptions.GoneException:
                logger.warning(f"Connection {connection_id} is gone, removing from table.")
                # Clean up the stale connection from DynamoDB
                try:
                    connections_table.delete_item(Key={'connectionId': connection_id})
                except Exception as e:
                    logger.error(f"Error cleaning up stale connection: {e}")

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
