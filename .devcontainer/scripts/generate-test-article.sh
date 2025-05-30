#!/bin/bash
set -e

# Script to generate a test article
cd /workspaces/RSS-TTS

echo "Generating a test article..."

# Default values
TEST_TITLE=${1:-"Test Article"}
TEST_CONTENT=${2:-"This is a test article content for RSS-TTS. It will be processed by the TTS engine."}

python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rss_tts.settings')
django.setup()
from django.contrib.auth import get_user_model
from text_to_audio.models import Feed, Article
import uuid

User = get_user_model()
admin = User.objects.get(username='admin')

# Find a feed or create one
try:
    feed = Feed.objects.filter(user=admin).first()
    if not feed:
        feed = Feed.objects.create(
            user=admin,
            name='Test Feed',
            url='https://example.com/rss',
            voice_mode='auto'
        )
        print(f'Created new feed: {feed.name}')

    # Create a test article
    article = Article.objects.create(
        feed=feed,
        title='$TEST_TITLE',
        link=f'https://example.com/article/{uuid.uuid4()}',
        content='$TEST_CONTENT',
        status='pending',
        voice_id='nova',  # Default voice
    )

    print(f'Test article created: {article.title}')
    print(f'You can view it at: http://localhost:9000/admin/text_to_audio/article/{article.id}/change/')
    print('To process this article, run the celery worker and use the admin interface to trigger processing')

except Exception as e:
    print(f'Error creating test article: {str(e)}')
"
