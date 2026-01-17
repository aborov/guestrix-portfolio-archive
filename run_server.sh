#!/bin/bash
# Script to run the Flask server

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

# Check if Docker is running
if ! docker ps &> /dev/null; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi

# Check if the LiveKit containers are running
if ! docker ps | grep -q "livekit_local-livekit-1"; then
    print_warning "LiveKit containers are not running. Starting them now..."
    docker-compose up -d

    # Wait for containers to start
    print_message "Waiting for containers to start..."
    sleep 5

    # Check if containers are running
    if ! docker ps | grep -q "livekit_local-livekit-1"; then
        print_error "LiveKit containers failed to start. Please check the logs with: docker-compose logs"
        exit 1
    fi
fi

# Check if the virtual environment exists
if [ ! -d "venv" ]; then
    print_warning "Virtual environment not found. Creating it now..."
    python3 -m venv venv
fi

# Activate the virtual environment
print_message "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! pip list | grep -q "flask"; then
    print_warning "Dependencies not installed. Installing them now..."
    pip install -r requirements.txt
fi

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    print_warning "ffmpeg is not installed. This is required for audio processing."
    print_message "On macOS, you can install it with: brew install ffmpeg"
    print_message "On Ubuntu, you can install it with: sudo apt-get install ffmpeg"
    print_message "Please install ffmpeg and try again."
fi

# Run the server
print_message "Starting the server..."
print_message "Open a new terminal and run: ngrok http 5001"
print_message "Then update your Twilio phone number's voice webhook URL with the ngrok URL + /twilio/voice"
print_message ""
print_message "Press Ctrl+C to stop the server."
python run_flask.py
