#!/bin/bash
# Flask App Deployment Script for Google Cloud Compute Engine
# This script automates the deployment of the Flask application to a Google Cloud VM

set -e  # Exit on error

# Configuration
PROJECT_ID="clean-art-454915-d9"
INSTANCE_NAME="guestrix-web-dashboard"
ZONE="us-central1-a"
REMOTE_APP_DIR="/app/dashboard"
LOCAL_APP_DIR="./concierge"
LOCAL_TEMP_DIR="./deploy_tmp"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_message() {
    echo -e "${GREEN}[DEPLOY] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    print_error "gcloud is not installed. Please install the Google Cloud SDK."
    exit 1
fi

# Check if project ID is set
print_message "Checking gcloud configuration..."
CURRENT_PROJECT=$(gcloud config get-value project)
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    print_warning "Current project is $CURRENT_PROJECT, setting to $PROJECT_ID"
    gcloud config set project $PROJECT_ID
fi

# Create temporary directory for deployment
print_message "Creating temporary directory for deployment..."
mkdir -p $LOCAL_TEMP_DIR

# Clean the temp directory if it exists
rm -rf $LOCAL_TEMP_DIR/*

# Create a fresh copy of the entire Flask application
print_message "Creating a fresh copy of the Flask application..."
mkdir -p $LOCAL_TEMP_DIR/concierge
print_message "Copying files from $LOCAL_APP_DIR to $LOCAL_TEMP_DIR/concierge (excluding virtual environments)..."
rsync -av --exclude="*/.venv" --exclude="*/__pycache__" $LOCAL_APP_DIR/ $LOCAL_TEMP_DIR/concierge/

# Create an entry point app.py in the root directory
print_message "Creating entry point app.py..."
cat > $LOCAL_TEMP_DIR/app.py << EOL
# Flask application entry point
import os
import sys

# Add the current directory to the path so that 'concierge' can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the Flask application
from concierge.app import app

if __name__ == '__main__':
    # This section is only executed when running the file directly
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
EOL

# Create a WSGI entry point for gunicorn
print_message "Creating WSGI entry point..."
cat > $LOCAL_TEMP_DIR/wsgi.py << EOL
# WSGI entry point for gunicorn
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the Flask application directly from concierge/app.py
from concierge.app import app as application

# For debugging
print(f"Python path: {sys.path}")
print(f"Current directory: {os.path.abspath(os.path.dirname(__file__))}")
EOL

# Create systemd service file
print_message "Creating systemd service file..."
cat > $LOCAL_TEMP_DIR/dashboard.service << EOL
[Unit]
Description=Guestrix Flask Web Dashboard
After=network.target

[Service]
User=ubuntu
WorkingDirectory=$REMOTE_APP_DIR
Environment=PATH=$REMOTE_APP_DIR/venv/bin:/usr/bin
Environment=DEPLOYMENT_ENV=production
Environment=GOOGLE_APPLICATION_CREDENTIALS=$REMOTE_APP_DIR/concierge/credentials/clean-art-454915-d9-firebase-adminsdk-fbsvc-9e1734f79e.json
Environment=MOZ_HEADLESS=1
Environment=FIREFOX_BINARY=/usr/bin/firefox
ExecStart=$REMOTE_APP_DIR/venv/bin/gunicorn -c $REMOTE_APP_DIR/gunicorn.conf.py wsgi:application
Restart=always
StandardOutput=append:/var/log/dashboard.log
StandardError=append:/var/log/dashboard.error.log

[Install]
WantedBy=multi-user.target
EOL

# Create gunicorn configuration
print_message "Creating gunicorn configuration..."
cat > $LOCAL_TEMP_DIR/gunicorn.conf.py << EOL
"""
Gunicorn configuration file.
"""

# The socket to bind
bind = "0.0.0.0:8080"

# The number of worker processes (favor lower memory footprint)
workers = 1

# The type of workers to use
worker_class = "sync"

# The number of threads for handling requests
threads = 2

# The maximum number of simultaneous clients
worker_connections = 1000

# The maximum number of requests a worker will process before restarting
max_requests = 1000

# The maximum number of requests a worker will process before restarting (jitter)
max_requests_jitter = 100

# The timeout for long-running operations like property imports
timeout = 600

# The timeout for worker processes to gracefully shutdown
graceful_timeout = 30

# The number of seconds to wait for requests on a Keep-Alive connection
keepalive = 5

# The path to the error log file
errorlog = "$REMOTE_APP_DIR/error.log"

# The path to the access log file
accesslog = "$REMOTE_APP_DIR/access.log"

# The log level
loglevel = "info"
EOL

# Create Nginx configuration
print_message "Creating Nginx configuration..."
cat > $LOCAL_TEMP_DIR/dashboard.nginx << EOL
server {
    server_name app.guestrix.ai;

    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        # Extended timeouts for long-running operations like property imports
        proxy_connect_timeout 120s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/app.guestrix.ai/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.guestrix.ai/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if (\$host = app.guestrix.ai) {
        return 301 https://\$host\$request_uri;
    }

    server_name app.guestrix.ai;
    listen 80;
    return 404;
}
EOL

# Create deployment script to run on the server
print_message "Creating remote deployment script..."
cat > $LOCAL_TEMP_DIR/setup.sh << EOL
#!/bin/bash
# Server-side setup script

set -e  # Exit on error

APP_DIR="$REMOTE_APP_DIR"
BACKUP_DIR="\${APP_DIR}_backup_\$(date +%Y%m%d_%H%M%S)"

# Cleanup function
cleanup() {
    echo "Performing cleanup..."

    # Remove old backups (keep only last 2)
    echo "Cleaning up old backups..."
    ls -dt \${APP_DIR}_backup_* | tail -n +3 | xargs -r sudo rm -rf

    # Clean up old log files
    echo "Cleaning up old log files..."
    sudo find /var/log -name "dashboard*.log*" -type f -mtime +7 -delete

    # Clean up pip cache
    echo "Cleaning up pip cache..."
    sudo rm -rf ~/.cache/pip

    # Clean up temporary files
    echo "Cleaning up temporary files..."
    sudo rm -rf /tmp/*

    # Clean up old Python bytecode files
    echo "Cleaning up Python bytecode files..."
    sudo find \$APP_DIR -name "*.pyc" -delete
    sudo find \$APP_DIR -name "__pycache__" -type d -exec rm -rf {} +

    # Do NOT remove venv in cleanup; we recreate/upgrade it explicitly below
}

# Perform cleanup before deployment
cleanup

# Create backup of current app
if [ -d "\$APP_DIR" ]; then
    echo "Creating backup of current application..."
    sudo cp -r "\$APP_DIR" "\$BACKUP_DIR"
fi

# Ensure app directory exists with proper permissions
sudo mkdir -p "\$APP_DIR"
sudo chown -R ubuntu:ubuntu "\$APP_DIR"

# Copy requirements.txt to the root directory
echo "Copying requirements.txt to the root directory..."
sudo cp "\$APP_DIR/concierge/requirements.txt" "\$APP_DIR/"

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv nginx certbot python3-certbot-nginx || true

# Ensure Firefox is available for Selenium (headless)
if ! command -v firefox >/dev/null 2>&1; then
  echo "Installing Firefox..."
  sudo apt-get install -y firefox || true
  if ! command -v firefox >/dev/null 2>&1 && command -v snap >/dev/null 2>&1; then
    echo "Installing Firefox via snap..."
    sudo snap install firefox --classic || true
  fi
fi

# Create a stable /usr/bin/firefox entry if needed
if ! command -v firefox >/dev/null 2>&1; then
  if [ -x /snap/bin/firefox ]; then
    echo "Linking /snap/bin/firefox to /usr/bin/firefox..."
    sudo ln -sf /snap/bin/firefox /usr/bin/firefox
  elif [ -x /usr/lib/firefox/firefox ]; then
    echo "Linking /usr/lib/firefox/firefox to /usr/bin/firefox..."
    sudo ln -sf /usr/lib/firefox/firefox /usr/bin/firefox
  fi
fi

# Set up Python virtual environment (create if missing, reuse otherwise)
echo "Ensuring Python virtual environment..."
if [ ! -d "\$APP_DIR/venv" ]; then
  python3 -m venv "\$APP_DIR/venv"
fi
source "\$APP_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "\$APP_DIR/requirements.txt"
pip install gunicorn eventlet

# Install latest version of google-cloud-firestore for Vector Search support
echo "Installing latest google-cloud-firestore with Vector support..."
pip install --upgrade google-cloud-firestore==2.20.2
pip install --upgrade firebase-admin>=6.2.0

# Fix any potential import issues with the Vector class
echo "Fixing potential import issues with the Vector class..."
if grep -q "from google.cloud.firestore_v1.vector import Vector" "\$APP_DIR/concierge/utils/firestore_client.py"; then
    echo "Fixing Vector import in firestore_client.py..."
    sudo sed -i 's/from google.cloud.firestore_v1.vector import Vector/from google.cloud.firestore_v1 import vector\\n# Vector class is now accessed as vector.Vector/g' "\$APP_DIR/concierge/utils/firestore_client.py"
    sudo sed -i 's/\([^\.]\)Vector(/\1vector.Vector(/g' "\$APP_DIR/concierge/utils/firestore_client.py"
fi

# Set up Nginx
echo "Setting up Nginx..."
sudo cp "\$APP_DIR/dashboard.nginx" /etc/nginx/sites-available/dashboard
sudo ln -sf /etc/nginx/sites-available/dashboard /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# Set up SSL with Let's Encrypt
echo "Setting up SSL with Let's Encrypt..."
sudo certbot --nginx -d app.guestrix.ai --non-interactive --agree-tos --email admin@guestrix.ai || true

# Set up systemd service
echo "Setting up systemd service..."
sudo cp "\$APP_DIR/dashboard.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard.service
sudo systemctl restart dashboard.service

# Xvfb no longer required: Firefox runs in headless mode

# Perform final cleanup (no venv removal)
echo "Final cleanup complete"

echo "Deployment completed successfully!"
EOL

# Make setup script executable
chmod +x $LOCAL_TEMP_DIR/setup.sh

# Zip the application for transfer
print_message "Creating deployment package..."
DEPLOY_PACKAGE="flask_app_$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf $DEPLOY_PACKAGE -C $LOCAL_TEMP_DIR .

# Transfer package to server
print_message "Transferring package to server..."
gcloud compute scp $DEPLOY_PACKAGE $INSTANCE_NAME:~/ --zone=$ZONE

# SSH into the instance and run deployment
print_message "Running deployment on server..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="
set -e
sudo rm -rf /tmp/flask_deploy
mkdir -p /tmp/flask_deploy
tar -xzf ~/$DEPLOY_PACKAGE -C /tmp/flask_deploy
sudo mkdir -p $REMOTE_APP_DIR
sudo cp -r /tmp/flask_deploy/* $REMOTE_APP_DIR/
sudo chown -R ubuntu:ubuntu $REMOTE_APP_DIR
sudo chmod +x $REMOTE_APP_DIR/setup.sh
cd $REMOTE_APP_DIR && sudo ./setup.sh
rm ~/$DEPLOY_PACKAGE
"

# Clean up
print_message "Cleaning up..."
rm -f $DEPLOY_PACKAGE
rm -rf $LOCAL_TEMP_DIR

print_message "Deployment completed successfully!"
print_message "Your application is now available at: https://app.guestrix.ai"