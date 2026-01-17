#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WebSocket Adapter Module

This module provides an adapter for different versions of the websockets library.
"""

import logging

# Configure logging
logger = logging.getLogger("telnyx_bidirectional")

async def websocket_adapter(handler):
    """Adapter for websockets library version differences."""
    async def wrapper(websocket):
        """Wrapper function that calls the original handler with a dummy path."""
        remote_address = websocket.remote_address if hasattr(websocket, 'remote_address') else 'unknown'
        logger.info(f"WebSocket adapter called for connection from {remote_address}")
        await handler(websocket, '/')
    return wrapper
