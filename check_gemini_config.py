#!/usr/bin/env python3
"""
Check current Gemini API configuration.
"""

import os
import sys
sys.path.append('/Users/aborov/Workspace/concierge')

from dotenv import load_dotenv

# Load environment variables
load_dotenv('./concierge/.env')

def check_gemini_config():
    print("🔍 GEMINI API CONFIGURATION CHECK")
    print("=" * 50)
    
    # Check environment variables
    deployment_env = os.getenv('DEPLOYMENT_ENV', 'Not set')
    gemini_api_key = os.getenv('GEMINI_API_KEY', 'Not set')
    gemini_api_key_paid = os.getenv('GEMINI_API_KEY_PAID', 'Not set')
    
    print(f"📊 DEPLOYMENT_ENV: {deployment_env}")
    print(f"🔑 GEMINI_API_KEY: {gemini_api_key[:10] if gemini_api_key != 'Not set' else 'Not set'}...")
    print(f"💰 GEMINI_API_KEY_PAID: {gemini_api_key_paid[:10] if gemini_api_key_paid != 'Not set' else 'Not set'}...")
    
    # Import and check the actual configuration
    try:
        from concierge.utils.gemini_config import _select_gemini_api_key, GEMINI_API_KEY
        
        selected_key = _select_gemini_api_key()
        print(f"\n🎯 SELECTED API KEY: {selected_key[:10] if selected_key else 'None'}...")
        print(f"🔧 GEMINI_API_KEY (from config): {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'None'}...")
        
        # Check which key is being used
        if selected_key == gemini_api_key and gemini_api_key == gemini_api_key_paid:
            print("✅ Using PAID API key (set as GEMINI_API_KEY)")
        elif selected_key == gemini_api_key:
            print("✅ Using FREE/DEVELOPMENT API key")
        elif selected_key == gemini_api_key_paid:
            print("✅ Using PAID API key")
        else:
            print("❓ Unknown key source")
            
    except Exception as e:
        print(f"❌ Error importing gemini_config: {e}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    check_gemini_config()
