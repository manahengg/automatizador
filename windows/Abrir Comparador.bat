@echo off
rem Abre la app con el Python oficial que va junto a este fichero.
cd /d "%~dp0app"
"%~dp0python\python.exe" "%~dp0app\automatizador\windows\lanzador.py"
if errorlevel 1 pause
