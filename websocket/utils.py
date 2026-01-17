#!/usr/bin/env python3
"""
Utilities

This module provides utility functions for the Telnyx Bidirectional Streaming application.
"""

import os
import json
import logging
import argparse
from typing import Dict, Any, Optional

def setup_logging(level: int = logging.DEBUG) -> logging.Logger:
    """
    Set up logging for the application.

    Args:
        level: The logging level to use (default: DEBUG for more detailed logs)

    Returns:
        The configured logger
    """
    # Configure logging
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("telnyx_bidirectional.log")
        ]
    )

    # Create logger
    logger = logging.getLogger("telnyx_bidirectional")
    logger.setLevel(level)

    # Set specific loggers to appropriate levels
    logging.getLogger("websockets").setLevel(logging.INFO)  # Reduce noise from websockets library
    logging.getLogger("aiohttp").setLevel(logging.INFO)     # Reduce noise from aiohttp library

    logger.info(f"Logging initialized at level: {logging.getLevelName(level)}")

    return logger

def load_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from a file.

    Args:
        config_file: The path to the configuration file

    Returns:
        The configuration dictionary
    """
    # Default configuration
    config = {
        "telnyx": {
            "webhook_port": 8082,
            "websocket_port": 8083,
            "host": "0.0.0.0",
            "sample_rate": 16000,
            "codec": "OPUS"
        },
        "gemini": {
            "model": "gemini-2.0-flash-live-001",
            "sample_rate": 24000,
            "voice": "Aoede"
        },
        "audio": {
            "chunk_size": 1600,  # 100ms at 16kHz
            "chunk_delay": 0.1,  # 100ms delay between chunks
            "buffer_size": 3  # Number of chunks to buffer before starting playback
        },
        "logging": {
            "level": "INFO",
            "file": "telnyx_bidirectional.log"
        }
    }

    # Load configuration from file if provided
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)

                # Update configuration with values from file
                for section, values in file_config.items():
                    if section in config:
                        config[section].update(values)
                    else:
                        config[section] = values
        except Exception as e:
            logging.error(f"Error loading configuration from {config_file}: {e}")

    return config

def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        The parsed arguments
    """
    parser = argparse.ArgumentParser(description="Telnyx Bidirectional Streaming with Gemini Live API")

    # Add arguments
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--webhook-port", type=int, help="Port for HTTP webhook server")
    parser.add_argument("--websocket-port", type=int, help="Port for WebSocket server")
    parser.add_argument("--host", help="Host to bind servers to")

    return parser.parse_args()

def mask_api_key(api_key: str) -> str:
    """
    Mask an API key for logging.

    Args:
        api_key: The API key to mask

    Returns:
        The masked API key
    """
    if not api_key:
        return "None"

    # Keep first 5 and last 5 characters, mask the rest
    if len(api_key) > 10:
        return f"{api_key[:5]}...{api_key[-5:]}"
    else:
        return "***"

def format_system_prompt(property_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Format the system prompt for Gemini Live API.

    Args:
        property_data: Property data to include in the prompt

    Returns:
        The formatted system prompt
    """
    # Get property information
    property_name = property_data.get("name", "this property") if property_data else "this property"
    property_address = property_data.get("address", "") if property_data else ""
    host_name = property_data.get("hostName", "your host") if property_data else "your host"

    # Create the system prompt
    system_prompt = f"""
    You are Staycee, a helpful AI concierge assistant for "{property_name}" located at "{property_address}".
    You are speaking with a guest over the phone.
    The host for this property is {host_name}.
    Your goal is to assist the guest with any questions or needs they have regarding their stay.
    Be conversational, friendly, and helpful.

    Keep your responses concise and conversational, as they will be read aloud over the phone.
    Limit your responses to 3-4 sentences maximum.

    CRITICAL INFRASTRUCTURE PROTECTION:
    If a guest asks about the location of critical infrastructure elements such as water shutoff valves, electrical panels, fuse boxes, circuit breakers, gas shutoff valves, HVAC system controls, air handler units, ventilation system access, sump pumps, water heaters, or other mechanical systems, you MUST first ask the guest to explain the specific reason they need this information. Only provide access details if there is a genuine emergency situation such as fire, smoke, electrical hazards, water leaks, flooding, pipe bursts, gas leaks, HVAC system failures causing dangerous temperatures, or any situation where immediate access would prevent property damage or ensure guest safety. For non-emergency requests, politely explain that this information is restricted for safety and security reasons, and suggest they contact the host directly.

    You have access to the following tools:
    1. google_search: Use this tool to search for information about local attractions, restaurants, services, or any other information that would be helpful to the guest.
    """

    # Add WiFi information if available
    if property_data:
        wifi_network = property_data.get("wifiNetwork")
        wifi_password = property_data.get("wifiPassword")
        if wifi_network and wifi_password:
            system_prompt += f"\n\nWiFi Network: {wifi_network}\nWiFi Password: {wifi_password}"

    return system_prompt

def format_knowledge_items(knowledge_items: list) -> str:
    """
    Format knowledge items for inclusion in the system prompt.

    Args:
        knowledge_items: List of knowledge items

    Returns:
        Formatted knowledge items string
    """
    if not knowledge_items:
        return ""

    formatted_items = []
    for item in knowledge_items:
        item_type = item.get('type', '')
        content = item.get('content', '')
        tags = item.get('tags', [])

        # Format based on item type
        type_prefix = f"[{item_type.upper()}] " if item_type else ''
        formatted_item = f"{type_prefix}{content}"

        # Add tags if available
        if tags and isinstance(tags, list) and len(tags) > 0:
            formatted_item += f"\nTags: {', '.join(tags)}"

        formatted_items.append(formatted_item)

    return "\n\n".join(formatted_items)
