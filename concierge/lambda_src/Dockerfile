# lambda_src/Dockerfile
# Use the official AWS Lambda Python runtime base image
FROM public.ecr.aws/lambda/python:3.11

# Set the working directory in the container
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy the requirements file first to leverage Docker cache
COPY lambda_src/requirements.txt .

# Force cache invalidation to ensure all dependencies are installed
# Install dependencies
# Using --no-cache-dir can reduce image size slightly
# Using --prefer-binary might speed up installs for some packages
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    echo "Cache busted $(date) - Updated dependencies"

# Copy function code and potentially scripts from the context
# This assumes the CDK build context is the project root directory (concierge/)
COPY lambda_src/voice_lambda_function.py .
COPY lambda_src/websocket_lambda_function.py .
COPY lambda_src/firebase_admin_config.py .
COPY lambda_src/consolidated_call_handler.py .

# Create a symbolic link for backward compatibility
RUN ln -sf voice_lambda_function.py lambda_function.py

# NEW: Copy the utils directory containing ai_helpers.py etc.
COPY utils/ ${LAMBDA_TASK_ROOT}/utils/

# Copy scripts if they exist (adjust path if needed)
COPY scripts/ ${LAMBDA_TASK_ROOT}/scripts/

# Copy credentials directory content if needed inside the image
# NOTE: Better practice is usually to pass credentials via environment variables or secrets manager,
# but copying is an option if required by the application logic.
# Ensure credentials/ directory exists in the build context (project root).
# COPY credentials/ ${LAMBDA_TASK_ROOT}/credentials/

# The CMD will be set dynamically by CDK's DockerImageFunction properties.
# Example: CMD ["lambda_function.lambda_handler"] is typically inferred or set in CDK.
