"""
Main GUI application for SONLab FRET Analysis
"""

try:
    from GUI.debug import dprint
except (ImportError, ModuleNotFoundError):
    from debug import dprint
import sys
import os
import importlib.util
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QTabWidget, QFrame, QFileDialog, QAction, 
                           QMessageBox, QActionGroup, QCheckBox, QSlider, QWidgetAction, 
                           QLabel, QProgressBar, QColorDialog, QDialog, QPushButton,
                           QTextBrowser, QDialogButtonBox,
                           QComboBox, QAbstractSpinBox)
from PyQt5.QtCore import Qt, QSettings, QTimer, QUrl, QDir, QByteArray, pyqtSignal, QObject, QEvent
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor, QPixmap, QDesktopServices

# Import local modules using relative imports
try:
    from GUI.bt_tab import BleedThroughTab
    from GUI.fret_tab import FretTab
    from GUI.cellpose_segmentation_tab import CellposeSegmentationTab
    from GUI.intensity_tab import IntensityAnalysisTab
    from GUI.config_manager import ConfigManager
    from GUI import theme as theme_system
    from GUI import widgets as widgets_module

except (ImportError, ModuleNotFoundError):
    # Fallback for direct script execution
    from bt_tab import BleedThroughTab
    from fret_tab import FretTab
    from cellpose_segmentation_tab import CellposeSegmentationTab
    from intensity_tab import IntensityAnalysisTab
    from config_manager import ConfigManager
    import theme as theme_system
    import widgets as widgets_module

# Manual segmentation functionality has been merged into CellposeSegmentationTab

# Application metadata
APP_NAME = "SONLab FRET Tool"
APP_VERSION = "v2.1.0-build"
ORGANIZATION_NAME = "SONLab"
ORGANIZATION_DOMAIN = "sonlab-bio.metu.edu.tr"

class WheelEventFilter(QObject):
    """Application-wide filter that prevents the mouse wheel from changing the
    value of combo boxes and spin boxes.

    Scrolling over these controls is a frequent source of accidental edits,
    especially when they sit inside scrollable panels. Instead of consuming the
    wheel event, it is forwarded to the control's parent so the surrounding
    panel still scrolls as expected. Open combo-box pop-up lists are unaffected
    because the pop-up is a separate view, not the QComboBox itself.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox)):
            parent = obj.parentWidget()
            if parent is not None:
                QApplication.sendEvent(parent, event)
            return True
        return super().eventFilter(obj, event)


# Determine if running as a PyInstaller bundle
def is_frozen():
    """Check if running as a PyInstaller bundle"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def resource_path(relative_path):
    """
    Get absolute path to resource, works for dev, installed, and PyInstaller.
    
    Args:
        relative_path (str): Relative path to the resource from the application root
        
    Returns:
        str: Absolute path to the resource
    """
    # Check if running as PyInstaller bundle
    if is_frozen():
        base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    # Check if running in installed mode (--installed flag)
    elif '--installed' in sys.argv:
        base_path = os.path.dirname(os.path.abspath(__file__))
    # Running in development mode
    else:
        base_path = os.path.abspath(os.path.dirname(__file__))
    
    # Handle icon path specifically
    if 'icon.' in relative_path.lower():
        icon_dir = os.path.join(base_path, 'icons')
        icon_path = os.path.join(icon_dir, os.path.basename(relative_path))
        if os.path.exists(icon_path):
            return icon_path
    
    # Handle path normalization for cross-platform compatibility
    path = os.path.join(base_path, relative_path)
    return os.path.normpath(path)


class SONLabGUI(QMainWindow):
    # Signal emitted when theme changes
    theme_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        # Set application information
        QApplication.setApplicationName(APP_NAME)
        QApplication.setApplicationVersion(APP_VERSION)
        QApplication.setOrganizationName(ORGANIZATION_NAME)
        QApplication.setOrganizationDomain(ORGANIZATION_DOMAIN)
        
        # Initialize settings
        self.settings = QSettings(ORGANIZATION_NAME, APP_NAME.replace(" ", ""))
        self.config = ConfigManager()
        
        # Initialize UI
        self.initUI()
        self.load_settings()
        
        # Set window icon
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Show walkthrough on first launch or if enabled
        if self.settings.value("showWalkthrough", True, type=bool):
            QTimer.singleShot(0, self.show_walkthrough)
        # Show about dialog on first launch or if enabled
        elif self.settings.value("showAboutOnStartup", True, type=bool):
            QTimer.singleShot(100, self.show_about_dialog_on_startup)
        
    def initUI(self):
        """Initialize the main window UI components"""
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        
        # Get available screen geometry
        screen = QApplication.primaryScreen().availableGeometry()
        width = min(1400, screen.width() * 0.9)  # 90% of screen width or 1400px, whichever is smaller
        height = min(800, screen.height() * 0.9)  # 90% of screen height or 800px, whichever is smaller
        
        # Calculate centered position
        x = (screen.width() - width) // 2
        y = (screen.height() - height) // 2
        
        # Set window geometry with safe values
        self.setGeometry(int(x), int(y), int(width), int(height))
        
        # Set minimum size to prevent window from becoming too small
        self.setMinimumSize(800, 600)
        
        # Application style will be set by the theme

        # Set window icon
        logo_path = resource_path('GUI/logos/logo.png')
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        
        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 8, 10, 8)

        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main_layout.addWidget(self.tabs)
        
        # Create and add tabs
        self.create_tabs()

        # Create Menu Bar
        self.create_menu_bar()

        # Status bar & progress bar
        self.status = self.statusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status.addPermanentWidget(self.progress_bar)
        
        self.bt_tab.donor_tab.fit_confirmation_signal.connect(self.check_fits_confirmed)
        self.bt_tab.acceptor_tab.fit_confirmation_signal.connect(self.check_fits_confirmed)
        self.bt_tab.s3_tab.fit_confirmation_signal.connect(self.check_fits_confirmed)
        self.bt_tab.s4_tab.fit_confirmation_signal.connect(self.check_fits_confirmed)
        
        # Force update all widgets to apply styles
        QApplication.instance().setStyle(QApplication.instance().style())

    def check_fits_confirmed(self):
        donor_confirmed = self.bt_tab.donor_tab.fit_is_confirmed
        acceptor_confirmed = self.bt_tab.acceptor_tab.fit_is_confirmed
        
        # Always enable the FRET tab
        self.tabs.setTabEnabled(self.fret_tab_index, True)
        
        # Control the run button state based on fits confirmation
        s3_s4_enabled = self.bt_tab.s3_s4_checkbox.isChecked()
        fret_analysis_ready = donor_confirmed and acceptor_confirmed
        if s3_s4_enabled:
            fret_analysis_ready = fret_analysis_ready and self.bt_tab.s3_tab.fit_is_confirmed and self.bt_tab.s4_tab.fit_is_confirmed
            
        if hasattr(self, 'fret_tab') and hasattr(self.fret_tab, 'run_button'):
            self.fret_tab.run_button.setEnabled(fret_analysis_ready)
            self.fret_tab.run_button.setToolTip(
                "Run FRET Analysis" if fret_analysis_ready 
                else "Complete bleedthrough parameter calibration first"
            )

        if fret_analysis_ready:
            donor_model = self.bt_tab.donor_tab.selected_fit_model
            donor_coeffs = self.bt_tab.donor_tab.fit_results[donor_model]
            acceptor_model = self.bt_tab.acceptor_tab.selected_fit_model
            acceptor_coeffs = self.bt_tab.acceptor_tab.fit_results[acceptor_model]
            
            s3_model = self.bt_tab.s3_tab.selected_fit_model if s3_s4_enabled else None
            s3_coeffs = self.bt_tab.s3_tab.fit_results.get(s3_model) if s3_s4_enabled else None
            s4_model = self.bt_tab.s4_tab.selected_fit_model if s3_s4_enabled else None
            s4_coeffs = self.bt_tab.s4_tab.fit_results.get(s4_model) if s3_s4_enabled else None
            
            self.fret_tab.set_correction_parameters(
                donor_model, donor_coeffs,
                acceptor_model, acceptor_coeffs,
                s3_model, s3_coeffs,
                s4_model, s4_coeffs,
                s3_s4_enabled
            )

    def create_tabs(self):
        """Create and add all tabs to the main window"""
        # Create tab instances
        self.bt_tab = BleedThroughTab(self.config, self)
        self.fret_tab = FretTab(self.config, self)
        self.segmentation_tab = CellposeSegmentationTab(self.config, self)
        self.intensity_tab = IntensityAnalysisTab(self.config, self)

        # Add tabs to the tab widget
        self.tabs.addTab(self.segmentation_tab, "Cellpose && Manual Segmentation")
        self.tabs.addTab(self.bt_tab, "Bleed-Through")
        self.tabs.addTab(self.fret_tab, "FRET Analysis")
        self.tabs.addTab(self.intensity_tab, "Intensity / Densitometry")
        
        # Store the index of the FRET tab for enabling/disabling
        self.fret_tab_index = self.tabs.indexOf(self.fret_tab)
        
        # FRET tab is always enabled, but the run button is controlled by BT confirmation

    def create_menu_bar(self):
        menu_bar = self.menuBar()

        # Settings Menu
        settings_menu = menu_bar.addMenu('Settings')

        # Font size adjustment via slider
        font_menu = settings_menu.addMenu('Font Size')
        slider_container = QWidget()
        slider_layout = QHBoxLayout(slider_container)
        slider_layout.setContentsMargins(6, 2, 6, 2)
        slider_label_small = QLabel("A")
        slider_label_small.setMinimumWidth(10)
        slider_label_big = QLabel("A")
        slider_label_big.setStyleSheet("font-size: 18pt;")
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(8, 20)  # sensible font size bounds
        self.font_slider.setTickInterval(1)
        self.font_slider.valueChanged.connect(self.on_font_slider_value_changed)
        slider_layout.addWidget(slider_label_small)
        slider_layout.addWidget(self.font_slider)
        slider_layout.addWidget(slider_label_big)
        slider_action = QWidgetAction(self)
        slider_action.setDefaultWidget(slider_container)
        font_menu.addAction(slider_action)

        reset_action = QAction('Reset to Default', self)
        reset_action.triggered.connect(self.reset_font_size)
        font_menu.addAction(reset_action)

        # Theme selection
        theme_menu = settings_menu.addMenu('Theme')
        light_action = QAction('Light', self, checkable=True)
        light_action.triggered.connect(lambda: self.set_theme('light'))
        theme_menu.addAction(light_action)

        dark_action = QAction('Dark', self, checkable=True)
        dark_action.triggered.connect(lambda: self.set_theme('dark'))
        theme_menu.addAction(dark_action)

        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.addAction(light_action)
        self.theme_action_group.addAction(dark_action)
        self.theme_action_group.setExclusive(True)

        # Help Menu
        help_menu = menu_bar.addMenu('Help')
        
        # Show Walkthrough
        walkthrough_action = QAction('Show Walkthrough', self)
        # Always show when invoked from the menu, regardless of the startup
        # preference. (triggered passes a bool, so wrap in a lambda.)
        walkthrough_action.triggered.connect(lambda: self.show_walkthrough(force=True))
        help_menu.addAction(walkthrough_action)
        help_menu.addSeparator()
        
        # User Guide
        user_guide_action = QAction('Open User Guide', self)
        user_guide_action.triggered.connect(self.open_user_guide)
        help_menu.addAction(user_guide_action)
        help_menu.addSeparator()
        
        # About
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

        # Layout toggle
        compact_layout_action = QAction('Compact Layout', self, checkable=True)
        compact_layout_action.setChecked(self.settings.value('compactLayout', False, type=bool))
        compact_layout_action.triggered.connect(self.toggle_compact_layout)
        settings_menu.addAction(compact_layout_action)

    def _apply_font_to_all_widgets(self, font):
        """Force-apply the font to every existing widget (needed because
        QApplication.setFont only affects newly created widgets)."""
        for widget in QApplication.allWidgets():
            widget.setFont(font)

    def set_application_font_size(self, size):
        """Apply the given font size application-wide and persist it."""
        if size > 0:
            font = QApplication.instance().font()
            font.setPointSize(size)
            QApplication.instance().setFont(font)
            self._apply_font_to_all_widgets(font)
            self.settings.setValue("fontSize", size)
            # keep slider in sync if it exists
            if hasattr(self, "font_slider"):
                self.font_slider.blockSignals(True)
                self.font_slider.setValue(size)
                self.font_slider.blockSignals(False)

    def on_font_slider_value_changed(self, value):
        self.set_application_font_size(value)

    # Kept for backwards compatibility if future shortcuts trigger these
    def increase_font_size(self):
        self.set_application_font_size(QApplication.instance().font().pointSize() + 1)

    def decrease_font_size(self):
        self.set_application_font_size(QApplication.instance().font().pointSize() - 1)

    def reset_font_size(self):
        default_font = QFont()
        self.set_application_font_size(default_font.pointSize())
        self.settings.remove("fontSize")

    def load_settings(self):
        try:
            # Load theme first as it affects the UI
            theme = self.settings.value("theme", "dark")
            self.set_theme(theme)
            
            # Load window state and geometry
            screen_geometry = QApplication.primaryScreen().availableGeometry()
            default_width = min(1400, screen_geometry.width() * 0.9)
            default_height = min(800, screen_geometry.height() * 0.9)
            
            # Restore window geometry if available
            if self.settings.contains("geometry"):
                try:
                    geometry = self.settings.value("geometry")
                    if isinstance(geometry, QByteArray) and not geometry.isEmpty():
                        # Restore the geometry first
                        self.restoreGeometry(geometry)
                        
                        # Get the restored geometry
                        restored_rect = self.frameGeometry()
                        
                        # Check if window is outside the current screen
                        if not screen_geometry.intersects(restored_rect):
                            # If window is completely outside, reset to default position
                            x = (screen_geometry.width() - default_width) // 2
                            y = (screen_geometry.height() - default_height) // 2
                            self.setGeometry(int(x), int(y), int(default_width), int(default_height))
                except Exception as e:
                    dprint(f"Error restoring window geometry: {e}")
                    # Fallback to default geometry
                    x = (screen_geometry.width() - default_width) // 2
                    y = (screen_geometry.height() - default_height) // 2
                    self.setGeometry(int(x), int(y), int(default_width), int(default_height))
            
            # Restore window state if available
            if self.settings.contains("windowState"):
                try:
                    state = self.settings.value("windowState")
                    if isinstance(state, QByteArray) and not state.isEmpty():
                        self.restoreState(state)
                except Exception as e:
                    dprint(f"Error restoring window state: {e}")
            
            # Load font size after theme is set
            font_size = self.settings.value("fontSize", type=int)
            if font_size and 8 <= font_size <= 20:  # Reasonable font size range
                self.set_application_font_size(font_size)
            elif hasattr(self, "font_slider"):
                # Initialize slider with current size if no saved size or invalid
                self.font_slider.setValue(QApplication.instance().font().pointSize())
            
            # Update theme action group if it exists
            if hasattr(self, 'theme_action_group') and self.theme_action_group is not None:
                for action in self.theme_action_group.actions():
                    if action.text().lower() == theme.lower():
                        action.setChecked(True)
                        break
                        
            # Save the initial geometry to config
            self.save_geometry_to_config()
            
        except Exception as e:
            dprint(f"Error loading settings: {e}")
            # Fallback to default settings if there's an error
            self.set_theme("dark")
    
    def save_geometry_to_config(self):
        """Save the current window geometry to the config file."""
        try:
            # Save geometry to config file
            geometry = self.saveGeometry()
            if geometry and not geometry.isEmpty():
                self.config.set('window/geometry', geometry.toHex().data().decode())
                self.config.sync()
        except Exception as e:
            dprint(f"Error saving geometry to config: {e}")
        
    def set_theme(self, theme_name):
        """Apply the light or dark theme across the whole application.

        All visual styling is defined centrally in :mod:`GUI.theme`; this method
        just applies the matching palette, style sheet and matplotlib settings
        and notifies the tabs so they can refresh their canvases.

        Args:
            theme_name (str): ``'light'`` or ``'dark'`` (anything else -> dark).
        """
        app = QApplication.instance()
        theme_name = 'light' if str(theme_name).lower() == 'light' else 'dark'

        # A consistent base style across platforms lets our palette + QSS win.
        app.setStyle("Fusion")
        app.setPalette(theme_system.build_qpalette(theme_name))
        stylesheet = theme_system.build_stylesheet(theme_name)
        # Compact mode (denser layout for small screens) is applied on top so it
        # survives theme switches, not just the Compact Layout toggle.
        if self.settings.value('compactLayout', False, type=bool):
            stylesheet += theme_system.compact_stylesheet()
        app.setStyleSheet(stylesheet)
        theme_system.apply_matplotlib_style(theme_name)

        # Re-tint vector button icons to match the new theme.
        widgets_module.apply_icon_theme(self, theme_name)

        # Let tabs refresh plot colours / canvas backgrounds for the new theme.
        self.theme_changed.emit()
        if hasattr(self, 'apply_tab_styles'):
            self.apply_tab_styles()

        # Keep the Settings > Theme radio buttons in sync (0=Light, 1=Dark).
        if getattr(self, 'theme_action_group', None) is not None:
            index = 0 if theme_name == 'light' else 1
            actions = self.theme_action_group.actions()
            if len(actions) > index:
                actions[index].setChecked(True)

        # Repaint every existing widget so the new style takes effect at once.
        for widget in app.allWidgets():
            widget.update()

        self.settings.setValue("theme", theme_name)

    def show_walkthrough(self, force=False):
        """Show an interactive walkthrough of the application's features.

        ``force=True`` (used by the Help menu) always shows the dialog. The
        automatic startup call leaves ``force=False`` so it respects the
        "Don't show on startup" preference.
        """
        if not force and not self.settings.value("showWalkthrough", True, type=bool):
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Welcome to {APP_NAME}")
        dialog.setMinimumSize(800, 600)
        
        layout = QVBoxLayout()
        
        # Add logo if available
        logo_paths = [
            resource_path('logos/logo.png'),
            resource_path('GUI/logos/logo.png'),
            resource_path('logos/icon_logo_neon_256x256.png')
        ]
        
        logo_label = QLabel()
        logo_found = False
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                try:
                    pixmap = QPixmap(logo_path)
                    if not pixmap.isNull():
                        logo_label.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        logo_label.setAlignment(Qt.AlignCenter)
                        logo_found = True
                        break
                except Exception as e:
                    dprint(f"Error loading logo {logo_path}: {str(e)}")
        
        if not logo_found and hasattr(self, 'windowIcon') and not self.windowIcon().isNull():
            logo_label.setPixmap(self.windowIcon().pixmap(100, 100))
            logo_label.setAlignment(Qt.AlignCenter)
        
        if logo_found or (hasattr(self, 'windowIcon') and not self.windowIcon().isNull()):
            layout.addWidget(logo_label)
        
        # Create tab widget for different sections
        tab_widget = QTabWidget()
        
        # Welcome tab
        welcome_tab = QWidget()
        welcome_layout = QVBoxLayout()
        welcome_text = QTextBrowser()
        welcome_text.setOpenExternalLinks(True)
        welcome_text.setHtml(f"""
        <h1>Welcome to {APP_NAME} {APP_VERSION}</h1>
        <p>Thank you for using our FRET analysis tool. This application is designed to help you analyze 
        Fluorescence Resonance Energy Transfer (FRET) microscopy images with ease and precision.</p>
        
        <h2>Key Features:</h2>
        <ul>
            <li><b>Cellpose Segmentation:</b> Advanced AI-powered cell segmentation for accurate ROI detection</li>
            <li><b>Manual Segmentation:</b> Draw and edit regions of interest with precision</li>
            <li><b>Bleed-Through Correction:</b> Compensate for spectral overlap between channels</li>
            <li><b>FRET Analysis:</b> Calculate FRET efficiency and other key metrics</li>
            <li><b>Batch Processing:</b> Process multiple images in one go</li>
        </ul>
        
        <p>Use the tabs below to learn more about each feature, or click 'OK' to begin.</p>
        """)
        welcome_layout.addWidget(welcome_text)
        welcome_tab.setLayout(welcome_layout)
        
        # Cellpose Segmentation tab
        cellpose_tab = QWidget()
        cellpose_layout = QVBoxLayout()
        cellpose_text = QTextBrowser()
        cellpose_text.setOpenExternalLinks(True)
        cellpose_text.setHtml("""
        <h1>Cellpose &amp; Manual Segmentation</h1>
        <p>The Cellpose integration provides state-of-the-art cell segmentation using deep learning,
        with manual polygon editing for refinement.</p>

        <h2>How to use:</h2>
        <ol>
            <li>Click 'Load Images' (or drag &amp; drop TIFF/CZI files) to add your images</li>
            <li>Adjust the Cellpose parameters (Model, Cell Diameter, Flow Threshold, Min Cell Size)</li>
            <li>Click 'Run Segmentation' to process the selected image</li>
            <li>Refine the result with the ROI Manager: 'Add ROI' to draw a cell, 'Delete ROI' to remove one</li>
            <li>Use 'Save Results', 'Send to FRET Tab', 'Send to Donor/Acceptor', or 'Batch Segment &amp; Transfer'</li>
        </ol>

        <h2>Tips:</h2>
        <ul>
            <li>'Cell Diameter' is the most impactful parameter &mdash; set it to 0 for automatic detection</li>
            <li>Lower the 'Flow Threshold' if cells are merged; increase 'Cell Diameter' if cells are split</li>
            <li>Raise 'Min Cell Size' to remove debris and small artifacts</li>
        </ul>
        """)
        cellpose_layout.addWidget(cellpose_text)
        cellpose_tab.setLayout(cellpose_layout)
        
        # FRET Analysis tab
        fret_tab = QWidget()
        fret_layout = QVBoxLayout()
        fret_text = QTextBrowser()
        fret_text.setOpenExternalLinks(True)
        fret_text.setHtml("""
        <h1>FRET Analysis</h1>
        <p>Compute pixel-wise FRET efficiency on your segmented, bleed-through-corrected cells.</p>

        <h2>Workflow:</h2>
        <ol>
            <li>Add segmented images (from the Segmentation tab or from disk)</li>
            <li>Confirm the bleed-through coefficients carried over from the Bleed-Through tab</li>
            <li>Choose one or more FRET formulas and set the display thresholds</li>
            <li>Assign images to groups for comparison, then click 'Run FRET Analysis'</li>
            <li>Review the maps, statistics, and plots, and export your results</li>
        </ol>

        <h2>What you get:</h2>
        <ul>
            <li>Color-coded FRET efficiency maps for each formula</li>
            <li>Per-cell and aggregate statistics (non-zero and thresholded averages)</li>
            <li>Histograms and box plots with group comparisons and significance testing</li>
            <li>Export to TIFF, CSV, and publication-ready figures</li>
        </ul>
        """)
        fret_layout.addWidget(fret_text)
        fret_tab.setLayout(fret_layout)

        # Bleed-Through tab
        bt_tab = QWidget()
        bt_layout = QVBoxLayout()
        bt_text = QTextBrowser()
        bt_text.setOpenExternalLinks(True)
        bt_text.setHtml("""
        <h1>Bleed-Through Correction</h1>
        <p>Measure and correct the spectral cross-talk that leaks from the donor and acceptor
        fluorophores into the FRET channel, using single-label control images.</p>

        <h2>How to use:</h2>
        <ol>
            <li>Select a channel sub-tab: Donor (S1) or Acceptor (S2) &mdash; enable S3/S4 for 4-frame data</li>
            <li>Add the matching control images: donor-only for S1/S3, acceptor-only for S2/S4</li>
            <li>Set the processing options (Gaussian Blur Sigma, optional Random Sampling) and click 'Run Analysis'</li>
            <li>Pick a fitting model (Constant, Linear, or Exponential) and click 'Confirm Fit'</li>
            <li>Click 'Save Parameters' to store the coefficients for the FRET analysis</li>
        </ol>

        <h2>Tips:</h2>
        <ul>
            <li>Send control images here directly from the Segmentation tab ('Send to Donor/Acceptor')</li>
            <li>Use the threshold controls to exclude saturated or low-signal pixels before fitting</li>
            <li>Saved parameters are also copied next to your input images for easy reuse</li>
        </ul>
        """)
        bt_layout.addWidget(bt_text)
        bt_tab.setLayout(bt_layout)

        # Add tabs (in pipeline order)
        tab_widget.addTab(welcome_tab, "Welcome")
        tab_widget.addTab(cellpose_tab, "Segmentation")
        tab_widget.addTab(bt_tab, "Bleed-Through")
        tab_widget.addTab(fret_tab, "FRET Analysis")
        
        layout.addWidget(tab_widget)
        
        # Add "Don't show again" checkbox
        dont_show = QCheckBox("Don't show this walkthrough on startup")
        dont_show.setChecked(False)
        
        # Add buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        
        layout.addWidget(dont_show)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        # Show the dialog
        dialog.exec_()
        
        # Save the preference
        if dont_show.isChecked():
            self.settings.setValue("showWalkthrough", False)
    
    def show_about_dialog_on_startup(self):
        # First show the walkthrough
        self.show_walkthrough()
        
        # Then show the about dialog if needed
        if self.settings.value("showAboutOnStartup", True, type=bool):
            about_box = QMessageBox(self)
            about_box.setWindowTitle(f"About {APP_NAME}")
            
            # Try multiple possible logo locations
            logo_paths = [
                resource_path('logos/logo.png'),  # Direct path in the root
                resource_path('GUI/logos/logo.png'),  # Path in GUI directory
                resource_path('logos/icon_logo_neon_256x256.png')  # Alternative logo
            ]
            
            logo_found = False
            for logo_path in logo_paths:
                if os.path.exists(logo_path):
                    try:
                        pixmap = QPixmap(logo_path)
                        if not pixmap.isNull():
                            about_box.setIconPixmap(pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                            logo_found = True
                            break
                    except Exception as e:
                        dprint(f"Error loading logo {logo_path}: {str(e)}")
            
            # If no logo found, use the application icon
            if not logo_found and hasattr(self, 'windowIcon') and not self.windowIcon().isNull():
                about_box.setIconPixmap(self.windowIcon().pixmap(128, 128))

            about_text = f"""
            <h3>{APP_NAME}</h3>
            <p>Version: {APP_VERSION}</p>
            <p>This application is designed for analyzing FRET microscopy images.</p>
            <p>Developed by the {ORGANIZATION_NAME} team.</p>
            <p>&copy; 2025 {ORGANIZATION_NAME}. All rights reserved.</p>
            """
            about_box.setText(about_text)

            # Add "Don't show again" checkbox
            check_box = QCheckBox("Don't show this message on startup")
            about_box.setCheckBox(check_box)

            about_box.setStandardButtons(QMessageBox.Ok)
            about_box.exec_()

            # Save the preference
            if check_box.isChecked():
                self.settings.setValue("showAboutOnStartup", False)

    # ---------------- Progress Bar API -----------------
    def start_progress(self, maximum: int):
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status.showMessage("Working…")

    def set_progress(self, value: int, message: str = None):
        self.progress_bar.setValue(value)
        if message:
            self.status.showMessage(message)

    def finish_progress(self):
        self.progress_bar.setVisible(False)
        self.status.showMessage("Done", 3000)

    # ---------------- Layout Toggle -----------------
    def toggle_compact_layout(self, compact: bool):
        """Toggle a denser layout for small screens.

        The compact style sheet is (re)applied inside :meth:`set_theme` based on
        this saved setting, so it stays in effect across theme switches.
        """
        self.settings.setValue('compactLayout', compact)
        self.set_theme(self.settings.value('theme', 'dark'))


    def open_user_guide(self):
        # The guide lives in user_guide/ at the project root. Check the layouts
        # used across dev, installed, and PyInstaller-bundled runs.
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            resource_path('user_guide/user_guide.pdf'),
            resource_path('GUI/user_guide/user_guide.pdf'),
            os.path.join(project_root, 'user_guide', 'user_guide.pdf'),
        ]
        pdf_path = next((p for p in candidates if os.path.exists(p)), None)
        if not pdf_path:
            QMessageBox.warning(self, "User Guide", "Could not find user_guide.pdf.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(pdf_path))

    def show_about_dialog(self):
        # This version is for the menu, without the checkbox
        about_box = QMessageBox(self)
        about_box.setWindowTitle(f"About {APP_NAME}")
        
        # Try multiple possible logo locations
        logo_paths = [
            resource_path('logos/logo.png'),  # Direct path in the root
            resource_path('GUI/logos/logo.png'),  # Path in GUI directory
            resource_path('logos/icon_logo_neon_256x256.png')  # Alternative logo
        ]
        
        logo_found = False
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                try:
                    pixmap = QPixmap(logo_path)
                    if not pixmap.isNull():
                        about_box.setIconPixmap(pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        logo_found = True
                        break
                except Exception as e:
                    dprint(f"Error loading logo {logo_path}: {str(e)}")
        
        # If no logo found, use the application icon
        if not logo_found and hasattr(self, 'windowIcon') and not self.windowIcon().isNull():
            about_box.setIconPixmap(self.windowIcon().pixmap(128, 128))

        about_text = f"""
        <h3>{APP_NAME}</h3>
        <p>Version: {APP_VERSION}</p>
        <p>This application is designed for analyzing FRET microscopy images.</p>
        <p>Developed by the {ORGANIZATION_NAME} team.</p>
        <p>&copy; 2025 {ORGANIZATION_NAME}. All rights reserved.</p>
        """
        about_box.setText(about_text)
        about_box.setStandardButtons(QMessageBox.Ok)
        about_box.exec_()

    def closeEvent(self, event):
        try:
            # Save window geometry and state
            try:
                # Save geometry to both QSettings and config file
                if not (self.isMaximized() or self.isMinimized() or self.isFullScreen()):
                    geometry = self.saveGeometry()
                    if not geometry.isEmpty():
                        self.settings.setValue("geometry", geometry)
                        # Also save to config file
                        self.config.set('window/geometry', geometry.toHex().data().decode())
                
                # Save window state
                state = self.saveState()
                if not state.isEmpty():
                    self.settings.setValue("windowState", state)
                
                # Save current theme
                current_theme = self.settings.value("theme", "dark")
                self.settings.setValue("theme", current_theme)
                self.config.set('window/theme', current_theme)
                
                # Save current font size if slider exists
                if hasattr(self, 'font_slider'):
                    font_size = self.font_slider.value()
                    self.settings.setValue("fontSize", font_size)
                    self.config.set('window/font_size', font_size)
                
                # Sync all settings
                self.settings.sync()
                self.config.sync()
                
            except Exception as e:
                dprint(f"Error saving window state: {e}")
                
        finally:
            # Always call the parent's closeEvent
            super().closeEvent(event)


def main():
    """Main entry point for the application"""
    import sys
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QMetaType
    from PyQt5.QtCore import QItemSelection
    
    # Register QItemSelection metatype to avoid warnings
    QMetaType.typeName(QMetaType.type('QItemSelection'))  # This will register the type if not already registered
    
    # Set up high DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Create application instance
    app = QApplication(sys.argv)

    # Make combo boxes and spin boxes ignore the mouse wheel app-wide
    # (parented to the app so it lives for the whole session).
    app.installEventFilter(WheelEventFilter(app))

    # Set application metadata
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setOrganizationDomain(ORGANIZATION_DOMAIN)
    
    # Create and show main window
    ex = SONLabGUI()
    ex.show()
    
    # Start application event loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    # This block runs when the script is executed directly
    import os
    import sys
    
    # Add the parent directory to Python path
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Define constants
    APP_NAME = "SONLab FRET Tool"
    APP_VERSION = "v2.1.0-build"
    ORGANIZATION_NAME = "SONLab"
    ORGANIZATION_DOMAIN = "sonlab-bio.metu.edu.tr"
    
    # Run the application
    try:
        main()
    except Exception as e:
        dprint(f"Error running application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

