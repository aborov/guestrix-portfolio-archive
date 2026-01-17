#!/usr/bin/env python3
"""
Script to fix the import statement in firestore_client.py
"""

import os
import sys
import re

def fix_import(file_path):
    """
    Fix the import statement in the firestore_client.py file
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Replace the incorrect import statement
    content = content.replace(
        'from google.cloud.firestore_v1.vector import Vector',
        'from google.cloud.firestore_v1 import vector\n# Vector class is now accessed as vector.Vector'
    )
    
    # Also replace any usage of Vector with vector.Vector
    content = re.sub(r'(?<!\.)Vector\(', 'vector.Vector(', content)
    
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Fixed import statement in {file_path}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = "/app/dashboard/concierge/utils/firestore_client.py"
    
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist")
        sys.exit(1)
    
    fix_import(file_path)
