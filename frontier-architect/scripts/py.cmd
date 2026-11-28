@echo off
setlocal
rem Launcher: run a script with the first Python 3.10+ found (VIRTUAL_ENV, py.exe -3, python, python3).
rem Usage: py.cmd <script.py> [args...]  (PowerShell: & "<skill_dir>/scripts/py.cmd" <script.py> ...)
set "CHK=import sys; sys.exit(sys.version_info < (3, 10))"
if not defined VIRTUAL_ENV goto :try_py
if not exist "%VIRTUAL_ENV%\Scripts\python.exe" goto :try_py
call "%VIRTUAL_ENV%\Scripts\python.exe" -c "%CHK%" >nul 2>&1
if not errorlevel 1 goto :use_venv
:try_py
call py.exe -3 -c "%CHK%" >nul 2>&1
if not errorlevel 1 goto :use_py
call python -c "%CHK%" >nul 2>&1
if not errorlevel 1 goto :use_python
call python3 -c "%CHK%" >nul 2>&1
if not errorlevel 1 goto :use_python3
echo py.cmd: no Python 3.10+ found (tried VIRTUAL_ENV, py -3, python, python3) 1>&2
exit /b 127
:use_venv
"%VIRTUAL_ENV%\Scripts\python.exe" %*
exit /b %errorlevel%
:use_py
py.exe -3 %*
exit /b %errorlevel%
:use_python
python %*
exit /b %errorlevel%
:use_python3
python3 %*
exit /b %errorlevel%
