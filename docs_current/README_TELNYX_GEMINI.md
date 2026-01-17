# Telnyx Bidirectional Streaming with Gemini Live API

This project implements bidirectional audio streaming between Telnyx phone calls and Google's Gemini Live API. It allows callers to have real-time voice conversations with Gemini AI through a phone call.

## Overview

The system consists of several components:

1. **WebSocket Server**: Handles WebSocket connections from Telnyx for bidirectional audio streaming
2. **HTTP Webhook Handler**: Processes Telnyx webhooks for call events
3. **Gemini Live Client**: Connects to Gemini Live API for bidirectional audio streaming
4. **Audio Processor**: Handles audio format conversion between services
5. **Call Manager**: Tracks active calls and their states

## Architecture

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│             │         │             │         │             │
│   Caller    │◄───────►│   Telnyx    │◄───────►│  WebSocket  │
│             │         │             │         │   Server    │
└─────────────┘         └─────────────┘         └──────┬──────┘
                                                       │
                                                       │
                                                       ▼
                                               ┌───────────────┐
                                               │               │
                                               │ Audio Process │
                                               │               │
                                               └───────┬───────┘
                                                       │
                                                       │
                                                       ▼
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│             │         │             │         │             │
│   Gemini    │◄───────►│  Gemini API │◄───────►│ Gemini Live │
│   Model     │         │             │         │   Client    │
└─────────────┘         └─────────────┘         └─────────────┘
```

## Files

- `websocket/telnyx_bidirectional_streaming.py`: Main application entry point
- `websocket/gemini_live_client.py`: Gemini Live API client
- `websocket/audio_processor.py`: Audio processing utilities
- `websocket/call_manager.py`: Call state management
- `websocket/utils.py`: Helper functions
- `websocket/__init__.py`: Package initialization
- `run_telnyx_websocket.py`: Entry point script to run the server

## Requirements

- Python 3.8+
- aiohttp
- websockets
- google-generativeai
- python-dotenv

## Environment Variables

Create a `.env` file with the following variables:

```
# Telnyx settings
TELNYX_API_KEY=your_telnyx_api_key
TELNYX_WEBHOOK_URL=https://your-domain.com/telnyx/webhook
WEBSOCKET_URL=wss://your-domain.com:8083

# Google settings
GEMINI_API_KEY=your_gemini_api_key
```

## Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up environment variables in `.env`
4. Run the server:
   ```
   python run_telnyx_websocket.py
   ```

You can enable debug logging with:
```
python run_telnyx_websocket.py --debug
```

## Deployment

### EC2 Deployment

#### Automatic Deployment

We've provided a deployment script that automates the setup process:

1. SSH into your EC2 instance:
   ```
   ssh -i "guestrix-key-pair.pem" ubuntu@voice.guestrix.ai
   ```

2. Clone the repository:
   ```
   git clone https://github.com/yourusername/concierge.git
   cd concierge
   ```

3. Run the deployment script:
   ```
   ./deploy_telnyx_websocket.sh
   ```

The script will:
- Update system packages
- Install required dependencies
- Set up a virtual environment
- Install Python packages
- Configure the systemd service
- Set up Nginx as a reverse proxy
- Configure SSL with Let's Encrypt
- Start the service

#### Manual Deployment

If you prefer to deploy manually:

1. SSH into your EC2 instance:
   ```
   ssh -i "guestrix-key-pair.pem" ubuntu@voice.guestrix.ai
   ```

2. Install dependencies:
   ```
   sudo apt update
   sudo apt install -y python3-pip python3-venv nginx certbot python3-certbot-nginx
   ```

3. Clone the repository and set up a virtual environment:
   ```
   git clone https://github.com/yourusername/concierge.git
   cd concierge
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install google-generativeai
   ```

4. Create a `.env` file with your API keys:
   ```
   TELNYX_API_KEY=your_telnyx_api_key
   GEMINI_API_KEY=your_gemini_api_key
   WEBSOCKET_URL=wss://voice.guestrix.ai/ws/
   ```

5. Copy the systemd service file:
   ```
   sudo cp telnyx-gemini.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable telnyx-gemini.service
   ```

6. Set up Nginx as a reverse proxy:
   ```
   sudo nano /etc/nginx/sites-available/voice.guestrix.ai
   ```

   Add the following content:
   ```
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
   ```

7. Enable the site and set up SSL:
   ```
   sudo ln -sf /etc/nginx/sites-available/voice.guestrix.ai /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   sudo certbot --nginx -d voice.guestrix.ai
   ```

8. Start the service:
   ```
   sudo systemctl start telnyx-gemini
   ```

### Monitoring and Management

We've provided a script to help monitor and manage the service:

```
./monitor_telnyx_websocket.sh [option]
```

Options:
- `logs` - Show service logs
- `status` - Check service status
- `restart` - Restart the service
- `stop` - Stop the service
- `start` - Start the service
- `nginx` - Check Nginx status and logs

### Testing

To test the WebSocket connection:

```
./test_websocket.py
```

Or specify a different URL:

```
./test_websocket.py --url wss://voice.guestrix.ai/ws/
```

### Setting Up Telnyx

1. Create a Telnyx account and get an API key
2. Set up a SIP trunk or phone number
3. Configure the webhook URL to point to your server:
   ```
   https://your-domain.com/telnyx/webhook
   ```
4. Configure the WebSocket URL for bidirectional streaming:
   ```
   wss://your-domain.com:8083
   ```

## Usage

1. Call your Telnyx phone number
2. The system will answer the call and connect you to Gemini Live API
3. Speak naturally and Gemini will respond in real-time

## Troubleshooting

### Common Issues

1. **WebSocket connection fails**:
   - Check that your server is accessible from the internet
   - Verify that port 8083 is open in your firewall
   - Check the WebSocket URL in your Telnyx configuration

2. **Audio quality issues**:
   - Adjust the sample rate and codec settings
   - Check network bandwidth and latency

3. **Gemini API errors**:
   - Verify your API key is correct
   - Check that you have access to the Gemini Live API
   - Ensure you're using a supported model

### Logs

Check the logs for detailed error messages:
```
tail -f telnyx_bidirectional.log
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [Telnyx API Documentation](https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming)
- [Google Gemini Live API Documentation](https://ai.google.dev/docs/gemini_api_overview)
- [Telnyx WebSocket Demo](https://github.com/team-telnyx/demo-node-telnyx/tree/master/websocket-demos/websoket-openai-demo)
