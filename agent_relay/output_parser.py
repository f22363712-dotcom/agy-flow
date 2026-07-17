"""Agent Output Contract Parser v1.

Extracts a structured ``parsed_output`` dict from free-text agent output
by locating a `` ```json `` fenced code block.  The parser never raises an
exception; anything that cannot be parsed returns a safe fallback.
"""

import json
import re


_DEFAULT_OUTPUT = {
    "status": "unknown",
    "summary": "",
    "changes": [],
    "files_touched": [],
    "tests_run": [],
    "risks": [],
    "next_action": "manual",
}


def _find_json_block(text):
    """Return the content inside the first ```json ... ``` block, or None."""
    # Match ```json optionally preceded by whitespace, capture everything
    # until ```
    m = re.search(
        r"```json\s*\n(.*?)\n\s*```",
        text,
        re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    return None


def _first_chars(text, n=200):
    """Return the first *n* non-whitespace characters of *text*."""
    stripped = text.strip()
    if not stripped:
        return ""
    return stripped[:n]


def _normalize(raw, parse_error=None):
    """Merge *raw* JSON dict with defaults, fill missing fields."""
    result = dict(_DEFAULT_OUTPUT)
    if parse_error:
        result["parse_error"] = parse_error

    if not isinstance(raw, dict):
        return result

    # status
    valid_statuses = {"completed", "needs_review", "blocked", "failed", "unknown"}
    raw_status = raw.get("status", "unknown")
    if isinstance(raw_status, str) and raw_status in valid_statuses:
        result["status"] = raw_status

    # summary
    raw_summary = raw.get("summary")
    if isinstance(raw_summary, str):
        result["summary"] = raw_summary

    # string list fields
    for list_field in ("changes", "files_touched", "tests_run", "risks"):
        raw_val = raw.get(list_field)
        if isinstance(raw_val, list):
            result[list_field] = [str(v) for v in raw_val]

    # next_action
    valid_actions = {"review", "revise", "submit", "manual", "none"}
    raw_action = raw.get("next_action", "manual")
    if isinstance(raw_action, str) and raw_action in valid_actions:
        result["next_action"] = raw_action

    return result


def parse_agent_output(text):
    """Parse *text* (agent stdout/response) into a structured dict.

    Returns
    -------
    dict with keys: ``status``, ``summary``, ``changes``, ``files_touched``,
    ``tests_run``, ``risks``, ``next_action``, and optionally ``parse_error``.
    """
    if not text or not isinstance(text, str):
        return dict(_DEFAULT_OUTPUT, parse_error="Empty or non-string output")

    block = _find_json_block(text)
    if block is None:
        fallback = dict(_DEFAULT_OUTPUT)
        fallback["summary"] = _first_chars(text, 200)
        fallback["parse_error"] = "No valid JSON block found"
        return fallback

    parsed = None
    try:
        parsed = json.loads(block)
    except json.JSONDecodeError as e:
        fallback = dict(_DEFAULT_OUTPUT)
        fallback["summary"] = _first_chars(text, 200)
        fallback["parse_error"] = f"JSON decode error: {e}"
        return fallback

    # Validate it's a dict
    if not isinstance(parsed, dict):
        fallback = dict(_DEFAULT_OUTPUT)
        fallback["summary"] = _first_chars(text, 200)
        fallback["parse_error"] = "JSON block is not a dictionary"
        return fallback

    return _normalize(parsed)
