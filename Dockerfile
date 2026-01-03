# Use official Python image as base
FROM python:3.10-slim


# Install supervisord and build tools for Python C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
	supervisor \
	gcc \
	build-essential \
	python3-dev \
	libffi-dev \
	&& rm -rf /var/lib/apt/lists/*


# Set working directory
WORKDIR /app

# Copy all files (including configs) from the build context
COPY . ./

# Make the wrapper script executable
RUN chmod +x /app/run_hdl-buspro-mqtt.sh

# Install dependencies
RUN pip install --no-cache-dir .

# Run supervisord
CMD ["supervisord", "-c", "/app/supervisord.conf"]
