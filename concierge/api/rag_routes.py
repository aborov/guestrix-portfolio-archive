from flask import Blueprint, request, jsonify, current_app
import traceback
import time

# Import the RAG functions from ai_helpers
from concierge.utils.ai_helpers import get_relevant_context, process_query_with_rag

# Create Blueprint
rag_bp = Blueprint('rag', __name__)

@rag_bp.route('/context', methods=['POST'])
def get_context():
    """
    API endpoint to retrieve relevant context from Firestore based on a query.

    Expected JSON payload:
    {
        "query": "The user's query text",
        "property_id": "The property ID to search in"
    }

    Returns:
    {
        "success": true/false,
        "found": true/false,
        "context": "The relevant context text",
        "items": [list of context items with similarity scores]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400

        query = data.get('query')
        property_id = data.get('property_id')

        if not query:
            return jsonify({"success": False, "error": "No query provided"}), 400

        if not property_id:
            return jsonify({"success": False, "error": "No property_id provided"}), 400

        # Log the request
        current_app.logger.info(f"RAG context request for property {property_id}: '{query}'")

        # Call the get_relevant_context function (now uses Firestore)
        results = get_relevant_context(query, property_id)

        # Log the results
        if results.get('found'):
            current_app.logger.info(f"Found {len(results.get('items', []))} relevant items for query")
        else:
            current_app.logger.warning(f"No relevant context found for query: '{query}'")

        # Return the results
        return jsonify({
            "success": True,
            "found": results.get('found', False),
            "context": results.get('context', ""),
            "items": results.get('items', [])
        })

    except Exception as e:
        current_app.logger.error(f"Error in RAG context API: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "found": False,
            "context": "",
            "items": []
        }), 500

@rag_bp.route('/process', methods=['POST'])
def process_query():
    """
    API endpoint to process a query with RAG and return a complete response.
    This combines context retrieval and response generation in one step.

    Expected JSON payload:
    {
        "query": "The user's query text",
        "property_id": "The property ID to search in",
        "property_context": {Optional property context object}
    }

    Returns:
    {
        "success": true/false,
        "response": "The generated response text",
        "has_context": true/false,
        "context_used": [list of context items used]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data provided"}), 400

        query = data.get('query')
        property_id = data.get('property_id')
        property_context = data.get('property_context')
        conversation_history = data.get('conversation_history', [])

        if not query:
            return jsonify({"success": False, "error": "No query provided"}), 400

        if not property_id:
            return jsonify({"success": False, "error": "No property_id provided"}), 400

        # Log the request
        current_app.logger.info(f"RAG process request for property {property_id}: '{query}'")

        # Call the process_query_with_rag function
        start_time = time.time()
        current_app.logger.info("Starting RAG processing")
        result = process_query_with_rag(query, property_id, property_context, conversation_history)
        elapsed_time = time.time() - start_time
        current_app.logger.info(f"RAG processing completed in {elapsed_time:.2f} seconds")

        # Log the results
        if result.get('has_context'):
            current_app.logger.info(f"Generated response with {len(result.get('context_used', []))} context items")
        else:
            current_app.logger.info("Generated response without context")

        # Return the results
        return jsonify({
            "success": True,
            "response": result.get('response', ""),
            "has_context": result.get('has_context', False),
            "context_used": result.get('context_used', [])
        })

    except Exception as e:
        current_app.logger.error(f"Error in RAG process API: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e),
            "response": "I'm sorry, I encountered an error while processing your request.",
            "has_context": False,
            "context_used": []
        }), 500
