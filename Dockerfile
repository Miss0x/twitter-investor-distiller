FROM python:3.13-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Data volume
VOLUME ["/app/data"]

# Default: start public dashboard on 8000
EXPOSE 8000
CMD ["python", "-m", "src.interfaces.web_api"]
