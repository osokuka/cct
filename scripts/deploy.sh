#!/bin/bash
# Production deployment script for ARCOM Cleaning Management System

set -e

echo "🚀 Starting ARCOM Production Deployment..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy env.example to .env and configure your settings."
    exit 1
fi

# Load environment variables
source .env

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs
mkdir -p docker/ssl
mkdir -p staticfiles
mkdir -p media

# Set proper permissions
echo "🔐 Setting permissions..."
chmod 755 logs
chmod 755 staticfiles
chmod 755 media

# Build and start services
echo "🐳 Building Docker images..."
docker-compose build --no-cache

echo "🔄 Starting services..."
docker-compose up -d db redis

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 10

# Run migrations
echo "📊 Running database migrations..."
docker-compose exec -T web python manage.py migrate

# Ensure the database cache table exists (used for cached config reads)
echo "🗃️  Ensuring cache table..."
docker-compose exec -T web python manage.py createcachetable

# Create superuser (if not exists)
echo "👤 Creating superuser..."
docker-compose exec -T web python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@arcom.com', 'admin123')
    print('Superuser created: admin/admin123')
else:
    print('Superuser already exists')
"

# Collect static files
echo "📦 Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput

# Start all services
echo "🚀 Starting all services..."
docker-compose up -d

# Show status
echo "📊 Service status:"
docker-compose ps

echo "✅ Deployment completed!"
echo "🌐 Application is available at: http://localhost"
echo "👤 Admin login: admin / admin123"
echo "📋 To view logs: docker-compose logs -f"
echo "🛑 To stop: docker-compose down"
