#!/usr/bin/env python3
"""
Fix script for WebSocket handler issue
"""

import sys
import os

# Path to the file to fix
file_path = "/home/ubuntu/telnyx_websocket/websocket/telnyx_bidirectional_streaming.py"

# Read the file
with open(file_path, 'r') as f:
    content = f.read()

# Fix the WebSocket serve call
old_line = "    await websockets.serve(handle_websocket, '0.0.0.0', 8083)"
new_line = "    await websockets.serve(lambda ws: handle_websocket(ws, '/'), '0.0.0.0', 8083)"

# Replace the line
content = content.replace(old_line, new_line)

# Write the file back
with open(file_path, 'w') as f:
    f.write(content)

print(f"Fixed WebSocket handler in {file_path}")
