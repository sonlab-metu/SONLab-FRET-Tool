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
try:
    from GUI.debug import dprint
except (ImportError, ModuleNotFoundError):
    from debug import dprint
import os
import sys
import time
import numpy as np
import tifffile
import cv2
from scipy.ndimage import binary_erosion
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
    dprint("Warning: czifile module not found. CZI file support will be disabled.")

# PyQt5 Imports
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFileDialog, QListWidget, QListWidgetItem, QMessageBox, 
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QSplitter,
    QSlider, QSizePolicy, QToolButton, QStyle, QToolTip, QProgressDialog, QScrollArea,
    QTabWidget, QInputDialog, QProgressBar, QApplication, QButtonGroup
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMimeData, QTimer, QSize, QPoint, QObject, QEvent
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QDragEnterEvent, QDropEvent

# Matplotlib imports
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.widgets import PolygonSelector, RectangleSelector, EllipseSelector
from matplotlib.patches import Polygon as MplPolygon

try:
    from GUI import theme as theme_system
    from GUI import widgets as ui_widgets
except (ImportError, ModuleNotFoundError):
    import theme as theme_system
    import widgets as ui_widgets


def intensity_to_uint16(frame):
    """Convert an intensity frame to uint16 while preserving its *original*
    numeric values.

    Frames coming from CZI/TIFF sources hold raw detector counts (e.g. 16-bit
    microscope data), not values normalised to [0, 1]. They must therefore be
    written out verbatim -- never rescaled. Integer frames are returned
    unchanged (cast to uint16); floating-point frames are rounded to the nearest
    integer and clipped to the uint16 range so the saved values are identical to
    the source intensities for ordinary 16-bit data.

    Note: this deliberately does NOT multiply by 65535. Doing so corrupts raw
    counts by overflowing the uint16 range (the cause of issue #51).
    """
    frame = np.asarray(frame)
    if np.issubdtype(frame.dtype, np.integer):
        # Already integral counts -- clip to the uint16 range to be safe.
        return np.clip(frame, 0, 65535).astype(np.uint16)
    # Floating-point raw counts: round to nearest integer, then clip.
    return np.clip(np.rint(frame.astype(np.float64)), 0, 65535).astype(np.uint16)


# Debug information
dprint("\n=== Python Environment ===")
dprint(f"Python version: {sys.version}")
dprint(f"Working directory: {os.getcwd()}")

# Import Cellpose with error handling
CELLPOSE_AVAILABLE = False
try:
    import cellpose
    from cellpose import models, utils, io
    
    # Get Cellpose version
    try:
        cellpose_version = importlib.metadata.version('cellpose')
        dprint(f"Cellpose version: {cellpose_version}")
    except:
        dprint("Could not determine Cellpose version")
    
    # Debug available models and functions
    dprint("\n=== Cellpose Debug Info ===")
    dprint(f"Cellpose available: {CELLPOSE_AVAILABLE}")
    dprint(f"Models module: {dir(models)}")
    
    if hasattr(models, 'MODEL_NAMES'):
        dprint(f"Available models: {models.MODEL_NAMES}")
    else:
        dprint("MODEL_NAMES not found in models")
        
    CELLPOSE_AVAILABLE = True
    
except ImportError as e:
    dprint(f"\n=== Cellpose Import Error ===")
    dprint(f"Error importing Cellpose: {e}")
    dprint("Please install Cellpose with: pip install cellpose")
    dprint("Or with GPU support: pip install cellpose[all]")
    
# Import OpenCV with error handling
try:
    import cv2
    dprint(f"\nOpenCV version: {cv2.__version__}")
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    dprint("\nWarning: OpenCV not available. Some features may be limited.")

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
            'outline_only': False,
            'segment_both': False,
            'adjust_outline': True,
            'outline_thickness': 10,
            # Channel registry: which raw input frame index holds each channel.
            # Segmentation normalizes output to [label, FRET, Donor, Acceptor].
            'fret_index': 0,
            'donor_index': 1,
            'acceptor_index': 2,
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
        self.both_check.toggled.connect(self._throttled_save_prefs)
        self.outline_thickness_check.toggled.connect(self._throttled_save_prefs)
        self.outline_thickness_spin.valueChanged.connect(self._throttled_save_prefs)
        self.fret_index_spin.valueChanged.connect(self._throttled_save_prefs)
        self.donor_index_spin.valueChanged.connect(self._throttled_save_prefs)
        self.acceptor_index_spin.valueChanged.connect(self._throttled_save_prefs)
        
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
        from PyQt5.QtWidgets import QHBoxLayout, QLabel

        # Create container widget and layout
        container = QWidget()
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(5)  # Add some spacing between elements

        # Add label
        label = QLabel(label_text)
        hbox.addWidget(label, stretch=1)  # Allow label to expand

        # Shared, theme-aware info control
        hbox.addWidget(ui_widgets.info_button(tooltip_text), alignment=Qt.AlignLeft)

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
                    
        dprint("Drag enter ignored - no valid files found")
        event.ignore()
    
    def dragLeaveEvent(self, event):
        """Handle drag leave event"""
        event.accept()
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop event to load CZI and TIFF files"""
        dprint("\n=== Drop Event Triggered ===")
        dprint(f"MIME formats: {event.mimeData().formats()}")
        
        if not event.mimeData().hasUrls():
            dprint("No URLs in mime data")
            event.ignore()
            return
            
        # Get list of valid image files
        image_files = []
        urls = event.mimeData().urls()
        dprint(f"Number of URLs: {len(urls)}")
        
        for i, url in enumerate(urls):
            try:
                file_path = url.toLocalFile()
                dprint(f"\nProcessing URL {i+1}:")
                dprint(f"  - URL: {url.toString()}")
                dprint(f"  - Local file: {file_path}")
                dprint(f"  - URL scheme: {url.scheme()}")
                
                # Skip if no file path
                if not file_path:
                    dprint("  - Skipping: Empty file path")
                    continue
                    
                # Normalize the path and check if it exists
                file_path = os.path.abspath(file_path)
                file_exists = os.path.exists(file_path)
                dprint(f"  - Absolute path: {file_path}")
                dprint(f"  - File exists: {file_exists}")
                
                if not file_exists:
                    dprint(f"  - Skipping: File does not exist")
                    continue
                    
                # Check file extension (case insensitive)
                file_path_lower = file_path.lower()
                is_czi = file_path_lower.endswith('.czi')
                is_tiff = file_path_lower.endswith(('.tif', '.tiff'))
                
                if is_czi or is_tiff:
                    dprint(f"  - Found {'CZI' if is_czi else 'TIFF'} file")
                    
                    # For CZI files, verify we can open them
                    if is_czi:
                        if not CZI_AVAILABLE:
                            dprint("  - Skipping: CZI support not available (install czifile package)")
                            continue
                            
                        try:
                            # Quick check if file is a valid CZI
                            with open(file_path, 'rb') as f:
                                header = f.read(4)
                                dprint(f"  - File header: {header}")
                                if header != b'ZISR':
                                    dprint(f"  - Error: Not a valid CZI file (expected 'ZISR' header)")
                                    continue
                                    
                            # Test opening with czifile
                            dprint("  - Testing CZI file with czifile...")
                            try:
                                with czifile.CziFile(file_path) as czi:
                                    dprint(f"  - Successfully opened CZI file")
                                    dprint(f"  - CZI shape: {czi.shape}")
                                    dprint(f"  - CZI size: {czi.size}")
                                    if hasattr(czi, 'metadata'):
                                        dprint("  - CZI metadata available")
                                    else:
                                        dprint("  - No CZI metadata available")
                                
                                # If we got here, the file is valid
                                dprint("  - CZI file is valid")
                                image_files.append(file_path)
                                
                            except Exception as czierr:
                                dprint(f"  - Error opening CZI with czifile: {str(czierr)}")
                                continue
                                
                        except Exception as e:
                            dprint(f"  - Error checking CZI file: {str(e)}")
                            continue
                    else:
                        # For TIFF files, just add them
                        image_files.append(file_path)
                        dprint(f"  - Added TIFF file")
                else:
                    dprint(f"  - Skipping: Unsupported file type")
                    
            except Exception as e:
                dprint(f"  - Error processing file: {str(e)}")
                continue
        
        dprint(f"\nFound {len(image_files)} valid image files to add")
        
        if not image_files:
            dprint("No valid image files found in drop")
            QMessageBox.warning(self, "Unsupported File", 
                              "Only CZI, TIFF, and TIF files are supported.")
            event.ignore()
            return
            
        dprint("\n=== Adding files to image list ===")
        # Add files to the image list
        self._add_image_paths(image_files)
        event.acceptProposedAction()
        
        # Force UI update
        QApplication.processEvents()
        dprint("=== Drop Event Complete ===\n")
    
    def _convert_czi_to_tiff(self, czi_path):
        """Convert CZI file to 3-frame TIFF stack (FRET, Donor, Acceptor)
        
        Returns:
            str: Path to the saved TIFF file, or None if conversion failed
        """
        dprint(f"Converting CZI to TIFF: {czi_path}")
        
        # Create output path with .tif extension
        base_path = os.path.splitext(czi_path)[0]
        output_path = f"{base_path}.tif"
        
        try:
            # Read the CZI file
            with czifile.CziFile(czi_path) as czi:
                images = czi.asarray()
                dprint(f"CZI shape: {images.shape}")
                
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
                        dprint(f"Unexpected CZI shape: {images.shape}. Expected 7 or 8 dimensions.")
                        return None
                    
                    # Verify we have at least 4 channels
                    if num_channels < 4:
                        dprint(f"Expected at least 4 channels, found {num_channels}")
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
                    dprint(f"Saved 3-frame TIFF: {output_path}")
                    return output_path
                    
                except IndexError as e:
                    dprint(f"Error extracting channels: {e}")
                    dprint(f"CZI shape: {images.shape}")
                    dprint("Expected shape: [T=1, Scene=1, C=4, Z=1, Y, X, S=1]")
                    return None
                    
        except Exception as e:
            import traceback
            dprint(f"Error converting CZI to TIFF: {e}")
            dprint(traceback.format_exc())
            return None
    
    def _add_image_paths(self, file_paths):
        """Helper method to add image paths to the list"""
        dprint("\n=== _add_image_paths ===")
        dprint(f"Input file_paths: {file_paths}")
        
        if not file_paths:
            dprint("No file paths provided")
            return
            
        # Initialize image_paths if it doesn't exist
        if not hasattr(self, 'image_paths') or not isinstance(self.image_paths, list):
            dprint("Initializing image_paths")
            self.image_paths = []
        
        # Process each file
        processed_paths = []
        
        # Debug: Print current image_paths
        dprint(f"Current image_paths before adding: {self.image_paths}")
        
        for file_path in file_paths:
            file_path = os.path.abspath(str(file_path))
            dprint(f"\nProcessing: {file_path}")
            
            # Skip if already in list
            if file_path in [os.path.abspath(str(p)) for p in self.image_paths]:
                dprint(f"  - Already in list, skipping")
                continue
                
            # Handle CZI files
            if file_path.lower().endswith('.czi'):
                if not CZI_AVAILABLE:
                    dprint("  - CZI support not available. Install with 'pip install czifile'")
                    continue
                    
                # Convert CZI to TIFF
                tiff_path = self._convert_czi_to_tiff(file_path)
                if tiff_path and os.path.exists(tiff_path):
                    dprint(f"  - Converted CZI to TIFF: {tiff_path}")
                    processed_paths.append(tiff_path)
                else:
                    dprint(f"  - Failed to convert CZI: {file_path}")
            
            # Handle TIFF files
            elif file_path.lower().endswith(('.tif', '.tiff')):
                if os.path.exists(file_path):
                    dprint(f"  - Adding TIFF file: {file_path}")
                    processed_paths.append(file_path)
                else:
                    dprint(f"  - File not found: {file_path}")
            
            else:
                dprint(f"  - Unsupported file type: {file_path}")
        
        if not processed_paths:
            msg = "No valid files to add"
            dprint(msg)
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
            dprint(f"Selected new file at index {first_new_index}")
            
            # Manually trigger selection change to ensure preview updates
            current_item = self.image_list.currentItem()
            if current_item:
                self.on_image_selected(current_item)
        
        # Update status
        status_msg = f"Added {len(processed_paths)} new image(s)"
        dprint(status_msg)
        self.update_status(status_msg)
        
        # Force UI update
        QApplication.processEvents()
        dprint("=== End _add_image_paths ===\n")
        
    def update_image_list_widget(self):
        """Update the image list widget with current image_paths"""
        dprint("Updating image list widget...")
        dprint(f"Current image_paths: {self.image_paths}")
        
        if not hasattr(self, 'image_list'):
            dprint("Error: image_list widget doesn't exist!")
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
                    dprint(f"  - Added to list: {display_name}")
                    
                except Exception as e:
                    dprint(f"Error adding {path} to list: {str(e)}")
            
            # Restore selection if possible
            if current_path and current_path in self.image_paths:
                index = self.image_paths.index(current_path)
                if 0 <= index < self.image_list.count():
                    self.image_list.setCurrentRow(index)
                    dprint(f"  - Restored selection to row {index}")
            
            # If no selection, select the first item
            if self.image_list.currentRow() < 0 and self.image_list.count() > 0:
                self.image_list.setCurrentRow(0)
                
        finally:
            # Always unblock signals when done
            self.image_list.blockSignals(False)
            
        dprint(f"List widget updated with {self.image_list.count()} items")
        
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
        left_panel.setContentsMargins(4, 4, 4, 4)
        left_panel.setSpacing(9)

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
        ui_widgets.set_button_icon(self.btn_load, "folder")
        button_row.addWidget(self.btn_load)
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self.remove_selected_images)
        self.btn_remove.setToolTip("Remove selected images from the list")
        self.btn_remove.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        ui_widgets.set_button_icon(self.btn_remove, "trash")
        button_row.addWidget(self.btn_remove)
        self.btn_metadata = QPushButton("Metadata")
        self.btn_metadata.clicked.connect(self.view_metadata)
        self.btn_metadata.setToolTip("View the metadata / tags of the selected image")
        self.btn_metadata.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        ui_widgets.set_button_icon(self.btn_metadata, "info")
        button_row.addWidget(self.btn_metadata)
        button_row.addStretch()
        list_container.addLayout(button_row)
        left_panel.addLayout(list_container)

        # Drag-and-drop placeholder
        self.drop_hint = QLabel("Drag & drop TIFF or CZI files here")
        self._style_drop_hint()
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
        ui_widgets.set_button_icon(self.add_roi_btn, "plus")
        self.del_roi_btn = QPushButton("Delete ROI")
        self.del_roi_btn.clicked.connect(self.delete_selected_roi)
        self.del_roi_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        ui_widgets.set_button_icon(self.del_roi_btn, "trash")
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
        self.btn_run.setObjectName("primaryButton")
        ui_widgets.set_button_icon(self.btn_run, "play", on_accent=True)
        self.btn_batch = QPushButton("Batch Segment && Transfer")
        self.btn_batch.clicked.connect(self.batch_segment_and_transfer)
        self.btn_batch.setToolTip("Process all images and transfer to FRET tab with group name")
        self.btn_batch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        ui_widgets.set_button_icon(self.btn_batch, "layers")
        self.btn_save = QPushButton("Save Results")
        self.btn_save.clicked.connect(self.save_results)
        self.btn_save.setToolTip("Save segmentation results to a 'segmented' directory")
        self.btn_save.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        ui_widgets.set_button_icon(self.btn_save, "save")
        # Create transfer buttons
        self.btn_save_transfer = QPushButton("FRET Tab")
        self.btn_save_transfer.clicked.connect(self.save_and_transfer)
        self.btn_save_transfer.setToolTip("Save results and transfer to the FRET tab with optional group assignment")
        self.btn_save_transfer.setObjectName("successButton")
        ui_widgets.set_button_icon(self.btn_save_transfer, "send", on_accent=True)

        self.btn_send_donor = QPushButton("Donor")
        self.btn_send_donor.clicked.connect(self.send_to_donor)
        self.btn_send_donor.setToolTip("Send the current image to the Donor channel without group assignment")
        self.btn_send_donor.setObjectName("primaryButton")
        ui_widgets.set_button_icon(self.btn_send_donor, "send", on_accent=True)

        self.btn_send_acceptor = QPushButton("Acceptor")
        self.btn_send_acceptor.clicked.connect(self.send_to_acceptor)
        self.btn_send_acceptor.setToolTip("Send the current image to the Acceptor channel without group assignment")
        self.btn_send_acceptor.setObjectName("dangerButton")
        ui_widgets.set_button_icon(self.btn_send_acceptor, "send", on_accent=True)

        self.btn_send_intensity = QPushButton("Intensity")
        self.btn_send_intensity.clicked.connect(self.send_to_intensity)
        self.btn_send_intensity.setToolTip(
            "Save the current segmentation and add it to the Intensity Analysis tab.\n"
            "Enable 'Segment both (membrane + whole-cell)' for membrane-vs-whole-cell analysis.")
        ui_widgets.set_button_icon(self.btn_send_intensity, "send", on_accent=True)

        # Set fixed size policy for all buttons
        for btn in [self.btn_save_transfer, self.btn_send_donor, self.btn_send_acceptor, self.btn_send_intensity]:
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        # Add buttons to layout with spacing
        transfer_button_layout = QHBoxLayout()
        send_to_label = QLabel("Send to:")
        send_to_label.setStyleSheet("font-weight: 600;")
        transfer_button_layout.addWidget(send_to_label)
        transfer_button_layout.addWidget(self.btn_send_donor)
        transfer_button_layout.addSpacing(5)
        transfer_button_layout.addWidget(self.btn_send_acceptor)
        transfer_button_layout.addSpacing(5)
        transfer_button_layout.addWidget(self.btn_send_intensity)
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
        self.outline_check.setChecked(False)
        self.outline_check.setToolTip("When checked, only cell outlines will be generated instead of filled masks.")
        self.outline_check.toggled.connect(self.update_outline_controls)
        params_layout.addRow(self.outline_check)
        # "Segment both" writes a combined stack [outline, filled, ...raw channels]
        # for the Intensity/Densitometry tab (membrane vs whole-cell). It does not
        # follow the FRET channel-order registry; raw frames are kept in input order.
        self.both_check = QCheckBox("Segment both (membrane + whole-cell)")
        self.both_check.setChecked(False)
        self.both_check.setToolTip(
            "When checked, saving/sending writes a single stack laid out as\n"
            "[outline, filled, ...raw channels] for the Intensity Analysis tab.\n"
            "The whole-cell mask is used for display and ROI editing; the outline\n"
            "(membrane) is derived from it at save time using the outline thickness.")
        self.both_check.toggled.connect(self.update_outline_controls)
        params_layout.addRow(self.both_check)
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

        # Channel-order registry: lets the user declare which frame of their raw
        # input stack is FRET / Donor / Acceptor. Segmentation reorders the saved
        # stack to the canonical [label, FRET, Donor, Acceptor] the BT and FRET
        # tabs expect, so the analysis stays correct regardless of acquisition order.
        channel_group = QGroupBox("Channel Order (input frames)")
        channel_layout = QFormLayout()
        channel_layout.setSpacing(5)
        channel_layout.setLabelAlignment(Qt.AlignRight)

        def _make_channel_spin(default_value):
            spin = QSpinBox()
            spin.setRange(0, 63)
            spin.setValue(default_value)
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return spin

        self.fret_index_spin = _make_channel_spin(0)
        self.donor_index_spin = _make_channel_spin(1)
        self.acceptor_index_spin = _make_channel_spin(2)
        self.add_info_icon(channel_layout, "FRET frame:", self.fret_index_spin,
                           "0-based frame index of the FRET channel in your raw input stack.")
        self.add_info_icon(channel_layout, "Donor frame:", self.donor_index_spin,
                           "0-based frame index of the Donor channel in your raw input stack.")
        self.add_info_icon(channel_layout, "Acceptor frame:", self.acceptor_index_spin,
                           "0-based frame index of the Acceptor channel (used for 4-channel / S3-S4 data).")
        channel_note = QLabel("Saved as: [label, FRET, Donor, Acceptor]")
        channel_note.setWordWrap(True)
        channel_note.setStyleSheet("font-style: italic;")
        channel_layout.addRow(channel_note)
        channel_group.setLayout(channel_layout)
        left_panel.addWidget(channel_group)

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
        
        # Set matplotlib rcParams from the central design system so plots match
        # the current theme (no global plt.style.use, which would leak into
        # every other tab's figures).
        theme_name = 'dark' if is_dark_theme else 'light'
        theme_system.apply_matplotlib_style(theme_name)

        # Create figure with theme-appropriate colors
        self.figure, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(8, 8), num=fig_num)
        theme_system.apply_figure_theme(self.figure, theme_name)

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
            dprint("Config manager not available, cannot save preferences")
            return False
            
        try:
            dprint("Saving preferences to config...")
            
            # Get current UI values
            model = self.model_combo.currentText()
            diameter = self.diameter_spin.value()
            flow_threshold = self.flow_spin.value()
            cellprob_threshold = self.cellprob_spin.value()
            min_size = self.minsize_spin.value()
            outline_only = self.outline_check.isChecked()
            segment_both = self.both_check.isChecked()
            adjust_outline = self.outline_thickness_check.isChecked()
            outline_thickness = self.outline_thickness_spin.value()
            
            dprint(f"Saving preferences: model={model}, diameter={diameter}, flow={flow_threshold}, "
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
            self.config.set('cellpose.display.segment_both', bool(segment_both))
            self.config.set('cellpose.display.adjust_outline', bool(adjust_outline))
            self.config.set('cellpose.display.outline_thickness', int(outline_thickness))

            # Save channel-order registry (which raw input frame is each channel)
            self.config.set('cellpose.channels.fret_index', int(self.fret_index_spin.value()))
            self.config.set('cellpose.channels.donor_index', int(self.donor_index_spin.value()))
            self.config.set('cellpose.channels.acceptor_index', int(self.acceptor_index_spin.value()))

            # Save window state and geometry if available
            if hasattr(self, 'saveGeometry'):
                try:
                    self.config.set('cellpose.window.geometry', bytes(self.saveGeometry()).hex())
                except Exception as e:
                    dprint(f"Warning: Could not save window geometry: {e}")
            
            # Save splitter state if available
            if hasattr(self, 'splitter') and self.splitter:
                try:
                    self.config.set('cellpose.window.splitter_state', bytes(self.splitter.saveState()).hex())
                except Exception as e:
                    dprint(f"Warning: Could not save splitter state: {e}")
            
            # Save to disk
            success = self.config.sync()
            if success:
                dprint("Preferences saved successfully")
            else:
                dprint("Warning: Failed to sync preferences to disk")
                
            return success
            
        except Exception as e:
            import traceback
            dprint(f"Error saving preferences: {e}")
            dprint(traceback.format_exc())
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
            dprint(f"Error restoring window state: {e}")
    
    def load_preferences(self):
        """Load preferences from config manager"""
        if not self.config:
            dprint("Config manager not available")
            return
            
        try:
            dprint("Loading preferences from config...")
            
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
            segment_both = bool(self.config.get('cellpose.display.segment_both', self.default_params['segment_both']))
            adjust_outline = bool(self.config.get('cellpose.display.adjust_outline', self.default_params['adjust_outline']))
            outline_thickness = int(self.config.get('cellpose.display.outline_thickness', self.default_params['outline_thickness']))

            # Load channel-order registry with defaults
            fret_index = int(self.config.get('cellpose.channels.fret_index', self.default_params['fret_index']))
            donor_index = int(self.config.get('cellpose.channels.donor_index', self.default_params['donor_index']))
            acceptor_index = int(self.config.get('cellpose.channels.acceptor_index', self.default_params['acceptor_index']))

            dprint(f"Loaded preferences: model={model}, diameter={diameter}, flow={flow_threshold}, "
                  f"cellprob={cellprob_threshold}, min_size={min_size}, outline_only={outline_only}, "
                  f"adjust_outline={adjust_outline}, outline_thickness={outline_thickness}")
            
            # Block signals while updating UI to prevent multiple saves
            self.model_combo.blockSignals(True)
            self.diameter_spin.blockSignals(True)
            self.flow_spin.blockSignals(True)
            self.cellprob_spin.blockSignals(True)
            self.minsize_spin.blockSignals(True)
            self.outline_check.blockSignals(True)
            self.both_check.blockSignals(True)
            self.outline_thickness_check.blockSignals(True)
            self.outline_thickness_spin.blockSignals(True)
            self.fret_index_spin.blockSignals(True)
            self.donor_index_spin.blockSignals(True)
            self.acceptor_index_spin.blockSignals(True)

            # Update UI controls
            index = self.model_combo.findText(model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            else:
                dprint(f"Warning: Model '{model}' not found in combo box")
                
            self.diameter_spin.setValue(diameter)
            self.flow_spin.setValue(flow_threshold)
            self.cellprob_spin.setValue(cellprob_threshold)
            self.minsize_spin.setValue(min_size)
            self.outline_check.setChecked(outline_only)
            self.both_check.setChecked(segment_both)
            self.outline_thickness_check.setChecked(adjust_outline)
            self.outline_thickness_spin.setValue(outline_thickness)
            self.fret_index_spin.setValue(fret_index)
            self.donor_index_spin.setValue(donor_index)
            self.acceptor_index_spin.setValue(acceptor_index)

            # Update internal state
            self.update_outline_controls()
            
            # Re-enable signals
            self.model_combo.blockSignals(False)
            self.diameter_spin.blockSignals(False)
            self.flow_spin.blockSignals(False)
            self.cellprob_spin.blockSignals(False)
            self.minsize_spin.blockSignals(False)
            self.outline_check.blockSignals(False)
            self.both_check.blockSignals(False)
            self.outline_thickness_check.blockSignals(False)
            self.outline_thickness_spin.blockSignals(False)
            self.fret_index_spin.blockSignals(False)
            self.donor_index_spin.blockSignals(False)
            self.acceptor_index_spin.blockSignals(False)

            dprint("Preferences loaded successfully")
            
        except Exception as e:
            import traceback
            dprint(f"Error loading preferences: {e}")
            dprint(traceback.format_exc())
    
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
            dprint(f"Warning: Could not set up FRET tab access: {str(e)}")
            
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
                
            dprint(f"Initialized Cellpose model: {model_type}")
            dprint(f"Using GPU: {use_gpu}")
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

    def view_metadata(self):
        """Show the metadata dialog for the currently selected image."""
        path = getattr(self, 'current_image_path', None)
        if not path:
            row = self.image_list.currentRow()
            if 0 <= row < len(self.image_paths):
                path = str(self.image_paths[row])
        ui_widgets.show_metadata_dialog(self, path)

    def _channel_registry(self):
        """Return the (FRET, Donor, Acceptor) input-frame indices from the
        channel-order UI, defaulting to the canonical 0/1/2 if not built yet."""
        if hasattr(self, 'fret_index_spin'):
            return (self.fret_index_spin.value(),
                    self.donor_index_spin.value(),
                    self.acceptor_index_spin.value())
        return (0, 1, 2)

    def _ordered_analysis_frames(self, original_frames):
        """Reorder the raw input frames into the canonical FRET, Donor, Acceptor
        order declared in the channel registry.

        Returns a list of frames (the caller prepends the label), so the saved
        stack becomes ``[label, FRET, Donor, Acceptor]`` — the layout the BT and
        FRET tabs expect. Out-of-range indices are skipped (with a status note)
        so a short stack still saves. With the default 0/1/2 mapping on a
        3-frame input this reproduces the previous output exactly.
        """
        if isinstance(original_frames, np.ndarray) and original_frames.ndim == 2:
            frames = [original_frames]
        else:
            frames = list(original_frames)
        n = len(frames)

        ordered, missing = [], []
        for name, idx in zip(("FRET", "Donor", "Acceptor"), self._channel_registry()):
            if 0 <= idx < n:
                ordered.append(frames[idx])
            else:
                missing.append(f"{name}={idx}")
        if not ordered:
            # Never produce an empty stack; fall back to the original order.
            ordered = frames
        if missing:
            self.update_status(
                "Channel order: frame index out of range for " + ", ".join(missing)
                + f" (stack has {n} frame(s)); skipped.")
        return ordered

    def _labels_to_outline(self, filled_labels, thickness=None):
        """Convert a filled label mask into an inward membrane-band label mask.

        For each cell the band starts at the cell border and grows *inward* by
        ``thickness`` pixels, so the whole band lies **inside** the cell —
        ``band = mask AND NOT erode(mask, thickness)``. This is the physically
        correct membrane region: unlike an outline drawn centred on the boundary
        (cv2.drawContours), no band pixel falls outside the cell. Erosion is done
        per label, so touching cells keep separate, correctly-labelled bands and
        the Intensity tab can pair membrane and whole-cell per cell.
        """
        if thickness is None:
            thickness = self.outline_thickness_spin.value() if hasattr(self, 'outline_thickness_spin') else 1
        thickness = max(1, int(thickness))
        outlines = np.zeros_like(filled_labels, dtype=np.uint16)
        for label_id in np.unique(filled_labels):
            if label_id == 0:  # Skip background
                continue
            mask = filled_labels == label_id
            eroded = binary_erosion(mask, iterations=thickness)
            band = mask & ~eroded  # border pixels going inward by `thickness`
            outlines[band] = int(label_id)
        return outlines

    def _both_stack_frames(self, filled_labels, original_img):
        """Assemble the combined ``[outline, filled, ...raw channels]`` stack for
        the Intensity/Densitometry tab (membrane vs whole-cell).

        The outline (membrane) is derived from ``filled_labels`` so the two masks
        share label ids. Raw frames are kept in their original input order — this
        path is intentionally NOT reordered by the FRET channel registry, since
        the Intensity tab declares its own channel layout.
        """
        outline = self._labels_to_outline(filled_labels)
        frames = [outline.astype(np.uint16), np.asarray(filled_labels).astype(np.uint16)]
        if original_img is not None:
            if isinstance(original_img, np.ndarray) and original_img.ndim == 2:
                raw_frames = [original_img]
            else:
                raw_frames = list(original_img)
            for frame in raw_frames:
                frames.append(intensity_to_uint16(frame))
        return frames

    def _segment_both_enabled(self):
        """True when the 'Segment both (membrane + whole-cell)' option is on."""
        return getattr(self, 'both_check', None) is not None and self.both_check.isChecked()

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
        
        # Convert to uint16 for TIFF saving, preserving the raw intensity
        # values exactly (no [0, 1] rescaling -- see intensity_to_uint16).
        if czi_data.dtype != np.uint16:
            czi_data = intensity_to_uint16(czi_data)
        
        # Save as TIFF
        tifffile.imwrite(temp_path, czi_data, photometric='minisblack',
                        metadata={'axes': 'CYX'})
        dprint(f"Saved CZI data as temporary TIFF: {temp_path}")
        # Track for cleanup so converted-CZI temp files don't accumulate on disk.
        if not hasattr(self, '_temp_files'):
            self._temp_files = []
        self._temp_files.append(temp_path)
        return temp_path

    def _cleanup_temp_files(self):
        """Delete any temporary TIFFs created from CZI conversions."""
        for path in getattr(self, '_temp_files', []):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                dprint(f"Could not remove temp file {path}: {e}")
        self._temp_files = []
    
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
            dprint(f"\n=== Loading image: {self.current_image_path} ===")
            
            # Read TIFF file (could be multi-frame)
            img = tifffile.imread(self.current_image_path)
            dprint(f"Loaded TIFF with shape: {img.shape}")
            
            # Handle multi-frame TIFF (should be 3 frames: FRET, Donor, Acceptor)
            if len(img.shape) == 3:
                dprint(f"Multi-frame TIFF detected with {img.shape[0]} frames")
                
                # Store all frames for saving later
                self.original_tiff_data = img
                
                # Find and use the best frame (highest mean intensity) for display and segmentation
                best_frame, best_idx = self.get_best_frame(img)
                img = best_frame
                dprint(f"Using frame {best_idx} (0-based) with highest mean intensity for segmentation")
            
            # Convert to float32 and normalize to 0-1
            img = img.astype(np.float32)
            img_normalized = (img - img.min()) / (img.max() - img.min() + 1e-6)
            
            # Store the original normalized image
            self.current_image = img_normalized
            
            dprint(f"Image loaded successfully, shape: {self.current_image.shape}")
            
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
        """Handle brightness slider change (fast, throttled base-image update)."""
        self.brightness = value / 100.0
        self.brightness_value.setText(f"{value}%")
        self._prefs_dirty = True
        self._schedule_bc_update()

    def on_contrast_changed(self, value):
        """Handle contrast slider change (fast, throttled base-image update)."""
        self.contrast = value / 100.0
        self.contrast_value.setText(f"{value}%")
        self._prefs_dirty = True
        self._schedule_bc_update()

    def _schedule_bc_update(self):
        """Rate-limit brightness/contrast redraws with a trailing update so the
        final slider value is always shown (the old time-throttle could drop it)."""
        timer = getattr(self, '_bc_timer', None)
        if timer is None:
            self._bc_timer = timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._flush_bc_update)
            self._bc_pending = False
        if timer.isActive():
            self._bc_pending = True
        else:
            self._apply_brightness_contrast()
            timer.start(30)

    def _flush_bc_update(self):
        if getattr(self, '_bc_pending', False):
            self._bc_pending = False
            self._apply_brightness_contrast()
            self._bc_timer.start(30)

    def _apply_brightness_contrast(self):
        """Re-apply brightness/contrast to *only* the base image artist.

        This skips the expensive parts of update_display (rebuilding the colored
        mask overlay, regionprops labels, tight_layout), so dragging the sliders
        stays smooth even with many ROIs.
        """
        base = getattr(self, '_disp_norm_base', None)
        img_artist = getattr(self, '_ax1_image', None)
        if base is None or img_artist is None or getattr(self, 'current_image', None) is None:
            if getattr(self, 'current_image', None) is not None:
                self.update_display(self.current_image, keep_rois=True)
            return
        contrast = getattr(self, 'contrast', 1.0) * 4.0
        brightness = getattr(self, 'brightness', 0.5) - 0.5
        img = np.clip((base - 0.5) * contrast + 0.5 + brightness, 0.0, 1.0)
        gamma = getattr(self, 'gamma', 0.5) * 2.0
        if gamma != 1.0:
            img = np.power(img, 1.0 / max(gamma, 0.1))
        img_artist.set_data((img * 255).astype(np.uint8))
        self.canvas.draw_idle()
    
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
            dprint(f"Error in auto-adjust: {str(e)}")
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
    
    def _label_overlay_cmap(self):
        """A cached 256-colour HSV colormap (alpha 0.5) for the label overlay."""
        cmap = getattr(self, '_overlay_cmap', None)
        if cmap is None:
            import matplotlib
            from matplotlib.colors import ListedColormap
            colours = matplotlib.colormaps['hsv'].resampled(256)(np.arange(256))
            colours[:, 3] = 0.5  # semi-transparent so the base image shows through
            self._overlay_cmap = cmap = ListedColormap(colours)
        return cmap

    def update_display(self, img, mask=None, keep_rois=False):
        """Update the image display with the current image and optional mask
        
        Args:
            img: Input image (can be multi-frame)
            mask: Optional segmentation mask
            keep_rois: If True, preserve existing ROIs when updating display
        """
        # Update figure and axes colors to match the current application theme
        theme_name = theme_system.current_theme_name()
        if hasattr(self, 'figure') and self.figure:
            theme_system.apply_figure_theme(self.figure, theme_name)
        try:
            # Clear the axes
            self.ax1.clear()
            self.ax2.clear()
            
            # Get display image (first frame if multi-frame)
            display_img = self.get_display_image(img)
            
            # Store the original image if this is a new image
            if not hasattr(self, 'current_image') or not keep_rois:
                self.current_image = display_img.copy()
            
            # Cache a normalised copy of the base image so brightness/contrast
            # can be re-applied cheaply (see _apply_brightness_contrast) without
            # rebuilding the whole display.
            base = self.current_image.astype(np.float32)
            mn, mx = float(base.min()), float(base.max())
            self._disp_norm_base = (base - mn) / (mx - mn) if mx > mn else np.zeros_like(base)

            # Apply display settings to the original image
            display_img = self.apply_display_effects(self.current_image)

            # Display the processed image (keep the artist for fast updates)
            self._ax1_image = self.ax1.imshow(display_img, cmap='gray', vmin=0, vmax=255)
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
                from skimage.measure import regionprops

                # Overlay the labels as a masked array coloured on the fly by a
                # cached colormap. This avoids allocating a full float64 (H, W, 4)
                # RGBA array (hundreds of MB for large images) and the per-label
                # Python loop that the previous implementation rebuilt every call.
                labels = self.current_labels
                overlay = np.ma.masked_where(labels == 0, labels % 256)
                self.ax2.imshow(overlay, cmap=self._label_overlay_cmap(),
                                vmin=0, vmax=255, interpolation='nearest')

                # Add region numbers (skip when too dense to be readable).
                regions = regionprops(labels.astype(np.int32))
                if len(regions) <= 250:
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
            dprint(f"Error updating display: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def update_outline_controls(self):
        """Update the state of outline controls based on checkboxes"""
        both_enabled = getattr(self, 'both_check', None) is not None and self.both_check.isChecked()

        # "Segment both" takes precedence: the whole-cell mask is shown/edited and
        # the outline is derived at save time, so "outlines only" is not meaningful
        # while it is on.
        if both_enabled and self.outline_check.isChecked():
            self.outline_check.blockSignals(True)
            self.outline_check.setChecked(False)
            self.outline_check.blockSignals(False)
        self.outline_check.setEnabled(not both_enabled)

        outlines_enabled = self.outline_check.isChecked()
        # The outline thickness is needed whenever an outline is produced — either
        # in outline-only mode or as the membrane frame of a "both" stack.
        needs_outline = outlines_enabled or both_enabled
        thickness_enabled = needs_outline and self.outline_thickness_check.isChecked()

        self.outline_thickness_check.setEnabled(needs_outline)
        self.outline_thickness_spin.setEnabled(thickness_enabled)

        # If no outline is produced at all, uncheck the thickness checkbox
        if not needs_outline:
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
                dprint(f"Error parsing ROI label: {e}")
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
    
    # ==================================================================
    # ROI drawing panel
    #
    # Interaction model (why node edits no longer spawn ROIs):
    #   matplotlib's PolygonSelector fires ``onselect`` on *every* change to a
    #   completed polygon (including dragging a vertex). We therefore treat that
    #   callback as "the pending shape changed" -- it never writes to the label
    #   image. A shape is only rasterised into ``current_labels`` when the user
    #   explicitly clicks "Add This ROI", which then clears the selector for the
    #   next shape. Nodes can be adjusted freely with no side effects.
    # ==================================================================
    def reset_roi_view(self):
        """Reset the ROI view to show the entire image."""
        if getattr(self, 'roi_ax', None) is None or getattr(self, 'roi_canvas', None) is None:
            return
        if getattr(self, 'current_labels', None) is not None:
            shape = self.current_labels.shape
        elif getattr(self, 'original_display_img', None) is not None:
            shape = self.original_display_img.shape
        else:
            shape = (1000, 1000)
        self.roi_ax.set_xlim(0, shape[1])
        self.roi_ax.set_ylim(shape[0], 0)
        self.roi_canvas.draw_idle()

    def _schedule_roi_display(self):
        """Rate-limit brightness/contrast redraws so dragging stays responsive.

        The first change is applied immediately; further changes during the
        short cooldown are coalesced into a single trailing update. This caps the
        redraw rate (~40 fps) instead of redrawing on every intermediate slider
        value.
        """
        timer = getattr(self, '_roi_update_timer', None)
        if timer is None:
            self.update_roi_display()
            return
        if timer.isActive():
            self._roi_update_pending = True
        else:
            self.update_roi_display()
            timer.start(25)

    def _flush_roi_display(self):
        if getattr(self, '_roi_update_pending', False):
            self._roi_update_pending = False
            self.update_roi_display()
            self._roi_update_timer.start(25)

    def update_roi_display(self):
        """Apply the brightness/contrast sliders to the ROI editor image.

        The image is normalised to [0, 1] once (``_roi_norm_base``) when the
        editor opens; each update only applies a cheap affine contrast/brightness
        transform, avoiding a full re-normalisation of every pixel per tick.
        """
        base = getattr(self, '_roi_norm_base', None)
        if base is None or getattr(self, 'roi_image', None) is None:
            return
        brightness = self.brightness_slider.value() / 100.0
        contrast = self.contrast_slider.value() / 100.0
        if contrast >= 0:
            img = (1.0 + contrast) * (base - 0.5) + 0.5
        else:
            img = (1.0 + contrast) * base + 0.5 * (1.0 - contrast)
        img = np.clip(img + brightness, 0.0, 1.0)
        self.roi_image.set_data(img)
        self.roi_canvas.draw_idle()

    def reset_roi_adjustments(self):
        """Reset the brightness/contrast sliders to their defaults."""
        for slider in (getattr(self, 'brightness_slider', None), getattr(self, 'contrast_slider', None)):
            if slider is not None:
                slider.blockSignals(True)
                slider.setValue(0)
                slider.blockSignals(False)
        self.update_roi_display()

    def start_roi(self):
        """Open the ROI editor for the current image.

        View navigation (pan / zoom / home) uses the standard matplotlib toolbar.
        Drawing uses a shape selector (polygon / rectangle / ellipse); while the
        toolbar is in pan or zoom mode matplotlib's ``widgetlock`` automatically
        suspends the selector, so the two never fight over the mouse.
        """
        if self.current_image is None:
            return
        try:
            display_img = self.get_display_image(self.current_image)

            # Ensure a label image exists to receive ROIs.
            if getattr(self, 'current_labels', None) is None:
                self.current_labels = np.zeros(display_img.shape[:2], dtype=np.uint16)

            # Re-open cleanly if a previous editor is still around.
            self._teardown_roi_editor()
            self.add_roi_btn.setEnabled(False)

            # Non-pyplot figure so it is freed as soon as we drop our references.
            self.roi_figure = Figure(figsize=(8, 8))
            self.roi_ax = self.roi_figure.add_subplot(111)
            self.roi_canvas = FigureCanvas(self.roi_figure)

            self.original_display_img = display_img.copy()
            # Normalise once; brightness/contrast then only apply a cheap affine.
            base = self.original_display_img.astype(np.float32)
            mn, mx = float(base.min()), float(base.max())
            self._roi_norm_base = (base - mn) / (mx - mn + 1e-8)
            self._pending_shape = None
            self._roi_undo_stack = []
            self.roi_shape = 'polygon'
            self._draw_enabled = True

            self.roi_image = self.roi_ax.imshow(self._roi_norm_base, cmap='gray', vmin=0.0, vmax=1.0)
            self.roi_ax.axis('off')
            theme_system.apply_figure_theme(self.roi_figure, theme_system.current_theme_name())

            # ---- Window & layout ----
            self.roi_window = QWidget()
            self.roi_window.setWindowTitle("Draw ROIs")
            self.roi_window.setWindowModality(Qt.ApplicationModal)
            self.roi_window.resize(1000, 820)
            main_layout = QVBoxLayout(self.roi_window)
            main_layout.setContentsMargins(8, 8, 8, 8)
            main_layout.setSpacing(8)

            # Coalesce rapid brightness/contrast changes into throttled redraws.
            self._roi_update_timer = QTimer(self.roi_window)
            self._roi_update_timer.setSingleShot(True)
            self._roi_update_timer.timeout.connect(self._flush_roi_display)
            self._roi_update_pending = False

            # ---- Draw controls + actions ----
            action_bar = QHBoxLayout()
            self.draw_toggle = QPushButton("Draw")
            self.draw_toggle.setCheckable(True)
            self.draw_toggle.setChecked(True)
            self.draw_toggle.setObjectName("primaryButton")
            self.draw_toggle.setToolTip("Toggle ROI drawing on/off (turn off to pan/zoom freely)")
            self.draw_toggle.toggled.connect(self._toggle_draw)
            ui_widgets.set_button_icon(self.draw_toggle, "plus", on_accent=True)
            action_bar.addWidget(self.draw_toggle)

            action_bar.addWidget(QLabel("Shape:"))
            self.shape_combo = QComboBox()
            self.shape_combo.addItems(["Polygon", "Rectangle", "Ellipse"])
            self.shape_combo.setToolTip("Polygon: click to add vertices, close the loop.\n"
                                        "Rectangle / Ellipse: click and drag, then adjust handles.")
            self.shape_combo.currentTextChanged.connect(self._on_shape_changed)
            action_bar.addWidget(self.shape_combo)

            action_bar.addSpacing(18)
            self.commit_roi_btn = QPushButton("Add This ROI")
            self.commit_roi_btn.setObjectName("successButton")
            self.commit_roi_btn.setToolTip("Write the current shape into the mask as a new ROI")
            self.commit_roi_btn.setEnabled(False)
            self.commit_roi_btn.clicked.connect(self.commit_pending_roi)
            ui_widgets.set_button_icon(self.commit_roi_btn, "check", on_accent=True)
            action_bar.addWidget(self.commit_roi_btn)

            self.undo_roi_btn = QPushButton("Undo Last")
            self.undo_roi_btn.setToolTip("Remove the most recently added ROI")
            self.undo_roi_btn.setEnabled(False)
            self.undo_roi_btn.clicked.connect(self.undo_last_roi)
            ui_widgets.set_button_icon(self.undo_roi_btn, "undo")
            action_bar.addWidget(self.undo_roi_btn)

            self.clear_shape_btn = QPushButton("Clear Shape")
            self.clear_shape_btn.setToolTip("Discard the shape currently being drawn")
            self.clear_shape_btn.clicked.connect(self.clear_pending_roi)
            ui_widgets.set_button_icon(self.clear_shape_btn, "clear")
            action_bar.addWidget(self.clear_shape_btn)

            action_bar.addStretch()
            done_btn = QPushButton("Done")
            done_btn.setObjectName("primaryButton")
            done_btn.clicked.connect(self.roi_window.close)
            ui_widgets.set_button_icon(done_btn, "check", on_accent=True)
            action_bar.addWidget(done_btn)
            main_layout.addLayout(action_bar)

            # ---- Matplotlib navigation toolbar (pan / zoom / home / save) ----
            self.roi_toolbar = NavigationToolbar2QT(self.roi_canvas, self.roi_window)
            for action in self.roi_toolbar.actions():
                if action.text() in ('Subplots', 'Customize'):
                    action.setVisible(False)
            theme_system.style_toolbar(self.roi_toolbar, theme_system.current_theme_name())
            main_layout.addWidget(self.roi_toolbar)

            # ---- Brightness / contrast ----
            controls = QHBoxLayout()
            controls.addWidget(QLabel("Brightness:"))
            self.brightness_slider = QSlider(Qt.Horizontal)
            self.brightness_slider.setRange(-100, 100)
            self.brightness_slider.setValue(0)
            self.brightness_slider.valueChanged.connect(self._schedule_roi_display)
            controls.addWidget(self.brightness_slider)
            controls.addWidget(QLabel("Contrast:"))
            self.contrast_slider = QSlider(Qt.Horizontal)
            self.contrast_slider.setRange(-100, 100)
            self.contrast_slider.setValue(0)
            self.contrast_slider.valueChanged.connect(self._schedule_roi_display)
            controls.addWidget(self.contrast_slider)
            bc_reset = QPushButton("Reset")
            bc_reset.setToolTip("Reset brightness and contrast")
            bc_reset.clicked.connect(self.reset_roi_adjustments)
            controls.addWidget(bc_reset)
            reset_view_btn = QPushButton("Reset View")
            reset_view_btn.setToolTip("Fit the whole image in the view")
            reset_view_btn.clicked.connect(self.reset_roi_view)
            ui_widgets.set_button_icon(reset_view_btn, "refresh")
            controls.addWidget(reset_view_btn)
            main_layout.addLayout(controls)

            # ---- Canvas ----
            self.roi_canvas.setParent(self.roi_window)
            main_layout.addWidget(self.roi_canvas, 1)

            # ---- Hint / status line ----
            self.roi_hint_label = QLabel()
            main_layout.addWidget(self.roi_hint_label)

            self.roi_window.closeEvent = self.roi_window_closed

            self.reset_roi_view()
            self._make_selector()
            self.roi_canvas.mpl_connect('scroll_event', self.on_mouse_scroll)
            self._update_roi_hint()

            self.roi_window.show()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Error", f"Failed to start ROI drawing: {e}")
            self.add_roi_btn.setEnabled(True)

    def _make_selector(self):
        """Create the selector for the current shape, disconnecting any old one."""
        old = getattr(self, 'poly_selector', None)
        if old is not None:
            try:
                old.set_active(False)
                old.disconnect_events()
            except Exception:
                pass
            self.poly_selector = None

        green = '#00e676'
        if self.roi_shape == 'rectangle':
            self.poly_selector = RectangleSelector(
                self.roi_ax, self._on_rect_select, useblit=True, button=[1],
                interactive=True, minspanx=3, minspany=3, spancoords='data',
                props=dict(facecolor=green, edgecolor=green, alpha=0.25, fill=True, linewidth=1.5),
            )
        elif self.roi_shape == 'ellipse':
            self.poly_selector = EllipseSelector(
                self.roi_ax, self._on_ellipse_select, useblit=True, button=[1],
                interactive=True, minspanx=3, minspany=3, spancoords='data',
                props=dict(facecolor=green, edgecolor=green, alpha=0.25, fill=True, linewidth=1.5),
            )
        else:  # polygon
            self.poly_selector = PolygonSelector(
                self.roi_ax, self._on_poly_select, useblit=True,
                props=dict(color=green, linewidth=1.5, alpha=0.9),
                handle_props=dict(markerfacecolor=green, markeredgecolor='white', markersize=7),
                grab_range=12,
            )
        self.poly_selector.set_active(bool(getattr(self, '_draw_enabled', True)))

    # -- selector callbacks: store the pending shape, never commit here --------
    def _on_poly_select(self, verts):
        if verts is not None and len(verts) >= 3:
            self._set_pending(('polygon', np.asarray(verts, dtype=float)))
        else:
            self._set_pending(None)

    def _on_rect_select(self, eclick, erelease):
        self._set_pending_from_extents('rectangle')

    def _on_ellipse_select(self, eclick, erelease):
        self._set_pending_from_extents('ellipse')

    def _set_pending_from_extents(self, kind):
        try:
            xmin, xmax, ymin, ymax = self.poly_selector.extents
        except Exception:
            self._set_pending(None)
            return
        if abs(xmax - xmin) < 1 or abs(ymax - ymin) < 1:
            self._set_pending(None)
        else:
            self._set_pending((kind, (xmin, xmax, ymin, ymax)))

    def _set_pending(self, shape):
        self._pending_shape = shape
        if hasattr(self, 'commit_roi_btn'):
            self.commit_roi_btn.setEnabled(shape is not None)
        self._update_roi_hint()

    def _toggle_draw(self, enabled):
        """Enable/disable drawing so the user can pan/zoom or click freely."""
        self._draw_enabled = bool(enabled)
        if getattr(self, 'poly_selector', None) is not None:
            self.poly_selector.set_active(self._draw_enabled)
        if getattr(self, 'roi_canvas', None) is not None:
            self.roi_canvas.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        self._update_roi_hint()

    def _on_shape_changed(self, text):
        self.roi_shape = text.strip().lower()
        self._set_pending(None)
        self._make_selector()
        if getattr(self, 'roi_canvas', None) is not None:
            self.roi_canvas.draw_idle()
        self._update_roi_hint()

    def commit_pending_roi(self):
        """Rasterise the pending shape into the label image as one new ROI."""
        shape = getattr(self, '_pending_shape', None)
        if shape is None or self.current_labels is None:
            return
        from skimage.draw import polygon as sk_polygon, ellipse as sk_ellipse
        kind, data = shape
        h, w = self.current_labels.shape
        if kind == 'polygon':
            verts = data
            xs = np.clip(verts[:, 0], 0, w - 1)
            ys = np.clip(verts[:, 1], 0, h - 1)
            rr, cc = sk_polygon(ys, xs, self.current_labels.shape)
        elif kind == 'rectangle':
            xmin, xmax, ymin, ymax = data
            r0, r1 = sorted((int(round(ymin)), int(round(ymax))))
            c0, c1 = sorted((int(round(xmin)), int(round(xmax))))
            r0, c0 = max(r0, 0), max(c0, 0)
            r1, c1 = min(r1, h - 1), min(c1, w - 1)
            rr, cc = np.mgrid[r0:r1 + 1, c0:c1 + 1]
            rr, cc = rr.ravel(), cc.ravel()
        else:  # ellipse
            xmin, xmax, ymin, ymax = data
            yc, xc = (ymin + ymax) / 2.0, (xmin + xmax) / 2.0
            ry, rx = abs(ymax - ymin) / 2.0, abs(xmax - xmin) / 2.0
            rr, cc = sk_ellipse(yc, xc, ry, rx, shape=self.current_labels.shape)

        if rr.size == 0:
            self._update_roi_hint()
            return

        new_label = int(self.current_labels.max()) + 1
        self.current_labels[rr, cc] = new_label
        self._roi_undo_stack.append(new_label)

        self._set_pending(None)
        self.undo_roi_btn.setEnabled(True)
        self._make_selector()  # fresh shape for the next ROI
        if getattr(self, 'roi_canvas', None) is not None:
            self.roi_canvas.draw_idle()
        self.update_display(self.current_image, keep_rois=True)
        self.populate_roi_list()
        self._update_roi_hint(committed=new_label)

    def undo_last_roi(self):
        """Remove the most recently committed ROI."""
        if not getattr(self, '_roi_undo_stack', None):
            return
        label = self._roi_undo_stack.pop()
        self.current_labels[self.current_labels == label] = 0
        self.renumber_labels()
        self._roi_undo_stack = list(range(1, int(self.current_labels.max()) + 1))
        self.undo_roi_btn.setEnabled(bool(self._roi_undo_stack))
        self.update_display(self.current_image, keep_rois=True)
        self.populate_roi_list()
        self._update_roi_hint()

    def clear_pending_roi(self):
        """Discard the shape currently being drawn."""
        self._set_pending(None)
        self._make_selector()
        if getattr(self, 'roi_canvas', None) is not None:
            self.roi_canvas.draw_idle()

    def _update_roi_hint(self, committed=None):
        if not hasattr(self, 'roi_hint_label'):
            return
        n = len(getattr(self, '_roi_undo_stack', []) or [])
        if not getattr(self, '_draw_enabled', True):
            msg = "Drawing off – pan/zoom with the toolbar, or turn Draw back on."
        elif committed is not None:
            msg = f"Added ROI #{committed}. Draw the next shape, or click Done."
        elif getattr(self, '_pending_shape', None) is not None:
            msg = "Shape ready – adjust it, then click 'Add This ROI'."
        elif getattr(self, 'roi_shape', 'polygon') == 'polygon':
            msg = "Polygon: click to add vertices, close the loop to finish."
        else:
            msg = f"{self.roi_shape.title()}: click and drag on the image, then adjust the handles."
        self.roi_hint_label.setText(f"{msg}   ({n} ROI(s) this session)")

    def on_mouse_scroll(self, event):
        """Ctrl+scroll to zoom the ROI view around the cursor."""
        if getattr(self, 'roi_ax', None) is None or event.inaxes != self.roi_ax:
            return
        if event.key != 'control':
            return
        xdata, ydata = event.xdata, event.ydata
        if xdata is None or ydata is None:
            return
        xlim = self.roi_ax.get_xlim()
        ylim = self.roi_ax.get_ylim()
        zoom = 1.1 if event.button == 'up' else 0.9
        x_range = (xlim[1] - xlim[0]) * zoom
        y_range = (ylim[1] - ylim[0]) * zoom
        x_frac = (xdata - xlim[0]) / (xlim[1] - xlim[0])
        y_frac = (ydata - ylim[0]) / (ylim[1] - ylim[0])
        self.roi_ax.set_xlim([xdata - x_frac * x_range, xdata + (1 - x_frac) * x_range])
        self.roi_ax.set_ylim([ydata - (1 - y_frac) * y_range, ydata + y_frac * y_range])
        self.roi_canvas.draw_idle()

    def roi_window_closed(self, event):
        """Finalise the editor: tear it down and free its matplotlib objects."""
        try:
            self._teardown_roi_editor()
            if hasattr(self, 'add_roi_btn'):
                self.add_roi_btn.setEnabled(True)
            if getattr(self, 'current_image', None) is not None:
                self.update_display(self.current_image, keep_rois=True)
                self.populate_roi_list()
        except Exception as e:
            dprint(f"Error cleaning up ROI window: {e}")
        event.accept()

    def _teardown_roi_editor(self):
        """Disconnect the selector and drop references so the figure is freed."""
        sel = getattr(self, 'poly_selector', None)
        if sel is not None:
            try:
                sel.disconnect_events()
            except Exception:
                pass
        self.poly_selector = None

        canvas = getattr(self, 'roi_canvas', None)
        if canvas is not None:
            try:
                canvas.setParent(None)
                canvas.close()
            except Exception:
                pass

        for attr in ('roi_toolbar', 'roi_canvas', 'roi_image', 'roi_ax', 'roi_figure'):
            if hasattr(self, attr):
                setattr(self, attr, None)
        self._pending_verts = None

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
                dprint(f"Error closing ROI window: {e}")
        
        # Clean up matplotlib figures and any converted-CZI temp files
        self.cleanup_figures()
        self._cleanup_temp_files()

        # Call parent close event
        super().closeEvent(event)
    
    def cleanup_figures(self):
        """Clean up all matplotlib figures."""
        # Close all tracked figures
        for fig in getattr(self, '_figures', []):
            try:
                plt.close(fig)
            except Exception as e:
                dprint(f"Error closing figure: {e}")
        
        # Clear the figures list
        if hasattr(self, '_figures'):
            self._figures.clear()
            
    def _style_drop_hint(self):
        """Style the drag-and-drop placeholder for the current theme."""
        if not hasattr(self, 'drop_hint'):
            return
        c = theme_system.palette(theme_system.current_theme_name())
        self.drop_hint.setStyleSheet(
            f"QLabel {{ color: {c['text_muted']}; font-style: italic; padding: 10px;"
            f" border: 2px dashed {c['border_strong']}; border-radius: 8px; margin: 4px; }}"
        )

    def update_theme(self):
        """Update the plot colors and toolbar icons when the application theme changes."""
        app = QApplication.instance()
        is_dark = app.palette().window().color().lightness() < 128
        self.current_theme = 'dark' if is_dark else 'light'
        self._style_drop_hint()

        # Pull the canonical colours from the central design system and keep the
        # per-tab attributes other methods rely on (self.bg_color, etc.) in sync.
        m = theme_system.mpl_colors(self.current_theme)
        self.text_color = m['fg']
        self.bg_color = m['bg']
        self.grid_color = m['grid']
        self.edge_color = m['edge']

        # Update matplotlib rcParams (no global plt.style.use side effects).
        theme_system.apply_matplotlib_style(self.current_theme)

        # Tint the navigation-toolbar icons; the toolbar chrome itself is styled
        # by the global QToolBar rules in the application style sheet.
        theme_system.style_navigation_toolbars(self, self.current_theme)

        # Recolour every figure/axes owned by this tab.
        if hasattr(self, 'ax1') and hasattr(self, 'ax2'):
            for fig in (getattr(self, attr, None) for attr in ('figure', 'roi_figure')):
                theme_system.apply_figure_theme(fig, self.current_theme)

            # Redraw the canvases so the new background/edge colours take effect
            # even when no image is loaded yet.
            for canvas_attr in ('canvas', 'roi_canvas'):
                canvas = getattr(self, canvas_attr, None)
                if canvas is not None:
                    canvas.draw_idle()

            # Force a full redraw of the display when an image is present.
            if hasattr(self, 'current_image') and self.current_image is not None:
                self.update_display(self.current_image, self.current_mask, keep_rois=True)

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
        dprint("\n=== Run button clicked ===")
        dprint(f"Button checked state: {checked}")
        dprint(f"Has image_paths: {hasattr(self, 'image_paths')}")
        if hasattr(self, 'image_paths'):
            dprint(f"Number of images: {len(self.image_paths)}")
        dprint(f"Has image_list: {hasattr(self, 'image_list')}")
        if hasattr(self, 'image_list'):
            dprint(f"Image list count: {self.image_list.count()}")
            
        if not hasattr(self, 'image_paths') or not self.image_paths:
            error_msg = "Error: No images loaded!"
            dprint(error_msg)
            self.update_status(error_msg)
            return
            
        if not hasattr(self, 'image_list') or self.image_list.count() == 0:
            error_msg = "Error: No images in the list!"
            dprint(error_msg)
            self.update_status(error_msg)
            return
            
        dprint(f"Proceeding to run_segmentation with {self.image_list.count()} images")
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
        
        dprint(f"Filtered out {masks.max() - (current_label - 1)} cells smaller than {min_size} pixels")
        return filtered_masks
    
    def run_segmentation(self):
        """Run Cellpose segmentation on selected images"""
        dprint("\n=== Starting run_segmentation ===")
        dprint(f"Number of images: {len(self.image_paths) if hasattr(self, 'image_paths') else 'No image_paths'}")
        dprint(f"Image list count: {self.image_list.count() if hasattr(self, 'image_list') else 'No image_list'}")
        
        if not hasattr(self, 'image_paths') or not self.image_paths:
            error_msg = "Error: No images loaded!"
            dprint(error_msg)
            self.update_status(error_msg)
            return
            
        # Get selected items or all if none selected
        selected_items = self.image_list.selectedItems()
        dprint(f"Selected items: {len(selected_items)}")
        if not selected_items:
            selected_items = [self.image_list.item(i) for i in range(self.image_list.count())]
            dprint(f"Using all {len(selected_items)} items")
            
        # Get current parameters
        model_type = self.model_combo.currentText()
        diameter = self.diameter_spin.value()
        flow_threshold = self.flow_spin.value()
        cellprob_threshold = self.cellprob_spin.value()
        
        dprint(f"Model: {model_type}, Diameter: {diameter}, Flow: {flow_threshold}, CellProb: {cellprob_threshold}")
        
        # Initialize model if needed
        try:
            dprint(f"Initializing Cellpose model with type: {model_type}")
            # Check available models
            dprint(f"Available models: {models.MODEL_NAMES}")
            
            # For newer versions of Cellpose, we need to use CellposeModel
            if hasattr(models, 'CellposeModel'):
                dprint("Using CellposeModel (newer API)")
                self.model = models.CellposeModel(
                    model_type=model_type,
                    gpu=_safe_cuda_available()
                )
            # Fallback to older API if needed
            elif hasattr(models, 'Cellpose'):
                dprint("Using Cellpose (older API)")
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
                dprint(f"Running segmentation with diameter={diameter}, flow_threshold={flow_threshold}, cellprob_threshold={cellprob_threshold}")
                
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
                    dprint(f"Filtered out {len(np.unique(masks)) - len(np.unique(filtered_masks))} cells smaller than {min_cell_size} pixels")
                    
                    # Process masks if outline-only mode is enabled. In "segment
                    # both" mode the whole-cell mask stays on screen (and editable);
                    # its outline is derived at save time.
                    if hasattr(self, 'outline_check') and self.outline_check.isChecked():
                        outlines = self._labels_to_outline(filtered_masks)
                        # Update display with outlines
                        self.current_mask = outlines
                        self.update_display(self.current_image, self.current_mask)
            
            except Exception as e:
                error_msg = f"Error processing {os.path.basename(image_path)}: {str(e)}"
                self.update_status(error_msg)
                dprint(error_msg)
    
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
            
            # Determine prefix based on segmentation mode
            if self._segment_both_enabled():
                prefix = "both_segmented_"
            elif hasattr(self, 'outline_check') and self.outline_check.isChecked():
                prefix = "outline_segmented_"
            else:
                prefix = "whole-cell_segmented_"

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
            
            dprint(f"Saving results to: {output_path}")
            dprint(f"Current mask shape: {self.current_mask.shape if hasattr(self, 'current_mask') else 'None'}")
            
            # Use current_labels if available (for ROI modifications), otherwise use current_mask
            mask_to_save = self.current_labels if hasattr(self, 'current_labels') and self.current_labels is not None else self.current_mask

            # Get the original image data (from either CZI or TIFF)
            original_img = None
            if hasattr(self, 'original_czi_data') and self.original_czi_data is not None:
                original_img = self.original_czi_data
                dprint(f"Original CZI data shape: {original_img.shape}")
            elif hasattr(self, 'original_tiff_data') and self.original_tiff_data is not None:
                original_img = self.original_tiff_data
                dprint(f"Original TIFF data shape: {original_img.shape}")

            if self._segment_both_enabled():
                # Combined membrane + whole-cell stack for the Intensity tab:
                # [outline, filled, ...raw channels in input order].
                frames_to_save = self._both_stack_frames(mask_to_save, original_img)
            else:
                # Canonical [label, FRET, Donor, Acceptor]: mask first, then the raw
                # frames reordered per the channel registry. Raw intensity values are
                # preserved exactly (no [0, 1] rescaling -- see intensity_to_uint16).
                frames_to_save = [mask_to_save.astype(np.uint16)]
                if original_img is not None:
                    for frame in self._ordered_analysis_frames(original_img):
                        frames_to_save.append(intensity_to_uint16(frame))
            
            # Print debug info about frame shapes
            dprint("Frame shapes being saved:")
            for i, frame in enumerate(frames_to_save):
                dprint(f"  Frame {i}: {frame.shape} (dtype: {frame.dtype})")
            
            # Save all frames at once with tifffile.imwrite
            tifffile.imwrite(output_path, frames_to_save, photometric='minisblack',
                        metadata={'axes': 'CYX'}, dtype=np.uint16)
            
            dprint(f"Successfully saved: {output_path}")
            self.update_status(f"Segmentation saved to: {os.path.basename(output_path)}")
            
            # If transfer to FRET was requested, do it now
            if transfer_to_fret and hasattr(self, 'fret_tab'):
                try:
                    self.fret_tab.load_segmentation(output_path)
                    self.update_status(f"Segmentation saved and transferred to FRET tab: {os.path.basename(output_path)}")
                except Exception as e:
                    dprint(f"Error transferring to FRET tab: {str(e)}")
            
            return [output_path]
            
        except Exception as e:
            error_msg = f"Failed to save results: {str(e)}"
            self.update_status(error_msg)
            dprint(error_msg)
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
        """Clear the current image display and related data, returning the view
        to its empty state."""
        self.current_image = None
        self.current_mask = None
        self.current_labels = None
        self.current_image_has_segmentation = False
        # The image is shown on ax1/ax2; clear those (not the unused self.ax) so
        # the last image does not linger once the list is empty.
        for ax_name in ('ax1', 'ax2'):
            ax = getattr(self, ax_name, None)
            if ax is not None:
                ax.clear()
                ax.axis('off')
        if getattr(self, 'canvas', None) is not None:
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

        # If the list is now empty, return the display to its empty state
        # instead of leaving the last selected image on screen (issue #46).
        if self.image_list.count() == 0:
            self.current_image_path = None
            self.clear_image_display()
            if hasattr(self, 'roi_list_widget'):
                self.roi_list_widget.clear()
            if hasattr(self, 'roi_items'):
                self.roi_items = []

        # Update status (removed duplicate status update)
        self.update_status(f"Removed {len(selected_items)} image(s) from the list")
    
    def set_buttons_enabled(self, enabled):
        """Enable/disable control buttons"""
        self.btn_load.setEnabled(enabled)
        self.btn_run.setEnabled(enabled)
        self.btn_batch.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.btn_save_transfer.setEnabled(enabled)
    
    def _next_image_list_item(self):
        """Return the (row, item) to select once the current image is removed.

        Returns (-1, None) for an empty list: the wrap-around modulo divides by
        the item count, which raised ZeroDivisionError when a send-to-channel
        was triggered while the viewer still held the last removed image.
        """
        count = self.image_list.count()
        if count == 0:
            return -1, None
        next_row = (self.image_list.row(self.image_list.currentItem()) + 1) % count
        return next_row, self.image_list.item(next_row)

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
        next_row, next_item = self._next_image_list_item()
        
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
                    
                # Prepare frames: label first, then the raw frames reordered per the
                # channel registry into canonical FRET, Donor, Acceptor order.
                # Use current_labels if available (contains manual edits), otherwise use current_mask
                mask_to_save = self.current_labels if hasattr(self, 'current_labels') and self.current_labels is not None else self.current_mask
                frames_to_save = [intensity_to_uint16(mask_to_save)]  # Label first with manual edits if available
                frames_to_save.extend(
                    intensity_to_uint16(frame) for frame in self._ordered_analysis_frames(img))

                # Save as a multi-frame TIFF with label as first frame
                tifffile.imwrite(output_path, np.stack(frames_to_save, axis=0),
                               photometric='minisblack', metadata={'axes': 'CYX'})
                
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

    def send_to_intensity(self):
        """Save the current segmentation and add it to the Intensity Analysis tab.

        The saved-stack layout follows the current segmentation mode: "Segment
        both" writes [outline, filled, ...raw channels] for membrane-vs-whole-cell
        analysis; otherwise the canonical [label, ...channels] stack is written and
        the Intensity tab can still analyse the whole cell only.
        """
        main_window = self.window()
        intensity_tab = getattr(main_window, 'intensity_tab', None)
        if intensity_tab is None or not hasattr(intensity_tab, 'add_image_paths'):
            self.update_status("Intensity Analysis tab is not available.")
            return
        if not self._segment_both_enabled():
            self.update_status(
                "Tip: enable 'Segment both (membrane + whole-cell)' for membrane analysis. "
                "Saving whole-cell only.")
        saved = self.save_results()
        if not saved:
            return
        intensity_tab.add_image_paths(saved)
        self.update_status(f"Sent to Intensity Analysis tab: {os.path.basename(saved[0])}")

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
        next_row, next_item = self._next_image_list_item()
        
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
                    
                    # Load the original multi-frame image
                    original_img = tifffile.imread(image_path)

                    both_mode = self.parent._segment_both_enabled()
                    if both_mode:
                        # Combined membrane + whole-cell stack for the Intensity tab:
                        # [outline, filled, ...raw channels in input order].
                        prefix = "both_segmented_"
                        frames_to_save = self.parent._both_stack_frames(masks, original_img)
                        expected_frames = len(frames_to_save)
                    else:
                        prefix = "outline_segmented_" if hasattr(self.parent, 'outline_check') and self.parent.outline_check.isChecked() else "whole-cell_segmented_"
                        # Mask first, then the raw frames reordered per the channel
                        # registry into canonical FRET, Donor, Acceptor order.
                        frames_to_save = [masks.astype(np.uint16)]
                        for frame in self.parent._ordered_analysis_frames(original_img):
                            frames_to_save.append(intensity_to_uint16(frame))
                        expected_frames = len(frames_to_save)
                    output_path = os.path.join(output_dir, f"{prefix}{base_name}.tif")

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
                            if num_frames != expected_frames:
                                self.error.emit(f"  Warning: Saved {num_frames} frames, expected {expected_frames}")
                    except Exception as e:
                        self.error.emit(f"  Warning: Could not verify saved file: {str(e)}")

                    if both_mode:
                        # "Both" stacks are not FRET-compatible; route them to the
                        # Intensity Analysis tab when it is available.
                        if self.transfer_to_intensity(output_path):
                            transferred_count += 1
                            self.progress.emit(f"  Sent to Intensity tab: {os.path.basename(output_path)}")
                        else:
                            self.progress.emit(f"  Saved (Intensity tab unavailable): {os.path.basename(output_path)}")
                    else:
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
        
        # Apply outline processing if outline-only mode is enabled. "Segment both"
        # keeps the filled mask here and derives the outline at save time.
        if (hasattr(self.parent, 'outline_check') and self.parent.outline_check.isChecked()
                and not self.parent._segment_both_enabled()):
            return self.parent._labels_to_outline(filtered_masks)

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

    def transfer_to_intensity(self, saved_path):
        """Route a combined membrane+whole-cell stack to the Intensity tab."""
        try:
            main_window = self.parent.window()
            intensity_tab = getattr(main_window, 'intensity_tab', None)
            if intensity_tab is None or not hasattr(intensity_tab, 'add_image_paths'):
                return False
            intensity_tab.add_image_paths([saved_path], group=self.group_name or None)
            return True
        except Exception as e:
            self.error.emit(f"Intensity transfer error: {str(e)}")
            return False

    def stop(self):
        """Stop the batch processing"""
        self.running = False
