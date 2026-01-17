#!/bin/bash

# Script to upload guest_dashboard_utils.js to EC2 instance
# Since SSH is not working, we'll use S3 as an intermediary

set -e

# Configuration
REGION="us-east-2"
INSTANCE_ID="i-0a89b31459f7620f1"
S3_BUCKET="guestrix-deployment-files"
FILE_TO_UPLOAD="concierge/static/js/guest_dashboard_utils.js"
REMOTE_PATH="/app/dashboard/concierge/static/js/guest_dashboard_utils.js"

echo "🚀 Starting file upload to EC2 instance..."

# Check if S3 bucket exists, create if not
echo "📦 Checking S3 bucket..."
if ! aws s3 ls "s3://$S3_BUCKET" --region $REGION &> /dev/null; then
    echo "Creating S3 bucket: $S3_BUCKET"
    aws s3 mb "s3://$S3_BUCKET" --region $REGION
else
    echo "S3 bucket exists: $S3_BUCKET"
fi

# Upload file to S3
echo "📤 Uploading file to S3..."
aws s3 cp "$FILE_TO_UPLOAD" "s3://$S3_BUCKET/guest_dashboard_utils.js" --region $REGION

# Create a script to download and install the file on the EC2 instance
echo "📝 Creating installation script..."
cat > install_file.sh << 'EOF'
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
EOF

# Upload the installation script to S3
aws s3 cp install_file.sh "s3://$S3_BUCKET/install_file.sh" --region $REGION

echo "✅ Files uploaded to S3"
echo "📋 Next steps:"
echo "1. Connect to your EC2 instance via AWS Console or another method"
echo "2. Run: aws s3 cp s3://guestrix-deployment-files/install_file.sh /tmp/install_file.sh"
echo "3. Run: chmod +x /tmp/install_file.sh"
echo "4. Run: sudo /tmp/install_file.sh"
echo ""
echo "🔗 Or use AWS Systems Manager if available:"
echo "aws ssm send-command --instance-ids $INSTANCE_ID --document-name 'AWS-RunShellScript' --parameters 'commands=[\"aws s3 cp s3://guestrix-deployment-files/install_file.sh /tmp/install_file.sh\",\"chmod +x /tmp/install_file.sh\",\"sudo /tmp/install_file.sh\"]' --region $REGION" 