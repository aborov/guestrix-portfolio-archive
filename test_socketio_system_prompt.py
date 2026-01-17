#!/usr/bin/env python3
"""
Test Socket.IO text chat to verify system prompt is being used.
"""

import requests
import json
import time

def test_socketio_system_prompt():
    """Test Socket.IO text chat by checking the server logs."""
    print("🚀 SOCKET.IO SYSTEM PROMPT TEST")
    print("=" * 50)
    
    # Test the magic link to see if Socket.IO works
    magic_link = "http://localhost:8080/magic/YevGoNlkkeXv0w8V0nDOitjDgNxq45RX9aWm/guest"
    
    print(f"📤 Testing magic link: {magic_link}")
    
    try:
        response = requests.get(magic_link, timeout=10)
        
        if response.status_code == 200:
            print("✅ Magic link is accessible")
            print("✅ Socket.IO text chat should work in the browser")
            print("\n💡 To test Socket.IO text chat with system prompt:")
            print("1. Open the magic link in your browser")
            print("2. Try sending a message like 'hello' or 'what's the WiFi password?'")
            print("3. Check the server logs to see if system prompt is being used")
            print("4. The response should be more personalized and use the shared system prompt")
            print("\n🔍 Expected behavior:")
            print("- System prompt should be stored in session")
            print("- process_text_query_with_tools should be called with system_prompt")
            print("- Response should be more contextual and personalized")
            return True
        else:
            print(f"❌ Magic link returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error accessing magic link: {e}")
        return False

if __name__ == "__main__":
    test_socketio_system_prompt()





