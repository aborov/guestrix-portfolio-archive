#!/bin/bash

# Script to update a single file on AWS staging server
set -e

INSTANCE_IP="3.129.87.54"
KEY_PATH="concierge/infra/guestrix-key-pair.pem"
SOURCE_FILE="concierge/static/js/guest_dashboard_utils.js"
TARGET_PATH="/app/dashboard/concierge/static/js/guest_dashboard_utils.js"

echo "Updating guest_dashboard_utils.js on AWS staging server..."

# Set correct permissions on key
chmod 400 "$KEY_PATH"

# Create a temporary script to execute on the remote server
cat > /tmp/update_file.sh << 'EOF'
#!/bin/bash
# Download the file content and update it
sudo cp /tmp/guest_dashboard_utils.js /app/dashboard/concierge/static/js/guest_dashboard_utils.js
sudo chown ubuntu:ubuntu /app/dashboard/concierge/static/js/guest_dashboard_utils.js
sudo chmod 644 /app/dashboard/concierge/static/js/guest_dashboard_utils.js

# Verify the update
echo "Verifying file update..."
grep -n "CRITICAL: When a guest asks about WiFi information" /app/dashboard/concierge/static/js/guest_dashboard_utils.js

# Restart the service
sudo systemctl restart dashboard
sleep 3
sudo systemctl status dashboard --no-pager -l

echo "File update completed successfully!"
EOF

# Try to copy the file using different methods
echo "Attempting to copy file to AWS instance..."

# Method 1: Try direct scp
if scp -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$KEY_PATH" "$SOURCE_FILE" "ubuntu@$INSTANCE_IP:/tmp/guest_dashboard_utils.js" 2>/dev/null; then
    echo "File copied successfully via scp"
    # Copy and execute the update script
    scp -o StrictHostKeyChecking=no -i "$KEY_PATH" /tmp/update_file.sh "ubuntu@$INSTANCE_IP:/tmp/update_file.sh"
    ssh -o StrictHostKeyChecking=no -i "$KEY_PATH" "ubuntu@$INSTANCE_IP" "chmod +x /tmp/update_file.sh && /tmp/update_file.sh"
else
    echo "SCP failed, trying alternative method..."
    
    # Method 2: Try using SSH with base64 encoding
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$KEY_PATH" "ubuntu@$INSTANCE_IP" "echo 'test'" 2>/dev/null; then
        echo "SSH connection successful, using base64 transfer..."
        
        # Encode the file and transfer via SSH
        base64 -i "$SOURCE_FILE" | ssh -o StrictHostKeyChecking=no -i "$KEY_PATH" "ubuntu@$INSTANCE_IP" "base64 -d > /tmp/guest_dashboard_utils.js"
        
        # Execute the update
        ssh -o StrictHostKeyChecking=no -i "$KEY_PATH" "ubuntu@$INSTANCE_IP" "$(cat /tmp/update_file.sh)"
    else
        echo "ERROR: Cannot connect to AWS instance. Please check:"
        echo "1. Instance is running"
        echo "2. Security group allows SSH (port 22)"
        echo "3. Key pair is correct"
        exit 1
    fi
fi

echo "AWS staging server update completed!"
