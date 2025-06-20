"""Service for analyzing article content."""

import json
import logging
import time

from django.conf import settings

# Maximum number of words to analyze with LLM models
# Reduced from 750k to a more reasonable amount to avoid excessive costs and context limits
MAX_ANALYSIS_WORDS = getattr(settings, "MAX_ANALYSIS_WORDS", 8_000)

# Total context window limits for different models
# Note: These are TOTAL context limits (prompt + completion)
MODEL_TOKEN_LIMITS = {
    "gpt-4": 8_192,  # 8k total context
    "gpt-4-32k": 32_768,  # 32k total context
    "gpt-4-turbo": 128_000,  # 128k total context
    "gpt-4o": 128_000,  # 128k total context
    "gpt-4o-mini": 128_000,  # 128k total context
    "gpt-4.1": 32_768,  # 32k total context (deprecated)
}

# Default conservative limit if model not recognized
DEFAULT_TOKEN_LIMIT = 8_000

# Rough approximation: 1 token ≈ 4 characters or 0.75 words
CHARS_PER_TOKEN = 4
WORDS_PER_TOKEN = 0.75

logger = logging.getLogger(__name__)


class ContentAnalysisService:
    """Service for analyzing article content."""

    def __init__(self, openai_api_key=None):
        """Initialize with optional API key override."""
        self.openai_api_key = openai_api_key
        self._client = None

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            import openai
            from django.conf import settings

            self._client = openai.OpenAI(
                api_key=self.openai_api_key or settings.OPENAI_API_KEY
            )
        return self._client

    def _estimate_token_count(self, text):
        """Estimate token count for text using simple approximation.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        # Use character count as primary estimation
        char_estimate = len(text) / CHARS_PER_TOKEN
        # Also check word count as secondary estimation
        word_estimate = len(text.split()) / WORDS_PER_TOKEN
        # Use the higher estimate to be conservative
        return int(max(char_estimate, word_estimate))

    def _calculate_dynamic_max_tokens(self, prompt_text, model):
        """Calculate dynamic max_completion_tokens based on prompt size and model.

        Args:
            prompt_text: The full prompt text being sent to the model.
            model: The model name being used.

        Returns:
            Safe max_completion_tokens value.
        """
        # Get model token limit
        model_limit = DEFAULT_TOKEN_LIMIT

        # Check for exact match first, then prefix match
        if model in MODEL_TOKEN_LIMITS:
            model_limit = MODEL_TOKEN_LIMITS[model]
        else:
            # Try prefix matching
            for model_prefix, limit in MODEL_TOKEN_LIMITS.items():
                if model.startswith(model_prefix):
                    model_limit = limit
                    break

        # Estimate prompt tokens (including system message)
        system_message = "You are an expert content analyzer."
        total_prompt_tokens = self._estimate_token_count(prompt_text + system_message)

        # Calculate remaining tokens for completion
        remaining_tokens = model_limit - total_prompt_tokens

        # For safety, use 80% of the remaining tokens for completion
        max_completion_tokens = int(remaining_tokens * 0.8)

        # Ensure we have at least 500 tokens for response, but don't exceed remaining tokens
        max_completion_tokens = max(500, min(max_completion_tokens, remaining_tokens))

        # Additional safety check: if prompt is extremely large, reduce completion tokens further
        if total_prompt_tokens > 50_000:  # Very large prompt
            max_completion_tokens = min(max_completion_tokens, 2_000)
        elif total_prompt_tokens > 20_000:  # Large prompt
            max_completion_tokens = min(max_completion_tokens, 4_000)

        logger.info(
            f"Dynamic token calculation: model={model}, model_limit={model_limit}, "
            f"prompt_tokens≈{total_prompt_tokens}, max_completion_tokens={max_completion_tokens}"
        )

        return max_completion_tokens

    def analyze_content(self, text, title=None, max_completion_tokens=None):
        """Analyze article text and recommend narration voices.

        Args:
            text: The article text to analyze.
            title: Optional article title for additional context.
            max_completion_tokens: Maximum tokens for the LLM response. If None,
                                   will be dynamically calculated based on prompt size.

        Returns:
            dict with keys:
                - voices: List of voice definitions including ``name``, ``tone``,
                  ``tts_model`` and ``tts_speed``.
                - audio_segments: List of segments with ``text`` and the
                  ``voice_name`` from ``voices`` that should read the segment.
        """
        # Use up to MAX_ANALYSIS_WORDS words for analysis
        words = text.split()
        text_sample = " ".join(words[:MAX_ANALYSIS_WORDS])

        # Create the unified prompt
        prompt = self._create_analysis_prompt(text_sample, title)

        # Get the model we'll use
        model = self._get_analysis_model()

        # Calculate dynamic max tokens if not provided
        if max_completion_tokens is None:
            max_completion_tokens = self._calculate_dynamic_max_tokens(prompt, model)

        # Prepare request data for logging
        request_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert content analyzer."},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": max_completion_tokens,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        # Log content analysis API call details
        logger.info(
            f"Content Analysis API Call: model={model}, "
            f"max_completion_tokens={max_completion_tokens}, temperature=0.3, "
            f"prompt_length={len(prompt)} chars, "
            f"text_sample_length={len(text_sample)} chars, "
            f"title='{title or 'None'}'"
        )

        # Call OpenAI API with JSON mode and detailed logging
        start_time = time.monotonic()
        try:
            response = self.client.chat.completions.create(**request_data)
            end_time = time.monotonic()
            duration_ms = int((end_time - start_time) * 1000)

            # Extract response data for logging
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
                            "content": choice.message.content,
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

            # Log successful API call
            from ..utils import log_openai_api_call

            log_openai_api_call(
                operation="Content Analysis",
                request_data=request_data,
                response_data=response_data,
                duration_ms=duration_ms,
            )

        except Exception as e:
            end_time = time.monotonic()
            duration_ms = int((end_time - start_time) * 1000)

            # Log failed API call
            from ..utils import log_openai_api_call

            log_openai_api_call(
                operation="Content Analysis",
                request_data=request_data,
                error=e,
                duration_ms=duration_ms,
            )
            raise

        # Parse the response
        try:
            content = response.choices[0].message.content
            result = json.loads(content)

            # Validate the structure
            if "voices" not in result or "audio_segments" not in result:
                raise ValueError(
                    "Missing 'voices' or 'audio_segments' in LLM response."
                )
            if not isinstance(result["voices"], list) or not isinstance(
                result["audio_segments"], list
            ):
                raise ValueError("'voices' and 'audio_segments' must be lists.")
            if not result["voices"]:  # Must have at least one voice
                raise ValueError("'voices' list cannot be empty.")
            if not result["audio_segments"]:  # Must have at least one segment
                raise ValueError("'audio_segments' list cannot be empty.")

            # Further validation for each voice and segment can be added here if needed
            # For example, check if all voice_names in audio_segments refer to defined voices.

            return result
        except (json.JSONDecodeError, AttributeError, IndexError, ValueError) as e:
            logger.error(
                f"Error parsing content analysis response or invalid structure: {e}"
            )
            # Log the problematic content
            logger.error(f"LLM Response Content: {content}")
            # Return a default structure
            return {
                "voices": [
                    {
                        "name": "narrator",
                        "tone": "Neutral, standard narration",
                        "tts_model": "alloy",
                        "tts_speed": 1.0,
                    }
                ],
                "audio_segments": [
                    {
                        "text": text,  # Use the original full text for the default segment
                        "voice_name": "narrator",
                    }
                ],
            }

    def _create_analysis_prompt(self, text, title):
        """Create the prompt for multi-voice content analysis."""
        title_context = f" for the article titled '{title}'" if title else ""
        return f"""
        Analyze the following text{title_context}. Your goal is to segment the text for narration using multiple voices where appropriate.

        Instructions:

        1.  **Identify Voice Opportunities:** Read through the text and identify distinct parts that would benefit from different voices. This could be:
            *   Narration vs. direct quotations.
            *   Different characters speaking.
            *   Shifts in tone or style (e.g., a formal introduction followed by a personal anecdote).

        2.  **Define Voices:** For each distinct voice you identify, create a voice definition. Each voice definition must include:
            *   `name`: A unique string identifier for the voice (e.g., "narrator", "expert_quote", "character_jane", "historical_figure"). Use descriptive names.
            *   `tone`: A brief description of the voice's character (e.g., "Clear and neutral, like an NPR reporter", "Authoritative and academic", "Energetic and youthful", "Warm and conversational").
            *   `tts_model`: Recommend one of the following TTS voice models: "alloy", "echo", "fable", "onyx", "nova", "shimmer".
            *   `tts_speed`: Recommend a speaking speed as a float between 0.75 (slower) and 1.5 (faster).

        3.  **Segment Text:** Divide the entire input text into `audio_segments`. Each segment must have:
            *   `text`: The actual text content for that segment.
            *   `voice_name`: The `name` of the voice (from your defined voices list) that should read this segment.
            *   Ensure that the concatenation of all `text` fields in `audio_segments` exactly matches the original input text.

        4.  **Output JSON:** Structure your entire analysis as a single JSON object with two main keys: "voices" and "audio_segments", following the format below.

        JSON Output Structure:
        {{
          "voices": [
            {{
              "name": "string (unique identifier for the voice)",
              "tone": "string (descriptive tone, e.g., 'Like an NPR reporter')",
              "tts_model": "string (e.g., 'alloy', 'onyx')",
              "tts_speed": "float (e.g., 1.0, 1.2)"
            }}
            // ... more voice definitions if needed
          ],
          "audio_segments": [
            {{
              "text": "string (the text segment)",
              "voice_name": "string (name of the voice to use from the 'voices' list)"
            }}
            // ... more text segments
          ]
        }}

        Examples:

        **Example 1: Article with Quotes (e.g., Harvard Business Review style)**

        Input Text:
        "The study, published in the Journal of Applied Psychology, found that employees who engaged in regular microbreaks reported higher levels of job satisfaction. 'Microbreaks are not about slacking off,' explains Dr. Emily Carter, the lead researcher, 'they are essential for maintaining focus and energy throughout the day.' The implications for businesses are significant, suggesting that fostering a culture that encourages short, frequent breaks could lead to a more productive workforce."

        Expected JSON Output:
        {{
          "voices": [
            {{
              "name": "narrator",
              "tone": "Clear and informative, like a documentary narrator",
              "tts_model": "nova",
              "tts_speed": 1.0
            }},
            {{
              "name": "dr_carter",
              "tone": "Authoritative and expert, slightly academic",
              "tts_model": "onyx",
              "tts_speed": 0.95
            }}
          ],
          "audio_segments": [
            {{
              "text": "The study, published in the Journal of Applied Psychology, found that employees who engaged in regular microbreaks reported higher levels of job satisfaction. ",
              "voice_name": "narrator"
            }},
            {{
              "text": "'Microbreaks are not about slacking off,' explains Dr. Emily Carter, the lead researcher, 'they are essential for maintaining focus and energy throughout the day.' ",
              "voice_name": "dr_carter"
            }},
            {{
              "text": "The implications for businesses are significant, suggesting that fostering a culture that encourages short, frequent breaks could lead to a more productive workforce.",
              "voice_name": "narrator"
            }}
          ]
        }}

        **Example 2: Narrative with Dialogue (e.g., Mark Twain snippet)**

        Input Text:
        "'TOM!' No answer. 'TOM!' No answer. 'What's gone with that boy, I wonder? You TOM!' No answer. The old lady pulled her spectacles down and looked over them about the room; then she put them up and looked out under them. She seldom or never looked THROUGH them for so small a thing as a boy; they were her state pair, the pride of her heart, and were built for 'style,' not service—she could have seen through a pair of stove-lids just as well. She looked perplexed for a moment, and then said, not fiercely, but still loud enough for the furniture to hear: 'Well, I lay if I get hold of you I'll—' She did not finish, for by this time she was bending down and punching under the bed with the broom."

        Expected JSON Output:
        {{
          "voices": [
            {{
              "name": "narrator",
              "tone": "Classic storyteller, slightly amused",
              "tts_model": "fable",
              "tts_speed": 1.1
            }},
            {{
              "name": "aunt_polly",
              "tone": "Elderly, a bit flustered but stern",
              "tts_model": "shimmer",
              "tts_speed": 0.9
            }}
          ],
          "audio_segments": [
            {{
              "text": "'TOM!' ",
              "voice_name": "aunt_polly"
            }},
            {{
              "text": "No answer. ",
              "voice_name": "narrator"
            }},
            {{
              "text": "'TOM!' ",
              "voice_name": "aunt_polly"
            }},
            {{
              "text": "No answer. ",
              "voice_name": "narrator"
            }},
            {{
              "text": "'What's gone with that boy, I wonder? You TOM!' ",
              "voice_name": "aunt_polly"
            }},
            {{
              "text": "No answer. The old lady pulled her spectacles down and looked over them about the room; then she put them up and looked out under them. She seldom or never looked THROUGH them for so small a thing as a boy; they were her state pair, the pride of her heart, and were built for 'style,' not service—she could have seen through a pair of stove-lids just as well. She looked perplexed for a moment, and then said, not fiercely, but still loud enough for the furniture to hear: ",
              "voice_name": "narrator"
            }},
            {{
              "text": "'Well, I lay if I get hold of you I'll—' ",
              "voice_name": "aunt_polly"
            }},
            {{
              "text": "She did not finish, for by this time she was bending down and punching under the bed with the broom.",
              "voice_name": "narrator"
            }}
          ]
        }}

        **Edge Case: Short or Monotone Text**
        If the text is very short or does not have clear distinctions for multiple voices, define a single "narrator" voice and include the entire text as one segment.

        **Consistency** of Voices**: Ensure that the same voice is used consistently for the same type of content throughout the text. For example, if you define a "narrator" voice, use it for all general narration segments. For news articles, think about how it would sound on the radio or in a podcast.

        Quotes and Dialogue**: For direct quotes or dialogue, create distinct voices that match the character or speaker's tone. Use descriptive names like "expert_quote" or "character_jane" to differentiate them. For quotes longer than a few words, switch between the narrator and the quoted speaker's voice.

        Example:
        "Jim is the smartest character in the book. It's a mistake to assume he's there to be ridiculed. In fact, he becomes a father to Huck," says Fishkin, who wrote the 1993 literature critic classic.

        This should be segmented as:
        [{{"text":"Jim is the smartest character in the book. It's a mistake to assume he's there to be ridiculed. In fact, he becomes a father to Huck,", "voice_name":"expert_quote"}},
        {{"text":" says Fishkin, who wrote the 1993 literature critic classic.", "voice_name":"narrator"}}]

        Article Text to Analyze:
        {text}
        """

    def _get_analysis_model(self):
        """Get the model to use for content analysis."""
        from django.conf import settings

        return getattr(settings, "OPENAI_ANALYSIS_MODEL", "gpt-4.1")
