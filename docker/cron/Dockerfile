FROM python:3.11-slim

# Install cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Django project
COPY . .

# Create cron job script
RUN echo '#!/bin/bash\ncd /app\npython manage.py daily_task_maintenance' > /app/run_maintenance.sh
RUN chmod +x /app/run_maintenance.sh

# Add cron job (runs daily at 11:59 PM)
RUN echo '59 23 * * * /app/run_maintenance.sh >> /var/log/cron.log 2>&1' | crontab -

# Create log file
RUN touch /var/log/cron.log

# Start cron in foreground
CMD ["cron", "-f"]
