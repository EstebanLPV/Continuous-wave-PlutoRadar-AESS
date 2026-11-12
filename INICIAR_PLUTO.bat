@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta instalar PlutoRadar. Ejecuta INSTALAR_WINDOWS.bat primero.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" comprobar_entorno.py
if errorlevel 1 (
  echo.
  echo El entorno no esta listo. Ejecuta REPARAR_ENTORNO.bat.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" native_app.py
if errorlevel 1 (
  echo.
  echo Error al iniciar PlutoRadar. Revisa el mensaje anterior.
  pause
)
