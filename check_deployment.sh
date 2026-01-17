#!/bin/bash
# Script to check the status of the deployed Flask application

# Configuration
PROJECT_ID="clean-art-454915-d9"
INSTANCE_NAME="guestrix-web-dashboard"
ZONE="us-central1-a"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${YELLOW}=============== $1 ===============${NC}\n"
}

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud is not installed. Please install the Google Cloud SDK.${NC}"
    exit 1
fi

# Check project configuration
CURRENT_PROJECT=$(gcloud config get-value project)
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    echo -e "${YELLOW}Setting project to $PROJECT_ID (was $CURRENT_PROJECT)${NC}"
    gcloud config set project $PROJECT_ID
fi

print_header "Checking VM Instance Status"
gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format="table(name, status, networkInterfaces[0].accessConfigs[0].natIP)"

print_header "Dashboard Service Status"
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --ssh-flag="-o ConnectTimeout=5" --command="sudo systemctl status dashboard.service"

print_header "Nginx Service Status"
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --ssh-flag="-o ConnectTimeout=5" --command="sudo systemctl status nginx"

print_header "Recent Application Logs"
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --ssh-flag="-o ConnectTimeout=5" --command="sudo tail -n 20 /app/dashboard/error.log"

print_header "Network Configuration"
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --ssh-flag="-o ConnectTimeout=5" --command="curl -s http://localhost:8080 > /dev/null && echo 'Application responding on localhost:8080: YES' || echo 'Application responding on localhost:8080: NO'"

print_header "Firewall Rules"
gcloud compute firewall-rules list --filter="network=default AND direction=INGRESS AND (allowed.ports=http OR allowed.ports=https)" --format="table(name, network, direction, allowed)"

print_header "SSL Certificate Status"
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --ssh-flag="-o ConnectTimeout=5" --command="sudo certbot certificates | grep -A2 app.guestrix.ai || echo 'No SSL certificate found for app.guestrix.ai'"

echo -e "\n${GREEN}Status check completed. Access your application at: https://app.guestrix.ai${NC}\n" 