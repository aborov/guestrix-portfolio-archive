#!/usr/bin/env python3
"""
Utility functions for the LiveKit integration.

This module provides helper functions for logging, configuration loading,
and other utilities used throughout the application.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Configure logging
def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Set up logging configuration.

    Args:
        level: The logging level (default: INFO)

    Returns:
        A configured logger
    """
    # Set up logging level from string
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    # Configure logging
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Create and return logger
    logger = logging.getLogger("livekit")
    return logger

# Create logger
logger = setup_logging()

def load_config() -> Dict[str, Any]:
    """
    Load configuration from environment variables.

    Returns:
        A dictionary containing the configuration
    """
    # Load environment variables
    # Try to load from .env.livekit first, then fall back to the twilio-gemini .env file
    if os.path.exists(".env.livekit"):
        load_dotenv(".env.livekit")
    elif os.path.exists("../.env.livekit"):
        load_dotenv("../.env.livekit")
    elif os.path.exists("../twilio-gemini/.env"):
        load_dotenv("../twilio-gemini/.env")

    # Get configuration from environment variables
    config = {
        "gemini": {
            "api_key": os.getenv("GEMINI_API_KEY"),
            "model": "gemini-2.0-flash-live-001",  # Use the correct model for live audio
            "voice": "Aoede",  # Default voice to use
            "sample_rate": 24000,
        },
        "twilio": {
            "account_sid": os.getenv("TWILIO_ACCOUNT_SID"),
            "auth_token": os.getenv("TWILIO_AUTH_TOKEN"),
            "phone_number": os.getenv("TWILIO_PHONE_NUMBER"),
            "sample_rate": 8000,
        },
        "livekit": {
            "api_key": os.getenv("LIVEKIT_API_KEY", "guestrix_key"),
            "api_secret": os.getenv("LIVEKIT_API_SECRET", "guestrix_secret"),
            "host": os.getenv("LIVEKIT_HOST", "localhost"),
            "port": int(os.getenv("LIVEKIT_PORT", "7880")),  # Default LiveKit port
        },
        "server": {
            "host": os.getenv("SERVER_HOST", "0.0.0.0"),
            "port": int(os.getenv("SERVER_PORT", "5001")),  # Using port 5001 to avoid conflict with AirPlay
        }
    }

    # Validate required configuration
    if not config["gemini"]["api_key"]:
        logger.error("GEMINI_API_KEY not found in environment variables")

    if not config["twilio"]["account_sid"] or not config["twilio"]["auth_token"]:
        logger.error("Twilio credentials not found in environment variables")

    return config

def mask_api_key(api_key: Optional[str]) -> str:
    """
    Mask an API key for logging.

    Args:
        api_key: The API key to mask

    Returns:
        A masked version of the API key
    """
    if not api_key:
        return "None"

    # Show only the first 4 and last 4 characters
    if len(api_key) > 8:
        return f"{api_key[:4]}...{api_key[-4:]}"
    else:
        return "****"

def log_config(config: Dict[str, Any]) -> None:
    """
    Log the configuration (with sensitive information masked).

    Args:
        config: The configuration dictionary
    """
    # Create a copy of the configuration
    masked_config = json.loads(json.dumps(config))

    # Mask sensitive information
    if "api_key" in masked_config.get("gemini", {}):
        masked_config["gemini"]["api_key"] = mask_api_key(masked_config["gemini"]["api_key"])

    if "account_sid" in masked_config.get("twilio", {}):
        masked_config["twilio"]["account_sid"] = mask_api_key(masked_config["twilio"]["account_sid"])

    if "auth_token" in masked_config.get("twilio", {}):
        masked_config["twilio"]["auth_token"] = mask_api_key(masked_config["twilio"]["auth_token"])

    if "api_key" in masked_config.get("livekit", {}):
        masked_config["livekit"]["api_key"] = mask_api_key(masked_config["livekit"]["api_key"])

    if "api_secret" in masked_config.get("livekit", {}):
        masked_config["livekit"]["api_secret"] = mask_api_key(masked_config["livekit"]["api_secret"])

    # Log the masked configuration
    logger.info(f"Configuration: {json.dumps(masked_config, indent=2)}")
