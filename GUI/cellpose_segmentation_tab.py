"""
Cellpose & Manual Segmentation tab for the SONLab FRET Analysis Tool

This tab combines both automated segmentation using Cellpose and manual segmentation
capabilities in a single interface. Users can:
- Load and view microscopy images
- Perform automated segmentation using Cellpose
- Manually add, edit, or delete ROIs
- Adjust image display settings
- Save and transfer segmentation results to the FRET analysis tab
"""
import os
import sys
import time
import numpy as np
import tifffile
import cv2
import torch
import warnings

# Suppress specific CUDA initialization warnings that can occur on systems without
# compatible GPUs. This keeps the console output clean for users running on CPU-only
# machines while still allowing genuine warnings to surface.
warnings.filterwarnings(
    "ignore",
    message=r"CUDA initialization: .*forward compatibility was attempted.*",
    category=UserWarning,
    module=r"torch\.cuda",
)

# -----------------------------------------------------------------------------
# Utility function to safely query CUDA without triggering hard errors on
# systems without compatible hardware/drivers. Torch can raise obscure runtime
# errors (e.g., error 804) when attempting to initialise CUDA on unsupported
# hardware. We wrap the check to catch these cases and gracefully fall back to
# CPU.
# -----------------------------------------------------------------------------

def _safe_cuda_available():
    """Return True if CUDA is available, otherwise False.

    This helper catches all exceptions that may be raised during the CUDA
    initialisation step (e.g., forward-compatibility error 804) and ensures the
    application continues on CPU without flooding the console with warnings.
    """
    try:
        # Catch warnings during the availability check to prevent noisy output
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            return torch.cuda.is_available() and torch.cuda.device_count() > 0
    except Exception:
        return False
import matplotlib.pyplot as plt
import importlib.metadata
import shutil
from pathlib import Path

# For CZI file support
try:
    import czifile
    CZI_AVAILABLE = True
except ImportError:
    CZI_AVAILABLE = False
    print("Warning: czifile module not found. CZI file support will be disabled.")

# PyQt5 Imports
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QListWidget, QListWidgetItem, QMessageBox, 
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QSplitter,
    QSlider, QSizePolicy, QToolButton, QStyle, QToolTip, QProgressDialog, QScrollArea,
    QTabWidget, QInputDialog, QProgressBar, QApplication
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMimeData, QTimer, QSize, QPoint, QObject, QEvent
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QDragEnterEvent, QDropEvent

# Matplotlib imports
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.widgets import PolygonSelector
from matplotlib.patches import Polygon as MplPolygon

# Debug information
print("\n=== Python Environment ===")
print(f"Python version: {sys.version}")
print(f"Working directory: {os.getcwd()}")

# Import Cellpose with error handling
CELLPOSE_AVAILABLE = False
try:
    import cellpose
    from cellpose import models, utils, io
    
    # Get Cellpose version
    try:
        cellpose_version = importlib.metadata.version('cellpose')
        print(f"Cellpose version: {cellpose_version}")
    except:
        print("Could not determine Cellpose version")
    
    # Debug available models and functions
    print("\n=== Cellpose Debug Info ===")
    print(f"Cellpose available: {CELLPOSE_AVAILABLE}")
    print(f"Models module: {dir(models)}")
    
    if hasattr(models, 'MODEL_NAMES'):
        print(f"Available models: {models.MODEL_NAMES}")
    else:
        print("MODEL_NAMES not found in models")
        
    CELLPOSE_AVAILABLE = True
    
except ImportError as e:
    print(f"\n=== Cellpose Import Error ===")
    print(f"Error importing Cellpose: {e}")
    print("Please install Cellpose with: pip install cellpose")
    print("Or with GPU support: pip install cellpose[all]")
    
# Import OpenCV with error handling
try:
    import cv2
    print(f"\nOpenCV version: {cv2.__version__}")
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("\nWarning: OpenCV not available. Some features may be limited.")

class CellposeSegmentationTab(QWidget):
    """
    Combined Cellpose and Manual Segmentation Tab
    
    This widget provides both automated segmentation using Cellpose and manual
    segmentation capabilities in a single interface. It allows users to:
    - Load and view microscopy images
    - Perform automated segmentation using Cellpose
    - Manually add, edit, or delete ROIs
    - Adjust image display settings
    - Save and transfer segmentation results to the FRET analysis tab
    """
    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.image_paths = []
        self.current_image = None
        self.current_mask = None
        self.current_image_path = None
        self.current_labels = None  # To store the current segmentation labels
        self.current_image_has_segmentation = False  # Track if current image has been segmented
        self.model = None
        self.poly_selector = None  # For ROI drawing
        self.roi_items = []  # To store ROI items
        self.parent_widget = parent  # Store reference to parent for tab switching
        self._figures = []  # Track all figures for cleanup
        self.splitter = None  # Will be initialized in init_ui()
        
        # Default display settings (will be overridden by config)
        self.brightness = 1.0
        self.contrast = 1.0
        
        # Track theme state
        self.current_theme = 'light'  # Will be updated on init_ui
        
        # Default output directory (will be overridden by config)
        self.output_dir = os.path.expanduser("~")  # Default to user's home directory
        
        # Default Cellpose parameters (will be overridden by config)
        self.default_params = {
            'model': 'cyto2',
            'diameter': 170.0,
            'flow_threshold': 0.4,
            'cellprob_threshold': 0.0,
            'min_size': 15000,
            'outline_only': True,
            'adjust_outline': True,
            'outline_thickness': 10
        }
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        self.setAcceptDrops(True)
        self.setAcceptDrops(True)  # Set multiple times to ensure it's enabled
        
        # Initialize UI first
        self.init_ui()
        
        # Connect preference changes to save_preferences with throttling
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        self.contrast_slider.valueChanged.connect(self.on_contrast_changed)
        
        # Connect to parent's theme change signal if available
        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(self.update_theme)
        
        # Update theme based on current application palette
        app = QApplication.instance()
        palette = app.palette()
        self.current_theme = 'dark' if palette.window().color().lightness() < 128 else 'light'
        
        # Connect parameter changes with throttling to prevent excessive saves
        self.model_combo.currentTextChanged.connect(self._throttled_save_prefs)
        self.diameter_spin.valueChanged.connect(self._throttled_save_prefs)
        self.flow_spin.valueChanged.connect(self._throttled_save_prefs)
        self.cellprob_spin.valueChanged.connect(self._throttled_save_prefs)
        self.minsize_spin.valueChanged.connect(self._throttled_save_prefs)
        self.outline_check.toggled.connect(self._throttled_save_prefs)
        self.outline_thickness_check.toggled.connect(self._throttled_save_prefs)
        self.outline_thickness_spin.valueChanged.connect(self._throttled_save_prefs)
        
        # Setup save preferences timer for throttling
        self._save_prefs_timer = QTimer(self)
        self._save_prefs_timer.setSingleShot(True)
        self._save_prefs_timer.setInterval(500)  # 500ms delay
        self._save_prefs_timer.timeout.connect(self.save_preferences)
        # Track whether preferences have unsaved changes
        self._prefs_dirty = False
        
        # Load saved preferences
        self.load_preferences()
        
        # Apply any saved window state
        self._apply_window_state()
        
        # Ensure the FRET tab is accessible
        self.setup_fret_tab_access()
        
        # Add progress dialog attribute
        self.progress_dialog = None

    def close_processing_dialog(self):
        if getattr(self, 'progress_dialog', None):
            self.progress_dialog.close()
            self.progress_dialog = None

    def show_processing_dialog(self, text="Processing..."):
        """Display a modal, non-cancelable progress dialog."""
        if getattr(self, 'progress_dialog', None) is None:
            self.progress_dialog = QProgressDialog(text, None, 0, 0, self)
            self.progress_dialog.setWindowTitle("Please Wait")
            self.progress_dialog.setWindowModality(Qt.ApplicationModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.setAutoClose(False)
            self.progress_dialog.setAutoReset(False)
        self.progress_dialog.setLabelText(text)
        self.progress_dialog.show()
        QApplication.processEvents()
    
    def add_info_icon(self, layout, label_text, widget, tooltip_text):
        """
        Add a label with an info icon that shows a tooltip when hovered.
        
        Args:
            layout: The parent layout to add this widget to
            label_text: Text for the label
            widget: Optional widget to add after the label and info icon
            tooltip_text: Help text to show in the tooltip (will be wrapped)
        """
        from PyQt5.QtWidgets import QHBoxLayout, QLabel, QToolButton, QToolTip
        from PyQt5.QtCore import Qt, QSize
        from PyQt5.QtGui import QFontMetrics, QPalette
        
        # Create container widget and layout
        container = QWidget()
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(5)  # Add some spacing between elements
        
        # Add label
        label = QLabel(label_text)
        hbox.addWidget(label, stretch=1)  # Allow label to expand
        
        # Configure tooltip styling with HTML for wrapping
        tooltip_style = """
            <style>
                body { 
                    white-space: pre-wrap; 
                    max-width: 400px;
                    font-family: "Segoe UI", Arial, sans-serif;
                    font-size: 9pt;
                }
            </style>
            <div>%s</div>
        """ % tooltip_text
        
        # Add info button with styled tooltip
        info_btn = QToolButton()
        info_btn.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_MessageBoxInformation')))
        info_btn.setIconSize(QSize(14, 14))  # Slightly smaller icon
        info_btn.setCursor(Qt.WhatsThisCursor)
        info_btn.setToolTip(tooltip_style)
        info_btn.setStyleSheet("""
            QToolButton {
                border: none;
                padding: 0px;
                margin-left: 2px;
                background: transparent;
            }
            QToolButton:hover {
                background: rgba(128, 128, 128, 20);
                border-radius: 7px;
            }
        """)
        hbox.addWidget(info_btn, alignment=Qt.AlignLeft)
        
        # Add the widget if provided
        if widget is not None:
            hbox.addWidget(widget, stretch=2)  # Allow widget to take more space
        
        hbox.addStretch()
        layout.addWidget(container)
        
        return container
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event to accept image files including CZI"""
        if event.mimeData().hasUrls():
            # Always accept the proposed action if there are URLs
            # We'll validate the actual files in dropEvent
            event.acceptProposedAction()
            # Show drop hint if it exists
            if hasattr(self, 'drop_hint'):
                self.drop_hint.show()
            return
                    
        print("Drag enter ignored - no valid files found")
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave event"""
        event.accept()
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop event to load CZI and TIFF files"""
        print("\n=== Drop Event Triggered ===")
        print(f"MIME formats: {event.mimeData().formats()}")
        
        if not event.mimeData().hasUrls():
            print("No URLs in mime data")
            event.ignore()
            return
            
        # Get list of valid image files
        image_files = []
        urls = event.mimeData().urls()
        print(f"Number of URLs: {len(urls)}")
        
        for i, url in enumerate(urls):
            try:
                file_path = url.toLocalFile()
                print(f"\nProcessing URL {i+1}:")
                print(f"  - URL: {url.toString()}")
                print(f"  - Local file: {file_path}")
                print(f"  - URL scheme: {url.scheme()}")
                
                # Skip if no file path
                if not file_path:
                    print("  - Skipping: Empty file path")
                    continue
                    
                # Normalize the path and check if it exists
                file_path = os.path.abspath(file_path)
                file_exists = os.path.exists(file_path)
                print(f"  - Absolute path: {file_path}")
                print(f"  - File exists: {file_exists}")
                
                if not file_exists:
                    print(f"  - Skipping: File does not exist")
                    continue
                    
                # Check file extension (case insensitive)
                file_path_lower = file_path.lower()
                is_czi = file_path_lower.endswith('.czi')
                is_tiff = file_path_lower.endswith(('.tif', '.tiff'))
                
                if is_czi or is_tiff:
                    print(f"  - Found {'CZI' if is_czi else 'TIFF'} file")
                    
                    # For CZI files, verify we can open them
                    if is_czi:
                        if not CZI_AVAILABLE:
                            print("  - Skipping: CZI support not available (install czifile package)")
                            continue
                            
                        try:
                            # Quick check if file is a valid CZI
                            with open(file_path, 'rb') as f:
                                header = f.read(4)
                                print(f"  - File header: {header}")
                                if header != b'ZISR':
                                    print(f"  - Error: Not a valid CZI file (expected 'ZISR' header)")
                                    continue
                                    
                            # Test opening with czifile
                            print("  - Testing CZI file with czifile...")
                            try:
                                with czifile.CziFile(file_path) as czi:
                                    print(f"  - Successfully opened CZI file")
                                    print(f"  - CZI shape: {czi.shape}")
                                    print(f"  - CZI size: {czi.size}")
                                    if hasattr(czi, 'metadata'):
                                        print("  - CZI metadata available")
                                    else:
                                        print("  - No CZI metadata available")
                                
                                # If we got here, the file is valid
                                print("  - CZI file is valid")
                                image_files.append(file_path)
                                
                            except Exception as czierr:
                                print(f"  - Error opening CZI with czifile: {str(czierr)}")
                                continue
                                
                        except Exception as e:
                            print(f"  - Error checking CZI file: {str(e)}")
                            continue
                    else:
                        # For TIFF files, just add them
                        image_files.append(file_path)
                        print(f"  - Added TIFF file")
                else:
                    print(f"  - Skipping: Unsupported file type")
                    
            except Exception as e:
                print(f"  - Error processing file: {str(e)}")
                continue
        
        print(f"\nFound {len(image_files)} valid image files to add")
        
        if not image_files:
            print("No valid image files found in drop")
            QMessageBox.warning(self, "Unsupported File", 
                              "Only CZI, TIFF, and TIF files are supported.")
            event.ignore()
            return
            
        print("\n=== Adding files to image list ===")
        # Add files to the image list
        self._add_image_paths(image_files)
        event.acceptProposedAction()
        
        # Force UI update
        QApplication.processEvents()
        print("=== Drop Event Complete ===\n")
    
    def _convert_czi_to_tiff(self, czi_path):
        """Convert CZI file to 3-frame TIFF stack (FRET, Donor, Acceptor)
        
        Returns:
            str: Path to the saved TIFF file, or None if conversion failed
        """
        print(f"Converting CZI to TIFF: {czi_path}")
        
        # Create output path with .tif extension
        base_path = os.path.splitext(czi_path)[0]
        output_path = f"{base_path}.tif"
        
        try:
            # Read the CZI file
            with czifile.CziFile(czi_path) as czi:
                images = czi.asarray()
                print(f"CZI shape: {images.shape}")
                
                try:
                    # Extract channels based on the shape
                    # Handle both 7D and 8D array shapes
                    # Expected shapes:
                    # 7D: [T=1, Scene=1, C=4, Z=1, Y, X, S=1]
                    # 8D: [T=1, Scene=1, C=4, Z=1, 1, Y, X, S=1]
                    if images.ndim == 7:
                        # 7D array [T, Scene, C, Z, Y, X, S]
                        _, _, num_channels, _, height, width, _ = images.shape
                        # Extract channels (0-based indexing)
                        fret = images[0, 0, 0, 0, :, :, 0]  # Channel 0: FRET
                        donor = images[0, 0, 1, 0, :, :, 0]  # Channel 1: Donor
                        acceptor = images[0, 0, 3, 0, :, :, 0]  # Channel 3: Acceptor
                        # Store all channels for 4-frame saving
                        channels = [images[0, 0, i, 0, :, :, 0] for i in range(num_channels)]
                    elif images.ndim == 8:
                        # 8D array [T, Scene, C, Z, 1, Y, X, S]
                        _, _, num_channels, _, _, height, width, _ = images.shape
                        # Extract channels (0-based indexing)
                        fret = images[0, 0, 0, 0, 0, :, :, 0]  # Channel 0: FRET
                        donor = images[0, 0, 1, 0, 0, :, :, 0]  # Channel 1: Donor
                        acceptor = images[0, 0, 3, 0, 0, :, :, 0]  # Channel 3: Acceptor
                        # Store all channels for 4-frame saving
                        channels = [images[0, 0, i, 0, 0, :, :, 0] for i in range(num_channels)]
                    else:
                        print(f"Unexpected CZI shape: {images.shape}. Expected 7 or 8 dimensions.")
                        return None
                    
                    # Verify we have at least 4 channels
                    if num_channels < 4:
                        print(f"Expected at least 4 channels, found {num_channels}")
                        return None
                    
                    # Convert to float32
                    fret = fret.astype(np.float32)
                    donor = donor.astype(np.float32)
                    acceptor = acceptor.astype(np.float32)
                    
                    # Stack into single 3-frame TIFF [3, H, W]
                    output_stack = np.stack([fret, donor, acceptor], axis=0)
                    
                    # Store the original CZI data for 4-frame saving
                    self.original_czi_data = np.stack([fret, donor, acceptor], axis=0)
                    
                    # Save as multi-page TIFF
                    tifffile.imwrite(
                        output_path, 
                        output_stack,
                        photometric='minisblack',
                        metadata={'axes': 'CYX'}
                    )
                    print(f"Saved 3-frame TIFF: {output_path}")
                    return output_path
                    
                except IndexError as e:
                    print(f"Error extracting channels: {e}")
                    print(f"CZI shape: {images.shape}")
                    print("Expected shape: [T=1, Scene=1, C=4, Z=1, Y, X, S=1]")
                    return None
                    
        except Exception as e:
            import traceback
            print(f"Error converting CZI to TIFF: {e}")
            print(traceback.format_exc())
            return None
    
    def _add_image_paths(self, file_paths):
        """Helper method to add image paths to the list"""
        print("\n=== _add_image_paths ===")
        print(f"Input file_paths: {file_paths}")
        
        if not file_paths:
            print("No file paths provided")
            return
            
        # Initialize image_paths if it doesn't exist
        if not hasattr(self, 'image_paths') or not isinstance(self.image_paths, list):
            print("Initializing image_paths")
            self.image_paths = []
        
        # Process each file
        processed_paths = []
        
        # Debug: Print current image_paths
        print(f"Current image_paths before adding: {self.image_paths}")
        
        for file_path in file_paths:
            file_path = os.path.abspath(str(file_path))
            print(f"\nProcessing: {file_path}")
            
            # Skip if already in list
            if file_path in [os.path.abspath(str(p)) for p in self.image_paths]:
                print(f"  - Already in list, skipping")
                continue
                
            # Handle CZI files
            if file_path.lower().endswith('.czi'):
                if not CZI_AVAILABLE:
                    print("  - CZI support not available. Install with 'pip install czifile'")
                    continue
                    
                # Convert CZI to TIFF
                tiff_path = self._convert_czi_to_tiff(file_path)
                if tiff_path and os.path.exists(tiff_path):
                    print(f"  - Converted CZI to TIFF: {tiff_path}")
                    processed_paths.append(tiff_path)
                else:
                    print(f"  - Failed to convert CZI: {file_path}")
            
            # Handle TIFF files
            elif file_path.lower().endswith(('.tif', '.tiff')):
                if os.path.exists(file_path):
                    print(f"  - Adding TIFF file: {file_path}")
                    processed_paths.append(file_path)
                else:
                    print(f"  - File not found: {file_path}")
            
            else:
                print(f"  - Unsupported file type: {file_path}")
        
        if not processed_paths:
            msg = "No valid files to add"
            print(msg)
            self.update_status(msg)
            return
        
        # Add new files to the list
        self.image_paths.extend(processed_paths)
        
        # Update the list widget
        self.update_image_list_widget()
        
        # Select the first new file and ensure preview updates
        if self.image_list.count() > 0:
            first_new_index = len(self.image_paths) - len(processed_paths)
            self.image_list.setCurrentRow(first_new_index)
            print(f"Selected new file at index {first_new_index}")
            
            # Manually trigger selection change to ensure preview updates
            current_item = self.image_list.currentItem()
            if current_item:
                self.on_image_selected(current_item)
        
        # Update status
        status_msg = f"Added {len(processed_paths)} new image(s)"
        print(status_msg)
        self.update_status(status_msg)
        
        # Force UI update
        QApplication.processEvents()
        print("=== End _add_image_paths ===\n")
        
    def update_image_list_widget(self):
        """Update the image list widget with current image_paths"""
        print("Updating image list widget...")
        print(f"Current image_paths: {self.image_paths}")
        
        if not hasattr(self, 'image_list'):
            print("Error: image_list widget doesn't exist!")
            return
            
        # Store current selection
        current_path = self.current_image_path if hasattr(self, 'current_image_path') else None
        
        # Block signals while updating to prevent selection change events
        self.image_list.blockSignals(True)
        
        try:
            # Clear the list widget
            self.image_list.clear()
            
            # Add all files to the list widget
            for i, path in enumerate(self.image_paths):
                try:
                    # Use basename for display but store full path in tooltip
                    display_name = os.path.basename(path)
                    item = QListWidgetItem(display_name)
                    item.setToolTip(path)  # Show full path in tooltip
                    item.setData(Qt.UserRole, path)  # Store full path in item data
                    self.image_list.addItem(item)
                    print(f"  - Added to list: {display_name}")
                    
                except Exception as e:
                    print(f"Error adding {path} to list: {str(e)}")
            
            # Restore selection if possible
            if current_path and current_path in self.image_paths:
                index = self.image_paths.index(current_path)
                if 0 <= index < self.image_list.count():
                    self.image_list.setCurrentRow(index)
                    print(f"  - Restored selection to row {index}")
            
            # If no selection, select the first item
            if self.image_list.currentRow() < 0 and self.image_list.count() > 0:
                self.image_list.setCurrentRow(0)
                
        finally:
            # Always unblock signals when done
            self.image_list.blockSignals(False)
            
        print(f"List widget updated with {self.image_list.count()} items")
        
    def init_ui(self):
        """Initialize the user interface with a stable layout"""
        # Main layout with consistent margins and spacing
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)  # Uniform margins
        main_layout.setSpacing(10)  # Uniform spacing

        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)

        # Left panel - Image list and controls
        left_widget = QWidget()
        left_widget.setMinimumWidth(300)  # Prevent collapse
        left_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        left_panel = QVBoxLayout(left_widget)
        left_panel.setContentsMargins(5, 5, 5, 5)
        left_panel.setSpacing(5)

        # Image list container
        list_container = QVBoxLayout()
        list_container.setSpacing(5)
        list_label = QLabel("Loaded Images:")
        list_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        list_container.addWidget(list_label)

        # Image list widget
        self.image_list = QListWidget()
        self.image_list.setSelectionMode(QListWidget.ExtendedSelection)
        # Use a lambda to handle the current item changed signal
        self.image_list.currentItemChanged.connect(
            lambda current, previous: self.on_image_selected(current, previous)
        )
        self.image_list.setMinimumHeight(150)  # Ensure usable height
        self.image_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        list_container.addWidget(self.image_list, 1)  # Stretch to fill space

        # Button row for Load and Remove
        button_row = QHBoxLayout()
        button_row.setSpacing(5)
        self.btn_load = QPushButton("Load Images")
        self.btn_load.clicked.connect(self.load_images)
        self.btn_load.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button_row.addWidget(self.btn_load)
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self.remove_selected_images)
        self.btn_remove.setToolTip("Remove selected images from the list")
        self.btn_remove.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button_row.addWidget(self.btn_remove)
        button_row.addStretch()
        list_container.addLayout(button_row)
        left_panel.addLayout(list_container)

        # Drag-and-drop placeholder
        self.drop_hint = QLabel("Drag & drop TIFF or CZI files here")
        self.drop_hint.setStyleSheet("""
            QLabel {
                color: #666;
                font-style: italic;
                padding: 10px;
                border: 2px dashed #aaa;
                border-radius: 5px;
                margin: 5px;
                text-align: center;
            }
        """)
        self.drop_hint.setAlignment(Qt.AlignCenter)
        self.drop_hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.drop_hint.setMinimumHeight(50)  # Reserve space
        left_panel.addWidget(self.drop_hint)

        # ROI manager group
        roi_group = QGroupBox("ROI Manager")
        roi_layout = QVBoxLayout()
        roi_layout.setSpacing(5)
        self.roi_list_widget = QListWidget()
        self.roi_list_widget.setMinimumHeight(100)  # Ensure usable height
        self.roi_list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        roi_layout.addWidget(self.roi_list_widget, 1)
        roi_btn_layout = QHBoxLayout()
        self.add_roi_btn = QPushButton("Add ROI")
        self.add_roi_btn.clicked.connect(self.start_roi)
        self.add_roi_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.del_roi_btn = QPushButton("Delete ROI")
        self.del_roi_btn.clicked.connect(self.delete_selected_roi)
        self.del_roi_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        roi_btn_layout.addWidget(self.add_roi_btn)
        roi_btn_layout.addWidget(self.del_roi_btn)
        roi_btn_layout.addStretch()
        roi_layout.addLayout(roi_btn_layout)
        roi_group.setLayout(roi_layout)
        left_panel.addWidget(roi_group)

        # Display settings group
        display_group = QGroupBox("Display Settings")
        display_layout = QVBoxLayout()
        display_layout.setSpacing(5)
        brightness_layout = QHBoxLayout()
        brightness_label = QLabel("Brightness:")
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 200)
        self.brightness_slider.setValue(100)
        self.brightness_slider.setTickPosition(QSlider.TicksBelow)
        self.brightness_slider.setTickInterval(25)
        self.brightness_slider.setSingleStep(5)
        self.brightness_slider.setPageStep(25)
        self.brightness_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.brightness_value = QLabel("100%")
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        brightness_layout.addWidget(brightness_label)
        brightness_layout.addWidget(self.brightness_slider, 1)
        brightness_layout.addWidget(self.brightness_value)
        display_layout.addLayout(brightness_layout)
        contrast_layout = QHBoxLayout()
        contrast_label = QLabel("Contrast:")
        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(0, 200)
        self.contrast_slider.setValue(100)
        self.contrast_slider.setTickPosition(QSlider.TicksBelow)
        self.contrast_slider.setTickInterval(25)
        self.contrast_slider.setSingleStep(5)
        self.contrast_slider.setPageStep(25)
        self.contrast_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.contrast_value = QLabel("100%")
        self.contrast_slider.valueChanged.connect(self.on_contrast_changed)
        contrast_layout.addWidget(contrast_label)
        contrast_layout.addWidget(self.contrast_slider, 1)
        contrast_layout.addWidget(self.contrast_value)
        display_layout.addLayout(contrast_layout)  # Add this line to include contrast layout
        btn_layout = QHBoxLayout()
        auto_btn = QPushButton("Auto")
        auto_btn.setToolTip("Automatically adjust brightness and contrast")
        auto_btn.clicked.connect(self.auto_adjust_display)
        auto_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        reset_btn = QPushButton("Reset")
        reset_btn.setToolTip("Reset to default display settings")
        reset_btn.clicked.connect(self.reset_display_settings)
        reset_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_layout.addWidget(auto_btn)
        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        display_layout.addLayout(btn_layout)
        display_group.setLayout(display_layout)
        left_panel.addWidget(display_group)

        # Action buttons
        button_layout = QVBoxLayout()
        button_layout.setSpacing(5)
        self.btn_run = QPushButton("Run Segmentation")
        self.btn_run.clicked.connect(self.on_run_clicked)
        self.btn_run.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_batch = QPushButton("Batch Segment && Transfer")
        self.btn_batch.clicked.connect(self.batch_segment_and_transfer)
        self.btn_batch.setToolTip("Process all images and transfer to FRET tab with group name")
        self.btn_batch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_save = QPushButton("Save Results")
        self.btn_save.clicked.connect(self.save_results)
        self.btn_save.setToolTip("Save segmentation results to a 'segmented' directory")
        self.btn_save.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Create transfer buttons
        self.btn_save_transfer = QPushButton("Send to FRET Tab")
        self.btn_save_transfer.clicked.connect(self.save_and_transfer)
        self.btn_save_transfer.setToolTip("Save results and transfer to FRET tab with optional group assignment")
        self.btn_save_transfer.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; padding: 5px 10px; border: none; }")
        
        self.btn_send_donor = QPushButton("Send to Donor")
        self.btn_send_donor.clicked.connect(self.send_to_donor)
        self.btn_send_donor.setToolTip("Send current image to Donor channel without group assignment")
        self.btn_send_donor.setStyleSheet("QPushButton { background-color: #2196F3; color: white; padding: 5px 10px; border: none; }")
        
        self.btn_send_acceptor = QPushButton("Send to Acceptor")
        self.btn_send_acceptor.clicked.connect(self.send_to_acceptor)
        self.btn_send_acceptor.setToolTip("Send current image to Acceptor channel without group assignment")
        self.btn_send_acceptor.setStyleSheet("QPushButton { background-color: #F44336; color: white; padding: 5px 10px; border: none; }")
        
        # Set fixed size policy for all buttons
        for btn in [self.btn_save_transfer, self.btn_send_donor, self.btn_send_acceptor]:
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        # Add buttons to layout with spacing
        transfer_button_layout = QHBoxLayout()
        transfer_button_layout.addStretch()
        transfer_button_layout.addWidget(self.btn_send_donor)
        transfer_button_layout.addSpacing(5)
        transfer_button_layout.addWidget(self.btn_send_acceptor)
        transfer_button_layout.addSpacing(5)
        transfer_button_layout.addWidget(self.btn_save_transfer)
        transfer_button_layout.addStretch()
        
        button_layout.addWidget(self.btn_run)
        button_layout.addWidget(self.btn_batch)
        button_layout.addWidget(self.btn_save)
        button_layout.addLayout(transfer_button_layout)
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        button_layout.addWidget(self.status_label)
        button_layout.addStretch()
        left_panel.addLayout(button_layout)

        # Cellpose parameters group using QFormLayout
        params_group = QGroupBox("Cellpose Parameters")
        params_layout = QFormLayout()
        params_layout.setSpacing(5)
        params_layout.setLabelAlignment(Qt.AlignRight)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["cyto2", "cyto", "nuclei", "tissuenet", "livecell"])
        self.model_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_info_icon(params_layout, "Model:", self.model_combo, 
                         "Cellpose model to use. 'cyto2' is recommended for most cell segmentation tasks.")
        self.diameter_spin = QDoubleSpinBox()
        self.diameter_spin.setRange(0, 500)
        self.diameter_spin.setValue(170)
        self.diameter_spin.setSingleStep(1)
        self.diameter_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        diameter_container = QWidget()
        diameter_hbox = QHBoxLayout(diameter_container)
        diameter_hbox.setContentsMargins(0, 0, 0, 0)
        diameter_hbox.addWidget(self.diameter_spin)
        diameter_hbox.addWidget(QLabel("pixels (0=auto)"))
        self.add_info_icon(params_layout, "Cell Diameter:", diameter_container,
                         "Average diameter of cells in pixels. Set to 0 for automatic detection.")
        self.flow_spin = QDoubleSpinBox()
        self.flow_spin.setRange(0.1, 1.0)
        self.flow_spin.setValue(0.4)
        self.flow_spin.setSingleStep(0.1)
        self.flow_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_info_icon(params_layout, "Flow Threshold:", self.flow_spin,
                         "Flow error threshold. Lower values are more accurate but may miss some cells.")
        self.cellprob_spin = QDoubleSpinBox()
        self.cellprob_spin.setRange(-6.0, 6.0)
        self.cellprob_spin.setValue(0.0)
        self.cellprob_spin.setSingleStep(0.1)
        self.cellprob_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_info_icon(params_layout, "Cell Prob. Threshold:", self.cellprob_spin,
                         "Cell probability threshold. Lower values detect more cells but may include more noise.")
        self.minsize_spin = QSpinBox()
        self.minsize_spin.setRange(1, 100000)
        self.minsize_spin.setValue(15000)
        self.minsize_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        minsize_container = QWidget()
        minsize_hbox = QHBoxLayout(minsize_container)
        minsize_hbox.setContentsMargins(0, 0, 0, 0)
        minsize_hbox.addWidget(self.minsize_spin)
        minsize_hbox.addWidget(QLabel("pixels"))
        self.add_info_icon(params_layout, "Min Cell Size:", minsize_container,
                         "Minimum size of objects to keep (in pixels). Smaller objects will be removed.")
        self.outline_check = QCheckBox("Generate outlines only")
        self.outline_check.setChecked(True)
        self.outline_check.setToolTip("When checked, only cell outlines will be generated instead of filled masks.")
        self.outline_check.toggled.connect(self.update_outline_controls)
        params_layout.addRow(self.outline_check)
        self.outline_thickness_check = QCheckBox("Adjust outline thickness")
        self.outline_thickness_check.setChecked(True)
        self.outline_thickness_check.setToolTip("When checked, you can adjust the thickness of the cell outlines.")
        params_layout.addRow(self.outline_thickness_check)
        self.outline_thickness_spin = QSpinBox()
        self.outline_thickness_spin.setRange(1, 20)
        self.outline_thickness_spin.setValue(10)
        self.outline_thickness_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outline_container = QWidget()
        outline_hbox = QHBoxLayout(outline_container)
        outline_hbox.setContentsMargins(0, 0, 0, 0)
        outline_hbox.addWidget(self.outline_thickness_spin)
        self.add_info_icon(params_layout, "Outline Thickness:", outline_container,
                         "Controls the thickness of the cell outlines. Higher values make thicker outlines.")
        self.outline_thickness_check.toggled.connect(self.update_outline_controls)
        self.update_outline_controls()
        params_group.setLayout(params_layout)
        left_panel.addWidget(params_group)

        # Right panel - Image display
        right_widget = QWidget()
        right_widget.setMinimumWidth(400)  # Prevent collapse
        right_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_panel = QVBoxLayout(right_widget)
        right_panel.setContentsMargins(5, 5, 5, 5)
        right_panel.setSpacing(5)

        # Matplotlib figure with dynamic sizing - vertical layout
        fig_num = len(plt.get_fignums()) + 1
        
        # Apply dark/light theme based on current application palette
        app = QApplication.instance()
        palette = app.palette()
        is_dark_theme = palette.window().color().lightness() < 128
        
        # Set matplotlib style based on theme
        if is_dark_theme:
            plt.style.use('dark_background')
            # Additional dark theme settings
            plt.rcParams.update({
                'figure.facecolor': '#2b2b2b',
                'axes.facecolor': '#2b2b2b',
                'savefig.facecolor': '#2b2b2b',
                'text.color': '#f0f0f0',
                'axes.labelcolor': '#f0f0f0',
                'xtick.color': '#f0f0f0',
                'ytick.color': '#f0f0f0',
                'axes.edgecolor': '#6d6d6d',
                'grid.color': '#3a3a3a',
                'figure.titlesize': 'large',
                'figure.titleweight': 'bold',
                'axes.titlesize': 'medium',
                'axes.titleweight': 'bold',
                'xtick.labelsize': 'small',
                'ytick.labelsize': 'small',
                'legend.framealpha': 0.8,
                'legend.facecolor': '#3a3a3a',
                'legend.edgecolor': '#6d6d6d',
            })
        
        # Create figure with theme-appropriate colors
        self.figure, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(8, 8), num=fig_num)
        
        # Set figure and axes background colors based on theme
        if is_dark_theme:
            self.figure.set_facecolor('#2b2b2b')
            for ax in [self.ax1, self.ax2]:
                ax.set_facecolor('#2b2b2b')
        else:
            self.figure.set_facecolor('white')
            for ax in [self.ax1, self.ax2]:
                ax.set_facecolor('white')
        
        # Adjust spacing between subplots
        self.figure.subplots_adjust(hspace=0.3)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setMinimumSize(400, 300)  # Prevent collapse
        self._figures.append(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        self.toolbar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_panel.addWidget(self.toolbar)
        right_panel.addWidget(self.canvas, 1)  # Stretch to fill space

        # Add widgets to splitter
        # Wrap left panel in a scrollable area so controls remain accessible on small windows
        scroll_left = QScrollArea()
        scroll_left.setWidgetResizable(True)
        scroll_left.setWidget(left_widget)
        splitter.addWidget(scroll_left)
        splitter.addWidget(right_widget)
        splitter.setSizes([300, 700])
        main_layout.addWidget(splitter, 1)
        self.setLayout(main_layout)
        
    def save_preferences(self):
        """Save current preferences to config manager"""
        if not self.config:
            print("Config manager not available, cannot save preferences")
            return False
            
        try:
            print("Saving preferences to config...")
            
            # Get current UI values
            model = self.model_combo.currentText()
            diameter = self.diameter_spin.value()
            flow_threshold = self.flow_spin.value()
            cellprob_threshold = self.cellprob_spin.value()
            min_size = self.minsize_spin.value()
            outline_only = self.outline_check.isChecked()
            adjust_outline = self.outline_thickness_check.isChecked()
            outline_thickness = self.outline_thickness_spin.value()
            
            print(f"Saving preferences: model={model}, diameter={diameter}, flow={flow_threshold}, "
                  f"cellprob={cellprob_threshold}, min_size={min_size}, outline_only={outline_only}, "
                  f"adjust_outline={adjust_outline}, outline_thickness={outline_thickness}")
            
            # Save display settings
            self.config.set('cellpose.display.brightness', float(self.brightness))
            self.config.set('cellpose.display.contrast', float(self.contrast))
            
            # Save Cellpose parameters
            self.config.set('cellpose.parameters.model', str(model))
            self.config.set('cellpose.parameters.diameter', float(diameter))
            self.config.set('cellpose.parameters.flow_threshold', float(flow_threshold))
            self.config.set('cellpose.parameters.cellprob_threshold', float(cellprob_threshold))
            self.config.set('cellpose.parameters.min_size', int(min_size))
            self.config.set('cellpose.display.outline_only', bool(outline_only))
            self.config.set('cellpose.display.adjust_outline', bool(adjust_outline))
            self.config.set('cellpose.display.outline_thickness', int(outline_thickness))
            
            # Save window state and geometry if available
            if hasattr(self, 'saveGeometry'):
                try:
                    self.config.set('cellpose.window.geometry', bytes(self.saveGeometry()).hex())
                except Exception as e:
                    print(f"Warning: Could not save window geometry: {e}")
            
            # Save splitter state if available
            if hasattr(self, 'splitter') and self.splitter:
                try:
                    self.config.set('cellpose.window.splitter_state', bytes(self.splitter.saveState()).hex())
                except Exception as e:
                    print(f"Warning: Could not save splitter state: {e}")
            
            # Save to disk
            success = self.config.sync()
            if success:
                print("Preferences saved successfully")
            else:
                print("Warning: Failed to sync preferences to disk")
                
            return success
            
        except Exception as e:
            import traceback
            print(f"Error saving preferences: {e}")
            print(traceback.format_exc())
            return False
    
    def _throttled_save_prefs(self):
        """Throttle save_preferences calls to avoid excessive disk I/O"""
        # Mark preferences as dirty; they will be saved when the tab closes.
        self._prefs_dirty = True
    
    def _apply_window_state(self):
        """Apply saved window state and geometry"""
        if not self.config:
            return
            
        try:
            # Restore window geometry
            if hasattr(self, 'restoreGeometry') and hasattr(self, 'saveGeometry'):
                geom_data = self.config.get('cellpose.window.geometry')
                if geom_data:
                    self.restoreGeometry(bytes.fromhex(geom_data))
            
            # Restore splitter state
            if hasattr(self, 'splitter') and self.splitter:
                splitter_state = self.config.get('cellpose.window.splitter_state')
                if splitter_state:
                    self.splitter.restoreState(bytes.fromhex(splitter_state))
                    
        except Exception as e:
            print(f"Error restoring window state: {e}")
    
    def load_preferences(self):
        """Load preferences from config manager"""
        if not self.config:
            print("Config manager not available")
            return
            
        try:
            print("Loading preferences from config...")
            
            # Load display settings with defaults
            self.brightness = float(self.config.get('cellpose.display.brightness', 1.0))
            self.contrast = float(self.config.get('cellpose.display.contrast', 1.0))
            
            # Update UI to reflect loaded preferences
            self.brightness_slider.blockSignals(True)
            self.contrast_slider.blockSignals(True)
            
            self.brightness_slider.setValue(int(self.brightness * 100))
            self.contrast_slider.setValue(int(self.contrast * 100))
            
            self.brightness_slider.blockSignals(False)
            self.contrast_slider.blockSignals(False)
            
            # Load Cellpose parameters with defaults
            model = str(self.config.get('cellpose.parameters.model', self.default_params['model']))
            diameter = float(self.config.get('cellpose.parameters.diameter', self.default_params['diameter']))
            flow_threshold = float(self.config.get('cellpose.parameters.flow_threshold', self.default_params['flow_threshold']))
            cellprob_threshold = float(self.config.get('cellpose.parameters.cellprob_threshold', self.default_params['cellprob_threshold']))
            min_size = int(self.config.get('cellpose.parameters.min_size', self.default_params['min_size']))
            outline_only = bool(self.config.get('cellpose.display.outline_only', self.default_params['outline_only']))
            adjust_outline = bool(self.config.get('cellpose.display.adjust_outline', self.default_params['adjust_outline']))
            outline_thickness = int(self.config.get('cellpose.display.outline_thickness', self.default_params['outline_thickness']))
            
            print(f"Loaded preferences: model={model}, diameter={diameter}, flow={flow_threshold}, "
                  f"cellprob={cellprob_threshold}, min_size={min_size}, outline_only={outline_only}, "
                  f"adjust_outline={adjust_outline}, outline_thickness={outline_thickness}")
            
            # Block signals while updating UI to prevent multiple saves
            self.model_combo.blockSignals(True)
            self.diameter_spin.blockSignals(True)
            self.flow_spin.blockSignals(True)
            self.cellprob_spin.blockSignals(True)
            self.minsize_spin.blockSignals(True)
            self.outline_check.blockSignals(True)
            self.outline_thickness_check.blockSignals(True)
            self.outline_thickness_spin.blockSignals(True)
            
            # Update UI controls
            index = self.model_combo.findText(model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            else:
                print(f"Warning: Model '{model}' not found in combo box")
                
            self.diameter_spin.setValue(diameter)
            self.flow_spin.setValue(flow_threshold)
            self.cellprob_spin.setValue(cellprob_threshold)
            self.minsize_spin.setValue(min_size)
            self.outline_check.setChecked(outline_only)
            self.outline_thickness_check.setChecked(adjust_outline)
            self.outline_thickness_spin.setValue(outline_thickness)
            
            # Update internal state
            self.update_outline_controls()
            
            # Re-enable signals
            self.model_combo.blockSignals(False)
            self.diameter_spin.blockSignals(False)
            self.flow_spin.blockSignals(False)
            self.cellprob_spin.blockSignals(False)
            self.minsize_spin.blockSignals(False)
            self.outline_check.blockSignals(False)
            self.outline_thickness_check.blockSignals(False)
            self.outline_thickness_spin.blockSignals(False)
            
            print("Preferences loaded successfully")
            
        except Exception as e:
            import traceback
            print(f"Error loading preferences: {e}")
            print(traceback.format_exc())
    
    def setup_fret_tab_access(self):
        """Ensure the FRET tab is accessible from this tab"""
        try:
            main_window = self.window()
            if not main_window:
                return
                
            # Try to get the FRET tab directly from the main window
            if hasattr(main_window, 'fret_tab'):
                self.fret_tab = main_window.fret_tab
                return
                
            # Fallback: Get the tab widget that contains all tabs
            tab_widget = main_window.findChild(QTabWidget, 'main_tabs')
            if not tab_widget and hasattr(main_window, 'tabs'):
                tab_widget = main_window.tabs
                
            if tab_widget:
                # Ensure the FRET tab is enabled
                for i in range(tab_widget.count()):
                    if tab_widget.tabText(i) == 'FRET Analysis':
                        tab_widget.setTabEnabled(i, True)
                        break
                        
        except Exception as e:
            print(f"Warning: Could not set up FRET tab access: {str(e)}")
            
    def initialize_model(self):
        """Initialize the Cellpose model"""
        try:
            model_type = self.model_combo.currentText()
            use_gpu = _safe_cuda_available()
            
            # For newer versions of Cellpose, we need to use CellposeModel
            if hasattr(models, 'CellposeModel'):
                self.model = models.CellposeModel(gpu=use_gpu, model_type=model_type)
            # Fallback to older API if needed
            elif hasattr(models, 'Cellpose'):
                self.model = models.Cellpose(gpu=use_gpu, model_type=model_type)
            else:
                raise ImportError("Could not find Cellpose model class. Please check your Cellpose installation.")
                
            print(f"Initialized Cellpose model: {model_type}")
            print(f"Using GPU: {use_gpu}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to initialize Cellpose model: {str(e)}")
            self.model = None
    
    def load_images(self):
        """Open file dialog to load image files (TIFF/CZI)"""
        file_filter = "Image Files (*.tif *.tiff *.czi);;TIFF Files (*.tif *.tiff);;"
        if CZI_AVAILABLE:
            file_filter += "CZI Files (*.czi);;"
        file_filter += "All Files (*)"
        
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Image Files", "", file_filter
        )
        
        self._add_image_paths(files)
    
    def on_image_selected(self, current, previous=None):
        """Handle selection of an image from the list.
        
        Args:
            current: The currently selected QListWidgetItem
            previous: The previously selected QListWidgetItem (ignored)
        """
        if not hasattr(self, 'image_paths') or not self.image_paths or current is None:
            return
            
        idx = self.image_list.row(current)
        if 0 <= idx < len(self.image_paths):
            # Clear ROI manager when a new image is selected
            if hasattr(self, 'roi_list_widget'):
                self.roi_list_widget.clear()
            if hasattr(self, 'roi_items'):
                self.roi_items = []
            
            # Set the current image path and load it
            self.current_image_path = self.image_paths[idx]
            self.load_current_image()
    
    def _save_czi_as_temp_tiff(self, czi_data):
        """Save CZI data as a temporary TIFF file and return the path"""
        import tempfile
        import uuid
        
        # Create a temporary file with .tif extension
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"temp_{uuid.uuid4().hex}.tif")
        
        # Convert to uint16 for TIFF saving
        if czi_data.dtype != np.uint16:
            czi_data = (czi_data * 65535).astype(np.uint16)
        
        # Save as TIFF
        tifffile.imwrite(temp_path, czi_data, photometric='minisblack',
                        metadata={'axes': 'CYX'})
        print(f"Saved CZI data as temporary TIFF: {temp_path}")
        return temp_path
    
    def load_current_image(self):
        """Load and display the currently selected image"""
        if not self.current_image_path:
            return
            
        try:
            # Reset segmentation state for new image
            self.current_mask = None
            self.current_labels = None
            self.current_image_has_segmentation = False
            
            # All files should be TIFF at this point
            print(f"\n=== Loading image: {self.current_image_path} ===")
            
            # Read TIFF file (could be multi-frame)
            img = tifffile.imread(self.current_image_path)
            print(f"Loaded TIFF with shape: {img.shape}")
            
            # Handle multi-frame TIFF (should be 3 frames: FRET, Donor, Acceptor)
            if len(img.shape) == 3:
                print(f"Multi-frame TIFF detected with {img.shape[0]} frames")
                
                # Store all frames for saving later
                self.original_tiff_data = img
                
                # Find and use the best frame (highest mean intensity) for display and segmentation
                best_frame, best_idx = self.get_best_frame(img)
                img = best_frame
                print(f"Using frame {best_idx} (0-based) with highest mean intensity for segmentation")
            
            # Convert to float32 and normalize to 0-1
            img = img.astype(np.float32)
            img_normalized = (img - img.min()) / (img.max() - img.min() + 1e-6)
            
            # Store the original normalized image
            self.current_image = img_normalized
            
            print(f"Image loaded successfully, shape: {self.current_image.shape}")
            
            # Display the image
            self.update_display(img_normalized)
            
            # Update status
            self.update_status("Image loaded. Click 'Run Segmentation' to segment.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image: {str(e)}")
    
    def get_best_frame(self, img):
        """Get the frame with the highest mean intensity from a multi-frame image.
        
        Args:
            img: Input image (can be single or multi-frame)
            
        Returns:
            The best frame (2D numpy array) and its index
        """
        if not isinstance(img, np.ndarray) or img.ndim != 3 or img.shape[0] <= 1:
            return img, 0 if isinstance(img, np.ndarray) and img.ndim == 3 else None
            
        # Calculate mean intensity for each frame
        frame_means = [np.mean(frame) for frame in img]
        best_frame_idx = np.argmax(frame_means)
        return img[best_frame_idx], best_frame_idx
    
    def get_display_image(self, img):
        """Get the best frame for display, using the frame with highest mean intensity.
        This ensures consistency between preview and segmentation.
        """
        best_frame, _ = self.get_best_frame(img)
        return best_frame if best_frame is not None else img
        
    def on_brightness_changed(self, value):
        """Handle brightness slider change with throttling"""
        self.brightness = value / 100.0
        self.brightness_value.setText(f"{value}%")
        if not hasattr(self, '_last_update') or time.time() - self._last_update > 0.1:  # 100ms throttle
            self._last_update = time.time()
            if hasattr(self, 'current_image') and self.current_image is not None:
                self.update_display(self.current_image, keep_rois=True)
            # Mark preferences as dirty instead of saving immediately
            self._prefs_dirty = True
    
    def on_contrast_changed(self, value):
        """Handle contrast slider change with throttling"""
        self.contrast = value / 100.0
        self.contrast_value.setText(f"{value}%")
        if not hasattr(self, '_last_update') or time.time() - self._last_update > 0.1:  # 100ms throttle
            self._last_update = time.time()
            if hasattr(self, 'current_image') and self.current_image is not None:
                self.update_display(self.current_image, keep_rois=True)
            # Mark preferences as dirty instead of saving immediately
            self._prefs_dirty = True
    
    def auto_adjust_display(self):
        """Automatically adjust brightness and contrast for optimal image display.
        Uses a combination of histogram equalization and adaptive contrast stretching.
        """
        if not hasattr(self, 'current_image') or self.current_image is None:
            return
            
        try:
            # Get the first frame if it's a multi-frame image
            img = self.current_image[0] if self.current_image.ndim == 3 else self.current_image
            
            # Convert to float32 for processing
            img_float = img.astype(np.float32)
            
            # Normalize to 0-1 range
            min_val = np.min(img_float)
            max_val = np.max(img_float)
            if max_val > min_val:
                img_norm = (img_float - min_val) / (max_val - min_val)
            else:
                img_norm = img_float
            
            # Convert to 8-bit for histogram calculations
            img_8bit = (img_norm * 255).astype(np.uint8)
            
            # Calculate image statistics
            mean_intensity = np.mean(img_8bit)
            std_intensity = np.std(img_8bit)
            
            # Apply adaptive histogram equalization
            clahe = cv2.createCLAHE(
                clipLimit=2.0 + (std_intensity / 32.0),
                tileGridSize=(8, 8)
            )
            img_eq = clahe.apply(img_8bit)
            
            # Calculate histogram of equalized image
            hist = cv2.calcHist([img_eq], [0], None, [256], [0, 256])
            hist = hist.ravel() / hist.sum()
            
            # Find intensity range that contains most of the data
            cdf = hist.cumsum()
            low_pct = 0.02  # 2% for low end
            high_pct = 0.98  # 98% for high end
            
            # Find the intensity values at the specified percentiles
            low_val = np.argmax(cdf >= low_pct)
            high_val = np.argmax(cdf >= high_pct)
            
            # Ensure we have a valid range
            if high_val <= low_val:
                high_val = min(255, low_val + 5)
            
            # Calculate contrast and brightness values
            contrast = 255.0 / max(1, high_val - low_val)
            brightness = (128.0 - ((low_val + high_val) / 2.0)) / 255.0
            
            # Convert to slider values (0-200% range, 100% = no change)
            contrast_pct = min(max(contrast * 50, 10), 400)  # 10-400% range
            brightness_pct = 100 + (brightness * 100)  # 0-200% range, centered at 100%
            
            # Apply limits
            contrast_pct = min(max(contrast_pct, 10), 400)
            brightness_pct = min(max(brightness_pct, 10), 190)
            
            # Update sliders
            self.brightness_slider.setValue(int(brightness_pct))
            self.contrast_slider.setValue(int(contrast_pct))
            
            # Update display
            self.update_display_settings()
            
        except Exception as e:
            print(f"Error in auto-adjust: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def reset_display_settings(self):
        """Reset display settings to default."""
        self.brightness_slider.setValue(100)
        self.contrast_slider.setValue(100)
        self.update_display_settings()
    
    def update_display_settings(self):
        """Update display based on brightness/contrast settings with throttling."""
        if not hasattr(self, '_update_timer'):
            self._update_timer = QTimer()
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._perform_display_update)
        
        # Restart the timer - this effectively debounces rapid updates
        self._update_timer.start(100)  # 100ms delay
    
    def _perform_display_update(self):
        """Perform the actual display update."""
        if hasattr(self, 'current_image') and self.current_image is not None:
            self.update_display(self.current_image, keep_rois=True)
    
    def apply_display_effects(self, img):
        """Apply brightness, contrast, and gamma to the image for display only."""
        if not hasattr(self, 'brightness') or not hasattr(self, 'contrast'):
            return img
        
        # Convert to float32 for processing
        img_float = img.astype(np.float32)
        
        # Normalize to 0-1 range
        min_val = np.min(img_float)
        max_val = np.max(img_float)
        if max_val > min_val:
            img_float = (img_float - min_val) / (max_val - min_val)
        
        # Get current values from class attributes
        brightness = self.brightness - 0.5  # Convert from 0-1 to -0.5 to +0.5 range
        contrast = self.contrast * 4.0  # Convert from 0-1 to 0.1 to 4.0 range
        
        # Apply contrast and brightness
        img_float = np.clip((img_float - 0.5) * contrast + 0.5 + brightness, 0, 1)
        
        # Apply gamma if available
        if hasattr(self, 'gamma'):
            gamma = self.gamma * 2.0  # Convert from 0-1 to 0.5 to 2.0 range
            if gamma != 1.0:
                img_float = np.power(img_float, 1.0 / max(gamma, 0.1))
        
        # Convert back to 8-bit
        return (img_float * 255).astype(np.uint8)
    
    def update_display(self, img, mask=None, keep_rois=False):
        """Update the image display with the current image and optional mask
        
        Args:
            img: Input image (can be multi-frame)
            mask: Optional segmentation mask
            keep_rois: If True, preserve existing ROIs when updating display
        """
        # Update plot colors based on current theme
        app = QApplication.instance()
        palette = app.palette()
        is_dark_theme = palette.window().color().lightness() < 128
        
        # Set appropriate colors based on theme
        if is_dark_theme:
            text_color = '#f0f0f0'
            bg_color = '#2b2b2b'
            grid_color = '#3a3a3a'
            edge_color = '#6d6d6d'
        else:
            text_color = 'black'
            bg_color = 'white'
            grid_color = '#e0e0e0'
            edge_color = '#cccccc'
            
        # Update figure and axes colors
        if hasattr(self, 'figure') and self.figure:
            self.figure.set_facecolor(bg_color)
            for ax in [self.ax1, self.ax2]:
                if ax:
                    ax.set_facecolor(bg_color)
                    ax.tick_params(colors=text_color)
                    for spine in ax.spines.values():
                        spine.set_edgecolor(edge_color)
                    ax.xaxis.label.set_color(text_color)
                    ax.yaxis.label.set_color(text_color)
                    ax.title.set_color(text_color)
                    ax.grid(color=grid_color, alpha=0.3)
        try:
            # Clear the axes
            self.ax1.clear()
            self.ax2.clear()
            
            # Get display image (first frame if multi-frame)
            display_img = self.get_display_image(img)
            
            # Store the original image if this is a new image
            if not hasattr(self, 'current_image') or not keep_rois:
                self.current_image = display_img.copy()
            
            # Apply display settings to the original image
            display_img = self.apply_display_effects(self.current_image)
            
            # Display the processed image
            self.ax1.imshow(display_img, cmap='gray', vmin=0, vmax=255)
            self.ax1.set_title("Original Image")
            self.ax1.axis('off')
            
            # Initialize or update current labels
            if not keep_rois or self.current_labels is None:
                if mask is not None and np.any(mask > 0):
                    self.current_labels = mask.copy()
                else:
                    self.current_labels = np.zeros_like(display_img, dtype=np.uint16)
            
            # Display current labels if available
            if self.current_labels is not None and np.any(self.current_labels > 0):
                # Create a colored mask overlay
                from matplotlib.colors import ListedColormap
                from skimage.measure import regionprops
                
                cmap = plt.cm.get_cmap('hsv', 256)
                mask_colored = np.zeros((*self.current_labels.shape, 4))
                
                for label_id in np.unique(self.current_labels):
                    if label_id == 0:  # Skip background
                        continue
                    mask_colored[self.current_labels == label_id] = cmap(label_id % 256)
                
                # Set alpha for the mask
                mask_colored[..., 3] = (self.current_labels > 0).astype(float) * 0.5
                self.ax2.imshow(mask_colored)
                
                # Add region numbers
                regions = regionprops(self.current_labels.astype(np.int32))
                
                # Add region labels
                for region in regions:
                    y, x = region.centroid
                    self.ax2.text(x, y, str(region.label), color='red', ha='center', va='center',
                               bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', pad=1))
            
            # Set titles and axis
            self.ax2.set_title("Segmentation Mask")
            self.ax2.axis('off')
            
            # Adjust layout to prevent overlap
            self.figure.tight_layout()
            
            # Force a canvas update
            self.canvas.draw_idle()
            
        except Exception as e:
            print(f"Error updating display: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def update_outline_controls(self):
        """Update the state of outline controls based on checkboxes"""
        outlines_enabled = self.outline_check.isChecked()
        thickness_enabled = outlines_enabled and self.outline_thickness_check.isChecked()
        
        self.outline_thickness_check.setEnabled(outlines_enabled)
        self.outline_thickness_spin.setEnabled(thickness_enabled)
        
        # If outlines are disabled, uncheck thickness checkbox
        if not outlines_enabled:
            self.outline_thickness_check.setChecked(False)
    
    # Drag and drop event handlers - using the consolidated dragEnterEvent above
    
    def dragLeaveEvent(self, event):
        """Handle drag leave event"""
        self.drop_hint.hide()
    
    def dropEvent(self, event):
        """Handle drop event"""
        self.drop_hint.hide()
        
        if event.mimeData().hasUrls():
            # Get list of files
            urls = event.mimeData().urls()
            file_paths = [url.toLocalFile() for url in urls]
            
            # Filter for image files
            image_exts = ['.tif', '.tiff', '.png', '.jpg', '.jpeg', '.czi']
            image_paths = [f for f in file_paths 
                         if os.path.isfile(f) and 
                         os.path.splitext(f)[1].lower() in image_exts]
            
            if image_paths:
                # Use _add_image_paths to properly handle adding new images
                self._add_image_paths(image_paths)
    
    # ROI Management Methods
    def populate_roi_list(self):
        """Populate ROI list widget based on current labels."""
        self.roi_list_widget.clear()
        if self.current_labels is None:
            return
            
        from skimage.measure import regionprops
        props = regionprops(self.current_labels)
        for prop in props:
            self.roi_list_widget.addItem(f"ROI {prop.label} - Area: {prop.area} px²")
    
    def delete_selected_roi(self):
        """Remove the selected ROI label from current_labels and update the display."""
        if self.current_labels is None or self.current_image is None:
            return
            
        selected_items = self.roi_list_widget.selectedItems()
        if not selected_items:
            return
            
        # Store the IDs of ROIs to be deleted
        deleted_labels = set()
        
        # First pass: collect all labels to be deleted
        for item in selected_items:
            try:
                label_text = item.text()
                # Handle both "ROI X" and "Label X" formats
                if "ROI" in label_text:
                    label_id = int(label_text.split()[1])
                else:
                    label_id = int(label_text.split()[1])
                deleted_labels.add(label_id)
            except (IndexError, ValueError) as e:
                print(f"Error parsing ROI label: {e}")
                continue
        
        # Second pass: remove all selected labels
        for label_id in deleted_labels:
            self.current_labels[self.current_labels == label_id] = 0
        
        # Renumber remaining labels to be sequential
        self.renumber_labels()
        
        # Update the display and ROI list
        self.update_display(self.current_image, keep_rois=True)
        self.populate_roi_list()  # Make sure ROI list is updated
        self.update_status(f"Deleted {len(deleted_labels)} ROI(s)")
    
    def renumber_labels(self):
        """Renumber labels to be sequential starting from 1"""
        if self.current_labels is None:
            return
            
        # Get unique labels, excluding background (0)
        unique_labels = np.unique(self.current_labels)
        unique_labels = unique_labels[unique_labels > 0]
        
        if len(unique_labels) == 0:
            return
            
        # Create mapping from old to new labels
        label_map = {old: new + 1 for new, old in enumerate(sorted(unique_labels))}
        label_map[0] = 0  # Keep background as 0
        
        # Apply mapping
        new_labels = np.zeros_like(self.current_labels)
        for old_label, new_label in label_map.items():
            if old_label > 0:  # Skip background
                new_labels[self.current_labels == old_label] = new_label
                
        self.current_labels = new_labels
    
    def reset_roi_view(self):
        """Reset the ROI view to show the entire image."""
        if hasattr(self, 'roi_ax') and hasattr(self, 'roi_canvas'):
            self.roi_ax.set_xlim(0, self.current_labels.shape[1] if hasattr(self, 'current_labels') else 1000)
            self.roi_ax.set_ylim(self.current_labels.shape[0] if hasattr(self, 'current_labels') else 1000, 0)
            self.roi_canvas.draw_idle()
    
    def update_roi_display(self):
        """Update the ROI display with current brightness/contrast settings."""
        if not hasattr(self, 'original_display_img') or not hasattr(self, 'roi_image'):
            return
            
        # Get current slider values
        brightness = self.brightness_slider.value() / 100.0  # Convert to -1.0 to 1.0 range
        contrast = self.contrast_slider.value() / 100.0  # Convert to -1.0 to 1.0 range
        
        # Apply brightness and contrast
        img = self.original_display_img.astype(float)
        img = (img - img.min()) / (img.max() - img.min() + 1e-8)  # Normalize to 0-1
        
        # Apply contrast (contrast * (x - 0.5) + 0.5)
        if contrast >= 0:
            img = (1 + contrast) * (img - 0.5) + 0.5
        else:
            img = (1 + contrast) * img + 0.5 * (1 - contrast)
            
        # Apply brightness
        img = img + brightness
        
        # Clip to valid range
        img = np.clip(img, 0, 1)
        
        # Update the image data
        self.roi_image.set_array(img)
        self.display_img = (img * 255).astype(np.uint8)  # Update display_img for ROI drawing
        self.roi_canvas.draw_idle()
    
    def reset_roi_adjustments(self):
        """Reset brightness and contrast sliders to default values."""
        if hasattr(self, 'brightness_slider') and hasattr(self, 'contrast_slider'):
            self.brightness_slider.blockSignals(True)
            self.contrast_slider.blockSignals(True)
            
            self.brightness_slider.setValue(0)
            self.contrast_slider.setValue(0)
            
            self.brightness_slider.blockSignals(False)
            self.contrast_slider.blockSignals(False)
            
            # Update display with default values
            self.update_roi_display()
    
    def update_roi_display(self):
        """Update the ROI display with current brightness/contrast settings."""
        if not hasattr(self, 'original_display_img') or not hasattr(self, 'roi_image'):
            return
            
        # Get current slider values
        brightness = self.brightness_slider.value() / 100.0  # Convert to -1.0 to 1.0 range
        contrast = self.contrast_slider.value() / 100.0  # Convert to -1.0 to 1.0 range
        
        # Apply brightness and contrast
        img = self.original_display_img.astype(float)
        img = (img - img.min()) / (img.max() - img.min() + 1e-8)  # Normalize to 0-1
        
        # Apply contrast (contrast * (x - 0.5) + 0.5)
        if contrast >= 0:
            img = (1 + contrast) * (img - 0.5) + 0.5
        else:
            img = (1 + contrast) * img + 0.5 * (1 - contrast)
            
        # Apply brightness
        img = img + brightness
        
        # Clip to valid range
        img = np.clip(img, 0, 1)
        
        # Update the image data
        self.roi_image.set_array(img)
        self.roi_canvas.draw_idle()
    
    def reset_roi_adjustments(self):
        """Reset brightness and contrast sliders to default values."""
        if hasattr(self, 'brightness_slider') and hasattr(self, 'contrast_slider'):
            self.brightness_slider.blockSignals(True)
            self.contrast_slider.blockSignals(True)
            
            self.brightness_slider.setValue(0)
            self.contrast_slider.setValue(0)
            
            self.brightness_slider.blockSignals(False)
            self.contrast_slider.blockSignals(False)
            
            # Update display with default values
            self.update_roi_display()

    def start_roi(self):
        """Start polygon ROI drawing on the image with zoom/pan support."""
        if self.current_image is None:
            return
            
        try:
            # Get display image (first frame if multi-frame)
            display_img = self.get_display_image(self.current_image)
            
            # Disable the button while drawing
            self.add_roi_btn.setEnabled(False)
            
            # Close any existing ROI window
            if hasattr(self, 'roi_window') and self.roi_window:
                try:
                    self.roi_window.close()
                except:
                    pass
            
            # Create a new figure for ROI drawing
            fig_num = len(plt.get_fignums()) + 1
            self.roi_figure, self.roi_ax = plt.subplots(figsize=(10, 10), num=fig_num)
            self.roi_figure.set_facecolor('none')
            self._figures.append(self.roi_figure)
            
            self.roi_canvas = FigureCanvas(self.roi_figure)
            
            # Create main window and layout
            self.roi_window = QWidget()
            self.roi_window.setWindowTitle("Draw ROI - Close when done")
            self.roi_window.setWindowModality(Qt.ApplicationModal)
            self.roi_window.resize(1000, 800)  # Set a reasonable default size
            
            # Main layout
            main_layout = QVBoxLayout(self.roi_window)
            main_layout.setContentsMargins(5, 5, 5, 5)
            main_layout.setSpacing(5)
            
            # Create toolbar layout
            toolbar_layout = QHBoxLayout()
            
            # Add mode selection buttons
            self.select_btn = QPushButton("Select")
            self.select_btn.setCheckable(True)
            self.select_btn.setChecked(True)
            self.select_btn.setToolTip("Select and draw polygon ROIs")
            self.select_btn.clicked.connect(lambda: self.set_tool_mode('select'))
            toolbar_layout.addWidget(self.select_btn)
            
            self.zoom_btn = QPushButton("Zoom")
            self.zoom_btn.setCheckable(True)
            self.zoom_btn.setToolTip("Zoom in/out with mouse wheel")
            self.zoom_btn.clicked.connect(lambda: self.set_tool_mode('zoom'))
            toolbar_layout.addWidget(self.zoom_btn)
            
            self.pan_btn = QPushButton("Pan")
            self.pan_btn.setCheckable(True)
            self.pan_btn.setToolTip("Pan the view")
            self.pan_btn.clicked.connect(lambda: self.set_tool_mode('pan'))
            toolbar_layout.addWidget(self.pan_btn)
            
            toolbar_layout.addStretch()
            
            reset_btn = QPushButton("Reset View")
            reset_btn.setToolTip("Reset the view to show the entire image")
            reset_btn.clicked.connect(self.reset_roi_view)
            toolbar_layout.addWidget(reset_btn)
            
            # Add toolbar layout to main layout
            main_layout.addLayout(toolbar_layout)
            
            # Add brightness/contrast controls
            controls_layout = QHBoxLayout()
            controls_layout.setContentsMargins(5, 5, 5, 5)
            controls_layout.setSpacing(10)
            
            # Brightness slider
            brightness_layout = QVBoxLayout()
            brightness_label = QLabel("Brightness:")
            self.brightness_slider = QSlider(Qt.Horizontal)
            self.brightness_slider.setRange(-100, 100)
            self.brightness_slider.setValue(0)
            self.brightness_slider.setToolTip("Adjust image brightness")
            self.brightness_slider.valueChanged.connect(self.update_roi_display)
            brightness_layout.addWidget(brightness_label)
            brightness_layout.addWidget(self.brightness_slider)
            controls_layout.addLayout(brightness_layout)
            
            # Contrast slider
            contrast_layout = QVBoxLayout()
            contrast_label = QLabel("Contrast:")
            self.contrast_slider = QSlider(Qt.Horizontal)
            self.contrast_slider.setRange(-100, 100)
            self.contrast_slider.setValue(0)
            self.contrast_slider.setToolTip("Adjust image contrast")
            self.contrast_slider.valueChanged.connect(self.update_roi_display)
            contrast_layout.addWidget(contrast_label)
            contrast_layout.addWidget(self.contrast_slider)
            controls_layout.addLayout(contrast_layout)
            
            # Reset button for sliders
            reset_btn = QPushButton("Reset")
            reset_btn.setToolTip("Reset brightness and contrast to default")
            reset_btn.clicked.connect(self.reset_roi_adjustments)
            controls_layout.addWidget(reset_btn)
            
            main_layout.addLayout(controls_layout)
            
            # Add matplotlib canvas
            self.roi_canvas.setParent(self.roi_window)
            main_layout.addWidget(self.roi_canvas)

            # Set up window close event
            self.roi_window.closeEvent = self.roi_window_closed
            
            # Store the original image for adjustments
            self.original_display_img = display_img.copy()
            
            # Store the original image for ROI drawing
            self.display_img = display_img.copy()
            
            # Clear the figure and show the image
            self.roi_ax.clear()
            self.roi_image = self.roi_ax.imshow(display_img, cmap='gray')
            self.roi_ax.axis('off')
            
            # Set initial view
            self.reset_roi_view()
            
            # Clear any previous polygon selector
            if hasattr(self, 'poly_selector') and self.poly_selector is not None:
                self.poly_selector.disconnect_events()
                self.poly_selector = None
                
            # Create new polygon selector with custom event handling
            self.poly_selector = PolygonSelector(
                self.roi_ax,
                self._roi_complete,
                useblit=True,
                props=dict(color='lime', linewidth=1),
                handle_props=dict(markerfacecolor='lime', markeredgecolor='lime'),
                grab_range=10
            )
            
            # Store the current tool mode
            self.current_tool_mode = 'select'  # 'select', 'zoom', or 'pan'
            
            # Create and configure the Matplotlib navigation toolbar
            self.roi_toolbar = NavigationToolbar2QT(self.roi_canvas, self.roi_window)
            main_layout.insertWidget(1, self.roi_toolbar)  # Add toolbar below buttons
            
            # Connect mouse events for our custom handling (if needed)
            self.roi_canvas.mpl_connect('scroll_event', self.on_mouse_scroll)
            
            # Connect to the navigation mode change event
            self.roi_toolbar.zoom()  # Initialize with zoom mode
            self.roi_toolbar.pan()   # Then switch to pan mode to ensure clean state
            self.roi_toolbar.home()  # Reset the view
            
            # Set up the default mode to 'select' (ROI drawing)
            self.set_tool_mode('select')
            
            # Initialize status with default tool mode
            self.update_status()
            
            # Disable the 'Subplots' and 'Customize' buttons which aren't needed
            for action in self.roi_toolbar.actions():
                if action.text() in ['Subplots', 'Customize']:
                    action.setVisible(False)
            
            # Show the ROI window
            self.roi_window.show()
            
        except Exception as e:
            print(f"Error starting ROI drawing: {e}")
            QMessageBox.warning(self, "Error", f"Failed to start ROI drawing: {str(e)}")
            self.add_roi_btn.setEnabled(True)
    
    def on_mouse_scroll(self, event):
        """Handle mouse scroll events for zooming with ctrl key."""
        if not hasattr(self, 'roi_ax') or event.inaxes != self.roi_ax:
            return
            
        # Only handle scroll zoom when ctrl is pressed
        if not event.key == 'control':
            return
            
        # Get the current x and y limits
        xlim = self.roi_ax.get_xlim()
        ylim = self.roi_ax.get_ylim()
        
        # Get the current mouse position in data coordinates
        xdata = event.xdata
        ydata = event.ydata
        
        if xdata is None or ydata is None:
            return
        
        # Calculate zoom factor (finer control)
        zoom_factor = 1.1 if event.button == 'up' else 0.9
        
        # Get the current dimensions
        x_range = xlim[1] - xlim[0]
        y_range = ylim[1] - ylim[0]
        
        # Calculate new dimensions
        new_x_range = x_range * zoom_factor
        new_y_range = y_range * zoom_factor
        
        # Calculate the relative position of the mouse in the current view
        x_frac = (xdata - xlim[0]) / x_range
        y_frac = (ydata - ylim[0]) / y_range
        
        # Calculate new limits based on mouse position
        new_xlim = [xdata - x_frac * new_x_range, xdata + (1 - x_frac) * new_x_range]
        new_ylim = [ydata - (1 - y_frac) * new_y_range, ydata + y_frac * new_y_range]
        
        # Set new limits with boundary checks
        img_shape = self.current_labels.shape if hasattr(self, 'current_labels') else (1000, 1000)
        
        # Ensure we don't zoom out too far
        max_zoom = max(img_shape[1] * 10, 1000)  # Max 10x image width
        min_zoom = min(img_shape[1] / 10, 100)   # Min 1/10th of image width
        
        if abs(new_xlim[1] - new_xlim[0]) > min_zoom and abs(new_ylim[1] - new_ylim[0]) > min_zoom:
            if abs(new_xlim[1] - new_xlim[0]) < max_zoom and abs(new_ylim[1] - new_ylim[0]) < max_zoom:
                self.roi_ax.set_xlim(new_xlim)
                self.roi_ax.set_ylim(new_ylim)
        
        # Redraw
        self.roi_canvas.draw_idle()

    def set_tool_mode(self, mode):
        """Set the current tool mode (select, zoom, pan)."""
        if not hasattr(self, 'roi_figure') or not hasattr(self, 'roi_window'):
            return
            
        # Update button states
        if hasattr(self, 'select_btn'):
            self.select_btn.setChecked(mode == 'select')
        if hasattr(self, 'zoom_btn'):
            self.zoom_btn.setChecked(mode == 'zoom')
        if hasattr(self, 'pan_btn'):
            self.pan_btn.setChecked(mode == 'pan')
        
        # Set the tool mode
        self.current_tool_mode = mode
        
        # Update the toolbar state and cursor
        if mode == 'select':
            # Disable navigation tools and enable polygon selector
            if hasattr(self, 'roi_toolbar'):
                # Turn off any active navigation tool
                if hasattr(self.roi_toolbar, '_active') and self.roi_toolbar._active in ['ZOOM', 'PAN']:
                    if self.roi_toolbar._active == 'ZOOM':
                        self.roi_toolbar.zoom()
                    else:
                        self.roi_toolbar.pan()
            
            # Enable polygon selector
            if hasattr(self, 'poly_selector'):
                self.poly_selector.set_visible(True)
                self.poly_selector.set_active(True)
            
            # Set cursor
            if hasattr(self, 'roi_canvas'):
                self.roi_canvas.setCursor(Qt.CrossCursor)
                
        elif mode == 'zoom':
            # Activate zoom tool
            if hasattr(self, 'roi_toolbar'):
                self.roi_toolbar.zoom()
            
            # Disable polygon selector
            if hasattr(self, 'poly_selector'):
                self.poly_selector.set_visible(False)
                self.poly_selector.set_active(False)
            
            # Set cursor
            if hasattr(self, 'roi_canvas'):
                self.roi_canvas.setCursor(Qt.CrossCursor)
                
        elif mode == 'pan':
            # Activate pan tool
            if hasattr(self, 'roi_toolbar'):
                self.roi_toolbar.pan()
            
            # Disable polygon selector
            if hasattr(self, 'poly_selector'):
                self.poly_selector.set_visible(False)
                self.poly_selector.set_active(False)
            
            # Set cursor
            if hasattr(self, 'roi_canvas'):
                self.roi_canvas.setCursor(Qt.OpenHandCursor)
        
        # Force redraw if canvas exists
        if hasattr(self, 'roi_canvas'):
            self.roi_canvas.draw_idle()
    
    def on_mouse_press(self, event):
        """Handle mouse press events."""
        if not hasattr(self, 'roi_ax') or event.inaxes != self.roi_ax:
            return
            
        # Let the polygon selector handle the event in select mode
        if (event.button == 1 and 
            self.current_tool_mode == 'select' and 
            hasattr(self, 'poly_selector') and 
            hasattr(self.poly_selector, 'onpress')):
            self.poly_selector.onpress(event)
    
    def on_mouse_release(self, event):
        """Handle mouse release events."""
        if not hasattr(self, 'roi_ax') or event.inaxes != self.roi_ax:
            return
            
        # Let the polygon selector handle the event in select mode
        if (event.button == 1 and 
            self.current_tool_mode == 'select' and 
            hasattr(self, 'poly_selector') and 
            hasattr(self.poly_selector, 'onrelease')):
            self.poly_selector.onrelease(event)
    
    def on_motion(self, event):
        """Handle mouse motion events."""
        if not hasattr(self, 'roi_ax') or event.inaxes != self.roi_ax:
            return
            
        # Let the polygon selector handle the event in select mode
        if (self.current_tool_mode == 'select' and 
            hasattr(self, 'poly_selector') and 
            hasattr(self.poly_selector, 'onmove')):
            self.poly_selector.onmove(event)
    
    def roi_window_closed(self, event):
        """Handle ROI window close event."""
        try:
            # Clean up polygon selector
            if hasattr(self, 'poly_selector') and self.poly_selector is not None:
                try:
                    self.poly_selector.disconnect_events()
                except Exception:
                    pass
                self.poly_selector = None
            
            # Clean up figure
            if hasattr(self, 'roi_figure'):
                try:
                    plt.close(self.roi_figure)
                except Exception:
                    pass
                self.roi_figure = None
                
            # Reset tool mode
            if hasattr(self, 'current_tool_mode'):
                self.current_tool_mode = 'select'
                
            if hasattr(self, 'add_roi_btn'):
                self.add_roi_btn.setEnabled(True)
                
        except Exception as e:
            print(f"Error cleaning up ROI window: {e}")
            
        event.accept()
        
    def save_roi_figure(self):
        """Save the current ROI figure."""
        if not hasattr(self, 'roi_figure'):
            return
            
        file_path, _ = QFileDialog.getSaveFileName(
            self.roi_window, 
            "Save ROI Figure", 
            "", 
            "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)"
        )
        
        if file_path:
            try:
                self.roi_figure.savefig(file_path, dpi=300, bbox_inches='tight')
                QMessageBox.information(self, "Success", f"Figure saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save figure: {str(e)}")
    
    def _roi_complete(self, verts):
        """Callback when ROI drawing is complete."""
        if self.current_image is None:
            return
            
        # Get display image to determine shape
        display_img = self.get_display_image(self.current_image)
        
        # Initialize labels if needed
        if not hasattr(self, 'current_labels') or self.current_labels is None:
            self.current_labels = np.zeros_like(display_img, dtype=np.uint16)
        
        try:
            # Convert polygon to mask
            from skimage.draw import polygon
            verts = np.array(verts)
            
            # Ensure vertices are within image bounds
            height, width = self.current_labels.shape
            verts[:, 0] = np.clip(verts[:, 0], 0, width-1)
            verts[:, 1] = np.clip(verts[:, 1], 0, height-1)
            
            # Create mask from polygon
            rr, cc = polygon(verts[:, 1], verts[:, 0], self.current_labels.shape)
            
            # Create a new label (max_label + 1)
            new_label = 1 if np.max(self.current_labels) == 0 else np.max(self.current_labels) + 1
            self.current_labels[rr, cc] = new_label
            
            # Update the display and ROI list
            self.update_display(self.current_image, keep_rois=True)
            self.populate_roi_list()  # Update ROI list after addition
            
        except Exception as e:
            print(f"Error creating ROI: {e}")
            QMessageBox.warning(self, "Error", f"Failed to create ROI: {str(e)}")
        finally:
            # Clean up any resources if needed
            pass
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Save preferences only if there are unsaved changes
        if getattr(self, '_prefs_dirty', False):
            self.save_preferences()
        # Close ROI window if open
        if hasattr(self, 'roi_window') and hasattr(self.roi_window, 'isVisible') and self.roi_window.isVisible():
            try:
                self.roi_window.close()
            except Exception as e:
                print(f"Error closing ROI window: {e}")
        
        # Clean up matplotlib figures
        self.cleanup_figures()
        
        # Call parent close event
        super().closeEvent(event)
    
    def cleanup_figures(self):
        """Clean up all matplotlib figures."""
        # Close all tracked figures
        for fig in getattr(self, '_figures', []):
            try:
                plt.close(fig)
            except Exception as e:
                print(f"Error closing figure: {e}")
        
        # Clear the figures list
        if hasattr(self, '_figures'):
            self._figures.clear()
            
    def update_theme(self):
        """Update the plot colors and toolbar icons when the application theme changes."""
        # Update the current theme based on application palette
        app = QApplication.instance()
        palette = app.palette()
        is_dark = palette.window().color().lightness() < 128
        self.current_theme = 'dark' if is_dark else 'light'
        
        # Set appropriate colors based on theme
        if is_dark:
            self.text_color = '#f0f0f0'
            self.bg_color = '#1a1a1a'  # Darker background for better contrast
            self.grid_color = '#3a3a3a'
            self.edge_color = '#5a5a5a'  # Brighter edge color for dark mode
            
            # Set Matplotlib style for dark theme
            plt.style.use('dark_background')
            # Force white text for all text elements
            plt.rcParams.update({
                'text.color': 'white',
                'axes.labelcolor': 'white',
                'xtick.color': 'white',
                'ytick.color': 'white',
                'axes.edgecolor': '#888888',
                'figure.facecolor': self.bg_color,
                'figure.edgecolor': self.edge_color,
                'savefig.facecolor': self.bg_color,
                'savefig.edgecolor': self.edge_color,
                'axes.facecolor': self.bg_color,
                'axes.grid': True,
                'grid.color': self.grid_color,
                'grid.alpha': 0.3,
                'axes.axisbelow': True,
                'legend.facecolor': self.bg_color,
                'legend.edgecolor': self.edge_color,
            })
        else:
            self.text_color = 'black'
            self.bg_color = 'white'
            self.grid_color = '#e0e0e0'
            self.edge_color = '#cccccc'
            
            # Set Matplotlib style for light theme
            plt.style.use('default')
            # Force black text for all text elements
            plt.rcParams.update({
                'text.color': 'black',
                'axes.labelcolor': 'black',
                'xtick.color': 'black',
                'ytick.color': 'black',
                'axes.edgecolor': '#666666',
                'figure.facecolor': self.bg_color,
                'figure.edgecolor': self.edge_color,
                'savefig.facecolor': self.bg_color,
                'savefig.edgecolor': self.edge_color,
                'axes.facecolor': self.bg_color,
                'axes.grid': True,
                'grid.color': self.grid_color,
                'grid.alpha': 0.3,
                'axes.axisbelow': True,
                'legend.facecolor': self.bg_color,
                'legend.edgecolor': self.edge_color,
            })
        
        # Update toolbar icons based on theme
        if hasattr(self, 'toolbar'):
            # Store the current view mode to restore it after updating icons
            current_mode = self.toolbar.mode if hasattr(self.toolbar, 'mode') else ''
            
            # Force toolbar to update its icons by toggling the theme
            if is_dark:
                # For dark theme, use white icons with proper SVG styling
                self.toolbar.setStyleSheet("""
                    QToolButton {
                        background: transparent;
                        border: 1px solid transparent;
                        border-radius: 4px;
                        padding: 2px;
                        margin: 0px;
                        color: #ffffff;
                    }
                    QToolButton:hover {
                        background: rgba(255, 255, 255, 0.1);
                        border: 1px solid #666666;
                    }
                    QToolButton:pressed {
                        background: rgba(255, 255, 255, 0.2);
                    }
                    QToolButton:disabled {
                        color: #666666;
                    }
                    /* Style for the navigation toolbar icons */
                    .QToolButton {
                        color: #ffffff;
                    }
                    .QToolButton:disabled {
                        color: #666666;
                    }
                """)
            else:
                # For light theme, use default styling
                self.toolbar.setStyleSheet("""
                    QToolButton {
                        background: transparent;
                        border: 1px solid transparent;
                        border-radius: 4px;
                        padding: 2px;
                        margin: 0px;
                        color: #000000;
                    }
                    QToolButton:hover {
                        background: rgba(0, 0, 0, 0.05);
                        border: 1px solid #cccccc;
                    }
                    QToolButton:pressed {
                        background: rgba(0, 0, 0, 0.1);
                    }
                    QToolButton:disabled {
                        color: #aaaaaa;
                    }
                """)
            
            # Force update the toolbar icons by toggling the mode
            if hasattr(self.toolbar, '_active') and self.toolbar._active:
                self.toolbar.pan()
                self.toolbar.zoom()
                
                # Restore the previous view mode
                if current_mode == 'zoom rect':
                    self.toolbar.zoom()
                elif current_mode == 'pan/zoom':
                    self.toolbar.pan()
        
        # Update plot colors and redraw
        if hasattr(self, 'ax1') and hasattr(self, 'ax2'):
            # Apply theme to all figures and axes
            for fig in [getattr(self, attr, None) for attr in ['figure', 'roi_figure']]:
                if fig is None:
                    continue
                    
                # Update toolbar icons for the figure
                for manager in plt._pylab_helpers.Gcf.get_all_fig_managers():
                    if manager.canvas.figure == fig:
                        # Set the toolbar style based on theme
                        if is_dark:
                            manager.toolbar.setStyleSheet("""
                                QToolBar {
                                    background-color: #2b2b2b;
                                    border: 1px solid #444444;
                                    border-radius: 4px;
                                    spacing: 2px;
                                    padding: 2px;
                                }
                                QToolButton {
                                    background-color: transparent;
                                    border: 1px solid transparent;
                                    border-radius: 4px;
                                    padding: 2px;
                                    margin: 0px;
                                }
                                QToolButton:hover {
                                    background-color: #3a3a3a;
                                    border: 1px solid #555555;
                                }
                                QToolButton:pressed {
                                    background-color: #4a4a4a;
                                }
                                QToolButton:disabled {
                                    background-color: transparent;
                                }
                            """)
                        else:
                            manager.toolbar.setStyleSheet("""
                                QToolBar {
                                    background-color: #f0f0f0;
                                    border: 1px solid #cccccc;
                                    border-radius: 4px;
                                    spacing: 2px;
                                    padding: 2px;
                                }
                                QToolButton {
                                    background-color: transparent;
                                    border: 1px solid transparent;
                                    border-radius: 4px;
                                    padding: 2px;
                                    margin: 0px;
                                }
                                QToolButton:hover {
                                    background-color: #e0e0e0;
                                    border: 1px solid #bbbbbb;
                                }
                                QToolButton:pressed {
                                    background-color: #d0d0d0;
                                }
                                QToolButton:disabled {
                                    background-color: transparent;
                                }
                            """)
                if fig is not None:
                    # Set figure background
                    fig.set_facecolor(self.bg_color)
                    fig.set_edgecolor(self.edge_color)
                    
                    # Update all axes in the figure
                    for ax in fig.get_axes():
                        # Set axes face color
                        ax.set_facecolor(self.bg_color)
                        
                        # Update tick parameters
                        ax.tick_params(axis='both', which='both', 
                                     colors=self.text_color,
                                     labelsize=9,
                                     width=0.8,
                                     length=4)
                        
                        # Update tick label colors
                        for label in ax.get_xticklabels() + ax.get_yticklabels():
                            label.set_color(self.text_color)
                            label.set_fontsize(9)
                        
                        # Update spine colors and width
                        for spine in ax.spines.values():
                            spine.set_edgecolor(self.edge_color)
                            spine.set_linewidth(1.0)
                        
                        # Update axis label colors and font size
                        ax.xaxis.label.set_color(self.text_color)
                        ax.yaxis.label.set_color(self.text_color)
                        ax.xaxis.label.set_fontsize(10)
                        ax.yaxis.label.set_fontsize(10)
                        
                        # Update title color and font size
                        if ax.get_title():
                            ax.title.set_color(self.text_color)
                            ax.title.set_fontsize(11)
                        
                        # Update grid
                        ax.grid(True, color=self.grid_color, linestyle=':', alpha=0.7, linewidth=0.7)
                        
                        # Update legend if it exists
                        legend = ax.get_legend()
                        if legend:
                            legend.get_frame().set_facecolor(self.bg_color)
                            legend.get_frame().set_edgecolor(self.edge_color)
                            legend.get_frame().set_alpha(0.9)
                            for text in legend.get_texts():
                                text.set_color(self.text_color)
            
            # Force a redraw of the display with updated theme colors
            if hasattr(self, 'current_image') and self.current_image is not None:
                self.update_display(self.current_image, self.current_mask, keep_rois=True)
        
        # Force garbage collection
        import gc
        gc.collect()
    
    def update_status(self, message=None):
        """Update status label with message or current tool mode
        
        Args:
            message: Optional message to display. If None, shows the current tool mode.
        """
        if message is None and hasattr(self, 'current_tool_mode'):
            # Show current tool mode if no message provided
            if self.current_tool_mode == 'select':
                message = "Mode: Draw ROI (click to add points, right-click to complete)"
            elif self.current_tool_mode == 'zoom':
                message = "Mode: Zoom (click and drag to zoom, right-click to zoom out)"
            elif self.current_tool_mode == 'pan':
                message = "Mode: Pan (click and drag to pan)"
            else:
                message = ""
        
        if hasattr(self, 'status_label') and message is not None:
            self.status_label.setText(str(message))
    
    def on_run_clicked(self, checked=None):
        """Handle run button click"""
        print("\n=== Run button clicked ===")
        print(f"Button checked state: {checked}")
        print(f"Has image_paths: {hasattr(self, 'image_paths')}")
        if hasattr(self, 'image_paths'):
            print(f"Number of images: {len(self.image_paths)}")
        print(f"Has image_list: {hasattr(self, 'image_list')}")
        if hasattr(self, 'image_list'):
            print(f"Image list count: {self.image_list.count()}")
            
        if not hasattr(self, 'image_paths') or not self.image_paths:
            error_msg = "Error: No images loaded!"
            print(error_msg)
            self.update_status(error_msg)
            return
            
        if not hasattr(self, 'image_list') or self.image_list.count() == 0:
            error_msg = "Error: No images in the list!"
            print(error_msg)
            self.update_status(error_msg)
            return
            
        print(f"Proceeding to run_segmentation with {self.image_list.count()} images")
        self.show_processing_dialog("Running segmentation...")
        self.run_segmentation()
        self.close_processing_dialog()

    def filter_small_cells(self, masks, min_size=15000):
        """Filter out cells smaller than the specified minimum size"""
        if masks is None or masks.max() == 0:
            return masks
            
        filtered_masks = np.zeros_like(masks)
        current_label = 1
        
        for label_id in np.unique(masks):
            if label_id == 0:  # Skip background
                continue
                
            # Create binary mask for current label
            mask = (masks == label_id).astype(np.uint8)
            
            # Calculate area
            area = np.sum(mask)
            
            # Only keep cells larger than min_size
            if area >= min_size:
                filtered_masks[mask > 0] = current_label
                current_label += 1
        
        print(f"Filtered out {masks.max() - (current_label - 1)} cells smaller than {min_size} pixels")
        return filtered_masks
    
    def run_segmentation(self):
        """Run Cellpose segmentation on selected images"""
        print("\n=== Starting run_segmentation ===")
        print(f"Number of images: {len(self.image_paths) if hasattr(self, 'image_paths') else 'No image_paths'}")
        print(f"Image list count: {self.image_list.count() if hasattr(self, 'image_list') else 'No image_list'}")
        
        if not hasattr(self, 'image_paths') or not self.image_paths:
            error_msg = "Error: No images loaded!"
            print(error_msg)
            self.update_status(error_msg)
            return
            
        # Get selected items or all if none selected
        selected_items = self.image_list.selectedItems()
        print(f"Selected items: {len(selected_items)}")
        if not selected_items:
            selected_items = [self.image_list.item(i) for i in range(self.image_list.count())]
            print(f"Using all {len(selected_items)} items")
            
        # Get current parameters
        model_type = self.model_combo.currentText()
        diameter = self.diameter_spin.value()
        flow_threshold = self.flow_spin.value()
        cellprob_threshold = self.cellprob_spin.value()
        
        print(f"Model: {model_type}, Diameter: {diameter}, Flow: {flow_threshold}, CellProb: {cellprob_threshold}")
        
        # Initialize model if needed
        try:
            print(f"Initializing Cellpose model with type: {model_type}")
            # Check available models
            print(f"Available models: {models.MODEL_NAMES}")
            
            # For newer versions of Cellpose, we need to use CellposeModel
            if hasattr(models, 'CellposeModel'):
                print("Using CellposeModel (newer API)")
                self.model = models.CellposeModel(
                    model_type=model_type,
                    gpu=_safe_cuda_available()
                )
            # Fallback to older API if needed
            elif hasattr(models, 'Cellpose'):
                print("Using Cellpose (older API)")
                self.model = models.Cellpose(
                    model_type=model_type,
                    gpu=_safe_cuda_available(),
                    diam_mean=diameter if diameter > 0 else None
                )
            else:
                raise ImportError("Could not find Cellpose model class. Please check your Cellpose installation.")
        except Exception as e:
            self.update_status(f"Error: Failed to initialize model: {str(e)}")
            return
        
        # Process each selected image
        for item in selected_items:
            idx = self.image_list.row(item)
            image_path = self.image_paths[idx]
            
            try:
                # Load and preprocess image
                img = tifffile.imread(image_path)
                if len(img.shape) == 3:  # Multi-frame image, use frame with highest intensity
                    img = img[np.argmax([np.mean(frame) for frame in img])]
                
                # Run segmentation
                print(f"Running segmentation with diameter={diameter}, flow_threshold={flow_threshold}, cellprob_threshold={cellprob_threshold}")
                
                # Convert image to float32 and normalize if needed
                if img.dtype != np.float32:
                    img = img.astype(np.float32)
                if img.max() > 1.0:
                    img = img / 255.0
                
                # Run segmentation with appropriate API
                if hasattr(self.model, 'eval'):
                    # Older API
                    masks, flows, _ = self.model.eval(
                        img, 
                        diameter=diameter,
                        flow_threshold=flow_threshold,
                        cellprob_threshold=cellprob_threshold
                    )
                else:
                    # Newer API
                    masks, flows, _ = self.model.eval(
                        img, 
                        channels=[0,0],  # grayscale
                        diameter=diameter,
                        flow_threshold=flow_threshold,
                        cellprob_threshold=cellprob_threshold
                    )
                
                # Filter out small cells
                min_cell_size = self.minsize_spin.value()
                filtered_masks = self.filter_small_cells(masks, min_cell_size)
                
                # Update current image and mask if this is the active image
                if image_path == self.current_image_path:
                    self.current_mask = filtered_masks
                    self.current_labels = filtered_masks.copy()
                    self.current_image_has_segmentation = True
                    self.update_display(self.current_image, filtered_masks)
                    self.populate_roi_list()  # Make sure ROI list is updated
                    self.update_status(f"Segmentation complete. Found {len(np.unique(filtered_masks))-1} cells after filtering.")
                    print(f"Filtered out {len(np.unique(masks)) - len(np.unique(filtered_masks))} cells smaller than {min_cell_size} pixels")
                    
                    # Process masks if outline mode is enabled
                    if hasattr(self, 'outline_check') and self.outline_check.isChecked():
                        outlines = np.zeros_like(filtered_masks, dtype=np.uint16)
                        for label_id in np.unique(filtered_masks):
                            if label_id == 0:  # Skip background
                                continue
                                
                            # Create binary mask for current label
                            mask = (filtered_masks == label_id).astype(np.uint8)
                            
                            # Find contours
                            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                            
                            # Draw contours with specified thickness
                            thickness = self.outline_thickness_spin.value() if hasattr(self, 'outline_thickness_spin') else 1
                            # Convert label_id to int and use it as the color (grayscale)
                            cv2.drawContours(outlines, contours, -1, int(label_id), thickness=thickness)
                        
                        # Update display with outlines
                        self.current_mask = outlines
                        self.update_display(self.current_image, self.current_mask)
            
            except Exception as e:
                error_msg = f"Error processing {os.path.basename(image_path)}: {str(e)}"
                self.update_status(error_msg)
                print(error_msg)
    
    def save_results(self, output_dir=None, transfer_to_fret=False):
        # If we have current_labels from ROI editing, make sure it's used for saving
        if hasattr(self, 'current_labels') and self.current_labels is not None:
            self.current_mask = self.current_labels.copy()
        """
        Save the segmentation results to the specified directory.
        Output directory is derived from the input file location if not specified.
        
        Args:
            output_dir: Optional output directory. If None, uses the input file's directory.
            transfer_to_fret: If True, transfer the saved mask to FRET tab after saving.
            
        Returns:
            list: List of saved file paths, or empty list on failure
        """
        if self.current_image is None:
            self.update_status("Error: No image loaded")
            return []
            
        if not hasattr(self, 'current_image_has_segmentation') or not self.current_image_has_segmentation:
            self.update_status("Error: No segmentation to save. Please run segmentation first.")
            return []
            
        try:
            # If no output directory provided, use the input file's directory
            if output_dir is None and self.current_image_path:
                output_dir = os.path.dirname(self.current_image_path)
            elif output_dir is None:
                output_dir = os.path.expanduser("~")
            
            # Create output directory structure:
            # /path/to/images/segmented/
            image_dir = os.path.dirname(self.current_image_path)
            base_name = os.path.basename(self.current_image_path)
            
            # Create output directory
            output_dir = os.path.join(image_dir, 'segmented')
            os.makedirs(output_dir, exist_ok=True)
            
            # Determine prefix based on outline mode
            prefix = "outline_segmented_" if hasattr(self, 'outline_check') and self.outline_check.isChecked() else "whole-cell_segmented_"
            
            # Create output filename with appropriate prefix in the segmented folder
            base_name = os.path.splitext(base_name)[0] + '.tif'
            output_filename = f"{prefix}{base_name}"
            output_path = os.path.join(output_dir, output_filename)
            
            # Prepare metadata as TIFF tags
            metadata = {
                'ImageDescription': f'Segmentation results for {os.path.basename(self.current_image_path)}',
                'Software': 'SONLab FRET Tool',
                'Segmentation Model': 'Cellpose',
                'Min Cell Size': str(self.minsize_spin.value())
            }
            
            print(f"Saving results to: {output_path}")
            print(f"Current mask shape: {self.current_mask.shape if hasattr(self, 'current_mask') else 'None'}")
            
            # Use current_labels if available (for ROI modifications), otherwise use current_mask
            mask_to_save = self.current_labels if hasattr(self, 'current_labels') and self.current_labels is not None else self.current_mask
            
            # Create a list to hold all frames, starting with the mask
            frames_to_save = [mask_to_save.astype(np.uint16)]
            
            # Get the original image data (from either CZI or TIFF)
            original_img = None
            if hasattr(self, 'original_czi_data') and self.original_czi_data is not None:
                original_img = self.original_czi_data
                print(f"Original CZI data shape: {original_img.shape}")
            elif hasattr(self, 'original_tiff_data') and self.original_tiff_data is not None:
                original_img = self.original_tiff_data
                print(f"Original TIFF data shape: {original_img.shape}")
            
            # Add original frames to the list
            if original_img is not None:
                if len(original_img.shape) == 3:  # Multi-frame image
                    for frame in original_img:
                        # Convert to uint16 if needed
                        if frame.dtype == np.float32:
                            frame = (frame * 65535).astype(np.uint16)
                        frames_to_save.append(frame.astype(np.uint16))
                else:  # Single frame image
                    frame = original_img
                    if frame.dtype == np.float32:
                        frame = (frame * 65535).astype(np.uint16)
                    frames_to_save.append(frame.astype(np.uint16))
            
            # Print debug info about frame shapes
            print("Frame shapes being saved:")
            for i, frame in enumerate(frames_to_save):
                print(f"  Frame {i}: {frame.shape} (dtype: {frame.dtype})")
            
            # Save all frames at once with tifffile.imwrite
            tifffile.imwrite(output_path, frames_to_save, photometric='minisblack',
                        metadata={'axes': 'CYX'}, dtype=np.uint16)
            
            print(f"Successfully saved: {output_path}")
            self.update_status(f"Segmentation saved to: {os.path.basename(output_path)}")
            
            # If transfer to FRET was requested, do it now
            if transfer_to_fret and hasattr(self, 'fret_tab'):
                try:
                    self.fret_tab.load_segmentation(output_path)
                    self.update_status(f"Segmentation saved and transferred to FRET tab: {os.path.basename(output_path)}")
                except Exception as e:
                    print(f"Error transferring to FRET tab: {str(e)}")
            
            return [output_path]
            
        except Exception as e:
            error_msg = f"Failed to save results: {str(e)}"
            self.update_status(error_msg)
            print(error_msg)
            return []
    
    def batch_segment_and_transfer(self):
        """Batch process all images, save segmentations, and transfer to FRET tab with group name"""
        if not hasattr(self, 'image_paths') or not self.image_paths:
            self.update_status("No images to process")
            return
            
        # Get group name from user
        group_dialog = QDialog(self)
        group_dialog.setWindowTitle("Assign Group for Batch")
        layout = QVBoxLayout()
        
        group_edit = QLineEdit()
        group_edit.setPlaceholderText("Enter group label")
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(group_dialog.accept)
        button_box.rejected.connect(group_dialog.reject)
        
        layout.addWidget(QLabel("Group for all images:"))
        layout.addWidget(group_edit)
        layout.addWidget(button_box)
        group_dialog.setLayout(layout)
        
        if group_dialog.exec_() != QDialog.Accepted:
            self.update_status("Batch processing cancelled")
            return
            
        group_name = group_edit.text().strip()
        if not group_name:
            self.update_status("Please enter a group name")
            return
            
        # Disable buttons during processing
        self.set_buttons_enabled(False)
        self.update_status(f"Starting batch processing of {len(self.image_paths)} images...")
        
        # Show processing dialog
        self.show_processing_dialog("Batch processing...")
        
        # Process in a separate thread to keep UI responsive
        self.batch_worker = BatchWorker(self, group_name)
        self.batch_worker.finished.connect(self.on_batch_complete)
        self.batch_worker.error.connect(self.on_batch_error)
        self.batch_worker.progress.connect(self.update_status)
        self.batch_worker.finished.connect(self.close_processing_dialog)  # Close dialog when finished
        self.batch_worker.error.connect(self.close_processing_dialog)    # Close dialog on error
        self.batch_worker.start()
    
    def on_batch_complete(self, transferred_count):
        """Called when batch processing is complete"""
        # Clear the image list and reset the display
        if transferred_count > 0:
            self.image_paths.clear()
            self.image_list.clear()
            self.clear_image_display()
            
        self.set_buttons_enabled(True)
        self.update_status(f"Batch processing complete. Transferred {transferred_count} images to FRET tab")
    
    def on_batch_error(self, error_msg):
        """Handle errors during batch processing"""
        self.set_buttons_enabled(True)
        self.update_status(f"Error during batch processing: {error_msg}")
        
    def filter_small_objects(self, masks, min_size):
        """
        Remove objects smaller than the specified minimum size.
        
        Args:
            masks: Labeled mask array (2D numpy array)
            min_size: Minimum size in pixels for objects to keep
            
        Returns:
            numpy.ndarray: Filtered mask with small objects removed
        """
        if min_size <= 0:
            return masks
            
        # Get unique labels, excluding background (0)
        labels = np.unique(masks)
        labels = labels[labels != 0]
        
        # Create output array
        filtered = np.zeros_like(masks)
        current_label = 1
        
        for label in labels:
            mask = masks == label
            if np.sum(mask) >= min_size:
                filtered[mask] = current_label
                current_label += 1
                
        return filtered
        
    def clear_image_display(self):
        """Clear the current image display and related data"""
        if hasattr(self, 'current_image'):
            self.current_image = None
        if hasattr(self, 'current_mask'):
            self.current_mask = None
        if hasattr(self, 'current_labels'):
            self.current_labels = None
        if hasattr(self, 'ax'):
            self.ax.clear()
            self.ax.axis('off')
            self.canvas.draw()
    
    def remove_selected_images(self):
        """Remove selected images from the list"""
        if not hasattr(self, 'image_list') or not hasattr(self, 'image_paths'):
            return
            
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            self.update_status("No images selected for removal")
            return
        
        # Get current selection info before any removal
        current_item = self.image_list.currentItem()
        current_row = self.image_list.row(current_item) if current_item else -1
        
        # Get the current image path for reference
        current_path = self.current_image_path if hasattr(self, 'current_image_path') else None
        
        # Find the first selected row that comes after the current row
        next_row = -1
        for row in sorted([self.image_list.row(item) for item in selected_items]):
            if row > current_row:
                next_row = row
                break
        
        # If no selected row after current, find the first before
        if next_row == -1 and selected_items:
            next_row = max(0, current_row - 1)
        
        # Remove the selected items
        for item in selected_items:
            row = self.image_list.row(item)
            if 0 <= row < len(self.image_paths):
                if current_path and self.image_paths[row] == current_path:
                    self.clear_image_display()
                self.image_paths.pop(row)
                self.image_list.takeItem(row)
                if row < next_row:
                    next_row -= 1
        
        # If we removed the current image, select the next one
        if current_item and current_item in selected_items and self.image_list.count() > 0:
            next_row = min(max(0, next_row), self.image_list.count() - 1)
            next_item = self.image_list.item(next_row)
            
            if next_item:
                # Temporarily block signals to prevent recursive updates
                self.image_list.blockSignals(True)
                
                # Set the current item and row
                self.image_list.setCurrentItem(next_item)
                self.image_list.setCurrentRow(next_row)
                
                # Update the display
                self.current_image_path = self.image_paths[next_row]
                self.load_current_image()
                
                # Force selection update
                self.image_list.clearSelection()
                self.image_list.setCurrentItem(next_item)
                self.image_list.setCurrentRow(next_row)
                
                # Re-enable signals
                self.image_list.blockSignals(False)
                
                # Ensure the list has focus to show selection
                self.image_list.setFocus()
        
        # Update status (removed duplicate status update)
        self.update_status(f"Removed {len(selected_items)} image(s) from the list")
    
    def set_buttons_enabled(self, enabled):
        """Enable/disable control buttons"""
        self.btn_load.setEnabled(enabled)
        self.btn_run.setEnabled(enabled)
        self.btn_batch.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.btn_save_transfer.setEnabled(enabled)
    
    def _transfer_to_channel(self, channel_type):
        """
        Internal method to transfer current image to a specific channel (donor/acceptor).
        
        Args:
            channel_type: Either 'donor' or 'acceptor'
        """
        if not hasattr(self, 'current_image_path') or not self.current_image_path:
            self.update_status(f"No image loaded to send to {channel_type}")
            return False
            
        if not hasattr(self, 'current_mask') or self.current_mask is None:
            self.update_status(f"No segmentation to send to {channel_type}")
            return False
            
        # Get the main window and ensure BT tab is accessible
        main_window = self.window()
        if not main_window or not hasattr(main_window, 'bt_tab'):
            self.setup_fret_tab_access()
            if not hasattr(main_window, 'bt_tab'):
                self.update_status(f"Error: Could not access BT tab to send to {channel_type}")
                return False
        
        bt_tab = main_window.bt_tab
        
        # Get the next item to select after transfer (before any removal)
        current_item = self.image_list.currentItem()
        next_row = (self.image_list.row(current_item) + 1) % self.image_list.count()
        next_item = self.image_list.item(next_row)
        
        try:
            # Create the output directory (segmented folder in the input directory)
            input_dir = os.path.dirname(self.current_image_path)
            output_dir = os.path.join(input_dir, 'segmented')
            os.makedirs(output_dir, exist_ok=True)
            
            # Determine the appropriate prefix based on outline setting
            prefix = "outline_segmented_" if hasattr(self, 'outline_check') and self.outline_check.isChecked() else "whole-cell_segmented_"
            
            # Create the output filename with the appropriate prefix
            base_name = os.path.splitext(os.path.basename(self.current_image_path))[0]
            output_filename = f"{prefix}{base_name}.tif"
            output_path = os.path.join(output_dir, output_filename)
            
            # Load the original image to get all frames
            try:
                img = tifffile.imread(self.current_image_path)
                
                # If it's a single frame, convert to 3D array (1, H, W)
                if len(img.shape) == 2:
                    img = img[np.newaxis, :, :]
                    
                # Prepare frames with label first, then all original frames in their original order
                # Use current_labels if available (contains manual edits), otherwise use current_mask
                mask_to_save = self.current_labels if hasattr(self, 'current_labels') and self.current_labels is not None else self.current_mask
                frames_to_save = [mask_to_save.astype(np.uint16)]  # Label first with manual edits if available
                frames_to_save.extend(img)  # Then all original frames
                
                # Save as a multi-frame TIFF with label as first frame
                tifffile.imwrite(output_path, np.stack(frames_to_save, axis=0), 
                               photometric='minisblack', metadata={'axes': 'CYX'}, 
                               dtype=np.uint16)
                
            except Exception as e:
                self.update_status(f"Error saving original frames: {str(e)}")
                import traceback
                traceback.print_exc()
                return False
            
            # Add to the appropriate channel in BT tab
            if channel_type == 'donor':
                if hasattr(bt_tab, 'donor_tab'):
                    # Remove the current item from the list
                    current_row = self.image_list.row(current_item)
                    if current_row >= 0 and current_row < len(self.image_paths):
                        self.image_paths.pop(current_row)
                        self.image_list.takeItem(current_row)
                        
                        # Select the next item
                        if self.image_list.count() > 0:
                            if next_row >= self.image_list.count():
                                next_row = self.image_list.count() - 1
                            next_item = self.image_list.item(next_row)
                            self.image_list.setCurrentItem(next_item)
                            self.image_list.scrollToItem(next_item)
                            # Trigger the selection change to update the display
                            self.on_image_selected(next_item, None)
                    
                    bt_tab.donor_tab.add_image_paths([output_path])
                    self.update_status(f"Sent to Donor channel: {os.path.basename(output_path)}")
                    return True
            else:  # 'acceptor'
                if hasattr(bt_tab, 'acceptor_tab'):
                    # Remove the current item from the list
                    current_row = self.image_list.row(current_item)
                    if current_row >= 0 and current_row < len(self.image_paths):
                        self.image_paths.pop(current_row)
                        self.image_list.takeItem(current_row)
                        
                        # Select the next item
                        if self.image_list.count() > 0:
                            if next_row >= self.image_list.count():
                                next_row = self.image_list.count() - 1
                            next_item = self.image_list.item(next_row)
                            self.image_list.setCurrentItem(next_item)
                            self.image_list.scrollToItem(next_item)
                            # Trigger the selection change to update the display
                            self.on_image_selected(next_item, None)
                    
                    bt_tab.acceptor_tab.add_image_paths([output_path])
                    self.update_status(f"Sent to Acceptor channel: {os.path.basename(output_path)}")
                    return True
            
            self.update_status(f"Error: Could not find {channel_type} tab in BT tab")
            return False
            
        except Exception as e:
            self.update_status(f"Error sending to {channel_type}: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def send_to_donor(self):
        """Send current image to Donor channel without group assignment"""
        self._transfer_to_channel('donor')
    
    def send_to_acceptor(self):
        """Send current image to Acceptor channel without group assignment"""
        self._transfer_to_channel('acceptor')
    
    def save_and_transfer(self):
        """Save results and transfer to FRET tab with optional group assignment"""
        # Get selected items or all if none selected
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            selected_items = [self.image_list.item(i) for i in range(self.image_list.count())]
            if not selected_items:
                self.update_status("No images to transfer")
                return
                
        # Get the next item to select after transfer (before any removal)
        current_item = self.image_list.currentItem()
        next_row = (self.image_list.row(current_item) + 1) % self.image_list.count()
        next_item = self.image_list.item(next_row)
        
        # Get group name from user (matching FRET tab's implementation)
        group_dialog = QDialog(self)
        group_dialog.setWindowTitle("Assign Group")
        layout = QVBoxLayout()
        
        group_edit = QLineEdit()
        group_edit.setPlaceholderText("Enter group label (optional)")
        if hasattr(self, 'last_used_group') and self.last_used_group:
            group_edit.setText(self.last_used_group)
            group_edit.selectAll()  # Select the text for easy replacement
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(group_dialog.accept)
        button_box.rejected.connect(group_dialog.reject)
        
        layout.addWidget(QLabel("Group:"))
        layout.addWidget(group_edit)
        layout.addWidget(button_box)
        group_dialog.setLayout(layout)
        
        # Close processing dialog before showing group dialog
        self.close_processing_dialog()
        
        if group_dialog.exec_() != QDialog.Accepted:
            self.update_status("Transfer cancelled")
            return
        
        # Show processing dialog again
        self.show_processing_dialog("Saving and transferring...")
        
        group_name = group_edit.text().strip() or None
        # Save the group name for future use
        if group_name:
            self.last_used_group = group_name
        transferred_count = 0
        
        # Get the main window and ensure FRET tab is accessible
        main_window = self.window()
        if not main_window or not hasattr(main_window, 'fret_tab'):
            self.setup_fret_tab_access()
            if not hasattr(main_window, 'fret_tab'):
                self.update_status("Error: Could not access FRET tab")
                self.close_processing_dialog()
                return
        
        fret_tab = main_window.fret_tab
        
        # Initialize necessary attributes if they don't exist
        if not hasattr(fret_tab, 'image_paths'):
            fret_tab.image_paths = []
        if not hasattr(fret_tab, 'image_groups'):
            fret_tab.image_groups = {}
        if not hasattr(fret_tab, 'analysis_results'):
            fret_tab.analysis_results = {}
        
        # Process each selected item
        transferred_paths = []
        for item in selected_items:
            idx = self.image_list.row(item)
            if idx < 0 or idx >= len(self.image_paths):
                continue
                
            image_path = self.image_paths[idx]
            
            try:
                # Save the segmentation
                saved_paths = self.save_results(transfer_to_fret=False)
                if not saved_paths:
                    self.update_status(f"No segmentation to save for {os.path.basename(image_path)}")
                    continue
                    
                saved_path = saved_paths[0]
                
                # Add to FRET tab's data structures
                if group_name:
                    fret_tab.image_groups[saved_path] = group_name
                
                # Add to FRET tab's image list if not already there
                if saved_path not in fret_tab.image_paths:
                    fret_tab.image_paths.append(saved_path)
                    
                    # Add to the list widget if it exists
                    if hasattr(fret_tab, 'image_list_widget'):
                        base_name = os.path.basename(saved_path)
                        item = QListWidgetItem(base_name)
                        
                        # Store the full path in UserRole for later reference
                        item.setData(Qt.UserRole, saved_path)
                        
                        # Update display text if grouped
                        if group_name:
                            item.setText(f"{base_name} [{group_name}]")
                            item.setToolTip(f"Group: {group_name}\nPath: {saved_path}")
                        else:
                            item.setToolTip(f"Path: {saved_path}")
                            
                        # Add to the list widget
                        fret_tab.image_list_widget.addItem(item)
                        fret_tab.image_list_widget.setCurrentItem(item)
                        
                        # Select the next item we determined earlier
                        if next_item and next_item in [self.image_list.item(i) for i in range(self.image_list.count())]:
                            self.image_list.setCurrentItem(next_item)
                            self.image_list.scrollToItem(next_item)
                            # Trigger the selection change to update the display
                            self.on_image_selected(next_item, None)
                        
                    # Just add the image to FRET tab without processing
                    # The FRET tab will handle processing when the user selects the image
                    if hasattr(fret_tab, 'update_tab_state'):
                        fret_tab.update_tab_state(True)
                    
                    # Update status to show successful transfer
                    self.update_status(f"Transferred {os.path.basename(saved_path)} to FRET tab")
                
                transferred_count += 1
                transferred_paths.append((idx, saved_path))
                
                # Force a UI update
                QApplication.processEvents()
                
            except Exception as e:
                self.update_status(f"Error processing {os.path.basename(image_path)}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Remove transferred images from the segmentation tab
        # Sort in reverse order to avoid index shifting issues
        for idx, _ in sorted(transferred_paths, key=lambda x: x[0], reverse=True):
            if 0 <= idx < len(self.image_paths):
                self.image_paths.pop(idx)
                item = self.image_list.takeItem(idx)
                if item:
                    del item
        
        if transferred_count > 0:
            self.update_status(f"Successfully transferred {transferred_count} image(s) to FRET tab")
            
            # Update the FRET tab's display if needed
            if hasattr(fret_tab, 'update_plot_display'):
                fret_tab.update_plot_display()
                
            # Clear the current image display if the current image was transferred
            if hasattr(self, 'current_image_path') and any(self.current_image_path == path for _, path in transferred_paths):
                self.clear_image_display()
        else:
            self.update_status("No images were transferred")
            
        # Close processing dialog
        self.close_processing_dialog()
        
class BatchWorker(QThread):
    """Worker thread for batch processing images"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(int)  # Number of processed images
    error = pyqtSignal(str)
    
    def __init__(self, parent, group_name):
        super().__init__(parent)
        self.parent = parent
        self.group_name = group_name
        self.running = True
    
    def run(self):
        try:
            transferred_count = 0
            total = len(self.parent.image_paths)
            
            self.progress.emit(f"Starting batch processing of {total} images...")
            
            # Initialize model if needed
            if not hasattr(self.parent, 'model') or self.parent.model is None:
                self.progress.emit("Initializing model...")
                self.initialize_model()
            
            # Process each image
            for idx in range(total):
                if not self.running:
                    self.progress.emit("Batch processing cancelled")
                    break
                    
                image_path = self.parent.image_paths[idx]
                self.progress.emit(f"Processing {idx+1}/{total}: {os.path.basename(image_path)}")
                
                try:
                    # Run segmentation
                    self.progress.emit("  Running segmentation...")
                    masks = self.run_segmentation(image_path)
                    if masks is None:
                        self.progress.emit("  No masks generated, skipping...")
                        continue
                    
                    # Save results
                    self.progress.emit("  Saving results...")
                    output_dir = os.path.join(os.path.dirname(image_path), 'segmented')
                    os.makedirs(output_dir, exist_ok=True)
                    base_name = os.path.splitext(os.path.basename(image_path))[0]
                    
                    # Determine prefix based on outline mode
                    prefix = "outline_segmented_" if hasattr(self.parent, 'outline_check') and self.parent.outline_check.isChecked() else "whole-cell_segmented_"
                    output_path = os.path.join(output_dir, f"{prefix}{base_name}.tif")
                    
                    # Load the original multi-frame image
                    original_img = tifffile.imread(image_path)
                    
                    # Create a list to hold all frames (mask first, then original frames)
                    frames_to_save = [masks.astype(np.uint16)]
                    
                    # Add original frames
                    if len(original_img.shape) == 3:  # Multi-frame image
                        for frame in original_img:
                            frames_to_save.append(frame.astype(np.uint16))
                    else:  # Single frame image
                        frames_to_save.append(original_img.astype(np.uint16))
                    
                    # Save all frames as a multi-page TIFF
                    tifffile.imwrite(output_path, frames_to_save, photometric='minisblack',
                        metadata={'axes': 'CYX'}, dtype=np.uint16)
                    
                    # Verify the file was saved and has the expected number of frames
                    if not os.path.exists(output_path):
                        self.error.emit(f"  Error: Failed to save {output_path}")
                        continue
                        
                    # Verify the saved file has the expected number of frames
                    try:
                        with tifffile.TiffFile(output_path) as tif:
                            num_frames = len(tif.pages)
                            expected_frames = 4  # Mask + 3 original frames
                            if num_frames != expected_frames:
                                self.error.emit(f"  Warning: Saved {num_frames} frames, expected {expected_frames}")
                    except Exception as e:
                        self.error.emit(f"  Warning: Could not verify saved file: {str(e)}")
                        
                    # Transfer to FRET tab
                    self.progress.emit(f"  Transferring to FRET tab: {output_path}")
                    if self.transfer_to_fret(output_path):
                        transferred_count += 1
                        self.progress.emit(f"  Successfully transferred {os.path.basename(output_path)}")
                    else:
                        self.error.emit(f"  Failed to transfer {os.path.basename(output_path)}")
                    
                except Exception as e:
                    error_msg = f"Error processing {os.path.basename(image_path)}: {str(e)}"
                    self.error.emit(error_msg)
                    import traceback
                    traceback.print_exc()
            
            self.progress.emit(f"Batch processing complete. Transferred {transferred_count}/{total} images")
            self.finished.emit(transferred_count)
            
        except Exception as e:
            error_msg = f"Batch processing error: {str(e)}"
            self.error.emit(error_msg)
            import traceback
            traceback.print_exc()
    
    def initialize_model(self):
        """Initialize the Cellpose model with current parameters"""
        model_type = self.parent.model_combo.currentText()
        diameter = self.parent.diameter_spin.value()
        
        if hasattr(models, 'CellposeModel'):
            self.parent.model = models.CellposeModel(
                model_type=model_type,
                gpu=_safe_cuda_available()
            )
        else:
            self.parent.model = models.Cellpose(
                model_type=model_type,
                gpu=_safe_cuda_available(),
                diam_mean=diameter if diameter > 0 else None
            )
    
    def run_segmentation(self, image_path):
        """Run segmentation on a single image"""
        # Load and preprocess image
        img = tifffile.imread(image_path)
        if len(img.shape) == 3:  # Multi-frame image
            # Use the frame with highest mean intensity for segmentation
            img_for_seg, _ = self.get_best_frame(img)
        else:
            img_for_seg = img
        
        # Convert image to float32 and normalize if needed
        if img.dtype != np.float32:
            img = img.astype(np.float32)
        if img.max() > 1.0:
            img = img / 255.0
        
        # Get parameters
        diameter = self.parent.diameter_spin.value()
        flow_threshold = self.parent.flow_spin.value()
        cellprob_threshold = self.parent.cellprob_spin.value()
        
        # Run segmentation
        if hasattr(self.parent.model, 'eval'):
            masks, _, _ = self.parent.model.eval(
                img,
                diameter=diameter,
                flow_threshold=flow_threshold,
                cellprob_threshold=cellprob_threshold,
                channels=[0,0]  # Grayscale
            )
        else:
            masks, _, _ = self.parent.model.eval(
                [img],
                diameter=diameter,
                flow_threshold=flow_threshold,
                cellprob_threshold=cellprob_threshold,
                channels=[0,0]  # Grayscale
            )
            masks = masks[0]  # Get first (only) result
        
        # Filter small objects
        min_size = self.parent.minsize_spin.value() if hasattr(self.parent, 'minsize_spin') else 10
        filtered_masks = self.parent.filter_small_objects(masks, min_size)
        
        # Apply outline processing if enabled
        if hasattr(self.parent, 'outline_check') and self.parent.outline_check.isChecked():
            outlines = np.zeros_like(filtered_masks, dtype=np.uint16)
            for label_id in np.unique(filtered_masks):
                if label_id == 0:  # Skip background
                    continue
                    
                # Create binary mask for current label
                mask = (filtered_masks == label_id).astype(np.uint8)
                
                # Find contours
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                # Draw contours with specified thickness
                thickness = self.parent.outline_thickness_spin.value() if hasattr(self.parent, 'outline_thickness_spin') else 1
                # Convert label_id to int and use it as the color (grayscale)
                cv2.drawContours(outlines, contours, -1, int(label_id), thickness=thickness)
            
            return outlines
        
        return filtered_masks

    def get_best_frame(self, img):
        """Get the frame with the highest mean intensity from a multi-frame image.
        
        Args:
            img: Input image (can be single or multi-frame)
            
        Returns:
            The best frame (2D numpy array) and its index
        """
        if not isinstance(img, np.ndarray) or img.ndim != 3 or img.shape[0] <= 1:
            return img, 0 if isinstance(img, np.ndarray) and img.ndim == 3 else None
            
        # Calculate mean intensity for each frame
        frame_means = [np.mean(frame) for frame in img]
        best_frame_idx = np.argmax(frame_means)
        return img[best_frame_idx], best_frame_idx

        
    def transfer_to_fret(self, saved_path):
        """Transfer a single segmentation to the FRET tab and ensure it's fully functional"""
        try:
            self.progress.emit(f"  Starting transfer of {saved_path}")
            
            # Get the main window and ensure FRET tab is accessible
            main_window = self.parent.window()
            if not hasattr(main_window, 'fret_tab'):
                # Try to set up FRET tab access if not already available
                if hasattr(self.parent, 'setup_fret_tab_access'):
                    self.parent.setup_fret_tab_access()
                    if not hasattr(main_window, 'fret_tab'):
                        self.error.emit("  Error: Could not access FRET tab after setup")
                        return False
                else:
                    self.error.emit("  Error: Main window does not have a FRET tab")
                    return False
            
            fret_tab = main_window.fret_tab
            
            # Initialize data structures if needed
            if not hasattr(fret_tab, 'image_paths'):
                fret_tab.image_paths = []
                self.progress.emit("  Initialized image_paths")
                
            if not hasattr(fret_tab, 'image_groups'):
                fret_tab.image_groups = {}
                self.progress.emit("  Initialized image_groups")
            
            # Add to FRET tab's data structures
            if self.group_name:
                fret_tab.image_groups[saved_path] = self.group_name
                self.progress.emit(f"  Added to group: {self.group_name}")
            
            # Add to FRET tab's image list if not already there
            if saved_path not in fret_tab.image_paths:
                # Add to the internal list first
                fret_tab.image_paths.append(saved_path)
                self.progress.emit(f"  Added to image_paths: {saved_path}")
                
                # Add to the list widget if it exists
                if hasattr(fret_tab, 'image_list_widget'):
                    base_name = os.path.basename(saved_path)
                    item = QListWidgetItem(base_name)
                    
                    # Store the full path in UserRole for later reference
                    item.setData(Qt.UserRole, saved_path)
                    
                    # Update display text if grouped
                    if self.group_name:
                        item.setText(f"{base_name} [{self.group_name}]")
                        item.setToolTip(f"Group: {self.group_name}\nPath: {saved_path}")
                    else:
                        item.setToolTip(f"Path: {saved_path}")
                    
                    # Add to the list widget
                    fret_tab.image_list_widget.addItem(item)
                    self.progress.emit(f"  Added to list widget: {base_name}")
                    
                    # Select the newly added item
                    fret_tab.image_list_widget.setCurrentItem(item)
                    
                    # Update the tab state to enable all controls
                    if hasattr(fret_tab, 'update_tab_state'):
                        fret_tab.update_tab_state(True)
                        self.progress.emit("  Enabled FRET tab controls")
                    
                    # Just add the image to FRET tab without processing
                    # The FRET tab will handle processing when the user selects the image
                    self.progress.emit(f"  Added {os.path.basename(saved_path)} to FRET tab")
                    self.progress.emit("  Image ready for processing in FRET tab")
                    return True
            
            self.progress.emit(f"  Successfully transferred {os.path.basename(saved_path)}")
            return True
            
        except Exception as e:
            error_msg = f"Transfer error: {str(e)}"
            self.error.emit(error_msg)
            import traceback
            traceback.print_exc()
            return False
    
    def stop(self):
        """Stop the batch processing"""
        self.running = False
