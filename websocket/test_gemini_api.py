#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for Gemini API key.

This script tests the Gemini API key by making a simple request to the Gemini API.
"""

import os
import json
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_gemini_api_key(api_key):
    """Test the Gemini API key by making a simple request."""
    logger.info("Testing Gemini API key...")

    # Create a session
    async with aiohttp.ClientSession() as session:
        # Test with a simple text generation request
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={api_key}"

        # Create a simple request
        request_data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Hello, Gemini! This is a test request."
                        }
                    ]
                }
            ]
        }

        try:
            # Make the request
            logger.info(f"Making request to Gemini API: {url.replace(api_key, 'REDACTED')}")
            async with session.post(url, json=request_data) as response:
                status = response.status
                response_text = await response.text()

                logger.info(f"Response status: {status}")

                if status == 200:
                    logger.info("API key is valid!")
                    response_json = json.loads(response_text)
                    logger.info(f"Response: {json.dumps(response_json, indent=2)}")
                    return True
                else:
                    logger.error(f"API key validation failed with status {status}")
                    logger.error(f"Response: {response_text}")
                    return False

        except Exception as e:
            logger.error(f"Error testing API key: {e}")
            return False

async def test_gemini_live_websocket(api_key):
    """Test the Gemini Live API WebSocket connection."""
    logger.info("Testing Gemini Live API WebSocket connection...")

    # Create a session
    async with aiohttp.ClientSession() as session:
        # Create the WebSocket URL with the API key
        ws_url = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={api_key}&alt=json"

        try:
            # Connect to the WebSocket with additional options
            logger.info(f"Connecting to Gemini Live API: {ws_url.replace(api_key, 'REDACTED')}")

            # Set connection options
            options = {
                'timeout': aiohttp.ClientTimeout(total=30),
                'heartbeat': 30.0,  # Send heartbeat every 30 seconds
                'compress': 15,     # Enable compression
                'autoclose': False,  # Don't auto-close the connection
                'max_msg_size': 0   # No limit on message size
            }

            async with session.ws_connect(ws_url, **options) as websocket:
                logger.info("Connected to Gemini Live API WebSocket")
                logger.info(f"WebSocket state: closed={websocket.closed}, protocol={websocket.protocol}, compress={websocket.compress}")

                # Try a simpler initial configuration
                initial_config = {
                    "type": "session.config",
                    "config": {
                        "model": "gemini-2.0-flash-live-001",
                        "generationConfig": {
                            "temperature": 0.7,
                            "topP": 0.95,
                            "topK": 40,
                            "candidateCount": 1,
                            "maxOutputTokens": 1024
                        },
                        "contents": [
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "text": "Hello, Gemini! This is a test message."
                                    }
                                ]
                            }
                        ]
                    }
                }

                # Send the configuration
                await websocket.send_json(initial_config)
                logger.info("Sent initial configuration to Gemini Live API")

                # Wait for a response
                logger.info("Waiting for response from Gemini Live API...")

                # Set a timeout for receiving messages
                timeout = 10  # seconds
                start_time = asyncio.get_event_loop().time()

                while True:
                    # Check if we've exceeded the timeout
                    current_time = asyncio.get_event_loop().time()
                    if current_time - start_time > timeout:
                        logger.warning(f"Timeout after {timeout} seconds waiting for response")
                        break

                    try:
                        # Wait for a message with a short timeout
                        msg = await asyncio.wait_for(websocket.receive(), timeout=1.0)

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            logger.info(f"Received message: {msg.data[:200]}...")
                            try:
                                data = json.loads(msg.data)
                                message_type = data.get("type", "unknown")
                                logger.info(f"Message type: {message_type}")

                                # If we get a response, we're good
                                return True
                            except json.JSONDecodeError:
                                logger.error(f"Error decoding JSON: {msg.data[:200]}...")
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error(f"WebSocket error: {msg.data}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            logger.warning("WebSocket closed")
                            break
                    except asyncio.TimeoutError:
                        # This is just for the inner wait_for, continue the loop
                        continue

                logger.warning("No response received from Gemini Live API")
                return False

        except Exception as e:
            logger.error(f"Error testing WebSocket connection: {e}")
            return False

async def main():
    """Main function."""
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
        return

    # Test API key
    api_valid = await test_gemini_api_key(api_key)

    if api_valid:
        # Test WebSocket connection
        websocket_valid = await test_gemini_live_websocket(api_key)

        if websocket_valid:
            logger.info("Gemini Live API WebSocket connection is working!")
        else:
            logger.error("Gemini Live API WebSocket connection is not working")
    else:
        logger.error("Gemini API key is not valid")

if __name__ == "__main__":
    asyncio.run(main())
