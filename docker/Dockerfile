FROM python:3.11-slim

WORKDIR /app

# Pick up Debian security fixes released since the base image was built
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

COPY . .

# Uploaded photos and favicons are stored here; mount a volume over this path
RUN mkdir -p static/uploads/photos static/uploads/favicon static/uploads/hero

EXPOSE 8000

ENTRYPOINT ["bash", "docker/entrypoint.sh"]
