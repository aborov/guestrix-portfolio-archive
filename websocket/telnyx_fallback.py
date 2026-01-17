#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telnyx Fallback Implementation

This module provides a fallback implementation for Telnyx using the speak API
when the Gemini Live API is not available.
"""

import os
import json
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv
import google.generativeai as genai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelnyxFallback:
    """
    Fallback implementation for Telnyx using the speak API.
    
    This class provides methods for sending text to Telnyx using the speak API
    when the Gemini Live API is not available.
    """
    
    def __init__(self, telnyx_api_key: str, gemini_api_key: str, call_control_id: str):
        """
        Initialize the Telnyx fallback.
        
        Args:
            telnyx_api_key: The Telnyx API key
            gemini_api_key: The Gemini API key
            call_control_id: The Telnyx call control ID
        """
        self.telnyx_api_key = telnyx_api_key
        self.gemini_api_key = gemini_api_key
        self.call_control_id = call_control_id
        
        # Initialize session
        self.session = None
        
        # Initialize Gemini model
        self.model = None
        
        logger.info(f"Initialized Telnyx fallback for call control ID: {call_control_id}")
    
    async def connect(self):
        """Connect to Telnyx and Gemini."""
        try:
            # Create session
            self.session = aiohttp.ClientSession()
            
            # Configure Gemini
            genai.configure(api_key=self.gemini_api_key)
            
            # Initialize the model
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            
            logger.info(f"Connected to Telnyx and Gemini for call control ID: {self.call_control_id}")
            return True
        except Exception as e:
            logger.error(f"Error connecting to Telnyx and Gemini for call control ID {self.call_control_id}: {e}", exc_info=True)
            await self.disconnect()
            return False
    
    async def send_audio_to_gemini(self, audio_data: bytes):
        """
        Send audio to Gemini.
        
        Since we're using the fallback implementation, we'll just log this.
        """
        logger.info(f"Received {len(audio_data)} bytes of audio for call control ID: {self.call_control_id}")
        logger.warning(f"Audio processing not available in fallback mode for call control ID: {self.call_control_id}")
    
    async def send_text_to_gemini(self, text: str):
        """
        Send text to Gemini and then to Telnyx.
        
        Args:
            text: The text to send to Gemini
        """
        try:
            logger.info(f"Sending text to Gemini for call control ID {self.call_control_id}: {text}")
            
            # Generate a response from Gemini
            response = self.model.generate_content(text)
            
            # Get the response text
            response_text = response.text
            
            logger.info(f"Received response from Gemini for call control ID {self.call_control_id}: {response_text}")
            
            # Send the response to Telnyx
            await self.send_text_to_telnyx(response_text)
            
            return True
        except Exception as e:
            logger.error(f"Error sending text to Gemini for call control ID {self.call_control_id}: {e}", exc_info=True)
            
            # Send a fallback message to Telnyx
            await self.send_text_to_telnyx("I'm sorry, I encountered an error. Please try again.")
            
            return False
    
    async def send_text_to_telnyx(self, text: str):
        """
        Send text to Telnyx using the speak API.
        
        Args:
            text: The text to send to Telnyx
        """
        try:
            # Create the speak API URL
            url = f"https://api.telnyx.com/v2/calls/{self.call_control_id}/actions/speak"
            
            # Create the speak API request
            speak_request = {
                "payload": text,
                "voice": "female",
                "language": "en-US"
            }
            
            # Set headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.telnyx_api_key}"
            }
            
            # Send the request
            async with self.session.post(url, json=speak_request, headers=headers) as response:
                if response.status == 200:
                    logger.info(f"Sent text to Telnyx speak API for call control ID {self.call_control_id}: {text}")
                    return True
                else:
                    response_text = await response.text()
                    logger.error(f"Error sending text to Telnyx speak API for call control ID {self.call_control_id}: {response.status} {response_text}")
                    return False
        except Exception as e:
            logger.error(f"Error sending text to Telnyx speak API for call control ID {self.call_control_id}: {e}", exc_info=True)
            return False
    
    async def disconnect(self):
        """Disconnect from Telnyx and Gemini."""
        logger.info(f"Disconnecting from Telnyx and Gemini for call control ID: {self.call_control_id}")
        
        # Close session
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info(f"Disconnected from Telnyx and Gemini for call control ID: {self.call_control_id}")

async def test_fallback():
    """Test the Telnyx fallback."""
    # Load environment variables
    load_dotenv()
    
    # Get API keys
    telnyx_api_key = os.getenv("TELNYX_API_KEY")
    gemini_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    if not telnyx_api_key:
        logger.error("Telnyx API key not found in environment variables")
        return False
    
    if not gemini_api_key:
        logger.error("Gemini API key not found in environment variables")
        return False
    
    # Create a test call control ID
    call_control_id = "test-call-control-id"
    
    # Create the fallback
    fallback = TelnyxFallback(telnyx_api_key, gemini_api_key, call_control_id)
    
    try:
        # Connect to Telnyx and Gemini
        if not await fallback.connect():
            logger.error("Failed to connect to Telnyx and Gemini")
            return False
        
        # Send a test message to Gemini
        await fallback.send_text_to_gemini("Hello, Gemini! This is a test message.")
        
        # Disconnect
        await fallback.disconnect()
        
        return True
    except Exception as e:
        logger.error(f"Error testing Telnyx fallback: {e}", exc_info=True)
        return False

async def main():
    """Main function."""
    # Test the fallback
    success = await test_fallback()
    
    if success:
        logger.info("Telnyx fallback test completed successfully")
    else:
        logger.error("Telnyx fallback test failed")

if __name__ == "__main__":
    asyncio.run(main())
