"""Utility functions for flatagents."""

import re


def strip_markdown_json(content: str) -> str:
    """
    Extract JSON from potentially wrapped response content.

    LLMs sometimes wrap JSON responses in markdown code blocks like:
    ```json
    {"key": "value"}
    ```

    Or include explanatory text before/after the JSON:
    "Here is the result:
    ```json
    {"key": "value"}
    ```"

    This function extracts the JSON so json.loads() can parse it.

    Args:
        content: Raw string that may contain markdown-wrapped JSON

    Returns:
        Extracted JSON string
    """
    if not content:
        return content

    text = content.strip()

    # First, try to find JSON in a markdown code fence (anywhere in content)
    fence_pattern = r'```(?:json|JSON)?\s*\n?([\s\S]*?)\n?```'
    match = re.search(fence_pattern, text)
    if match:
        return match.group(1).strip()

    # If no fence, try to find a raw JSON object or array
    json_pattern = r'(\{[\s\S]*\}|\[[\s\S]*\])'
    match = re.search(json_pattern, text)
    if match:
        return match.group(1)

    return text
