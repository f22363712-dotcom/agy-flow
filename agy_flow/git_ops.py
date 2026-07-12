import subprocess
from agy_flow.config import PROJECT_ROOT

def run_cmd(cmd, cwd=None):
    """Executes a command and returns the exit code, stdout, and stderr."""
    run_cwd = cwd or str(PROJECT_ROOT)
    print(f"Executing: {' '.join(cmd)} in {run_cwd}")
    res = subprocess.run(cmd, cwd=run_cwd, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()
