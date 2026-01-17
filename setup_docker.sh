#!/bin/bash
# Script to set up LiveKit SIP using Docker for local testing

# Exit on error
set -e

# Set variables
API_KEY="guestrix_key"
API_SECRET="guestrix_secret"
CONFIG_DIR="./config"
DOCKER_DIR="."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored messages
print_message() {
    echo -e "${GREEN}[INFO] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

print_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

print_message "Setting up LiveKit SIP using Docker for local testing..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install it first."
    print_message "You can install it from https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_warning "Docker Compose is not installed. Checking if it's available via docker compose..."
    if ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not available. Please install it first."
        print_message "You can install it from https://docs.docker.com/compose/install/"
        exit 1
    else
        print_message "Docker Compose is available via 'docker compose'."
    fi
fi

# Create directories
print_message "Creating directories..."
mkdir -p ${CONFIG_DIR}

# Create configuration file for LiveKit
print_message "Creating LiveKit configuration file..."
cat > ${CONFIG_DIR}/livekit.yaml << EOF
port: 7880
rtc:
  tcp_port: 7881
  port_range_start: 50000
  port_range_end: 50100
  use_external_ip: false
keys:
  ${API_KEY}: ${API_SECRET}
logging:
  level: info
EOF

# Create configuration file for LiveKit SIP
print_message "Creating LiveKit SIP configuration file..."
cat > ${CONFIG_DIR}/sip-config.yaml << EOF
api_key: ${API_KEY}
api_secret: ${API_SECRET}
ws_url: ws://livekit:7880
redis:
  address: redis:6379
sip_port: 8080
rtp_port: 10000-10100
use_external_ip: false
logging:
  level: info
EOF

# Create docker-compose.yml
print_message "Creating docker-compose.yml..."
cat > docker-compose.yml << EOF
services:
  redis:
    image: redis:alpine
    ports:
      - "6380:6379"
    restart: unless-stopped

  livekit:
    image: livekit/livekit-server
    ports:
      - "7890:7880"
      - "7891:7881/tcp"
      - "7892:7882/udp"
      - "50200-50300:50000-50100/udp"
    volumes:
      - ./config/livekit.yaml:/livekit.yaml
    command: --config /livekit.yaml
    restart: unless-stopped

  livekit-sip:
    image: livekit/sip
    ports:
      - "8090:8080/udp"
      - "8090:8080/tcp"
      - "10200-10300:10000-10100/udp"
    volumes:
      - ./config/sip-config.yaml:/config.yaml
    command: --config /config.yaml
    depends_on:
      - redis
      - livekit
    restart: unless-stopped
EOF

print_message "LiveKit SIP Docker setup completed."
print_message ""
print_message "To start the services, run:"
print_message "cd $(pwd) && docker-compose up -d"
print_message ""
print_message "To stop the services, run:"
print_message "cd $(pwd) && docker-compose down"
print_message ""
print_message "To view logs, run:"
print_message "cd $(pwd) && docker-compose logs -f"

# Make the script executable
chmod +x ${0}
