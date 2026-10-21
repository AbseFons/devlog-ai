@echo off
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
REM El programa espera de 20:00 a 03:00, revisa cada 15 min y preserva 7 días de catchup.
REM Gaming Safe no ejecuta Qwen si detecta PC activa, juegos o GPU con poca VRAM.
python devlog.py safe-run --days 7 --interval-minutes 15 --max-wait-minutes 420 >> "logs\devlog.log" 2>&1
exit /b %errorlevel%
