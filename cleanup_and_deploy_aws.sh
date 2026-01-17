#!/bin/bash
# Simple cleanup and deployment script for AWS EC2

set -e

# Configuration
INSTANCE_DNS="ec2-3-129-87-54.us-east-2.compute.amazonaws.com"
KEY_PATH="concierge/infra/guestrix-key-pair.pem"
REMOTE_APP_DIR="/app/dashboard"

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

# Step 1: Clean up the instance
print_message "Cleaning up EC2 instance..."
ssh -i "$KEY_PATH" ec2-user@$INSTANCE_DNS "
    echo 'Stopping any running services...'
    sudo systemctl stop dashboard || true
    sudo systemctl stop nginx || true

    echo 'Cleaning up disk space...'
    sudo rm -rf /app/*
    sudo rm -rf /tmp/*
    sudo rm -rf /var/log/*.log
    sudo rm -rf /home/ec2-user/*.tar.gz
    sudo yum clean all

    echo 'Current disk usage:'
    df -h
"

# Step 2: Create minimal deployment package
print_message "Creating minimal deployment package..."
rm -rf ./deploy_minimal
mkdir -p ./deploy_minimal

# Copy only essential Flask files
print_message "Copying essential Flask files..."
cp -r concierge/templates ./deploy_minimal/
cp -r concierge/static ./deploy_minimal/
cp -r concierge/utils ./deploy_minimal/
cp -r concierge/api ./deploy_minimal/
cp -r concierge/auth ./deploy_minimal/
cp -r concierge/views ./deploy_minimal/
cp -r concierge/sockets ./deploy_minimal/
cp -r concierge/credentials ./deploy_minimal/
cp concierge/app.py ./deploy_minimal/
cp concierge/config.py ./deploy_minimal/
cp concierge/.env ./deploy_minimal/

# Create simplified requirements.txt (matching local versions)
cat > ./deploy_minimal/requirements.txt << EOL
# Web framework
Flask==3.0.2
Flask-SocketIO==5.3.6
python-socketio==5.11.1
websockets>=13.0.0,<15.1.0
gunicorn==21.2.0
eventlet==0.36.1

# Environment and utilities
python-dotenv==1.0.1
requests==2.31.0
icalendar==5.0.11
APScheduler==3.10.4

# Firebase / Google Cloud (core only)
firebase-admin==6.4.0
google-cloud-firestore==2.14.0
google-auth==2.27.0

# AWS SDK (for DynamoDB conversations)
boto3==1.34.34

# File Processing (basic only)
pypdf==5.5.0
python-docx==1.1.0
EOL

# Create WSGI entry point
cat > ./deploy_minimal/wsgi.py << EOL
import os
import sys

# Add the current directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the Flask application
from app import app as application

if __name__ == "__main__":
    application.run()
EOL

# Create gunicorn config
cat > ./deploy_minimal/gunicorn.conf.py << EOL
bind = "0.0.0.0:8080"
workers = 1
worker_class = "eventlet"
worker_connections = 100
timeout = 30
keepalive = 2
max_requests = 500
preload_app = True
accesslog = "/var/log/gunicorn_access.log"
errorlog = "/var/log/gunicorn_error.log"
loglevel = "info"
EOL

# Create systemd service
cat > ./deploy_minimal/dashboard.service << EOL
[Unit]
Description=Guestrix Flask Web Dashboard (Dev)
After=network.target

[Service]
User=ec2-user
WorkingDirectory=$REMOTE_APP_DIR
Environment=PATH=$REMOTE_APP_DIR/venv/bin
ExecStart=$REMOTE_APP_DIR/venv/bin/gunicorn -c $REMOTE_APP_DIR/gunicorn.conf.py wsgi:application
Restart=always
StandardOutput=append:/var/log/dashboard.log
StandardError=append:/var/log/dashboard.error.log

[Install]
WantedBy=multi-user.target
EOL

# Create nginx config
cat > ./deploy_minimal/dashboard.nginx << EOL
server {
    server_name dev.guestrix.ai;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    listen 80;
}
EOL

# Create setup script
cat > ./deploy_minimal/setup.sh << EOL
#!/bin/bash
set -e

APP_DIR="$REMOTE_APP_DIR"

echo "Setting up application directory..."
sudo mkdir -p "\$APP_DIR"
sudo chown -R ec2-user:ec2-user "\$APP_DIR"

echo "Installing system dependencies..."
sudo amazon-linux-extras install -y nginx1

echo "Installing Python 3.9..."
# Install development tools needed to compile Python
sudo yum groupinstall -y "Development Tools"
sudo yum install -y openssl-devel bzip2-devel libffi-devel zlib-devel

# Download and compile Python 3.9.6
cd /tmp
wget https://www.python.org/ftp/python/3.9.6/Python-3.9.6.tgz
tar xzf Python-3.9.6.tgz
cd Python-3.9.6
./configure --enable-optimizations --with-ensurepip=install
make -j \$(nproc)
sudo make altinstall

# Set up alternatives for python3 and pip3
sudo alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.9 1
sudo alternatives --install /usr/bin/pip3 pip3 /usr/local/bin/pip3.9 1

# Clean up
cd /
rm -rf /tmp/Python-3.9.6*

# Verify installation
python3 --version
pip3 --version

echo "Setting up Python virtual environment..."
python3 -m venv "\$APP_DIR/venv"
source "\$APP_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "\$APP_DIR/requirements.txt"

echo "Setting up Nginx..."
sudo cp "\$APP_DIR/dashboard.nginx" /etc/nginx/conf.d/dashboard.conf
sudo nginx -t && sudo systemctl restart nginx
sudo systemctl enable nginx

echo "Setting up systemd service..."
sudo cp "\$APP_DIR/dashboard.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard.service
sudo systemctl restart dashboard.service

echo "Deployment completed successfully!"
EOL

chmod +x ./deploy_minimal/setup.sh

# Step 3: Create deployment package
print_message "Creating deployment package..."
tar -czf minimal_flask_app.tar.gz -C ./deploy_minimal .

# Step 4: Transfer and deploy
print_message "Transferring package to server..."
scp -i "$KEY_PATH" minimal_flask_app.tar.gz ec2-user@$INSTANCE_DNS:~/

print_message "Running deployment on server..."
ssh -i "$KEY_PATH" ec2-user@$INSTANCE_DNS "
    set -e

    echo 'Extracting deployment package...'
    sudo mkdir -p $REMOTE_APP_DIR
    sudo tar -xzf ~/minimal_flask_app.tar.gz -C $REMOTE_APP_DIR
    sudo chown -R ec2-user:ec2-user $REMOTE_APP_DIR

    echo 'Running setup script...'
    cd $REMOTE_APP_DIR && sudo ./setup.sh

    echo 'Cleaning up...'
    rm ~/minimal_flask_app.tar.gz

    echo 'Checking service status...'
    sudo systemctl status dashboard --no-pager -l

    echo 'Final disk usage:'
    df -h
"

# Step 5: Clean up local files
print_message "Cleaning up local files..."
rm -rf ./deploy_minimal
rm -f minimal_flask_app.tar.gz

print_message "Deployment completed successfully!"
print_message "Your application should be available at: http://dev.guestrix.ai"
print_message "Instance: $INSTANCE_DNS"

print_warning "Don't forget to:"
print_warning "1. Update DNS records to point dev.guestrix.ai to the instance IP"
print_warning "2. Set up SSL certificates if needed"
print_warning "3. Test the application"
