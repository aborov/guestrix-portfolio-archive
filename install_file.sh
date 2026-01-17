#!/bin/bash
set -e

# Download file from S3
echo "📥 Downloading file from S3..."
aws s3 cp s3://guestrix-deployment-files/guest_dashboard_utils.js /tmp/guest_dashboard_utils.js

# Create backup of existing file
echo "💾 Creating backup..."
sudo cp /app/dashboard/concierge/static/js/guest_dashboard_utils.js /app/dashboard/concierge/static/js/guest_dashboard_utils.js.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || echo "No existing file to backup"

# Install the new file
echo "🔧 Installing new file..."
sudo cp /tmp/guest_dashboard_utils.js /app/dashboard/concierge/static/js/guest_dashboard_utils.js

# Set correct permissions
sudo chown www-data:www-data /app/dashboard/concierge/static/js/guest_dashboard_utils.js
sudo chmod 644 /app/dashboard/concierge/static/js/guest_dashboard_utils.js

# Restart the application
echo "🔄 Restarting application..."
sudo systemctl restart dashboard || sudo systemctl restart nginx || echo "No dashboard service found, trying nginx"

echo "✅ File installation complete!"
echo "📊 File details:"
ls -la /app/dashboard/concierge/static/js/guest_dashboard_utils.js
echo "📋 First 10 lines of the file:"
head -10 /app/dashboard/concierge/static/js/guest_dashboard_utils.js
