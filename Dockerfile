ARG BUILD_FROM
FROM $BUILD_FROM

# Install dependencies
# FFmpeg with x264 for HLS encoding, Chromium for dashboard capture
RUN apk add --no-cache \
    python3 \
    py3-pip \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ttf-freefont \
    font-noto-emoji \
    ffmpeg \
    netcat-openbsd

# Set up Python virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python packages
COPY rootfs/usr/src/app/requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create HLS output directory
RUN mkdir -p /tmp/hls

# Copy application files
COPY rootfs /

# Set working directory
WORKDIR /usr/src/app

# Make scripts executable
RUN chmod a+x /etc/services.d/dashboard-streams/run \
    && chmod a+x /etc/services.d/dashboard-streams/finish
