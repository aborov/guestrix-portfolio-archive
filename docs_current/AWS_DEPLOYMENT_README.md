# AWS EC2 Flask App Deployment Guide

This guide explains how to deploy the Guestrix Flask application to AWS EC2 with the `dev.guestrix.ai` subdomain for testing purposes.

## Overview

This deployment creates a production-like environment on AWS EC2 that mirrors the Google Cloud setup but uses the `dev.guestrix.ai` subdomain for testing before deploying to production.

### Architecture
- **AWS EC2 t2.micro instance** (Free Tier eligible)
- **Amazon Linux 2** operating system
- **Nginx** as reverse proxy
- **Gunicorn** as WSGI server
- **Let's Encrypt** for SSL certificates
- **systemd** for service management

## Prerequisites

1. **AWS CLI configured** with appropriate credentials
2. **SSH key pair** (`guestrix-key-pair`) exists in AWS
3. **Domain access** to manage `guestrix.ai` DNS records
4. **Required tools**: `jq`, `dig`, `curl`

## Quick Start

### 1. Deploy the Application

```bash
# Make the script executable (if not already)
chmod +x deploy_flask_app_aws.sh

# Run the deployment
./deploy_flask_app_aws.sh
```

This script will:
- Create a new EC2 t2.micro instance
- Set up security groups
- Install and configure all dependencies
- Deploy the Flask application
- Configure Nginx and SSL
- Start all services

### 2. Update DNS Records

```bash
# Check current DNS status
./update_dns_aws.sh status

# Update DNS to point to the new instance
./update_dns_aws.sh update
```

### 3. Monitor the Deployment

```bash
# Check overall status
./monitor_flask_app_aws.sh status

# View application logs
./monitor_flask_app_aws.sh logs

# Check system resources
./monitor_flask_app_aws.sh resources
```

## Detailed Usage

### Deployment Script (`deploy_flask_app_aws.sh`)

The deployment script performs the following steps:

1. **Validates prerequisites** (AWS CLI, key pair)
2. **Creates/updates security group** with required ports (22, 80, 443, 8080)
3. **Launches EC2 instance** with Amazon Linux 2
4. **Waits for instance** to be ready and SSH accessible
5. **Packages application** (excluding unnecessary files)
6. **Transfers files** to the instance
7. **Runs remote setup** script that:
   - Updates system packages
   - Installs Python, Nginx, Certbot
   - Sets up virtual environment
   - Installs Python dependencies
   - Configures Nginx with SSL
   - Sets up systemd service
   - Starts all services

### Monitoring Script (`monitor_flask_app_aws.sh`)

Available commands:

```bash
# Check instance and service status (default)
./monitor_flask_app_aws.sh status

# View application logs
./monitor_flask_app_aws.sh logs [recent|full|errors]

# Check system resources (CPU, memory, disk)
./monitor_flask_app_aws.sh resources

# Restart application services
./monitor_flask_app_aws.sh restart

# SSH into the instance
./monitor_flask_app_aws.sh ssh
```

### DNS Management Script (`update_dns_aws.sh`)

Available commands:

```bash
# Show current DNS status
./update_dns_aws.sh status

# Update DNS to point to current instance
./update_dns_aws.sh update

# Delete DNS record
./update_dns_aws.sh delete
```

## Configuration Details

### Security Group Rules
- **Port 22**: SSH access from anywhere
- **Port 80**: HTTP access (redirects to HTTPS)
- **Port 443**: HTTPS access
- **Port 8080**: Direct access to Gunicorn (for debugging)

### Application Structure
```
/app/dashboard/
├── concierge/           # Flask application code
├── wsgi.py             # Gunicorn WSGI entry point
├── gunicorn.conf.py    # Gunicorn configuration
├── dashboard.service   # systemd service file
├── dashboard.nginx     # Nginx configuration
└── requirements.txt    # Python dependencies
```

### Service Configuration
- **systemd service**: `dashboard.service`
- **Nginx config**: `/etc/nginx/conf.d/dashboard.conf`
- **SSL certificates**: Let's Encrypt via Certbot
- **Logs**: 
  - Application: `journalctl -u dashboard`
  - Nginx: `/var/log/nginx/`
  - Gunicorn: `/var/log/dashboard.*.log`

## Troubleshooting

### Common Issues

1. **SSH Connection Timeout**
   ```bash
   # Check instance status
   aws ec2 describe-instances --region us-east-2 --instance-ids <instance-id>
   
   # Check security group rules
   ./monitor_flask_app_aws.sh status
   ```

2. **Application Not Starting**
   ```bash
   # Check service logs
   ./monitor_flask_app_aws.sh logs errors
   
   # SSH into instance and check manually
   ./monitor_flask_app_aws.sh ssh
   sudo systemctl status dashboard
   ```

3. **SSL Certificate Issues**
   ```bash
   # SSH into instance
   ./monitor_flask_app_aws.sh ssh
   
   # Check certbot status
   sudo certbot certificates
   
   # Renew certificates if needed
   sudo certbot renew --dry-run
   ```

4. **DNS Not Resolving**
   ```bash
   # Check DNS status
   ./update_dns_aws.sh status
   
   # Update DNS if needed
   ./update_dns_aws.sh update
   
   # Test DNS resolution
   dig dev.guestrix.ai
   ```

### Manual Commands

If you need to perform manual operations:

```bash
# SSH into the instance
ssh -i "concierge/infra/guestrix-key-pair.pem" ec2-user@<instance-dns>

# Check service status
sudo systemctl status dashboard nginx

# View logs
sudo journalctl -u dashboard -f
sudo tail -f /var/log/nginx/error.log

# Restart services
sudo systemctl restart dashboard nginx

# Check application files
ls -la /app/dashboard/
```

## Cost Considerations

- **EC2 t2.micro**: Free Tier eligible (750 hours/month)
- **EBS storage**: 30GB Free Tier
- **Data transfer**: 1GB Free Tier outbound
- **Route 53**: $0.50/month per hosted zone (already exists)

## Cleanup

To remove the deployment:

```bash
# Get instance ID
aws ec2 describe-instances --region us-east-2 \
  --filters "Name=tag:Name,Values=guestrix-flask-dev" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text

# Terminate instance
aws ec2 terminate-instances --region us-east-2 --instance-ids <instance-id>

# Delete DNS record
./update_dns_aws.sh delete

# Delete security group (optional)
aws ec2 delete-security-group --region us-east-2 --group-name guestrix-flask-sg
```

## Next Steps

After successful deployment:

1. **Test the application** at `https://dev.guestrix.ai`
2. **Verify all features** work as expected
3. **Monitor performance** and resource usage
4. **Update production** deployment if tests pass
5. **Set up monitoring** and alerting if needed

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review application logs using the monitoring script
3. Verify AWS resources in the AWS Console
4. Check DNS configuration in Route 53
