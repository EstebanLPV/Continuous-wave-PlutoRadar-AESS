@echo off
setlocal
cd /d "%~dp0"
title AESS - Instalar PlutoRadar

echo ================================================
echo       AESS / PlutoRadar - Instalacion limpia
echo ================================================
echo.
where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: No se encontro el lanzador de Python 'py'.
  echo Instala Python 3.12 o 3.13 con Tcl/Tk e IDLE habilitado.
  goto error
)

echo [1/4] Verificando Tcl/Tk de Windows...
py -3 -c "import tkinter as tk; root=tk.Tk(); root.withdraw(); root.destroy(); print('Tkinter y Tcl/Tk: OK')"
if errorlevel 1 (
  echo.
  echo ERROR: La instalacion de Python no puede iniciar Tkinter.
  echo Si aparece "Can't find a usable init.tcl":
  echo Abre el instalador oficial de Python, selecciona Modify/Repair
  echo y activa "tcl/tk and IDLE". Luego vuelve a ejecutar este archivo.
  echo El entorno virtual NO puede reparar una instalacion base sin Tcl/Tk.
  goto error
)

echo [2/4] Preparando entorno virtual...
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 goto error
)

echo [3/4] Instalando dependencias...
"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto error
"%~dp0.venv\Scripts\python.exe" -m pip install --no-cache-dir --upgrade --force-reinstall -r requirements.txt
if errorlevel 1 goto error

echo [4/4] Comprobando interfaz y bibliotecas...
"%~dp0.venv\Scripts\python.exe" comprobar_entorno.py
if errorlevel 1 goto error

echo.
echo INSTALACION COMPLETA. Ejecuta INICIAR_PLUTO.bat.
pause
exit /b 0
:error
echo.
echo INSTALACION INCOMPLETA. Revisa el error anterior.
pause
exit /b 1
