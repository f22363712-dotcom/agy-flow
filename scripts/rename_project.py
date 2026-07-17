"""Batch rename agent-relay → agent-relay across the entire codebase.

Replacement rules:
  agent_relay  → agent_relay   (Python package, imports, paths)
  agent-relay  → agent-relay   (CLI command, project name)
  AgentRelay   → AgentRelay    (CamelCase in TS/React/display names)
  agent relay  → agent relay   (text references)
  agent-relay-mcp → agent-relay-mcp (MCP server name)
"""

import os
import shutil

PROJECT = r"D:\multi_agent_collaboration"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}
SKIP_FILES = {
    "package-lock.json",
    "package.json",
}

# ── File extension filter ──
TEXT_EXTS = {
    ".py",
    ".md",
    ".json",
    ".toml",
    ".html",
    ".css",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

# ── Replacement pairs (order matters: longer first) ──
REPLACEMENTS = [
    ("agent_relay", "agent_relay"),
    ("agent-relay", "agent-relay"),
    ("AgentRelay", "AgentRelay"),
    ("agent relay", "agent relay"),
]

# ── Phase 1: Text replacements in files ──
print("=" * 60)
print("Phase 1: Text replacements in source files")
print("=" * 60)

changed = 0
total = 0
for root, dirs, files in os.walk(PROJECT):
    # Skip unwanted dirs
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    rel_root = os.path.relpath(root, PROJECT)
    if any(skip in rel_root.split(os.sep) for skip in SKIP_DIRS):
        continue

    for fname in files:
        if fname in SKIP_FILES:
            continue
        ext = os.path.splitext(fname)[1].lower()
        if ext not in TEXT_EXTS:
            continue

        fpath = os.path.join(root, fname)
        total += 1

        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        new_content = content
        for old, new in REPLACEMENTS:
            new_content = new_content.replace(old, new)

        if new_content != content:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_content)
            changed += 1
            print(f"  ✏️  {os.path.relpath(fpath, PROJECT)}")

print(f"\nFiles scanned: {total}, files modified: {changed}")

# ── Phase 2: Rename files ──
print("\n" + "=" * 60)
print("Phase 2: Rename files and directories")
print("=" * 60)

# Rename agent-relay.py → agent-relay.py
old_cli = os.path.join(PROJECT, "agent-relay.py")
new_cli = os.path.join(PROJECT, "agent-relay.py")
if os.path.exists(old_cli):
    # Read and update internal references in the file first
    with open(old_cli, "r", encoding="utf-8") as f:
        cli_content = f.read()
    for old, new in REPLACEMENTS:
        cli_content = cli_content.replace(old, new)
    with open(new_cli, "w", encoding="utf-8") as f:
        f.write(cli_content)
    os.remove(old_cli)
    print(f"  📦 {old_cli} → {new_cli}")

# Rename docs/value-trials files that contain agy
trials_dir = os.path.join(PROJECT, "docs", "value-trials")
if os.path.isdir(trials_dir):
    for fname in os.listdir(trials_dir):
        if "agy" in fname.lower():
            old_path = os.path.join(trials_dir, fname)
            new_name = fname.replace(
                "x-cost", "x-cost"
            )  # no-op, agy not in these names
            # Actually these files are named x-cost-metadata etc., not agy
            pass

# Rename agent_relay/ → agent_relay/
old_pkg = os.path.join(PROJECT, "agent_relay")
new_pkg = os.path.join(PROJECT, "agent_relay")
if os.path.isdir(old_pkg):
    shutil.move(old_pkg, new_pkg)
    print(f"  📦 {old_pkg} → {new_pkg}")

# Rename history.md (agent-relay-history.md)
for base in ["agent-relay-history.md"]:
    old_path = os.path.join(PROJECT, base)
    if os.path.exists(old_path):
        new_path = os.path.join(PROJECT, base.replace("agent-relay", "agent-relay"))
        shutil.move(old_path, new_path)
        print(f"  📦 {base} → {os.path.basename(new_path)}")

print("\n✅ Rename complete!")
print("\n⚠️  Reminder: pyproject.toml needs manual update for package name/entry point.")
