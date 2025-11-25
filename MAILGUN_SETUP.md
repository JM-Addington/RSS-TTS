# Mailgun Email-to-Feed Setup Guide

This guide explains how to set up the Mailgun integration for emailing articles directly to your RSS-TTS feeds.

## Overview

With Mailgun integration enabled, each feed automatically gets its own unique email address (e.g., `happy-river-42@mg.example.com`). Users can forward emails, newsletters, or documents to this address, and they'll automatically be converted to audio and added to the feed.

### Supported Content

- **Email body**: Plain text and HTML emails
- **PDF attachments**: Text will be extracted from PDF files
- **HTML attachments**: Article text will be extracted from HTML files
- The email subject line becomes the article title

## Prerequisites

1. A Mailgun account (free tier works)
2. A verified domain in Mailgun (e.g., `mg.yourdomain.com`)
3. Your RSS-TTS instance must be publicly accessible (Mailgun needs to send webhooks)

## Setup Steps

### 1. Configure Environment Variables

Add these variables to your `.env` file:

```bash
# Mailgun settings
MAILGUN_API_KEY=your-mailgun-api-key-here
MAILGUN_DOMAIN=mg.yourdomain.com
MAILGUN_WEBHOOK_SIGNING_KEY=your-webhook-signing-key-here

# Required for route creation
SITE_URL=https://your-domain.com
```

**Where to find these values:**

- **MAILGUN_API_KEY**: Found in Mailgun Dashboard → Settings → API Keys → Private API key
- **MAILGUN_DOMAIN**: Your verified Mailgun domain (e.g., `mg.yourdomain.com`)
- **MAILGUN_WEBHOOK_SIGNING_KEY**: Found in Mailgun Dashboard → Settings → Webhooks → HTTP webhook signing key
- **SITE_URL**: Your public RSS-TTS URL (must be HTTPS in production)

### 2. Verify Mailgun Domain

1. Log into [Mailgun](https://app.mailgun.com/)
2. Go to **Sending** → **Domains**
3. Add your domain (e.g., `mg.yourdomain.com`)
4. Add the required DNS records to your domain:
   - TXT records for SPF and DKIM
   - CNAME record for tracking
   - MX records (if receiving email)
5. Wait for verification (usually takes a few minutes to hours)

### 3. Restart Your Application

After adding the environment variables:

```bash
# For Docker deployments
docker-compose restart

# For local development
python manage.py runserver
```

## How It Works

### Automatic Setup

1. When a new feed is created, the system automatically:
   - Generates a unique, readable email address (e.g., `happy-river-42@mg.example.com`)
   - Creates a Mailgun route to forward emails to that address to your webhook
   - Stores the route ID for cleanup when the feed is deleted

2. Email addresses are **deterministic** - they're generated from the feed's UUID token, so regenerating will produce the same address.

### Email Processing Flow

1. User forwards an email to the feed's address
2. Mailgun receives the email and POSTs it to: `https://your-domain.com/api/v1/mailgun/incoming/`
3. The webhook:
   - Verifies the Mailgun signature for security
   - Parses the email content and attachments
   - Creates a new Article in the feed
   - Queues the article for TTS processing
4. The article appears in the feed like any other article

### Email Address Format

Email addresses use a readable format: `adjective-noun-number@domain`

Examples:
- `happy-river-42@mg.example.com`
- `crystal-eagle-23@mg.example.com`
- `bright-forest-87@mg.example.com`

This format is:
- Easy to read and remember
- Unique per feed
- Deterministic (same feed = same email)

## Viewing Email Addresses

### In the Feed List

Each feed card shows the email address with a copy button:

```
Email to Feed:
happy-river-42@mg.example.com [Copy]
Forward emails or newsletters to this address to add them to your feed.
```

### In the Article List

When viewing a feed's articles, the email address is displayed in a prominent card:

```
📧 Email to Feed
Forward emails or newsletters to this address to automatically add them to your feed:
happy-river-42@mg.example.com [Copy]

Supported formats: Plain text emails, HTML emails, PDF attachments, and HTML attachments.
```

## Troubleshooting

### Email addresses not showing

**Symptom**: Feeds don't have email addresses in the UI.

**Solutions**:
1. Check that `MAILGUN_API_KEY` and `MAILGUN_DOMAIN` are set in `.env`
2. Verify the Mailgun domain is verified in Mailgun dashboard
3. Restart your application after adding environment variables
4. Check logs for any errors during feed creation

### Emails not creating articles

**Symptom**: Emails are sent but articles don't appear in the feed.

**Solutions**:
1. Check that `SITE_URL` is set correctly and publicly accessible
2. Verify the webhook URL is reachable: `https://your-domain.com/api/v1/mailgun/incoming/`
3. Check Mailgun logs (Dashboard → Sending → Logs) for delivery issues
4. Review application logs for webhook processing errors
5. Verify `MAILGUN_WEBHOOK_SIGNING_KEY` matches your Mailgun account

### Routes not being created

**Symptom**: Email addresses show but Mailgun routes aren't created.

**Solutions**:
1. Check application logs for route creation errors
2. Verify your Mailgun API key has permission to create routes
3. Manually check routes in Mailgun Dashboard → Sending → Routes
4. Ensure `SITE_URL` is set (required for webhook URL generation)

### Invalid signature errors

**Symptom**: Webhook returns 403 Forbidden.

**Solutions**:
1. Verify `MAILGUN_WEBHOOK_SIGNING_KEY` is correct
2. Check that the key matches your Mailgun account's webhook signing key
3. Ensure the signing key hasn't been rotated in Mailgun

## Manual Route Management

If you need to manually manage routes:

### View Routes

```bash
curl -s --user 'api:YOUR_API_KEY' \
    https://api.mailgun.net/v3/routes
```

### Delete a Route

```bash
curl -X DELETE --user 'api:YOUR_API_KEY' \
    https://api.mailgun.net/v3/routes/ROUTE_ID
```

### Create a Route Manually

```bash
curl -X POST --user 'api:YOUR_API_KEY' \
    https://api.mailgun.net/v3/routes \
    -F priority=0 \
    -F description="Feed route" \
    -F expression="match_recipient('email@mg.example.com')" \
    -F action="forward('https://your-domain.com/api/v1/mailgun/incoming/')" \
    -F action="stop()"
```

## Security Considerations

1. **Webhook Signature Verification**: All incoming webhooks are verified using HMAC SHA256 to prevent spoofing
2. **HTTPS Required**: Use HTTPS in production to protect webhook data in transit
3. **Email Address Privacy**: Email addresses are unique per feed but publicly visible - don't use for sensitive content
4. **Content Validation**: The system validates email content and filters out malicious content

## Testing

### Send a Test Email

1. Find your feed's email address in the UI
2. Send a test email:
   ```
   To: happy-river-42@mg.example.com
   Subject: Test Article
   Body: This is a test of the email-to-feed feature!
   ```
3. Check the feed's article list - the article should appear within a minute
4. Monitor logs for any errors

### Test with Attachments

Send an email with:
- A PDF attachment containing text
- Or an HTML attachment (saved webpage)
- The attachment content will be extracted and used as the article text

## Performance Notes

- Email processing is asynchronous - articles are queued for TTS conversion
- Large PDFs may take longer to process
- The system respects your feed's default voice settings
- Failed emails are logged but don't retry automatically

## Support

For issues specific to:
- **Mailgun delivery**: Check [Mailgun Support](https://help.mailgun.com/)
- **RSS-TTS integration**: Check application logs and GitHub issues
- **Email parsing**: Enable debug logging to see detailed parsing information
