#!/usr/bin/env python3
import os
import aws_cdk as cdk
from dotenv import load_dotenv 

from infra.infra_stack import InfraStack

# --- Load .env file --- 
# Construct the path to the .env file in the parent directory
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env') 
# Check if the .env file exists
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Loaded environment variables from: {dotenv_path}")
else:
    print(f"Warning: .env file not found at {dotenv_path}. Proceeding without it.")

app = cdk.App()

# Define common environment for all stacks
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'), 
    region=os.getenv('CDK_DEFAULT_REGION')
)

# Deploy the main infrastructure stack
infra_stack = InfraStack(
    app, 
    "InfraStack",
    env=env
)

app.synth()
