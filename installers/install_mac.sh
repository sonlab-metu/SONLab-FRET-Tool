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
INSTALL_DIR="$PROJECT_ROOT"
VENV_DIR="$INSTALL_DIR/venv"

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

# Function to check if Python version is at least 3.10
check_python_version() {
    local python_cmd=$1
    local version
    version=$($python_cmd -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null)
    if [ $? -eq 0 ]; then
        # Compare version numbers
        if [ "$(printf '%s\n' "3.10" "$version" | sort -V | head -n1)" = "3.10" ]; then
            return 0  # Python 3.10 or higher found
        fi
    fi
    return 1  # Python 3.10+ not found
}

# Check for Python 3.10
PYTHON_CMD="python3.10"
if ! check_python_version "$PYTHON_CMD"; then
    # Try with python3
    PYTHON_CMD="python3"
    if ! check_python_version "$PYTHON_CMD"; then
        warning "Python 3.10+ is required but not found."
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
        fi
    fi
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

# Create installation directory
status "Preparing installation directory..."
mkdir -p "$INSTALL_DIR" || error "Failed to create installation directory"

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
section "Setting Up Python Environment"
status "Creating Python virtual environment with Python 3.10..."
if [ -d "$VENV_DIR" ]; then
    warning "Virtual environment already exists at $VENV_DIR"
    echo -n "Do you want to recreate it? [y/N] "
    read -r
    if [[ "$REPLY" =~ ^[Yy] ]]; then
        rm -rf "$VENV_DIR"
        $PYTHON_CMD -m venv "$VENV_DIR" || error "Failed to create virtual environment with Python 3.10"
    fi
else
    $PYTHON_CMD -m venv "$VENV_DIR" || error "Failed to create virtual environment with Python 3.10"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate" || error "Failed to activate virtual environment"

# Upgrade pip
status "Upgrading pip..."
python3 -m pip install --upgrade pip || warning "Failed to upgrade pip, continuing anyway..."

# Install packages from requirements.txt
status "Installing Python packages..."
pip install -r "$SCRIPT_DIR/requirements.txt" || error "Failed to install requirements"

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

# Set up application files
section "Setting Up Application Files"
status "Creating application directory structure..."
APP_DIR="$INSTALL_DIR/app"
ICON_DIR="$APP_DIR/icons"
LUT_DIR="$APP_DIR/luts"

# Create necessary directories
for dir in "$ICON_DIR" "$LUT_DIR"; do
    mkdir -p "$dir" || warning "Failed to create directory: $dir"
done

# Copy Python files
status "Copying Python files..."
cp "$PROJECT_ROOT/"*.py "$APP_DIR/" 2>/dev/null || warning "No Python files found to copy"

# Handle application icon
status "Creating application icon..."
ICONSRC="$PROJECT_ROOT/GUI/logos/logo.png"
ICONSET="$APP_DIR/icon.iconset"
ICON_DEST="$APP_DIR/AppIcon.icns"

# Create logos directory in app folder
mkdir -p "$ICON_DIR" || warning "Failed to create icons directory"

if [ -f "$ICONSRC" ]; then
    mkdir -p "$ICONSET" || warning "Failed to create iconset directory"
    
    # Generate icons in different sizes
    sizes=(16 32 64 128 256 512)
    for size in "${sizes[@]}"; do
        sips -z $size $size "$ICONSRC" --out "$ICONSET/icon_${size}x${size}.png" || \
            warning "Failed to create ${size}x${size} icon"
        
        # Create @2x versions for Retina displays
        if [ $size -ge 32 ]; then
            double_size=$((size * 2))
            sips -z $double_size $double_size "$ICONSRC" --out "$ICONSET/icon_${size}x${size}@2x.png" || \
                warning "Failed to create ${size}x${size}@2x icon"
        fi
    done
    
    # Create .icns file
    if [ -d "$ICONSET" ]; then
        iconutil -c icns "$ICONSET" -o "$ICON_DEST" || warning "Failed to create .icns file"
        rm -rf "$ICONSET"
    fi
    
    # Copy original icons
    cp "$ICONSRC" "$ICON_DIR/" || warning "Failed to copy logo.png"
    [ -f "$PROJECT_ROOT/GUI/logos/icon.png" ] && \
        cp "$PROJECT_ROOT/GUI/logos/icon.png" "$ICON_DIR/" 2>/dev/null || true
    [ -f "$PROJECT_ROOT/GUI/logos/icon.ico" ] && \
        cp "$PROJECT_ROOT/GUI/logos/icon.ico" "$ICON_DIR/" 2>/dev/null || true
else
    warning "logo.png not found in GUI/logos directory, skipping icon creation"
    # Try to find and copy any available icon
    for icon in "$PROJECT_ROOT/GUI/logos/"*.{png,ico}; do
        if [ -f "$icon" ]; then
            cp "$icon" "$ICON_DIR/" && status "Copied $(basename "$icon") to icons directory"
        fi
    done
fi

# Copy LUT files
status "Copying LUT files..."
if [ -d "$PROJECT_ROOT/lut_files" ]; then
    cp -r "$PROJECT_ROOT/lut_files/"* "$LUT_DIR/" 2>/dev/null || \
        warning "Failed to copy LUT files"
else
    cp "$PROJECT_ROOT/"*.lut "$LUT_DIR/" 2>/dev/null || \
        warning "No LUT files found to copy"
fi

# Copy JSON config files
status "Copying configuration files..."
cp "$PROJECT_ROOT/"*.json "$APP_DIR/" 2>/dev/null || \
    warning "No JSON configuration files found to copy"

# Copy GUI directory if it exists
if [ -d "$PROJECT_ROOT/GUI" ]; then
    status "Copying GUI files..."
    cp -r "$PROJECT_ROOT/GUI" "$APP_DIR/" || \
        warning "Failed to copy GUI directory"
fi

# Create macOS application bundle
section "Creating macOS Application"
APP_BUNDLE="$INSTALL_DIR/SONLab FRET Tool.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"

# Clean up any existing app bundle
[ -d "$APP_BUNDLE" ] && rm -rf "$APP_BUNDLE"

# Create bundle structure
status "Creating application bundle structure..."
mkdir -p "$APP_MACOS" "$APP_RESOURCES" || \
    error "Failed to create application bundle structure"

# Create Info.plist
cat > "$APP_CONTENTS/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundleDisplayName</key>
    <string>$APP_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>com.sonlab.frettool</string>
    <key>CFBundleVersion</key>
    <string>2.0.2</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0.2</string>
    <key>CFBundleExecutable</key>
    <string>SONLab_FRET_Tool</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.icns</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.science-research</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>This app requires microphone access for certain features.</string>
    <key>NSCameraUsageDescription</key>
    <string>This app requires camera access for certain features.</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

# Create the launcher script
status "Creating launcher script..."
cat > "$APP_MACOS/SONLab_FRET_Tool" << 'EOL'
#!/bin/bash
# SONLab FRET Tool Launcher for macOS
# This script launches the application with the correct Python environment

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
VENV_DIR="$APP_ROOT/venv"
APP_DIR="$APP_ROOT/app"

# Set environment variables
export PYTHONUNBUFFERED=1
export PYTHONPATH="$APP_DIR:$PYTHONPATH"

# Activate virtual environment
source "$VENV_DIR/bin/activate" || {
    osascript -e 'display notification "Failed to activate Python virtual environment" with title "SONLab FRET Tool Error"'
    exit 1
}

# Set working directory
cd "$APP_DIR" || {
    osascript -e 'display notification "Failed to change to application directory" with title "SONLab FRET Tool Error"'
    exit 1
}

# Run the application
python3 -m GUI.main_gui "$@"
EXIT_CODE=$?

# Show error message if the application crashed
if [ $EXIT_CODE -ne 0 ]; then
    osascript -e "display notification \"Application exited with code $EXIT_CODE\" with title \"SONLab FRET Tool Crashed\""
fi

exit $EXIT_CODE
EOL

# Make the launcher executable
chmod +x "$APP_MACOS/SONLab_FRET_Tool"

# Copy icon to resources
if [ -f "$APP_DIR/AppIcon.icns" ]; then
    cp "$APP_DIR/AppIcon.icns" "$APP_RESOURCES/" || warning "Failed to copy app icon"
fi

# Create Applications folder shortcut
status "Creating Applications folder shortcut..."
ln -sf "$APP_BUNDLE" "$HOME/Applications/$(basename "$APP_BUNDLE")" 2>/dev/null || \
    warning "Failed to create Applications folder shortcut"

# Finalize installation
section "Installation Complete!"
success "$APP_NAME has been successfully installed to:"
echo -e "  ${BOLD}$INSTALL_DIR${NC}\n"

echo -e "${GREEN}You can now launch the application using one of these methods:${NC}"
echo "1. From your Applications folder: $HOME/Applications/$(basename "$APP_BUNDLE")"
echo "2. From the installation directory: open '$APP_BUNDLE'"
echo -e "\n${YELLOW}Note:${NC} If you see a security warning when first opening the app, please:"
echo "  1. Right-click on the app and select 'Open'"
echo "  2. Click 'Open' in the security dialog"
echo -e "\n${GREEN}To uninstall:${NC}"
echo "Simply delete the installation directory: $INSTALL_DIR"

# Open the installation directory in Finder
if [ -d "/usr/bin/open" ]; then
    echo -e "\n${BLUE}Opening installation directory in Finder...${NC}"
    open "$INSTALL_DIR"
fi
# Verify installation
status "Verifying installation..."
if [ ! -d "$VENV_DIR" ] || [ ! -d "$APP_DIR" ]; then
    error "Installation verification failed. Some components are missing."
fi

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

# Run the application using the virtual environment's Python
exec "$VENV_DIR/bin/python" -m GUI.main_gui "$@"
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
