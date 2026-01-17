#!/bin/bash
# Script to fix the import statement in firestore_client.py

set -e  # Exit on error

# Configuration
INSTANCE_NAME="guestrix-web-dashboard"
ZONE="us-central1-a"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_message() {
    echo -e "${GREEN}[UPDATE] $1${NC}"
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

# SSH into the instance and run the fix script
print_message "Running fix commands on the server..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --command="
set -e
# Stop the service
sudo systemctl stop dashboard.service || true

# Fix the import statement directly using sed
sudo sed -i 's/from google.cloud.firestore_v1.vector import Vector/from google.cloud.firestore_v1 import vector\\n# Vector class is now accessed as vector.Vector/g' /app/dashboard/concierge/utils/firestore_client.py

# Fix any usage of Vector with vector.Vector
sudo sed -i 's/\([^\.]\)Vector(/\1vector.Vector(/g' /app/dashboard/concierge/utils/firestore_client.py

# Reload systemd and restart services
sudo systemctl daemon-reload
sudo systemctl restart dashboard.service

# Check service status
sudo systemctl status dashboard.service
"

print_message "Fix completed!"
print_message "Your application should now be available at: https://app.guestrix.ai"
