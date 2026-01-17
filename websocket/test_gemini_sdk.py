#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for Gemini API using the official Google AI Python SDK.

This script tests the Gemini API using the official Google AI Python SDK.
"""

import os
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

def test_gemini_api_key(api_key):
    """Test the Gemini API key using the official SDK."""
    logger.info("Testing Gemini API key using the official SDK...")
    
    # Configure the API key
    genai.configure(api_key=api_key)
    
    try:
        # List available models
        models = genai.list_models()
        logger.info("Available models:")
        for model in models:
            if "gemini" in model.name.lower():
                logger.info(f"- {model.name}")
        
        # Test with a simple text generation request
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content("Hello, Gemini! This is a test message.")
        
        logger.info(f"Response: {response.text}")
        logger.info("API key is valid!")
        return True
    
    except Exception as e:
        logger.error(f"Error testing API key: {e}")
        return False

async def test_gemini_streaming(api_key):
    """Test the Gemini streaming API using the official SDK."""
    logger.info("Testing Gemini streaming API using the official SDK...")
    
    # Configure the API key
    genai.configure(api_key=api_key)
    
    try:
        # Test with a streaming text generation request
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(
            "Hello, Gemini! This is a test message.",
            stream=True
        )
        
        logger.info("Streaming response:")
        for chunk in response:
            if chunk.text:
                logger.info(f"Chunk: {chunk.text}")
        
        logger.info("Streaming API is working!")
        return True
    
    except Exception as e:
        logger.error(f"Error testing streaming API: {e}")
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
    
    # Test API key
    api_valid = test_gemini_api_key(api_key)
    
    if api_valid:
        # Test streaming API
        streaming_valid = await test_gemini_streaming(api_key)
        
        if streaming_valid:
            logger.info("Gemini streaming API is working!")
        else:
            logger.error("Gemini streaming API is not working")
    else:
        logger.error("Gemini API key is not valid")

if __name__ == "__main__":
    asyncio.run(main())
