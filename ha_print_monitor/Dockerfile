FROM python:3.12-slim

ARG BUILD_VERSION=0.3.1
ARG BUILD_ARCH

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libopencv-dev \
    python3-opencv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create writable runtime directories and non-root user
RUN groupadd --system app && \
    useradd --system --gid app --home /app app && \
    mkdir -p /data/captures /data/logs /data/backups /data/models && \
    chmod +x /app/run.sh && \
    chown -R app:app /app /data

USER app

# Internal ingress port. No public add-on port is exposed in config.yaml.
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=5)"

# Run application
CMD ["/app/run.sh"]
