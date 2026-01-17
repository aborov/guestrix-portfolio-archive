#!/bin/bash
# Script to monitor the Telnyx Bidirectional Streaming service

# Function to display usage
function show_usage {
    echo "Usage: $0 [option]"
    echo "Options:"
    echo "  logs    - Show service logs"
    echo "  status  - Check service status"
    echo "  restart - Restart the service"
    echo "  stop    - Stop the service"
    echo "  start   - Start the service"
    echo "  nginx   - Check Nginx status and logs"
    echo "  help    - Show this help message"
}

# Check if an argument was provided
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

# Process the argument
case "$1" in
    logs)
        echo "Showing service logs (press Ctrl+C to exit)..."
        sudo journalctl -u telnyx-gemini.service -f
        ;;
    status)
        echo "Checking service status..."
        sudo systemctl status telnyx-gemini.service
        ;;
    restart)
        echo "Restarting the service..."
        sudo systemctl restart telnyx-gemini.service
        echo "Service restarted."
        ;;
    stop)
        echo "Stopping the service..."
        sudo systemctl stop telnyx-gemini.service
        echo "Service stopped."
        ;;
    start)
        echo "Starting the service..."
        sudo systemctl start telnyx-gemini.service
        echo "Service started."
        ;;
    nginx)
        echo "Checking Nginx status..."
        sudo systemctl status nginx
        echo ""
        echo "Showing Nginx error logs (press Ctrl+C to exit)..."
        sudo tail -f /var/log/nginx/error.log
        ;;
    help)
        show_usage
        ;;
    *)
        echo "Unknown option: $1"
        show_usage
        exit 1
        ;;
esac
