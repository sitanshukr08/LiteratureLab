@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.ps1 first.
  pause
  exit /b 1
)
echo LiteratureLab: http://127.0.0.1:8765
echo Leave this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" -m uvicorn literaturelab.api:app --host 127.0.0.1 --port 8765
pause
