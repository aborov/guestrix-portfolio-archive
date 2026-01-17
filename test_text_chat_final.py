#!/usr/bin/env python3
"""
Final test script for text chat functionality.
Tests Socket.IO connection, authentication, and message sending.
"""

import socketio
import time
import json

def test_text_chat():
    print("🚀 FINAL TEXT CHAT TEST")
    print("=" * 50)
    
    # Create Socket.IO client
    sio = socketio.Client()
    
    # Track test results
    test_results = {
        'connection': False,
        'authentication': False,
        'message_sent': False,
        'response_received': False,
        'errors': []
    }
    
    @sio.event
    def connect():
        print("✅ Connected to server")
        test_results['connection'] = True
        
        # Send authentication
        auth_data = {
            'user_id': 'temp_magic_',
            'property_id': '1a344329-2670-4b34-a4f6-e28513a3200c',
            'guest_name': 'Testing',
            'reservation_id': 'd3e661b5-e451-480f-851c-95835880f1a6',
            'phone_number': '+15551234555'
        }
        
        print("🔐 Sending authentication...")
        sio.emit('auth', auth_data)
    
    @sio.event
    def auth_success(data):
        print("✅ Authentication successful")
        test_results['authentication'] = True
        
        # Send a test message
        print("📤 Sending test message...")
        message_data = {
            'message': 'hello',
            'property_id': '1a344329-2670-4b34-a4f6-e28513a3200c'
        }
        sio.emit('text_message_from_user', message_data)
        test_results['message_sent'] = True
    
    @sio.event
    def text_message_from_ai(data):
        print("✅ Received AI response:")
        print(f"   Message: {data.get('message', 'No message')}")
        test_results['response_received'] = True
        
        # Disconnect after receiving response
        sio.disconnect()
    
    @sio.event
    def disconnect():
        print("🔌 Disconnected from server")
    
    @sio.event
    def connect_error(data):
        print(f"❌ Connection error: {data}")
        test_results['errors'].append(f"Connection error: {data}")
    
    try:
        # Connect to the server
        print("🔗 Connecting to server...")
        sio.connect('http://localhost:8080')
        
        # Wait for response (with timeout)
        start_time = time.time()
        timeout = 30  # 30 seconds timeout
        
        while not test_results['response_received'] and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        if time.time() - start_time >= timeout:
            print("⏰ Test timed out")
            test_results['errors'].append("Test timed out")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        test_results['errors'].append(f"Test error: {e}")
    
    finally:
        if sio.connected:
            sio.disconnect()
    
    # Print results
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS:")
    print(f"   Connection: {'✅' if test_results['connection'] else '❌'}")
    print(f"   Authentication: {'✅' if test_results['authentication'] else '❌'}")
    print(f"   Message Sent: {'✅' if test_results['message_sent'] else '❌'}")
    print(f"   Response Received: {'✅' if test_results['response_received'] else '❌'}")
    
    if test_results['errors']:
        print("\n❌ ERRORS:")
        for error in test_results['errors']:
            print(f"   - {error}")
    
    # Overall result
    all_passed = all([
        test_results['connection'],
        test_results['authentication'],
        test_results['message_sent'],
        test_results['response_received']
    ])
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Text chat is working correctly.")
    else:
        print("\n❌ SOME TESTS FAILED. Check the errors above.")
    
    return all_passed

if __name__ == "__main__":
    test_text_chat()





