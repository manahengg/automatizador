@echo off
rem Instala el Comparador de ofertas sin ejecutables propios: usa el python.exe oficial (firmado) que va en esta
rem carpeta para ejecutar app\automatizador\windows\instalar.py (copia, accesos directos). Ver ese fichero.
cd /d "%~dp0"
if not exist "python\python.exe" (
  echo ERROR: no encuentro la carpeta "python" junto a este fichero.
  echo Descomprime el ZIP completo antes de ejecutar Instalar.bat.
  pause
  exit /b 1
)
"python\python.exe" "app\automatizador\windows\instalar.py" %*
if errorlevel 1 (
  pause
  exit /b 1
)
timeout /t 8
