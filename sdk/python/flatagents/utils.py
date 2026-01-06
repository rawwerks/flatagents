"""Utility functions for flatagents."""

import re


def strip_markdown_json(content: str) -> str:
    """
    Strip markdown code block fences from JSON content.

    LLMs sometimes wrap JSON responses in markdown code blocks like:
    ```json
    {"key": "value"}
    ```

    This function removes those fences so json.loads() can parse the content.

    Args:
        content: Raw string that may contain markdown-wrapped JSON

    Returns:
        Cleaned string with markdown fences removed
    """
    if not content:
        return content

    text = content.strip()

    # Pattern to match ```json or ```JSON or just ``` at start
    # and ``` at end, capturing the content in between
    pattern = r'^```(?:json|JSON)?\s*\n?(.*?)\n?```$'
    match = re.match(pattern, text, re.DOTALL)

    if match:
        return match.group(1).strip()

    return text
