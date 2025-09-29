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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_ROOT/venv"

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
if [ ! -f "$PROJECT_ROOT/GUI/main_gui.py" ]; then
    error "This script must be run from the 'installers' directory of the extracted SONLab-FRET-Tool package."
    echo "Please extract the package and run: cd SONLab-FRET-Tool/installers"
    exit 1
fi

# Check for Python installation
section "Checking Dependencies"
status "Checking for Python 3.10..."

# Function to check if Python version is exactly 3.10
check_python_version() {
    local python_cmd=$1
    local version
    version=$($python_cmd -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null)
    if [ $? -ne 0 ]; then
        return 1  # Python command failed
    fi
    
    # Check if version is exactly 3.10
    if [ "$version" = "3.10" ]; then
        return 0  # Python 3.10 found
    fi
    
    # Check if version is higher than 3.10
    if [ "$(printf '%s\n' "3.10" "$version" | sort -V | head -n1)" = "3.10" ] && [ "$version" != "3.10" ]; then
        error "Python version $version is too new. Only Python 3.10 is supported."
        echo "Please install Python 3.10 using one of these methods:"
        echo "  1. Download from https://www.python.org/downloads/macos/"
        echo "  2. Using Homebrew: brew install python@3.10"
        exit 1
    fi
    
    return 1  # Python 3.10 not found
}

# Check for Python 3.10
PYTHON_CMD="python3.10"
if ! check_python_version "$PYTHON_CMD"; then
    # Try with python3
    PYTHON_CMD="python3"
    if ! check_python_version "$PYTHON_CMD"; then
        warning "Python 3.10 is required but not found."
        echo "Please install Python 3.10 using one of these methods:"
        echo "  1. Download from https://www.python.org/downloads/macos/"
        echo "  2. Using Homebrew: brew install python@3.10"
        echo -n "Would you like to install Python 3.10 using Homebrew? [Y/n] "
        read -r
        if [ -z "$REPLY" ] || [[ "$REPLY" =~ ^[Yy] ]]; then
            if ! command -v brew >/dev/null 2>&1; then
                error "Homebrew is required to install Python 3.10. Please install Homebrew first."
            fi
            status "Installing Python 3.10 via Homebrew..."
            brew install python@3.10 || error "Failed to install Python 3.10"
            # Add Python 3.10 to PATH if needed
            if [[ ":$PATH:" != *"/usr/local/opt/python@3.10/bin:"* ]]; then
                echo 'export PATH="/usr/local/opt/python@3.10/bin:$PATH"' >> ~/.zshrc
                export PATH="/usr/local/opt/python@3.10/bin:$PATH"
            fi
            PYTHON_CMD="python3.10"
        else
            error "Python 3.10 is required but not found. Please install it manually and try again."
            exit 1
        fi
    fi
fi

# Verify we have exactly Python 3.10
PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if [ "$PYTHON_VERSION" != "3.10" ]; then
    error "Unexpected Python version $PYTHON_VERSION. Only Python 3.10 is supported."
    exit 1
fi

export PYTHON_CMD

# Check for Homebrew and Xcode Command Line Tools
status "Checking for required tools..."
if ! command -v brew >/dev/null 2>&1; then
    warning "Homebrew is not installed. It's required for some dependencies."
    echo -n "Would you like to install Homebrew now? [Y/n] "
    read -r
    if [ -z "$REPLY" ] || [[ "$REPLY" =~ ^[Yy] ]]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || \
            error "Failed to install Homebrew"
        
        # Add Homebrew to PATH if needed
        if [[ "$SHELL" == *"zsh"* ]]; then
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
            eval "$(/opt/homebrew/bin/brew shellenv)"
        else
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.bash_profile
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    fi
fi

# Install Xcode Command Line Tools if needed
if ! xcode-select -p &>/dev/null; then
    status "Installing Xcode Command Line Tools..."
    xcode-select --install || error "Failed to install Xcode Command Line Tools"
    # Wait for Xcode installation to complete
    until xcode-select -p &>/dev/null; do
        echo -n "."
        sleep 5
    done
    echo ""
fi

# Prepare installation directory
status "Preparing installation directory..."

# Create virtual environment in the project root
section "Setting Up Python Environment"
status "Creating Python virtual environment with Python 3.10..."
$PYTHON_CMD -m venv "$VENV_DIR" || error "Failed to create virtual environment with Python 3.10"

# Activate virtual environment
source "$VENV_DIR/bin/activate" || error "Failed to activate virtual environment"

# Upgrade pip
status "Upgrading pip..."
"$VENV_DIR/bin/pip" install --upgrade pip || warning "Failed to upgrade pip, continuing anyway..."

# Install packages from requirements.txt
status "Installing Python packages..."
"$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/installers/requirements.txt" || error "Failed to install requirements"

# Install PyTorch
section "Installing PyTorch"
echo "Select your compute platform:"
echo "1. CPU only - Recommended for most Macs"
echo "2. MPS (Metal Performance Shaders) - For Apple Silicon Macs (experimental)"
echo -n "Enter your choice (1-2): "
read -r PLATFORM_CHOICE

status "Installing PyTorch with selected backend..."
case $PLATFORM_CHOICE in
    2)
        # MPS (Metal) backend for Apple Silicon
        pip install torch torchvision torchaudio || \
            warning "Failed to install PyTorch with MPS support. Trying with --no-cache-dir..." && \
            pip install --no-cache-dir torch torchvision torchaudio || \
            error "Failed to install PyTorch with MPS support"
        ;;
    *)
        # CPU-only version (default)
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu || \
            warning "Failed to install CPU-only PyTorch. Trying with --no-cache-dir..." && \
            pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu || \
            error "Failed to install CPU-only PyTorch"
        ;;
esac

# No need to copy files, we'll use them in place

# Create macOS application bundle
section "Creating macOS Application"
APP_NAME="SONLab FRET Tool"
APP_PATH="/Applications/$APP_NAME.app"
APP_CONTENTS="$APP_PATH/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"

# Remove existing app if it exists
if [ -d "$APP_PATH" ]; then
    status "Removing existing $APP_NAME.app..."
    rm -rf "$APP_PATH"
fi

# Create the app bundle structure
status "Creating application bundle..."
mkdir -p "$APP_MACOS"
mkdir -p "$APP_RESOURCES"

# Create Info.plist
cat > "$APP_CONTENTS/Info.plist" << 'EOL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>SONLab_FRET_Tool</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>org.sonlab.frettool</string>
    <key>CFBundleName</key>
    <string>SONLab FRET Tool</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
</dict>
</plist>
EOL

# Create the app bundle launcher
cat > "$APP_MACOS/SONLab_FRET_Tool" << 'EOL'
#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
source "$SCRIPT_DIR/venv/bin/activate"
python -m GUI.main_gui "$@"
EOL

# Make the launcher executable
chmod +x "$APP_MACOS/$APP_NAME"

# Copy the icon to the resources
if [ -f "$ICON_DEST" ]; then
    cp "$ICON_DEST" "$APP_RESOURCES/AppIcon.icns"
    status "Application icon added to bundle"
else
    warning "Could not find application icon"
fi

# Create a simple launcher script in the project directory
status "Creating launcher script..."
cat > "$PROJECT_ROOT/start_fret_tool.sh" << 'EOF'
#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"

# Run the application
python -m GUI.main_gui "$@"
EOF

# Make the launcher executable
chmod +x "$PROJECT_ROOT/start_fret_tool.sh"

# Create a desktop shortcut
DESKTOP_SHORTCUT="$HOME/Desktop/$APP_NAME.desktop"
cat > "$DESKTOP_SHORTCUT" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=FRET Analysis Tool
Exec=$APP_PATH/Contents/MacOS/$APP_NAME
Icon=$APP_RESOURCES/AppIcon.icns
Terminal=false
Categories=Science;Biology;
EOF

# Make the desktop shortcut executable
chmod +x "$DESKTOP_SHORTCUT"

# Finalize application bundle
status "Finalizing $APP_NAME.app..."

# Set the application icon
if [ -f "$ICON_DEST" ]; then
    # Convert the icon to icns format if needed
    if [ ! -f "$PROJECT_ROOT/AppIcon.icns" ]; then
        cp "$ICON_DEST" "$PROJECT_ROOT/AppIcon.icns"
    fi
    
    # Set the icon for the app bundle
    Rez -append "$PROJECT_ROOT/AppIcon.icns" -o "$APP_PATH/Icon"
    SetFile -a C "$APP_PATH"
fi

# Set permissions
chmod -R 755 "$APP_PATH"
chmod +x "$APP_PATH/Contents/MacOS/$APP_NAME"

# Verify the app bundle
if [ -d "$APP_PATH" ]; then
    success "Successfully created $APP_NAME.app in Applications folder"
    status "You can now launch $APP_NAME from:"
    echo "  • Applications folder"
    echo "  • Desktop shortcut"
    echo "  • Terminal: $PROJECT_ROOT/start_fret_tool.sh"
else
    warning "Failed to create application bundle"
    status "You can still run the application using:"
    echo "  $PROJECT_ROOT/start_fret_tool.sh"
fi

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
