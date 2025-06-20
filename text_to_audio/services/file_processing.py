"""File processing service for PDF and HTML uploads.

This module provides functionality to extract text content from uploaded
PDF and HTML files, similar to URL-based content extraction.
"""

import logging
import mimetypes
import os
from typing import Optional, Tuple

from django.core.files.uploadedfile import UploadedFile

logger = logging.getLogger(__name__)


class FileProcessingService:
    """Service for processing uploaded PDF and HTML files."""

    def __init__(self):
        """Initialize the file processing service."""
        pass

    def detect_file_type(self, uploaded_file: UploadedFile) -> Optional[str]:
        """Detect the file type from the uploaded file.

        Args:
            uploaded_file: The uploaded file object.

        Returns:
            Detected file type ('pdf', 'html', 'txt') or None if unsupported.
        """
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(uploaded_file.name or "")

        # Check file extension as fallback
        if uploaded_file.name:
            extension = os.path.splitext(uploaded_file.name.lower())[1]
        else:
            extension = ""

        # Determine file type
        if mime_type == "application/pdf" or extension == ".pdf":
            return "pdf"
        elif (
            mime_type in ["text/html", "application/xhtml+xml"]
            or extension in [".html", ".htm"]
        ):
            return "html"
        elif mime_type == "text/plain" or extension == ".txt":
            return "txt"

        return None

    def extract_text_from_pdf(self, file_content: bytes) -> Tuple[bool, str, Optional[str]]:
        """Extract text content from a PDF file.

        Args:
            file_content: The PDF file content as bytes.

        Returns:
            Tuple of (success, extracted_text, error_message).
        """
        try:
            import PyPDF2
            from io import BytesIO

            # Create a BytesIO object from the file content
            pdf_file = BytesIO(file_content)

            # Create a PDF reader
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            # Extract text from all pages
            text_parts = []
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text.strip():
                        text_parts.append(page_text.strip())
                except Exception as e:
                    logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
                    continue

            if not text_parts:
                return False, "", "No readable text found in the PDF file"

            # Join all text with newlines
            extracted_text = "\n".join(text_parts)

            return True, extracted_text, None

        except ImportError:
            error_msg = "PyPDF2 library not available for PDF processing"
            logger.error(error_msg)
            return False, "", error_msg
        except Exception as e:
            error_msg = f"Error processing PDF file: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg

    def extract_text_from_html(self, file_content: bytes) -> Tuple[bool, str, Optional[str]]:
        """Extract text content from an HTML file.

        Args:
            file_content: The HTML file content as bytes.

        Returns:
            Tuple of (success, extracted_text, error_message).
        """
        try:
            # Decode the HTML content
            html_content = file_content.decode("utf-8", errors="ignore")

            # Use existing HTML extraction function
            from ..utils import extract_article_text

            return extract_article_text(html_content)

        except Exception as e:
            error_msg = f"Error processing HTML file: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg

    def extract_text_from_txt(self, file_content: bytes) -> Tuple[bool, str, Optional[str]]:
        """Extract text content from a plain text file.

        Args:
            file_content: The text file content as bytes.

        Returns:
            Tuple of (success, extracted_text, error_message).
        """
        try:
            # Decode the text content
            text_content = file_content.decode("utf-8", errors="ignore").strip()

            if not text_content:
                return False, "", "The text file appears to be empty"

            return True, text_content, None

        except Exception as e:
            error_msg = f"Error processing text file: {str(e)}"
            logger.error(error_msg)
            return False, "", error_msg

    def process_file_with_gpt(
        self, file_content: bytes, file_type: str, filename: str = ""
    ) -> Tuple[bool, str, Optional[str]]:
        """Process file content using GPT-4.1 for intelligent extraction.

        Args:
            file_content: The file content as bytes.
            file_type: The detected file type ('pdf', 'html', 'txt').
            filename: The original filename for context.

        Returns:
            Tuple of (success, extracted_text, error_message).
        """
        try:
            # First extract text using appropriate method
            if file_type == "pdf":
                success, raw_text, error = self.extract_text_from_pdf(file_content)
            elif file_type == "html":
                success, raw_text, error = self.extract_text_from_html(file_content)
            elif file_type == "txt":
                success, raw_text, error = self.extract_text_from_txt(file_content)
            else:
                return False, "", f"Unsupported file type: {file_type}"

            if not success:
                return False, "", error

            # Use GPT-4.1 to clean and structure the content
            from django.conf import settings
            import openai
            import time

            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

            # Prepare the prompt for GPT-4.1
            prompt = f"""Clean and structure this extracted text from a {file_type.upper()} file for audio narration.

Remove any formatting artifacts, fix spacing issues, and ensure the text flows naturally for speech.
Include only the main content that should be narrated, such as:
- Main headings and titles
- Body paragraphs and content
- Important quotes or excerpts
- Lists and bullet points (format naturally for speech)

Remove:
- Page numbers, headers, footers
- Table of contents entries
- Navigation elements
- Copyright notices
- Irrelevant metadata

Filename: {filename}

Raw extracted text:
{raw_text}

CLEANED TEXT FOR NARRATION:"""

            # Log the API call
            start_time = time.monotonic()
            request_data = {
                "model": "gpt-4.1-2025-04-14",  # Using GPT-4.1 with large context
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert at cleaning and structuring text extracted from documents for audio narration. Make the text flow naturally for speech while preserving all important content.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 32768,  # GPT-4.1 supports up to 32K output tokens
                "temperature": 0.1,  # Low temperature for consistent cleaning
            }

            try:
                # mypy: disable-error-code="call-overload"
                response = client.chat.completions.create(**request_data)  # type: ignore[call-overload]
                end_time = time.monotonic()
                duration_ms = int((end_time - start_time) * 1000)

                # Extract the cleaned content
                cleaned_text = response.choices[0].message.content.strip()

                # Log the successful API call
                from ..utils import log_openai_api_call

                response_data = {
                    "id": response.id,
                    "model": response.model,
                    "object": response.object,
                    "created": response.created,
                    "choices": [
                        {
                            "index": choice.index,
                            "message": {
                                "role": choice.message.role,
                                "content": (
                                    choice.message.content[:500] + "..."
                                    if len(choice.message.content) > 500
                                    else choice.message.content
                                ),
                            },
                            "finish_reason": choice.finish_reason,
                        }
                        for choice in response.choices
                    ],
                    "usage": (
                        {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                        }
                        if response.usage
                        else None
                    ),
                }

                log_openai_api_call(
                    operation=f"File Content Cleaning ({file_type.upper()})",
                    request_data=request_data,
                    response_data=response_data,
                    duration_ms=duration_ms,
                )

                if not cleaned_text:
                    return False, "", "GPT-4.1 could not clean the extracted content"

                return True, cleaned_text, None

            except openai.APIError as e:
                error_msg = f"OpenAI API error during file processing: {str(e)}"
                logger.error(error_msg)
                # Fall back to raw extracted text
                logger.info("Falling back to raw extracted text due to API error")
                return True, raw_text, None
            except Exception as e:
                error_msg = f"Error calling GPT-4.1 for file processing: {str(e)}"
                logger.error(error_msg)
                # Fall back to raw extracted text
                logger.info("Falling back to raw extracted text due to processing error")
                return True, raw_text, None

        except Exception as e:
            error_message = f"Error in file processing: {str(e)}"
            logger.error(error_message)
            return False, "", error_message

    def process_uploaded_file(self, uploaded_file: UploadedFile) -> Tuple[bool, str, str, Optional[str]]:
        """Process an uploaded file and extract its text content.

        Args:
            uploaded_file: The uploaded file object.

        Returns:
            Tuple of (success, extracted_text, detected_file_type, error_message).
        """
        try:
            # Detect file type
            file_type = self.detect_file_type(uploaded_file)
            if not file_type:
                supported_types = ["PDF (.pdf)", "HTML (.html, .htm)", "Text (.txt)"]
                return False, "", "", f"Unsupported file type. Supported types: {', '.join(supported_types)}"

            # Read file content
            uploaded_file.seek(0)  # Reset file pointer
            file_content = uploaded_file.read()

            if not file_content:
                return False, "", file_type, "The uploaded file appears to be empty"

            # Check file size (limit to 50MB for processing)
            max_size = 50 * 1024 * 1024  # 50MB
            if len(file_content) > max_size:
                return False, "", file_type, f"File too large. Maximum size is {max_size // (1024 * 1024)}MB"

            # Use GPT processing for better results
            from django.conf import settings
            use_gpt_processing = getattr(settings, "USE_GPT_FOR_FILE_PROCESSING", True)

            if use_gpt_processing:
                success, text, error = self.process_file_with_gpt(
                    file_content, file_type, uploaded_file.name or ""
                )
                if success:
                    return True, text, file_type, None
                else:
                    # Log the error but fall back to basic extraction
                    logger.warning(
                        f"GPT file processing failed: {error}. Falling back to basic extraction."
                    )

            # Fall back to basic extraction methods
            if file_type == "pdf":
                success, text, error = self.extract_text_from_pdf(file_content)
            elif file_type == "html":
                success, text, error = self.extract_text_from_html(file_content)
            elif file_type == "txt":
                success, text, error = self.extract_text_from_txt(file_content)
            else:
                return False, "", file_type, f"Unsupported file type: {file_type}"

            if not success:
                return False, "", file_type, error

            return True, text, file_type, None

        except Exception as e:
            error_message = f"Error processing uploaded file: {str(e)}"
            logger.error(error_message)
            return False, "", "", error_message
