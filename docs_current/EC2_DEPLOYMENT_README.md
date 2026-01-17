# EC2 Deployment Guide

This guide explains how to deploy both the Flask web app and WebSocket server on the same EC2 t2.micro instance.

## Overview

The deployment process involves:
1. Installing Nginx as a reverse proxy
2. Deploying the Flask app to the EC2 instance
3. Updating the WebSocket server configuration
4. Monitoring resource usage

## Prerequisites

- AWS EC2 t2.micro instance running Ubuntu
- SSH access to the EC2 instance
- The SSH key file (guestrix-key-pair.pem) located in the concierge/infra directory
- The WebSocket server already deployed on the EC2 instance

## Deployment Steps

### 1. Update EC2 Instance Details

The EC2 instance details are already configured in the scripts:
- EC2_HOST: ec2-3-148-215-6.us-east-2.compute.amazonaws.com
- KEY_FILE: concierge/infra/guestrix-key-pair.pem
- REMOTE_USER: ubuntu

### 2. Run the Deployment Script

```bash
# Make the script executable
chmod +x deploy_all.sh

# Run the deployment script
./deploy_all.sh
```

This script will:
- Install Nginx on the EC2 instance
- Deploy the Flask app
- Update the WebSocket server configuration
- Monitor resource usage

### 3. Update Telnyx Webhook Configuration

After deployment, update your Telnyx webhook configuration as described in `update_telnyx_webhook.md`.

### 4. Monitor Resource Usage

Regularly monitor the resource usage of your EC2 instance:

```bash
./monitor_ec2.sh
```

## File Structure

- `deploy_all.sh`: Main deployment script
- `install_nginx.sh`: Script to install Nginx
- `deploy_flask_app.sh`: Script to deploy the Flask app
- `update_websocket_config.sh`: Script to update the WebSocket server configuration
- `monitor_ec2.sh`: Script to monitor resource usage
- `guestrix_nginx.conf`: Nginx configuration file
- `update_telnyx_webhook.md`: Instructions for updating Telnyx webhook configuration

## Troubleshooting

### Nginx Configuration Issues

If Nginx fails to start or has configuration issues:

```bash
ssh -i "concierge/infra/guestrix-key-pair.pem" ubuntu@ec2-3-148-215-6.us-east-2.compute.amazonaws.com
sudo nginx -t
sudo systemctl status nginx
```

### Flask App Issues

If the Flask app fails to start:

```bash
ssh -i "concierge/infra/guestrix-key-pair.pem" ubuntu@ec2-3-148-215-6.us-east-2.compute.amazonaws.com
sudo systemctl status guestrix-flask
sudo tail -n 100 /var/log/guestrix-flask.log
```

### WebSocket Server Issues

If the WebSocket server has issues:

```bash
ssh -i "concierge/infra/guestrix-key-pair.pem" ubuntu@ec2-3-148-215-6.us-east-2.compute.amazonaws.com
sudo systemctl status websocket-server
sudo tail -n 100 /var/log/websocket-server.log
```

### Quick SSH Access

For quick SSH access to the EC2 instance:

```bash
ssh -i "concierge/infra/guestrix-key-pair.pem" ubuntu@ec2-3-148-215-6.us-east-2.compute.amazonaws.com
```

## Resource Optimization

To optimize resource usage on the t2.micro instance:

1. Reduce Gunicorn workers and threads if needed
2. Monitor memory usage and adjust as necessary
3. Consider setting up swap space if memory becomes an issue
4. Use application-level caching where possible

## Domain Configuration

To configure your domain (app.guestrix.ai) to point to your EC2 instance:

1. Get the public IP address of your EC2 instance
2. Update your DNS records to point to this IP address
3. If using HTTPS, set up SSL certificates using Let's Encrypt
