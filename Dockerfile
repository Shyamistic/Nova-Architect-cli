# Nova Architect v2.0 — Production Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# Set work directory
WORKDIR /app

# Install system dependencies for Nova Act / Playwright
RUN apt-get update && apt-get install -y \
    libgbm-dev \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Create directory für SQLite database
RUN mkdir -p /app/data && chown -R 1000:1000 /app/data

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8000
ENV HOST=0.0.0.0

# Expose port
EXPOSE 8000

# Start application
CMD ["python", "backend/main.py"]
