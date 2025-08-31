#!/bin/sh

echo "Starting entrypoint script..."

# Wait for postgres to be ready
echo "Waiting for PostgreSQL..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL is ready!"

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z redis 6379; do
  sleep 0.1
done
echo "Redis is ready!"

# Create necessary directories
echo "Creating directories..."
mkdir -p /app/static
mkdir -p /app/staticfiles
mkdir -p /app/media
mkdir -p /app/logs

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput || {
    echo "Migration failed, but continuing..."
}

# Collect static files (with clear option to avoid conflicts)
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear || {
    echo "Static collection had issues, but continuing..."
}

# Create cache table for database caching
echo "Creating cache table..."
python manage.py createcachetable || {
    echo "Cache table creation skipped or failed..."
}

echo "Entrypoint script completed!"

# Execute the main command
exec "$@"