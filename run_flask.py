#!/usr/bin/env python3
"""
Script to run the Flask server on port 5001.
"""

import server

if __name__ == "__main__":
    # Get the Flask app from the server module
    app = server.app
    
    # Run the app on port 5001
    app.run(host="0.0.0.0", port=5001, debug=False)
