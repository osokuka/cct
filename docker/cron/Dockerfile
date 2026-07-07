FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        cron \
        postgresql-client \
        build-essential \
        libpq-dev \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the Django project
COPY . /app/

# Create non-root user
RUN adduser --disabled-password --gecos '' cronuser \
    && chown -R cronuser:cronuser /app

# Create directories
RUN mkdir -p /app/staticfiles /app/media /var/log

# Create cron job scripts
RUN echo '#!/bin/bash\ncd /app\npython manage.py daily_task_maintenance' > /app/run_maintenance.sh
RUN chmod +x /app/run_maintenance.sh
RUN echo '#!/bin/bash\ncd /app\npython manage.py generate_route_tasks' > /app/run_generate_tasks.sh
RUN chmod +x /app/run_generate_tasks.sh

# Cron jobs:
#  - daily maintenance at 23:59
#  - weekly/bi-weekly route task generation every Sunday at 00:01
RUN printf '%s\n' \
    '59 23 * * * /app/run_maintenance.sh >> /var/log/cron.log 2>&1' \
    '1 0 * * 0 /app/run_generate_tasks.sh >> /var/log/cron.log 2>&1' \
    | crontab -

# Create log file and set permissions
RUN touch /var/log/cron.log && chown cronuser:cronuser /var/log/cron.log

# Start cron in foreground (as root, but tasks run as cronuser)
CMD ["cron", "-f"]
