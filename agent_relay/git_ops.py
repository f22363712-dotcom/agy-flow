import subprocess
import sys
from agent_relay.config import PROJECT_ROOT


def run_cmd(cmd, cwd=None):
    """Executes a command and returns the exit code, stdout, and stderr."""
    run_cwd = cwd or str(PROJECT_ROOT)
    # Log to stderr so JSON-RPC stdout protocol is never polluted
    print(f"Executing: {' '.join(cmd)} in {run_cwd}", file=sys.stderr, flush=True)
    res = subprocess.run(cmd, cwd=run_cwd, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()
