@echo off
setlocal
cd /d "%~dp0"
echo Esta accion eliminara SOLO el entorno virtual .venv del proyecto.
echo NO elimina el codigo ni la configuracion ni el proyecto de GNU Radio.
choice /C SN /M "Deseas reconstruir el entorno de Python"
if errorlevel 2 exit /b 0
if exist ".venv" rmdir /s /q ".venv"
if exist ".venv" (
  echo No se pudo borrar .venv. Cierra PlutoRadar y prueba otra vez.
  pause
  exit /b 1
)
call INSTALAR_WINDOWS.bat
