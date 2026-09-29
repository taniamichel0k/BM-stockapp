@echo off
title Control de Stock BM
cd /d "%~dp0"

echo ===================================================
echo       INICIANDO CONTROL DE STOCK BM
echo ===================================================
echo.
echo Iniciando aplicacion en ventana independiente...

.venv\Scripts\python.exe app_desktop.py
