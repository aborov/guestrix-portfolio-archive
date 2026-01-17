#!/bin/bash
# Flask App Deployment Script for AWS EC2
# This script automates the deployment of the Flask application to an AWS EC2 instance

set -e  # Exit on error

# Resolve script directory to make relative paths reliable
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Configuration
INSTANCE_TYPE="t2.micro"
AMI_ID="ami-0c02fb55956c7d316"  # Ubuntu Server 22.04 LTS (HVM) - Latest for us-east-2
KEY_NAME="guestrix-key-pair"
SECURITY_GROUP_NAME="guestrix-flask-sg"
REGION="us-east-2"
DOMAIN="dev.guestrix.ai"
REMOTE_APP_DIR="/app/dashboard"
LOCAL_APP_DIR="$SCRIPT_DIR/concierge"
LOCAL_TEMP_DIR="$SCRIPT_DIR/deploy_tmp_aws"

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

# Compute absolute path to SSH key
KEY_PATH="$SCRIPT_DIR/concierge/infra/$KEY_NAME.pem"

# Check if AWS CLI is configured
if ! aws configure list &> /dev/null; then
    print_error "AWS CLI is not configured. Please run 'aws configure' first."
    exit 1
fi

# Check if the key pair exists
print_message "Checking if key pair exists..."
if ! aws ec2 describe-key-pairs --region $REGION --key-names $KEY_NAME &> /dev/null; then
    print_error "Key pair '$KEY_NAME' not found. Please create it first."
    exit 1
fi

# Create or update security group
print_message "Creating/updating security group..."
SECURITY_GROUP_ID=$(aws ec2 describe-security-groups --region $REGION --group-names $SECURITY_GROUP_NAME --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [ "$SECURITY_GROUP_ID" = "None" ]; then
    print_message "Creating new security group..."
    SECURITY_GROUP_ID=$(aws ec2 create-security-group --region $REGION --group-name $SECURITY_GROUP_NAME --description "Security group for Guestrix Flask app" --query 'GroupId' --output text)

    # Add rules
    aws ec2 authorize-security-group-ingress --region $REGION --group-id $SECURITY_GROUP_ID --protocol tcp --port 22 --cidr 0.0.0.0/0
    aws ec2 authorize-security-group-ingress --region $REGION --group-id $SECURITY_GROUP_ID --protocol tcp --port 80 --cidr 0.0.0.0/0
    aws ec2 authorize-security-group-ingress --region $REGION --group-id $SECURITY_GROUP_ID --protocol tcp --port 443 --cidr 0.0.0.0/0
    aws ec2 authorize-security-group-ingress --region $REGION --group-id $SECURITY_GROUP_ID --protocol tcp --port 8080 --cidr 0.0.0.0/0
else
    print_message "Using existing security group: $SECURITY_GROUP_ID"
fi

# Check if instance already exists
print_message "Checking for existing instance..."
EXISTING_INSTANCE=$(aws ec2 describe-instances --region $REGION \
    --filters "Name=tag:Name,Values=guestrix-flask-dev" "Name=instance-state-name,Values=running,stopped,stopping" \
    --query 'Reservations[0].Instances[0].[InstanceId,State.Name]' \
    --output text 2>/dev/null)

if [ "$EXISTING_INSTANCE" != "None" ] && [ -n "$EXISTING_INSTANCE" ]; then
    INSTANCE_ID=$(echo "$EXISTING_INSTANCE" | awk '{print $1}')
    INSTANCE_STATE=$(echo "$EXISTING_INSTANCE" | awk '{print $2}')

    print_message "Found existing instance: $INSTANCE_ID (state: $INSTANCE_STATE)"

    if [ "$INSTANCE_STATE" = "stopped" ]; then
        print_message "Starting stopped instance..."
        aws ec2 start-instances --region $REGION --instance-ids $INSTANCE_ID
        print_message "Waiting for instance to be running..."
        aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID
    elif [ "$INSTANCE_STATE" = "stopping" ]; then
        print_message "Waiting for instance to stop completely..."
        aws ec2 wait instance-stopped --region $REGION --instance-ids $INSTANCE_ID
        print_message "Starting instance..."
        aws ec2 start-instances --region $REGION --instance-ids $INSTANCE_ID
        print_message "Waiting for instance to be running..."
        aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID
    else
        print_message "Instance is already running"
    fi
else
    # Launch new EC2 instance only if none exists
    print_message "No existing instance found. Launching new EC2 instance..."
    INSTANCE_ID=$(aws ec2 run-instances --region $REGION \
        --image-id $AMI_ID \
        --count 1 \
        --instance-type $INSTANCE_TYPE \
        --key-name $KEY_NAME \
        --security-group-ids $SECURITY_GROUP_ID \
        --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=guestrix-flask-dev}]' \
        --query 'Instances[0].InstanceId' \
        --output text)

    print_message "Instance launched with ID: $INSTANCE_ID"

    # Wait for instance to be running
    print_message "Waiting for instance to be running..."
    aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID
fi

# Get instance public DNS
INSTANCE_DNS=$(aws ec2 describe-instances --region $REGION --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].PublicDnsName' --output text)
INSTANCE_IP=$(aws ec2 describe-instances --region $REGION --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

print_message "Instance is running at: $INSTANCE_DNS ($INSTANCE_IP)"

# Verify PEM key exists and has correct permissions
if [ ! -f "$KEY_PATH" ]; then
    print_error "SSH key not found at $KEY_PATH"
    exit 1
fi
chmod 400 "$KEY_PATH" 2>/dev/null || true

# Wait for SSH to be available
print_message "Waiting for SSH to be available..."
for i in {1..30}; do
    if ssh -i "$KEY_PATH" -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=accept-new ubuntu@$INSTANCE_DNS "echo SSH ready" &> /dev/null; then
        print_message "SSH is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "SSH connection failed after 30 attempts"
        exit 1
    fi
    sleep 10
done

# Clean up any existing temp directory
rm -rf $LOCAL_TEMP_DIR
mkdir -p $LOCAL_TEMP_DIR

# Copy Flask application files selectively
print_message "Preparing Flask application files..."
rsync -av --exclude=".venv/" --exclude="__pycache__/" --exclude="node_modules/" \
    --exclude="lambda_*" --exclude="lambda_src/" --exclude="websocket*" --exclude="infra/" \
    --exclude="tests/" --exclude="docs/" --exclude=".git/" \
    --exclude="*.pyc" --exclude="*.pyo" --exclude="*.log" \
    --exclude=".DS_Store" --exclude="*.so" --exclude="*.dylib" \
    $LOCAL_APP_DIR/ $LOCAL_TEMP_DIR/concierge/

# Copy the full production requirements.txt for AWS deployment
print_message "Using full production requirements.txt for AWS deployment..."
cp $LOCAL_APP_DIR/requirements.txt $LOCAL_TEMP_DIR/requirements.txt

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
Description=Guestrix Flask Web Dashboard (Dev)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=$REMOTE_APP_DIR
Environment=PATH=$REMOTE_APP_DIR/venv/bin:/usr/bin
Environment=DISPLAY=:99
Environment=DEPLOYMENT_ENV=staging
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

# The number of worker processes (t2.micro has 1GB RAM)
workers = 1

# The type of workers to use
worker_class = "sync"

# The number of threads for handling requests
threads = 2

# The maximum number of requests a worker will process before restarting
max_requests = 1000

# The maximum jitter to add to max_requests
max_requests_jitter = 100

# Timeout for graceful workers restart (increased for long-running operations like property imports)
timeout = 300

# Keep alive timeout
keepalive = 10

# Preload the application
preload_app = True

# Logging
accesslog = "/var/log/gunicorn_access.log"
errorlog = "/var/log/gunicorn_error.log"
loglevel = "info"
EOL

# Create Nginx configuration
print_message "Creating Nginx configuration..."
cat > $LOCAL_TEMP_DIR/dashboard.nginx << EOL
server {
    server_name $DOMAIN;

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
        
        # Extended timeouts for long-running operations like property imports
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if (\$host = $DOMAIN) {
        return 301 https://\$host\$request_uri;
    }

    server_name $DOMAIN;
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

# Function to cleanup on exit
cleanup() {
    echo "Cleaning up temporary files..."
    rm -rf /tmp/flask_deploy
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Function to check if a command exists
command_exists() {
    command -v "\$1" >/dev/null 2>&1
}

# Function to check service status
check_service() {
    if systemctl is-active --quiet "\$1"; then
        echo "Service \$1 is running"
        return 0
    else
        echo "Service \$1 is not running"
        return 1
    fi
}

# Remove existing app directory if it exists (skip backup to save space)
if [ -d "\$APP_DIR" ]; then
    echo "Removing existing application directory..."
    sudo rm -rf "\$APP_DIR"
fi

# Ensure app directory exists with proper permissions
sudo mkdir -p "\$APP_DIR"
sudo chown -R ubuntu:ubuntu "\$APP_DIR"

# Copy all deployment files from temp location
if [ -d "/tmp/flask_deploy" ]; then
    echo "Copying deployment files to app directory..."
    cp -r /tmp/flask_deploy/* "\$APP_DIR/"
    chown -R ubuntu:ubuntu "\$APP_DIR"
fi

# Detect OS and set package manager
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=\$ID
    OS_VERSION=\$VERSION_ID
else
    echo "Cannot detect OS, defaulting to Amazon Linux"
    OS="amazon"
fi

echo "Detected OS: \$OS \$OS_VERSION"

# Set package manager and update commands based on OS
case \$OS in
    "ubuntu"|"debian")
        PKG_MANAGER="apt"
        UPDATE_CMD="sudo apt update -y"
        INSTALL_CMD="sudo apt install -y"
        PYTHON_PKG="python3 python3-pip python3-venv"
        NGINX_PKG="nginx"
        FIREFOX_PKG="firefox"
        CERTBOT_PKG="certbot python3-certbot-nginx"
        UPDATE_LOG="/var/log/last_apt_update"
        ;;
    "amazon"|"rhel"|"centos")
        PKG_MANAGER="yum"
        UPDATE_CMD="sudo yum update -y"
        INSTALL_CMD="sudo yum install -y"
        PYTHON_PKG="python3 python3-pip"
        NGINX_PKG="nginx"
        FIREFOX_PKG="firefox"
        CERTBOT_PKG="certbot python2-certbot-nginx"
        UPDATE_LOG="/var/log/last_yum_update"
        ;;
    *)
        echo "Unsupported OS: \$OS, defaulting to Amazon Linux commands"
        PKG_MANAGER="yum"
        UPDATE_CMD="sudo yum update -y"
        INSTALL_CMD="sudo yum install -y"
        PYTHON_PKG="python3 python3-pip"
        NGINX_PKG="nginx"
        FIREFOX_PKG="firefox"
        CERTBOT_PKG="certbot python2-certbot-nginx"
        UPDATE_LOG="/var/log/last_yum_update"
        ;;
esac

# Update system packages (only if not recently updated)
if [ ! -f \$UPDATE_LOG ] || [ \$(find \$UPDATE_LOG -mtime +1) ]; then
    echo "Updating system packages using \$PKG_MANAGER..."
    \$UPDATE_CMD
    sudo touch \$UPDATE_LOG
else
    echo "System packages recently updated, skipping..."
fi

# Install system dependencies (check if already installed)
echo "Installing system dependencies using \$PKG_MANAGER..."

# Install nginx
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    if [ "\$OS" = "amazon" ]; then
        # Use amazon-linux-extras for Amazon Linux 2
        sudo amazon-linux-extras install -y nginx1 || \$INSTALL_CMD \$NGINX_PKG
    else
        \$INSTALL_CMD \$NGINX_PKG
    fi
else
    echo "Nginx already installed"
fi

# Install Firefox for Selenium support (headless; Xvfb not required)
echo "Ensuring Firefox for Selenium headless support..."
\$INSTALL_CMD \$FIREFOX_PKG || true
if ! command -v firefox &> /dev/null; then
    # Try common Firefox locations
    for firefox_path in /usr/lib64/firefox/firefox /usr/lib/firefox/firefox /usr/bin/firefox; do
        if [ -x "\$firefox_path" ]; then
            sudo ln -sf "\$firefox_path" /usr/bin/firefox
            break
        fi
    done
fi

# Install Python 3
echo "Installing Python 3..."
if command -v python3 &> /dev/null; then
    echo "Python 3 already available: \$(python3 --version)"
else
    echo "Installing Python 3..."
    if [ "\$OS" = "amazon" ]; then
        # Use amazon-linux-extras for Amazon Linux 2
        sudo amazon-linux-extras install -y python3.8 || \$INSTALL_CMD python3 python3-pip
    else
        \$INSTALL_CMD \$PYTHON_PKG
    fi
fi

# Ensure we have pip for Python 3
if ! command -v pip3 &> /dev/null; then
    echo "Installing pip3..."
    \$INSTALL_CMD python3-pip || curl https://bootstrap.pypa.io/get-pip.py | python3
fi

# Verify Python version
python3 --version

# Install certbot for Let's Encrypt
if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    # Change to home directory to avoid directory issues
    cd ~
    
    if [ "\$OS" = "amazon" ]; then
        # Install EPEL repository for Amazon Linux 2
        sudo amazon-linux-extras install -y epel || true
        # Install certbot and nginx plugin
        \$INSTALL_CMD \$CERTBOT_PKG || {
            echo "Certbot yum installation failed, trying pip installation..."
            sudo pip3 install certbot certbot-nginx
        }
    else
        # For Ubuntu/Debian
        \$INSTALL_CMD \$CERTBOT_PKG || {
            echo "Certbot apt installation failed, trying pip installation..."
            sudo pip3 install certbot certbot-nginx
        }
    fi
else
    echo "Certbot already installed"
fi

# Set up Python virtual environment
echo "Setting up Python virtual environment..."
cd "\$APP_DIR"
# Remove old virtual environment if it exists (to handle Python version changes)
if [ -d "venv" ]; then
    echo "Removing old virtual environment..."
    rm -rf "venv"
fi

echo "Creating new virtual environment with Python 3..."
python3 -m venv "venv"

echo "Installing dependencies..."
source "venv/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# Install gunicorn and eventlet if not already installed
pip show gunicorn &> /dev/null || pip install gunicorn
pip show eventlet &> /dev/null || pip install eventlet

# Install specific version of google-cloud-firestore
pip install google-cloud-firestore==2.20.2

# Fix urllib3 compatibility issue with older OpenSSL versions
echo "Fixing urllib3 compatibility..."
if [ "\$OS" = "amazon" ]; then
    echo "Installing urllib3<2.0 for Amazon Linux 2 OpenSSL compatibility..."
    pip install 'urllib3<2.0'
else
    echo "Using default urllib3 for \$OS..."
fi

# Install additional dependencies that may be missing
echo "Installing additional required dependencies..."
pip install google-genai numpy boto3

# Fix import paths for lambda_src references
echo "Fixing import paths..."
find "\$APP_DIR" -name "*.py" -type f -exec sed -i 's/from concierge\.lambda_src\.firebase_admin_config import/from concierge.utils.firestore_client import/g' {} \;

# Clear Python cache to avoid import issues
echo "Clearing Python cache..."
find "\$APP_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "\$APP_DIR" -name "*.pyc" -type f -delete 2>/dev/null || true

# Create credentials symlink for Firebase
echo "Setting up Firebase credentials path..."
cd "\$APP_DIR"
ln -sf concierge/credentials credentials 2>/dev/null || true

# Fix Firebase credentials path in .env file for server deployment
echo "Fixing Firebase credentials path in .env file..."
if [ -f "concierge/.env" ]; then
    # Update GOOGLE_APPLICATION_CREDENTIALS to use server path
    sed -i 's|GOOGLE_APPLICATION_CREDENTIALS=/Users/aborov/Workspace/concierge/concierge/credentials/|GOOGLE_APPLICATION_CREDENTIALS=/app/dashboard/concierge/credentials/|g' concierge/.env
    echo "Updated GOOGLE_APPLICATION_CREDENTIALS path for server deployment"
else
    echo "Warning: .env file not found"
fi

# Create log files with proper permissions
echo "Setting up log files..."
sudo touch /var/log/gunicorn_access.log /var/log/gunicorn_error.log /var/log/dashboard.log /var/log/dashboard.error.log
sudo chown ubuntu:ubuntu /var/log/gunicorn_*.log /var/log/dashboard*.log

# Ensure proper ownership of the entire app directory
sudo chown -R ubuntu:ubuntu "\$APP_DIR"

# Set up Nginx and SSL
echo "Setting up Nginx and SSL..."
sudo systemctl enable nginx
# Create a temporary HTTP-only config for certbot
sudo tee /etc/nginx/conf.d/dashboard.conf > /dev/null << 'HTTPCONF'
server {
    server_name $DOMAIN;
    listen 80;

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
        
        # Extended timeouts for long-running operations like property imports
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
HTTPCONF

# Test and reload nginx
sudo nginx -t && sudo systemctl reload nginx

# Get SSL certificate using nginx plugin (most reliable method)
echo "Obtaining SSL certificate..."
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@guestrix.ai || {
    echo "Nginx plugin failed, trying standalone method..."
    sudo systemctl stop nginx
    sudo certbot certonly --standalone -d $DOMAIN --non-interactive --agree-tos --email admin@guestrix.ai || {
        echo "SSL certificate setup failed, continuing with HTTP-only"
        sudo systemctl start nginx
        exit 0
    }
    sudo systemctl start nginx
    # If standalone worked, manually configure nginx for SSL
    if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
        echo "Manually configuring nginx for SSL..."
        sudo cp "\$APP_DIR/dashboard.nginx" /etc/nginx/conf.d/dashboard.conf
        sudo nginx -t && sudo systemctl reload nginx
    fi
}

# Set up automatic certificate renewal
echo "Setting up automatic certificate renewal..."
sudo crontab -l 2>/dev/null | grep -q certbot || echo '0 12 * * * /usr/bin/certbot renew --quiet' | sudo crontab -

# Verify SSL setup
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "SSL certificate successfully configured!"
    echo "Certificate expires: \$(sudo certbot certificates 2>/dev/null | grep 'Expiry Date' | head -1 || echo 'Unknown')"
else
    echo "SSL certificate not obtained, running with HTTP-only config"
fi

# Xvfb is not required because Firefox runs in headless mode

# Set up systemd service
echo "Setting up systemd service..."
sudo cp "\$APP_DIR/dashboard.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dashboard.service
sudo systemctl restart dashboard.service

# Wait for service to start and verify
echo "Waiting for service to start..."
sleep 5
if sudo systemctl is-active --quiet dashboard.service; then
    echo "✅ Dashboard service is running successfully"
    # Test local connectivity
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q "302\|200"; then
        echo "✅ Application is responding correctly"
    else
        echo "⚠️  Application may not be responding correctly"
        sudo journalctl -u dashboard.service --no-pager -n 10
    fi
else
    echo "❌ Dashboard service failed to start"
    sudo systemctl status dashboard.service --no-pager
    sudo journalctl -u dashboard.service --no-pager -n 20
fi

# Perform final cleanup
cleanup

echo "Deployment completed successfully!"
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "Application is available at: https://$DOMAIN"
else
    echo "Application is available at: http://$DOMAIN"
fi
EOL

# Make setup script executable
chmod +x $LOCAL_TEMP_DIR/setup.sh

# Zip the application for transfer
print_message "Creating deployment package..."
DEPLOY_PACKAGE="flask_app_aws_$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf $DEPLOY_PACKAGE -C $LOCAL_TEMP_DIR .

# Transfer package to server
print_message "Transferring package to server..."
scp -i "$KEY_PATH" $DEPLOY_PACKAGE ubuntu@$INSTANCE_DNS:~/

# SSH into the instance and run deployment
print_message "Running deployment on server..."
ssh -i "$KEY_PATH" ubuntu@$INSTANCE_DNS "
set -e
sudo rm -rf /tmp/flask_deploy
mkdir -p /tmp/flask_deploy
tar -xzf ~/$DEPLOY_PACKAGE -C /tmp/flask_deploy
echo 'Files in deployment package:'
ls -la /tmp/flask_deploy/
# Copy requirements.txt to a safe location before setup
cp /tmp/flask_deploy/requirements.txt /tmp/requirements_safe.txt
sudo mkdir -p $REMOTE_APP_DIR
sudo cp -r /tmp/flask_deploy/* $REMOTE_APP_DIR/
sudo chown -R ubuntu:ubuntu $REMOTE_APP_DIR
echo 'Files copied to app directory:'
ls -la $REMOTE_APP_DIR/
sudo chmod +x $REMOTE_APP_DIR/setup.sh
cd /tmp && sudo ./flask_deploy/setup.sh
rm ~/$DEPLOY_PACKAGE
"

# Clean up
print_message "Cleaning up..."
rm -f $DEPLOY_PACKAGE
rm -rf $LOCAL_TEMP_DIR

print_message "Deployment completed successfully!"
print_message "Your application is now available at: https://$DOMAIN"
print_message "Instance ID: $INSTANCE_ID"
print_message "Instance DNS: $INSTANCE_DNS"
print_message "Instance IP: $INSTANCE_IP"

print_warning "Don't forget to:"
print_warning "1. Update your DNS records to point $DOMAIN to $INSTANCE_IP"
print_warning "2. Test the application at https://$DOMAIN"
