"""
Gunicorn configuration file for development.
Similar to production but with development-friendly settings.
"""

# The socket to bind - use localhost for development
bind = "127.0.0.1:5000"

# Single worker for development
workers = 1

# Use gevent worker class - same as production
worker_class = "gevent"

# Same threads as production
threads = 2

# Same connection settings as production
worker_connections = 300

# Restart workers more frequently in development for code changes
max_requests = 100
max_requests_jitter = 10

# Increased timeout for development to prevent worker timeouts during startup
timeout = 120  # Increased from 60 to 120 seconds

# Increased graceful timeout for development
graceful_timeout = 60  # Increased from 30 to 60 seconds

# Keep-alive same as production
keepalive = 5

# Don't preload app in development for easier debugging
preload_app = False

# Development-friendly logging
errorlog = "-"  # Log to stderr (console)
accesslog = "-"  # Log to stdout (console)
loglevel = "info"  # Changed from debug to info to reduce log noise

# Automatic reloading for development - made less sensitive
reload = True
reload_extra_files = [
    "concierge/templates/",
    "concierge/static/",
    ".env"
]

# Development-friendly temp directory
worker_tmp_dir = "/tmp"

# SocketIO compatibility settings
worker_class = "gevent"  # Explicit setting for clarity 