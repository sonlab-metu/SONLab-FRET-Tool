# SONLab FRET Tool Installation

This directory contains the installation scripts for the SONLab FRET Tool. The tool supports both Windows and Linux operating systems.

## Prerequisites

### Windows
- Windows 10 or later
- At least 4GB of free disk space
- Administrator privileges (required for installation)

### Linux
- A modern Linux distribution (Ubuntu 20.04+, CentOS 8+, etc.)
- At least 4GB of free disk space
- Build tools (gcc, make, etc.) - will be installed automatically if missing
- curl - will be installed automatically if missing

## Installation Instructions

### Windows
1. Download the `install_windows.bat` script
2. Right-click the script and select "Run as administrator"
3. Follow the on-screen instructions to complete the installation
4. A desktop shortcut will be created for easy access

### Linux
1. Open a terminal
2. Make the installation script executable:
   ```bash
   chmod +x install_linux.sh
   ```
3. Run the installation script:
   ```bash
   ./install_linux.sh
   ```
4. Follow the on-screen instructions to complete the installation
5. A desktop launcher will be created for easy access

## PyTorch Backend Selection

During installation, you'll be prompted to select a PyTorch backend:

1. **CUDA 11.8** - For NVIDIA GPUs with CUDA 11.8
2. **CUDA 12.6** - For NVIDIA GPUs with CUDA 12.6
3. **CUDA 12.8** - For NVIDIA GPUs with CUDA 12.8
4. **ROCm 6.3** - For AMD GPUs with ROCm 6.3
5. **CPU only** - For systems without GPU acceleration

Choose the option that matches your hardware. If you're unsure, select the CPU-only option.

## Uninstallation

### Windows
Run the `uninstall.bat` file in the installation directory.

### Linux
Run the `uninstall.sh` script in the installation directory.

## Troubleshooting

### Common Issues

#### Installation Fails
- Ensure you have sufficient disk space (at least 4GB free)
- Make sure you have a stable internet connection
- Run the installer as administrator (Windows) or with sudo (Linux) if needed

#### PyTorch CUDA Issues
If you experience issues with CUDA:
1. Verify your GPU supports the selected CUDA version
2. Ensure you have the correct NVIDIA drivers installed
3. Try the CPU-only version if GPU acceleration is not required

### Getting Help
For additional support, please contact the SONLab support team.

## License
This software is licensed under the terms of the MIT License. See the [LICENSE](../LICENSE) file for details.
