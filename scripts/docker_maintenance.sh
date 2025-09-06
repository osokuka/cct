#!/bin/bash
# Docker maintenance script for daily task processing

# Configuration
CONTAINER_NAME="arcom_web_1"  # Adjust based on your container name
COMMAND="python manage.py daily_task_maintenance"

# Check if container is running
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo "Error: Container $CONTAINER_NAME is not running"
    exit 1
fi

# Run the maintenance command
echo "Running daily maintenance in container $CONTAINER_NAME..."
docker exec $CONTAINER_NAME $COMMAND

# Check exit status
if [ $? -eq 0 ]; then
    echo "Daily maintenance completed successfully"
else
    echo "Error: Daily maintenance failed"
    exit 1
fi
