import json
import os
import telnyx
import traceback
import google.genai as genai
from datetime import datetime, timezone
import numpy as np
import math

# --- AWS SDK ---
import boto3
from boto3.dynamodb.conditions import Key, Attr
# --- End AWS SDK --- #

# Import our caching utilities (will remain None if import fails)
try:
    from utils.cache_helpers import firestore_cache, get_cached_firestore_client
except ImportError:
    try:
        # Try alternate import path for Lambda environment
        from concierge.utils.cache_helpers import firestore_cache, get_cached_firestore_client
    except ImportError:
        print("Warning: Could not import cache_helpers. Caching will be disabled.")
        firestore_cache = None
        get_cached_firestore_client = None

# --- Telnyx Configuration ---
def configure_telnyx():
    api_key = os.environ.get('TELNYX_API_KEY')
    if api_key:
        telnyx.api_key = api_key
        print("Telnyx API Key configured.")
        return True
    else:
        print("Error: TELNYX_API_KEY environment variable not set.")
        return False

# --- Gemini Configuration ---
def configure_gemini():
    gemini_api_key = os.environ.get('GEMINI_API_KEY')
    if gemini_api_key:
        try:
            # Test creating a client with the new SDK
            client = genai.Client(api_key=gemini_api_key)
            print("Gemini API Key configured with new SDK.")
            return True
        except Exception as e:
            print(f"Error configuring Gemini: {e}")
            traceback.print_exc()
            return False
    else:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return False

# --- Constants / Config (Example) ---
# LanceDB constants removed - migrated to Firestore for vector search
# LANCEDB_URI = os.environ.get("LANCEDB_S3_URI", "/tmp/lancedb") # Default to tmp if not set
# TABLE_NAME = os.environ.get("LANCEDB_TABLE_NAME", "knowledge_base")
TELNYX_SMS_NUMBER = os.environ.get('TELNYX_SMS_NUMBER')
GEMINI_EMBEDDING_MODEL = 'text-embedding-004' # Use the same model as ingestion
GEMINI_EMBEDDING_TASK_TYPE = "RETRIEVAL_DOCUMENT"  # Use the same task type as ingestion

# --- Persistent Connections ---
_firestore_db = None

# --- Initialization (potential cold start impact) ---
dynamodb_client = None
dynamodb_initialized = False
gemini_initialized = False # Add flag for Gemini initialization

def initialize_dynamodb():
    global dynamodb_client, dynamodb_initialized
    if not dynamodb_initialized:
        print("Initializing DynamoDB client...")
        try:
            # Get the table name from environment variable
            table_name = os.environ.get('DYNAMODB_TABLE_NAME')
            if not table_name:
                print("Error: DYNAMODB_TABLE_NAME environment variable not set.")
                return False

            # Initialize DynamoDB client
            dynamodb_client = boto3.resource('dynamodb')
            print(f"Successfully initialized DynamoDB client for table: {table_name}")
            dynamodb_initialized = True
            return True
        except Exception as e:
            # Catch any broader errors during the process
            print(f"Unexpected error during DynamoDB setup: {e}")
            traceback.print_exc()
            # Ensure state reflects failure
            dynamodb_client = None
            dynamodb_initialized = False
            return False
    else:
        # If already initialized, ensure dynamodb_client is set
        if not dynamodb_client:
            try:
                dynamodb_client = boto3.resource('dynamodb')
                print("Re-initialized DynamoDB client on warm start.")
                return True
            except Exception as e:
                print(f"Error re-initializing DynamoDB client on warm start: {e}")
                dynamodb_client = None
                dynamodb_initialized = False
                return False
        return True

def initialize_firebase():
    """
    Initialize Firebase and get a Firestore client.
    Reuses connection across invocations during the Lambda's lifecycle.
    """
    # If we have the get_cached_firestore_client helper, use it
    if get_cached_firestore_client is not None:
        return get_cached_firestore_client()

    # Otherwise use Firebase Admin SDK directly
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        # Check if Firebase app is already initialized
        try:
            app = firebase_admin.get_app()
            print("Firebase app already initialized")
        except ValueError:
            # Initialize Firebase app
            cred_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
            if not cred_path:
                print("GOOGLE_APPLICATION_CREDENTIALS environment variable not set")
                return None

            # Initialize with credentials file
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            print("Firebase app initialized with credentials file")

        # Get Firestore client (environment-aware via central helper if available)
        try:
            from concierge.utils.firestore_client import get_firestore_client as _central_get_client
            db = _central_get_client()
        except Exception:
            db = firestore.client()
        print("Firestore client initialized")
        return db
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        traceback.print_exc()
        return None

def initialize_resources():
    global dynamodb_initialized, gemini_initialized, _firestore_db

    # Initialize Gemini FIRST
    # Use a flag to ensure configure_gemini is called only once effectively
    if not gemini_initialized:
        print("Configuring Gemini...")
        if configure_gemini():
             gemini_initialized = True
        else:
             print("Gemini configuration failed. Embedding will not work.")
             # gemini_initialized remains False

    # Initialize DynamoDB SECOND (dependency for property context)
    initialize_dynamodb()

    # Initialize Firebase THIRD
    _firestore_db = initialize_firebase()
    if _firestore_db:
        print("Firebase initialized successfully.")
    else:
        print("Firebase initialization failed.")


def calculate_cosine_similarity(vec1, vec2):
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score between 0 and 1
    """
    # Convert to numpy arrays if they aren't already
    v1 = np.array(vec1)
    v2 = np.array(vec2)

    # Calculate dot product
    dot_product = np.dot(v1, v2)

    # Calculate magnitudes
    mag1 = np.linalg.norm(v1)
    mag2 = np.linalg.norm(v2)

    # Calculate cosine similarity
    if mag1 > 0 and mag2 > 0:
        return dot_product / (mag1 * mag2)
    else:
        return 0.0

def get_gemini_greeting():
    """Generates a welcome greeting using the Gemini API."""
    try:
        # Use the specific stable model name
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = "Generate a short, friendly, and professional welcome message for someone calling a premium concierge phone service. Start with a greeting like Hello or Welcome."
        print(f"Generating Gemini response with prompt: '{prompt}'")
        response = model.generate_content(prompt)
        # Basic check for response content
        if response.text:
            print(f"Gemini generated greeting: '{response.text}'")
            return response.text
        else:
            print("Error: Gemini response was empty.")
            # Consider checking response.prompt_feedback as well
            if response.prompt_feedback:
                 print(f"Gemini prompt feedback: {response.prompt_feedback}")
            return "Hello, thank you for calling. Please wait a moment." # Fallback
    except Exception as e:
        print(f"Error generating Gemini greeting: {e}")
        traceback.print_exc()
        return "Hello, thank you for calling. Please wait a moment." # Fallback message

# --- Lambda Handler for Telnyx Phone Call Webhooks ---
def lambda_handler(event, context):
    """
    Handles incoming requests from API Gateway, expected to be triggered by Telnyx webhooks.
    Processes phone call events (call.initiated, call.answered, call.hangup) and SMS messages.
    For phone calls, establishes bidirectional audio streaming with the WebSocket server.
    For SMS, retrieves property context based on sender's phone number and uses RAG to generate responses.
    """
    print("Received event:")
    print(json.dumps(event))

    # Configure Telnyx (essential)
    if not configure_telnyx():
        return {'statusCode': 500, 'body': json.dumps('Internal Server Error: Telnyx not configured')}

    # Initialize resources (Firebase, Gemini) - may run on cold start
    initialize_resources() # Safe to call multiple times
    # Use the gemini_initialized flag set by initialize_resources
    gemini_configured = gemini_initialized

    # Check if this is a direct invocation for ingestion
    if 'action' in event and event['action'] == 'ingest':
        qna_id = event.get('qna_id')
        print(f"Processing QnA item: {qna_id}, Action: ingest")

        if not qna_id:
            print("Error: 'qna_id' missing in ingestion event.")
            return {'statusCode': 400, 'body': json.dumps({'error': "Missing 'qna_id'"})}

        if not initialize_dynamodb():
            print("Error: DynamoDB client not initialized. Cannot process ingestion.")
            return {'statusCode': 500, 'body': json.dumps({'error': 'DynamoDB client not initialized'})}

        # Connect to Firestore for ingestion
        db = _firestore_db
        if not db:
            return {'statusCode': 500, 'body': json.dumps({'error': 'Firestore connection failed'})}

        if not gemini_configured:
            print("Error: Gemini not configured. Cannot generate embeddings.")
            return {'statusCode': 500, 'body': json.dumps({'error': 'Gemini not configured'})}

        try:
            # 1. Fetch QnA data from DynamoDB
            table_name = os.environ.get('DYNAMODB_TABLE_NAME')
            table = dynamodb_client.Table(table_name)

            # Construct the key for the knowledge item
            # Format: PROPERTY#{property_id}#ITEM#{source_id}#{item_id}
            # Since we only have the item_id, we need to scan with a filter
            response = table.scan(
                FilterExpression=Attr('SK').contains(qna_id)
            )

            items = response.get('Items', [])
            if not items:
                print(f"Error: QnA item {qna_id} not found in DynamoDB.")
                return {'statusCode': 404, 'body': json.dumps({'error': f'QnA item {qna_id} not found'})}

            # Use the first matching item
            qna_data = items[0]
            question = qna_data.get('Question')
            answer = qna_data.get('Answer')

            # Extract property_id from the PK (format: PROPERTY#{property_id})
            pk = qna_data.get('PK', '')
            property_id = pk.replace('PROPERTY#', '') if pk.startswith('PROPERTY#') else None

            if not question or not answer or not property_id:
                print(f"Error: Missing question, answer, or propertyId in QnA item {qna_id}.")
                return {'statusCode': 400, 'body': json.dumps({'error': 'Incomplete QnA data'})}

            # Combine question and answer for embedding
            text_to_embed = f"Q: {question}\nA: {answer}"

            # 2. Generate Embedding using Gemini
            print(f"Generating embedding for QnA item: {qna_id}")
            client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
            embedding_result = client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=[text_to_embed], # API expects a list
                config={
                    'task_type': GEMINI_EMBEDDING_TASK_TYPE
                }
            )
            if (hasattr(embedding_result, 'embeddings') and
                embedding_result.embeddings and
                len(embedding_result.embeddings) > 0):
                vector = embedding_result.embeddings[0].values
                print("Successfully generated embedding vector.")
            else:
                print(f"Error: Failed to generate embedding for {qna_id}. Response: {embedding_result}")
                raise ValueError("Embedding generation failed")

            # 3. Add/Update data in Firestore
            print(f"Adding/Updating knowledge item {qna_id} in Firestore...")

            # Prepare data for Firestore
            data = {
                'embedding': vector,
                'content': text_to_embed,
                'propertyId': property_id,
                'updatedAt': datetime.now(timezone.utc)
            }

            # Add to Firestore
            doc_ref = db.collection('knowledge_items').document(qna_id)
            doc_ref.set(data)
            print(f"Successfully added/updated knowledge item {qna_id} in Firestore.")

            # 4. Update DynamoDB status to 'ingested'
            table.update_item(
                Key={
                    'PK': qna_data.get('PK'),
                    'SK': qna_data.get('SK')
                },
                UpdateExpression="SET #status = :status, #lastIngested = :timestamp, firestore_status = :firestore_status",
                ExpressionAttributeNames={
                    '#status': 'Status',
                    '#lastIngested': 'LastIngested'
                },
                ExpressionAttributeValues={
                    ':status': 'ingested',
                    ':timestamp': datetime.now(timezone.utc).isoformat(),
                    ':firestore_status': 'ingested'
                }
            )
            print(f"Successfully processed QnA item {qna_id} for action 'ingest'. Marked as 'ingested'.")

            return {'statusCode': 200, 'body': json.dumps({'message': f'Successfully ingested {qna_id}'})}

        except Exception as ingest_e:
            print(f"Error during ingestion process for {qna_id}: {ingest_e}")
            traceback.print_exc()
            return {'statusCode': 500, 'body': json.dumps({'error': f'Ingestion failed for {qna_id}: {str(ingest_e)}'})}

    try:
        # API Gateway HTTP API wraps the original body in a 'body' field,
        # and it might be a JSON string that needs parsing.
        if 'body' in event and isinstance(event['body'], str):
            body = json.loads(event['body'])
        else:
            # Handle cases where body might already be parsed or missing
            body = event.get('body', {})
            if not isinstance(body, dict): # Basic check if body is usable
                 body = {}

        event_data = body.get('data', {})
        event_type = event_data.get('event_type')
        payload = event_data.get('payload', {})
        call_control_id = payload.get('call_control_id')

        print(f"Event Type: {event_type}")
        print(f"Call Control ID: {call_control_id}")

        # --- Call Control Logic ---
        if event_type == 'call.initiated' and payload.get('direction') == 'incoming':
            call_control_id = payload.get('call_control_id')
            print(f"Call Control ID: {call_control_id}")

            # Extract caller's phone number
            caller_number = None
            if 'from' in payload:
                # Handle both formats: string or object with phone_number
                from_value = payload.get('from')
                if isinstance(from_value, str):
                    caller_number = from_value
                elif isinstance(from_value, dict) and 'phone_number' in from_value:
                    caller_number = from_value.get('phone_number')

            print(f"Caller Phone Number: {caller_number}")

            if call_control_id:
                print(f"Answering call {call_control_id} with bidirectional OPUS@16kHz stream...")
                try:
                    # Use the class method create_answer directly
                    websocket_url = os.getenv('WEBSOCKET_URL')
                    if not websocket_url:
                        print("Error: WEBSOCKET_URL environment variable not set.")
                        return {'statusCode': 500, 'body': json.dumps({'error': 'WebSocket URL not configured'})}

                    # Append caller's phone number as a query parameter if available
                    if caller_number:
                        # Add caller's phone number as a query parameter
                        if '?' in websocket_url:
                            websocket_url += f"&caller_number={caller_number}"
                        else:
                            websocket_url += f"?caller_number={caller_number}"
                        print(f"Added caller number to WebSocket URL: {websocket_url}")

                    print(f"Attempting to stream to WebSocket URL: {websocket_url}")
                    # Enhanced bidirectional streaming configuration
                    response = telnyx.Call.create_answer(
                        call_control_id,
                        stream_url=websocket_url,
                        bidirectional=True,
                        stream_bidirectional_codec="OPUS",
                        stream_bidirectional_sampling_rate=16000,
                        stream_track="both_tracks",  # Ensure we're streaming both tracks
                        client_state="gemini_voice_call"  # Add client state for tracking
                    )
                    print(f"Call answered successfully: {response}")
                except Exception as e:
                    print(f"Error answering call {call_control_id}: {e}")
                    traceback.print_exc()
                    return {'statusCode': 500, 'body': json.dumps({'error': f'Error answering call: {str(e)}'})}
            else:
                print("Error: call_control_id missing in call.initiated payload.")
                return {'statusCode': 400, 'body': json.dumps({'error': 'Missing call_control_id'})}

        elif event_type == 'call.answered':
            call_control_id = payload.get('call_control_id')
            print(f"Call Control ID: {call_control_id}")
            print(f"Call {call_control_id} answered. Bidirectional stream established.")

            # No longer speak greeting from here. WebSocket server will handle interaction.
            # --- MODIFICATION END ---
        elif event_type == 'call.hangup':
            call_control_id = body['data']['payload']['call_control_id']
            hangup_cause = body['data']['payload'].get('hangup_cause', 'N/A')
            hangup_source = body['data']['payload'].get('hangup_source', 'N/A')
            print(f"Call {call_control_id} hung up. Cause: {hangup_cause}, Source: {hangup_source}")
        elif event_type == 'call.cost':
            # Existing logic for call.cost - can be refined later if needed
            call_control_id = body['data']['payload']['call_control_id']
            print(f"Received call.cost event for {call_control_id}.") # Simplified log for now
        elif event_type == 'message.received':
            print("Received message.received event.")

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
            # Use 'id' for message ID based on common Telnyx webhook structure
            message_id = event_data.get('id') # Message ID is often outside payload

            print(f"SMS From: {sender_number}, To: {telnyx_to_number}, Text: '{message_text}', Message ID: {message_id}")

            # Basic validation
            if not sender_number or not message_text:
                print("Error: Missing sender number or message text in payload.")
                # Acknowledge webhook, but indicate bad request
                return { 'statusCode': 400, 'body': json.dumps('Bad Request: Missing sender or text') }

            if not TELNYX_SMS_NUMBER:
                 print("Error: TELNYX_SMS_NUMBER environment variable not set. Cannot send reply.")
                 # Acknowledge webhook, but indicate server config issue
                 return { 'statusCode': 500, 'body': json.dumps('Internal Server Error: Sending number not configured') }

            # --- NEW: Identify Property based on Sender and Active Reservation ---
            identified_property_id = None
            guest_name = None # Store guest name if available

            # Check if DynamoDB is initialized
            if initialize_dynamodb():
                try:
                    # Get the table name from environment variable
                    table_name = os.environ.get('DYNAMODB_TABLE_NAME')
                    table = dynamodb_client.Table(table_name)

                    # Get current time for active reservation check
                    now_utc = datetime.now(timezone.utc).isoformat()

                    print(f"Querying reservations for phone {sender_number} active at {now_utc}")

                    # Query reservations where this phone is the primary guest phone using GSI1
                    response = table.query(
                        IndexName="GSI1",
                        KeyConditionExpression=Key('GSI1PK').eq(f"PHONE#{sender_number}")
                    )

                    # Filter for active reservations
                    active_reservations = []
                    for res in response.get('Items', []):
                        start_date = res.get('StartDate')
                        end_date = res.get('EndDate')

                        if start_date and end_date and start_date <= now_utc and end_date > now_utc:
                            active_reservations.append(res)

                    if len(active_reservations) == 1:
                        res_data = active_reservations[0]
                        # Extract property_id from the PK (format: PROPERTY#{property_id})
                        pk = res_data.get('PK', '')
                        identified_property_id = pk.replace('PROPERTY#', '') if pk.startswith('PROPERTY#') else None
                        guest_name = res_data.get('GuestName')
                        print(f"Found active reservation for property ID: {identified_property_id}")
                    elif len(active_reservations) == 0:
                        print("No active reservation found for this sender.")
                    else:
                        # Multiple active reservations found - how to handle?
                        # For now, log warning and don't select a specific property.
                        print(f"Warning: Found {len(active_reservations)} active reservations for sender {sender_number}. Cannot uniquely identify property.")
                        # Optionally, could try to find the most relevant one (e.g., latest start date)

                except Exception as dynamodb_e:
                    print(f"Error querying DynamoDB for reservations: {dynamodb_e}")
                    traceback.print_exc()
            else:
                print("DynamoDB client not initialized, cannot query reservations.")
            # --- END: Identify Property --- #

            knowledge_response = "" # Initialize knowledge_response
            generated_response = "I received your message. Processing..." # Placeholder

            # --- RAG Pipeline ---
            try:
                # 2. RAG: Retrieve relevant knowledge (if property identified and RAG resources available)
                # Check if property is identified AND Gemini is configured for embedding
                if identified_property_id and gemini_configured:
                    # Check cache first if available
                    cached_result = None
                    if firestore_cache is not None:
                        cached_result = firestore_cache.get(identified_property_id, message_text, 'knowledge_items')
                        if cached_result is not None and cached_result.get('found'):
                            print(f"Using cached knowledge response for property {identified_property_id}")
                            knowledge_response = cached_result.get('context', "")
                            print(f"Found cached knowledge: {knowledge_response[:100]}...")

                    # Only proceed with RAG lookup if no cache hit
                    if cached_result is None:
                        # Use Firestore for RAG
                        db = _firestore_db
                        if not db:
                            print("Error: Firestore not initialized. Skipping knowledge lookup.")
                        else:
                            print("Performing RAG lookup...")
                            try:
                                # --- Generate Embedding with Gemini ---
                                try:
                                    print(f"Generating query vector using Gemini ({GEMINI_EMBEDDING_MODEL}) for: '{message_text[:50]}...' ")
                                    # Embed the incoming message text using the Gemini API
                                    client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
                                    embedding_result = client.models.embed_content(
                                        model=GEMINI_EMBEDDING_MODEL,
                                        contents=[message_text], # API expects a list of texts
                                        config={
                                            'task_type': GEMINI_EMBEDDING_TASK_TYPE
                                        }
                                    )

                                    # Check result and extract the vector (it's a list containing one embedding)
                                    if (hasattr(embedding_result, 'embeddings') and
                                        embedding_result.embeddings and
                                        len(embedding_result.embeddings) > 0):
                                        query_vector = embedding_result.embeddings[0].values
                                        print("Successfully generated query vector.")
                                    else:
                                        print(f"Error: Unexpected response format from Gemini embedding API: {embedding_result}")
                                        raise ValueError("Invalid response from Gemini embedding API")

                                except Exception as embed_e:
                                    print(f"Error generating Gemini embedding for query: {embed_e}")
                                    traceback.print_exc()
                                    # If embedding fails, we cannot search
                                    query_vector = None # Ensure query_vector is None so search is skipped
                                # --- End Gemini Embedding ---

                                # Search Firestore, filtering by property_id (only if embedding succeeded)
                                if query_vector:
                                    try:
                                        # Perform vector search in Firestore
                                        knowledge_collection = db.collection('knowledge_items')

                                        try:
                                            # Use Firestore's native vector search if available
                                            # This requires a vector index to be set up in the Firebase console
                                            print(f"Performing vector search in Firestore for property {identified_property_id}")

                                            # Create a vector query with property filter
                                            vector_query = knowledge_collection.where('propertyId', '==', identified_property_id)

                                            # Add vector search parameters
                                            # Note: This is the syntax for Firestore vector search
                                            # The actual implementation might vary based on the Firestore version
                                            vector_search_params = {
                                                'vector': query_vector,
                                                'field': 'embedding',
                                                'distance_measure': 'COSINE',
                                                'limit': 3
                                            }

                                            # Execute the query with vector search
                                            # Note: The actual API might be different depending on the Firestore version
                                            # This is a placeholder for the actual vector search API
                                            print("Attempting to use native vector search in Firestore")

                                            # Fallback to manual vector search if native search fails or isn't available
                                            # Get all documents for the property
                                            results = vector_query.get()

                                            # Process results
                                            if results:
                                                # Convert to list of documents
                                                docs = list(results)
                                                print(f"Found {len(docs)} knowledge items for property {identified_property_id}")

                                                # Calculate vector similarity for each document
                                                scored_docs = []
                                                for doc in docs:
                                                    doc_data = doc.to_dict()
                                                    if 'embedding' in doc_data:
                                                        # Calculate cosine similarity
                                                        similarity = calculate_cosine_similarity(query_vector, doc_data['embedding'])
                                                        scored_docs.append((doc, similarity))

                                                # Sort by similarity (highest first)
                                                scored_docs.sort(key=lambda x: x[1], reverse=True)

                                                # Take top 3 results
                                                top_docs = scored_docs[:3]
                                        except Exception as vector_search_err:
                                            print(f"Error with vector search: {vector_search_err}")
                                            # Fallback to empty results
                                            top_docs = []

                                        if top_docs:
                                            print(f"Found {len(top_docs)} relevant documents.")
                                            # Extract content from results
                                            knowledge_texts = []
                                            for doc, score in top_docs:
                                                doc_data = doc.to_dict()
                                                content = doc_data.get('content', '')
                                                if content:
                                                    knowledge_texts.append(content)

                                            # Combine the text from the results
                                            knowledge_snippets = "\n".join(knowledge_texts)
                                            knowledge_response = f"Based on the information I have:\n{knowledge_snippets}"

                                            # Cache the successful results
                                            if firestore_cache is not None:
                                                cache_data = {
                                                    'found': True,
                                                    'context': knowledge_response,
                                                    'items': [{'text': text} for text in knowledge_texts]
                                                }
                                                firestore_cache.set(identified_property_id, message_text, 'knowledge_items', cache_data)
                                                print(f"Cached knowledge response for property {identified_property_id}")
                                        else:
                                            print("No relevant documents found in Firestore for this property.")
                                            # Keep the default "couldn't find information" response

                                            # Cache the empty results too
                                            if firestore_cache is not None:
                                                cache_data = {'found': False, 'context': "", 'items': []}
                                                firestore_cache.set(identified_property_id, message_text, 'knowledge_items', cache_data)
                                    except Exception as search_e:
                                        print(f"Error during Firestore search for property '{identified_property_id}': {search_e}")
                                        traceback.print_exc()
                                        # Keep the default "couldn't find information" response
                                else:
                                    print("Skipping Firestore search because query embedding failed.")
                            except Exception as db_e:
                                print(f"Error with Firestore: {db_e}")
                                traceback.print_exc()

                    # The rest of your event handling remains unchanged...

            except Exception as rag_e:
                print(f"Error during RAG process: {rag_e}")
                traceback.print_exc()

            # 3. Generate Response using Gemini (if configured)
            if gemini_configured:
                try:
                    # Construct Prompt for LLM
                    rag_prompt = f"""You are a helpful concierge assistant. Answer the user's question based ONLY on the following context. If the context doesn't contain the answer, clearly state that you don't have that specific information based on the provided context. Do not make up answers.

Context:
{knowledge_response}

User Question:
{message_text}

Answer:"""

                    # Call LLM (Gemini)
                    print("Generating response with RAG context using Gemini...")
                    # Ensure Gemini is configured before trying to use the model object
                    if genai.GenerativeModel: # Check if genai was configured successfully
                        llm = genai.GenerativeModel('gemini-2.0-flash')
                        llm_response = llm.generate_content(rag_prompt)

                        # Add more robust response handling
                        try:
                            generated_response = llm_response.text
                            print(f"LLM generated response: {generated_response}")
                        except ValueError:
                             # If the response doesn't contain text, check prompt feedback
                            print(f"Warning: Gemini response did not contain text. Feedback: {llm_response.prompt_feedback}")
                            generated_response = "I found some information, but had trouble formulating a response. Could you rephrase?"
                        except Exception as gen_e:
                            print(f"Error accessing Gemini response text: {gen_e}")
                            generated_response = "Sorry, I encountered an issue while generating the response."
                    else:
                        print("Gemini SDK not available for generation.")
                        generated_response = "I received your message, but cannot generate a detailed response right now."


                except Exception as e:
                    print(f"Error generating Gemini response: {e}")
                    traceback.print_exc()
                    generated_response = "Sorry, I encountered an issue while generating the response."
            else:
                print("Gemini not configured, cannot generate RAG response.")
                generated_response = "I received your message, but my AI brain is offline right now."

            # 5. Send Response via Telnyx SMS
            print(f"Attempting to send reply to {sender_number} from {TELNYX_SMS_NUMBER}")
            try:
                # Ensure the generated response is not empty
                if not generated_response:
                     print("Warning: Generated response was empty. Sending a default message.")
                     generated_response = "I received your message, but couldn't generate a specific reply."

                telnyx.Message.create(
                    to=sender_number,
                    from_=TELNYX_SMS_NUMBER,
                    text=generated_response
                )
                print("SMS reply sent successfully.")
            except Exception as e:
                print(f"Error sending Telnyx SMS reply: {e}")
                traceback.print_exc()
                # Log error, but still return 200 to Telnyx

        else:
            # Keep logging for genuinely unhandled/unexpected event types
            call_control_id = body.get('data', {}).get('payload', {}).get('call_control_id', 'N/A')
            print(f"Received unhandled event type: {event_type} for call {call_control_id}")

    except KeyError as e:
        print(f"Error: Missing expected key in event data: {e}")
    except Exception as e:
        print(f"Error processing event:")
        traceback.print_exc()
        print(f"Error processing event: {e}")
        # Log error but don't necessarily crash the function
        # Telnyx might send webhooks we don't need to act on

    # Always return 200 OK to Telnyx to acknowledge receipt of the webhook
    response = {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({"message": "Webhook received successfully"})
    }
    return response
