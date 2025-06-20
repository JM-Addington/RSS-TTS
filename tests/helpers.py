import json
from types import SimpleNamespace


def make_chat_completion(content="{}", *, model="gpt-4o"):
    """Return a minimal object that looks like openai.chat.completions response."""
    if isinstance(content, dict):
        content = json.dumps(content)
    message = SimpleNamespace(content=content, role="assistant")
    choice = SimpleNamespace(message=message, finish_reason="stop", index=0)
    usage = SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    return SimpleNamespace(
        id="chatcmpl-test",
        model=model,
        object="chat.completion",
        created=0,
        choices=[choice],
        usage=usage,
    )
