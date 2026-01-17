# Dockerfile for Flask application
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY concierge/ ./concierge/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Expose port
EXPOSE 8080

# Run the application
CMD ["gunicorn", "--workers=2", "--threads=4", "--bind=0.0.0.0:8080", "app:application"]
