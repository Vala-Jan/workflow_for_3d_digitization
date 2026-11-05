@echo off
REM Verify SHA-256 checksums of all packages in master
cd /d "%~dp0"

REM Find Python: first the "py" launcher, then "python" (skips the Microsoft Store alias)
set PY=
py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY python -c "import sys" >nul 2>nul && set PY=python
if not defined PY (
  echo.
  echo Python was not found.
  echo Install Python from https://www.python.org and tick "Add Python to PATH",
  echo or disable the "python.exe" App execution alias in Windows settings.
  echo.
  pause
  exit /b 1
)

%PY% dig3d.py verify
pause
