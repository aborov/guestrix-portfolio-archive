#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for Gemini Live API.

This script tests the Gemini Live API using the official Google AI Python SDK.
"""

import os
import time
import base64
import logging
import asyncio
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_api_key():
    """Load the API key from environment variables or config files."""
    # Load environment variables
    load_dotenv()
    
    # Get API key - try both environment variable names
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    # If still not found, try to load from config file
    if not api_key:
        try:
            # Try to load from the same config as the main application
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
            logger.info(f"Trying to load API key from config file: {config_path}")
            
            if os.path.exists(config_path):
                # Load the .env file
                load_dotenv(config_path)
                api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            
            # If still not found, try the server location
            if not api_key:
                server_config_path = '/home/ubuntu/telnyx_websocket/.env'
                if os.path.exists(server_config_path):
                    logger.info(f"Trying to load API key from server config: {server_config_path}")
                    load_dotenv(server_config_path)
                    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    if not api_key:
        logger.error("API key not found in environment variables or config files")
        return None
    
    return api_key

def handle_response(response):
    """Handle the response from the Gemini Live API."""
    try:
        for chunk in response:
            # Check for text
            if hasattr(chunk, "text") and chunk.text:
                logger.info(f"Received text: {chunk.text}")
            
            # Check for audio
            if hasattr(chunk, "audio") and chunk.audio:
                audio_data = chunk.audio
                logger.info(f"Received audio: {len(audio_data)} bytes")
    except Exception as e:
        logger.error(f"Error handling response: {e}")

async def test_gemini_live_api():
    """Test the Gemini Live API."""
    # Load API key
    api_key = load_api_key()
    if not api_key:
        return False
    
    # Configure the API key
    genai.configure(api_key=api_key)
    
    try:
        # List available models
        models = genai.list_models()
        logger.info("Available models:")
        for model in models:
            if "gemini" in model.name.lower():
                logger.info(f"- {model.name}")
        
        # Create a live session
        logger.info("Creating a live session...")
        
        # Find the live model
        live_model = None
        for model in models:
            if "live" in model.name.lower():
                live_model = model.name
                logger.info(f"Found live model: {live_model}")
                break
        
        if not live_model:
            logger.warning("No live model found, using default name")
            live_model = "gemini-2.0-flash-live-001"
        
        # Create a model instance
        model = genai.GenerativeModel(live_model)
        
        # Create a live session
        logger.info(f"Creating a live session with model: {live_model}")
        session = model.start_live_session()
        logger.info("Live session created successfully")
        
        # Send a text message
        logger.info("Sending a text message...")
        response = session.send_message("Hello, Gemini! This is a test message.")
        logger.info("Message sent, processing response...")
        
        # Handle the response
        handle_response(response)
        
        # Wait a moment
        await asyncio.sleep(2)
        
        # Send an audio message
        logger.info("Sending an audio message...")
        
        # Create a simple audio sample (silence)
        audio_data = bytes([0] * 1000)  # 1000 bytes of silence
        
        # Send the audio
        response = session.send_audio(audio_data)
        logger.info("Audio sent, processing response...")
        
        # Handle the response
        handle_response(response)
        
        # End the session
        logger.info("Ending the session...")
        session.end()
        logger.info("Session ended successfully")
        
        return True
    
    except Exception as e:
        logger.error(f"Error testing Gemini Live API: {e}", exc_info=True)
        return False

async def main():
    """Main function."""
    # Test Gemini Live API
    success = await test_gemini_live_api()
    
    if success:
        logger.info("Gemini Live API test completed successfully")
    else:
        logger.error("Gemini Live API test failed")

if __name__ == "__main__":
    asyncio.run(main())
