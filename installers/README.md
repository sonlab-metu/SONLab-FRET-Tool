# SONLab FRET Tool Installation Guide

This document provides detailed installation instructions for the SONLab FRET Tool on Windows, Linux, and macOS systems.

## Prerequisites

### All Systems
- At least 8GB of free disk space
- Stable internet connection
- **Python 3.10** (strictly required for dependency compatibility)
  - Other Python versions, including newer ones, are not supported
  - [Download Python 3.10.11](https://www.python.org/downloads/release/python-31011/)

## Installation Instructions

### Windows Installation (Two Methods Available)

#### Method 1: GUI Installer (Recommended for Most Users)
1. **Download the Installer**
   - Download `SONLab_FRET_Tool_Setup.exe` from our [releases page](https://github.com/sonlab-metu/SONLab-FRET-Tool/releases)
   - The file will be named something like `SONLab_FRET_Tool_Setup_x64.exe`

2. **Run the Installer**
   - Double-click the downloaded `.exe` file
   - If you see a security warning, click "More info" then "Run anyway"
   - Follow the on-screen instructions in the installation wizard
   - Choose your preferred installation location and components
   - Select your PyTorch backend (CUDA/CPU) from the options

3. **Complete the Installation**
   - The installer will create a desktop shortcut and Start Menu entry
   - You can launch the application from either location after installation

#### Method 2: Manual Installation (Advanced Users)
1. **Download and Extract**
   - Download the `SONLab-FRET-Tool` repository
   - Extract it to your desired location (e.g., `C:\Users\YourUsername\SONLab-FRET-Tool`)

2. **Install Python 3.10 (if not already installed)**
   - Download and install Python 3.10.11 from: [python.org/downloads/release/python-31011](https://www.python.org/downloads/release/python-31011/)
   - During installation, make sure to check "Add Python 3.10 to PATH"

3. **Run the Installer**
   - Open PowerShell as Administrator
   - Navigate to the installers directory:
     ```powershell
     cd "path\to\SONLab-FRET-Tool\installers"
     ```
   - Run the installation script:
     ```powershell
     Set-ExecutionPolicy Bypass -Scope Process -Force; .\install_windows.ps1
     ```

3. **Complete the Installation**
   - Follow the on-screen prompts to select your PyTorch backend
   - The installer will create a desktop shortcut and Start Menu entry

### Linux Installation

1. **Extract the Repository**
   ```bash
   unzip SONLab-FRET-Tool.zip -d ~/
   cd ~/SONLab-FRET-Tool/installers
   ```

2. **Install Python 3.10 (if not already installed)**
   - Debian/Ubuntu:
     ```bash
     sudo add-apt-repository ppa:deadsnakes/ppa
     sudo apt update
     sudo apt install python3.10 python3.10-venv python3.10-dev
     ```
   - Red Hat/CentOS:
     ```bash
     sudo dnf install python3.10 python3.10-devel
     ```
   - Arch Linux:
     ```bash
     sudo pacman -S python310 python-pip
     ```

3. **Run the Installer**
   ```bash
   ./install_linux.sh
   ```
   - The script will request sudo privileges to install system dependencies
   - A desktop launcher will be created in `~/.local/share/applications`

3. **Launch the Application**
   - Find "SONLab FRET Tool" in your applications menu
   - Or run from terminal: `~/SONLab-FRET-Tool/start_fret_tool.sh`

### macOS Installation

1. **Extract the Repository**
   ```bash
   unzip SONLab-FRET-Tool.zip -d ~/Applications/
   cd ~/Applications/SONLab-FRET-Tool/installers
   ```

2. **Install Python 3.10 (if not already installed)**
   - Using Homebrew (recommended):
     ```bash
     brew install python@3.10
     ```
   - Or download from: [python.org/downloads/release/python-31011](https://www.python.org/downloads/release/python-31011/)
   - Make sure Python 3.10 is in your PATH

3. **Run the Installer**
   ```bash
   bash install_mac.sh
   ```
   - The script will install Homebrew if needed
   - It will create an application bundle in `~/Applications/SONLab_FRET_Tool.app`

3. **First Run**
   - If you see a security warning, right-click the app and select "Open"
   - Then click "Open" in the security dialog

## Important Notes

### Python Version Requirement
- **Python 3.10 is strictly required** for compatibility with all dependencies
- Other Python versions, including newer ones, are not supported and may cause issues
- The installer will verify Python 3.10 is installed before proceeding

## PyTorch Backend Selection

During installation, you'll be prompted to select a PyTorch backend:

1. **NVIDIA CUDA 11.8** - For NVIDIA GPUs
2. **NVIDIA CUDA 12.6** - For newer NVIDIA GPUs
3. **NVIDIA CUDA 12.8** - For latest NVIDIA GPUs
4. **AMD ROCm 6.3** - For AMD GPUs (Linux only)
5. **CPU only** - No GPU acceleration

## Uninstallation

### Windows
#### For GUI Installation:
- Open Windows Settings > Apps > Apps & features
- Find "SONLab FRET Tool" in the list
- Click Uninstall and follow the prompts

#### For Manual Installation:
- Delete the `SONLab-FRET-Tool` directory
- Remove the desktop shortcut and Start Menu entry

### Linux
```bash
rm -rf ~/SONLab-FRET-Tool
rm ~/.local/share/applications/sonlab-fret-tool.desktop
```

### macOS
```bash
rm -rf ~/Applications/SONLab_FRET_Tool.app
rm -rf ~/Applications/SONLab-FRET-Tool
```

## Troubleshooting

### Common Issues

#### Installation Fails
- Ensure you have at least 8GB free disk space
- Verify your internet connection is stable
- Run the installer with administrator/root privileges if needed

#### GPU Acceleration Issues
1. Verify your GPU is supported by the selected backend
2. Ensure you have the latest drivers installed
3. Try the CPU-only version if GPU acceleration is not required

## Download the GUI Installer

The latest GUI installer can be downloaded from our [releases page](https://github.com/sonlab-metu/SONLab-FRET-Tool/releases). Look for the `.exe` file in the "Assets" section of the latest release.

## Support

For additional assistance, please contact the SONLab support team or open an issue on our [GitHub repository](https://github.com/sonlab-metu/SONLab-FRET-Tool/issues).

## License
This software is licensed under the terms of the MIT License. See the [LICENSE](../LICENSE) file for details.
