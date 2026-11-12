@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Primero ejecuta INSTALAR_WINDOWS.bat.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" diagnostico_zmq.py
pause
