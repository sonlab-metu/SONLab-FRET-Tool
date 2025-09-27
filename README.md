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

- **Bleed-Through Correction**: Accurate donor and acceptor bleed-through estimation
- **Automated Segmentation**: Multiple thresholding methods and Cellpose integration
- **Manual ROI Selection**: Interactive tools for precise region-of-interest selection
- **FRET Analysis**: Comprehensive calculation of FRET efficiency and related metrics
- **Data Export**: Save analysis results in various formats for downstream processing
- **Customizable Interface**: Adjustable UI elements and theming options

## Installation

### Prerequisites

#### Windows
- Windows 10 or later (64-bit)
- Python 3.8 or later (installed automatically if missing)
- At least 4 GB of free disk space (8 GB recommended)
- Administrator privileges
- Internet connection

#### Linux
- Ubuntu 20.04+, Fedora 38+, or another modern distribution
- Python 3.8 or later
- Build tools (`gcc`, `make`, etc.) – installed automatically if missing
- At least 4 GB of free disk space (8 GB recommended)
- Internet connection

#### macOS
- macOS 12 Monterey or later (Intel & Apple Silicon)
- Python 3.8 or later (Homebrew installation offered if missing)
- Xcode Command-Line Tools (prompted automatically)
- At least 4 GB of free disk space (8 GB recommended)
- Internet connection

### Python Dependencies

All Python dependencies are installed automatically by the platform-specific installers and include (non-exhaustive):

- PyQt5
- numpy, scipy, matplotlib, scikit-image, scikit-learn
- opencv-python, tifffile, cellpose
- torch (with optional CUDA / ROCm / MPS acceleration)

### Installation Instructions

> **Tip** : Each installer creates an isolated **virtual environment** inside the installation directory so it will not disturb your system Python.

#### Windows
1. **Download** the repository ZIP or clone with Git and open **`GUI/installers`**.
2. **Run** `install_windows.bat` as **Administrator** (right-click ▶ “Run as administrator”).
3. Follow the prompts to choose an installation path and PyTorch backend.
4. **Launch** via the desktop shortcut *SONLab FRET Tool* or `start_fret_tool.bat` in the install folder.

#### Linux
```bash
# Clone repository and run installer
git clone https://github.com/aznursoy/SONLab-FRET-Tool.git
cd SONLab-FRET-Tool/GUI/installers
chmod +x install_linux.sh
./install_linux.sh
```
The script will install build tools (via `sudo`), create a virtual environment, install dependencies and add a desktop entry.

Launch from your applications menu or:
```bash
~/SONLab_FRET_Tool/start_fret_tool.sh
```

#### macOS
```bash
# Clone repository and run installer
git clone https://github.com/aznursoy/SONLab-FRET-Tool.git
cd SONLab-FRET-Tool/GUI/installers
chmod +x install_mac.sh
./install_mac.sh
```
The installer will:
- Offer to install Homebrew/python if missing
- Create a virtual environment and install dependencies (including PyTorch MPS or CPU)
- Build a signed **`SONLab FRET Tool.app`** bundle in `~/Applications/SONLab_FRET_Tool`
- Create a terminal launcher `start_fret_tool.sh`

Launch via **Finder ▶ Applications ▶ SONLab FRET Tool** or:
```bash
~/Applications/SONLab_FRET_Tool/start_fret_tool.sh
```
If macOS blocks the app, right-click ▸ **Open** to bypass Gatekeeper once.

### PyTorch Backend Selection
During installation you’ll be prompted to pick:
- **CUDA 11.8 / 12.x** for NVIDIA GPUs (Windows & Linux)
- **ROCm 6.3** for AMD GPUs (Linux)
- **MPS** for Apple Silicon (macOS)
- **CPU-only** if no GPU acceleration is required

### Troubleshooting

| Issue | Fix |
|-------|-----|
| *Python not found* | Ensure Python 3.8+ is installed / added to PATH. The installer will guide you. |
| *Permission denied* | Windows: run installer as Administrator.<br>Linux: don’t use `sudo` except when prompted.<br>macOS: ensure installer script is executable `chmod +x`. |
| *Icon not showing* | Log out/in or run `update-desktop-database ~/.local/share/applications` (Linux). |
| *Import errors after install* | Delete the install dir and rerun installer; ensure you selected the correct backend. |

For further help open an issue in the GitHub repository.

## Usage

After installation:
```bash
# Example (Linux/macOS)
~/SONLab_FRET_Tool/start_fret_tool.sh
```
or open the app shortcut. The interface provides three main tabs:

1. **Bleed-Through Correction** – calibrate donor/acceptor bleed-through.
2. **Segmentation** – automated (Otsu, adaptive) or Cellpose-based segmentation.
3. **FRET Analysis** – compute pixel-wise FRET efficiency and export CSVs.

## Contributing & License

Contributions are welcome — please read [`CONTRIBUTING.md`](CONTRIBUTING.md).

Licensed under the MIT License. See [`LICENSE`](LICENSE) for details.

## Contact

- 💬 Discussions / issues on [GitHub](https://github.com/aznursoy/SONLab-FRET-Tool)
- 📧 support@sonlab.org

---
<div align="center">
  <sub>Developed with ❤️ by SONLab Research Group — © 2025 SONLab</sub>
</div>
