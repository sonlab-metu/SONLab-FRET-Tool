@echo off

:: =============================================================
:: SONLab FRET Tool Windows Installer
:: =============================================================

:: Get directory of this script (adds trailing backslash)
set "SCRIPT_DIR=%~dp0"
:: Remove trailing backslash for convenience in some operations
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: PROJECT_ROOT is one level above installers\
for %%i in ("%SCRIPT_DIR%\..") do set "PROJECT_ROOT=%%~fi"

:: -------------------------------------------------------------
:: 1. Check Python installation (>= 3.8)
:: -------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.^
 Please install Python 3.8 or later from https://www.python.org/downloads/windows/ and re-run this script.
    goto :EOF
)

python -c "import sys,sysconfig,platform,os; sys.exit(0 if sys.version_info>=(3,8) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Detected Python version is lower than 3.8.^
 Please install Python 3.8 or newer and re-run this script.
    goto :EOF
)

:: -------------------------------------------------------------
:: 2. Ask for installation directory
:: -------------------------------------------------------------
set "DEFAULT_INSTALL=%USERPROFILE%\SONLab_FRET_Tool"echo.
echo Where would you like to install SONLab FRET Tool?
echo Press ENTER to accept the default location: %DEFAULT_INSTALL%
set /p INSTALL_DIR=Installation directory: 
if "%INSTALL_DIR%"=="" set "INSTALL_DIR=%DEFAULT_INSTALL%"

:: Create directory (including parents)
if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
    if errorlevel 1 (
        echo Failed to create directory "%INSTALL_DIR%". Check permissions or path and try again.
        goto :EOF
    )
)

:: Warn if directory is not empty
dir /b "%INSTALL_DIR%" 2>nul | findstr . >nul
if not errorlevel 1 (
    echo.
    echo WARNING: The directory "%INSTALL_DIR%" is not empty.
    set /p CONTINUE=Continue installation anyway? (y/N): 
    if /I not "%CONTINUE%"=="Y" (
        goto :EOF
    )
)

:: -------------------------------------------------------------
:: 3. Create Python virtual environment
:: -------------------------------------------------------------
python -m venv "%INSTALL_DIR%\venv"
if errorlevel 1 (
    echo Failed to create virtual environment. Ensure the ^"venv^" module is installed.
    goto :EOF
)

set "PIP=%INSTALL_DIR%\venv\Scripts\pip.exe"
set "PYTHON=%INSTALL_DIR%\venv\Scripts\python.exe"

:: Upgrade pip and install base requirements
echo Installing Python dependencies...
"%PIP%" install --upgrade pip
"%PIP%" install -r "%SCRIPT_DIR%\requirements.txt"

:: -------------------------------------------------------------
:: 4. Install PyTorch
:: -------------------------------------------------------------
echo.
echo Select your compute platform for PyTorch:
echo 1 ^) CUDA 11.8  ‑ NVIDIA GPUs with CUDA 11.8
echo 2 ^) CUDA 12.6  ‑ NVIDIA GPUs with CUDA 12.6
echo 3 ^) CUDA 12.8  ‑ NVIDIA GPUs with CUDA 12.8
echo 4 ^) ROCm 6.3   ‑ AMD GPUs with ROCm 6.3
echo 5 ^) CPU only   ‑ no GPU acceleration
choice /c 12345 /n /m "Enter your choice (1-5): "
set "CHOICE=%errorlevel%"

if "%CHOICE%"=="1" (
    echo Installing PyTorch (CUDA 11.8)...
    "%PIP%" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
) else if "%CHOICE%"=="2" (
    echo Installing PyTorch (CUDA 12.6)...
    "%PIP%" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
) else if "%CHOICE%"=="3" (
    echo Installing PyTorch (CUDA 12.8)...
    "%PIP%" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
) else if "%CHOICE%"=="4" (
    echo Installing PyTorch (ROCm 6.3)...
    "%PIP%" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3
) else (
    echo Installing CPU-only PyTorch...
    "%PIP%" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
)

:: -------------------------------------------------------------
:: 5. Copy application files
:: -------------------------------------------------------------
echo Setting up application files...
mkdir "%INSTALL_DIR%\app" >nul 2>&1
mkdir "%INSTALL_DIR%\app\icons" >nul 2>&1
mkdir "%INSTALL_DIR%\app\luts" >nul 2>&1

:: Copy Python files
xcopy "%PROJECT_ROOT%\*.py" "%INSTALL_DIR%\app\" /Y /I /Q >nul

:: Copy icons
if exist "%PROJECT_ROOT%\icon.png" xcopy "%PROJECT_ROOT%\icon.png" "%INSTALL_DIR%\app\icons\" /Y /I /Q >nul
if exist "%PROJECT_ROOT%\logo.png" xcopy "%PROJECT_ROOT%\logo.png" "%INSTALL_DIR%\app\icons\" /Y /I /Q >nul

:: Copy LUT files
xcopy "%PROJECT_ROOT%\*.lut" "%INSTALL_DIR%\app\luts\" /Y /I /Q >nul

:: Copy JSON config files (optional)
xcopy "%PROJECT_ROOT%\*.json" "%INSTALL_DIR%\app\" /Y /I /Q >nul 2>&1

:: -------------------------------------------------------------
:: 6. Create launcher batch file
:: -------------------------------------------------------------
(
 echo @echo off
 echo set "SCRIPT_DIR=%%~dp0"
 echo if "%%SCRIPT_DIR:~-1%%"=="\\" set "SCRIPT_DIR=%%SCRIPT_DIR:~0,-1%%"
 echo set "PYTHONPATH=%%SCRIPT_DIR%%\app"
 echo "%%SCRIPT_DIR%%\venv\Scripts\python.exe" "%%SCRIPT_DIR%%\app\main_gui.py" %%*
) > "%INSTALL_DIR%\start_fret_tool.bat"

:: Make sure CRLF endings are preserved by Windows automatically

:: -------------------------------------------------------------
:: 7. Completion message
:: -------------------------------------------------------------
echo.
echo ============================================================
echo  Installation Complete!
echo ============================================================
echo SONLab FRET Tool has been installed to:
echo     %INSTALL_DIR%
echo.
echo You can run the application using:
echo     %INSTALL_DIR%\start_fret_tool.bat
echo.
echo (Optionally create a shortcut to this file on your Desktop.)
echo.

exit /b 0
