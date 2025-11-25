"""Views for handling Mailgun webhook requests."""

import logging
import os
import uuid

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Article, Feed
from .services.email_cleaning_service import EmailCleaningService
from .services.email_parser import EmailParser
from .services.mailgun_service import MailgunService
from .tasks import process_article
from .utils import extract_text_from_pdf, extract_title_from_html

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def mailgun_incoming_webhook(request):
    """Handle incoming email webhooks from Mailgun.

    This endpoint receives POST requests from Mailgun when emails are sent
    to feed-specific addresses. It parses the email, creates an Article,
    and queues it for TTS processing.

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
        # Parse the email data
        email_data = EmailParser.parse_webhook_payload(request.POST, request.FILES)

        # Validate email data
        is_valid, error_msg = EmailParser.is_valid_email_data(request.POST)
        if not is_valid:
            logger.warning(f"Invalid email data: {error_msg}")
            return HttpResponseBadRequest(f"Invalid email data: {error_msg}")

        # Find the feed by recipient email
        recipient = email_data.get("recipient")
        if not recipient:
            logger.warning("No recipient in email data")
            return HttpResponseBadRequest("No recipient found")

        try:
            feed = Feed.objects.get(inbound_email=recipient)
        except Feed.DoesNotExist:
            logger.warning(f"No feed found for recipient: {recipient}")
            return HttpResponseBadRequest(f"No feed found for recipient: {recipient}")

        # Extract content - priority: attachments > email body
        text_content = ""
        title = email_data.get("subject", "Email Article")

        # AIDEV-NOTE: Process attachments first (PDF, HTML) before falling back to email body
        # This matches the file upload flow in FeedArticleCreateView
        attachments = email_data.get("attachments", [])
        processed_attachment = False

        for attachment in attachments:
            file_obj = attachment.get("file")
            if not file_obj:
                continue

            filename = attachment.get("filename", "")
            content_type = attachment.get("content_type", "")

            # Handle PDF attachments
            if content_type == "application/pdf":
                extracted_text = extract_text_from_pdf(file_obj)
                if not extracted_text.startswith("Error:"):
                    text_content = extracted_text
                    processed_attachment = True
                    if not title or title == "Email Article":
                        title = os.path.splitext(filename)[0]
                    break  # Use first successfully processed attachment

            # Handle HTML attachments
            elif content_type == "text/html":
                try:
                    file_obj.seek(0)
                    html_content = file_obj.read().decode("utf-8")
                    from .utils import clean_html_minimal, extract_article_text

                    cleaned_html = clean_html_minimal(html_content)
                    success, text, error = extract_article_text(cleaned_html)
                    if success and text:
                        text_content = text
                        processed_attachment = True

                        # Try to extract title from HTML
                        if not title or title == "Email Article":
                            extracted_title = extract_title_from_html(html_content)
                            if extracted_title:
                                title = extracted_title
                            else:
                                title = os.path.splitext(filename)[0]
                        break  # Use first successfully processed attachment
                except Exception as e:
                    logger.warning(f"Failed to process HTML attachment: {e}")
                    continue

        # If no attachment was processed, use email body
        if not processed_attachment:
            text_content = email_data.get("text_content", "")

            # AIDEV-NOTE: Apply LLM-based email cleaning to extract main content
            # Only applies to email body text (not attachments like PDFs/HTML files)
            # Removes boilerplate, ads, signatures while keeping core content
            if text_content and getattr(settings, "ENABLE_EMAIL_CONTENT_CLEANING", True):
                logger.info(
                    f"Applying LLM-based email content cleaning for feed {feed.id}"
                )
                cleaning_service = EmailCleaningService()
                success, cleaned_text, metadata, error = (
                    cleaning_service.clean_email_content(text_content, title)
                )

                if success and cleaned_text:
                    logger.info(
                        f"Email content cleaned successfully: {metadata.get('content_type', 'unknown')} "
                        f"(confidence: {metadata.get('confidence', 'unknown')}, "
                        f"reduction: {metadata.get('reduction_percent', 0)}%)"
                    )
                    text_content = cleaned_text
                else:
                    logger.warning(
                        f"Email cleaning failed or returned empty, using raw text: {error}"
                    )
                    # Fall back to raw text if cleaning fails

        # Validate we have some content
        if not text_content or not text_content.strip():
            logger.warning("No text content extracted from email")
            return HttpResponseBadRequest("No text content found in email")

        # Create the article
        article = Article(
            feed=feed,
            title=title,
            text_content=text_content,
            status=Article.PROCESSING,
            audio_uuid=uuid.uuid4(),
        )

        # Use feed's default voice settings if available
        if feed.default_voice_preset:
            preset = feed.default_voice_preset
            from text_to_audio.models import VOICE_CHOICES

            standard_voices = [choice[0] for choice in VOICE_CHOICES]
            if preset.voice_id in standard_voices:
                article.voice = preset.voice_id
                article.voice_id = None
            else:
                article.voice_id = preset.voice_id
                article.voice = "alloy"
            article.speed = preset.speed
            article.voice_preset = preset

        # Save and queue for processing
        article.save()
        task = process_article.delay(article.pk)
        article.celery_task_id = task.id
        article.save(update_fields=["celery_task_id", "updated_at"])

        logger.info(
            f"Created article {article.pk} from email to {recipient} "
            f"(sender: {email_data.get('sender')})"
        )

        return HttpResponse("Email processed successfully", status=200)

    except Exception as e:
        logger.error(f"Error processing Mailgun webhook: {e}", exc_info=True)
        return HttpResponseBadRequest(f"Error processing email: {str(e)}")
