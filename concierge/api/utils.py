import google.generativeai as genai
import json
import traceback # For error logging
import logging
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from datetime import datetime
from concierge.utils.gemini_config import genai_enabled, gemini_model
from concierge.lambda_src.firebase_admin_config import get_firestore_client

# Get the initialized Firestore client
db = get_firestore_client()

# This is a simplification; dependency injection or a config object would be better.
def generate_qna_with_gemini(text_content: str, property_details: dict) -> list[dict]:
    """Generates Q&A pairs from text content using Google Gemini.
    Args:
        text_content: The extracted text from the knowledge source (up to ~1M tokens for Flash).
        property_details: A dictionary containing details about the property
                          (e.g., name, address) for context.
    Returns:
        A list of dictionaries, where each dictionary represents a Q&A pair
        with 'question' and 'answer' keys, or an empty list if generation
        fails, is disabled, or returns no valid content.
    """
    # Check if Gemini is enabled and the model was initialized
    if not genai_enabled or not gemini_model:
        print("Gemini Q&A generation is disabled (API key missing, config failed, or model init failed).")
        return []

    print(f"Attempting to generate Q&A for property: {property_details.get('id', 'N/A')}")

    # --- Craft the Prompt --- #
    # Provide context about the property if available
    property_name = property_details.get('name', 'the property')
    property_address = property_details.get('address', '')
    context_prompt = f"You are creating a knowledge base for guests staying at {property_name}" \
                     f"{(' located at ' + property_address) if property_address else ''}.\n\n"

    instruction_prompt = (
        "Read the following text provided by the property host. "
        "Identify key information that a guest might need to know (e.g., WiFi, check-out, amenities, rules, local tips). "
        "Generate a list of potential questions a guest might ask based *only* on the information in this text. "
        "For each question, provide a concise and accurate answer derived *only* from the provided text. "
        "Format the output as a JSON list of objects, where each object has a 'question' key and an 'answer' key. "
        "Example: [{\"question\": \"What is the WiFi password?\", \"answer\": \"The password is GuestPass123.\"}, ...]. "
        "Output *only* the raw JSON list, with no introductory text, explanation, or markdown formatting like ```json ... ```."
    )

    full_prompt = f"{context_prompt}{instruction_prompt}\n\n--- Host Provided Text ---\n{text_content}\n--- End Host Provided Text ---"

    # --- Call Gemini API and Parse Response --- #
    generated_qna = []
    try:
        # Configure safety settings if needed (optional)
        # safety_settings = [...]
        # response = gemini_model.generate_content(full_prompt, safety_settings=safety_settings)

        print(f"Sending prompt to Gemini (length: {len(full_prompt)} chars) for property {property_details.get('id', 'N/A')}...")
        response = gemini_model.generate_content(full_prompt)

        # --- Basic Response Validation ---
        if not response.parts:
            print(f"Warning: Gemini response has no parts for property {property_details.get('id', 'N/A')}.")
            # Check finish_reason if available
            try:
                print(f"Finish reason: {response.prompt_feedback}") # Or response.candidates[0].finish_reason etc.
            except Exception: pass # Ignore errors in getting finish reason
            return []

        response_text = response.text.strip()
        if not response_text:
            print(f"Warning: Gemini response text is empty for property {property_details.get('id', 'N/A')}.")
            return []

        print(f"Received response from Gemini (length: {len(response_text)} chars). Attempting JSON parse.")
        # print(f"DEBUG: Raw Gemini Response:\n{response_text[:500]}...") # Uncomment for deep debugging

        # --- Parse JSON --- #
        # The model might sometimes still include ```json ... ``` despite the prompt
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip() # Strip again after removing backticks

        parsed_json = json.loads(response_text)

        # --- Validate Parsed Structure --- #
        if isinstance(parsed_json, list):
            valid_items = []
            for item in parsed_json:
                if isinstance(item, dict) and 'question' in item and 'answer' in item and \
                   isinstance(item['question'], str) and item['question'].strip() and \
                   isinstance(item['answer'], str) and item['answer'].strip():
                    valid_items.append({
                        'question': item['question'].strip(),
                        'answer': item['answer'].strip()
                    })
                else:
                    print(f"Warning: Skipping invalid/incomplete Q&A item: {item}")
            generated_qna = valid_items
            print(f"Successfully parsed {len(generated_qna)} valid Q&A pairs from Gemini response.")
        else:
            print(f"Error: Parsed JSON is not a list: {type(parsed_json)}")

    except json.JSONDecodeError as json_err:
        print(f"Error: Failed to decode JSON response from Gemini: {json_err}")
        print(f"--- Start Gemini Raw Response causing JSON Error ---")
        print(response_text) # Log the problematic text
        print(f"--- End Gemini Raw Response --- ")
    except Exception as e:
        # Catch other potential errors (API connection, etc.)
        print(f"Error during Gemini API call or processing: {e}")
        import traceback
        traceback.print_exc()

    return generated_qna

def generate_knowledge_items_with_gemini(text_content: str, property_details: dict) -> list[dict]:
    """Generates knowledge items from text content using Google Gemini with the new schema.

    Args:
        text_content: The extracted text from the knowledge source (up to ~1M tokens for Flash).
        property_details: A dictionary containing details about the property
                          (e.g., name, address) for context.

    Returns:
        A list of dictionaries, where each dictionary represents a knowledge item
        with 'type', 'tags', and 'content' keys, or an empty list if generation
        fails, is disabled, or returns no valid content.
    """
    # Check if Gemini is enabled and the model was initialized
    if not genai_enabled or not gemini_model:
        print("Gemini knowledge item generation is disabled (API key missing, config failed, or model init failed).")
        return []

    print(f"Attempting to generate knowledge items for property: {property_details.get('id', 'N/A')}")

    # --- Craft the Prompt --- #
    # Provide context about the property if available
    property_name = property_details.get('name', 'the property')
    property_address = property_details.get('address', '')
    context_prompt = f"You are creating a knowledge base for guests staying at {property_name}" \
                     f"{(' located at ' + property_address) if property_address else ''}.\n\n"

    instruction_prompt = (
        "Read the following text provided by the property host. "
        "Identify key information that a guest might need to know and create structured knowledge items. "
        "Each knowledge item should have a type, tags, and content. "
        "Types should be one of: 'information', 'rule', 'instruction', 'emergency', or 'places'. "
        "Tags should be a list of relevant keywords. "
        "Content should be the actual information, written in a clear, concise manner. "

        "SPECIAL INSTRUCTIONS FOR PLACES TYPE: "
        "When processing lists of local attractions, restaurants, cafes, shops, etc., use the 'places' type. "
        "Group places into logical categories (e.g., 'Italian Restaurants', 'Family Attractions', 'Coffee Shops'). "
        "Create separate knowledge items for each category, not for each individual place. "
        "For example, all Italian restaurants should be in one 'places' item, all coffee shops in another. "
        "If there are many places in a subcategory (e.g., multiple Italian restaurants or attractions for kids), "
        "create a separate item for that subcategory. "
        "For tags, use category descriptors like 'restaurant', 'italian', 'coffee', 'family', etc. - NOT the names of individual places. "
        "The content should include all places in that category with their details, formatted in a clear, readable way. "

        "Format the output as a JSON list of objects, where each object has 'type', 'tags', and 'content' keys. "
        "Example: [{\"type\": \"information\", \"tags\": [\"wifi\", \"internet\"], \"content\": \"The WiFi password is GuestPass123.\"}, "
        "{\"type\": \"places\", \"tags\": [\"restaurant\", \"italian\", \"pizza\"], \"content\": \"Italian Restaurants:\\n- Mario's Pizzeria: Authentic wood-fired pizza, open 11am-10pm, 123 Main St\\n- Pasta Palace: Family-style Italian dining, open 5pm-11pm, 456 Oak Ave\"}]. "
        "Output *only* the raw JSON list, with no introductory text, explanation, or markdown formatting."
    )

    full_prompt = f"{context_prompt}{instruction_prompt}\n\n--- Host Provided Text ---\n{text_content}\n--- End Host Provided Text ---"

    # --- Call Gemini API and Parse Response --- #
    generated_items = []
    try:
        print(f"Sending prompt to Gemini (length: {len(full_prompt)} chars) for property {property_details.get('id', 'N/A')}...")
        response = gemini_model.generate_content(full_prompt)

        # --- Basic Response Validation ---
        if not response.parts:
            print(f"Warning: Gemini response has no parts for property {property_details.get('id', 'N/A')}.")
            try:
                print(f"Finish reason: {response.prompt_feedback}")
            except Exception: pass
            return []

        response_text = response.text.strip()
        if not response_text:
            print(f"Warning: Gemini response text is empty for property {property_details.get('id', 'N/A')}.")
            return []

        print(f"Received response from Gemini (length: {len(response_text)} chars). Attempting JSON parse.")

        # --- Parse JSON --- #
        # The model might sometimes still include ```json ... ``` despite the prompt
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip() # Strip again after removing backticks

        parsed_json = json.loads(response_text)

        # --- Validate Parsed Structure --- #
        if isinstance(parsed_json, list):
            valid_items = []
            for item in parsed_json:
                if isinstance(item, dict) and 'type' in item and 'content' in item and \
                   isinstance(item['type'], str) and item['type'].strip() and \
                   isinstance(item['content'], str) and item['content'].strip():

                    # Ensure type is one of the allowed values
                    item_type = item['type'].strip().lower()
                    if item_type not in ['information', 'rule', 'instruction', 'emergency', 'places']:
                        item_type = 'information'  # Default to information

                    # Ensure tags is a list of strings
                    tags = item.get('tags', [])
                    if not isinstance(tags, list):
                        tags = []
                    tags = [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()]

                    valid_items.append({
                        'type': item_type,
                        'tags': tags,
                        'content': item['content'].strip()
                    })
                else:
                    print(f"Warning: Skipping invalid/incomplete knowledge item: {item}")

            generated_items = valid_items
            print(f"Successfully parsed {len(generated_items)} valid knowledge items from Gemini response.")
        else:
            print(f"Error: Parsed JSON is not a list: {type(parsed_json)}")

    except json.JSONDecodeError as json_err:
        print(f"Error: Failed to decode JSON response from Gemini: {json_err}")
        print(f"--- Start Gemini Raw Response causing JSON Error ---")
        print(response_text) # Log the problematic text
        print(f"--- End Gemini Raw Response --- ")
    except Exception as e:
        # Catch other potential errors (API connection, etc.)
        print(f"Error during Gemini API call or processing: {e}")
        import traceback
        traceback.print_exc()

    return generated_items