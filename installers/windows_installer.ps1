# build_installer.ps1
# SONLab FRET Tool PowerShell installer script to be compiled with ps2exe

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Check-PythonVersion {
    Write-Host "Checking Python 3.8+ availability..."
    try {
        $ver = python -c "import sys; print(sys.version_info[:3])" 2>$null
        if (-not $ver) { throw "Python not found." }
        python -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)"
        if ($LASTEXITCODE -ne 0) {
            throw "Python version < 3.8"
        }
    } catch {
        Write-Host "Python 3.8 or higher is required. Please install and add to PATH."
        exit 1
    }
}

function Ask-InstallDir {
    $default = Join-Path $env:USERPROFILE "SONLab_FRET_Tool"
    Write-Host
    Write-Host "Where would you like to install SONLab FRET Tool?"
    Write-Host "Press ENTER to accept the default location: $default"
    $dir = Read-Host "Installation directory"
    if ([string]::IsNullOrWhiteSpace($dir)) { $dir = $default }
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        if (-not (Test-Path $dir)) {
            Write-Host "Failed to create directory $dir"
            exit 1
        }
    }
    return $dir
}

function Warn-IfNotEmpty($dir) {
    $items = Get-ChildItem -Path $dir -Force -ErrorAction SilentlyContinue
    if ($items) {
        Write-Host
        $answer = Read-Host "WARNING: Directory '$dir' is not empty. Continue installation anyway? (y/N)"
        if ($answer.ToLower() -ne 'y') {
            Write-Host "Installation aborted."
            exit 0
        }
    }
}

function Create-Venv($dir) {
    Write-Host "Creating Python virtual environment..."
    python -m venv "$dir\venv"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment. Ensure Python venv module is installed."
        exit 1
    }
}

function Install-Dependencies($pipPath, $requirementsFile) {
    Write-Host "Upgrading pip and installing dependencies..."
    & $pipPath install --upgrade pip
    & $pipPath install -r $requirementsFile
}

function Install-PyTorch($pipPath) {
    Write-Host
    Write-Host "Select your compute platform for PyTorch:"
    Write-Host "1) CUDA 11.8"
    Write-Host "2) CUDA 12.6"
    Write-Host "3) CUDA 12.8"
    Write-Host "4) ROCm 6.3"
    Write-Host "5) CPU only"
    $choice = Read-Host "Enter your choice (1-5)"
    switch ($choice) {
        '1' { & $pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 }
        '2' { & $pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126 }
        '3' { & $pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 }
        '4' { & $pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3 }
        default { & $pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu }
    }
}

function Copy-AppFiles($projectRoot, $installDir) {
    Write-Host "Copying application files..."
    $appDir = Join-Path $installDir "app"
    $iconsDir = Join-Path $appDir "icons"
    $lutsDir = Join-Path $appDir "luts"
    New-Item -ItemType Directory -Path $appDir,$iconsDir,$lutsDir -Force | Out-Null

    Copy-Item "$projectRoot\*.py" -Destination $appDir -Force
    Copy-Item "$projectRoot\*.lut" -Destination $lutsDir -Force -ErrorAction SilentlyContinue
    Copy-Item "$projectRoot\*.json" -Destination $appDir -Force -ErrorAction SilentlyContinue
    Copy-Item "$projectRoot\icon.png","$projectRoot\logo.png" -Destination $iconsDir -Force -ErrorAction SilentlyContinue
}

function Create-LauncherBat($installDir) {
    $batFile = Join-Path $installDir "start_fret_tool.bat"
    $content = @"
@echo off
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PYTHONPATH=%SCRIPT_DIR%\app"
"%SCRIPT_DIR%\venv\Scripts\python.exe" "%SCRIPT_DIR%\app\main_gui.py" %*
"@
    $content | Out-File -Encoding ASCII -FilePath $batFile
}

# --- Main Script ---

Write-Host "Starting SONLab FRET Tool installation..."

# Get absolute path of current script (works inside EXE created by ps2exe)
$InvocationPath = $MyInvocation.MyCommand.Path

if ([string]::IsNullOrEmpty($InvocationPath)) {
    # fallback if empty (somehow)
    $InvocationPath = $PSCommandPath
}

if ([string]::IsNullOrEmpty($InvocationPath)) {
    Write-Host "ERROR: Unable to determine script path."
    exit 1
}

$ScriptDir = Split-Path -Parent $InvocationPath
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "DEBUG: InvocationPath = '$InvocationPath'"
Write-Host "DEBUG: ScriptDir = '$ScriptDir'"
Write-Host "DEBUG: ProjectRoot = '$ProjectRoot'"


Write-Host "Script directory: $ScriptDir"
Write-Host "Project root directory: $ProjectRoot"

$requirementsTxt = Join-Path $ScriptDir "requirements.txt"

Check-PythonVersion

$installDir = Ask-InstallDir
Warn-IfNotEmpty $installDir

Create-Venv $installDir

$pipExe = Join-Path $installDir "venv\Scripts\pip.exe"
$pythonExe = Join-Path $installDir "venv\Scripts\python.exe"

Install-Dependencies $pipExe $requirementsTxt
Install-PyTorch $pipExe
Copy-AppFiles $ProjectRoot $installDir
Create-LauncherBat $installDir

Write-Host
Write-Host "==============================================="
Write-Host "Installation Complete!"
Write-Host "Installed at: $installDir"
Write-Host "Run the application via start_fret_tool.bat"
Write-Host "==============================================="
