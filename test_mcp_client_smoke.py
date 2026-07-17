"""Tests for scripts/mcp_client_smoke.py — MCP Client Smoke."""

import json
import os
import re
import sys
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
scripts_dir = project_root / "scripts"


class TestMCPClientSmoke(unittest.TestCase):
    def test_smoke_script_exists(self):
        self.assertTrue((scripts_dir / "mcp_client_smoke.py").exists())

    def test_smoke_script_compiles(self):
        import py_compile

        py_compile.compile(str(scripts_dir / "mcp_client_smoke.py"), doraise=True)

    def test_smoke_script_runs_and_passes(self):
        """Run the smoke script and verify overall=pass."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(scripts_dir / "mcp_client_smoke.py")],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(project_root),
        )
        # Extract the JSON report from stdout. It's the last top-level JSON
        # object.
        text = result.stdout
        # Walk backward to find '"overall"'
        idx = text.rfind('"overall"')
        if idx < 0:
            self.fail(f"No 'overall' in output. tail: {text[-500:]}")

        # Walk backward to find the outermost opening '{'
        brace_depth = 0
        report_start = idx
        for i in range(idx, -1, -1):
            if text[i] == "}":
                brace_depth += 1
            elif text[i] == "{":
                brace_depth -= 1
                if brace_depth < 0:
                    report_start = i
                    break

        # Walk forward from idx to find the matching closing '}'
        brace_depth = 0
        report_end = idx
        for i in range(idx, len(text)):
            if text[i] == "{":
                brace_depth += 1
            elif text[i] == "}":
                brace_depth -= 1
                if brace_depth < 0:
                    report_end = i + 1
                    break

        report_text = text[report_start:report_end]
        try:
            report = json.loads(report_text)
        except json.JSONDecodeError as e:
            self.fail(f"JSON parse error: {e}\nText: {report_text[:500]}")

        self.assertEqual(
            report.get("overall"),
            "pass",
            f"Report: {json.dumps(report, indent=2)[:1000]}",
        )
        self.assertGreater(
            len(report.get("steps", [])),
            4,
            f"Too few steps: {json.dumps(report, indent=2)[:500]}",
        )

    def test_smoke_steps_are_meaningful(self):
        """Verify the smoke script exercises multiple MCP tools."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(scripts_dir / "mcp_client_smoke.py")],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(project_root),
        )
        text = result.stdout
        # Count PASS lines as steps
        pass_count = text.count("[PASS]")
        self.assertGreaterEqual(
            pass_count,
            6,
            f"Expected >=6 passed steps, got {pass_count}.\n{text[-500:]}",
        )
        # Must include key tools
        self.assertIn("initialize", text)
        self.assertIn("tools/list", text)
        self.assertIn("agy_doctor", text)


if __name__ == "__main__":
    unittest.main()
