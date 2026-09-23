@echo off
cd /d "%~dp0"
title Quantum Trading
python launch.py
if errorlevel 1 pause
