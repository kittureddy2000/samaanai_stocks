# Backend Dockerfile for Django API
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY backend/ ./backend/
COPY trading_api/ ./trading_api/
COPY manage.py .

# Collect static files
RUN python manage.py collectstatic --noinput --settings=backend.settings.production || true

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DJANGO_SETTINGS_MODULE=backend.settings.production

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run with gunicorn
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 120 backend.wsgi:application
