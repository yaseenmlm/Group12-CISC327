# Library Management System - CISC 327 Group 12 (Assignment 4)
# Build:  docker build -t cisc327-a4 .
# Run:    docker run --rm -p 5000:5000 cisc327-a4
FROM python:3.12-slim

# No .pyc files in the image; print logs straight to `docker logs`
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer is cached when only code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what the app needs at runtime (tests, docs, git data stay out)
COPY run.py notification_service.py ./
COPY app/ ./app/

# Don't run the server as root
RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

# 0.0.0.0 so the server accepts connections from outside the container
CMD ["flask", "--app", "run", "run", "--host", "0.0.0.0", "--port", "5000"]
