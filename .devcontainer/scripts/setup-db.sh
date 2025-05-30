#!/bin/bash
set -e

# Script to set up the database from scratch
cd /workspaces/RSS-TTS

echo "Setting up database..."
python manage.py migrate

echo "Creating superuser (if not exists)..."
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rss_tts.settings')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
"

echo "Database setup complete!"
echo "You can log in to the admin panel with:"
echo "Username: admin"
echo "Password: admin"
