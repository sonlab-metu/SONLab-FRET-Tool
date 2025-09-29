#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'
BLUE='\033[0;34m'

# Application information
APP_NAME="SONLab FRET Tool"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$APP_DIR/venv"

# Function to display section headers
section() {
    echo -e "\n${GREEN}=== $1 ===${NC}\n"
}

# Function to display status messages
status() {
    echo -e "${BLUE}➔${NC} $1"
}

# Function to display success messages
success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to display warnings
warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to display errors and exit
error() {
    echo -e "${RED}✗ $1${NC}" >&2
    exit 1
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
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

# Check if we're running from the correct directory
if [ ! -f "$APP_DIR/GUI/main_gui.py" ]; then
    error "This script must be run from the 'installers' directory of the extracted SONLab-FRET-Tool package."
    echo "Please extract the package and run: cd SONLab-FRET-Tool/installers"
    exit 1
fi

# Check for Python installation
section "Checking Dependencies"
status "Checking for Python 3.8 or later..."
if ! command -v python3 >/dev/null 2>&1; then
    error "Python 3 is not installed."
    echo "Please install Python 3.8 or later using your distribution's package manager:"
    echo "  Debian/Ubuntu: sudo apt update && sudo apt install python3 python3-venv python3-pip"
    echo "  Red Hat/CentOS: sudo dnf install python3 python3-venv python3-pip"
    echo "  Arch Linux: sudo pacman -S python python-pip"
fi

# Check for required system packages
status "Checking for required system packages..."
MISSING_DEPS=()

if ! command_exists gcc; then
    MISSING_DEPS+=("gcc")
fi

if ! command_exists make; then
    MISSING_DEPS+=("make")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    warning "The following required packages are not installed: ${MISSING_DEPS[*]}"
    echo "These packages are required for building some Python dependencies."
    echo -n "Would you like to install them now? [Y/n] "
    read -r
    if [ -z "$REPLY" ] || [[ "$REPLY" =~ ^[Yy] ]]; then
        if command_exists apt; then
            sudo apt update && sudo apt install -y "${MISSING_DEPS[@]}" python3-venv
        elif command_exists dnf; then
            sudo dnf install -y "${MISSING_DEPS[@]}" python3-venv
        elif command_exists pacman; then
            sudo pacman -S --noconfirm "${MISSING_DEPS[@]}" python-virtualenv
        else
            warning "Could not determine package manager. Please install the required packages manually:"
            echo "  ${MISSING_DEPS[*]}"
            echo -n "Press Enter to continue or Ctrl+C to cancel..."
            read -r
        fi
    fi
fi

# Create virtual environment
section "Setting Up Python Environment"
status "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR" || error "Failed to create virtual environment."

# Activate virtual environment
source "$VENV_DIR/bin/activate" || error "Failed to activate virtual environment."

# Upgrade pip
status "Upgrading pip..."
"$VENV_DIR/bin/pip" install --upgrade pip || warning "Failed to upgrade pip, continuing anyway..."

# Install packages from requirements.txt
status "Installing Python packages..."
"$VENV_DIR/bin/pip" install -r "$APP_DIR/installers/requirements.txt" || error "Failed to install requirements."

# Install PyTorch
section "Installing PyTorch"
echo "Select your compute platform:"
echo "1. CUDA 11.8 - NVIDIA GPUs with CUDA 11.8"
echo "2. CUDA 12.6 - NVIDIA GPUs with CUDA 12.6"
echo "3. CUDA 12.8 - NVIDIA GPUs with CUDA 12.8"
echo "4. ROCm 6.3 - AMD GPUs with ROCm 6.3 (Linux only)"
echo "5. CPU only - no GPU acceleration"
echo -n "Enter your choice (1-5): "
read -r PLATFORM_CHOICE

status "Installing PyTorch with selected backend..."
case $PLATFORM_CHOICE in
    1)
        "$VENV_DIR/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 || \
            warning "Failed to install PyTorch with CUDA 11.8. Trying with --no-cache-dir..." && \
            "$VENV_DIR/bin/pip" install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118 || \
            error "Failed to install PyTorch with CUDA 11.8"
        ;;
    2)
        "$VENV_DIR/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126 || \
            warning "Failed to install PyTorch with CUDA 12.6. Trying with --no-cache-dir..." && \
            "$VENV_DIR/bin/pip" install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126 || \
            error "Failed to install PyTorch with CUDA 12.6"
        ;;
    3)
        "$VENV_DIR/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 || \
            warning "Failed to install PyTorch with CUDA 12.8. Trying with --no-cache-dir..." && \
            "$VENV_DIR/bin/pip" install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 || \
            error "Failed to install PyTorch with CUDA 12.8"
        ;;
    4)
        "$VENV_DIR/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3 || \
            warning "Failed to install PyTorch with ROCm 6.3. Trying with --no-cache-dir..." && \
            "$VENV_DIR/bin/pip" install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.3 || \
            error "Failed to install PyTorch with ROCm 6.3"
        ;;
    *)
        "$VENV_DIR/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu || \
            warning "Failed to install CPU-only PyTorch. Trying with --no-cache-dir..." && \
            "$VENV_DIR/bin/pip" install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu || \
            error "Failed to install CPU-only PyTorch"
        ;;
esac

# Create launcher script
section "Creating Application Launcher"
status "Creating launcher script..."

# Create a start script
cat > "$APP_DIR/start_fret_tool.sh" << 'EOL'
#!/bin/bash
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Run the application
python3 -m GUI.main_gui "$@"
EOL

# Make the launcher executable
chmod +x "$APP_DIR/start_fret_tool.sh"

# Create desktop entry
status "Creating desktop entry..."
DESKTOP_ENTRY="$HOME/.local/share/applications/sonlab-fret-tool.desktop"
mkdir -p "$(dirname "$DESKTOP_ENTRY")"

cat > "$DESKTOP_ENTRY" << EOL
[Desktop Entry]
Version=v2.0.2
Type=Application
Name=SONLab FRET Tool
Comment=FRET analysis tool for microscopy
Exec=$APP_DIR/start_fret_tool.sh
Icon=$APP_DIR/GUI/logos/icon.png
Terminal=false
Categories=Science;Education;Biology;
StartupWMClass=SONLab FRET Tool
EOL

# Make desktop entry executable
chmod +x "$DESKTOP_ENTRY"

# Update icon cache and desktop database
if [ -n "$XDG_CURRENT_DESKTOP" ]; then
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        status "Updating icon cache..."
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    fi

    if command -v update-desktop-database >/dev/null 2>&1; then
        status "Updating desktop database..."
        update-desktop-database "$(dirname "$DESKTOP_ENTRY")" 2>/dev/null || true
    fi
fi

# Finalize installation
section "Installation Complete!"
success "SONLab FRET Tool has been successfully installed to:"
echo -e "  ${BOLD}$APP_DIR${NC}\n"

echo -e "${GREEN}You can now launch the application using one of these methods:${NC}"
echo "1. Desktop launcher: Search for 'SONLab FRET Tool' in your applications menu"
echo "2. Command line: $APP_DIR/start_fret_tool.sh"
echo "3. Double-click the start_fret_tool.sh file in the application directory"

if [ -z "$XDG_CURRENT_DESKTOP" ]; then
    echo -e "\n${YELLOW}Note: You're not running in a desktop environment. "
    echo "The application is a GUI tool and requires a desktop environment to run properly.${NC}" 
else
    echo -e "\n${YELLOW}Note: If you don't see the application in your menu, please log out and log back in.${NC}"
fi

echo -e "\n${GREEN}To uninstall:${NC}"
echo "1. Delete the application directory: $APP_DIR"
echo "2. Remove the desktop entry: rm ~/.local/share/applications/sonlab-fret-tool.desktop"
