#!/bin/bash
# Deployment script for websocket server changes
# This script packages and deploys the updated websocket files to the EC2 server

# Set variables
EC2_HOST="ubuntu@ec2-3-130-141-92.us-east-2.compute.amazonaws.com"
SSH_KEY="./concierge/infra/guestrix-key-pair.pem"
REMOTE_DIR="/home/ubuntu/telnyx_websocket/websocket"
LOCAL_DIR="./websocket"
TEMP_DIR="./deploy_temp"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="${REMOTE_DIR}_backup_${TIMESTAMP}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    echo -e "${GREEN}[DEPLOY] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    print_error "SSH key not found: $SSH_KEY"
    print_message "Checking for alternative key locations..."

    # Try to find the key in the infra directory
    INFRA_KEY="./concierge/infra/guestrix-key-pair.pem"
    if [ -f "$INFRA_KEY" ]; then
        print_message "Found key at $INFRA_KEY"
        SSH_KEY="$INFRA_KEY"
    else
        print_error "No SSH key found. Please provide the correct path to the SSH key."
        exit 1
    fi
fi

# Make sure the SSH key has the right permissions
chmod 600 "$SSH_KEY"

# Create temporary directory for deployment
print_message "Creating temporary directory for deployment..."
mkdir -p "$TEMP_DIR"

# Copy files to temporary directory
print_message "Copying files to temporary directory..."
cp "$LOCAL_DIR/telnyx_bidirectional_streaming.py" "$TEMP_DIR/"
cp "$LOCAL_DIR/gemini_live_client.py" "$TEMP_DIR/"
cp "$LOCAL_DIR/audio_processor.py" "$TEMP_DIR/"
cp "$LOCAL_DIR/utils.py" "$TEMP_DIR/"
cp "$LOCAL_DIR/call_manager.py" "$TEMP_DIR/"

# Create a deployment package
print_message "Creating deployment package..."
DEPLOY_PACKAGE="websocket_deploy_${TIMESTAMP}.tar.gz"
tar -czf "$DEPLOY_PACKAGE" -C "$TEMP_DIR" .

# Test SSH connection
print_message "Testing SSH connection to $EC2_HOST..."
ssh -i "$SSH_KEY" -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$EC2_HOST" "echo Connection successful" > /dev/null 2>&1

if [ $? -ne 0 ]; then
    print_error "Failed to connect to $EC2_HOST. Please check your SSH key and connection."
    exit 1
fi

print_message "SSH connection successful."

# Create backup of current files on the server
print_message "Creating backup of current files on the server..."
ssh -i "$SSH_KEY" "$EC2_HOST" "sudo cp -r $REMOTE_DIR $BACKUP_DIR"

# Transfer the deployment package
print_message "Transferring deployment package to server..."
scp -i "$SSH_KEY" "$DEPLOY_PACKAGE" "$EC2_HOST:/tmp/"

# Deploy the files
print_message "Deploying files on the server..."
ssh -i "$SSH_KEY" "$EC2_HOST" "sudo tar -xzf /tmp/$DEPLOY_PACKAGE -C $REMOTE_DIR"

# Check if the telnyx-gemini service exists
print_message "Checking if telnyx-gemini service exists..."
ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl is-active telnyx-gemini" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    # Restart the service
    print_message "Restarting telnyx-gemini service..."
    ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl restart telnyx-gemini"

    # Check if the service started successfully
    sleep 2
    ssh -i "$SSH_KEY" "$EC2_HOST" "sudo systemctl is-active telnyx-gemini" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        print_message "Service restarted successfully."
    else
        print_error "Failed to restart the service. Checking logs..."
        ssh -i "$SSH_KEY" "$EC2_HOST" "sudo journalctl -u telnyx-gemini -n 20"
    fi
else
    print_warning "telnyx-gemini service not found. You may need to start it manually."
    print_message "Checking for running Python processes..."
    ssh -i "$SSH_KEY" "$EC2_HOST" "ps aux | grep python | grep -v grep"

    # Try to restart the process manually
    print_message "Attempting to restart the process manually..."
    ssh -i "$SSH_KEY" "$EC2_HOST" "cd /home/ubuntu/telnyx_websocket && ./run_telnyx_websocket.py"
fi

# Clean up
print_message "Cleaning up temporary files..."
rm -rf "$TEMP_DIR"
rm "$DEPLOY_PACKAGE"

print_message "Deployment completed."
print_message "You can check the logs with: ssh -i $SSH_KEY $EC2_HOST 'sudo journalctl -u telnyx-gemini -n 100 || cat /home/ubuntu/telnyx_websocket/telnyx_bidirectional.log'"
print_message "If needed, you can restore from backup with: ssh -i $SSH_KEY $EC2_HOST 'sudo cp -r $BACKUP_DIR/* $REMOTE_DIR/'"
