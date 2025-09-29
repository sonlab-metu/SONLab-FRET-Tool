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
ICON_SRC="$PROJECT_ROOT/GUI/logos/logo.png"
ICON_DEST="$PROJECT_ROOT/AppIcon.icns"

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
    # Try with python3.10 from Homebrew if installed
    if [ -f "/usr/local/bin/python3.10" ]; then
        PYTHON_CMD="/usr/local/bin/python3.10"
        if check_python_version "$PYTHON_CMD"; then
            status "Found Python 3.10 at $PYTHON_CMD"
        fi
    else
        # Try with python3
        PYTHON_CMD="python3"
    fi
    
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
        if ! pip install torch torchvision torchaudio; then
            warning "Failed to install PyTorch with MPS support. Trying with --no-cache-dir..."
            if ! pip install --no-cache-dir torch torchvision torchaudio; then
                error "Failed to install PyTorch with MPS support"
            fi
        fi
        ;;
    *)
        # CPU-only version (default)
        if ! pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu; then
            warning "Failed to install CPU-only PyTorch. Trying with --no-cache-dir..."
            if ! pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu; then
                error "Failed to install CPU-only PyTorch"
            fi
        fi
        ;;
esac

# Set up paths for the application
APP_PATH="/Applications/$APP_NAME.app"
APP_CONTENTS="$APP_PATH/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"

# Ensure we have the required directories
mkdir -p "$PROJECT_ROOT/GUI/logos" "$PROJECT_ROOT/lut_files" || error "Failed to create required directories"

# Create macOS application bundle
section "Creating macOS Application"

# Remove existing app if it exists
if [ -d "$APP_PATH" ]; then
    status "Removing existing $APP_NAME.app..."
    rm -rf "$APP_PATH"
fi

# Create the app bundle structure
status "Creating application bundle..."
mkdir -p "$APP_MACOS"
mkdir -p "$APP_RESOURCES"

# Create the main executable
APP_MAIN="$APP_MACOS/$APP_NAME"
cat > "$APP_MAIN" << 'EOL'
#!/bin/bash
# Get the directory of the app bundle
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
# Use the directory where the app bundle is located
PROJECT_DIR="$(dirname "$SCRIPT_DIR")/$(basename "$SCRIPT_DIR/..")"

# Activate virtual environment
source "$PROJECT_DIR/venv/bin/activate"

# Run the application
exec python -m GUI.main_gui "$@"
EOL

# Make the main executable
chmod +x "$APP_MAIN"

# Create Info.plist
cat > "$APP_CONTENTS/Info.plist" << EOL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$APP_NAME</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.icns</string>
    <key>CFBundleIdentifier</key>
    <string>org.sonlab.frettool</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
</dict>
</plist>
EOL

# Handle application icon
if [ -f "$ICON_SRC" ]; then
    status "Creating application icon..."
    # Create iconset directory
    ICONSET_DIR="$PROJECT_ROOT/$APP_NAME.iconset"
    mkdir -p "$ICONSET_DIR"
    
    # Generate icons in different sizes
    sips -z 16 16 "$ICON_SRC" --out "$ICONSET_DIR/icon_16x16.png"
    sips -z 32 32 "$ICON_SRC" --out "$ICONSET_DIR/icon_16x16@2x.png"
    sips -z 32 32 "$ICON_SRC" --out "$ICONSET_DIR/icon_32x32.png"
    sips -z 64 64 "$ICON_SRC" --out "$ICONSET_DIR/icon_32x32@2x.png"
    sips -z 128 128 "$ICON_SRC" --out "$ICONSET_DIR/icon_128x128.png"
    sips -z 256 256 "$ICON_SRC" --out "$ICONSET_DIR/icon_128x128@2x.png"
    sips -z 256 256 "$ICON_SRC" --out "$ICONSET_DIR/icon_256x256.png"
    sips -z 512 512 "$ICON_SRC" --out "$ICONSET_DIR/icon_256x256@2x.png"
    sips -z 512 512 "$ICON_SRC" --out "$ICONSET_DIR/icon_512x512.png"
    
    # Create .icns file
    iconutil -c icns "$ICONSET_DIR" -o "$ICON_DEST"
    
    # Clean up
    rm -rf "$ICONSET_DIR"
    
    # Copy icon to app bundle
    cp "$ICON_DEST" "$APP_RESOURCES/AppIcon.icns"
    status "Application icon created and added to bundle"
else
    warning "Could not find source icon at $ICON_SRC"
fi

# Create a launcher script in the project directory
status "Creating launcher script..."
cat > "$PROJECT_ROOT/start_${APP_NAME// /_}.sh" << EOF
#!/bin/bash
# Get the directory where this script is located
SCRIPT_DIR="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" && pwd )"

# Check if virtual environment exists
if [ ! -d "\$SCRIPT_DIR/venv" ]; then
    echo "Error: Virtual environment not found at \$SCRIPT_DIR/venv"
    echo "Please run the installer again to set up the environment"
    exit 1
fi

# Activate virtual environment
source "\$SCRIPT_DIR/venv/bin/activate"

# Run the application
exec python -m GUI.main_gui "\$@"
EOF

# Make the launcher executable
# Make the launcher executable
chmod +x "$PROJECT_ROOT/start_${APP_NAME// /_}.sh"

# Finalize application bundle
status "Finalizing $APP_NAME.app..."

# Set permissions
chmod -R 755 "$APP_PATH"
chmod +x "$APP_PATH/Contents/MacOS/$APP_NAME"

# Create desktop shortcut
DESKTOP_SHORTCUT="$HOME/Desktop/$APP_NAME.desktop"
cat > "$DESKTOP_SHORTCUT" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=FRET Analysis Tool
Exec=$APP_PATH/Contents/MacOS/$APP_NAME
Icon=$APP_PATH/Contents/Resources/AppIcon.icns
Terminal=false
Categories=Science;Biology;
EOF
chmod +x "$DESKTOP_SHORTCUT"

# Verify the app bundle
if [ -d "$APP_PATH" ]; then
    success "Installation completed successfully!"
    echo -e "\n${GREEN}You can now run $APP_NAME using one of these methods:${NC}"
    echo "1. Double-click the '$APP_NAME' app in your Applications folder"
    echo "2. Double-click the '$APP_NAME' icon on your Desktop"
    echo "3. Run from terminal: ${BOLD}$PROJECT_ROOT/start_${APP_NAME// /_}.sh${NC}"
    echo ""
    echo "Note: If you see a security warning when first running the app:"
    echo "  1. Right-click the app in Finder"
    echo "  2. Select 'Open'"
    echo "  3. Click 'Open' in the security dialog"
else
    warning "Failed to create application bundle"
    status "You can still run the application using:"
    echo "  $PROJECT_ROOT/start_${APP_NAME// /_}.sh"
    echo "  $PYTHON_CMD -m GUI.main_gui"
fi

# Create desktop shortcut
DESKTOP_SHORTCUT="$HOME/Desktop/${APP_NAME}.desktop"
cat > "$DESKTOP_SHORTCUT" << EOL
[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=FRET Analysis Tool
Exec=$APP_PATH/Contents/MacOS/$APP_NAME
Icon=$APP_PATH/Contents/Resources/AppIcon.icns
Terminal=false
Categories=Science;Biology;
EOL
chmod +x "$DESKTOP_SHORTCUT"

# Print completion message
section "Installation Complete!"
echo -e "${GREEN}SONLab FRET Tool has been successfully installed!${NC}"
echo -e "Application bundle: ${BOLD}$APP_PATH${NC}"
echo -e "Launcher script:    ${BOLD}$PROJECT_ROOT/start_${APP_NAME// /_}.sh${NC}"
echo ""
echo -e "${GREEN}You can now run the application using one of these methods:${NC}"
echo -e "1. Double-click the 'SONLab FRET Tool' app in your Applications folder"
echo -e "2. Double-click the 'SONLab FRET Tool' icon on your Desktop"
echo -e "3. Run from terminal: ${BOLD}$INSTALL_DIR/start_fret_tool.sh${NC}"
echo ""
echo -e "${YELLOW}Note: If you see a security warning when opening the app, right-click the app"
echo -e "and select 'Open' to bypass the security check. You'll only need to do this once.${NC}"
