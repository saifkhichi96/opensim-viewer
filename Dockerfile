FROM python:3.9-slim

# System dependencies for FFmpeg and the OpenGL/X11 window
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libx11-6 libxext6 libxrender1 libsm6 \
    libxkbcommon0 libxkbcommon-x11-0 libxcb1 libxfixes3 \
    mesa-utils mesa-va-drivers \
    ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

# App
WORKDIR /app
COPY pyproject.toml README.md /app/
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src
COPY assets /app/assets
RUN pip install --no-cache-dir --no-deps .
ENV PYTHONPATH=/app/src

# Populate AppData Geometry on first run
ENV OSIM_APPDATA=/root/.local/share/osim-viewer

ENTRYPOINT ["osim-viewer"]
