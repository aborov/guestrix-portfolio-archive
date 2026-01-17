# Cloud Infrastructure Guide

## Overview

The Guestrix project uses a hybrid cloud architecture leveraging both **AWS** and **Google Cloud Platform (GCP)** services. This document provides comprehensive information about the cloud services used, how to access them, and deployment procedures.

---

## Architecture Summary

### Primary Services by Provider

**Google Cloud Platform (GCP)** - Production Environment
- **Firestore**: Primary database for users, properties, knowledge sources, reservations, and magic links
- **Firebase Authentication**: Phone-based user authentication
- **Gemini API**: AI conversational agent and embeddings generation
- **Compute Engine**: Production Flask application hosting (e2-medium instance)
- **Domain**: `app.guestrix.ai`

**Amazon Web Services (AWS)** - Staging Environment & Supporting Services
- **EC2**: Staging Flask application hosting (t2.micro instance)
- **DynamoDB**: Conversation history and WebSocket connections only
- **Lambda**: Serverless functions (legacy, being phased out)
- **S3**: Static assets and deployment artifacts
- **Domain**: `dev.guestrix.ai`

---

## Google Cloud Platform (GCP)

### Project Information
- **Project ID**: `clean-art-454915-d9`
- **Project Name**: Guestrix Production
- **Region**: `us-central1`

### Services Used

#### 1. Firestore Database
**Purpose**: Primary database for all application data

**Collections**:
- `users` - User profiles and authentication data
- `properties` - Property information and configurations
- `knowledge_sources` - Knowledge base sources
- `knowledge_items` - Individual knowledge entries with vector embeddings
- `reservations` - Guest reservations
- `magic_links` - Temporary access links for guests
- `conversations` - Chat history (migrating from DynamoDB)
- `voice_sessions` - Voice call transcriptions and recordings

**Databases**:
- `(default)` - Production database
- `development` - Development/testing database

**Access via Web Portal**:
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select project: `clean-art-454915-d9`
3. Navigate to "Firestore Database" in the left sidebar
4. Browse collections or run queries

**Access via CLI**:
```bash
# Install gcloud CLI
# macOS: brew install google-cloud-sdk
# Linux: curl https://sdk.cloud.google.com | bash

# Initialize and authenticate
gcloud init
gcloud auth login
gcloud config set project clean-art-454915-d9

# Query Firestore (using firestore emulator or scripts)
gcloud firestore operations list
```

#### 2. Firebase Authentication
**Purpose**: Phone-based user authentication

**Access via Web Portal**:
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select project: `clean-art-454915-d9`
3. Navigate to "Authentication" in the left sidebar
4. View users, sign-in methods, and usage statistics

#### 3. Gemini API
**Purpose**: AI conversational agent, voice calls, text embeddings, and property data processing

**Models Used**:

**Voice Calls**:
- `gemini-live-2.5-flash-preview` - Real-time voice calls in guest dashboard (latest model)
- `gemini-2.0-flash-live-001` - Real-time voice calls in landing page and legacy features
- `gemini-2.5-flash` - Text chat fallback during voice calls

**Text Chat (Guest Dashboard)**:
- `gemini-2.5-flash-lite` - Main text chat model with function calling and Google Search
- `gemini-2.5-flash-lite` - RAG (Retrieval Augmented Generation) queries with knowledge base

**Property Management (Host Dashboard)**:
- `gemini-2.0-flash` - Airbnb property import and data extraction
- `gemini-2.0-flash` - Property validation and enhancement
- `gemini-2.0-flash-lite` - Property setup and configuration assistance

**Embeddings (All Features)**:
- `text-embedding-004` - Vector embeddings for knowledge base (768 dimensions)

**Legacy/Fallback Models**:
- `gemini-1.5-flash` - Fallback handler for voice calls
- `gemini-1.5-pro` - Used in some test scripts
- `gemini-2.0-flash-exp` - Experimental features (being phased out)

**Access via Web Portal**:
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. View API keys and usage

**Access via CLI**:
```bash
# List enabled APIs
gcloud services list --enabled | grep generative
```

#### 4. Compute Engine
**Purpose**: Production Flask application hosting

**Instance Details**:
- **Name**: `guestrix-web-dashboard`
- **Zone**: `us-central1-a`
- **Machine Type**: `e2-medium` (2 vCPU, 4GB RAM)
- **Status**: Running
- **External IP**: `35.209.244.249`

**Access via Web Portal**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to "Compute Engine" > "VM instances"
3. Select `guestrix-web-dashboard`

**Access via CLI**:
```bash
# Set project
gcloud config set project clean-art-454915-d9

# List instances
gcloud compute instances list

# SSH into instance
gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a

# View logs
gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a \
  --command="sudo journalctl -u dashboard.service -n 100"

# Check deployment status
./check_deployment.sh
```

### GCP CLI Setup

```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash
# Or on macOS: brew install google-cloud-sdk

# Initialize and authenticate
gcloud init
gcloud auth login

# Set project
gcloud config set project clean-art-454915-d9

# Verify configuration
gcloud config list
```

---

## Amazon Web Services (AWS)

### Account Information
- **Region**: `us-east-2` (Ohio)
- **Account ID**: `817634563684`

### Services Used

#### 1. EC2 (Elastic Compute Cloud)
**Purpose**: Staging Flask application hosting

**Instance Details**:
- **Name**: `guestrix-flask-dev`
- **Instance ID**: `i-0b9969c1b2c25b5b6`
- **Instance Type**: `t2.micro` (1 vCPU, 1GB RAM) - Free Tier eligible
- **AMI**: Ubuntu Server 22.04 LTS
- **Status**: Running
- **External IP**: `3.16.167.103`
- **Launch Date**: September 2, 2025

**Access via Web Portal**:
1. Go to [AWS Console](https://console.aws.amazon.com/)
2. Select region: `us-east-2`
3. Navigate to "EC2" > "Instances"
4. Select instance: `guestrix-flask-dev`

**Access via CLI**:
```bash
# List instances
aws ec2 describe-instances \
  --region us-east-2 \
  --filters "Name=tag:Name,Values=guestrix-flask-dev" \
  --output table

# SSH into instance (requires key pair)
ssh -i concierge/infra/guestrix-key-pair.pem ubuntu@3.16.167.103

# View instance details
aws ec2 describe-instances \
  --region us-east-2 \
  --instance-ids i-0b9969c1b2c25b5b6
```

**Security Groups**:
- Name: `guestrix-flask-sg`
- Inbound Rules:
  - Port 22 (SSH): 0.0.0.0/0
  - Port 80 (HTTP): 0.0.0.0/0
  - Port 443 (HTTPS): 0.0.0.0/0
  - Port 8080 (Application): 0.0.0.0/0

#### 2. DynamoDB
**Purpose**: Conversation history and WebSocket connections only

**Note**: The legacy `ConciergeTable` has been deprecated. All user, property, and knowledge data has been migrated to Firestore.

**Active Tables**:
- `Conversations` - Chat conversation history
- `InfraStack-WebSocketConnections8A9A9887-DQWO37VOKSUC` - Active WebSocket connections
- `InfraStack-connections` - Legacy WebSocket connections
- `WaitList` - Landing page waitlist (production)
- `WaitList-dev` - Landing page waitlist (development)
- `WaitList-prod` - Landing page waitlist (production)

**Access via Web Portal**:
1. Go to [AWS Console](https://console.aws.amazon.com/)
2. Navigate to "DynamoDB" > "Tables"
3. Select region: `us-east-2`
4. Browse tables

**Access via CLI**:
```bash
# List tables
aws dynamodb list-tables --region us-east-2

# Describe a table
aws dynamodb describe-table \
  --region us-east-2 \
  --table-name Conversations

# Query conversations
aws dynamodb scan \
  --region us-east-2 \
  --table-name Conversations \
  --max-items 10
```

#### 3. S3 (Simple Storage Service)
**Purpose**: Static assets, deployment artifacts, and CDK assets

**Buckets**:
- `guestrix-deployment` - Main deployment artifacts
- `guestrix-deployment-files` - Application files
- `cdk-hnb659fds-assets-817634563684-us-east-2` - CDK deployment assets
- `amplify-guestrix-*-deployment` - Amplify deployment buckets (multiple environments)

**Access via Web Portal**:
1. Go to [AWS Console](https://console.aws.amazon.com/)
2. Navigate to "S3"
3. Browse buckets

**Access via CLI**:
```bash
# List buckets
aws s3 ls --region us-east-2

# List bucket contents
aws s3 ls s3://guestrix-deployment/

# Copy files
aws s3 cp local-file.txt s3://guestrix-deployment/
```

#### 4. Lambda (Legacy - Being Phased Out)
**Purpose**: Serverless functions for knowledge ingestion (deprecated)

**Note**: Lambda functions are being phased out as we migrate to Firestore-based ingestion.

**Access via Web Portal**:
1. Go to [AWS Console](https://console.aws.amazon.com/)
2. Navigate to "Lambda" > "Functions"
3. Select region: `us-east-2`

**Access via CLI**:
```bash
# List functions
aws lambda list-functions --region us-east-2

# Invoke a function
aws lambda invoke \
  --region us-east-2 \
  --function-name your-function-name \
  --payload '{"key":"value"}' \
  response.json
```

### AWS CLI Setup

```bash
# Install AWS CLI
# macOS: brew install awscli
# Linux: pip install awscli
# Windows: Download installer from aws.amazon.com/cli

# Configure credentials
aws configure
# AWS Access Key ID: [Your Access Key]
# AWS Secret Access Key: [Your Secret Key]
# Default region name: us-east-2
# Default output format: json

# Verify configuration
aws sts get-caller-identity
aws ec2 describe-instances --region us-east-2
```

**Environment Variables** (alternative to `aws configure`):
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-2
```

---

## Deployment

### Production Deployment (GCP)

**Script**: `deploy_flask_app.sh`

**Target**: Google Cloud Compute Engine
- **Instance**: `guestrix-web-dashboard`
- **Domain**: `app.guestrix.ai`
- **Environment**: Production

**Deployment Steps**:
```bash
# Make script executable
chmod +x deploy_flask_app.sh

# Run deployment
./deploy_flask_app.sh
```

**What it does**:
1. Creates deployment package from `./concierge` directory
2. Transfers to GCP instance via `gcloud compute scp`
3. Installs dependencies (Python 3, Nginx, Firefox, Certbot)
4. Sets up Python virtual environment
5. Configures Gunicorn WSGI server (port 8080)
6. Configures Nginx reverse proxy with SSL
7. Obtains Let's Encrypt SSL certificate
8. Creates systemd service for auto-restart
9. Starts the application

**Monitoring**:
```bash
# Check deployment status
./check_deployment.sh

# View logs
gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a \
  --command="sudo tail -f /var/log/dashboard.log"

# Check service status
gcloud compute ssh guestrix-web-dashboard --zone=us-central1-a \
  --command="sudo systemctl status dashboard.service"
```

### Staging Deployment (AWS)

**Script**: `deploy_flask_app_aws.sh`

**Target**: AWS EC2
- **Instance**: `guestrix-flask-dev` (t2.micro)
- **Domain**: `dev.guestrix.ai`
- **Environment**: Staging

**Deployment Steps**:
```bash
# Ensure AWS CLI is configured
aws configure list

# Make script executable
chmod +x deploy_flask_app_aws.sh

# Run deployment
./deploy_flask_app_aws.sh
```

**What it does**:
1. Checks/creates security group with required ports
2. Launches or reuses existing t2.micro EC2 instance
3. Waits for SSH availability
4. Creates deployment package from `./concierge` directory
5. Transfers to EC2 instance via `scp`
6. Installs dependencies (Python 3, Nginx, Firefox, Certbot)
7. Sets up Python virtual environment
8. Configures Gunicorn WSGI server (port 8080)
9. Configures Nginx reverse proxy with SSL
10. Obtains Let's Encrypt SSL certificate
11. Creates systemd service for auto-restart
12. Starts the application

**Monitoring**:
```bash
# Check deployment status
./monitor_flask_app_aws.sh status

# View logs
./monitor_flask_app_aws.sh logs

# Check resources
./monitor_flask_app_aws.sh resources
```

### Deployment Comparison

| Aspect | Production (GCP) | Staging (AWS) |
|--------|-----------------|---------------|
| Script | `deploy_flask_app.sh` | `deploy_flask_app_aws.sh` |
| Platform | Google Compute Engine | AWS EC2 |
| Instance Type | e2-medium (2 vCPU, 4GB RAM) | t2.micro (1 vCPU, 1GB RAM) |
| Domain | app.guestrix.ai | dev.guestrix.ai |
| Environment Variable | `DEPLOYMENT_ENV=production` | `DEPLOYMENT_ENV=staging` |
| Database | Firestore (default) | Firestore (development) |
| SSL | Let's Encrypt (automatic) | Let's Encrypt (automatic) |
| Web Server | Nginx + Gunicorn | Nginx + Gunicorn |
| Workers | 1 worker, 2 threads | 1 worker, 2 threads |
| Timeout | 600s | 300s |

---

## Database Architecture

### Data Storage Strategy

**Firestore (Primary Database)**:
- Users and authentication
- Properties and configurations
- Knowledge sources and items (with vector embeddings)
- Reservations
- Magic links
- Voice sessions

**DynamoDB (Secondary - Conversations Only)**:
- Chat conversation history
- WebSocket connection tracking

### Migration Status

✅ **Completed**: Migration from DynamoDB `ConciergeTable` to Firestore
- All user data migrated
- All property data migrated
- All knowledge sources and items migrated
- All reservations migrated

🔄 **In Progress**: Conversation history migration
- Currently stored in DynamoDB `Conversations` table
- Will be migrated to Firestore

---

## Environment Variables

### Required for Both Environments

```bash
# Flask Configuration
FLASK_SECRET_KEY=your_secure_random_string
FLASK_ENV=production  # or development

# Google Cloud / Firebase
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
GOOGLE_CLOUD_PROJECT_ID=clean-art-454915-d9
FIREBASE_PROJECT_ID=clean-art-454915-d9

# Gemini API
GEMINI_API_KEY=your_gemini_api_key
GEMINI_ENABLED=True

# AWS (for DynamoDB conversations)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-2

# Deployment Environment
DEPLOYMENT_ENV=production  # or staging
```

### Environment-Specific Variables

**Production (GCP)**:
```bash
DEPLOYMENT_ENV=production
# Uses Firestore (default) database
```

**Staging (AWS)**:
```bash
DEPLOYMENT_ENV=staging
# Uses Firestore development database
```

---

## Cost Optimization

### Current Cost Drivers

**Google Cloud**:
- Compute Engine: ~$30-50/month (e2-medium instance)
- Firestore: ~$5-20/month (depends on reads/writes)
- Gemini API: Pay-per-use (varies by usage)

**AWS**:
- EC2 t2.micro: **Free Tier eligible** (first 12 months)
- DynamoDB: ~$5-10/month (on-demand pricing)
- S3: ~$1-5/month (storage and requests)

### Cost Optimization Tips

1. **EC2 Instance**: Stop when not in use
   ```bash
   aws ec2 stop-instances --region us-east-2 --instance-ids i-0b9969c1b2c25b5b6
   aws ec2 start-instances --region us-east-2 --instance-ids i-0b9969c1b2c25b5b6
   ```

2. **DynamoDB**: Use on-demand pricing for variable workloads

3. **S3**: Enable lifecycle policies to archive old files

4. **Firestore**: Optimize queries to reduce document reads

---

## Security

### Access Control

**Google Cloud**:
- IAM roles configured for service accounts
- Firestore security rules enforce access control
- Firebase Authentication manages user sessions

**AWS**:
- IAM policies for EC2, DynamoDB, S3, Lambda
- Security groups control network access
- SSH keys required for EC2 access

### Credentials Management

**SSH Keys**:
- GCP: Managed via `gcloud compute ssh` (automatic)
- AWS: `guestrix-key-pair.pem` stored in `concierge/infra/`

**Service Account Keys**:
- Stored in `concierge/credentials/` (gitignored)
- Referenced via `GOOGLE_APPLICATION_CREDENTIALS` environment variable

---

## Troubleshooting

### Common Issues

**1. Deployment fails with "Connection refused"**
```bash
# GCP: Check firewall rules
gcloud compute firewall-rules list

# AWS: Check security group
aws ec2 describe-security-groups --region us-east-2 \
  --group-names guestrix-flask-sg
```

**2. SSL certificate issues**
```bash
# Check certificate status
sudo certbot certificates

# Renew certificate
sudo certbot renew
```

**3. Application not responding**
```bash
# Check service status
sudo systemctl status dashboard.service

# View logs
sudo journalctl -u dashboard.service -n 100

# Restart service
sudo systemctl restart dashboard.service
```

**4. Database connection issues**
```bash
# Check Firestore credentials
echo $GOOGLE_APPLICATION_CREDENTIALS
cat $GOOGLE_APPLICATION_CREDENTIALS

# Test Firestore connection
python -c "from concierge.utils.firestore_client import get_firestore_client; print(get_firestore_client())"
```

---

## Additional Resources

### Documentation
- [AWS EC2 Documentation](https://docs.aws.amazon.com/ec2/)
- [Google Compute Engine Documentation](https://cloud.google.com/compute/docs)
- [Firebase Documentation](https://firebase.google.com/docs)
- [Firestore Documentation](https://firebase.google.com/docs/firestore)
- [Gemini API Documentation](https://ai.google.dev/docs)

### Monitoring Scripts
- `check_deployment.sh` - Check GCP deployment status
- `monitor_flask_app_aws.sh` - Monitor AWS deployment
- `check_property_conversations.py` - Check conversation data

### Support
For issues or questions, refer to the project README or contact the development team.

