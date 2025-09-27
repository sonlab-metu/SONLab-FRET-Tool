"""
Main GUI application for SONLab FRET Analysis
"""

import sys
import os
import importlib.util
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QTabWidget, QFrame, QFileDialog, QAction, 
                           QMessageBox, QActionGroup, QCheckBox, QSlider, QWidgetAction, 
                           QLabel, QProgressBar, QColorDialog, QDialog, QPushButton, 
                           QWizard, QWizardPage, QTextBrowser, QDialogButtonBox)
from PyQt5.QtCore import Qt, QSettings, QTimer, QUrl, QDir, QByteArray, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor, QPixmap, QDesktopServices

# Import local modules using relative imports
try:
    from GUI.bt_tab import BleedThroughTab
    from GUI.fret_tab import FretTab
    from GUI.cellpose_segmentation_tab import CellposeSegmentationTab
    from GUI.config_manager import ConfigManager

except ImportError or ModuleNotFoundError:
    # Fallback for direct script execution
    from bt_tab import BleedThroughTab
    from fret_tab import FretTab
    from cellpose_segmentation_tab import CellposeSegmentationTab
    from config_manager import ConfigManager

# Manual segmentation functionality has been merged into CellposeSegmentationTab

# Application metadata
APP_NAME = "SONLab FRET Tool"
APP_VERSION = "v2.0.2"
ORGANIZATION_NAME = "SONLab"
ORGANIZATION_DOMAIN = "sonlab-bio.metu.edu.tr"

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
        
        # Create tab widget
        self.tabs = QTabWidget()
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
        
        # Force update all widgets to apply styles
        QApplication.instance().setStyle(QApplication.instance().style())

    def check_fits_confirmed(self):
        donor_confirmed = self.bt_tab.donor_tab.fit_is_confirmed
        acceptor_confirmed = self.bt_tab.acceptor_tab.fit_is_confirmed
        
        # Always enable the FRET tab
        self.tabs.setTabEnabled(self.fret_tab_index, True)
        
        # Control the run button state based on fits confirmation
        fret_analysis_ready = donor_confirmed and acceptor_confirmed
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
            
            self.fret_tab.set_correction_parameters(
                donor_model, donor_coeffs,
                acceptor_model, acceptor_coeffs
            )

    def create_tabs(self):
        """Create and add all tabs to the main window"""
        # Create tab instances
        self.bt_tab = BleedThroughTab(self.config, self)
        self.fret_tab = FretTab(self.config, self)
        self.segmentation_tab = CellposeSegmentationTab(self.config, self)
        
        # Add tabs to the tab widget
        self.tabs.addTab(self.segmentation_tab, "Cellpose && Manual Segmentation")
        self.tabs.addTab(self.bt_tab, "Bleed-Through")
        self.tabs.addTab(self.fret_tab, "FRET Analysis")
        
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
        walkthrough_action.triggered.connect(self.show_walkthrough)
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

        # Theme editor
        edit_dark_action = QAction('Edit Dark Theme...', self)
        edit_dark_action.triggered.connect(self.open_theme_editor)
        theme_menu.addAction(edit_dark_action)

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
                    print(f"Error restoring window geometry: {e}")
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
                    print(f"Error restoring window state: {e}")
            
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
            print(f"Error loading settings: {e}")
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
            print(f"Error saving geometry to config: {e}")
        
    def set_theme(self, theme_name):
        """
        Set the application theme
        
        Args:
            theme_name (str): Name of the theme to apply ('light', 'dark', or 'system')
        """
        # Always use Fusion style for consistent palette cross-platform
        app = QApplication.instance()
        app.setStyle("Fusion")
    
        # Apply custom dark overrides if present
        custom = self.settings.value('customDarkPalette', {}) if isinstance(self.settings.value('customDarkPalette', {}), dict) else {}
        
        if theme_name == 'dark':
            # Configure matplotlib for dark theme
            try:
                import matplotlib as mpl
                import matplotlib.pyplot as plt
                mpl.rcParams.update({
                    'figure.facecolor': '#2b2b2b',
                    'axes.facecolor': '#2b2b2b',
                    'savefig.facecolor': '#2b2b2b',
                    'text.color': '#f0f0f0',
                    'axes.labelcolor': '#f0f0f0',
                    'xtick.color': '#f0f0f0',
                    'ytick.color': '#f0f0f0',
                    'axes.edgecolor': '#6d6d6d',
                    'axes.grid': True,
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
            except ImportError:
                pass

            # Create dark palette
            dark_palette = QPalette()
            dark_color = QColor(45, 45, 45)
            disabled_color = QColor(100, 100, 100)
            text_color = QColor(240, 240, 240)
            highlight_color = QColor(42, 130, 218)
            
            # Set palette colors
            dark_palette.setColor(QPalette.Window, dark_color)
            dark_palette.setColor(QPalette.WindowText, text_color)
            dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
            dark_palette.setColor(QPalette.AlternateBase, dark_color)
            dark_palette.setColor(QPalette.ToolTipBase, text_color)
            dark_palette.setColor(QPalette.ToolTipText, text_color)
            dark_palette.setColor(QPalette.Text, text_color)
            dark_palette.setColor(QPalette.Disabled, QPalette.Text, disabled_color)
            dark_palette.setColor(QPalette.Button, dark_color.darker(120))
            dark_palette.setColor(QPalette.ButtonText, text_color)
            dark_palette.setColor(QPalette.BrightText, Qt.red)
            dark_palette.setColor(QPalette.Link, highlight_color)
            dark_palette.setColor(QPalette.Highlight, highlight_color)
            dark_palette.setColor(QPalette.HighlightedText, Qt.white)
            dark_palette.setColor(QPalette.LinkVisited, highlight_color.darker(150))
            
            # Apply palette to the application
            app.setPalette(dark_palette)
            
            # Force style refresh
            app.setStyleSheet(app.styleSheet())
            
            # Notify all tabs about the theme change
            self.theme_changed.emit()
            
            # Apply tab styles to all tab widgets
            if hasattr(self, 'apply_tab_styles'):
                self.apply_tab_styles()
            
            # Force update all widgets
            for widget in app.allWidgets():
                widget.update()
            
            # Apply stylesheet for additional theming
            dark_stylesheet = """
                /* Base widget styling */
                QWidget {
                    color: #f0f0f0;
                    background-color: #2b2b2b;
                    selection-background-color: #3a7abf;
                    selection-color: white;
                }
                
                /* Main window and header */
                QMainWindow {
                    background-color: #2b2b2b;
                }
                
                /* Menu bar */
                QMenuBar {
                    background-color: #2b2b2b;
                    color: #f0f0f0;
                    border-bottom: 1px solid #3a3a3a;
                    padding: 2px;
                }
                
                QMenuBar::item {
                    background: transparent;
                    padding: 4px 8px;
                    margin: 2px 1px;
                    border-radius: 3px;
                }
                
                QMenuBar::item:selected {
                    background: #3a3a3a;
                }
                
                QMenuBar::item:pressed {
                    background: #4a4a4a;
                }
                
                /* ===== GLOBAL TAB STYLING ===== */
                /* Apply to all tab widgets and tab bars */
                QTabBar {
                    background: #2b2b2b;
                    border: none;
                    spacing: 2px;
                }
                
                QTabBar::tab {
                    background: #353535;
                    color: #f0f0f0;
                    border: 1px solid #3a3a3a;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    padding: 8px 12px;
                    margin: 0 2px 0 0;
                    min-width: 80px;
                }
                
                QTabBar::tab:selected {
                    background: #2b2b2b;
                    border-bottom: 1px solid #2b2b2b;
                }
                
                QTabBar::tab:!selected {
                    margin-top: 2px;
                    background: #2a2a2a;
                }
                
                QTabBar::tab:hover:!selected {
                    background: #3a3a3a;
                }
                
                /* Tab widget container */
                QTabWidget::pane {
                    border: 1px solid #3a3a3a;
                    top: -1px;
                    background: #2b2b2b;
                    position: absolute;
                    border-radius: 4px;
                }
                
                /* Main tab bar */
                QTabBar {
                    background: #2b2b2b;
                    border: none;
                    spacing: 2px;
                    qproperty-drawBase: 0;
                }
                
                /* All tabs (both main and nested) */
                QTabBar::tab {
                    background: #353535;
                    color: #f0f0f0;
                    border: 1px solid #3a3a3a;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    padding: 8px 12px;
                    margin: 0 2px 0 0;
                    min-width: 80px;
                }
                
                /* Selected tab */
                QTabBar::tab:selected {
                    background: #2b2b2b;
                    border-bottom: 1px solid #2b2b2b;
                    margin-bottom: 0;
                }
                
                /* Unselected tab */
                QTabBar::tab:!selected {
                    margin-top: 2px;
                    background: #2a2a2a;
                    border-bottom: 1px solid #3a3a3a;
                }
                
                /* Hover state */
                QTabBar::tab:hover:!selected {
                    background: #3a3a3a;
                }
                
                /* Tab close button */
                QTabBar::close-button {
                    background: transparent;
                    padding: 0px 2px;
                    image: url(close.png);
                }
                
                QTabBar::close-button:hover {
                    background: #4a4a4a;
                }
                
                /* Tab scroll buttons */
                QTabBar QToolButton {
                    background: #353535;
                    border: 1px solid #3a3a3a;
                    margin: 0;
                    padding: 4px;
                }
                
                QTabBar QToolButton::left-arrow, 
                QTabBar QToolButton::right-arrow {
                    width: 16px;
                    height: 16px;
                    image: none;
                }
                
                /* Nested tab widgets */
                QTabWidget QTabWidget::pane {
                    border: 1px solid #3a3a3a;
                    top: 1px;
                }
                
                QTabWidget QTabBar::tab {
                    padding: 4px 8px;
                    min-width: 60px;
                    font-size: 0.9em;
                }
            
            /* Navigation toolbar */
            QToolBar {
                background: #2b2b2b;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                spacing: 2px;
                padding: 2px;
            }
            
            QToolBar QToolButton {
                background: #3a3a3a;
                border: 1px solid #4a4a4a;
                border-radius: 3px;
                padding: 3px;
                margin: 1px;
            }
            
            QToolBar QToolButton:hover {
                background: #4a4a4a;
                border: 1px solid #5a5a5a;
            }
            
            QToolBar QToolButton:pressed {
                background: #2a2a2a;
            }
            
            /* Standard widgets */
            QLineEdit, 
            QTextEdit, 
            QPlainTextEdit, 
            QSpinBox, 
            QDoubleSpinBox, 
            QComboBox, 
            QListWidget, 
            QTreeWidget, 
            QTableWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                padding: 3px;
                border-radius: 3px;
            }
            
            QPushButton, 
            QToolButton {
                background-color: #3a3a3a;
                color: #e0e0e0;
                border: 1px solid #4a4a4a;
                padding: 5px;
                border-radius: 3px;
            }
            
            QPushButton:hover, 
            QToolButton:hover {
                background-color: #4a4a4a;
                border: 1px solid #5a5a5a;
            }
            
            QPushButton:pressed, 
            QToolButton:pressed {
                background-color: #2a2a2a;
            }
            
            /* Headers and tooltips */
            QHeaderView::section {
                background-color: #353535;
                color: #f0f0f0;
                padding: 4px;
                border: 1px solid #3a3a3a;
            }
            
            QToolTip {
                color: #f0f0f0;
                background-color: #353535;
                border: 1px solid #3a3a3a;
            }
            
            /* Menu styling */
            QMenu {
                background-color: #2b2b2b;
                color: #f0f0e0;
                border: 1px solid #3a3a3a;
            }
            
            QMenu::item:selected {
                background-color: #3a7abf;
                color: white;
            }
            
            QMenu::item {
                padding: 4px 25px 4px 20px;
            }
            
            QMenu::separator {
                height: 1px;
                background: #3a3a3a;
                margin: 4px 0px;
            }
                
                /* Selected tab */
                QTabBar::tab:selected, QTabBar::tab:selected:active {
                    background: #2b2b2b !important;
                    border-bottom: 1px solid #2b2b2b !important;
                    margin-bottom: -1px !important;
                }
                
                /* Unselected tab */
                QTabBar::tab:!selected {
                    margin-top: 2px !important;
                    background: #2a2a2a !important;
                    border-bottom: 1px solid #3a3a3a !important;
                }
                
                /* Hover state */
                QTabBar::tab:hover:!selected {
                    background: #3a3a3a !important;
                }
                
                /* Tab close button */
                QTabBar::close-button {
                    background: transparent !important;
                    padding: 0px 2px !important;
                }
                
                QTabBar::close-button:hover {
                    background: #4a4a4a !important;
                }
                
                /* Tab scroll buttons */
                QTabBar QToolButton {
                    background: #353535 !important;
                    border: 1px solid #3a3a3a !important;
                    margin: 0 !important;
                    padding: 0 !important;
                }
                
                QTabBar QToolButton::left-arrow, 
                QTabBar QToolButton::right-arrow {
                    width: 16px !important;
                    height: 16px !important;
                    image: none !important; /* Remove default arrow images */
                }
                
                /* Tab bar corner widget */
                QTabWidget::tab-bar {
                    left: 0; /* Move the tabs to the far left */
                }
                
                /* Ensure tab bar text is visible */
                QTabBar QLabel, 
                QTabBar::tab {
                    color: #f0f0f0 !important;
                    background: transparent !important;
                }
                
                /* Fix for tab bar in dock widgets */
                QDockWidget QTabBar::tab {
                    margin-bottom: 0px !important;
                    padding: 4px 8px !important;
                }
                
                /* Special case for tab bars in tab widgets */
                QTabWidget QTabBar::tab {
                    margin-bottom: -1px !important;
                }
                
                /* Matplotlib figure styling */
                FigureCanvas, MplWidget {
                    background-color: #1e1e1e;
                    border: 1px solid #3a3a3a;
                    border-radius: 4px;
                }
                
                /* Standard widgets (duplicate removed) */
                QLineEdit, 
                QTextEdit, 
                QPlainTextEdit, 
                QSpinBox, 
                QDoubleSpinBox, 
                QComboBox, 
                QListWidget, 
                QTreeWidget, 
                QTableWidget {
                    background-color: #1e1e1e;
                    color: #e0e0e0;
                    border: 1px solid #3a3a3a;
                    padding: 3px;
                    border-radius: 3px;
                }
                
                QPushButton, 
                QToolButton {
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                    border: 1px solid #4a4a4a;
                    padding: 5px;
                    border-radius: 3px;
                }
                
                QPushButton:hover, 
                QToolButton:hover {
                    background-color: #4a4a4a;
                    border: 1px solid #5a5a5a;
                }
                
                QPushButton:pressed, 
                QToolButton:pressed {
                    background-color: #2a2a2a;
                }
                
                /* Headers and tooltips */
                QHeaderView::section {
                    background-color: #353535;
                    color: #f0f0f0;
                    padding: 4px;
                    border: 1px solid #3a3a3a;
                }
                
                QToolTip {
                    color: #f0f0f0;
                    background-color: #353535;
                    border: 1px solid #3a3a3a;
                }
                
                /* Menu styling */
                QMenu {
                    background-color: #2b2b2b;
                    color: #f0f0f0;
                    border: 1px solid #3a3a3a;
                }
                
                QMenu::item:selected {
                    background-color: #3a7abf;
                }
                
                /* Scrollbars */
                QScrollBar:vertical, 
                QScrollBar:horizontal {
                    border: 1px solid #3a3a3a;
                    background: #2b2b2b;
                    width: 12px;
                    margin: 0px;
                }
                
                QScrollBar::handle:vertical, 
                QScrollBar::handle:horizontal {
                    background: #4a4a4a;
                    min-height: 20px;
                    min-width: 20px;
                    border-radius: 3px;
                }
                
                QScrollBar::handle:vertical:hover, 
                QScrollBar::handle:horizontal:hover {
                    background: #5a5a5a;
                }
                
                QScrollBar::add-line:vertical, 
                QScrollBar::sub-line:vertical,
                QScrollBar::add-line:horizontal, 
                QScrollBar::sub-line:horizontal {
                    height: 0px;
                    width: 0px;
                }
            """
            try:
                app.setStyleSheet(dark_stylesheet)
            except Exception as e:
                print(f"Error setting dark stylesheet: {str(e)}")
                app.setStyleSheet("")  # Fallback to default stylesheet
            if hasattr(self, 'theme_action_group') and self.theme_action_group is not None:
                self.theme_action_group.actions()[1].setChecked(True)
        else:
            # Reset to default light theme
            app.setPalette(app.style().standardPalette())
            
            # Force style refresh
            app.setStyleSheet("")
            
            # Update theme action group
            if hasattr(self, 'theme_action_group') and self.theme_action_group is not None:
                self.theme_action_group.actions()[0].setChecked(True)
                
            # Force update all widgets
            for widget in app.allWidgets():
                widget.update()
                
            # Notify all tabs about the theme change
            self.theme_changed.emit()
        
        # Force update all widgets
        for widget in app.allWidgets():
            widget.update()
        
        self.settings.setValue("theme", theme_name)

    def show_walkthrough(self):
        """Show an interactive walkthrough of the application's features."""
        # Check if we should show the walkthrough
        if not self.settings.value("showWalkthrough", True, type=bool):
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
                    print(f"Error loading logo {logo_path}: {str(e)}")
        
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
        
        <p>Use the tabs below to learn more about each feature, or click 'Start Using' to begin.</p>
        """)
        welcome_layout.addWidget(welcome_text)
        welcome_tab.setLayout(welcome_layout)
        
        # Cellpose Segmentation tab
        cellpose_tab = QWidget()
        cellpose_layout = QVBoxLayout()
        cellpose_text = QTextBrowser()
        cellpose_text.setOpenExternalLinks(True)
        cellpose_text.setHtml("""
        <h1>Cellpose Segmentation</h1>
        <p>The Cellpose integration provides state-of-the-art cell segmentation using deep learning.</p>
        
        <h2>How to use:</h2>
        <ol>
            <li>Load your image using the 'Open Image' button</li>
            <li>Adjust the segmentation parameters as needed</li>
            <li>Click 'Run Segmentation' to process the image</li>
            <li>Review and refine the segmentation if necessary</li>
            <li>Save or export your results</li>
        </ol>
        
        <h2>Tips:</h2>
        <ul>
            <li>Use the 'Preview' button to test parameters on a small region</li>
            <li>Adjust the 'Cell Diameter' parameter for best results</li>
            <li>Use the 'Flow Threshold' to control segmentation sensitivity</li>
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
        <p>Perform Fluorescence Resonance Energy Transfer (FRET) analysis on your segmented cells.</p>
        
        <h2>Workflow:</h2>
        <ol>
            <li>Complete the segmentation in the Cellpose tab</li>
            <li>Define your FRET channels in the settings</li>
            <li>Run the FRET analysis</li>
            <li>Review the results and export as needed</li>
        </ol>
        
        <h2>Key Metrics:</h2>
        <ul>
            <li>FRET Efficiency</li>
            <li>Donor and Acceptor intensities</li>
            <li>Correlation analysis</li>
            <li>Time-lapse analysis (if applicable)</li>
        </ul>
        """)
        fret_layout.addWidget(fret_text)
        fret_tab.setLayout(fret_layout)
        
        # Add tabs
        tab_widget.addTab(welcome_tab, "Welcome")
        tab_widget.addTab(cellpose_tab, "Cellpose Segmentation")
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
                        print(f"Error loading logo {logo_path}: {str(e)}")
            
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
        if compact:
            QApplication.instance().setStyleSheet("* { padding: 2px; margin: 2px; }")
        else:
            QApplication.instance().setStyleSheet("")
        self.settings.setValue('compactLayout', compact)

    # ---------------- Theme Editor -----------------
    def open_theme_editor(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Dark Theme Editor')
        vbox = QVBoxLayout(dlg)
        pick_bg_btn = QPushButton('Pick Window Color')
        pick_text_btn = QPushButton('Pick Text Color')
        pick_highlight_btn = QPushButton('Pick Highlight Color')
        preview_label = QLabel('Preview')
        vbox.addWidget(pick_bg_btn)
        vbox.addWidget(pick_text_btn)
        vbox.addWidget(pick_highlight_btn)
        vbox.addWidget(preview_label)
        chosen = {}
        def pick_color(key):
            col = QColorDialog.getColor(parent=dlg)
            if col.isValid():
                chosen[key] = col.name()
                preview_label.setStyleSheet(f"background-color: {chosen.get('bg', '#333')}; color: {chosen.get('text', '#fff')};")
        pick_bg_btn.clicked.connect(lambda: pick_color('bg'))
        pick_text_btn.clicked.connect(lambda: pick_color('text'))
        pick_highlight_btn.clicked.connect(lambda: pick_color('hl'))
        ok_btn = QPushButton('Save')
        vbox.addWidget(ok_btn)
        ok_btn.clicked.connect(dlg.accept)
        if dlg.exec_() == QDialog.Accepted and chosen:
            self.settings.setValue('customDarkPalette', chosen)
            self.set_theme('dark')

    # ---------------- Walk-through Wizard -----------------
    def show_wizard(self):
        wiz = QWizard(self)
        wiz.setWindowTitle('SONLab FRET Analysis Walk-through')
        def add_page(title, text):
            page = QWizardPage()
            page.setTitle(title)
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            layout = QVBoxLayout(page)
            layout.addWidget(lbl)
            return page
        wiz.addPage(add_page('Welcome', 'This wizard briefly introduces the main tabs.'))
        wiz.addPage(add_page('Manual Segmentation', 'Use this tab to manually segment images.'))
        wiz.addPage(add_page('Automated Segmentation', 'Run automated segmentation algorithms here.'))
        wiz.addPage(add_page('Bleed-Through', 'Fit bleed-through curves for donor/acceptor.'))
        wiz.addPage(add_page('FRET Calculation', 'Calculate corrected FRET efficiency.'))
        wiz.exec_()
        self.settings.setValue('wizardShown', True)

    def open_user_guide(self):
        pdf_path = resource_path('GUI/user_guide/user_guide.pdf')
        if not os.path.exists(pdf_path):
            QMessageBox.warning(self, "User Guide", f"Could not find user_guide.pdf at {pdf_path}.")
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
                    print(f"Error loading logo {logo_path}: {str(e)}")
        
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
                print(f"Error saving window state: {e}")
                
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
    APP_VERSION = "v2.0.2"
    ORGANIZATION_NAME = "SONLab"
    ORGANIZATION_DOMAIN = "sonlab-bio.metu.edu.tr"
    
    # Run the application
    try:
        main()
    except Exception as e:
        print(f"Error running application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

