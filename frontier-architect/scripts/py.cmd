@echo off
rem Launcher: run a script with the first Python 3.10+ found (py -3, python3, python).
rem Usage: py.cmd <script.py> [args...]
set "CHK=import sys; sys.exit(sys.version_info < (3, 10))"
py -3 -c "%CHK%" >nul 2>&1
if not errorlevel 1 ( py -3 %* & exit /b %errorlevel% )
python3 -c "%CHK%" >nul 2>&1
if not errorlevel 1 ( python3 %* & exit /b %errorlevel% )
python -c "%CHK%" >nul 2>&1
if not errorlevel 1 ( python %* & exit /b %errorlevel% )
echo py.cmd: no Python 3.10+ found (tried py -3, python3, python) 1>&2
exit /b 127
