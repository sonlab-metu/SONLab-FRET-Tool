# SONLab FRET Tool Installation Guide

This document provides detailed installation instructions for the SONLab FRET Tool on Windows, Linux, and macOS systems.

## Prerequisites

### All Systems
- At least 8GB of free disk space
- Stable internet connection
- Python 3.8 or later (will be required for the installation)

## Installation Instructions

### Windows Installation

1. **Download and Extract**
   - Download the `SONLab-FRET-Tool` repository
   - Extract it to your desired location (e.g., `C:\Users\YourUsername\SONLab-FRET-Tool`)

2. **Run the Installer**
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
   - The application will be installed in the directory where you extracted the files

### Linux Installation

1. **Extract the Repository**
   ```bash
   unzip SONLab-FRET-Tool.zip -d ~/
   cd ~/SONLab-FRET-Tool/installers
   ```

2. **Run the Installer**
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

2. **Run the Installer**
   ```bash
   bash install_mac.sh
   ```
   - The script will install Homebrew if needed
   - It will create an application bundle in `~/Applications/SONLab_FRET_Tool.app`

3. **First Run**
   - If you see a security warning, right-click the app and select "Open"
   - Then click "Open" in the security dialog

## PyTorch Backend Selection

During installation, you'll be prompted to select a PyTorch backend:

1. **NVIDIA CUDA 11.8** - For NVIDIA GPUs
2. **NVIDIA CUDA 12.6** - For newer NVIDIA GPUs
3. **NVIDIA CUDA 12.8** - For latest NVIDIA GPUs
4. **AMD ROCm 6.3** - For AMD GPUs (Linux only)
5. **CPU only** - No GPU acceleration

## Uninstallation

### Windows
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

## Support
For additional assistance, please contact the SONLab support team.

## License
This software is licensed under the terms of the MIT License. See the [LICENSE](../LICENSE) file for details.
