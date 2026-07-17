@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "SYSTEM_PYTHON=python"

if exist "%VENV_PYTHON%" (
    set "PYTHON_EXE=%VENV_PYTHON%"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo No se encontró Python en el sistema.
        echo Instala Python 3.9+ o ejecuta install_windows.bat.
        exit /b 1
    )
    set "PYTHON_EXE=%SYSTEM_PYTHON%"
)

if "%~1"=="" (
    "%PYTHON_EXE%" "%SCRIPT_DIR%secure_file_manager.py" --help
) else (
    "%PYTHON_EXE%" "%SCRIPT_DIR%secure_file_manager.py" %*
)

endlocal
