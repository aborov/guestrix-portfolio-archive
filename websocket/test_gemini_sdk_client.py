#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for the Gemini SDK client.

This script tests the Gemini SDK client by sending audio and text to the Gemini Live API.
"""

import os
import time
import logging
import asyncio
from dotenv import load_dotenv

from gemini_sdk_client import GeminiSdkClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_gemini_sdk_client(api_key):
    """Test the Gemini SDK client."""
    logger.info("Testing Gemini SDK client...")
    
    # Create a client
    client = GeminiSdkClient(api_key, stream_id="test-stream")
    
    try:
        # Connect to the Gemini Live API
        welcome_message = await client.connect()
        logger.info(f"Welcome message: {welcome_message}")
        
        # Send a text prompt
        await client.send_text("Hello, Gemini! This is a test message.")
        
        # Wait for a response
        logger.info("Waiting for response...")
        
        # Wait for up to 10 seconds for a response
        start_time = time.time()
        while time.time() - start_time < 10:
            # Check for text response
            text = await client.get_text()
            if text:
                logger.info(f"Received text: {text}")
                break
            
            # Check for audio response
            audio = await client.get_audio()
            if audio:
                logger.info(f"Received {len(audio)} bytes of audio")
                break
            
            # Sleep to avoid busy waiting
            await asyncio.sleep(0.1)
        
        # Disconnect
        await client.disconnect()
        logger.info("Disconnected from Gemini Live API")
        
        return True
    
    except Exception as e:
        logger.error(f"Error testing Gemini SDK client: {e}", exc_info=True)
        return False

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

async def main():
    """Main function."""
    # Load API key
    api_key = load_api_key()
    if not api_key:
        return
    
    # Test Gemini SDK client
    client_valid = await test_gemini_sdk_client(api_key)
    
    if client_valid:
        logger.info("Gemini SDK client is working!")
    else:
        logger.error("Gemini SDK client is not working")

if __name__ == "__main__":
    asyncio.run(main())
