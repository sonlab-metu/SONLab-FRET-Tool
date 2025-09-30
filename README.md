# SONLab FRET Analysis Tool

<div align="center">
  <img src="GUI/logos/logo.png" alt="SONLab Logo" width="200"/>
  
  [![Version](https://img.shields.io/badge/version-v2.0.2-blue.svg)](https://sonlab-bio.metu.edu.tr)
  [![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
  [![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
  [![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()
</div>

## Overview

SONLab FRET Analysis Tool is a comprehensive graphical application designed for analyzing Fluorescence Resonance Energy Transfer (FRET) data. The application provides a user-friendly interface for processing microscopy images with specialized tools for bleed-through correction, segmentation, and FRET efficiency calculations.

## Features

- **Bleed-Through (Cross talk(orrection**: Accurate donor and acceptor bleed-through estimation
- **Automated Segmentation**: Multiple thresholding methods and Cellpose integration
- **Manual ROI Selection**: Interactive tools for precise region-of-interest selection
- **FRET Analysis**: Comprehensive calculation of FRET efficiency and related metrics
- **Data Export**: Save analysis results in various formats for downstream processing
- **Customizable Interface**: Adjustable UI elements and theming options

## Installation

We provide two methods to install the SONLab FRET Tool:
1. **Using Installers** (Recommended): Simple, automated installation with a desktop launcher
2. **Manual Installation**: For advanced users who want more control

### 1. Installation Using Installers (Recommended)

For automated installation with desktop integration, please refer to the installation scripts in the `installers/` directory:

- Windows: Run `installers/install_windows.ps1`
- Linux: Run `installers/install_linux.sh`
- macOS: Run `installers/install_mac.sh`

See the [Installers Documentation](installers/README.md) for detailed instructions.

### 2. Manual Installation

For advanced users who prefer manual setup:

#### Prerequisites

**All Platforms:**
- Python 3.8 or later
- pip (Python package manager)
- Git (or download the repository as ZIP)
- At least 8 GB of free disk space
- Internet connection

**Additional for Linux:**
- Build tools
- Python development headers

**Additional for macOS:**
- Xcode Command Line Tools
- Homebrew (recommended for Python installation)

#### Installation Steps

1. **Clone or Download the Repository**
   ```bash
   git clone https://github.com/sonlab-metu/SONLab-FRET-Tool.git
   cd SONLab-FRET-Tool
   ```
   Or download the ZIP and extract it.

2. **Create and Activate a Virtual Environment**

   **Windows (Command Prompt):**
   ```cmd
   python -m venv venv
   .\venv\Scripts\activate
   ```

   **Linux/macOS:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   # Install core requirements
   pip install -r installers/requirements.txt
   ```

When installing PyTorch, choose the appropriate version for your hardware. Run one of the following commands based on your compute platform:

**NVIDIA GPUs with CUDA 11.8**
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

 **NVIDIA GPUs with CUDA 12.6**
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
   ```

 **NVIDIA GPUs with CUDA 12.8**
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
   ```

 **AMD GPUs with ROCm 6.3** (Linux only)
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3
   ```

 **CPU-only** (No GPU acceleration)
   ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
   ```

**Note for macOS Users:**
- PyTorch will automatically use the Metal Performance Shaders (MPS) backend on Apple Silicon.
- Use the standard CPU installation command for macOS.

4. **Run the Application**
   ```bash
   # From the project root directory
   python3 -m GUI.main_gui
   ```

   **Note:** This method doesn't create a desktop shortcut or application launcher. You'll need to activate the virtual environment and run the command each time.

#### Running Without Virtual Environment (Not Recommended)

If you choose not to use a virtual environment (not recommended), you can install the requirements directly:

```bash
pip install -r installers/requirements.txt
# Install PyTorch as shown above
python3 -m GUI.main_gui
```



### Troubleshooting

| Issue | Solution |
|-------|----------|
| **Python not found** | Ensure Python 3.8+ is installed and in your system PATH |
| **Missing dependencies** | Install required system packages (see Prerequisites) |
| **Import errors** | Make sure all Python dependencies are installed in the virtual environment |
| **GPU not detected** | Verify CUDA/cuDNN is installed and compatible with your PyTorch version |
| **macOS app security** | If blocked, right-click the app and select Open, then confirm |

For further help open an issue in the GitHub repository.

## Contributing & License

Contributions are welcome — please read [`CONTRIBUTING.md`](CONTRIBUTING.md).

Licensed under the MIT License. See [`LICENSE`](LICENSE) for details.

## Contact

- 💬 Discussions / issues on [GitHub](https://github.com/sonlab-metu/SONLab-FRET-Tool)
- 📧 sonlab@metu.edu.tr

---
<div align="center">
  <sub>Developed with ❤️ by SONLab Research Group — © 2025 SONLab</sub>
</div>

