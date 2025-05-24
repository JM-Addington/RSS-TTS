# Apple Podcasts Testing Guide

This guide explains how to test the RSS-TTS application with Apple Podcasts to verify that MP3 files play correctly.

## Quick Test

Run the automated byte-range test:
```bash
./test_byte_range.sh
```

This script will:
- Set up a test MP3 file
- Start the Docker containers with Caddy
- Verify byte-range request support
- Show you the test results

## Manual Testing with Apple Podcasts

### 1. Start the Application
```bash
docker-compose up -d
```

### 2. Create Test Content
1. Visit http://localhost:8084
2. Create a user account
3. Create a new feed (e.g., "Test Feed")
4. Add an article with either:
   - A URL to scrape
   - Manual text content
5. Wait for processing to complete

### 3. Get the RSS Feed URL
1. Go to your feed list
2. Copy the RSS feed URL (it will look like: `http://localhost:8084/feeds/{uuid}/`)

### 4. Test in Apple Podcasts
1. Open Apple Podcasts on macOS or iOS
2. Go to Library → Shows → + → Add a Show by URL
3. Paste your RSS feed URL
4. Subscribe to the podcast
5. Try to play the episode

### Expected Results
- ✅ The episode should appear in Apple Podcasts
- ✅ The MP3 should play without errors
- ✅ You should be able to seek/scrub through the audio
- ✅ The episode should download successfully

### Troubleshooting

If the MP3 doesn't play:
1. Check Caddy logs: `docker-compose logs caddy`
2. Verify the file exists: `ls -la media/articles/`
3. Test byte-range support: `curl -I -H "Range: bytes=0-1000" http://localhost:8084/audio/{uuid}/`
4. Look for HTTP 206 response (not 200)

### Testing with ngrok (for real device testing)
If you want to test on a real iPhone/iPad:
```bash
# Install ngrok if you haven't already
brew install ngrok

# Expose your local server
ngrok http 8084

# Use the ngrok URL in your RSS feed settings
```

Update your `.env` file with the ngrok URL:
```
SITE_URL=https://your-subdomain.ngrok.io
```

Then restart the containers and use the ngrok URL for testing.

## What We Fixed

The issue was that Apple Podcasts requires byte-range request support for streaming MP3 files. When Apple Podcasts requests part of a file (e.g., `Range: bytes=200-300`), the server must:

1. Return HTTP 206 (Partial Content), not HTTP 200
2. Include a `Content-Range` header
3. Support the `Accept-Ranges: bytes` header

Django's `FileResponse` doesn't handle this properly, so we added Caddy as a reverse proxy that:
- Serves MP3 files directly at `/audio/{uuid}/`
- Automatically handles byte-range requests
- Returns proper HTTP 206 responses
- Provides better performance for static files
