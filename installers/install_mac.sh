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
    echo "Please install Python 3.8 or later using one of these methods:"
    echo "  1. Download from https://www.python.org/downloads/"
    echo "  2. Using Homebrew: brew install python@3.9"
    echo -e "\nAfter installation, please run this script again."
    exit 1
fi

# Check for Homebrew
if ! command -v brew >/dev/null 2>&1; then
    echo -e "${YELLOW}Homebrew is not installed. It's required for some dependencies.${NC}"
    echo -n "Would you like to install Homebrew now? [Y/n] "
    read -r
    if [ "$REPLY" = "" ] || [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
fi

# Install required tools for icon conversion
section "Installing required tools"
if ! command -v sips >/dev/null 2>&1 || ! command -v iconutil >/dev/null 2>&1; then
    echo "Installing required tools..."
    xcode-select --install 2>/dev/null || true
fi

# Get the directory where this script is located
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")

# Set installation directory
section "Installation Location"
echo -e "${GREEN}Where would you like to install SONLab FRET Tool?${NC}"
echo "Press Enter to use the default location: ~/Applications/SONLab_FRET_Tool"
echo -n "Installation directory: "
read -r INSTALL_DIR

# Set default if empty
if [ -z "$INSTALL_DIR" ]; then
    INSTALL_DIR="$HOME/Applications/SONLab_FRET_Tool"
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
    echo "Please make sure you have the required system packages installed."
    exit 1
fi

# Install packages from requirements.txt
section "Installing Python packages"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Install PyTorch
section "Installing PyTorch"
echo "Select your compute platform:"
echo "1. CPU only - no GPU acceleration (recommended for most Macs)"
echo "2. MPS (Metal Performance Shaders) - For Apple Silicon Macs"
echo -n "Enter your choice (1-2): "
read -r PLATFORM_CHOICE

case $PLATFORM_CHOICE in
    2)
        echo "Installing PyTorch with MPS (Metal) support..."
        "$INSTALL_DIR/venv/bin/pip" install torch torchvision torchaudio
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

# Copy Python files
echo "Copying Python files..."
cp "$PROJECT_ROOT/"*.py "$INSTALL_DIR/app/"

# Create iconset for .icns
echo "Creating application icon..."
mkdir -p "$INSTALL_DIR/app/icon.iconset"

# Convert logo.png to .icns format
if [ -f "$PROJECT_ROOT/logo.png" ]; then
    sips -z 16 16     "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_16x16.png"
    sips -z 32 32     "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_16x16@2x.png"
    sips -z 32 32     "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_32x32.png"
    sips -z 64 64     "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_32x32@2x.png"
    sips -z 128 128   "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_128x128.png"
    sips -z 256 256   "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_128x128@2x.png"
    sips -z 256 256   "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_256x256.png"
    sips -z 512 512   "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_256x256@2x.png"
    sips -z 512 512   "$PROJECT_ROOT/logo.png" --out "$INSTALL_DIR/app/icon.iconset/icon_512x512.png"
    
    # Create .icns file
    iconutil -c icns "$INSTALL_DIR/app/icon.iconset" -o "$INSTALL_DIR/app/AppIcon.icns"
    rm -rf "$INSTALL_DIR/app/icon.iconset"
    
    # Also copy the original icons
    cp "$PROJECT_ROOT/logo.png" "$INSTALL_DIR/app/icons/"
    cp "$PROJECT_ROOT/icon.png" "$INSTALL_DIR/app/icons/" 2>/dev/null || true
else
    echo -e "${YELLOW}Warning: logo.png not found, skipping .icns creation${NC}"
fi

# Copy LUT files
echo "Copying LUT files..."
cp "$PROJECT_ROOT/"*.lut "$INSTALL_DIR/app/luts/" 2>/dev/null || true

# Copy JSON config files
echo "Copying configuration files..."
cp "$PROJECT_ROOT/"*.json "$INSTALL_DIR/app/" 2>/dev/null || true

# Create macOS application bundle
section "Creating macOS Application Bundle"
APP_BUNDLE="$INSTALL_DIR/SONLab FRET Tool.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"

mkdir -p "$APP_MACOS"
mkdir -p "$APP_RESOURCES"

# Create Info.plist
cat > "$APP_CONTENTS/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>SONLab FRET Tool</string>
    <key>CFBundleDisplayName</key>
    <string>SONLab FRET Tool</string>
    <key>CFBundleIdentifier</key>
    <string>com.sonlab.frettool</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>SONLab_FRET_Tool</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.icns</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

# Create the launcher script
cat > "$APP_MACOS/SONLab_FRET_Tool" << 'EOL'
#!/bin/bash
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Go up three levels from MacOS to the .app bundle, then to the actual install directory
INSTALL_DIR="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Set the working directory to the install directory
cd "$INSTALL_DIR"

# Debug information
echo "SCRIPT_DIR: $SCRIPT_DIR"
echo "INSTALL_DIR: $INSTALL_DIR"
echo "Current directory: $(pwd)"

# Check if venv exists
if [ ! -d "$INSTALL_DIR/venv" ]; then
    echo "Error: Python virtual environment not found at $INSTALL_DIR/venv"
    exit 1
fi

# Check if app directory exists
if [ ! -d "$INSTALL_DIR/app" ]; then
    echo "Error: App directory not found at $INSTALL_DIR/app"
    exit 1
fi

# Create a temporary directory for the GUI package
TEMP_GUI_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_GUI_DIR"' EXIT

# Create the GUI package structure
mkdir -p "$TEMP_GUI_DIR/GUI"

# Copy all Python files to the temporary GUI package
cp "$INSTALL_DIR/app/"*.py "$TEMP_GUI_DIR/GUI/"

# Create __init__.py if it doesn't exist
touch "$TEMP_GUI_DIR/GUI/__init__.py"

# Create a temporary main script
cat > "$TEMP_GUI_DIR/run_app.py" << 'PYTHON_SCRIPT'
import sys
import os

# Add the GUI package to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run main
try:
    from GUI.main_gui import main
    sys.exit(main())
except ImportError as e:
    print(f'Error importing main_gui: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_SCRIPT

# Set up the Python path
export PYTHONPATH="$TEMP_GUI_DIR:$INSTALL_DIR"

# Run the application using the virtual environment's Python
exec "$INSTALL_DIR/venv/bin/python" "$TEMP_GUI_DIR/run_app.py" "$@"
EOL

# Make the launcher executable
chmod +x "$APP_MACOS/SONLab_FRET_Tool"

# Copy the icon to the resources
if [ -f "$INSTALL_DIR/app/AppIcon.icns" ]; then
    cp "$INSTALL_DIR/app/AppIcon.icns" "$APP_RESOURCES/AppIcon.icns"
fi

# Create a simple launcher script for the terminal
cat > "$INSTALL_DIR/start_fret_tool.sh" << 'EOL'
#!/bin/bash
# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Set the working directory to the install directory
cd "$SCRIPT_DIR"

# Debug information
echo "Installation directory: $SCRIPT_DIR"

# Check if venv exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Error: Python virtual environment not found at $SCRIPT_DIR/venv"
    exit 1
fi

# Check if app directory exists
if [ ! -d "$SCRIPT_DIR/app" ]; then
    echo "Error: App directory not found at $SCRIPT_DIR/app"
    exit 1
fi

# Create a temporary directory for the GUI package
TEMP_GUI_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_GUI_DIR"' EXIT

# Create the GUI package structure
mkdir -p "$TEMP_GUI_DIR/GUI"

# Copy all Python files to the temporary GUI package
cp "$SCRIPT_DIR/app/"*.py "$TEMP_GUI_DIR/GUI/"

# Create __init__.py if it doesn't exist
touch "$TEMP_GUI_DIR/GUI/__init__.py"

# Create a temporary main script
cat > "$TEMP_GUI_DIR/run_app.py" << 'PYTHON_SCRIPT'
import sys
import os

# Add the GUI package to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run main
try:
    from GUI.main_gui import main
    sys.exit(main())
except ImportError as e:
    print(f'Error importing main_gui: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_SCRIPT

# Set up the Python path
export PYTHONPATH="$TEMP_GUI_DIR:$SCRIPT_DIR"

# Run the application using the virtual environment's Python
exec "$SCRIPT_DIR/venv/bin/python" "$TEMP_GUI_DIR/run_app.py" "$@"
EOL

chmod +x "$INSTALL_DIR/start_fret_tool.sh"

# Create a desktop entry
DESKTOP_ENTRY="$HOME/Desktop/SONLab FRET Tool"
cat > "$DESKTOP_ENTRY" << 'EOL'
#!/bin/bash
open "$INSTALL_DIR/SONLab FRET Tool.app"
EOL
chmod +x "$DESKTOP_ENTRY"

# Print completion message
section "Installation Complete!"
echo -e "${GREEN}SONLab FRET Tool has been successfully installed to:${NC}"
echo -e "${BOLD}$INSTALL_DIR${NC}"
echo ""
echo -e "${GREEN}You can now run the application using one of these methods:${NC}"
echo -e "1. Double-click the 'SONLab FRET Tool' app in your Applications folder"
echo -e "2. Double-click the 'SONLab FRET Tool' icon on your Desktop"
echo -e "3. Run from terminal: ${BOLD}$INSTALL_DIR/start_fret_tool.sh${NC}"
echo ""
echo -e "${YELLOW}Note: If you see a security warning when opening the app, right-click the app"
echo -e "and select 'Open' to bypass the security check. You'll only need to do this once.${NC}"
