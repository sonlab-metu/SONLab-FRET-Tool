# SONLab FRET Tool Windows Installer
# This script installs the SONLab FRET Tool with all its dependencies

[CmdletBinding()]
param(
    [Parameter()]
    [string]$InstallDir = "$env:USERPROFILE\SONLab_FRET_Tool",
    
    [Parameter()]
    [switch]$Silent,
    
    [Parameter()]
    [ValidateSet('cuda118', 'cuda126', 'cuda128', 'rocm63', 'cpu')]
    [string]$PyTorchBackend = 'cpu',
    
    [Parameter()]
    [switch]$Force
)

# Set up console output colors
$Host.UI.RawUI.WindowTitle = "SONLab FRET Tool Installer"
$ErrorActionPreference = "Stop"

# Console colors
$Colors = @{
    Reset = "`e[0m"
    Red = "`e[91m"
    Green = "`e[92m"
    Yellow = "`e[93m"
    Blue = "`e[94m"
    Magenta = "`e[95m"
    Cyan = "`e[96m"
    White = "`e[97m"
    Bold = "`e[1m"
    Underline = "`e[4m"
}

# Helper functions for colored output
function Write-Status {
    param([string]$Message)
    Write-Host "${$Colors.Cyan}[*]${$Colors.Reset} $Message"
}

function Write-Success {
    param([string]$Message)
    Write-Host "${$Colors.Green}[+]${$Colors.Reset} $Message"
}

function Write-Warning {
    param([string]$Message)
    Write-Host "${$Colors.Yellow}[!]${$Colors.Reset} $Message"
}

function Write-Error {
    param([string]$Message)
    Write-Host "${$Colors.Red}[!] ERROR:${$Colors.Reset} $Message"
}

function Write-Section {
    param([string]$Title)
    $line = '=' * 80
    Write-Host "`n${$Colors.Blue}$line${$Colors.Reset}"
    Write-Host "${$Colors.Blue}${$Colors.Bold}$($Title.ToUpper())${$Colors.Reset}"
    Write-Host "${$Colors.Blue}$line${$Colors.Reset}"
}

function Exit-WithError {
    param([string]$Message, [int]$ExitCode = 1)
    Write-Error $Message
    exit $ExitCode
}

# Ensure we're running as admin if needed
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warning "This script is not running as Administrator. Some operations might require elevation."
    if (-not $Silent) {
        $response = Read-Host "Continue anyway? (y/N)"
        if ($response -notmatch '^[yY]') {
            exit 1
        }
    }
}

function Test-PythonVersion {
    Write-Status "Checking Python installation..."
    
    # Try python3 first, then python
    $pythonCmds = @('python3', 'python')
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
            # Command not found, try next one
            continue
        }
    }
    
    if (-not $pythonPath) {
        Write-Error "Python is not installed or not in PATH"
        Write-Host "${$Colors.Reset}Please install Python 3.8 or later from https://www.python.org/downloads/"
        Write-Host "During installation, make sure to select 'Add Python to PATH'${$Colors.Reset}"
        return $false
    }
    
    # Check version
    $versionMatch = $pythonVersion -match '(\d+)\.(\d+)'
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
        Write-Error "Python 3.8 or higher is required (found $pythonVersion)"
        return $false
    }
    
    Write-Success "Found Python $pythonVersion at $pythonPath"
    return $true
}

function Get-InstallDirectory {
    param([string]$DefaultDir = "$env:USERPROFILE\SONLab_FRET_Tool")
    
    if ($Silent) {
        return $InstallDir
    }
    
    Write-Host "`n${$Colors.Bold}Installation Directory${$Colors.Reset}"
    Write-Host "Where would you like to install SONLab FRET Tool?"
    Write-Host "Default location: ${$Colors.Cyan}$DefaultDir${$Colors.Reset}"
    
    while ($true) {
        $dir = Read-Host "  Enter installation path or press Enter to use default"
        
        if ([string]::IsNullOrWhiteSpace($dir)) {
            $dir = $DefaultDir
        }
        
        # Expand any environment variables in the path
        $dir = [System.Environment]::ExpandEnvironmentVariables($dir)
        
        # Convert to absolute path
        $dir = [System.IO.Path]::GetFullPath($dir)
        
        # Check if path is valid
        try {
            $dirInfo = [System.IO.DirectoryInfo]$dir
            if (-not $dirInfo.Parent.Exists) {
                Write-Warning "Parent directory does not exist"
                continue
            }
            
            # Check if directory exists and is not empty
            if ($dirInfo.Exists -and $dirInfo.GetFiles().Count -gt 0 -and -not $Force) {
                Write-Warning "Directory is not empty: $dir"
                $overwrite = Read-Host "  Overwrite? (y/N)"
                if ($overwrite -ne 'y') {
                    continue
                }
            }
            
            return $dir
        } catch {
            Write-Warning "Invalid path: $_"
        }
    }
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

function New-PythonVenv {
    param(
        [string]$TargetDir,
        [switch]$Force
    )
    
    $venvPath = Join-Path $TargetDir "venv"
    
    # Check if venv already exists
    if (Test-Path $venvPath) {
        if ($Force) {
            Write-Status "Removing existing virtual environment..."
            Remove-Item -Path $venvPath -Recurse -Force -ErrorAction Stop
        } else {
            Write-Warning "Virtual environment already exists at $venvPath"
            return $true
        }
    }
    
    Write-Status "Creating Python virtual environment at $venvPath..."
    try {
        $python = (Get-Command python -ErrorAction Stop).Source
        
        # Create the virtual environment
        & $python -m venv $venvPath
        
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create virtual environment"
        }
        
        # Verify the virtual environment was created
        if (-not (Test-Path (Join-Path $venvPath "Scripts\python.exe"))) {
            throw "Virtual environment creation failed - Python executable not found"
        }
        
        Write-Success "Virtual environment created successfully"
        return $true
    } catch {
        Write-Error "Failed to create virtual environment: $_"
        if (Test-Path $venvPath) {
            Remove-Item -Path $venvPath -Recurse -Force -ErrorAction SilentlyContinue
        }
        return $false
    }
}

function Install-PythonDependencies {
    param(
        [string]$VenvPath,
        [string]$RequirementsFile
    )
    
    $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    
    if (-not (Test-Path $pipPath)) {
        Write-Error "pip not found at $pipPath"
        return $false
    }
    
    # Upgrade pip first
    Write-Status "Upgrading pip..."
    & $pythonPath -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Failed to upgrade pip, continuing anyway..."
    }
    
    # Install requirements
    if (Test-Path $RequirementsFile) {
        Write-Status "Installing Python dependencies from $RequirementsFile..."
        & $pipPath install -r $RequirementsFile
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install Python dependencies"
            return $false
        }
        Write-Success "Python dependencies installed successfully"
    } else {
        Write-Warning "Requirements file not found: $RequirementsFile"
    }
    
    return $true
}

function Install-PyTorch {
    param(
        [string]$VenvPath,
        [string]$Backend = 'cpu'
    )
    
    $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
    $torchInstallCmd = ""
    
    # Determine PyTorch installation command based on backend
    $torchInstallCmd = switch ($Backend.ToLower()) {
        'cuda118' { 
            Write-Status "Installing PyTorch with CUDA 11.8 support..."
            "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118"
        }
        'cuda126' { 
            Write-Status "Installing PyTorch with CUDA 12.6 support..."
            "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126"
        }
        'cuda128' { 
            Write-Status "Installing PyTorch with CUDA 12.8 support..."
            "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128"
        }
        'rocm63' { 
            Write-Status "Installing PyTorch with ROCm 6.3 support..."
            "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3"
        }
        default { 
            Write-Status "Installing CPU-only PyTorch..."
            "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu"
        }
    }
    
    # Execute the installation
    try {
        Invoke-Expression $torchInstallCmd
        if ($LASTEXITCODE -ne 0) {
            throw "PyTorch installation failed with exit code $LASTEXITCODE"
        }
        Write-Success "PyTorch installed successfully with $Backend backend"
        return $true
    } catch {
        Write-Error "Failed to install PyTorch: $_"
        return $false
    }
}

function Copy-ApplicationFiles {
    param(
        [string]$SourceDir,
        [string]$TargetDir
    )
    
    Write-Status "Copying application files..."
    
    # Define directory structure
    $dirs = @{
        app = Join-Path $TargetDir "app"
        icons = Join-Path $TargetDir "app\icons"
        luts = Join-Path $TargetDir "app\luts"
        gui = Join-Path $TargetDir "app\GUI"
    }
    
    # Create directories
    foreach ($dir in $dirs.Values) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }
    
    # Copy files with error handling
    try {
        # Copy Python files
        Get-ChildItem -Path $SourceDir -Filter "*.py" | 
            Where-Object { $_.Name -ne 'setup.py' } |
            Copy-Item -Destination $dirs.app -Force -ErrorAction Stop
        
        # Copy LUT files
        if (Test-Path "$SourceDir\lut_files") {
            Copy-Item -Path "$SourceDir\lut_files\*" -Destination $dirs.luts -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            Get-ChildItem -Path $SourceDir -Filter "*.lut" | 
                Copy-Item -Destination $dirs.luts -Force -ErrorAction SilentlyContinue
        }
        
        # Copy JSON configs
        Get-ChildItem -Path $SourceDir -Filter "*.json" | 
            Copy-Item -Destination $dirs.app -Force -ErrorAction SilentlyContinue
        
        # Copy icons
        @('icon.png', 'logo.png', 'icon.ico') | ForEach-Object {
            if (Test-Path "$SourceDir\$_") {
                Copy-Item -Path "$SourceDir\$_" -Destination $dirs.icons -Force -ErrorAction SilentlyContinue
            }
        }
        
        # Copy GUI directory if it exists
        if (Test-Path "$SourceDir\GUI") {
            Copy-Item -Path "$SourceDir\GUI\*" -Destination $dirs.gui -Recurse -Force -ErrorAction SilentlyContinue
        }
        
        Write-Success "Application files copied successfully"
        return $true
    } catch {
    }

    function Install-PythonDependencies {
        param(
            [string]$VenvPath,
            [string]$RequirementsFile
        )
        
        $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
        $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
        
        if (-not (Test-Path $pipPath)) {
            Write-Error "pip not found at $pipPath"
            return $false
        }
        
        # Upgrade pip first
        Write-Status "Upgrading pip..."
        & $pythonPath -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Failed to upgrade pip, continuing anyway..."
        }
        
        # Install requirements
        if (Test-Path $RequirementsFile) {
            Write-Status "Installing Python dependencies from $RequirementsFile..."
            & $pipPath install -r $RequirementsFile
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Failed to install Python dependencies"
                return $false
            }
            Write-Success "Python dependencies installed successfully"
        } else {
            Write-Warning "Requirements file not found: $RequirementsFile"
        }
        
        return $true
    }

    function Install-PyTorch {
        param(
            [string]$VenvPath,
            [string]$Backend = 'cpu'
        )
        
        $pipPath = Join-Path $VenvPath "Scripts\pip.exe"
        $torchInstallCmd = ""
        
        # Determine PyTorch installation command based on backend
        $torchInstallCmd = switch ($Backend.ToLower()) {
            'cuda118' { 
                Write-Status "Installing PyTorch with CUDA 11.8 support..."
                "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118"
            }
            'cuda126' { 
                Write-Status "Installing PyTorch with CUDA 12.6 support..."
                "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126"
            }
            'cuda128' { 
                Write-Status "Installing PyTorch with CUDA 12.8 support..."
                "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128"
            }
            'rocm63' { 
                Write-Status "Installing PyTorch with ROCm 6.3 support..."
                "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3"
            }
            default { 
                Write-Status "Installing CPU-only PyTorch..."
                "$pipPath install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu"
            }
        }
        
        # Execute the installation
        try {
            Invoke-Expression $torchInstallCmd
            if ($LASTEXITCODE -ne 0) {
                throw "PyTorch installation failed with exit code $LASTEXITCODE"
            }
            Write-Success "PyTorch installed successfully with $Backend backend"
            return $true
        } catch {
            Write-Error "Failed to install PyTorch: $_"
            return $false
        }
    }

    function Copy-ApplicationFiles {
        param(
            [string]$SourceDir,
            [string]$TargetDir
        )
        
        Write-Status "Copying application files..."
        
        # Define directory structure
        $dirs = @{
            app = Join-Path $TargetDir "app"
            icons = Join-Path $TargetDir "app\icons"
            luts = Join-Path $TargetDir "app\luts"
            gui = Join-Path $TargetDir "app\GUI"
        }
        
        # Create directories
        foreach ($dir in $dirs.Values) {
            if (-not (Test-Path $dir)) {
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
            }
        }
        
        # Copy files with error handling
        try {
            # Copy Python files
            Get-ChildItem -Path $SourceDir -Filter "*.py" | 
                Where-Object { $_.Name -ne 'setup.py' } |
                Copy-Item -Destination $dirs.app -Force -ErrorAction Stop
            
            # Copy LUT files
            if (Test-Path "$SourceDir\lut_files") {
                Copy-Item -Path "$SourceDir\lut_files\*" -Destination $dirs.luts -Recurse -Force -ErrorAction SilentlyContinue
            } else {
                Get-ChildItem -Path $SourceDir -Filter "*.lut" | 
                    Copy-Item -Destination $dirs.luts -Force -ErrorAction SilentlyContinue
            }
            
            # Copy JSON configs
            Get-ChildItem -Path $SourceDir -Filter "*.json" | 
                Copy-Item -Destination $dirs.app -Force -ErrorAction SilentlyContinue
            
            # Copy icons
            @('icon.png', 'logo.png', 'icon.ico') | ForEach-Object {
                if (Test-Path "$SourceDir\$_") {
                    Copy-Item -Path "$SourceDir\$_" -Destination $dirs.icons -Force -ErrorAction SilentlyContinue
                }
            }
            
            # Copy GUI directory if it exists
            if (Test-Path "$SourceDir\GUI") {
                Copy-Item -Path "$SourceDir\GUI\*" -Destination $dirs.gui -Recurse -Force -ErrorAction SilentlyContinue
            }
            
            Write-Success "Application files copied successfully"
            return $true
        } catch {
            Write-Error "Failed to copy application files: $_"
            return $false
        }
    }

    function New-ApplicationLauncher {
        param(
            [string]$InstallDir
        )
        
        $launcherBat = Join-Path $InstallDir "SONLab_FRET_Tool.bat"
        $pythonExe = Join-Path $InstallDir "venv\Scripts\python.exe"
        $mainScript = Join-Path $InstallDir "app\main_gui.py"
        
        $launcherContent = @"
@echo off
:: SONLab FRET Tool Launcher
:: This script launches the application with the correct Python environment

setlocal enabledelayedexpansion

:: Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
if "!SCRIPT_DIR:~-1!"=="\" set "SCRIPT_DIR=!SCRIPT_DIR:~0,-1!"

:: Set environment variables
set "PYTHONPATH=!SCRIPT_DIR!\app"
set "PYTHONUNBUFFERED=1"

:: Check if Python executable exists
if not exist "$pythonExe" (
    echo Error: Python executable not found at $pythonExe
    pause
    exit /b 1
)

Write-Host "${$Colors.Reset}"
Write-Host "${$Colors.Blue}${$Colors.Bold}SONLab FRET Tool Installer for Windows${$Colors.Reset}"
Write-Host "${$Colors.Blue}===============================================${$Colors.Reset}"

# Check if running in silent mode
if ($Silent) {
    Write-Status "Running in silent mode with the following parameters:"
    Write-Host "  Install Directory: $InstallDir"
    Write-Host "  PyTorch Backend: $PyTorchBackend"
    Write-Host "  Force: $Force"
}

# Get script directory
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
}

# Get project root (one level up from installers directory)
$ProjectRoot = Split-Path -Parent $ScriptDir
$requirementsTxt = Join-Path $ScriptDir "requirements.txt"

# Check Python installation
if (-not (Test-PythonVersion)) {
    Exit-WithError "Python 3.8 or higher is required but not found."
}

# Get installation directory
$installDir = Get-InstallDirectory -DefaultDir $InstallDir

# Create installation directory if it doesn't exist
if (-not (Test-Path $installDir)) {
    try {
        New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    } catch {
        Exit-WithError "Failed to create installation directory: $_"
    }
}

# Create virtual environment
if (-not (New-PythonVenv -TargetDir $installDir -Force:$Force)) {
    Exit-WithError "Failed to create Python virtual environment"
}

# Install Python dependencies
$venvPath = Join-Path $installDir "venv"
if (-not (Install-PythonDependencies -VenvPath $venvPath -RequirementsFile $requirementsTxt)) {
    Exit-WithError "Failed to install Python dependencies"
}

# Install PyTorch with selected backend
if ($Silent) {
    $backend = $PyTorchBackend
} else {
    Write-Host "`n${$Colors.Bold}PyTorch Backend Selection${$Colors.Reset}"
    Write-Host "Select the PyTorch backend to install:"
    Write-Host "  1) CUDA 11.8 (NVIDIA GPUs)"
    Write-Host "  2) CUDA 12.6 (NVIDIA GPUs, newer)"
    Write-Host "  3) CUDA 12.8 (NVIDIA GPUs, latest)"
    Write-Host "  4) ROCm 6.3 (AMD GPUs)"
    Write-Host "  5) CPU only (no GPU acceleration)"
    
    $choice = Read-Host "`nEnter your choice (1-5, default is 5)"
    $backend = switch ($choice) {
        '1' { 'cuda118' }
        '2' { 'cuda126' }
        '3' { 'cuda128' }
        '4' { 'rocm63' }
        default { 'cpu' }
    }
}

if (-not (Install-PyTorch -VenvPath $venvPath -Backend $backend)) {
    Write-Warning "PyTorch installation failed, falling back to CPU-only version"
    if (-not (Install-PyTorch -VenvPath $venvPath -Backend 'cpu')) {
        Exit-WithError "Failed to install PyTorch (CPU-only)"
    }
}

# Copy application files
if (-not (Copy-ApplicationFiles -SourceDir $ProjectRoot -TargetDir $installDir)) {
    Exit-WithError "Failed to copy application files"
}

# Create launcher
if (-not (New-ApplicationLauncher -InstallDir $installDir)) {
    Exit-WithError "Failed to create application launcher"
}

# Installation complete
Write-Section "Installation Complete!"
Write-Host "${$Colors.Green}${$Colors.Bold}SONLab FRET Tool has been successfully installed!${$Colors.Reset}"
Write-Host "${$Colors.Bold}Installation Directory:${$Colors.Reset} $installDir"
Write-Host "${$Colors.Bold}Python Environment:${$Colors.Reset} $venvPath"
Write-Host "${$Colors.Bold}PyTorch Backend:${$Colors.Reset} $backend"

# Display next steps
Write-Host "`n${$Colors.Bold}How to run the application:${$Colors.Reset}"
Write-Host "1. Double-click on 'SONLab FRET Tool' on your desktop"
Write-Host "   or"
Write-Host "2. Navigate to '$installDir' and run 'SONLab_FRET_Tool.bat'"

# Add uninstall information
$uninstallBat = Join-Path $installDir "uninstall.bat"
$uninstallContent = @"
@echo off
echo Uninstalling SONLab FRET Tool...
echo.
echo WARNING: This will remove all files in the installation directory.
echo          This action cannot be undone.
echo.
set /p confirm=Are you sure you want to continue? (y/N): 
if /i not "%confirm%"=="y" (
    echo Uninstallation cancelled.
    pause
    exit /b 1
)

echo Removing files...
rmdir /s /q "$installDir"
if exist "%USERPROFILE%\Desktop\SONLab FRET Tool.lnk" (
    del "%USERPROFILE%\Desktop\SONLab FRET Tool.lnk"
)

echo.
echo SONLab FRET Tool has been uninstalled.
pause
"@

$uninstallContent | Out-File -FilePath $uninstallBat -Encoding ASCII -Force
Write-Host "`n${$Colors.Yellow}Note:${$Colors.Reset} To uninstall, run 'uninstall.bat' in the installation directory."

# Open installation directory if not in silent mode
if (-not $Silent) {
    $openDir = Read-Host "`nOpen installation directory now? (Y/n)"
    if ($openDir -ne 'n' -and $openDir -ne 'N') {
        Start-Process $installDir
    }
}

# Exit with success
Write-Host "`n${$Colors.Green}${$Colors.Bold}Installation completed successfully!${$Colors.Reset}"
exit 0
