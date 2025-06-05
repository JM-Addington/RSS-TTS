# GPT-Based URL Extraction

## Overview

This feature uses GPT-4o1 (with its 1M+ token context window) to intelligently extract article content from web pages. Instead of using rigid rules to extract text, we clean the HTML minimally and let GPT-4o1 determine what content should be narrated.

## How It Works

1. **HTML Cleaning**: BeautifulSoup removes only unwanted elements:
   - Script and style tags
   - Form elements
   - Meta tags and other non-content elements
   - Unnecessary attributes (class, id, style, onclick, etc.)
   - Keeps only essential attributes (href for links, src/alt for images)

2. **GPT-4o1 Extraction**: The cleaned HTML is sent to GPT-4o1 with instructions to:
   - Extract the main article title and body
   - Include image descriptions from alt text
   - Include table summaries
   - Exclude navigation, ads, footers, sidebars, comments, etc.

3. **Fallback**: If GPT extraction fails, the system falls back to the traditional BeautifulSoup-based extraction.

## Configuration

### Environment Variables

- `USE_GPT_FOR_URL_EXTRACTION`: Enable/disable GPT extraction (default: `True`)
- `OPENAI_API_KEY`: Required for GPT-4o1 API access

### Django Settings

```python
# Enable GPT-based URL extraction
USE_GPT_FOR_URL_EXTRACTION = True
```

## Usage

The feature is automatically used when processing URLs through the article submission form or API. No code changes are required.

## Benefits

1. **Better Content Extraction**: GPT-4o1 understands context and can intelligently identify the main article content
2. **Handles Complex Layouts**: Works with various website structures without custom rules
3. **Preserves Structure**: Maintains the logical flow of the article
4. **Image Descriptions**: Automatically includes alt text as narration-friendly descriptions

## Cost Considerations

GPT-4o1 usage is billed per token. With the 1M+ context window, even large web pages can be processed, but costs should be monitored for high-volume usage.

## Testing

Run the test suite:
```bash
python manage.py test tests.text_to_audio.test_gpt_url_extraction
```

## Troubleshooting

1. **GPT extraction fails**: Check the logs for specific error messages. Common issues:
   - API rate limits
   - Invalid API key
   - Network connectivity

2. **Fallback to traditional extraction**: This is normal behavior when GPT extraction fails. Check logs for the specific error.

3. **Poor extraction quality**: The GPT prompt can be adjusted in `text_to_audio/utils.py` in the `extract_article_text_with_gpt` function.
