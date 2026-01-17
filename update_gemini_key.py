#!/usr/bin/env python3
"""
Update GEMINI_API_KEY to use the paid key in development mode.
"""

import os
import sys
sys.path.append('/Users/aborov/Workspace/concierge')

from dotenv import load_dotenv

def update_gemini_key():
    print("🔧 UPDATING GEMINI API KEY CONFIGURATION")
    print("=" * 50)
    
    # Load current environment variables
    load_dotenv('./concierge/.env')
    
    # Get the paid API key
    paid_key = os.getenv('GEMINI_API_KEY_PAID')
    if not paid_key:
        print("❌ GEMINI_API_KEY_PAID not found in environment")
        return False
    
    print(f"💰 Found paid API key: {paid_key[:10]}...")
    
    # Check if .env file exists
    env_file_path = './concierge/.env'
    if not os.path.exists(env_file_path):
        print(f"📝 Creating .env file at {env_file_path}")
        # Create the .env file with the paid key
        with open(env_file_path, 'w') as f:
            f.write(f"GEMINI_API_KEY={paid_key}\n")
            f.write(f"GEMINI_API_KEY_PAID={paid_key}\n")
            f.write("DEPLOYMENT_ENV=development\n")
    else:
        print(f"📝 Updating existing .env file at {env_file_path}")
        # Read existing content
        with open(env_file_path, 'r') as f:
            lines = f.readlines()
        
        # Update or add GEMINI_API_KEY
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('GEMINI_API_KEY=') and not line.startswith('GEMINI_API_KEY_PAID='):
                lines[i] = f"GEMINI_API_KEY={paid_key}\n"
                updated = True
                break
        
        if not updated:
            lines.append(f"GEMINI_API_KEY={paid_key}\n")
        
        # Write back to file
        with open(env_file_path, 'w') as f:
            f.writelines(lines)
    
    print("✅ Updated GEMINI_API_KEY to use paid key")
    print("🔄 Please restart the server to apply changes")
    
    return True

if __name__ == "__main__":
    update_gemini_key()





