# WSGI entry point for gunicorn
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the Flask application directly from concierge/app.py
# The concierge directory is already in the path
from concierge.app import app as application

# For debugging
print(f"Python path: {sys.path}")
print(f"Current directory: {os.path.abspath(os.path.dirname(__file__))}")
