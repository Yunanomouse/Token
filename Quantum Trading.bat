@echo off
title Quantum Trading
cd /d "%~dp0"
echo Quantum Trading launcher
echo Folder: %cd%
echo.
set PY=
where py >nul 2>nul && py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY ( where python >nul 2>nul && python -c "import sys" >nul 2>nul && set PY=python )
if not defined PY ( where python3 >nul 2>nul && python3 -c "import sys" >nul 2>nul && set PY=python3 )
if not defined PY (
  echo Python was not found on this computer.
  echo.
  echo Install it from https://www.python.org/downloads/windows/
  echo and tick "Add python.exe to PATH" in the installer, then run this again.
  echo.
  echo If you installed Python from the Microsoft Store, open Settings ^> Apps ^>
  echo Advanced app settings ^> App execution aliases and turn on python.exe.
  echo.
  pause
  exit /b 1
)
echo Using: %PY%
%PY% --version
echo.
%PY% launch.py
echo.
echo The dashboard has stopped.
pause
