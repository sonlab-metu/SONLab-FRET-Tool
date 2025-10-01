# SONLab FRET Tool Windows Installer
# This script installs the SONLab FRET Tool with all its dependencies

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Silent,
    
    [Parameter()]
    [ValidateSet('cuda118', 'cuda126', 'cpu')]
    [string]$PyTorchBackend = 'cpu'
)

# Set up console output
$Host.UI.RawUI.WindowTitle = "SONLab FRET Tool Installer"
$ErrorActionPreference = "Stop"

# Helper functions for colored output
function Write-Status {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Yellow
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[!] ERROR: $Message" -ForegroundColor Red
}

function Write-Section {
    param([string]$Title)
    Write-Host "`n============================================================" -ForegroundColor Blue
    Write-Host $Title.ToUpper() -ForegroundColor Blue
    Write-Host "============================================================" -ForegroundColor Blue
}

function Exit-WithError {
    param([string]$Message, [int]$ExitCode = 1)
    Write-ErrorMsg $Message
    Read-Host "Press Enter to exit"
    exit $ExitCode
}

# Check if running as admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $Silent) {
    Write-Warning "Not running as Administrator. Some operations might require elevation."
    $response = Read-Host "Continue anyway? (y/N)"
    if ($response -notmatch '^[yY]') {
        exit 1
    }
}

# Check Python installation
function Test-PythonVersion {
    Write-Status "Checking Python installation..."
    
    $pythonCmds = @('python', 'python3')
    $pythonPath = $null
    $pythonVersion = $null
    
    foreach ($cmd in $pythonCmds) {
        try {
            $versionOutput = & $cmd --version 2>&1
            if ($LASTEXITCODE -eq 0) {
                $pythonPath = (Get-Command $cmd).Source
                $pythonVersion = $versionOutput -replace '^Python\s+', ''
                break
            }
        } catch {
            continue
        }
    }
    
    if (-not $pythonPath) {
        Write-ErrorMsg "Python 3.10 is not installed or not in PATH"
        Write-Host "Please install Python 3.10 from: https://www.python.org/downloads/release/python-31011/" -ForegroundColor Yellow
        Write-Host "During installation, make sure to select 'Add Python to PATH'" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Note: Python 3.10 is specifically required due to dependency compatibility." -ForegroundColor Yellow
        Write-Host "      Other versions (including newer ones) may cause issues with dependencies." -ForegroundColor Yellow
        return $false
    }
    
    # Check version - specifically require Python 3.10.x
    $versionMatch = $pythonVersion -match '(\d+)\.(\d+)'
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    
    if ($major -ne 3 -or $minor -ne 10) {
        Write-ErrorMsg "Python 3.10.x is required for stable functioning (found $pythonVersion)"
        Write-Host "Note: Python 3.10 is specifically required due to dependency compatibility." -ForegroundColor Yellow
        Write-Host "      Please install Python 3.10 from: https://www.python.org/downloads/release/python-31011/" -ForegroundColor Yellow
        return $false
    }
    
    Write-Success "Found Python $pythonVersion at $pythonPath"
    return $true
}

# Create virtual environment
function New-PythonVenv {
    param([string]$VenvPath)
    
    if (Test-Path $VenvPath) {
        Write-Status "Removing existing virtual environment..."
        Remove-Item -Path $VenvPath -Recurse -Force -ErrorAction Stop
    }
    
    Write-Status "Creating Python virtual environment..."
    try {
        $python = (Get-Command python -ErrorAction Stop).Source
        & $python -m venv $VenvPath
        
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment"
        }
        
        if (-not (Test-Path (Join-Path $VenvPath "Scripts\python.exe"))) {
            throw "Virtual environment creation failed"
        }
        
        Write-Success "Virtual environment created successfully"
        return $true
    } catch {
        Write-ErrorMsg "Failed to create virtual environment: $_"
        return $false
    }
}

# Install Python dependencies
function Install-PythonDependencies {
    param(
        [string]$VenvPath,
        [string]$RequirementsFile
    )
    
    $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    
    if (-not (Test-Path $pipPath)) {
        Write-ErrorMsg "pip not found at $pipPath"
        return $false
    }
    
    # Upgrade pip
    Write-Status "Upgrading pip..."
    & $pythonPath -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to upgrade pip, continuing anyway..."
    }
    
    # Install requirements
    if (Test-Path $RequirementsFile) {
        Write-Status "Installing Python dependencies..."
        & $pipPath install -r $RequirementsFile
        if ($LASTEXITCODE -ne 0) {
            Write-ErrorMsg "Failed to install Python dependencies"
            return $false
        }
        Write-Success "Python dependencies installed successfully"
    } else {
        Write-Warning "Requirements file not found: $RequirementsFile"
    }
    
    return $true
}

# Install PyTorch
function Install-PyTorch {
    param(
        [string]$VenvPath,
        [string]$Backend = 'cpu'
    )
    
    $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
    
    Write-Status "Installing PyTorch with $Backend backend..."
    
    $torchUrl = switch ($Backend.ToLower()) {
        'cuda118' { "https://download.pytorch.org/whl/cu118" }
        'cuda126' { "https://download.pytorch.org/whl/cu126" }
        default { "https://download.pytorch.org/whl/cpu" }
    }
    
    try {
        & $pipPath install torch torchvision torchaudio --index-url $torchUrl
        if ($LASTEXITCODE -ne 0) {
            throw "PyTorch installation failed"
        }
        Write-Success "PyTorch installed successfully"
        return $true
    } catch {
        Write-ErrorMsg "Failed to install PyTorch: $_"
        return $false
    }
}

# Create launcher script
function New-LauncherScript {
    param([string]$ProjectRoot)
    
    Write-Status "Creating launcher script..."
    
    $launcherPath = Join-Path $ProjectRoot "start_SONLab_FRET_Tool.bat"
    $launcherContent = @"
@echo off
REM SONLab FRET Tool Launcher
setlocal

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Check if virtual environment exists
if not exist "%SCRIPT_DIR%\venv\Scripts\python.exe" (
    echo Error: Virtual environment not found at %SCRIPT_DIR%\venv
    echo Please run the installer again to set up the environment
    pause
    exit /b 1
)

REM Activate virtual environment and run the application
call "%SCRIPT_DIR%\venv\Scripts\activate.bat"
python -m GUI.main_gui %*
"@
    
    try {
        $launcherContent | Out-File -FilePath $launcherPath -Encoding ASCII -Force
        Write-Success "Launcher script created: $launcherPath"
        return $launcherPath
    } catch {
        Write-ErrorMsg "Failed to create launcher script: $_"
        return $null
    }
}

# Create desktop shortcut
function New-DesktopShortcut {
    param(
        [string]$ProjectRoot,
        [string]$LauncherPath
    )
    
    Write-Status "Creating desktop shortcut..."
    
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktopPath "SONLab FRET Tool.lnk"
    $iconPath = Join-Path $ProjectRoot "GUI\logos\icon.ico"
    
    # Check if icon exists, if not try to find it
    if (-not (Test-Path $iconPath)) {
        $iconPath = Join-Path $ProjectRoot "GUI\logos\logo.png"
        if (-not (Test-Path $iconPath)) {
            Write-Warning "Icon not found at $iconPath"
            $iconPath = $null
        }
    }
    
    try {
        $WScriptShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WScriptShell.CreateShortcut($shortcutPath)
        $Shortcut.TargetPath = $LauncherPath
        $Shortcut.WorkingDirectory = $ProjectRoot
        $Shortcut.Description = "SONLab FRET Tool - FRET Analysis Application"
        
        if ($iconPath) {
            $Shortcut.IconLocation = $iconPath
        }
        
        $Shortcut.Save()
        Write-Success "Desktop shortcut created"
        return $true
    } catch {
        Write-Warning "Failed to create desktop shortcut: $_"
        return $false
    }
}

# Main installation flow
Write-Section "SONLab FRET Tool Installer for Windows"

# Get script and project directories
try {
    $ScriptPath = $MyInvocation.MyCommand.Definition
    $ScriptDir = Split-Path -Parent $ScriptPath
} catch {
    $ScriptDir = Get-Location
}


$ProjectRoot = Split-Path -Parent $ScriptDir
$VenvPath = Join-Path $ProjectRoot "venv"
$RequirementsFile = Join-Path $ScriptDir "requirements.txt"

Write-Status "Project root: $ProjectRoot"
Write-Status "Virtual environment: $VenvPath"

# Verify project structure
if (-not (Test-Path (Join-Path $ProjectRoot "GUI\main_gui.py"))) {
    Exit-WithError "This script must be run from the 'installers' directory of the SONLab FRET Tool project."
}

# Check Python
if (-not (Test-PythonVersion)) {
    Exit-WithError "Python 3.8 or higher is required."
}

# Create virtual environment
Write-Section "Setting Up Python Environment"
if (-not (New-PythonVenv -VenvPath $VenvPath)) {
    Exit-WithError "Failed to create virtual environment."
}

# Install dependencies
if (-not (Install-PythonDependencies -VenvPath $VenvPath -RequirementsFile $RequirementsFile)) {
    Exit-WithError "Failed to install Python dependencies."
}

# Select PyTorch backend
if (-not $Silent) {
    Write-Section "PyTorch Backend Selection"
    Write-Host "Select the PyTorch backend to install:"
    Write-Host "  1) CUDA 11.8 (NVIDIA GPUs)"
    Write-Host "  2) CUDA 12.6 (NVIDIA GPUs, newer)"
    Write-Host "  3) CPU only (no GPU acceleration, recommended)"
    
    $choice = Read-Host "`nEnter your choice (1-3, default is 3)"
    $PyTorchBackend = switch ($choice) {
        '1' { 'cuda118' }
        '2' { 'cuda126' }
        default { 'cpu' }
    }
}

# Install PyTorch
if (-not (Install-PyTorch -VenvPath $VenvPath -Backend $PyTorchBackend)) {
    Write-Warning "PyTorch installation failed, trying CPU-only version..."
    if (-not (Install-PyTorch -VenvPath $VenvPath -Backend 'cpu')) {
        Exit-WithError "Failed to install PyTorch."
    }
}

# Create launcher script
Write-Section "Creating Launcher"
$launcherPath = New-LauncherScript -ProjectRoot $ProjectRoot
if (-not $launcherPath) {
    Exit-WithError "Failed to create launcher script."
}

# Create desktop shortcut
New-DesktopShortcut -ProjectRoot $ProjectRoot -LauncherPath $launcherPath | Out-Null

# Installation complete
Write-Section "Installation Complete!"
Write-Success "SONLab FRET Tool has been successfully installed!"
Write-Host "`nInstallation Details:" -ForegroundColor White
Write-Host "  Project Directory: $ProjectRoot" -ForegroundColor White
Write-Host "  Virtual Environment: $VenvPath" -ForegroundColor White
Write-Host "  PyTorch Backend: $PyTorchBackend" -ForegroundColor White

Write-Host "`nHow to run the application:" -ForegroundColor White
Write-Host "  1. Double-click 'SONLab FRET Tool' on your desktop"
Write-Host "  2. Run: $launcherPath"
Write-Host "  3. From command prompt in project directory: venv\Scripts\activate && python -m GUI.main_gui"

if (-not $Silent) {
    Write-Host ""
    $openDir = Read-Host "Open project directory now? (Y/n)"
    if ($openDir -ne 'n' -and $openDir -ne 'N') {
        Start-Process $ProjectRoot
    }
}

Write-Host "`n" -NoNewline
Write-Success "Installation completed successfully!"
exit 0
