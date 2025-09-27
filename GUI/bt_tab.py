"""
Bleed-through calculation tab for the SONLab FRET Analysis Tool
"""
import os
import sys
import numpy as np
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton, 
                           QLabel, QSpinBox, QCheckBox, QDoubleSpinBox, QFileDialog, 
                           QListWidget, QScrollArea, QFrame, QApplication, QRadioButton, 
                           QButtonGroup, QStyle, QTabWidget, QFormLayout, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import io
import json
from PyQt5.QtGui import QPixmap, QIcon
import traceback
import tifffile
from skimage import exposure
from PyQt5.QtGui import QImage

try:
    from GUI.bt_calculation import fit_and_plot, process_donor_only_samples, process_acceptor_only_samples
except ImportError or ModuleNotFoundError:
    from bt_calculation import fit_and_plot, process_donor_only_samples, process_acceptor_only_samples

class AnalysisChannelTab(QWidget):
    fit_confirmation_signal = pyqtSignal()
    def __init__(self, channel_name, config_manager=None, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.channel_name = channel_name
        self.results = {}
        self.image_paths = []
        self.fit_results = {}
        self.selected_fit_model = 'Exponential'
        self.fit_is_confirmed = False
        self.zoom_connection_id = None
        self.pan_connection_id = None
        self.current_theme = 'light'  # Will be updated in initUI

        # Flag to avoid auto-refit when thresholds applied
        self.threshold_active = False

        self.zoom_timer = QTimer(self)
        self.zoom_timer.setSingleShot(True)
        self.zoom_timer.timeout.connect(self.refit_and_update)
        
        self.initUI()
        self.setAcceptDrops(True)

    def initUI(self):
        main_layout = QHBoxLayout(self)
        settings_panel = self.create_settings_panel()
        
        results_and_plot_area = QWidget()
        results_and_plot_layout = QVBoxLayout(results_and_plot_area)
        
        self.coeffs_widget, self.radio_group = self.create_channel_results_group(self.channel_name)
        self.plot_widget = self.create_plot_widget()

        results_and_plot_layout.addWidget(self.coeffs_widget['group'])
        results_and_plot_layout.addWidget(self.plot_widget)

        main_layout.addWidget(settings_panel)
        main_layout.addWidget(results_and_plot_area)
        self.setLayout(main_layout)

    def create_settings_panel(self):
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)
        settings_widget.setFixedWidth(300)

        if self.channel_name == 'S1':
            group_title = "Donor-Only Samples"
        else:
            group_title = "Acceptor-Only Samples"
        settings_layout.addWidget(self.create_image_selection_group(group_title, self.add_image, self.remove_image))
        
        settings_layout.addWidget(self.create_processing_settings_group())
        # Threshold group for manual filtering
        self.threshold_group = self.create_threshold_group()
        settings_layout.addWidget(self.threshold_group)

        self.run_button = QPushButton(f"Run {self.channel_name} Analysis")
        self.run_button.clicked.connect(self.run_analysis)
        settings_layout.addWidget(self.run_button)

        confirm_reset_layout = QHBoxLayout()
        self.confirm_button = QPushButton("Confirm Fit")
        self.confirm_button.clicked.connect(self.confirm_fit)
        self.confirm_button.setEnabled(False)
        confirm_reset_layout.addWidget(self.confirm_button)

        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_analysis)
        self.reset_button.setEnabled(False)
        confirm_reset_layout.addWidget(self.reset_button)
        settings_layout.addLayout(confirm_reset_layout)

        self.status_label = QLabel("Ready. Add images and run analysis.")
        self.status_label.setWordWrap(True)
        settings_layout.addWidget(self.status_label)

        settings_layout.addStretch(1)

        # Make the entire settings panel scrollable
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(settings_widget)
        scroll_area.setFixedWidth(300)
        return scroll_area

    def create_image_selection_group(self, title, add_method, remove_method):
        group = QGroupBox(title)
        layout = QVBoxLayout()
        
        self.image_list = QListWidget()
        self.image_list.setFixedHeight(150)

        buttons_layout = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(add_method)
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(remove_method)
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.remove_button)
        
        layout.addWidget(self.image_list)
        layout.addLayout(buttons_layout)

        # Preview area for showing first frame of selected image
        self.preview_label = QLabel("Preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFixedHeight(180)
        # Set initial style according to theme
        app = QApplication.instance()
        palette = app.palette()
        is_dark = palette.window().color().lightness() < 128
        bg_col = '#2b2b2b' if is_dark else '#f8f8f8'
        border_col = '#555' if is_dark else '#ccc'
        self.preview_label.setStyleSheet(f"border: 1px solid {border_col}; background: {bg_col};")
        layout.addWidget(self.preview_label)

        # Update preview when selection changes
        self.image_list.currentRowChanged.connect(self.show_image_preview)
        group.setLayout(layout)
        return group

    def create_processing_settings_group(self):
        group = QGroupBox("Processing Settings")
        layout = QFormLayout()

        self.sigma_spin = QDoubleSpinBox()
        self.sigma_spin.setRange(0, 10)
        self.sigma_spin.setSingleStep(0.1)
        default_sigma = 2.0 if self.config is None else self.config.get(f'bt.{self.channel_name}.sigma', 2.0)
        self.sigma_spin.setValue(default_sigma)
        self.add_info_icon(layout, "Gaussian Blur Sigma:", self.sigma_spin, "Standard deviation for Gaussian kernel.")

        self.sampling_check = QCheckBox("Enable")
        self.sample_size_spin = QSpinBox()
        self.sample_size_spin.setRange(1, 1000000)
        default_sample = 10000 if self.config is None else self.config.get(f'bt.{self.channel_name}.sample_size', 10000)
        self.sample_size_spin.setValue(default_sample)
        self.sampling_check.toggled.connect(self.sample_size_spin.setEnabled)
        if self.config:
            self.sigma_spin.valueChanged.connect(lambda v: self.config.set(f'bt.{self.channel_name}.sigma', float(v)))
            self.sampling_check.toggled.connect(lambda state: self.config.set(f'bt.{self.channel_name}.sampling_enabled', bool(state)))
            self.sample_size_spin.valueChanged.connect(lambda v: self.config.set(f'bt.{self.channel_name}.sample_size', int(v)))
            # restore sampling enabled state
            self.sampling_check.setChecked(self.config.get(f'bt.{self.channel_name}.sampling_enabled', False))
            self.sample_size_spin.setEnabled(self.sampling_check.isChecked())
        self.sample_size_spin.setEnabled(False)
        self.add_info_icon(layout, "Random Sampling:", self.sampling_check, "Enable to use a random subset of pixels.")
        layout.addRow("Sample Size:", self.sample_size_spin)

        group.setLayout(layout)
        return group

    def create_channel_results_group(self, channel_name):
        group = QGroupBox(f"{channel_name} Coefficients")
        layout = QHBoxLayout()
        radio_group = QButtonGroup(self)

        models = {'Constant': {'params': ['b']}, 'Linear': {'params': ['a', 'b']}, 'Exponential': {'params': ['a', 'k', 'b']}}
        coeffs_widgets = {}
        for model_name, details in models.items():
            model_group = QGroupBox()
            model_layout = QVBoxLayout()
            radio = QRadioButton(model_name)
            radio_group.addButton(radio)
            model_layout.addWidget(radio)
            formula_label = QLabel()
            pixmap = self.render_latex_formula(model_name)
            formula_label.setPixmap(pixmap)
            model_layout.addWidget(formula_label)
            params_widgets = {}
            for param in details['params']:
                param_label = QLabel(f"{param}: --")
                model_layout.addWidget(param_label)
                params_widgets[param] = param_label
            model_group.setLayout(model_layout)
            layout.addWidget(model_group)
            coeffs_widgets[model_name] = {'radio': radio, 'params': params_widgets, 'formula_label': formula_label}

        coeffs_widgets['group'] = group
        group.setLayout(layout)
        coeffs_widgets['Linear']['radio'].setChecked(True)
        radio_group.buttonClicked.connect(self.update_coefficient_display)
        return coeffs_widgets, radio_group

    def create_plot_widget(self):
        plot_widget = QWidget()
        layout = QVBoxLayout(plot_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Initialize with current theme
        app = QApplication.instance()
        palette = app.palette()
        is_dark_theme = palette.window().color().lightness() < 128
        self.current_theme = 'dark' if is_dark_theme else 'light'
        
        # Create figure with theme-appropriate colors
        self.figure = plt.figure(facecolor='#2b2b2b' if is_dark_theme else 'white')
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, plot_widget)
        # Apply initial toolbar theme
        self.update_toolbar_theme()
        
        # Connect theme change signal if parent has it
        if hasattr(self.parent(), 'theme_changed'):
            self.parent().theme_changed.connect(self.update_theme)
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        
        note_label = QLabel("<b>Note:</b> After zooming, 'Home' is disabled. Re-run analysis to reset.")
        note_label.setWordWrap(True)
        note_label.setStyleSheet("font-style: italic; color: #555; border: 1px solid #ccc; padding: 5px; border-radius: 3px;")
        layout.addWidget(note_label)
        
        return plot_widget

    def update_theme(self):
        """Update plot colors when theme changes"""
        app = QApplication.instance()
        palette = app.palette()
        is_dark_theme = palette.window().color().lightness() < 128
        self.current_theme = 'dark' if is_dark_theme else 'light'
        
        # Update plot with new theme
        self.update_plot_theme()
        self.update_preview_theme()
        self.update_toolbar_theme()
        self.update_formula_theme()

    def update_plot_theme(self):
        """Update plot colors based on current theme"""
        if not hasattr(self, 'figure') or not self.figure:
            return
            
        is_dark = self.current_theme == 'dark'
        text_color = '#f0f0f0' if is_dark else 'black'
        bg_color = '#2b2b2b' if is_dark else 'white'
        grid_color = '#3a3a3a' if is_dark else '#e0e0e0'
        edge_color = '#6d6d6d' if is_dark else '#cccccc'
        
        # Update figure and axes
        self.figure.set_facecolor(bg_color)
        for ax in self.figure.get_axes():
            ax.set_facecolor(bg_color)
            ax.tick_params(colors=text_color)
            for spine in ax.spines.values():
                spine.set_edgecolor(edge_color)
            if ax.get_xlabel():
                ax.xaxis.label.set_color(text_color)
            if ax.get_ylabel():
                ax.yaxis.label.set_color(text_color)
            if ax.get_title():
                ax.title.set_color(text_color)
            ax.grid(color=grid_color, alpha=0.3)
            
            # Update legend if it exists
            legend = ax.get_legend()
            if legend:
                legend.get_frame().set_facecolor(bg_color)
                legend.get_frame().set_edgecolor(edge_color)
                for text in legend.get_texts():
                    text.set_color(text_color)
        
        # Redraw the canvas
        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.draw()

    def update_preview_theme(self):
        """Update preview label background to match theme."""
        is_dark = self.current_theme == 'dark'
        bg_col = '#2b2b2b' if is_dark else '#f8f8f8'
        border_col = '#555' if is_dark else '#ccc'
        self.preview_label.setStyleSheet(f"border: 1px solid {border_col}; background: {bg_col};")

    def update_formula_theme(self):
        """Re-render formula pixmaps to match text color in theme."""
        text_color_dark = self.current_theme == 'dark'
        for model_name, details in self.coeffs_widget.items():
            if model_name in ('group',):
                continue
            label = details.get('formula_label')
            if label:
                pixmap = self.render_latex_formula(model_name)
                label.setPixmap(pixmap)

    def update_toolbar_theme(self):
        """Adjust navigation toolbar icon colors based on theme."""
        if not hasattr(self, 'toolbar'):
            return
        is_dark = self.current_theme == 'dark'
        if is_dark:
            # recolor icons to white
            for action in self.toolbar.actions():
                # Cache original icon once
                if action.data() is None:
                    action.setData(action.icon())
                icon = action.icon()
                if not icon.isNull():
                    pixmap = icon.pixmap(24, 24)
                    white_pix = self._pixmap_to_white(pixmap)
                    action.setIcon(QIcon(white_pix))
            self.toolbar.setStyleSheet("QToolButton {color: white;}")
        else:
            for action in self.toolbar.actions():
                orig_icon = action.data()
                if isinstance(orig_icon, QIcon):
                    action.setIcon(orig_icon)
            # clear stylesheet
            self.toolbar.setStyleSheet("")

    def _pixmap_to_white(self, pixmap):
        """Return a white version of a mono pixmap."""
        img = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        for y in range(img.height()):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                # If pixel not transparent and dark, make white
                if c.alpha() > 0 and c.red() < 128:
                    img.setPixelColor(x, y, Qt.white)
        return QPixmap.fromImage(img)

    def on_zoom_pan(self, ax):
        if self.fit_is_confirmed:
            return
        if self.zoom_timer.isActive():
            self.zoom_timer.stop()
        self.zoom_timer.start(500)

    def add_info_icon(self, layout, label_text, widget, tooltip_text):
        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel(label_text))
        row_layout.addWidget(widget)
        info_button = QPushButton()
        info_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        info_button.setFlat(True)
        info_button.setToolTip(tooltip_text)
        row_layout.addWidget(info_button)
        layout.addRow(row_layout)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls]
        valid_files = [f for f in files if f.lower().endswith(('.tif', '.tiff'))]
        if valid_files:
            self.add_image_paths(valid_files)

    def add_image(self):
        files, _ = QFileDialog.getOpenFileNames(self, f"Select {self.channel_name} Images", "", "TIFF Files (*.tif *.tiff)")
        if files:
            self.add_image_paths(files)

    def add_image_paths(self, file_paths):
        added_files = []
        for path in file_paths:
            if path not in self.image_paths:
                self.image_paths.append(path)
                added_files.append(os.path.basename(path))
        if added_files:
            self.image_list.addItems(added_files)
            # Select last added image to trigger preview
            self.image_list.setCurrentRow(self.image_list.count() - 1)

    def remove_image(self):
        for item in self.image_list.selectedItems():
            row = self.image_list.row(item)
            self.image_list.takeItem(row)
            del self.image_paths[row]

    def show_image_preview(self, index):
        """Display the first frame of the selected TIFF image in the preview label."""
        if index < 0 or index >= len(self.image_paths):
            self.preview_label.clear()
            self.preview_label.setText("Preview")
            return
        try:
            img_path = self.image_paths[index]
            img = tifffile.imread(img_path)[0].astype(float)
            # Contrast enhancement for preview – adaptive histogram equalization
            img_norm = (img - img.min()) / (np.ptp(img) + 1e-8)
            img_eq = exposure.equalize_adapthist(img_norm, clip_limit=0.03)
            img_uint8 = (img_eq * 255).astype(np.uint8)
            h, w = img_uint8.shape
            qimg = QImage(img_uint8.data, w, h, w, QImage.Format_Grayscale8)
            pixmap = QPixmap.fromImage(qimg).scaled(self.preview_label.width(), self.preview_label.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_label.setPixmap(pixmap)
        except Exception as e:
            self.preview_label.setText("Error loading preview")
            print(f"Preview error: {e}")

    def render_latex_formula(self, model):
        formulas = {'Constant': r'$y = b$', 'Linear': r'$y = ax + b$', 'Exponential': r'$y = ae^{-kx} + b$'}
        text_color = 'white' if getattr(self, 'current_theme', 'light') == 'dark' else 'black'
        fig = plt.figure(figsize=(1.5, 0.5), facecolor='none')
        fig.text(0.5, 0.5, formulas.get(model, ''), ha='center', va='center', fontsize=12, color=text_color)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', transparent=True)
        plt.close(fig)
        buf.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.read())
        return pixmap

    def run_analysis(self):
        if not self.image_paths:
            self.show_status("Please select at least one image.", 'red')
            return
        try:
            self.show_status("Processing...", 'blue')
            QApplication.processEvents()

            self.threshold_active = False  # reset
            self.figure.clear(); self.ax = self.figure.add_subplot(1, 1, 1)
            self.ax.callbacks.connect('xlim_changed', self.on_zoom_pan)
            self.ax.callbacks.connect('ylim_changed', self.on_zoom_pan)

            if self.channel_name == 'S1':
                d_intensity, s1 = process_donor_only_samples(self.image_paths, self.sigma_spin.value())
                self.results = {'d_intensity': d_intensity, 's1': s1}
                self.fit_results = fit_and_plot(d_intensity, s1, 'Donor Intensity', 'S1 Ratio', 'S1 vs Donor', self.ax, self.sampling_check.isChecked(), self.sample_size_spin.value())
            else:
                a_intensity, s2 = process_acceptor_only_samples(self.image_paths, self.sigma_spin.value())
                self.results = {'a_intensity': a_intensity, 's2': s2}
                self.fit_results = fit_and_plot(a_intensity, s2, 'Acceptor Intensity', 'S2 Ratio', 'S2 vs Acceptor', self.ax, self.sampling_check.isChecked(), self.sample_size_spin.value())
            
            self.ax.set_ylim(0,1)
            self.figure.tight_layout()
            self.canvas.draw()
            self.update_coefficient_display()
            self.notify_if_fit_unavailable()
            # Set default threshold spinboxes to full data ranges
            if self.channel_name == 'S1':
                xdata, ydata = self.results['d_intensity'], self.results['s1']
            else:
                xdata, ydata = self.results['a_intensity'], self.results['s2']
            if len(xdata) and len(ydata):
                self.xmin_spin.setValue(float(np.min(xdata)))
                self.xmax_spin.setValue(float(np.max(xdata)))
                self.ymin_spin.setValue(max(0.0, float(np.min(ydata))))
                self.ymax_spin.setValue(min(1.0, float(np.max(ydata))))
            self.show_status("Analysis successful.", 'green')
            self.confirm_button.setEnabled(True)
            self.reset_button.setEnabled(False)
        except Exception as e:
            self.show_status(f"Error: {e}", 'red')
            traceback.print_exc()

    def refit_and_update(self):
        if not self.results:
            return

        if getattr(self, 'threshold_active', False):
            return

        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()

        if self.channel_name == 'S1':
            x_full, y_full = self.results.get('d_intensity'), self.results.get('s1')
            x_label, y_label, title = 'Donor Intensity', 'S1 Ratio', 'S1 vs Donor'
        else:
            x_full, y_full = self.results.get('a_intensity'), self.results.get('s2')
            x_label, y_label, title = 'Acceptor Intensity', 'S2 Ratio', 'S2 vs Acceptor'

        if x_full is None or y_full is None:
            return

        mask = (x_full > xlim[0]) & (x_full < xlim[1]) & (y_full > ylim[0]) & (y_full < ylim[1])
        x_zoomed, y_zoomed = x_full[mask], y_full[mask]

        self.figure.clear()
        self.ax = self.figure.add_subplot(1, 1, 1)
        self.zoom_connection_id = self.ax.callbacks.connect('xlim_changed', self.on_zoom_pan)
        self.pan_connection_id = self.ax.callbacks.connect('ylim_changed', self.on_zoom_pan)
        self.fit_results = fit_and_plot(x_zoomed, y_zoomed, x_label, y_label, title, self.ax, self.sampling_check.isChecked(), self.sample_size_spin.value())
        self.ax.set_xlim(xlim)
        self.ax.set_ylim(ylim)
        self.ax.set_ylim(0,1)
        self.figure.tight_layout()
        self.canvas.draw()
        self.update_coefficient_display()
        self.notify_if_fit_unavailable()
        self.show_status("Refit on zoomed area successful.", 'green')

    def update_coefficient_display(self, _=None):
        if not self.fit_results:
            return
        self.update_channel_coeffs(self.coeffs_widget, self.fit_results, self.radio_group)

    def update_channel_coeffs(self, widget_dict, coeffs_data, radio_group):
        if not coeffs_data:
            return
        selected_model_button = radio_group.checkedButton()
        if not selected_model_button:
            return
        selected_model = selected_model_button.text()

        for model_name, details in widget_dict.items():
            if model_name == 'group': continue
            for param_name, param_label in details['params'].items():
                param_label.setText(f"{param_name}: --")

        if selected_model in coeffs_data and coeffs_data[selected_model] is not None:
            coeffs = coeffs_data[selected_model]
            details = widget_dict[selected_model]
            if selected_model == 'Constant':
                details['params']['b'].setText(f"b: {coeffs:.4f}")
            elif selected_model == 'Linear':
                details['params']['a'].setText(f"a: {coeffs[0]:.4f}")
                details['params']['b'].setText(f"b: {coeffs[1]:.4f}")
            elif selected_model == 'Exponential':
                details['params']['a'].setText(f"a: {coeffs[0]:.4f}")
                details['params']['k'].setText(f"k: {coeffs[1]:.4f}")
                details['params']['b'].setText(f"b: {coeffs[2]:.4f}")
        elif selected_model in coeffs_data:
            details = widget_dict[selected_model]
            for param_name, param_label in details['params'].items():
                param_label.setText(f"{param_name}: Fit Failed")

    def notify_if_fit_unavailable(self):
        """Inform the user if the chosen fit model failed or is not logical for data."""
        selected_button = self.radio_group.checkedButton()
        if not selected_button or not self.fit_results:
            return
        model = selected_button.text()
        if model not in self.fit_results or self.fit_results[model] is None:
            # show warning without turning it red (use orange)
            self.show_status(f"{model} fit not applicable to current data.", 'orange')

    def show_status(self, message, color):
        self.status_label.setText(f"<font color='{color}'>{message}</font>")

    def set_controls_enabled(self, enabled):
        """Helper method to enable/disable all relevant controls."""
        self.run_button.setEnabled(enabled)
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.sigma_spin.setEnabled(enabled)
        self.sampling_check.setEnabled(enabled)
        self.sample_size_spin.setEnabled(enabled)
        for button in self.radio_group.buttons():
            button.setEnabled(enabled)

    def confirm_fit(self):
        selected_button = self.radio_group.checkedButton()
        if not selected_button:
            self.show_status("Error: No fit model selected.", "red")
            return
        self.selected_fit_model = selected_button.text()

        if self.selected_fit_model not in self.fit_results or self.fit_results[self.selected_fit_model] is None:
            self.show_status(f"Error: Fit for {self.selected_fit_model} has failed or is not available.", "red")
            return

        self.fit_is_confirmed = True
        self.set_controls_enabled(False)
        self.confirm_button.setEnabled(False)
        self.reset_button.setEnabled(True)

        if self.zoom_connection_id:
            self.ax.callbacks.disconnect(self.zoom_connection_id)
            self.zoom_connection_id = None
        if self.pan_connection_id:
            self.ax.callbacks.disconnect(self.pan_connection_id)
            self.pan_connection_id = None

        self.show_status("Fit confirmed. Controls are locked.", "blue")
        self.fit_confirmation_signal.emit()

    def reset_analysis(self):
        self.fit_is_confirmed = False
        self.set_controls_enabled(True)
        self.confirm_button.setEnabled(True)
        self.reset_button.setEnabled(False)
        
        if hasattr(self, 'ax') and self.ax:
            if not self.zoom_connection_id:
                self.zoom_connection_id = self.ax.callbacks.connect('xlim_changed', self.on_zoom_pan)
            if not self.pan_connection_id:
                self.pan_connection_id = self.ax.callbacks.connect('ylim_changed', self.on_zoom_pan)
            
        self.show_status("Controls unlocked. Ready for new analysis or refitting.", "black")

    def get_parameters(self):
        """Helper method to retrieve all parameters from this tab for saving."""
        serializable_fit_results = {}
        for model, coeffs in self.fit_results.items():
            if isinstance(coeffs, np.ndarray):
                serializable_fit_results[model] = coeffs.tolist()
            else:
                serializable_fit_results[model] = coeffs

        return {
            'sigma': self.sigma_spin.value(),
            'use_sampling': self.sampling_check.isChecked(),
            'sample_size': self.sample_size_spin.value(),
            'selected_fit_model': self.radio_group.checkedButton().text() if self.radio_group.checkedButton() else self.selected_fit_model,
            'fit_results': serializable_fit_results
        }

    def set_parameters(self, params):
        """Helper method to set all parameters from a loaded file."""
        self.sigma_spin.setValue(params.get('sigma', 1.0))
        self.sampling_check.setChecked(params.get('use_sampling', True))
        self.sample_size_spin.setValue(params.get('sample_size', 5000))

        self.fit_results = {k: np.array(v) if isinstance(v, list) else v for k, v in params.get('fit_results', {}).items()}
        self.selected_fit_model = params.get('selected_fit_model', 'Exponential')

        for button in self.radio_group.buttons():
            if button.text() == self.selected_fit_model:
                button.setChecked(True)
                break
        
        self.update_coefficient_display()

        if self.results:
            fit_and_plot(self.ax, self.results, self.fit_results, self.selected_fit_model)
            self.canvas.draw()
        
        self.confirm_button.setEnabled(True)
        self.reset_button.setEnabled(True)

    # -------------------- Threshold UI --------------------
    def create_threshold_group(self):
        """Widgets for xmin/xmax/ymin/ymax and related buttons."""
        thresh_group = QGroupBox("Thresholds")
        layout = QFormLayout()

        self.xmin_spin = QDoubleSpinBox(); self.xmin_spin.setRange(0, 1e12)
        self.xmax_spin = QDoubleSpinBox(); self.xmax_spin.setRange(0, 1e12)
        self.ymin_spin = QDoubleSpinBox(); self.ymin_spin.setRange(0, 1); self.ymin_spin.setSingleStep(0.01)
        self.ymax_spin = QDoubleSpinBox(); self.ymax_spin.setRange(0, 1); self.ymax_spin.setSingleStep(0.01)

        layout.addRow("X min:", self.xmin_spin)
        layout.addRow("X max:", self.xmax_spin)
        layout.addRow("Y min:", self.ymin_spin)
        layout.addRow("Y max:", self.ymax_spin)

        btn_layout = QHBoxLayout()
        self.update_plot_btn = QPushButton("Update Plot")
        self.update_plot_btn.clicked.connect(self.apply_thresholds_and_refit)
        self.show_thresh_btn = QPushButton("Show on Plot")
        self.show_thresh_btn.clicked.connect(self.show_threshold_lines)
        btn_layout.addWidget(self.update_plot_btn)
        btn_layout.addWidget(self.show_thresh_btn)

        layout.addRow(btn_layout)
        thresh_group.setLayout(layout)
        return thresh_group

    # ---------------- Threshold handling methods ----------------
    def apply_thresholds_and_refit(self):
        """Apply user-defined thresholds and update the plot and fit."""
        if not self.results:
            self.show_status("Please run analysis first.", 'red'); return

        if self.channel_name == 'S1':
            x_full, y_full = self.results['d_intensity'], self.results['s1']
            x_label, y_label, title = 'Donor Intensity', 'S1 Ratio', 'S1 vs Donor'
        else:
            x_full, y_full = self.results['a_intensity'], self.results['s2']
            x_label, y_label, title = 'Acceptor Intensity', 'S2 Ratio', 'S2 vs Acceptor'

        xmin, xmax = self.xmin_spin.value(), self.xmax_spin.value()
        ymin, ymax = self.ymin_spin.value(), self.ymax_spin.value()

        finite_mask = np.isfinite(x_full) & np.isfinite(y_full)
        mask = finite_mask & (x_full >= xmin) & (x_full <= xmax) & (y_full >= ymin) & (y_full <= ymax)
        if np.count_nonzero(mask) == 0:
            self.show_status("Threshold excludes all data points.", 'red'); return

        x_sel, y_sel = x_full[mask], y_full[mask]

        # Reset threshold lines storage because axes will be cleared
        self._threshold_lines = []

        # Plot and fit
        self.figure.clear(); self.ax = self.figure.add_subplot(1,1,1)
        self.fit_results = fit_and_plot(x_sel, y_sel, x_label, y_label, title, self.ax, self.sampling_check.isChecked(), self.sample_size_spin.value())
        self.ax.set_ylim(0,1)
        self.figure.tight_layout(); self.canvas.draw()
        # Draw threshold lines so they remain visible
        self.show_threshold_lines()

        self.update_coefficient_display(); self.notify_if_fit_unavailable()
        self.show_status("Plot updated with thresholds.", 'green')

        # set flag so future zoom callbacks ignored
        self.threshold_active = True

    def show_threshold_lines(self):
        """Draw threshold lines on plot to visualize current ranges."""
        if not hasattr(self, 'ax'):
            return
        xmin, xmax = self.xmin_spin.value(), self.xmax_spin.value()
        ymin, ymax = self.ymin_spin.value(), self.ymax_spin.value()

        recreate = (
            not hasattr(self, '_threshold_lines') or
            len(self._threshold_lines) != 4 or
            any(ln.axes is None for ln in self._threshold_lines)
        )
        if recreate:
            # Create lines first time
            self._threshold_lines = [
                self.ax.axvline(xmin, color='purple', linestyle='--'),
                self.ax.axvline(xmax, color='purple', linestyle='--'),
                self.ax.axhline(ymin, color='purple', linestyle='--'),
                self.ax.axhline(ymax, color='purple', linestyle='--'),
            ]
        else:
            # Update existing line positions
            self._threshold_lines[0].set_xdata([xmin, xmin])
            self._threshold_lines[1].set_xdata([xmax, xmax])
            self._threshold_lines[2].set_ydata([ymin, ymin])
            self._threshold_lines[3].set_ydata([ymax, ymax])

        self.canvas.draw_idle()

class BleedThroughTab(QWidget):
    # Signal emitted when theme changes
    theme_changed = pyqtSignal()
    
    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.donor_tab = AnalysisChannelTab('S1', self.config, self)
        self.acceptor_tab = AnalysisChannelTab('S2', self.config, self)
        self.initUI()
        self.donor_tab.fit_confirmation_signal.connect(self.check_confirmation_status)
        self.acceptor_tab.fit_confirmation_signal.connect(self.check_confirmation_status)
        
        # Connect theme changed signal from parent if available
        if parent and hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(self.on_theme_changed)
    
    def on_theme_changed(self):
        """Handle theme changes from parent"""
        self.theme_changed.emit()

    def initUI(self):
        main_layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self.donor_tab, "Donor (S1)")
        tabs.addTab(self.acceptor_tab, "Acceptor (S2)")
        main_layout.addWidget(tabs)

        # Centralized Save/Load controls
        save_load_group = QGroupBox("Manage Parameters")
        save_load_layout = QHBoxLayout()
        self.save_button = QPushButton("Save Parameters")
        self.save_button.clicked.connect(self.save_parameters)
        self.save_button.setEnabled(False) # Disabled by default
        self.load_button = QPushButton("Load Parameters")
        self.load_button.clicked.connect(self.load_parameters)
        save_load_layout.addWidget(self.save_button)
        save_load_layout.addWidget(self.load_button)
        save_load_group.setLayout(save_load_layout)
        main_layout.addWidget(save_load_group)

        self.setLayout(main_layout)

    def check_confirmation_status(self):
        if self.donor_tab.fit_is_confirmed and self.acceptor_tab.fit_is_confirmed:
            self.save_button.setEnabled(True)
            self.donor_tab.show_status("Both fits confirmed. Ready to transfer.", "green")
            self.acceptor_tab.show_status("Both fits confirmed. Ready to transfer.", "green")
        else:
            self.save_button.setEnabled(False)

    def save_parameters(self):
        file_path = 'bt_params.json' # Predefined file name
        params_to_save = {
            'donor_params': self.donor_tab.get_parameters(),
            'acceptor_params': self.acceptor_tab.get_parameters()
        }

        try:
            with open(file_path, 'w') as f:
                json.dump(params_to_save, f, indent=4)
            self.donor_tab.show_status(f"Parameters saved to {file_path}", "green")
            self.acceptor_tab.show_status(f"Parameters saved to {file_path}", "green")
            QMessageBox.information(self, "Success", f"Parameters were successfully saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Error saving parameters: {e}")
            traceback.print_exc()

    def load_parameters(self):
        default_path = 'bt_params.json'
        file_to_load = None

        if os.path.exists(default_path):
            reply = QMessageBox.question(self, 'Load Parameters',
                                       "A file from the last session was found. Would you like to load it?",
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                                       QMessageBox.Yes)

            if reply == QMessageBox.Yes:
                file_to_load = default_path
            elif reply == QMessageBox.No:
                # User wants to choose a different file
                file_to_load, _ = QFileDialog.getOpenFileName(self, "Load Bleed-Through Parameters", "", "JSON Files (*.json);;All Files (*)")
            else: # Cancel
                return
        else:
            # Default file doesn't exist, so just open the dialog
            file_to_load, _ = QFileDialog.getOpenFileName(self, "Load Bleed-Through Parameters", "", "JSON Files (*.json);;All Files (*)")

        if file_to_load:
            self._load_from_path(file_to_load)

    def _load_from_path(self, file_path):
        try:
            with open(file_path, 'r') as f:
                loaded_params = json.load(f)

            if 'donor_params' not in loaded_params or 'acceptor_params' not in loaded_params:
                QMessageBox.warning(self, "Invalid File", "The selected file does not contain valid donor and acceptor parameters.")
                return

            self.donor_tab.set_parameters(loaded_params['donor_params'])
            self.acceptor_tab.set_parameters(loaded_params['acceptor_params'])

            self.donor_tab.show_status(f"Parameters loaded from {os.path.basename(file_path)}", "green")
            self.acceptor_tab.show_status(f"Parameters loaded from {os.path.basename(file_path)}", "green")
            self.check_confirmation_status()

        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Error loading parameters: {e}")
            traceback.print_exc()
