#!/bin/bash
# Deployment script for Telnyx Bidirectional Streaming with Gemini Live API

# Exit on error
set -e

echo "Starting deployment of Telnyx Bidirectional Streaming with Gemini Live API..."

# Check if running as root
if [ "$EUID" -eq 0 ]; then
  echo "Please run this script as a regular user, not as root."
  exit 1
fi

# Update system packages
echo "Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install required packages
echo "Installing required packages..."
sudo apt install -y python3-pip python3-venv nginx certbot python3-certbot-nginx

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Install Google Generative AI
echo "Installing Google Generative AI..."
pip install google-generativeai

# Copy systemd service file
echo "Setting up systemd service..."
sudo cp telnyx-gemini.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telnyx-gemini.service

# Set up Nginx
echo "Setting up Nginx..."
sudo tee /etc/nginx/sites-available/voice.guestrix.ai > /dev/null << 'EOF'
server {
    listen 80;
    server_name voice.guestrix.ai;

    location /telnyx/ {
        proxy_pass http://localhost:8082;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket endpoint
    location /ws/ {
        proxy_pass http://localhost:8083;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        return 404;
    }
}
EOF

# Enable the site
sudo ln -sf /etc/nginx/sites-available/voice.guestrix.ai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Set up SSL with Let's Encrypt
echo "Setting up SSL with Let's Encrypt..."
sudo certbot --nginx -d voice.guestrix.ai --non-interactive --agree-tos --email tools@guestrix.ai

# Start the service
echo "Starting the service..."
sudo systemctl start telnyx-gemini.service

# Check service status
echo "Checking service status..."
sudo systemctl status telnyx-gemini.service

echo "Deployment completed successfully!"
echo "The service is now running at https://voice.guestrix.ai/telnyx/"
echo "WebSocket server is available at wss://voice.guestrix.ai/ws/"
