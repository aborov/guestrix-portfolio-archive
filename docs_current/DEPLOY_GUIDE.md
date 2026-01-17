# Guestrix Flask App Deployment Guide

This guide explains how to deploy the Guestrix Flask application to the Google Cloud Compute Engine instance and how to update it in the future.

## Prerequisites

- Google Cloud SDK installed and configured
- Access to the Google Cloud project
- SSH access to the `guestrix-web-dashboard` VM instance
- Git repository cloned locally

## Deployment Process

### 1. Using the Deployment Script

The easiest way to deploy the application is to use the provided deployment script:

```bash
./deploy_flask_app.sh
```

This script will:
- Selectively copy only the Flask web dashboard components
- Package the application
- Transfer it to the server
- Install dependencies
- Configure Nginx and SSL
- Set up the systemd service
- Start the application

### 2. What Gets Deployed

The script selectively copies only the components needed for the Flask web dashboard:

- Main Flask application (`app.py`, `wsgi.py`, `requirements.txt`)
- Templates directory (HTML templates)
- Static files (JavaScript, CSS, images)
- API routes
- Authentication modules
- View controllers
- Utility functions
- Socket handlers

This ensures that AWS Lambda functions, EC2-specific components, and other unrelated files are not deployed to the Google Cloud instance.

### 3. Manual Deployment

If you need to make specific changes or troubleshoot issues, you can follow these manual steps:

#### 3.1. Prepare the Application

```bash
# Create a deployment package
mkdir -p deploy_tmp
rsync -av --exclude="*/.venv" --exclude="*/__pycache__" ./concierge/ deploy_tmp/concierge/

# Create necessary configuration files
# (See deploy_flask_app.sh for details)

# Package the application
tar -czf flask_app_deployment.tar.gz -C deploy_tmp .
```

#### 3.2. Transfer to Server

```bash
gcloud compute scp flask_app_deployment.tar.gz guestrix-web-dashboard:~/ --zone=us-central1-a
```

#### 3.3. Deploy on Server

```bash
# SSH into the server
gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a

# Extract the package
mkdir -p /tmp/flask_deploy
tar -xzf ~/flask_app_deployment.tar.gz -C /tmp/flask_deploy

# Copy to application directory
sudo mkdir -p /app/dashboard
sudo cp -r /tmp/flask_deploy/* /app/dashboard/
sudo chown -R ubuntu:ubuntu /app/dashboard

# Install dependencies
cd /app/dashboard
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn

# Install specific version of google-cloud-firestore
pip install google-cloud-firestore==2.20.2

# Fix Vector import if needed
sudo sed -i 's/from google.cloud.firestore_v1.vector import Vector/from google.cloud.firestore_v1 import vector\\n# Vector class is now accessed as vector.Vector/g' /app/dashboard/concierge/utils/firestore_client.py
sudo sed -i 's/\([^\.]\)Vector(/\1vector.Vector(/g' /app/dashboard/concierge/utils/firestore_client.py

# Set up Nginx and systemd
# (See deploy_flask_app.sh for details)
```

## Making Updates

When you want to update the application with new features or fixes:

1. Make your changes to the codebase locally
2. Test the changes to ensure they work as expected
3. Run the deployment script to update the application:

```bash
./deploy_flask_app.sh
```

The script automatically:
- Creates a backup of the current application on the server
- Deploys the updated code
- Restarts the services to apply the changes

## Rollback Process

If something goes wrong after deployment, you can rollback to a previous version:

1. SSH into the server:
   ```bash
   gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a
   ```

2. List the available backups:
   ```bash
   ls -la /app/dashboard_backup_*
   ```

3. Restore from a backup:
   ```bash
   sudo systemctl stop dashboard
   sudo rm -rf /app/dashboard
   sudo cp -r /app/dashboard_backup_YYYYMMDD_HHMMSS /app/dashboard
   sudo chown -R ubuntu:ubuntu /app/dashboard
   sudo systemctl start dashboard
   ```

## Troubleshooting

### Common Issues

1. **Import Error with Vector Class**

   If you see an error like:
   ```
   ModuleNotFoundError: No module named 'google.cloud.firestore_v1.vector'
   ```

   Fix:
   ```bash
   # SSH into the server
   gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a
   
   # Fix the import
   sudo sed -i 's/from google.cloud.firestore_v1.vector import Vector/from google.cloud.firestore_v1 import vector\\n# Vector class is now accessed as vector.Vector/g' /app/dashboard/concierge/utils/firestore_client.py
   sudo sed -i 's/\([^\.]\)Vector(/\1vector.Vector(/g' /app/dashboard/concierge/utils/firestore_client.py
   
   # Restart the service
   sudo systemctl restart dashboard.service
   ```

2. **Worker Timeout Issues**

   If you see worker timeout errors in the logs:
   ```
   WORKER TIMEOUT (pid:XXXX)
   ```

   Fix:
   ```bash
   # SSH into the server
   gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a
   
   # Change worker class from eventlet to sync
   sudo sed -i 's/worker_class = "eventlet"/worker_class = "sync"/' /app/dashboard/gunicorn.conf.py
   
   # Restart the service
   sudo systemctl restart dashboard.service
   ```

3. **Nginx 502 Bad Gateway**

   Check Nginx error logs:
   ```bash
   sudo tail -n 50 /var/log/nginx/error.log
   ```

   Verify the application is running:
   ```bash
   sudo systemctl status dashboard.service
   sudo ss -tulpn | grep 8080
   ```

## Monitoring

### Checking Logs

```bash
# Application error logs
sudo tail -f /app/dashboard/error.log

# Application access logs
sudo tail -f /app/dashboard/access.log

# System service logs
sudo journalctl -u dashboard.service -f

# Nginx error logs
sudo tail -f /var/log/nginx/error.log

# Nginx access logs
sudo tail -f /var/log/nginx/access.log
```

### Checking Service Status

```bash
sudo systemctl status dashboard.service
```

## Restarting the Application

```bash
sudo systemctl restart dashboard.service
```

## SSL Certificate Renewal

SSL certificates are automatically renewed by Certbot. If you need to manually renew:

```bash
sudo certbot renew
```

## Customizing the Deployment

If you need to customize the deployment process:

1. Edit the `deploy_flask_app.sh` script to modify:
   - Environment variables
   - Server configuration
   - Deployment steps
   - Which files and directories are included

2. For major changes to the application structure, update:
   - The systemd service file
   - The Nginx configuration
   - The gunicorn configuration
