from aws_cdk import (
    Stack,
    aws_lambda as _lambda, # Keep this alias
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_s3 as s3,
    aws_s3_assets as s3_assets,
    aws_iam as iam,
    RemovalPolicy,
    Duration,
    BundlingOptions,
    CfnOutput,
    aws_ecr_assets as ecr_assets,
    aws_dynamodb as dynamodb,
    aws_logs as logs, # Import logs module
    aws_elasticbeanstalk as elasticbeanstalk,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_certificatemanager as acm,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecs_patterns as ecs_patterns
)
from constructs import Construct
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file in the parent directory
dotenv_path = os.path.join(os.path.dirname(__file__), '../../.env')
load_dotenv(dotenv_path=dotenv_path)

# Load .env file for CDK deployment environment
load_dotenv()

# --- Import defaults from the script if needed (optional, could hardcode or rely on env vars) ---
# This assumes ingest_knowledge.py is accessible relative to this infra script
# Adjust path if necessary, or simply rely on environment variables in Lambda
# try:
#     sys.path.append(os.path.join(os.path.dirname(__file__), '../../scripts'))
#     from ingest_knowledge import DEFAULT_TABLE_NAME, DEFAULT_MODEL
# except ImportError:
#     print("Warning: Could not import defaults from ingest_knowledge.py. Using hardcoded/env var values.")
DEFAULT_TABLE_NAME = 'knowledge_base' # Fallback if import fails or is omitted
DEFAULT_MODEL = 'all-MiniLM-L6-v2'   # Fallback if import fails or is omitted
# ---------------------------------------------------------------------------------------------

class InfraStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Retrieve environment variables
        telnyx_api_key = os.getenv('TELNYX_API_KEY')
        if not telnyx_api_key:
            raise ValueError("TELNYX_API_KEY environment variable not set")

        gemini_api_key = os.getenv('GEMINI_API_KEY')
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        websocket_url = os.getenv('WEBSOCKET_URL')
        if not websocket_url:
            raise ValueError("WEBSOCKET_URL environment variable not set")

        # --- DynamoDB Table for WebSocket Connections ---
        connections_table = dynamodb.Table(
            self, "ConnectionsTable",
            table_name=f"{self.stack_name}-connections",
            partition_key=dynamodb.Attribute(name="connectionId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY # Automatically remove table on stack deletion (for dev)
        )

        # --- Define Docker Image Asset Code (Separate for each handler) ---
        # Define Docker Image Asset Code for Consolidated Call Handler
        consolidated_call_handler_code = _lambda.DockerImageCode.from_image_asset(
            directory=os.path.join(os.path.dirname(__file__), "../../"), # Path to project root
            file="lambda_src/Dockerfile", # Path to Dockerfile relative to directory
            # Specify the command (handler) for this specific asset
            cmd=["consolidated_call_handler.lambda_handler"],
            platform=ecr_assets.Platform.LINUX_AMD64 # Match other Docker Lambdas
        )

        # Keep the original code for backward compatibility
        telnyx_image_code = _lambda.DockerImageCode.from_image_asset(
            directory=os.path.join(os.path.dirname(__file__), "../../"), # Reverted path
            file="lambda_src/Dockerfile", # Reverted path
            # Specify the command (handler) for this specific asset
            cmd=["voice_lambda_function.lambda_handler"],
            platform=ecr_assets.Platform.LINUX_AMD64 # <<< USE STATIC MEMBER
        )

        # --- Telnyx Webhook Lambda (Docker) ---
        telnyx_webhook_handler = _lambda.DockerImageFunction(
            self,
            "TelnyxPhoneCallHandler",  # Renamed to be more explicit
            code=telnyx_image_code, # Use the specific code asset
            architecture=_lambda.Architecture.X86_64,
            # Handler is now defined within the code asset
            timeout=Duration.seconds(30), # Adjust as needed
            memory_size=1024, # Increase memory if needed for larger libraries
            environment={
                'TELNYX_API_KEY': telnyx_api_key,
                'GEMINI_API_KEY': gemini_api_key, # Pass Gemini key
                'WEBSOCKET_URL': websocket_url,
                'TELNYX_SMS_NUMBER': os.getenv('TELNYX_SMS_NUMBER'),
                # Using Firestore for main data operations
            }
            # Note: No layers or bundling needed anymore
        )

        # --- Consolidated Call Handler Lambda (Docker) ---
        consolidated_call_handler_lambda = _lambda.DockerImageFunction(
            self,
            "ConsolidatedCallHandler",
            code=consolidated_call_handler_code,
            architecture=_lambda.Architecture.X86_64,
            timeout=Duration.seconds(30),
            memory_size=1024,
            environment={
                'TELNYX_API_KEY': telnyx_api_key,
                'GEMINI_API_KEY': gemini_api_key,
                'WEBSOCKET_URL': websocket_url,
                'TELNYX_SMS_NUMBER': os.getenv('TELNYX_SMS_NUMBER'),
                # Using Firestore for main data operations
                'CONNECTIONS_TABLE_NAME': connections_table.table_name
            },
            log_group=logs.LogGroup(
                self,
                "ConsolidatedCallHandlerLogGroup",
                log_group_name=f"/aws/lambda/{self.stack_name}-ConsolidatedCallHandler",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY
            )
        )

        # Grant permissions to the consolidated Lambda
        connections_table.grant_read_write_data(consolidated_call_handler_lambda)

        # Grant permission to manage API Gateway connections
        consolidated_call_handler_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["execute-api:ManageConnections"],
            resources=[f"arn:aws:execute-api:{self.region}:{self.account}:*/*/*/@connections/*"]
        ))

        # === WebSocket API Integrations (Defined *before* API Gateway) ===
        # Define Docker Image Asset Code for WebSocket Handler
        websocket_image_code = _lambda.DockerImageCode.from_image_asset(
            directory=os.path.join(os.path.dirname(__file__), "../../"), # Path to project root
            file="lambda_src/Dockerfile", # Path to Dockerfile relative to directory
            # Specify the command (handler) for this specific asset
            cmd=["websocket_lambda_function.lambda_handler"], # Corrected handler path
            platform=ecr_assets.Platform.LINUX_AMD64 # Match other Docker Lambdas
        )

        websocket_handler_lambda = _lambda.DockerImageFunction( # Changed from _lambda.Function
            self,
            "WebSocketHandler",
            code=websocket_image_code, # Use the Docker image code
            architecture=_lambda.Architecture.X86_64, # Specify architecture
            # Remove runtime, handler, and code/bundling - managed by Docker image
            environment={
                "CONNECTIONS_TABLE_NAME": connections_table.table_name,
                "GEMINI_API_KEY": gemini_api_key,
                # Using Firestore for main data operations
                # WEBSOCKET_API_URL will be added later
            },
            log_group=logs.LogGroup(
                self,
                "WebSocketHandlerLogGroup",
                log_group_name=f"/aws/lambda/{self.stack_name}-WebSocketHandler",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY
            ),
            memory_size=512, # Keep memory/timeout settings
            timeout=Duration.seconds(30)
        )

        # Grant WebSocket Lambda permissions to write to DynamoDB
        connections_table.grant_read_write_data(websocket_handler_lambda)

        # Grant WebSocket Lambda permission to manage API Gateway connections
        websocket_handler_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["execute-api:ManageConnections"],
            resources=[f"arn:aws:execute-api:{self.region}:{self.account}:*/*/*/@connections/*"]
        ))

        # Grant WebSocket Lambda permission to manage API Gateway connections
        websocket_handler_lambda.add_permission(
            "ApiGatewayInvokePermission",
            principal=iam.ServicePrincipal("apigateway.amazonaws.com"),
            # Restrict source ARN to the specific API Gateway API for better security
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:*/*/*/*"
        )

        # Use the consolidated handler for WebSocket integrations
        connect_integration = apigw_integrations.WebSocketLambdaIntegration("ConnectIntegration", consolidated_call_handler_lambda)
        disconnect_integration = apigw_integrations.WebSocketLambdaIntegration("DisconnectIntegration", consolidated_call_handler_lambda)
        default_integration = apigw_integrations.WebSocketLambdaIntegration("DefaultIntegration", consolidated_call_handler_lambda)

        # === API Gateway WebSocket API ===
        websocket_api = apigwv2.WebSocketApi(
            self,
            "ConciergeWebSocketApi",
            # Reference pre-defined integrations
            connect_route_options=apigwv2.WebSocketRouteOptions(integration=connect_integration),
            disconnect_route_options=apigwv2.WebSocketRouteOptions(integration=disconnect_integration),
            default_route_options=apigwv2.WebSocketRouteOptions(integration=default_integration),
        )

        # Define a log group for WebSocket API logs
        websocket_log_group = logs.LogGroup(
            self,
            "WebSocketApiLogs",
            retention=logs.RetentionDays.TWO_YEARS, # Optional: Adjust retention
            removal_policy=RemovalPolicy.DESTROY # Optional: Adjust removal policy
        )

        # Create the WebSocket Stage
        dev_stage = apigwv2.WebSocketStage(
            self,
            "DevStage",
            web_socket_api=websocket_api,
            stage_name="dev",
            auto_deploy=True,
        )

        # --- Update Lambda environment with correct WebSocket API URL ---
        websocket_api_stage_url = f"{websocket_api.api_endpoint}/{dev_stage.stage_name}"
        # Note: The /dev is required in the URL for WebSocket connections
        websocket_handler_lambda.add_environment("WEBSOCKET_API_URL", websocket_api_stage_url)

        # Also update the consolidated Lambda with the WebSocket API URL
        consolidated_call_handler_lambda.add_environment("WEBSOCKET_API_URL", websocket_api_stage_url)

        # Also make the URL available as a CfnOutput
        CfnOutput(
            self,
            "WebSocketApiFullUrl",
            value=websocket_api_stage_url,
            description="The complete URL of the WebSocket API including stage"
        )

        # Ensure the stage deployment happens after the log group is created
        dev_stage.node.add_dependency(websocket_log_group)

        # --- Configure Logging via L1 CfnStage properties ---
        # Get the underlying CfnStage L1 construct
        cfn_stage = dev_stage.node.default_child
        if isinstance(cfn_stage, apigwv2.CfnStage):
            cfn_stage.access_log_settings = apigwv2.CfnStage.AccessLogSettingsProperty(
                destination_arn=websocket_log_group.log_group_arn,
                format=json.dumps({
                    # Standard fields + custom fields
                    "requestId": "$context.requestId",
                    "ip": "$context.identity.sourceIp",
                    "caller": "$context.identity.caller",
                    "user": "$context.identity.user",
                    "requestTime": "$context.requestTime",
                    "httpMethod": "$context.httpMethod",
                    "resourcePath": "$context.resourcePath",
                    "status": "$context.status",
                    "protocol": "$context.protocol",
                    "responseLength": "$context.responseLength",
                    "routeKey": "$context.routeKey",
                    "eventType": "$context.eventType",
                    "connectionId": "$context.connectionId",
                    "error": "$context.error.message",
                    "integrationError": "$context.integration.error",
                    "integrationStatus": "$context.integration.status"
                })
            )
            cfn_stage.default_route_settings = apigwv2.CfnStage.RouteSettingsProperty(
                logging_level="INFO",  # Execution log level
                data_trace_enabled=True # Execution log data tracing
            )
        # --- End L1 Logging Configuration ---

        # Output the WebSocket API endpoint URL
        CfnOutput(
            self,
            "WebSocketApiUrl",
            value=websocket_api.api_endpoint,
            description="The URL of the WebSocket API"
        )

        # --- API Gateway for Telnyx Phone Call Webhooks ---
        # Define the HTTP API Gateway using the consolidated handler
        http_api = apigwv2.HttpApi(
            self,
            "TelnyxPhoneCallApi",
            description="HTTP API to receive Telnyx Phone Call Webhooks",
            default_integration=apigw_integrations.HttpLambdaIntegration(
                "TelnyxPhoneCallIntegration",
                consolidated_call_handler_lambda
            )
        )

        # Output the API endpoint URL after deployment
        CfnOutput(
            self,
            "TelnyxPhoneCallApiUrl",
            value=http_api.url,
            description="The URL of the Telnyx Phone Call API Gateway endpoint"
        )

        # --- Add Consolidated Call Handler Lambda ARN Output ---
        CfnOutput(
            self,
            "ConsolidatedCallHandlerArn",
            value=consolidated_call_handler_lambda.function_arn,
            description="ARN of the Consolidated Call Handler Lambda function"
        )
        # --- End Consolidated Call Handler Lambda ARN Output ---

        # === EC2 Instance for Flask App ===
        # Create a VPC for the EC2 instance
        vpc = ec2.Vpc(
            self,
            "GuestrixVpc",
            max_azs=2,  # Use 2 Availability Zones for high availability
            nat_gateways=0  # No NAT Gateways to reduce costs (we'll use public subnets)
        )

        # Create a security group for the EC2 instance
        security_group = ec2.SecurityGroup(
            self,
            "GuestrixSecurityGroup",
            vpc=vpc,
            description="Security group for Guestrix Flask app",
            allow_all_outbound=True
        )

        # Allow HTTP and HTTPS traffic
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow HTTP traffic"
        )
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            "Allow HTTPS traffic"
        )
        # Allow SSH for management (optional, can be removed for production)
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(22),
            "Allow SSH traffic"
        )

        # Create a role for the EC2 instance
        instance_role = iam.Role(
            self,
            "GuestrixInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ]
        )

        # Create user data script to set up the EC2 instance
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "#!/bin/bash",
            "exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1",
            "echo 'Starting user data script execution'",

            # Update and install dependencies
            "apt-get update -y",
            "apt-get install -y git python3-pip python3-venv python3-dev build-essential nginx certbot python3-certbot-nginx",

            # Clone the repository
            "echo 'Cloning repository'",
            "mkdir -p /app",
            "cd /app",
            "git clone https://github.com/aborov/concierge.git .",

            # Set up Python environment
            "echo 'Setting up Python environment'",
            "python3 -m venv venv",
            "source venv/bin/activate",
            "pip install --upgrade pip",
            "pip install -r requirements.txt",
            "pip install gunicorn",

            # Create environment file
            "echo 'Creating environment file'",
            "cat > /app/.env << 'EOL'",
            f"GEMINI_API_KEY={gemini_api_key}",
            "# Using Firestore for main data operations",
            f"WEBSOCKET_API_URL={websocket_api_stage_url}",
            "FLASK_ENV=production",
            f"TELNYX_API_KEY={telnyx_api_key}",
            f"AWS_DEFAULT_REGION={self.region}",
            "FLASK_SECRET_KEY=a_secure_secret_key_for_production",
            "EOL",

            # Set up AWS credentials
            "echo 'Setting up AWS credentials'",
            "mkdir -p /root/.aws",
            "cat > /root/.aws/credentials << 'EOL'",
            "[default]",
            f"region = {self.region}",
            "EOL",

            # Set up Nginx
            "echo 'Setting up Nginx'",
            "cat > /etc/nginx/sites-available/guestrix << 'EOL'",
            "server {",
            "    listen 80;",
            "    server_name app.guestrix.ai;",
            "",
            "    location / {",
            "        proxy_pass http://localhost:8080;",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;",
            "        proxy_set_header Upgrade $http_upgrade;",
            "        proxy_set_header Connection \"upgrade\";",
            "        proxy_read_timeout 300s;",
            "        proxy_connect_timeout 75s;",
            "    }",
            "}",
            "EOL",

            # Enable the Nginx site
            "ln -s /etc/nginx/sites-available/guestrix /etc/nginx/sites-enabled/",
            "rm -f /etc/nginx/sites-enabled/default",
            "systemctl restart nginx",

            # Set up SSL with Certbot (will be run after DNS is configured)
            "echo 'Creating SSL setup script'",
            "echo '#!/bin/bash' > /app/setup_ssl.sh",
            "echo 'certbot --nginx -d app.guestrix.ai --non-interactive --agree-tos --email admin@guestrix.ai' >> /app/setup_ssl.sh",
            "chmod +x /app/setup_ssl.sh",

            # Create a simple health check endpoint
            "echo 'Creating health check endpoint'",
            "mkdir -p /app/concierge/templates",
            "cat > /app/concierge/templates/health.html << 'EOL'",
            "<html><body><h1>Guestrix App is Running</h1></body></html>",
            "EOL",

            # Create systemd service for the Flask app
            "echo 'Creating systemd service'",
            "cat > /etc/systemd/system/guestrix.service << 'EOL'",
            "[Unit]",
            "Description=Guestrix Flask Application",
            "After=network.target",
            "",
            "[Service]",
            "User=root",
            "WorkingDirectory=/app",
            "Environment=PATH=/app/venv/bin",
            "ExecStart=/app/venv/bin/gunicorn --workers=2 --threads=4 --bind=0.0.0.0:8080 --timeout=120 app:application",
            "Restart=always",
            "StandardOutput=append:/var/log/guestrix.log",
            "StandardError=append:/var/log/guestrix.error.log",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "EOL",

            # Create directories for WebSocket server
            "echo 'Setting up WebSocket server'",
            "mkdir -p /app/websocket_server",
            "mkdir -p /app/utils",

            # Copy WebSocket server files from assets
            "cp -r /app/assets/websocket_server/* /app/websocket_server/",
            "cp -r /app/assets/utils/* /app/utils/",

            # Install opuslib for audio encoding
            "echo 'Installing opuslib for audio encoding'",
            "apt-get install -y libopus-dev",
            "source /app/venv/bin/activate",
            "pip install opuslib",

            # Create systemd service for WebSocket server
            "echo 'Creating WebSocket server systemd service'",
            "cp /app/assets/websocket-server.service /etc/systemd/system/",
            "touch /var/log/websocket-server.log /var/log/websocket-server.error.log",
            "chmod 644 /var/log/websocket-server.log /var/log/websocket-server.error.log",

            # Start and enable the services
            "echo 'Starting Flask application'",
            "touch /var/log/guestrix.log /var/log/guestrix.error.log",
            "chmod 644 /var/log/guestrix.log /var/log/guestrix.error.log",
            "systemctl daemon-reload",
            "systemctl start guestrix",
            "systemctl enable guestrix",

            # Start and enable the WebSocket server
            "echo 'Starting WebSocket server'",
            "systemctl start websocket-server",
            "systemctl enable websocket-server",

            # Run SSL setup after a delay to ensure DNS propagation
            "echo 'Scheduling SSL setup'",
            "(sleep 300 && /app/setup_ssl.sh >> /var/log/ssl-setup.log 2>&1) &",

            # Add a simple test script to verify the app is running
            "echo 'Creating test script'",
            "cat > /app/test_app.sh << 'EOL'",
            "#!/bin/bash",
            "echo 'Testing Flask app...'",
            "curl -v http://localhost:8080/health",
            "echo 'Testing Nginx...'",
            "curl -v http://localhost/health",
            "echo 'Flask service status:'",
            "systemctl status guestrix",
            "echo 'WebSocket server status:'",
            "systemctl status websocket-server",
            "echo 'Nginx status:'",
            "systemctl status nginx",
            "echo 'Flask logs:'",
            "tail -n 50 /var/log/guestrix.log",
            "echo 'Flask error logs:'",
            "tail -n 50 /var/log/guestrix.error.log",
            "echo 'WebSocket server logs:'",
            "tail -n 50 /var/log/websocket-server.log",
            "echo 'WebSocket server error logs:'",
            "tail -n 50 /var/log/websocket-server.error.log",
            "EOL",
            "chmod +x /app/test_app.sh",

            # Final message
            "echo 'User data script completed'"
        )

        # Create assets for the WebSocket server
        websocket_server_asset = s3_assets.Asset(
            self,
            "WebSocketServerAsset",
            path=os.path.join(os.path.dirname(__file__), "../assets/websocket_server")
        )

        utils_asset = s3_assets.Asset(
            self,
            "UtilsAsset",
            path=os.path.join(os.path.dirname(__file__), "../assets/utils")
        )

        websocket_service_asset = s3_assets.Asset(
            self,
            "WebSocketServiceAsset",
            path=os.path.join(os.path.dirname(__file__), "../assets/websocket-server.service")
        )

        # Create the EC2 instance
        instance = ec2.Instance(
            self,
            "GuestrixAppInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T2,
                ec2.InstanceSize.MICRO
            ),
            machine_image=ec2.MachineImage.lookup(
                name="ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*",
                owners=["099720109477"]  # Canonical's AWS account ID
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=security_group,
            role=instance_role,
            user_data=user_data,
            key_name=os.getenv('EC2_KEY_PAIR_NAME', 'guestrix-key-pair')  # Specify an existing key pair for SSH access
        )

        # Grant the instance access to the assets
        websocket_server_asset.grant_read(instance.role)
        utils_asset.grant_read(instance.role)
        websocket_service_asset.grant_read(instance.role)

        # Add user data to download the assets
        instance.user_data.add_commands(
            f"mkdir -p /app/assets/websocket_server",
            f"mkdir -p /app/assets/utils",
            f"aws s3 cp {websocket_server_asset.s3_object_url} /app/assets/websocket_server/ --recursive",
            f"aws s3 cp {utils_asset.s3_object_url} /app/assets/utils/ --recursive",
            f"aws s3 cp {websocket_service_asset.s3_object_url} /app/assets/websocket-server.service"
        )

        # Output the EC2 instance public IP and DNS
        CfnOutput(
            self,
            "EC2InstancePublicIP",
            value=instance.instance_public_ip,
            description="Public IP address of the EC2 instance"
        )

        CfnOutput(
            self,
            "EC2InstancePublicDNS",
            value=instance.instance_public_dns_name,
            description="Public DNS name of the EC2 instance"
        )

        # Output the custom domain URL
        CfnOutput(
            self,
            "CustomDomainURL",
            value="https://app.guestrix.ai",
            description="Custom domain URL for the application"
        )

        # Note: We're not creating a Route 53 record here because it already exists
        # You'll need to manually update the Route 53 record to point to the new EC2 instance
        # after deployment
