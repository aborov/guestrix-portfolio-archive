"""
Gunicorn configuration file.
"""

# The socket to bind
bind = "0.0.0.0:8080"

# The number of worker processes
workers = 2

# The type of workers to use
worker_class = "sync"

# The number of threads for handling requests
threads = 4

# The maximum number of requests a worker will process before restarting
max_requests = 1000

# The maximum jitter to add to max_requests
max_requests_jitter = 100

# Timeout for graceful workers restart
timeout = 1800

# Keep alive timeout
keepalive = 5

# Preload the application
preload_app = True

# Logging
accesslog = "/var/log/gunicorn_access.log"
errorlog = "/var/log/gunicorn_error.log"
loglevel = "info"
