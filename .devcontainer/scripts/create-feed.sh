#!/bin/bash
set -e

# Script to create a test feed
cd /workspaces/RSS-TTS

# Default values
FEED_URL=${1:-"https://news.ycombinator.com/rss"}
FEED_NAME=${2:-"Hacker News"}

echo "Creating test feed..."
python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rss_tts.settings')
django.setup()
from django.contrib.auth import get_user_model
from text_to_audio.models import Feed

User = get_user_model()
admin = User.objects.get(username='admin')

feed, created = Feed.objects.get_or_create(
    url='$FEED_URL',
    defaults={
        'user': admin,
        'name': '$FEED_NAME',
        'voice_mode': 'auto'
    }
)

if created:
    print(f'Feed \"{feed.name}\" created successfully')
else:
    print(f'Feed \"{feed.name}\" already exists')
"

echo "Test feed setup complete!"
