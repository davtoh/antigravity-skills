#!/bin/sh
# Launcher: run a script with the first Python 3.10+ found (python3, python, py -3).
# Usage: sh py.sh <script.py> [args...]   (Windows cmd/PowerShell: py.cmd)
# Needs no Python to start, so it works where bare `python` is Python 2 or python3 is missing.
for cand in python3 python "py -3"; do
  # shellcheck disable=SC2086
  if $cand -c "import sys; sys.exit(sys.version_info < (3, 10))" >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    exec $cand "$@"
  fi
done
echo "py.sh: no Python 3.10+ found (tried python3, python, py -3)" >&2
exit 127
