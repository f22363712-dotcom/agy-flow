"""Tests for agy_flow/output_parser.py — Agent Output Contract Parser."""

from agy_flow.output_parser import parse_agent_output
import json
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestOutputParser(unittest.TestCase):
    def test_valid_json_block(self):
        text = """Some text before

```json
{
  "status": "completed",
  "summary": "Fixed login bug",
  "changes": ["Updated validation"],
  "files_touched": ["src/login.py"],
  "tests_run": ["pytest test_login.py"],
  "risks": ["OAuth edge case"],
  "next_action": "review"
}
```

Some text after"""
        result = parse_agent_output(text)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"], "Fixed login bug")
        self.assertEqual(result["changes"], ["Updated validation"])
        self.assertEqual(result["files_touched"], ["src/login.py"])
        self.assertEqual(result["tests_run"], ["pytest test_login.py"])
        self.assertEqual(result["risks"], ["OAuth edge case"])
        self.assertEqual(result["next_action"], "review")
        self.assertNotIn("parse_error", result)

    def test_no_json_block_fallback(self):
        text = "Just some plain text output with no JSON block at all."
        result = parse_agent_output(text)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["next_action"], "manual")
        self.assertIn("parse_error", result)
        self.assertIn("No valid JSON block found", result["parse_error"])

    def test_malformed_json_fallback(self):
        text = """Some text

```json
{this is not valid json}
```"""
        result = parse_agent_output(text)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["next_action"], "manual")
        self.assertIn("parse_error", result)
        self.assertIn("JSON decode error", result["parse_error"])

    def test_json_not_dict_fallback(self):
        text = """Result

```json
[1, 2, 3]
```"""
        result = parse_agent_output(text)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("not a dictionary", result.get("parse_error", ""))

    def test_empty_text(self):
        result = parse_agent_output("")
        self.assertEqual(result["status"], "unknown")
        self.assertIn("parse_error", result)

    def test_non_string_input(self):
        result = parse_agent_output(None)
        self.assertEqual(result["status"], "unknown")
        self.assertIn("parse_error", result)

    def test_missing_fields_filled_with_defaults(self):
        text = """```json
{"status": "completed"}
```"""
        result = parse_agent_output(text)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"], "")
        self.assertEqual(result["changes"], [])
        self.assertEqual(result["files_touched"], [])
        self.assertEqual(result["tests_run"], [])
        self.assertEqual(result["risks"], [])
        self.assertEqual(result["next_action"], "manual")
        self.assertNotIn("parse_error", result)

    def test_invalid_status_replaced(self):
        text = """```json
{"status": "nonexistent_status"}
```"""
        result = parse_agent_output(text)
        self.assertEqual(result["status"], "unknown")

    def test_invalid_next_action_replaced(self):
        text = """```json
{"next_action": "fly_to_mars"}
```"""
        result = parse_agent_output(text)
        self.assertEqual(result["next_action"], "manual")

    def test_multiple_blocks_uses_first_json(self):
        text = """First block
```json
{"status": "completed", "summary": "First"}
```
Second block
```json
{"status": "blocked", "summary": "Second"}
```"""
        result = parse_agent_output(text)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["summary"], "First")

    def test_parser_never_raises(self):
        """parse_agent_output must never raise an exception."""
        inputs = [
            None,
            "",
            "plain text",
            "```json\n{{{```",
            "```json\n[]```",
            123,
            {"not": "string"},
        ]
        for inp in inputs:
            try:
                result = parse_agent_output(inp)
                self.assertIsInstance(result, dict)
            except Exception as e:
                self.fail(f"Parser raised {e} for input {inp!r}")


if __name__ == "__main__":
    unittest.main()
