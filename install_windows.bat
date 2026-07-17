@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

where py >nul 2>nul
if errorlevel 1 (
    echo Python no encontrado.
    echo Instala Python 3.9+ desde https://www.python.org/downloads/windows/
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo Creando entorno virtual...
    py -3 -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

echo.
echo Instalacion completada.
echo.
echo El proyecto funciona sin dependencias externas.
echo Para iniciar el programa ejecuta:
echo   start_windows.bat --help
echo.

endlocal
