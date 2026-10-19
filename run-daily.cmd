@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
python devlog.py catchup --days 7 >> "logs\devlog.log" 2>&1
exit /b %errorlevel%
