"""Service for analyzing article content."""

import json
import logging

# Maximum number of words to analyze with large context LLM models
MAX_ANALYSIS_WORDS = 750_000

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

    def analyze_content(self, text, title=None, max_completion_tokens=500):
        """
        Analyze article content to detect tone and generate summary.

        Args:
            text: The article text to analyze
            title: Optional article title for context
            max_completion_tokens: Maximum tokens for the response

        Returns:
            dict with keys:
                - tone: Detected tone of the article
                - summary: Generated summary
                - voice_recommendation: Recommended voice settings
        """
        # Use up to MAX_ANALYSIS_WORDS words for analysis to leverage GPT-4.1's large context
        words = text.split()
        text_sample = " ".join(words[:MAX_ANALYSIS_WORDS])

        # Create the unified prompt
        prompt = self._create_analysis_prompt(text_sample, title)

        # Call OpenAI API with JSON mode
        response = self.client.chat.completions.create(
            model=self._get_analysis_model(),
            messages=[
                {"role": "system", "content": "You are an expert content analyzer."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=max_completion_tokens,
            temperature=0.3,
            response_format={"type": "json_object"},
        )

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

        Article Text to Analyze:
        {text}
        """

    def _get_analysis_model(self):
        """Get the model to use for content analysis."""
        from django.conf import settings

        return getattr(settings, "OPENAI_ANALYSIS_MODEL", "gpt-4.1")
