#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'
BLUE='\033[0;34m'

# Function to display section headers
section() {
    echo ""
    echo -e "${GREEN}=== $1 ===${NC}"
    echo ""
}

# Function to display warnings
warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if running as root
if [ "$(id -u)" -eq 0 ]; then
    warning "It's not recommended to run this script as root. Please run as a normal user."
    echo -n "Do you want to continue? [y/N] "
    read -r
    if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
        exit 1
    fi
fi

# Check for Python installation
section "Checking for Python 3.8 or later"
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}Python 3 is not installed.${NC}"
    echo "Please install Python 3.8 or later using your distribution's package manager:"
    echo -e "  Debian/Ubuntu: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    echo -e "  Red Hat/CentOS: sudo dnf install python3 python3-venv python3-pip"
    echo -e "  Arch Linux: sudo pacman -S python python-pip"
    echo -e "\nAfter installation, please run this script again."
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

# Set installation directory
echo -e "\n${GREEN}Where would you like to install SONLab FRET Tool?${NC}"
echo "Press Enter to use the default location: ~/SONLab_FRET_Tool"
echo -n "Installation directory: "
read -r INSTALL_DIR

# Set default if empty
if [ -z "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/SONLab_FRET_Tool"
fi

# Expand ~ to home directory
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

# Create installation directory if it doesn't exist
mkdir -p "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Could not create installation directory.${NC}"
    echo "Please check the path and permissions and try again."
    exit 1
fi

# Check if the directory is empty
if [ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    echo -e "${YELLOW}Warning: The directory $INSTALL_DIR is not empty.${NC}"
    echo -n "Do you want to continue? [y/N] "
    read -r
    if [ "$REPLY" != "y" ] && [ "$REPLY" != "Y" ]; then
        exit 1
    fi
fi

# Create virtual environment
section "Creating Python virtual environment"
python3 -m venv "$INSTALL_DIR/venv"
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to create virtual environment.${NC}"
    echo "Please make sure you have the required system packages installed:"
    echo "  Debian/Ubuntu: sudo apt install python3-venv"
    echo "  Red Hat/CentOS: sudo dnf install python3-venv"
    echo "  Arch Linux: sudo pacman -S python-virtualenv"
    exit 1
fi

# Install packages from requirements.txt
section "Installing Python packages from requirements.txt"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Install PyTorch
section "Installing PyTorch"
echo "Select your compute platform:"
echo "1. CUDA 11.8 - NVIDIA GPUs with CUDA 11.8"
echo "2. CUDA 12.6 - NVIDIA GPUs with CUDA 12.6"
echo "3. CUDA 12.8 - NVIDIA GPUs with CUDA 12.8"
echo "4. ROCm 6.3 - AMD GPUs with ROCm 6.3"
echo "5. CPU only - no GPU acceleration"
echo -n "Enter your choice (1-5): "
read -r PLATFORM_CHOICE

case $PLATFORM_CHOICE in
    1)
        echo "Installing PyTorch with CUDA 11.8 support..."
        "$INSTALL_DIR/venv/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
        ;;
    2)
        echo "Installing PyTorch with CUDA 12.6 support..."
        "$INSTALL_DIR/venv/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
        ;;
    3)
        echo "Installing PyTorch with CUDA 12.8 support..."
        "$INSTALL_DIR/venv/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
        ;;
    4)
        echo "Installing PyTorch with ROCm 6.3 support..."
        "$INSTALL_DIR/venv/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3
        ;;
    *)
        echo "Installing CPU-only PyTorch..."
        "$INSTALL_DIR/venv/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
        ;;
esac

# Create application directory structure
section "Setting up application files"
mkdir -p "$INSTALL_DIR/app"
mkdir -p "$INSTALL_DIR/app/icons"
mkdir -p "$INSTALL_DIR/app/luts"
mkdir -p "$INSTALL_DIR/installers"

# Copy all Python files (excluding installers directory)
echo "Copying Python files..."
find "$PROJECT_ROOT" -maxdepth 1 -name "*.py" -exec cp {} "$INSTALL_DIR/app/" \;

# Copy icons
echo "Copying icons..."
cp "$PROJECT_ROOT/icon.png" "$INSTALL_DIR/app/icons/" 2>/dev/null || true
cp "$PROJECT_ROOT/logo.png" "$INSTALL_DIR/app/icons/" 2>/dev/null || true

# Copy LUT files
echo "Copying LUT files..."
cp "$PROJECT_ROOT/"*.lut "$INSTALL_DIR/app/luts/" 2>/dev/null || true

# Copy JSON config files
echo "Copying configuration files..."
cp "$PROJECT_ROOT/"*.json "$INSTALL_DIR/app/" 2>/dev/null || true

# Copy license and documentation
echo "Copying documentation..."
cp "$PROJECT_ROOT/LICENSE" "$INSTALL_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/README.md" "$INSTALL_DIR/" 2>/dev/null || true
cp "$PROJECT_ROOT/CHANGELOG.md" "$INSTALL_DIR/" 2>/dev/null || true

# Copy installers for reference
echo "Copying installer files..."
cp -r "$PROJECT_ROOT/installers" "$INSTALL_DIR/" 2>/dev/null || true

# Create launcher script
section "Creating launcher"
cat > "$INSTALL_DIR/start_fret_tool.sh" << 'EOL'
#!/bin/bash
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create a temporary directory for the GUI package
TEMP_GUI_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_GUI_DIR"' EXIT

# Create the GUI package structure
mkdir -p "$TEMP_GUI_DIR/GUI"

# Create __init__.py if it doesn't exist
if [ ! -f "$SCRIPT_DIR/app/__init__.py" ]; then
    touch "$SCRIPT_DIR/app/__init__.py"
fi

# Copy all Python files to the temporary GUI package
cp "$SCRIPT_DIR/app/"*.py "$TEMP_GUI_DIR/GUI/"

# Create a temporary main script that will import and run the application
cat > "$TEMP_GUI_DIR/run_app.py" << 'PYTHON_SCRIPT'
import sys
import os
from GUI.main_gui import main

if __name__ == "__main__":
    # Add the directory containing the GUI package to the path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
PYTHON_SCRIPT

# Set the PYTHONPATH to include the temporary directory
export PYTHONPATH="$TEMP_GUI_DIR:$SCRIPT_DIR"

# Run the application using the virtual environment's Python
"$SCRIPT_DIR/venv/bin/python" "$TEMP_GUI_DIR/run_app.py" "$@"
EOL

chmod +x "$INSTALL_DIR/start_fret_tool.sh"

# Create desktop launcher
section "Creating desktop launcher"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/sonlab-fret-tool.desktop" << EOL
[Desktop Entry]
Version=1.0
Type=Application
Name=SONLab FRET Tool
Comment=FRET analysis tool from SONLab
Exec=$INSTALL_DIR/start_fret_tool.sh
Icon=$INSTALL_DIR/app/icons/logo.png
Terminal=false
Categories=Science;Biology;
StartupWMClass=SONLab FRET Tool
EOL

# Update icon cache
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor"
fi

# Update desktop database
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR"
fi

# Print completion message
section "Installation Complete!"
echo -e "${GREEN}SONLab FRET Tool has been successfully installed to:${NC}"
echo -e "${BOLD}$INSTALL_DIR${NC}"
echo ""
echo -e "${GREEN}You can now run the application using one of these methods:${NC}"
echo -e "1. Desktop launcher: Look for 'SONLab FRET Tool' in your applications menu"
echo -e "2. Command line: ${BOLD}$INSTALL_DIR/start_fret_tool.sh${NC}"
echo ""
echo -e "${YELLOW}Note: If you don't see the application in your menu, please log out and log back in.${NC}"
echo ""
echo -e "To uninstall, simply remove the directory: ${BOLD}$INSTALL_DIR${NC}"
