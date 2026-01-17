import os
from flask import jsonify

@app.route('/api/gemini-voice-config', methods=['GET'])
def get_gemini_voice_config():
    """
    Endpoint to provide Gemini API key and configuration for voice calls.
    This is required for the voice call feature to work properly.
    """
    try:
        # Get the API key from environment variables
        api_key = app.config.get('GEMINI_API_KEY')
        
        # If not in config, try environment variable
        if not api_key:
            api_key = os.environ.get('GEMINI_API_KEY')
        
        if not api_key:
            app.logger.error("No Gemini API key found in configuration or environment variables")
            return jsonify({"error": "API key not configured"}), 500
        
        # Return the API key and any other configuration needed
        return jsonify({
            "apiKey": api_key,
            "model": "gemini-2.0-flash-live-001",
            "apiVersion": "v1beta"
        })
    except Exception as e:
        app.logger.error(f"Error serving Gemini voice config: {str(e)}")
        return jsonify({"error": str(e)}), 500 