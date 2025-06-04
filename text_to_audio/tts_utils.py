"""Shared TTS utilities for tasks and parallel processing."""

import logging

logger = logging.getLogger(__name__)


def _clamp_tts_speed(speed: float) -> float:
    """Clamp TTS speed to valid range [0.25, 4.0].

    Args:
        speed: The desired TTS speed

    Returns:
        Speed clamped to valid range
    """
    return max(0.25, min(speed, 4.0))


def _configure_model_aware_speed(tts_model, speed, instructions=""):
    """
    Configure speed parameter based on TTS model capabilities.

    For gpt-4o-mini-tts: Speed is controlled via instructions parameter.
    For tts-1 and tts-1-hd: Speed is controlled via direct speed parameter.

    Args:
        tts_model: The TTS model being used
        speed: The desired speed multiplier
        instructions: Existing instructions text

    Returns:
        Tuple of (tts_request_updates, final_instructions)
        where tts_request_updates is a dict to merge into the TTS request
    """
    # Clamp speed to valid range
    clamped_speed = _clamp_tts_speed(speed)

    if tts_model.startswith("gpt-4o"):
        # For gpt-4o models, use instructions for speed control
        speed_instruction = f"Speak at {clamped_speed}x speed."
        if instructions:
            final_instructions = f"{instructions} {speed_instruction}"
        else:
            final_instructions = speed_instruction

        # Do not include the speed parameter for gpt-4o models
        return {}, final_instructions
    else:
        # For tts-1 and tts-1-hd models, use direct speed parameter
        return {"speed": clamped_speed}, instructions


def _legacy_chunk_text(text: str, max_length: int = 4000) -> tuple[bool, list[str]]:
    """Split text into chunks for TTS processing (optimized for large texts).

    Uses a linear scanning approach for better performance on large documents.
    Prioritizes natural breaks in this order:
    1. Line breaks (\n)
    2. Sentence boundaries (. ! ?)
    3. Clause boundaries (; ,)
    4. Word boundaries (spaces)
    5. Force splits within words as last resort

    Returns:
        tuple: (success, chunks)
            - success (bool): True if all splits were at natural boundaries
            - chunks (list): List of text chunks, each <= max_length
    """
    logger.debug(
        f"_chunk_text called with text of len {len(text)} and max_length {max_length}"
    )

    if not text:
        return True, []

    if len(text) <= max_length:
        return True, [text]

    chunks = []
    perfect_split = True
    current_chunk = ""

    # Define break characters in priority order
    sentence_breaks = {".", "!", "?"}

    i = 0
    text_len = len(text)

    while i < text_len:
        char = text[i]

        # Check if adding this character would exceed max_length
        if len(current_chunk) + 1 > max_length:
            # We need to break here, find the best break point in current_chunk
            if current_chunk:
                break_point = _legacy_find_best_break_point(current_chunk, max_length)
                if break_point > 0:
                    chunks.append(current_chunk[:break_point].strip())
                    current_chunk = current_chunk[break_point:].strip()
                    if current_chunk and len(current_chunk) > max_length:
                        # Still too long, force split
                        perfect_split = False
                        chunks.append(current_chunk[:max_length])
                        current_chunk = current_chunk[max_length:]
                else:
                    # No good break point found, force split
                    perfect_split = False
                    chunks.append(current_chunk[:max_length])
                    current_chunk = current_chunk[max_length:]
            # Check if we can now add the current character after splitting
            if len(current_chunk) + 1 <= max_length:
                # We can now add the character, fall through to normal processing
                pass
            else:
                # Still can't add the character, skip it and move to next
                # This prevents the infinite loop by ensuring i is incremented
                i += 1
                continue

        # Add character to current chunk
        current_chunk += char

        # Check for natural break opportunities
        if char == "\n":
            # Line break - highest priority
            chunks.append(current_chunk.strip())
            current_chunk = ""
        elif char in sentence_breaks and i + 1 < text_len and text[i + 1].isspace():
            # Sentence break followed by space
            current_chunk += text[i + 1]  # Include the space
            chunks.append(current_chunk.strip())
            current_chunk = ""
            i += 1  # Skip the space we just added

        i += 1

    # Add any remaining chunk
    if current_chunk.strip():
        if len(current_chunk) > max_length:
            # Need to split the remaining chunk
            remaining = current_chunk.strip()
            while remaining:
                if len(remaining) <= max_length:
                    chunks.append(remaining)
                    break

                break_point = _legacy_find_best_break_point(remaining, max_length)
                if break_point > 0:
                    chunks.append(remaining[:break_point].strip())
                    remaining = remaining[break_point:].strip()
                else:
                    # Force split
                    perfect_split = False
                    chunks.append(remaining[:max_length])
                    remaining = remaining[max_length:]
        else:
            chunks.append(current_chunk.strip())

    # Filter out empty chunks
    chunks = [chunk for chunk in chunks if chunk]

    return perfect_split, chunks


def _legacy_find_best_break_point(text: str, max_length: int) -> int:
    """Find the best break point within a text segment.

    Returns the index where to break, or 0 if no good break point found.
    """
    if len(text) <= max_length:
        return len(text)

    # Search backwards from max_length for break opportunities
    search_text = text[:max_length]

    # Priority 1: Sentence breaks with space after
    for i in range(len(search_text) - 2, -1, -1):
        if search_text[i] in {".", "!", "?"} and search_text[i + 1].isspace():
            return i + 2  # Include the punctuation and space

    # Priority 2: Clause breaks with space after
    for i in range(len(search_text) - 2, -1, -1):
        if search_text[i] in {";", ","} and search_text[i + 1].isspace():
            return i + 2

    # Priority 3: Word boundaries (spaces)
    for i in range(len(search_text) - 1, -1, -1):
        if search_text[i].isspace():
            return i + 1

    # No good break point found
    return 0
