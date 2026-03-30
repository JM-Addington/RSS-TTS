"""Views for handling Mailgun webhook requests."""

import base64
import logging

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Feed
from .services.email_parser import EmailParser
from .services.mailgun_service import MailgunService
from .tasks import process_incoming_email

logger = logging.getLogger(__name__)

# AIDEV-NOTE: defense-in-depth — Mailgun enforces ~25MB upstream, but we cap at 10MB
# to limit memory use (base64 adds ~33% overhead) and match forms.py MAX_UPLOAD_SIZE.
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10MB


@csrf_exempt
@require_POST
def mailgun_incoming_webhook(request):
    """Handle incoming email webhooks from Mailgun.

    This endpoint receives POST requests from Mailgun when emails are sent
    to feed-specific addresses. It validates the request, queues processing
    asynchronously, and returns immediately to avoid webhook timeouts.

    AIDEV-NOTE: Critical - return HTTP 200 quickly to avoid Mailgun timeout.
    Heavy processing (LLM email cleaning, PDF extraction) happens in Celery task.

    Args:
        request: Django HttpRequest with POST data and FILES from Mailgun

    Returns:
        HttpResponse with status 200 on success, 400/403 on error
    """
    # AIDEV-NOTE: Webhook security - verify signature before processing
    # Extract signature data from POST
    timestamp = request.POST.get("timestamp", "")
    token = request.POST.get("token", "")
    signature = request.POST.get("signature", "")

    # Verify webhook signature
    mailgun_service = MailgunService()
    if not mailgun_service.verify_webhook_signature(timestamp, token, signature):
        logger.warning("Invalid Mailgun webhook signature")
        return HttpResponseForbidden("Invalid signature")

    try:
        # Validate email data (quick check)
        is_valid, error_msg = EmailParser.is_valid_email_data(request.POST)
        if not is_valid:
            logger.warning(f"Invalid email data: {error_msg}")
            return HttpResponseBadRequest(f"Invalid email data: {error_msg}")

        # Find the feed by recipient email (quick database lookup)
        recipient = EmailParser.extract_recipient(request.POST)
        if not recipient:
            logger.warning("No recipient in email data")
            return HttpResponseBadRequest("No recipient found")

        try:
            feed = Feed.objects.get(inbound_email=recipient)
        except Feed.DoesNotExist:
            logger.warning(f"No feed found for recipient: {recipient}")
            return HttpResponseBadRequest(f"No feed found for recipient: {recipient}")

        # Extract email content for async processing
        # Read attachments into memory and base64 encode for Celery serialization
        attachments_data = []
        attachment_count = int(request.POST.get("attachment-count", 0))
        for i in range(1, attachment_count + 1):
            attachment_key = f"attachment-{i}"
            if attachment_key in request.FILES:
                file_obj = request.FILES[attachment_key]
                if file_obj.size > MAX_ATTACHMENT_SIZE:
                    logger.warning(
                        "Skipping oversized attachment '%s' (%d bytes, limit %d bytes)",
                        file_obj.name,
                        file_obj.size,
                        MAX_ATTACHMENT_SIZE,
                    )
                    continue
                file_obj.seek(0)
                file_bytes = file_obj.read()
                attachments_data.append(
                    {
                        "filename": file_obj.name,
                        "content_type": file_obj.content_type,
                        "data": base64.b64encode(file_bytes).decode("ascii"),
                    }
                )

        # Extract text content
        text_content, _ = EmailParser.extract_text_content(request.POST)

        # Build payload for async task
        email_payload = {
            "feed_id": feed.id,
            "subject": EmailParser.extract_title(request.POST),
            "text_content": text_content,
            "sender": EmailParser.extract_sender(request.POST),
            "attachments": attachments_data,
        }

        # Queue for async processing and return immediately
        process_incoming_email.delay(email_payload)

        logger.info(
            f"Queued email processing for feed {feed.id} "
            f"(recipient: {recipient}, sender: {email_payload['sender']}, "
            f"attachments: {len(attachments_data)})"
        )

        return HttpResponse("Email accepted for processing", status=200)

    except Exception as e:
        logger.error(f"Error accepting Mailgun webhook: {e}", exc_info=True)
        return HttpResponseBadRequest(f"Error accepting email: {str(e)}")
