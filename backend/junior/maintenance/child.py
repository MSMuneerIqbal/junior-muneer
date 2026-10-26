"""Stdlib-only stdin gate: no child code starts until its supervisor owns the process tree."""

import subprocess
import sys

if __name__ == "__main__":
    if sys.stdin.readline().strip() != "junior-go":
        raise SystemExit(125)
    raise SystemExit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL))
