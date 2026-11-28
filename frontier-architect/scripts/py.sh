#!/bin/sh
# Launcher: run a script with the first Python 3.10+ found (VIRTUAL_ENV, python3, python, py -3).
# Usage: sh py.sh <script.py> [args...]   (Windows PowerShell: & "<skill_dir>/scripts/py.cmd" ...)
# Needs no Python to start, so it works where bare `python` is Python 2 or python3 is missing.
CHK="import sys; sys.exit(sys.version_info < (3, 10))"
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  if "$VIRTUAL_ENV/bin/python" -c "$CHK" >/dev/null 2>&1; then
    exec "$VIRTUAL_ENV/bin/python" "$@"
  fi
fi
for cand in python3 python "py -3"; do
  # shellcheck disable=SC2086
  if $cand -c "$CHK" >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    exec $cand "$@"
  fi
done
echo "py.sh: no Python 3.10+ found (tried VIRTUAL_ENV, python3, python, py -3)" >&2
exit 127
