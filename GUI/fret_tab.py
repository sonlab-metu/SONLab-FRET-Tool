import os
import sys
import numpy as np
import tifffile
import czifile as czi
from sklearn.mixture import GaussianMixture
from scipy import stats
from scipy.signal import find_peaks
from scipy.ndimage import gaussian_filter1d
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QPushButton, QLabel,
    QFileDialog, QListWidget, QFormLayout, QCheckBox, QMessageBox,
    QDoubleSpinBox, QToolButton, QStyle, QTableWidget, QTableWidgetItem, QHeaderView, QListWidgetItem,
    QTabWidget, QApplication, QComboBox, QLineEdit, QButtonGroup, QRadioButton, QScrollArea, QGridLayout,
    QSplitter, QSpinBox, QColorDialog, QScrollArea, QSizePolicy, QProgressDialog
)
from PyQt5.QtGui import QColor
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.legend import Legend
from scipy.ndimage import uniform_filter, gaussian_filter
import sys
from PyQt5.QtCore import Qt, QTimer, QMetaObject, Q_ARG, pyqtSlot, QThread, QObject, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog
import csv

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class FretTab(QWidget):
    def __init__(self, config_manager=None, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.current_theme = 'light'
        
        # Connect to parent's theme_changed signal if available
        if parent and hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(self.update_theme)
        self.image_paths = []
        self.donor_model = None
        self.donor_coeffs = None
        self.acceptor_model = None
        self.acceptor_coeffs = None
        self.analysis_results = {}
        self.image_groups = {}
        self.ramps_colormap = self.load_ramps_colormap()
        self.current_representative_image = None  # Track current representative image
        self.current_cell_id = None  # Track currently selected cell ID
        self.current_cell_mask = None  # Track currently selected cell mask
        self.distribution_enabled = True  # Track distribution analysis state
        self.initUI()
        self.setAcceptDrops(True)
        self.update_tab_state(False)
        self.image_group.setEnabled(True)

    def update_theme(self):
        app = QApplication.instance()
        palette = app.palette()
        is_dark_theme = palette.window().color().lightness() < 128
        self.current_theme = 'dark' if is_dark_theme else 'light'
        
        # Update scrollbar styles for better visibility in dark theme
        scrollbar_style = """
            QScrollBar:horizontal {
                border: none;
                background: #2d2d2d;
                height: 12px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: #606060;
                min-width: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #707070;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                height: 0px;
            }
            QScrollBar:vertical {
                border: none;
                background: #2d2d2d;
                width: 12px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #606060;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #707070;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                width: 0px;
                height: 0px;
            }
        """ if is_dark_theme else ""
        
        # Apply the style to the application
        app.setStyleSheet(app.styleSheet() + scrollbar_style)
        
        # Update plot themes
        self.update_plot_themes()

    def _update_axes_theme(self, ax, is_dark):
        """Update the theme of a single axes object."""
        # Set colors based on theme
        text_color = '#ffffff' if is_dark else '#000000'
        grid_color = '#4a4a4a' if is_dark else '#e0e0e0'
        face_color = '#1a1a1a' if is_dark else '#ffffff'
        
        # Update axes properties
        ax.set_facecolor(face_color)
        
        # Update title and labels
        ax.title.set_color(text_color)
        ax.xaxis.label.set_color(text_color)
        ax.yaxis.label.set_color(text_color)
        
        # Update tick colors
        ax.tick_params(axis='x', colors=text_color)
        ax.tick_params(axis='y', colors=text_color)
        
        # Update spines
        for spine in ax.spines.values():
            spine.set_edgecolor(text_color)
        
        # Update grid
        ax.grid(True, color=grid_color, alpha=0.3)
        
        # Set a high-contrast color cycle for dark theme to ensure plot lines are visible
        if is_dark:
            bright_colors = [
                '#FF6B6B',  # Red
                '#4ECDC4',  # Turquoise
                '#F7E967',  # Yellow
                '#C44DFF',  # Purple
                '#1E90FF',  # Blue
                '#FFA500',  # Orange
            ]
            ax.set_prop_cycle(color=bright_colors)
        else:
            # Revert to Matplotlib default for light theme
            ax.set_prop_cycle(None)

        # Update legend if it exists
        if ax.legend_ is not None:
            legend = ax.legend_ 
            frame = legend.get_frame()
            if frame is not None:
                frame.set_facecolor(face_color)
                frame.set_edgecolor(text_color)
            for text in legend.get_texts():
                text.set_color(text_color)
    
    def update_plot_themes(self):
        is_dark = self.current_theme == 'dark'
        
        # Common figure parameters - using pure black for dark mode
        figure_bg = '#1a1a1a' if is_dark else '#ffffff'  # Slightly off-black for better contrast
        figure_params = {
            'facecolor': figure_bg,
            'edgecolor': '#4a4a4a' if is_dark else '#e0e0e0'
        }
        
        # Canvas style sheet for dark/light mode
        canvas_style = f"""
            background-color: {figure_bg};
            border: 1px solid {'#4a4a4a' if is_dark else '#e0e0e0'};
            border-radius: 4px;
        """
        
        # Update each figure if it exists
        for fig_attr, canvas_attr in [
            ('figure', 'canvas'),
            ('hist_figure', 'hist_canvas'),
            ('box_figure', 'box_canvas'),
            ('agg_hist_figure', 'agg_hist_canvas'),
            ('agg_box_figure', 'agg_box_canvas'),
            ('fourier_image_figure', 'fourier_image_canvas'),
            ('fft_figure', 'fft_canvas'),
            ('cell_hist_figure', 'cell_hist_canvas')
        ]:
            fig = getattr(self, fig_attr, None)
            canvas = getattr(self, canvas_attr, None)
            
            if fig is not None:
                # Update figure properties
                fig.set_facecolor(figure_params['facecolor'])
                fig.set_edgecolor(figure_params['edgecolor'])
                fig.set_tight_layout(True)  # Ensure proper padding
                
                # Update all axes in the figure
                for ax in fig.get_axes():
                    self._update_axes_theme(ax, is_dark)
                
                # Update canvas properties
                if canvas is not None:
                    canvas.setStyleSheet(canvas_style)
                    canvas.draw()
                    
        # Force redraw of all canvases
        for canvas_attr in ['canvas', 'hist_canvas', 'box_canvas', 'agg_hist_canvas', 'agg_box_canvas', 'fourier_image_canvas', 'fft_canvas', 'cell_hist_canvas']:
            canvas = getattr(self, canvas_attr, None)
            if canvas is not None:
                canvas.draw()

    def _update_axes_theme(self, ax, is_dark):
        # Define colors based on theme
        text_color = '#ffffff' if is_dark else '#000000'  # Brighter white for dark mode
        bg_color = '#1e1e1e' if is_dark else '#ffffff'    # Darker background for better contrast
        grid_color = '#3a3a3a' if is_dark else '#e0e0e0'  # Slightly brighter grid for dark mode
        edge_color = '#5a5a5a' if is_dark else '#cccccc'  # Brighter edge color for dark mode
        
        # Set face colors
        ax.set_facecolor(bg_color)
        
        # Update tick parameters for better visibility
        ax.tick_params(axis='both', which='both', 
                      colors=text_color,
                      labelsize=9,
                      width=0.8,
                      length=4)
        
        # Update tick label colors
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_color(text_color)
            label.set_fontsize(9)
        
        # Update spine colors and width
        for spine in ax.spines.values():
            spine.set_edgecolor(edge_color)
            spine.set_linewidth(1.0)
            
        # Update axis label colors and font size
        ax.xaxis.label.set_color(text_color)
        ax.yaxis.label.set_color(text_color)
        ax.xaxis.label.set_fontsize(10)
        ax.yaxis.label.set_fontsize(10)
        
        # Update title color and font size
        if ax.get_title():
            ax.title.set_color(text_color)
            ax.title.set_fontsize(11)
            
        # Update grid
        ax.grid(True, color=grid_color, linestyle=':', alpha=0.7, linewidth=0.7)
        
        # Update legend
        legend = ax.get_legend()
        if legend:
            legend.get_frame().set_facecolor(bg_color)
            legend.get_frame().set_edgecolor(edge_color)
            legend.get_frame().set_alpha(0.9)
            for text in legend.get_texts():
                text.set_color(text_color)
                text.set_fontsize(9)
                
        # Update colorbar if it exists
        if hasattr(ax, 'cbar'):
            ax.cbar.ax.yaxis.set_tick_params(color=text_color, labelsize=9)
            plt.setp(plt.getp(ax.cbar.ax.axes, 'yticklabels'), 
                    color=text_color,
                    fontsize=9)
            ax.cbar.outline.set_edgecolor(edge_color)
            ax.cbar.outline.set_linewidth(1.0)

    def save_plot(self, figure, plot_type):
        """Save the plot as a high-resolution image in the background.
        
        Args:
            figure: The matplotlib figure to save
            plot_type: Type of plot ('histogram' or 'boxplot') for default filename
        """
        # Get default filename based on plot type and current formula
        default_filename = f"{plot_type}_{self.aggregate_formula_combo.currentText()}.png"
        default_filename = default_filename.replace(" ", "_")
        
        # Get save path from user
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Save {plot_type} as...",
            default_filename,
            "PNG (*.png);;TIFF (*.tif);;PDF (*.pdf);;SVG (*.svg);;All Files (*)"
        )
        
        if not file_path:
            return  # User cancelled
            
        # Create a worker class to handle the save operation
        class SaveWorker(QObject):
            finished = pyqtSignal()
            error = pyqtSignal(str)
            success = pyqtSignal(str)
            
            def __init__(self, figure, file_path):
                super().__init__()
                self.figure = figure
                self.file_path = file_path
            
            def run(self):
                try:
                    # Save with high resolution (300 DPI) and tight layout
                    self.figure.savefig(
                        self.file_path,
                        dpi=300,
                        bbox_inches='tight',
                        facecolor=self.figure.get_facecolor(),
                        edgecolor='none',
                        transparent=False
                    )
                    self.success.emit(f"Plot saved successfully to:\n{self.file_path}")
                except Exception as e:
                    self.error.emit(f"Error saving plot: {str(e)}")
                finally:
                    self.finished.emit()
        
        # Create thread and worker
        self.save_thread = QThread()
        self.save_worker = SaveWorker(figure, file_path)
        self.save_worker.moveToThread(self.save_thread)
        
        # Connect signals
        self.save_thread.started.connect(self.save_worker.run)
        self.save_thread.finished.connect(self.update_aggregate_histogram_plot)
        self.save_worker.finished.connect(self.save_thread.quit)
        self.save_worker.finished.connect(self.save_worker.deleteLater)
        self.save_thread.finished.connect(self.save_thread.deleteLater)
        self.save_worker.success.connect(self._show_save_success)
        self.save_worker.error.connect(self._show_save_error)
        
        # Start the thread
        self.save_thread.start()
    
    @pyqtSlot(str)
    def _show_save_success(self, message):
        """Show a success message after saving."""
        QMessageBox.information(self, "Save Successful", message)
    
    @pyqtSlot(str)
    def _show_save_error(self, message):
        """Show an error message if saving fails."""
        QMessageBox.critical(self, "Save Error", message)

    def export_summary_to_csv(self):
        if not self.analysis_results:
            QMessageBox.warning(self, "No Data", "No analysis results to export.")
            return
        selected_formula = self.aggregate_formula_combo.currentText()
        if not selected_formula:
            QMessageBox.warning(self, "No Formula Selected", "Please select a formula to export.")
            return
        table = self.aggregate_stats_table
        if table.rowCount() == 0 or table.columnCount() == 0:
            QMessageBox.warning(self, "Empty Table", "No data to export.")
            return
        default_filename = f"FRET_summary_{selected_formula.replace(' ', '_')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Summary as CSV",
            os.path.join(os.path.expanduser("~"), default_filename),
            "CSV Files (*.csv)"
        )
        if not file_path:
            return
        try:
            if not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                header = [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]
                writer.writerow(header)
                for row in range(table.rowCount()):
                    row_data = [table.item(row, col).text() if table.item(row, col) else "" for col in range(table.columnCount())]
                    writer.writerow(row_data)
            QMessageBox.information(self, "Export Successful", f"Summary data exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV file:\n{str(e)}")

    @staticmethod
    def _p_to_symbol(p):
        if p < 0.0001: return "****"
        if p < 0.001: return "***"
        if p < 0.01: return "**"
        if p < 0.05: return "*"
        return "ns"

    @staticmethod
    def _draw_sig(ax, x1, x2, y, text):
        ax.plot([x1, x1, x2, x2], [y, y+0.5, y+0.5, y], lw=1.0, c='k')
        ax.text((x1+x2)/2, y+0.5, text, ha='center', va='bottom')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        files = [url.toLocalFile() for url in urls]
        valid_files = [f for f in files if f.lower().endswith(('.tif', '.tiff', '.czi'))]
        if valid_files:
            self.add_image_paths(valid_files)

    def add_info_icon(self, layout, label_text, widget, tooltip_text):
        label_widget = QWidget()
        h_layout = QHBoxLayout(label_widget)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addWidget(QLabel(label_text))
        info_button = QToolButton()
        info_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxInformation))
        info_button.setToolTip(tooltip_text)
        info_button.setStyleSheet("QToolButton { border: none; background: transparent; }")
        h_layout.addWidget(info_button)
        h_layout.addStretch()
        layout.addRow(label_widget, widget)

    def _open_histogram_popout(self, figure, title):
        """Special handler for histogram popouts that recreates the plot from data"""
        # Get the current formula and data
        selected_formula = self.aggregate_formula_combo.currentText()
        if not selected_formula or not hasattr(self, 'analysis_results') or not self.analysis_results:
            QMessageBox.warning(self, "Error", "No data available for histogram.")
            return
        
        # Create dialog and layout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} (Pop-out)")
        dlg.setMinimumSize(1000, 800)  # Larger default size for better visibility
        
        layout = QVBoxLayout(dlg)
        
        # Create scroll area for the plot
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create container for the scroll area
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(5)
        
        # Create a new figure with larger size for popout
        new_fig = plt.Figure(figsize=(12, 8), dpi=100)  # Larger size for popout
        new_fig.set_facecolor('black' if self.current_theme == 'dark' else 'white')
        
        # Create canvas and set size policy
        canvas = FigureCanvas(new_fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Create axes with more space
        ax = new_fig.add_subplot(111)
        
        # Get histogram data
        edges = np.linspace(0, 50, 257)
        centers = (edges[:-1] + edges[1:]) / 2
        lower_thr = self.lower_threshold_spinbox.value()
        upper_thr = self.upper_threshold_spinbox.value()
        
        # Group data by image group
        group_hists = {}
        for path, efficiencies in self.analysis_results.items():
            if selected_formula not in efficiencies or "_labels" not in efficiencies:
                continue
            gname = self.image_groups.get(path, "Ungrouped")
            eff_map = efficiencies[selected_formula]
            labels_arr = efficiencies["_labels"]
            
            for lbl in np.unique(labels_arr)[1:]:
                mask = ((labels_arr == lbl) & np.isfinite(eff_map) & (eff_map > 0))
                vals = eff_map[mask]
                if vals.size == 0:
                    continue
                hist_vals = vals[(vals >= lower_thr) & (vals <= upper_thr)]
                if hist_vals.size == 0:
                    continue
                counts, _ = np.histogram(hist_vals, bins=edges)
                pct = (counts / vals.size) * 100
                group_hists.setdefault(gname, []).append(pct)
        
        if not group_hists:
            QMessageBox.warning(self, "Error", "No valid data points found for histogram.")
            return
        
        # Plot each group's histogram
        colors = plt.cm.tab10.colors
        y_max = 0
        
        for idx, (group, hist_list) in enumerate(group_hists.items()):
            hist_matrix = np.vstack(hist_list)
            mean = np.mean(hist_matrix, axis=0)
            std = np.std(hist_matrix, axis=0)
            sem = std / np.sqrt(hist_matrix.shape[0])
            
            # Use SEM or SD based on radio button selection
            error_type = "SEM" if hasattr(self, 'sem_radio') and self.sem_radio.isChecked() else "SD"
            error_bars = sem if error_type == "SEM" else std
            
            # Update y_max for axis limits
            y_max = max(y_max, np.max(mean + error_bars))
            
            # Plot with error bars
            ax.errorbar(centers, mean, yerr=error_bars, fmt='-o', 
                       color=colors[idx % len(colors)], 
                       markersize=3, linewidth=1.2, 
                       capsize=3, alpha=0.7, 
                       label=f'{group} (n={len(hist_list)})')
        
        # Set plot labels and title
        ax.set_xlabel("FRET Efficiency (%)", fontsize=10)
        ax.set_ylabel("Pixel Percentage (%)", fontsize=10)
        
        # Set title with error type
        title_text = self.agg_hist_title_edit.text() or f"Aggregate Histogram by Group (Error: {error_type})"
        ax.set_title(title_text, fontsize=11)
        
        # Set axis limits
        ax.set_xlim(0, 50)
        ax.set_ylim(0, y_max * 1.2 if y_max > 0 else 1)
        
        # Add grid for better readability
        ax.grid(True, linestyle='--', alpha=0.3)
        
        # Create a compact legend in the upper right
        if len(group_hists) > 1:
            legend = ax.legend(
                loc='upper right',
                bbox_to_anchor=(1.0, 1.0),
                ncol=1,  # Single column for better space usage
                frameon=True,
                framealpha=0.8,
                fancybox=True,
                shadow=False,
                borderpad=0.5,
                handlelength=1.0,
                handletextpad=0.5,
                columnspacing=0.5,
                fontsize='x-small',
                markerscale=0.8,
                labelspacing=0.3
            )
            
            # Adjust the legend frame to be more compact
            frame = legend.get_frame()
            frame.set_linewidth(0.5)
            frame.set_facecolor('0.9' if self.current_theme == 'light' else '0.2')
            frame.set_edgecolor('0.5')
        
        # Adjust layout to make room for legend below
        new_fig.tight_layout(rect=[0, 0.05, 1, 0.95])  # Leave space at bottom for legend
        
        # Add export button
        btn_export = QPushButton("Export Data")
        btn_export.clicked.connect(self.export_aggregate_histogram_data)
        
        # Set up the rest of the UI
        toolbar = NavigationToolbar(canvas, dlg)
        container_layout.addWidget(toolbar)
        container_layout.addWidget(canvas)
        container_layout.addWidget(btn_export)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Store reference to prevent garbage collection
        if not hasattr(self, '_popup_refs'):
            self._popup_refs = []
        self._popup_refs.append((dlg, canvas, new_fig, btn_export))
        
        # Show the dialog
        dlg.show()
    
    def _open_boxplot_popout(self, figure, title):
        """Special handler for box plot popouts that recreates the plot from data"""
        # Get the current formula and data
        selected_formula = self.aggregate_formula_combo.currentText()
        if not selected_formula or not hasattr(self, 'analysis_results') or not self.analysis_results:
            QMessageBox.warning(self, "Error", "No data available for box plot.")
            return
        
        # Create dialog and layout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} (Pop-out)")
        dlg.setMinimumSize(1000, 800)  # Larger default size for better visibility
        
        layout = QVBoxLayout(dlg)
        
        # Create scroll area for the plot
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create container for the scroll area
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(5)
        
        # Create a new figure with larger size for popout
        new_fig = plt.Figure(figsize=(12, 8), dpi=100)  # Larger size for popout
        new_fig.set_facecolor('black' if self.current_theme == 'dark' else 'white')
        
        # Create canvas and set size policy
        canvas = FigureCanvas(new_fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Group data by image group
        from collections import defaultdict
        group_data = defaultdict(list)
        for path, efficiencies in self.analysis_results.items():
            if selected_formula not in efficiencies or "_labels" not in efficiencies:
                continue
            lower_thr = self.lower_threshold_spinbox.value()
            upper_thr = self.upper_threshold_spinbox.value()
            eff_map = efficiencies[selected_formula]
            labels_arr = efficiencies["_labels"]
            per_cell_avgs = []
            for lbl in np.unique(labels_arr)[1:]:  # Skip background (0)
                mask = ((labels_arr == lbl) & np.isfinite(eff_map) & 
                       (eff_map >= lower_thr) & (eff_map <= upper_thr) & (eff_map > 0))
                vals = eff_map[mask]
                if vals.size > 0:
                    per_cell_avgs.append(np.mean(vals))
            if per_cell_avgs:
                gname = self.image_groups.get(path, "Ungrouped")
                group_data[gname].extend(per_cell_avgs)
        
        if not group_data:
            QMessageBox.warning(self, "Error", "No valid data points found for box plot.")
            return
        
        # Prepare data for plotting
        labels_sorted = sorted(group_data.keys())
        box_data = [group_data[g] for g in labels_sorted]
        
        # Create axes with more space
        ax = new_fig.add_subplot(111)
        
        # Calculate statistics for legend (excluding outliers)
        group_stats = []
        for i, (group, data) in enumerate(zip(labels_sorted, box_data)):
            if not data:
                continue
                
            # Calculate whisker positions to identify outliers
            q1 = np.percentile(data, 25)
            q3 = np.percentile(data, 75)
            iqr = q3 - q1
            lower_whisker = q1 - 1.5 * iqr
            upper_whisker = q3 + 1.5 * iqr
            
            # Filter out outliers for statistics
            inliers = [x for x in data if lower_whisker <= x <= upper_whisker]
            
            # Calculate statistics using only inliers
            mean_val = np.mean(inliers) if inliers else 0
            n_points = len(inliers)
            
            # Calculate compactness using only inliers
            compactness = (np.sum((np.array(inliers) - mean_val) ** 2))/len(inliers) if inliers else 0
            group_stats.append((i, group, mean_val, n_points, compactness))
        
        # Calculate statistical significance
        import scipy.stats as stats
        comparisons = []
        if len(labels_sorted) == 2:
            pval = stats.ttest_ind(box_data[0], box_data[1], equal_var=False).pvalue
            comparisons.append((0, 1, pval))
        elif len(labels_sorted) > 2:
            p_anova = stats.f_oneway(*box_data).pvalue
            from itertools import combinations
            for (i, j) in combinations(range(len(labels_sorted)), 2):
                p = stats.ttest_ind(box_data[i], box_data[j], equal_var=False).pvalue * len(labels_sorted)*(len(labels_sorted)-1)/2
                comparisons.append((i, j, min(p, 1.0)))
        
        # Create box plot
        y_max = max(max(d) if d else 0 for d in box_data) * 1.05
        step = y_max * 0.05 if y_max > 0 else 1
        cur_y = y_max
        
        # Get colors for each group using the same colormap as the main plot
        colors = plt.cm.tab10.colors
        box_colors = [colors[i % len(colors)] for i in range(len(box_data))]
        
        # Create boxplot with consistent styling and disable built-in outliers
        for i, (data, color) in enumerate(zip(box_data, box_colors), 1):
            if not data:
                continue
                
            # Create the boxplot with group-specific color
            bp = ax.boxplot([data], positions=[i], vert=True, patch_artist=True, widths=0.6,
                          boxprops=dict(facecolor=color, alpha=0.5),
                          medianprops=dict(color="red", linewidth=1.5),
                          showmeans=True,
                          meanprops=dict(marker='D', markeredgecolor='black',
                                       markerfacecolor='yellow', markersize=5),
                          showfliers=False)  # We'll add our own fliers
            
            # Calculate whisker positions (Q1 - 1.5*IQR and Q3 + 1.5*IQR)
            q1 = np.percentile(data, 25)
            q3 = np.percentile(data, 75)
            iqr = q3 - q1
            lower_whisker = q1 - 1.5 * iqr
            upper_whisker = q3 + 1.5 * iqr
            
            # Add jitter to x-positions
            jitter = 0.15  # Slightly more jitter for better visibility
            x_jitter = np.random.uniform(i - jitter, i + jitter, size=len(data))
            
            # Convert to numpy array for boolean indexing
            data_array = np.array(data)
            
            # Separate inliers and outliers
            inliers = (data_array >= lower_whisker) & (data_array <= upper_whisker)
            outliers = ~inliers
            
            # Plot inliers with the same color as the box
            ax.scatter(x_jitter[inliers], data_array[inliers],
                      color=color, s=25, alpha=0.9,
                      zorder=4, edgecolor='white', linewidth=0.8)
            
            # Plot outliers (red in light theme, green in dark theme)
            if np.any(outliers):
                outlier_color = '#2ecc71' if self.current_theme == 'dark' else '#e74c3c'
                ax.scatter(x_jitter[outliers], data_array[outliers],
                          color=outlier_color, s=30, alpha=0.9,
                          zorder=4, edgecolor='white', linewidth=0.8)
        
        # Add significance bars
        for i, j, p in comparisons:
            symbol = self._p_to_symbol(p)
            self._draw_sig(ax, i+1, j+1, cur_y, symbol)
            cur_y += step
        
        # Set plot labels and title
        ax.set_xticks(range(1, len(labels_sorted) + 1))
        ax.set_xticklabels(labels_sorted, rotation=45, ha='right')
        ax.set_ylabel(self.agg_box_y_label_edit.text() or "% FRET Efficiency")
        
        # Set title
        title_text = self.agg_box_title_edit.text() or f"Per-cell Averages by Group ({selected_formula})\n(Threshold: {self.lower_threshold_spinbox.value()}-{self.upper_threshold_spinbox.value()}%)"
        ax.set_title(title_text)
        
        # Create a more compact legend with just the group names and colors
        legend_handles = []
        legend_labels = []
        for (i, group, mean_val, n_points, compactness), color in zip(group_stats, box_colors):
            legend_handles.append(plt.Rectangle((0, 0), 0.8, 0.8, fc=color, ec='black', linewidth=0.5, alpha=0.5))
            legend_labels.append(f'{group}: {mean_val:.1f}% (n={n_points}, C={compactness:.1f})')
        
        # Add legend below the plot
        legend = ax.legend(legend_handles, legend_labels, 
                         loc='upper center',
                         bbox_to_anchor=(0.5, -0.15),  # Below the plot
                         ncol=min(4, len(legend_labels)),  # Maximum 4 columns
                         frameon=True,
                         framealpha=0.9,
                         fancybox=True,
                         shadow=True,
                         borderpad=0.5,
                         handlelength=1.2,
                         handletextpad=0.3,
                         columnspacing=0.8,
                         fontsize='small')
        
        # Adjust layout to make room for legend below
        new_fig.tight_layout(rect=[0, 0.05, 1, 0.95])  # Leave space at bottom for legend
        
        # Set up the rest of the UI
        toolbar = NavigationToolbar(canvas, dlg)
        container_layout.addWidget(toolbar)
        container_layout.addWidget(canvas)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Store reference to prevent garbage collection
        if not hasattr(self, '_popup_refs'):
            self._popup_refs = []
        self._popup_refs.append((dlg, canvas, new_fig))
        
        # Show the dialog
        dlg.show()
        
    def open_popout(self, figure, title="Plot"):
        # For aggregate box plots, use the aggregate popup handler
        if title == "Aggregate Box Plot" and hasattr(self, 'analysis_results'):
            self._open_boxplot_popout(figure, title)
            return
        # For current image box plot, use a separate handler
        elif title == "Box Plot" and hasattr(self, 'analysis_results'):
            self._open_current_image_boxplot_popout(figure, title)
            return
            
        # Original popout code for other plot types
        from matplotlib.legend import Legend as Legend
        from matplotlib.axes import Axes
        from matplotlib.lines import Line2D
        from matplotlib.patches import Polygon, Rectangle, PathPatch
        from matplotlib.collections import PathCollection, LineCollection, PatchCollection
        import numpy as np
        
        # Create a new dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} (Pop-out)")
        dlg.setMinimumSize(800, 600)
        
        # Create layout
        layout = QVBoxLayout(dlg)
        
        # Create a scroll area for the plot
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create a container widget for the scroll area
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(5)
        
        # Create a new figure with the same size as original
        new_fig = plt.Figure(figsize=figure.get_size_inches(), dpi=figure.dpi)
        new_fig.set_facecolor(figure.get_facecolor())
        
        # Create canvas and set size policy
        canvas = FigureCanvas(new_fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Get the current figure manager to access the renderer
        from matplotlib.backends.backend_qt5agg import FigureManagerQT
        manager = FigureManagerQT(canvas, 0)
        
        # Copy all axes from the original figure
        for ax in figure.get_axes():
            try:
                # Create new axes with same position and projection
                pos = ax.get_position()
                new_ax = new_fig.add_axes([pos.x0, pos.y0, pos.width, pos.height],
                                       projection=ax.get_projection() if hasattr(ax, 'get_projection') else None)
                
                # Copy basic properties
                new_ax.set_xlabel(ax.get_xlabel())
                new_ax.set_ylabel(ax.get_ylabel())
                new_ax.set_title(ax.get_title())
                new_ax.set_xlim(ax.get_xlim())
                new_ax.set_ylim(ax.get_ylim())
                new_ax.grid(ax.get_gridspec() is not None)
                
                # Store artists to add after all others (for z-ordering)
                artists_to_add = []
                
                # First pass: collect all artists
                for artist in ax.get_children():
                    # Skip axes and legend objects
                    if isinstance(artist, (Axes, Legend)):
                        continue
                    
                    try:
                        # For Line2D objects (lines, markers, etc.)
                        if isinstance(artist, Line2D):
                            x, y = artist.get_data()
                            if x is not None and y is not None and len(x) > 0 and len(y) > 0:
                                new_artist = Line2D(x, y, 
                                                 color=artist.get_color(),
                                                 linestyle=artist.get_linestyle(),
                                                 linewidth=artist.get_linewidth(),
                                                 marker=artist.get_marker(),
                                                 markersize=artist.get_markersize(),
                                                 label=artist.get_label(),
                                                 alpha=artist.get_alpha(),
                                                 zorder=artist.get_zorder())
                                artists_to_add.append((new_artist, artist.get_zorder()))
                        
                        # For PathCollections (scatter plots, histograms, etc.)
                        elif isinstance(artist, PathCollection):
                            offsets = artist.get_offsets()
                            if len(offsets) > 0:
                                # Get properties from the original artist
                                facecolors = artist.get_facecolor()
                                edgecolors = artist.get_edgecolor()
                                sizes = artist.get_sizes()
                                linewidths = artist.get_linewidths()
                                
                                # Create new scatter plot
                                new_artist = new_ax.scatter(offsets[:, 0], offsets[:, 1],
                                                        c=facecolors,
                                                        s=sizes,
                                                        edgecolors=edgecolors,
                                                        linewidths=linewidths,
                                                        alpha=artist.get_alpha(),
                                                        zorder=artist.get_zorder())
                                artists_to_add.append((new_artist, artist.get_zorder()))
                        
                        # For PathPatch objects (main boxes in boxplots)
                        elif isinstance(artist, PathPatch):
                            try:
                                new_patch = Polygon(artist.get_path().vertices,
                                                    closed=True,
                                                    facecolor=artist.get_facecolor(),
                                                    edgecolor=artist.get_edgecolor(),
                                                    linewidth=artist.get_linewidth(),
                                                    zorder=artist.get_zorder())
                                artists_to_add.append((new_patch, artist.get_zorder()))
                            except Exception as _:
                                pass
                        # For LineCollections (error bars, etc.)
                        elif hasattr(artist, 'get_segments'):
                            segments = artist.get_segments()
                            if len(segments) > 0:
                                linewidths = artist.get_linewidths()
                                if not linewidths:
                                    linewidths = [1.0]
                                
                                # Create a new LineCollection
                                new_artist = LineCollection(segments,
                                                         linewidths=linewidths[0],
                                                         colors=artist.get_colors(),
                                                         linestyles=artist.get_linestyle(),
                                                         alpha=artist.get_alpha(),
                                                         zorder=artist.get_zorder())
                                artists_to_add.append((new_artist, artist.get_zorder()))
                        
                        # For Patches (boxes in box plots, etc.)
                        elif hasattr(artist, 'get_paths'):
                            paths = artist.get_paths()
                            if paths:
                                # Handle box plot boxes specifically
                                if hasattr(artist, '_boxes'):  # This is a box plot
                                    for box in artist['boxes']:
                                        path = box.get_path()
                                        vertices = path.vertices
                                        if vertices.size > 0:
                                            patch = Polygon(vertices,
                                                         closed=True,
                                                         facecolor=box.get_facecolor(),
                                                         edgecolor=box.get_edgecolor(),
                                                         linewidth=box.get_linewidth(),
                                                         zorder=box.get_zorder())
                                            artists_to_add.append((patch, box.get_zorder()))
                                
                                # Handle other path-based artists
                                for path in paths:
                                    if path.vertices.size > 0:
                                        patch = Polygon(path.vertices,
                                                     closed=path.closed,
                                                     facecolor=artist.get_facecolor(),
                                                     edgecolor=artist.get_edgecolor(),
                                                     linewidth=artist.get_linewidth(),
                                                     zorder=artist.get_zorder())
                                        artists_to_add.append((patch, artist.get_zorder()))
                    
                    except Exception as e:
                        print(f"Could not copy artist {artist.__class__.__name__}: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Add all collected artists in z-order
                for artist, _ in sorted(artists_to_add, key=lambda x: x[1]):
                    if isinstance(artist, Line2D):
                        new_ax.add_line(artist)
                    else:
                        new_ax.add_artist(artist)
                
                # Copy legend if it exists
                if ax.get_legend() is not None:
                    handles, labels = ax.get_legend_handles_labels()
                    if handles and labels:
                        new_ax.legend(handles, labels)
                
                # Copy tick parameters
                new_ax.tick_params(axis='both', which='both',
                                 direction=ax.xaxis.get_tick_params().get('direction', 'out'),
                                 length=ax.xaxis.get_tick_params().get('length', 4),
                                 width=ax.xaxis.get_tick_params().get('width', 0.5))
                
                # Copy spines and facecolor
                new_ax.set_facecolor(ax.get_facecolor())
                
                # Copy axis scale (log/linear)
                new_ax.set_xscale(ax.get_xscale())
                new_ax.set_yscale(ax.get_yscale())
                
            except Exception as e:
                print(f"Error copying axes: {e}")
                import traceback
                traceback.print_exc()
        
        # Add toolbar
        toolbar = NavigationToolbar(canvas, dlg)
        
        # Add widgets to layout
        container_layout.addWidget(toolbar)
        container_layout.addWidget(canvas)
        
        # Set up scroll area
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Store reference to prevent garbage collection
        if not hasattr(self, '_popup_refs'):
            self._popup_refs = []
        self._popup_refs.append((dlg, canvas, new_fig, manager))
        
        # Draw the canvas after a short delay to ensure proper rendering
        def delayed_draw():
            canvas.draw()
            dlg.show()
        
        # Use a single-shot timer to ensure the dialog is shown before drawing
        QTimer.singleShot(50, delayed_draw)

    def initUI(self):
        main_layout = QHBoxLayout(self)
        # Set stretch factors to make the left panel resizable
        main_layout.setStretch(0, 1)  # Left panel
        main_layout.setStretch(1, 3)  # Right panel (plots area)
        
        # Wrap the settings panel in a scroll area to keep parameters visible when window is small
        settings_container = QWidget()
        settings_container.setMinimumWidth(300)  # Minimum width to prevent becoming too narrow
        settings_container.setMaximumWidth(600)  # Maximum width to prevent becoming too wide
        left_layout = QVBoxLayout(settings_container)
        
        # Create scroll area for settings
        scroll_settings = QScrollArea()
        scroll_settings.setWidgetResizable(True)
        scroll_settings.setWidget(settings_container)
        scroll_settings.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_settings.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_settings.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Set a style sheet for the scroll area to ensure scrollbars are visible in dark mode
        scroll_settings.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:horizontal, QScrollBar:vertical {
                background: #2d2d2d;
                height: 12px;
                width: 12px;
                margin: 0px;
                border: none;
            }
            QScrollBar::handle:horizontal, QScrollBar::handle:vertical {
                background: #606060;
                min-width: 20px;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover, QScrollBar::handle:vertical:hover {
                background: #707070;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                width: 0px;
                height: 0px;
            }
        """)

        group_assign_layout = QHBoxLayout()
        group_assign_layout.addWidget(QLabel("Group:"))
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Enter group label")
        group_assign_layout.addWidget(self.group_edit)
        assign_btn = QPushButton("Apply to Selected")
        assign_btn.clicked.connect(self.assign_group_to_selected)
        group_assign_layout.addWidget(assign_btn)
        left_layout.addLayout(group_assign_layout)

        self.image_group = QGroupBox("Image Selection")
        image_layout = QVBoxLayout()
        self.image_list_widget = QListWidget()
        self.image_list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.image_list_widget.setFixedHeight(150)
        self.image_list_widget.currentRowChanged.connect(self.update_plot_display)
        self.image_list_widget.currentRowChanged.connect(self.update_histogram_plot)
        self.image_list_widget.currentRowChanged.connect(self.update_current_boxplot)
        add_button = QPushButton("Add Images")
        add_button.clicked.connect(self.add_images)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_image)
        reset_button = QPushButton("Reset Tab")
        reset_button.clicked.connect(self.reset_tab)
        image_buttons_layout = QHBoxLayout()
        image_buttons_layout.addWidget(add_button)
        image_buttons_layout.addWidget(remove_button)
        image_buttons_layout.addWidget(reset_button)
        image_layout.addWidget(self.image_list_widget)
        image_layout.addLayout(image_buttons_layout)
        self.image_group.setLayout(image_layout)
        left_layout.addWidget(self.image_group)

        self.params_group = QGroupBox("Bleed-Through Parameters")
        params_layout = QFormLayout()
        self.donor_model_label = QLabel("N/A")
        self.donor_coeffs_label = QLabel("N/A")
        self.acceptor_model_label = QLabel("N/A")
        self.acceptor_coeffs_label = QLabel("N/A")
        params_layout.addRow("Donor (S1) Model:", self.donor_model_label)
        params_layout.addRow("Donor (S1) Coeffs:", self.donor_coeffs_label)
        params_layout.addRow("Acceptor (S2) Model:", self.acceptor_model_label)
        params_layout.addRow("Acceptor (S2) Coeffs:", self.acceptor_coeffs_label)
        self.params_group.setLayout(params_layout)
        left_layout.addWidget(self.params_group)

        self.fret_settings_group = QGroupBox("FRET Settings")
        fret_settings_layout = QFormLayout()
        
        self.lower_threshold_spinbox = QDoubleSpinBox()
        default_lt = 0.00 if self.config is None else self.config.get('fret.lower_threshold', 0.00)
        self.lower_threshold_spinbox.setRange(0, 10)
        self.lower_threshold_spinbox.setSingleStep(0.1)
        self.lower_threshold_spinbox.setValue(default_lt)
        if self.config:
            self.lower_threshold_spinbox.valueChanged.connect(lambda v: self.config.set('fret.lower_threshold', float(v)))
        self.lower_threshold_spinbox.setSuffix(" %")
        self.add_info_icon(fret_settings_layout, "Lower Threshold (%):", self.lower_threshold_spinbox, "Set the lower display threshold for efficiency maps.")

        self.upper_threshold_spinbox = QDoubleSpinBox()
        default_ut = 50.0 if self.config is None else self.config.get('fret.upper_threshold', 50.0)
        self.upper_threshold_spinbox.setRange(0, 100)
        self.upper_threshold_spinbox.setSingleStep(1)
        self.upper_threshold_spinbox.setValue(default_ut)
        if self.config:
            self.upper_threshold_spinbox.valueChanged.connect(lambda v: self.config.set('fret.upper_threshold', float(v)))
        self.upper_threshold_spinbox.setSuffix(" %")
        self.add_info_icon(fret_settings_layout, "Upper Threshold (%):", self.upper_threshold_spinbox, "Set the upper display threshold for efficiency maps.")

        self.bg_kernel_spinbox = QDoubleSpinBox()
        default_bg = 50.0 if self.config is None else self.config.get('fret.bg_kernel', 50.0)
        self.bg_kernel_spinbox.setRange(1, 100)
        self.bg_kernel_spinbox.setSingleStep(1)
        self.bg_kernel_spinbox.setValue(default_bg)
        if self.config:
            self.bg_kernel_spinbox.valueChanged.connect(lambda v: self.config.set('fret.bg_kernel', float(v)))
        self.add_info_icon(fret_settings_layout, "Background Kernel Size:", self.bg_kernel_spinbox, "Size of the kernel for local background subtraction.")

        self.gaussian_blur_spinbox = QDoubleSpinBox()
        default_gb = 2.0 if self.config is None else self.config.get('fret.gaussian_blur', 2.0)
        self.gaussian_blur_spinbox.setRange(0, 10)
        self.gaussian_blur_spinbox.setSingleStep(0.1)
        self.gaussian_blur_spinbox.setValue(default_gb)
        if self.config:
            self.gaussian_blur_spinbox.valueChanged.connect(lambda v: self.config.set('fret.gaussian_blur', float(v)))
        self.add_info_icon(fret_settings_layout, "Gaussian Blur Sigma:", self.gaussian_blur_spinbox, "Sigma for Gaussian blur. Set to 0 to disable.")

        # PixFRET Thresholding Controls
        self.pixfret_threshold_checkbox = QCheckBox("Enable PixFRET Thresholding")
        self.pixfret_threshold_factor_spinbox = QDoubleSpinBox()
        self.pixfret_threshold_factor_spinbox.setRange(0.1, 10.0)
        self.pixfret_threshold_factor_spinbox.setSingleStep(0.1)
        self.pixfret_threshold_factor_spinbox.setValue(1.0)
        self.pixfret_threshold_factor_spinbox.setEnabled(False)
        self.pixfret_threshold_checkbox.toggled.connect(self.pixfret_threshold_factor_spinbox.setEnabled)
        fret_settings_layout.addRow(self.pixfret_threshold_checkbox)
        self.add_info_icon(fret_settings_layout, "Threshold Factor:", self.pixfret_threshold_factor_spinbox, "Multiplier for PixFRET threshold calculation.")
        if self.config:
            pixfret_enabled = self.config.get('fret.pixfret_threshold_enabled', False)
            self.pixfret_threshold_checkbox.setChecked(pixfret_enabled)
            self.pixfret_threshold_factor_spinbox.setEnabled(pixfret_enabled)
            default_factor = self.config.get('fret.pixfret_threshold_factor', 1.0)
            self.pixfret_threshold_factor_spinbox.setValue(default_factor)
            self.pixfret_threshold_checkbox.toggled.connect(lambda state: self.config.set('fret.pixfret_threshold_enabled', state))
            self.pixfret_threshold_factor_spinbox.valueChanged.connect(lambda value: self.config.set('fret.pixfret_threshold_factor', float(value)))

        # Donor/Acceptor Ratio Threshold
        self.ratio_threshold_spinbox = QSpinBox()
        self.ratio_threshold_spinbox.setRange(1, 1000)
        default_ratio = 100 if self.config is None else int(self.config.get('fret.donor_acceptor_ratio_threshold', 100))
        self.ratio_threshold_spinbox.setValue(default_ratio)
        if self.config:
            self.ratio_threshold_spinbox.valueChanged.connect(lambda v: self.config.set('fret.donor_acceptor_ratio_threshold', int(v)))
        self.add_info_icon(
            fret_settings_layout,
            "D/A Ratio Threshold:",
            self.ratio_threshold_spinbox,
            "Pixels with donor/acceptor mean ratio greater than this value or less than its reciprocal will be excluded."
        )
        # Label to show number of excluded cells for current image
        self.excluded_cells_ratio_label = QLabel("Excluded Cells: 0")
        fret_settings_layout.addRow("Excluded Cells:", self.excluded_cells_ratio_label)

        # Cell Efficiency Threshold Controls
        self.cell_eff_threshold_checkbox = QCheckBox("Enable Cell Efficiency Threshold")
        self.cell_eff_threshold_checkbox.setChecked(False)
        self.cell_eff_lower_spinbox = QDoubleSpinBox()
        self.cell_eff_lower_spinbox.setRange(0, 100)
        self.cell_eff_lower_spinbox.setSingleStep(1)
        self.cell_eff_lower_spinbox.setValue(0)
        self.cell_eff_upper_spinbox = QDoubleSpinBox()
        self.cell_eff_upper_spinbox.setRange(0, 100)
        self.cell_eff_upper_spinbox.setSingleStep(1)
        self.cell_eff_upper_spinbox.setValue(50)
        # Disable until checkbox checked
        self.cell_eff_lower_spinbox.setEnabled(False)
        self.cell_eff_upper_spinbox.setEnabled(False)
        self.cell_eff_threshold_checkbox.toggled.connect(self.cell_eff_lower_spinbox.setEnabled)
        self.cell_eff_threshold_checkbox.toggled.connect(self.cell_eff_upper_spinbox.setEnabled)
        if self.config:
            self.cell_eff_threshold_checkbox.toggled.connect(lambda state: self.config.set('fret.cell_eff_threshold_enabled', state))
            self.cell_eff_lower_spinbox.valueChanged.connect(lambda v: self.config.set('fret.cell_eff_lower', float(v)))
            self.cell_eff_upper_spinbox.valueChanged.connect(lambda v: self.config.set('fret.cell_eff_upper', float(v)))
        fret_settings_layout.addRow(self.cell_eff_threshold_checkbox)
        self.add_info_icon(fret_settings_layout, "Cell Lower (%):", self.cell_eff_lower_spinbox, "Exclude cells whose mean efficiency is below this value.")
        self.add_info_icon(fret_settings_layout, "Cell Upper (%):", self.cell_eff_upper_spinbox, "Exclude cells whose mean efficiency is above this value.")

        self.fret_settings_group.setLayout(fret_settings_layout)
        left_layout.addWidget(self.fret_settings_group)

        self.formula_group = QGroupBox("FRET Formulas")
        formula_layout = QVBoxLayout()
        self.formula_checkboxes = {
            "FRET/Donor": QCheckBox("FRET/Donor"),
            "FRET/Acceptor": QCheckBox("FRET/Acceptor"),
            "Xia": QCheckBox("Xia et al. (FRET/sqrt(D*A))"),
            "Gordon": QCheckBox("Gordon et al. (FRET/(D*A))"),
            "PixFRET": QCheckBox("PixFRET (FRET/(D+FRET))")
        }
        for name, checkbox in self.formula_checkboxes.items():
            checked = True if self.config is None else self.config.get(f'fret.formulas.{name}', True)
            checkbox.setChecked(checked)
            checkbox.stateChanged.connect(self.update_plot_display)
            if self.config:
                checkbox.stateChanged.connect(lambda state, n=name: self.config.set(f'fret.formulas.{n}', bool(state)))
            formula_layout.addWidget(checkbox)
        self.formula_group.setLayout(formula_layout)
        left_layout.addWidget(self.formula_group)

        self.analysis_group = QGroupBox("Analysis")
        analysis_layout = QVBoxLayout()
        self.analyze_all_checkbox = QCheckBox("Analyze all images in the list")
        self.analyze_all_checkbox.setChecked(True)
        self.save_efficiencies_checkbox = QCheckBox("Save Efficiency Images")
        info_save_label = QLabel("Note: To save images, check formulas and click 'Run FRET Analysis'.")
        info_save_label.setWordWrap(True)
        info_save_label.setStyleSheet("font-size: 10pt; color: gray;")
        analysis_layout.addWidget(self.analyze_all_checkbox)
        analysis_layout.addWidget(self.save_efficiencies_checkbox)
        analysis_layout.addWidget(info_save_label)
        self.run_button = QPushButton("Run FRET Analysis")
        self.run_button.setEnabled(False)
        self.run_button.setToolTip("Complete bleedthrough parameter calibration first")
        self.run_button.clicked.connect(self.run_analysis)
        analysis_layout.addWidget(self.run_button)
        self.analysis_group.setLayout(analysis_layout)
        left_layout.addWidget(self.analysis_group)

        left_layout.addStretch()
        main_layout.addWidget(scroll_settings)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_tabs = QTabWidget()
        right_layout.addWidget(right_tabs)

        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        app = QApplication.instance()
        palette = app.palette()
        is_dark_theme = palette.window().color().lightness() < 128
        self.current_theme = 'dark' if is_dark_theme else 'light'
        # Initialize with default theme, will be updated by update_plot_themes
        self.figure = plt.figure(facecolor='black' if is_dark_theme else 'white')
        self.canvas = FigureCanvas(self.figure)
        # Set explicit background color for the canvas widget
        self.canvas.setStyleSheet(f"background-color: {'#000000' if is_dark_theme else '#ffffff'};")
        self.toolbar = NavigationToolbar(self.canvas, self)
        # Force update of all plot themes
        if hasattr(self, 'update_plot_themes'):
            self.update_plot_themes()
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)
        right_tabs.addTab(plot_tab, "View")

        stats_container_tab = QWidget()
        stats_container_layout = QVBoxLayout(stats_container_tab)
        stats_tabs = QTabWidget()
        stats_container_layout.addWidget(stats_tabs)
        right_tabs.addTab(stats_container_tab, "Process")

        current_stats_container = QWidget()
        current_stats_container_layout = QVBoxLayout(current_stats_container)
        self.current_inner_tabs = QTabWidget()
        current_stats_container_layout.addWidget(self.current_inner_tabs)

        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        self.current_stats_table = QTableWidget()
        self.current_stats_table.setColumnCount(6)
        self.current_stats_table.setHorizontalHeaderLabels(["Formula", "Avg (All)", "Avg (btw thresh %)", "% < Lower", "% > Upper", "# NZ Pixels"])
        self.current_stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        summary_layout.addWidget(self.current_stats_table)
        self.binned_stats_table = QTableWidget()
        column_headers = ["Label", "Formula", "Avg E (All)", "Avg E (btw thresh %)", "% < Lower", "% > Upper", "# Pixels"]
        self.binned_stats_table.setColumnCount(len(column_headers))
        self.binned_stats_table.setHorizontalHeaderLabels(column_headers)
        self.binned_stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        summary_layout.addWidget(QLabel("Efficiency per labelled cell:"))
        summary_layout.addWidget(self.binned_stats_table)
        self.current_inner_tabs.addTab(summary_tab, "Summary")

        # Create the histogram tab with a scroll area
        histogram_scroll = QScrollArea()
        histogram_scroll.setWidgetResizable(True)
        histogram_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        histogram_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create a container widget for the scroll area
        scroll_widget = QWidget()
        scroll_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        histogram_scroll.setWidget(scroll_widget)
        
        # Create the main layout for the scroll widget
        hist_layout = QVBoxLayout(scroll_widget)
        hist_layout.setContentsMargins(5, 5, 5, 5)
        hist_layout.setSpacing(10)
        
        # Create the actual content widget
        histogram_tab = QWidget()
        hist_layout.addWidget(histogram_tab)
        
        # Create the layout for the histogram tab content
        hist_content_layout = QVBoxLayout(histogram_tab)
        hist_content_layout.setContentsMargins(5, 5, 5, 5)
        hist_content_layout.setSpacing(5)
        ctl_layout = QHBoxLayout()
        ctl_layout.addWidget(QLabel("Formula:"))
        self.hist_formula_combo = QComboBox()
        self.hist_formula_combo.addItems(self.formula_checkboxes.keys())
        self.hist_formula_combo.currentIndexChanged.connect(self.update_histogram_plot)
        self.hist_formula_combo.currentIndexChanged.connect(self.update_current_boxplot)
        ctl_layout.addWidget(self.hist_formula_combo)
        self.excluded_cells_label = QLabel("Excluded Cells: 0")
        ctl_layout.addWidget(self.excluded_cells_label)
        ctl_layout.addStretch()
        hist_content_layout.addLayout(ctl_layout)
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Title:"))
        self.hist_title_edit = QLineEdit("Current Image Histogram")
        self.hist_title_edit.editingFinished.connect(self.update_histogram_plot)
        title_layout.addWidget(self.hist_title_edit)
        title_layout.addStretch()
        hist_content_layout.addLayout(title_layout)
        self.hist_figure = plt.figure(figsize=(4,3), facecolor='black' if self.current_theme == 'dark' else 'white')
        self.hist_canvas = FigureCanvas(self.hist_figure)
        self.hist_canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'};");
        pop_hist_btn = QToolButton()
        pop_hist_btn.setText("↗")
        pop_hist_btn.setToolTip("Pop-out histogram")
        pop_hist_btn.clicked.connect(lambda: self.open_popout(self.hist_figure, "Histogram"))
        hist_content_layout.addWidget(pop_hist_btn, alignment=Qt.AlignRight)
        toolbar_hist = NavigationToolbar(self.hist_canvas, self)
        hist_content_layout.addWidget(toolbar_hist)
        hist_content_layout.addWidget(self.hist_canvas)
        box_ctl_layout = QHBoxLayout()
        box_ctl_layout.addWidget(QLabel("Box Y-label:"))
        self.box_y_label_edit = QLineEdit("% FRET Efficiency")
        self.box_y_label_edit.editingFinished.connect(self.update_current_boxplot)
        box_ctl_layout.addWidget(self.box_y_label_edit)
        box_ctl_layout.addStretch()
        hist_content_layout.addLayout(box_ctl_layout)
        self.box_figure = plt.figure(figsize=(4,3), facecolor='black' if self.current_theme == 'dark' else 'white')
        self.box_canvas = FigureCanvas(self.box_figure)
        self.box_canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'};");
        pop_box_btn = QToolButton()
        pop_box_btn.setText("↗")
        pop_box_btn.setToolTip("Pop-out box plot")
        pop_box_btn.clicked.connect(lambda: self.open_popout(self.box_figure, "Box Plot"))
        hist_content_layout.addWidget(pop_box_btn, alignment=Qt.AlignRight)
        toolbar_box = NavigationToolbar(self.box_canvas, self)
        hist_content_layout.addWidget(toolbar_box)
        hist_content_layout.addWidget(self.box_canvas)
        
        # Add stretch to push content to the top
        hist_content_layout.addStretch(1)
        histogram_tab.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        scroll_widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        scroll_widget.adjustSize()
        self.current_inner_tabs.addTab(histogram_scroll, "Histogram && Box Plot")
        
        # Distribution Analysis Tab
        fourier_tab = QWidget()
        fourier_layout = QVBoxLayout(fourier_tab)
        
        # Enable/disable checkbox
        self.distribution_enabled_checkbox = QCheckBox("Enable Distribution Analysis")
        self.distribution_enabled_checkbox.setChecked(False)
        self.distribution_enabled_checkbox.stateChanged.connect(self.on_distribution_enabled_changed)
        fourier_layout.addWidget(self.distribution_enabled_checkbox)
        
        # Top controls
        fourier_controls = QHBoxLayout()
        
        # Formula selection - use the same formulas as in the FRET tab
        fourier_controls.addWidget(QLabel("Efficiency Formula:"))
        self.fourier_formula_combo = QComboBox()
        
        # Connect to the main formula combo box to keep them in sync
        self.fourier_formula_combo.currentIndexChanged.connect(self.on_fourier_formula_changed)
        fourier_controls.addWidget(self.fourier_formula_combo)
        
        # Add GMM components control
        fourier_controls.addWidget(QLabel("Max Components:"))
        self.max_components_spinbox = QSpinBox()
        self.max_components_spinbox.setRange(1, 5)
        self.max_components_spinbox.setValue(3)
        self.max_components_spinbox.setToolTip("Maximum number of Gaussian components to fit")
        fourier_controls.addWidget(self.max_components_spinbox)
        
        # Add update button to refresh GMM analysis
        self.update_gmm_btn = QPushButton("Update Analysis")
        self.update_gmm_btn.clicked.connect(self.update_cell_analysis)
        fourier_controls.addWidget(self.update_gmm_btn)
        
        fourier_layout.addLayout(fourier_controls)
        
        # Initialize distribution analysis state
        self.distribution_enabled = False
        self.fourier_formula_combo.setEnabled(False)
        self.max_components_spinbox.setEnabled(False)
        self.update_gmm_btn.setEnabled(False)
        
        # Initialize with available formulas from the main tab
        self.update_fourier_formula_list()
        
        # Cell selection info
        self.selected_cell_label = QLabel("Selected Cell: None")
        fourier_controls.addStretch()
        fourier_controls.addWidget(self.selected_cell_label)
        
        fourier_layout.addLayout(fourier_controls)
        
        # Splitter for image and plots
        splitter = QSplitter(Qt.Vertical)
        
        # Image display area
        self.fourier_image_figure = plt.Figure(figsize=(6, 6), facecolor='black' if self.current_theme == 'dark' else 'white')
        self.fourier_image_canvas = FigureCanvas(self.fourier_image_figure)
        self.fourier_image_canvas.setMinimumHeight(300)
        self.fourier_image_canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'};")
        self.fourier_image_canvas.mpl_connect('button_press_event', self.on_cell_click)  # Reconnect click handler for GMM cell selection
        splitter.addWidget(self.fourier_image_canvas)
        
        # Distribution and Histogram plots
        plots_widget = QWidget()
        plots_layout = QHBoxLayout(plots_widget)
        
        # GMM Decomposition plot
        self.fft_figure = plt.Figure(figsize=(5, 3), facecolor='black' if self.current_theme == 'dark' else 'white')
        self.fft_canvas = FigureCanvas(self.fft_figure)
        self.fft_canvas.setToolTip("Gaussian Mixture Model decomposition of cell efficiency distribution")
        self.fft_canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'};")
        plots_layout.addWidget(self.fft_canvas)
        
        # Cell histogram plot
        self.cell_hist_figure = plt.Figure(figsize=(4, 3), facecolor='black' if self.current_theme == 'dark' else 'white')
        self.cell_hist_canvas = FigureCanvas(self.cell_hist_figure)
        self.cell_hist_canvas.setToolTip("Histogram of cell efficiency values")
        self.cell_hist_canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'};")
        plots_layout.addWidget(self.cell_hist_canvas)
        
        splitter.addWidget(plots_widget)
        fourier_layout.addWidget(splitter)
        
        # Add navigation toolbars
        fourier_toolbar = NavigationToolbar(self.fourier_image_canvas, self)
        fourier_layout.addWidget(fourier_toolbar)
        
        # Initialize class variables
        self.current_cell_id = None
        self.current_efficiency_map = None
        self.cell_masks = {}
        
        # Connect signals
        if hasattr(self, 'analysis_completed'):
            self.analysis_completed.connect(self.on_analysis_completed)
        
        # Connect to the image selection changed signal
        if hasattr(self, 'image_list_widget'):
            self.image_list_widget.currentItemChanged.connect(self.on_image_selection_changed)
        
        self.current_inner_tabs.addTab(fourier_tab, "Distribution Analysis")
        
        stats_tabs.addTab(current_stats_container, "Current Image")

        aggregate_stats_tab = QWidget()
        aggregate_stats_layout = QVBoxLayout(aggregate_stats_tab)
        agg_controls_layout = QHBoxLayout()
        agg_controls_layout.addWidget(QLabel("Display statistics for formula:"))
        self.aggregate_formula_combo = QComboBox()
        self.aggregate_formula_combo.addItems(self.formula_checkboxes.keys())
        # Connect formula combo box changes to update all relevant plots and tables
        self.aggregate_formula_combo.currentIndexChanged.connect(self.update_aggregate_stats_table)
        self.aggregate_formula_combo.currentIndexChanged.connect(self.update_aggregate_histogram_plot)
        self.aggregate_formula_combo.currentIndexChanged.connect(self.update_aggregate_boxplot)
        # Don't update representative images when formula changes - now manual with Find Rep Image button
        # self.aggregate_formula_combo.currentIndexChanged.connect(self.update_representative_images)  # Removed automatic update
        agg_controls_layout.addWidget(self.aggregate_formula_combo)
        agg_controls_layout.addStretch()
        aggregate_stats_layout.addLayout(agg_controls_layout)
        self.agg_tabs = QTabWidget()
        aggregate_stats_layout.addWidget(self.agg_tabs)
        agg_summary_tab = QWidget()
        agg_summary_layout = QVBoxLayout(agg_summary_tab)
        self.aggregate_stats_table = QTableWidget()
        self.aggregate_stats_table.setColumnCount(7)
        self.aggregate_stats_table.setHorizontalHeaderLabels([
            "Image", "Group", "Avg E (%)", "Avg E (btw thresh %)", "% Below Low", "% Above High", "Non-Zero Pixels"
        ])
        self.aggregate_stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        export_btn = QToolButton()
        export_btn.setText("📄 Export CSV")
        export_btn.setToolTip("Export summary statistics to CSV")
        export_btn.clicked.connect(self.export_summary_to_csv)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(export_btn)
        agg_summary_layout.addWidget(self.aggregate_stats_table)
        agg_summary_layout.addLayout(btn_layout)
        self.agg_tabs.addTab(agg_summary_tab, "Summary")
        # Create the aggregate plots tab with a scroll area
        agg_plots_scroll = QScrollArea()
        agg_plots_scroll.setWidgetResizable(True)
        agg_plots_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        agg_plots_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create a container widget for the scroll area
        agg_scroll_widget = QWidget()
        agg_scroll_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        agg_plots_scroll.setWidget(agg_scroll_widget)
        
        # Create the main layout for the scroll widget
        agg_plots_layout = QVBoxLayout(agg_scroll_widget)
        agg_plots_layout.setContentsMargins(5, 5, 5, 5)
        agg_plots_layout.setSpacing(10)
        
        # Create the actual content widget
        agg_plots_tab = QWidget()
        agg_plots_layout.addWidget(agg_plots_tab)
        
        # Create the layout for the plots tab content
        agg_content_layout = QVBoxLayout(agg_plots_tab)
        agg_content_layout.setContentsMargins(5, 5, 5, 5)
        agg_content_layout.setSpacing(5)
        
        # Histogram controls (moved above the plot)
        hist_controls_layout = QVBoxLayout()
        
        # Histogram title
        agg_hist_title_l = QHBoxLayout()
        agg_hist_title_l.addWidget(QLabel("Hist Title:"))
        self.agg_hist_title_edit = QLineEdit("Aggregate Histogram")
        self.agg_hist_title_edit.editingFinished.connect(self.update_aggregate_histogram_plot)
        agg_hist_title_l.addWidget(self.agg_hist_title_edit)
        agg_hist_title_l.addStretch()
        hist_controls_layout.addLayout(agg_hist_title_l)
        
        # Error type selection
        error_type_layout = QHBoxLayout()
        error_type_layout.addWidget(QLabel("Error Type:"))
        self.error_type_group = QButtonGroup(self)
        self.sem_radio = QRadioButton("SEM")
        self.sd_radio = QRadioButton("SD")
        self.sem_radio.setChecked(True)
        self.error_type_group.addButton(self.sem_radio)
        self.error_type_group.addButton(self.sd_radio)
        self.sem_radio.toggled.connect(self.update_aggregate_histogram_plot)
        self.sd_radio.toggled.connect(self.update_aggregate_histogram_plot)
        error_type_layout.addWidget(self.sem_radio)
        error_type_layout.addWidget(self.sd_radio)
        error_type_layout.addStretch()
        hist_controls_layout.addLayout(error_type_layout)
        
        # Add histogram controls to main layout
        agg_content_layout.addLayout(hist_controls_layout)
        
        # Histogram plot with increased height
        self.agg_hist_figure = plt.figure(figsize=(5, 5), facecolor='black' if self.current_theme == 'dark' else 'white')
        self.agg_hist_canvas = FigureCanvas(self.agg_hist_figure)
        self.agg_hist_canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'};")
        
        pop_agg_hist = QToolButton()
        pop_agg_hist.setText("↗")
        pop_agg_hist.setToolTip("Pop-out histogram")
        pop_agg_hist.clicked.connect(lambda: self._open_histogram_popout(self.agg_hist_figure, "Aggregate Histogram"))
        
        save_hist = QToolButton()
        save_hist.setText("Save 💾")
        save_hist.setToolTip("Save histogram as high-res image")
        save_hist.clicked.connect(lambda: self.save_plot(self.agg_hist_figure, "histogram"))
        
        hist_header = QHBoxLayout()
        hist_header.addStretch()
        hist_header.addWidget(save_hist)
        hist_header.addWidget(pop_agg_hist)
        
        agg_content_layout.addLayout(hist_header)
        agg_content_layout.addWidget(NavigationToolbar(self.agg_hist_canvas, self))
        agg_content_layout.addWidget(self.agg_hist_canvas)
        
        # Add some spacing between plots
        agg_content_layout.addSpacing(20)
        
        # Box plot with increased height (title will be added below the plot)
        self.agg_box_figure = plt.figure(figsize=(5, 5), facecolor='black' if self.current_theme == 'dark' else 'white')
        self.agg_box_canvas = FigureCanvas(self.agg_box_figure)
        self.agg_box_canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'};")
        
        pop_agg_box = QToolButton()
        pop_agg_box.setText("↗")
        pop_agg_box.setToolTip("Pop-out box plot")
        pop_agg_box.clicked.connect(lambda: self.open_popout(self.agg_box_figure, "Aggregate Box Plot"))
        
        save_box = QToolButton()
        save_box.setText("Save 💾")
        save_box.setToolTip("Save box plot as high-res image")
        save_box.clicked.connect(lambda: self.save_plot(self.agg_box_figure, "boxplot"))
        
        box_header = QHBoxLayout()
        box_header.addStretch()
        box_header.addWidget(save_box)
        box_header.addWidget(pop_agg_box)
        
        agg_content_layout.addLayout(box_header)
        agg_content_layout.addWidget(NavigationToolbar(self.agg_box_canvas, self))
        agg_content_layout.addWidget(self.agg_box_canvas)
        
        # Box plot controls (moved below the plot)
        box_controls_layout = QVBoxLayout()
        
        # Box plot title
        agg_box_title_l = QHBoxLayout()
        agg_box_title_l.addWidget(QLabel("Box Title:"))
        self.agg_box_title_edit = QLineEdit("Aggregate Box Plot")
        self.agg_box_title_edit.editingFinished.connect(self.update_aggregate_boxplot)
        agg_box_title_l.addWidget(self.agg_box_title_edit)
        agg_box_title_l.addStretch()
        box_controls_layout.addLayout(agg_box_title_l)
        
        # Y-label control
        agg_box_ctl = QHBoxLayout()
        agg_box_ctl.addWidget(QLabel("Box Y-label:"))
        self.agg_box_y_label_edit = QLineEdit("% FRET Efficiency")
        self.agg_box_y_label_edit.editingFinished.connect(self.update_aggregate_boxplot)
        agg_box_ctl.addWidget(self.agg_box_y_label_edit)
        agg_box_ctl.addStretch()
        box_controls_layout.addLayout(agg_box_ctl)
        
        # Add box plot controls to main layout
        agg_content_layout.addLayout(box_controls_layout)
        
        # Add stretch to push content to the top
        agg_content_layout.addStretch(1)
        agg_plots_tab.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        agg_scroll_widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        agg_scroll_widget.adjustSize()
        self.agg_tabs.addTab(agg_plots_scroll, "Plots")
        
        # Add Representative Images tab
        rep_images_tab = QWidget()
        rep_images_layout = QVBoxLayout(rep_images_tab)
        
        # Group selection and controls
        group_sel_layout = QHBoxLayout()
        group_sel_layout.addWidget(QLabel("Select Group:"))
        self.rep_group_combo = QComboBox()
        # Remove automatic update on group change
        group_sel_layout.addWidget(self.rep_group_combo)
        
        # Add Find Rep Image button right after the combo box
        self.find_rep_btn = QPushButton("Find Rep Image")
        self.find_rep_btn.setToolTip("Find and display the representative image for the selected group")
        self.find_rep_btn.clicked.connect(self.update_representative_images)
        group_sel_layout.addWidget(self.find_rep_btn)
        
        # Add stretch and export button to layout
        group_sel_layout.addStretch()
        self.export_rep_btn = QPushButton("Export All Frames")
        self.export_rep_btn.clicked.connect(lambda: self.export_rep_btn.setEnabled(False) or self.export_representative_frames(self.current_representative_image, 'all') or self.export_rep_btn.setEnabled(True))
        group_sel_layout.addWidget(self.export_rep_btn)
        
        # Scroll area for images
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.rep_images_container = QWidget()
        self.rep_images_layout = QVBoxLayout(self.rep_images_container)
        
        # Create a grid for the frames
        self.frames_grid = QGridLayout()
        self.frames_grid.setSpacing(10)
        
        # Create frames for each image type
        self.frame_widgets = {}
        frame_types = ['efficiency', 'fret', 'donor', 'acceptor']
        frame_titles = ['FRET Efficiency', 'FRET Channel', 'Donor Channel', 'Acceptor Channel']
        
        for i, (frame_type, title) in enumerate(zip(frame_types, frame_titles)):
            # Create a group box for each frame
            group_box = QGroupBox(title)
            frame_layout = QVBoxLayout()
            
            # Create figure and canvas with consistent DPI
            fig = plt.Figure(figsize=(4, 4), dpi=100)
            canvas = FigureCanvas(fig)
            canvas.setStyleSheet(f"background-color: {'#000000' if self.current_theme == 'dark' else '#ffffff'}")
            
            # Explicitly disable tight_layout
            fig.set_tight_layout(False)
            
            # Add a single subplot that fills the figure
            ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])  # [left, bottom, width, height]
            ax.axis('off')  # Hide the axes initially
            
            # Add to layout
            frame_layout.addWidget(canvas)
            group_box.setLayout(frame_layout)
            
            # Add to grid (2x2 layout)
            row = i // 2
            col = i % 2
            self.frames_grid.addWidget(group_box, row, col)
            
            # Store widgets for later reference
            self.frame_widgets[frame_type] = {
                'figure': fig,
                'canvas': canvas,
                'group_box': group_box
            }
        
        # Add the grid to the layout
        self.rep_images_layout.addLayout(self.frames_grid)
        self.rep_images_layout.addStretch()
        scroll.setWidget(self.rep_images_container)
        
        # Add layouts to main layout
        rep_images_layout.addLayout(group_sel_layout)
        rep_images_layout.addWidget(scroll)
        
        # Initialize with current groups but don't update images yet
        self._update_rep_group_combo()
        
        # Clear any existing representative images
        for frame_type, widgets in self.frame_widgets.items():
            fig = widgets['figure']
            fig.clear()
            ax = fig.add_subplot(111)
            ax.set_facecolor('black' if self.current_theme == 'dark' else 'white')
            ax.axis('off')
            ax.text(0.5, 0.5, "Click 'Find Rep Image' to display", 
                   ha='center', va='center', 
                   color='white' if self.current_theme == 'dark' else 'black',
                   fontsize=12)
            widgets['canvas'].draw()
        
        self.agg_tabs.addTab(rep_images_tab, "Representative Images")
        
        stats_tabs.addTab(aggregate_stats_tab, "All Images")
        main_layout.addWidget(right_panel, 1)

    def update_tab_state(self, enabled):
        self.params_group.setEnabled(enabled)
        self.fret_settings_group.setEnabled(enabled)
        self.formula_group.setEnabled(enabled)
        self.analysis_group.setEnabled(enabled)
        self.toolbar.setEnabled(enabled)
        self.canvas.setEnabled(True)
        if not enabled:
            self.figure.clear()
            self.canvas.draw()

    def add_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Images", "", "Image Files (*.tif *.czi)")
        if files:
            self.add_image_paths(files)

    def _update_rep_group_combo(self):
        """Update the representative images group combo box with current groups."""
        if not hasattr(self, 'rep_group_combo') or not hasattr(self, 'image_groups'):
            return
            
        current_text = self.rep_group_combo.currentText()
        self.rep_group_combo.clear()
        
        # Add all unique groups from the image_groups dictionary
        groups = set(self.image_groups.values())
        if not groups:  # If no groups, add a default one
            groups = {"Default"}
            
        for group in sorted(groups):
            self.rep_group_combo.addItem(group)
        
        # Restore selection if possible
        if current_text and self.rep_group_combo.findText(current_text) >= 0:
            self.rep_group_combo.setCurrentText(current_text)
        elif self.rep_group_combo.count() > 0:
            self.rep_group_combo.setCurrentIndex(0)
            
        # Don't update representative images automatically - wait for button click
        # The images will be updated when the user clicks the 'Find Rep Image' button

    def _update_group_combo(self):
        """Update the group combo box with current groups."""
        current_text = self.group_combo.currentText()
        self.group_combo.clear()
        
        # Add all unique group names
        groups = sorted(set(self.image_groups.values()))
        if not groups:
            self.group_combo.addItem("No groups available")
            self.group_combo.setEnabled(False)
            return
            
        self.group_combo.setEnabled(True)
        self.group_combo.addItem("Select a group")
        self.group_combo.addItems(groups)
        
        # Try to restore the previous selection
        if current_text in groups:
            self.group_combo.setCurrentText(current_text)
        elif groups:
            self.group_combo.setCurrentIndex(1)  # Select first group
            
    def add_image_paths(self, file_paths):
        added = False
        for file_path in file_paths:
            if file_path not in self.image_paths:
                self.image_paths.append(file_path)
                item = QListWidgetItem(os.path.basename(file_path))
                item.setData(Qt.UserRole, os.path.basename(file_path))
                self.image_list_widget.addItem(item)
                # Initialize image group if not exists
                if file_path not in self.image_groups:
                    self.image_groups[file_path] = "Ungrouped"
                added = True
        if added:
            self.update_tab_state(True)

    def remove_image(self):
        selected_items = self.image_list_widget.selectedItems()
        if not selected_items:
            return
        indices_to_remove = sorted([self.image_list_widget.row(item) for item in selected_items], reverse=True)
        for index in indices_to_remove:
            self.image_list_widget.takeItem(index)
            image_path = self.image_paths.pop(index)
            if image_path in self.analysis_results:
                del self.analysis_results[image_path]

    def reset_parameters(self):
        self.donor_model = None
        self.donor_coeffs = None
        self.acceptor_model = None
        self.acceptor_coeffs = None
        self.image_paths.clear()
        self.image_list_widget.clear()
        self.analysis_results.clear()
        self.donor_model_label.setText("N/A")
        self.donor_coeffs_label.setText("N/A")
        self.acceptor_model_label.setText("N/A")
        self.acceptor_coeffs_label.setText("N/A")
        self.figure.clear()
        self.current_stats_table.setRowCount(0)
        self.aggregate_stats_table.setRowCount(0)
        self.canvas.draw()

    def set_correction_parameters(self, donor_model, donor_coeffs, acceptor_model, acceptor_coeffs):
        self.donor_model = donor_model
        self.donor_coeffs = donor_coeffs
        self.acceptor_model = acceptor_model
        self.acceptor_coeffs = acceptor_coeffs
        self.donor_model_label.setText(f"<b>{donor_model}</b>")
        self.donor_coeffs_label.setText(str(np.round(self.donor_coeffs, 4)))
        self.acceptor_model_label.setText(f"<b>{acceptor_model}</b>")
        self.acceptor_coeffs_label.setText(str(np.round(self.acceptor_coeffs, 4)))
        QMessageBox.information(self, "Parameters Received", "Bleed-through parameters have been successfully transferred.")

    def pixfret_threshold(self, donor_image: np.ndarray, acceptor_image: np.ndarray, bg_donor: float, bg_acceptor: float, threshold_factor: float = 1.0, use_local_averaging: bool = True) -> np.ndarray:
        """
        Apply PixFRET-style thresholding to FRET image data.
        
        Parameters:
        -----------
        donor_image : np.ndarray
            2D array of donor channel intensities
        acceptor_image : np.ndarray
            2D array of acceptor channel intensities
        bg_donor : float
            Background intensity for donor channel
        bg_acceptor : float
            Background intensity for acceptor channel
        threshold_factor : float, optional
            Multiplier for the threshold (default: 1.0)
        use_local_averaging : bool, optional
            Whether to apply 3×3 local averaging (default: True)
            
        Returns:
        --------
        mask : np.ndarray
            Boolean mask where True indicates pixels passing the threshold
        """
        # Background subtraction
        donor_sub = donor_image - bg_donor
        acceptor_sub = acceptor_image - bg_acceptor
        donor_sub[donor_sub < 0] = 0
        acceptor_sub[acceptor_sub < 0] = 0

        # Optional 3×3 local averaging
        if use_local_averaging:
            donor_local = uniform_filter(donor_sub, size=3, mode='reflect')
            acceptor_local = uniform_filter(acceptor_sub, size=3, mode='reflect')
        else:
            donor_local = donor_sub
            acceptor_local = acceptor_sub

        # Threshold calculation
        donor_threshold = bg_donor * threshold_factor
        acceptor_threshold = bg_acceptor * threshold_factor
        intensity = np.sqrt(donor_sub * acceptor_sub)
        Nthresh = np.sqrt(bg_donor * bg_acceptor) * threshold_factor

        # Pixel inclusion
        mask = (donor_local > donor_threshold) & (acceptor_local > acceptor_threshold) & (intensity > Nthresh)
        return mask

    def run_analysis(self):
        if not self.image_paths:
            QMessageBox.warning(self, "No Images", "Please add images to analyze.")
            return
        if self.analyze_all_checkbox.isChecked():
            image_paths_to_process = self.image_paths
        else:
            current_item = self.image_list_widget.currentItem()
            if not current_item:
                QMessageBox.warning(self, "No Selection", "Please select an image to analyze.")
                return
            image_paths_to_process = [self.image_paths[self.image_list_widget.row(current_item)]]
        if self.analyze_all_checkbox.isChecked():
            self.analysis_results.clear()
        total_images = len(image_paths_to_process)
        original_button_text = self.run_button.text()
        self.run_button.setEnabled(False)
        QApplication.processEvents()
        self.show_processing_dialog("Processing...")
        try:
            for i, file_path in enumerate(image_paths_to_process):
                self.run_button.setText(f"Processing... ({i+1}/{total_images})")
                QApplication.processEvents()
                try:
                    labels, fret, donor, acceptor, bg_donor, bg_acceptor = self.load_and_prepare_image(file_path)
                    if donor is None:
                        continue
                    efficiencies = {}
                    selected_formulas = [name for name, cb in self.formula_checkboxes.items() if cb.isChecked()]
                    label_mask = labels > 0
                    # Apply PixFRET thresholding if enabled
                    if self.pixfret_threshold_checkbox.isChecked():
                        threshold_factor = self.pixfret_threshold_factor_spinbox.value()
                        pixfret_mask = self.pixfret_threshold(donor, acceptor, bg_donor, bg_acceptor, threshold_factor)
                        final_mask = label_mask & pixfret_mask
                    else:
                        final_mask = label_mask

                    # Initialize excluded_labels as an empty set for backward compatibility
                    excluded_labels = set()
                    
                    # Donor/Acceptor ratio filtering per pixel
                    ratio_threshold = self.ratio_threshold_spinbox.value()
                    if ratio_threshold > 0:
                        # Calculate ratio for each pixel, avoiding division by zero
                        with np.errstate(divide='ignore', invalid='ignore'):
                            ratio = np.divide(donor, acceptor, out=np.zeros_like(donor, dtype=float), where=acceptor>0)
                        # Create a mask for pixels where ratio is within threshold
                        valid_ratio = (ratio <= ratio_threshold) & (ratio >= 1.0 / ratio_threshold)
                        # Only apply to labeled regions
                        valid_ratio = valid_ratio | (labels == 0)
                        # Update final mask
                        final_mask = final_mask & valid_ratio
                        
                        # For backward compatibility, find cells that were completely excluded
                        for lbl in np.unique(labels):
                            if lbl == 0:
                                continue
                            cell_mask = (labels == lbl)
                            if not np.any(final_mask[cell_mask]):
                                excluded_labels.add(lbl)
                    else:
                        final_mask = label_mask
                        
                    # Cell efficiency threshold filtering
                    if self.cell_eff_threshold_checkbox.isChecked():
                        cell_lower = self.cell_eff_lower_spinbox.value()
                        cell_upper = self.cell_eff_upper_spinbox.value()
                        if selected_formulas:
                            formula_for_thresh = selected_formulas[0]
                        else:
                            formula_for_thresh = 'FRET/Donor'
                        temp_eff_map = self.calculate_fret_efficiency(fret, donor, acceptor, formula_for_thresh)
                        temp_eff_map[~final_mask] = 0
                        
                        # Calculate mean efficiency for each cell and update mask
                        for lbl in np.unique(labels):
                            if lbl == 0 or lbl in excluded_labels:
                                continue
                            cell_mask = (labels == lbl)
                            vals = temp_eff_map[cell_mask]
                            vals = vals[np.isfinite(vals) & (vals > 0)]
                            if vals.size == 0:
                                continue
                            mean_val = vals.mean()
                            if mean_val < cell_lower or mean_val > cell_upper:
                                excluded_labels.add(lbl)
                                final_mask[cell_mask] = False
                    # Store efficiency maps for each formula and apply thresholds
                    for formula_name in selected_formulas:
                        eff_map = self.calculate_fret_efficiency(fret, donor, acceptor, formula_name)
                        # Apply final mask and set out-of-threshold pixels to 0
                        eff_map[~final_mask] = 0
                        
                        # Get current display thresholds
                        lower_thr = self.lower_threshold_spinbox.value()
                        upper_thr = self.upper_threshold_spinbox.value()
                        
                        # Apply display thresholds (set to 0 if outside range)
                        if lower_thr > 0 or upper_thr < 100:  # Only if thresholds are not at default values
                            with np.errstate(invalid='ignore'):  # Ignore invalid comparison warnings
                                eff_map[(eff_map < lower_thr) | (eff_map > upper_thr)] = 0
                        
                        efficiencies[formula_name] = eff_map
                    
                    # Store channel data with consistent keys
                    efficiencies["_labels"] = labels.astype(int)
                    efficiencies["_excluded_count"] = len(excluded_labels)
                    efficiencies["f"] = fret  # FRET channel
                    efficiencies["d"] = donor  # Donor channel
                    efficiencies["a"] = acceptor  # Acceptor channel
                    
                    # Store all results
                    self.analysis_results[file_path] = efficiencies
                    if self.save_efficiencies_checkbox.isChecked():
                        eff_to_save = {fn: efficiencies[fn] for fn in selected_formulas if fn in efficiencies}
                        # Always include labels in the saved results
                        if '_labels' in efficiencies:
                            eff_to_save['_labels'] = efficiencies['_labels']
                        if eff_to_save:
                            self.save_results(file_path, eff_to_save)
                    
                    # Store the set of formulas used in this analysis
                    self.used_formulas = selected_formulas
                    
                    # Update all formula combo boxes to show only the used formulas
                    combo_boxes = [
                        (self.aggregate_formula_combo, self.aggregate_formula_combo.currentText()),
                        (self.hist_formula_combo, self.hist_formula_combo.currentText()),
                        (self.fourier_formula_combo, self.fourier_formula_combo.currentText())
                    ]
                    
                    for combo_box, current_text in combo_boxes:
                        if combo_box is not None:
                            combo_box.blockSignals(True)  # Prevent triggering events during update
                            combo_box.clear()
                            combo_box.addItems(selected_formulas)
                            
                            # Try to restore the previous selection if it's still valid
                            if current_text in selected_formulas:
                                idx = selected_formulas.index(current_text)
                                combo_box.setCurrentIndex(idx)
                            combo_box.blockSignals(False)  # Re-enable signals
                    
                    # Make sure the distribution analysis formula combo is enabled if needed
                    if hasattr(self, 'fourier_formula_combo'):
                        self.fourier_formula_combo.setEnabled(len(selected_formulas) > 0 and self.distribution_enabled)
                except Exception as e:
                    error_msg = f"Failed to process {os.path.basename(file_path)}: {e}"
                    QMessageBox.critical(self, "Processing Error", error_msg)
                    self.analysis_results.pop(file_path, None)
                    continue
            if image_paths_to_process:
                self.update_plot_display()
                self.update_aggregate_stats_table()
                # Don't update representative images automatically - wait for button click
                # self.update_representative_images()  # Removed automatic update
            QMessageBox.information(self, "Analysis Complete", f"Processed {total_images} image(s).")
        finally:
            self.run_button.setText(original_button_text)
            self.run_button.setEnabled(True)
            self.close_processing_dialog()

    def load_and_prepare_image(self, file_path):
        if file_path.lower().endswith('.czi'):
            czi_file = czi.CziFile(file_path)
            image_data = czi_file.asarray().squeeze()
            if image_data.ndim != 3 or image_data.shape[0] < 4:
                raise ValueError("CZI file must contain at least 4 channels (Labels, FRET, Donor, Acceptor).")
            labels, fret_channel, donor_channel, acceptor_channel = [image_data[i].astype(float) for i in range(4)]
        elif file_path.lower().endswith(('.tif', '.tiff')):
            image_data = tifffile.imread(file_path)
            if image_data.ndim != 3 or image_data.shape[0] < 4:
                raise ValueError("TIFF file must have at least 4 frames (Labels, FRET, Donor, Acceptor).")
            labels, fret_channel, donor_channel, acceptor_channel = [image_data[i].astype(float) for i in range(4)]
        else:
            QMessageBox.warning(self, "Unsupported Format", f"Unsupported file format: {os.path.basename(file_path)}.")
            return None, None, None, None, None, None
        sigma = self.gaussian_blur_spinbox.value()
        if sigma > 0:
            donor_channel = gaussian_filter(donor_channel, sigma=sigma)
            acceptor_channel = gaussian_filter(acceptor_channel, sigma=sigma)
            fret_channel = gaussian_filter(fret_channel, sigma=sigma)
        donor_channel, bg_donor = self.subtract_background(donor_channel)
        acceptor_channel, bg_acceptor = self.subtract_background(acceptor_channel)
        fret_channel, _ = self.subtract_background(fret_channel)
        donor_bleed = self.apply_correction(donor_channel, self.donor_model, self.donor_coeffs)
        acceptor_bleed = self.apply_correction(acceptor_channel, self.acceptor_model, self.acceptor_coeffs)
        corrected_fret = fret_channel - donor_bleed - acceptor_bleed
        corrected_fret[corrected_fret < 0] = 0
        return labels, corrected_fret, donor_channel, acceptor_channel, bg_donor, bg_acceptor

    def apply_correction(self, image, model, coeffs):
        if model == 'Constant':
            return image * coeffs
        elif model == 'Linear':
            return image * (coeffs[0] * image + coeffs[1])
        elif model == 'Exponential':
            return image * (coeffs[0] * np.exp(-coeffs[1] * image) + coeffs[2])
        return np.zeros_like(image)

    def subtract_background(self, image, kernel_size=None):
        if kernel_size is None:
            kernel_size = int(self.bg_kernel_spinbox.value()) if hasattr(self, 'bg_kernel_spinbox') else 30
        local_means = uniform_filter(image.astype(float), size=kernel_size, mode='reflect')
        min_mean = float(np.min(local_means))
        bg_sub = image - min_mean
        bg_sub[bg_sub < 0] = 0
        return bg_sub, min_mean

    def calculate_fret_efficiency(self, f, d, a, formula_name):
        f, d, a = f.astype(float), d.astype(float), a.astype(float)
        efficiency = np.zeros_like(f, dtype=float)
        with np.errstate(divide='ignore', invalid='ignore'):
            if formula_name == "FRET/Donor":
                efficiency = np.divide(f, d, out=np.zeros_like(f, dtype=float), where=d!=0)
            elif formula_name == "FRET/Acceptor":
                efficiency = np.divide(f, a, out=np.zeros_like(f, dtype=float), where=a!=0)
            elif formula_name == "Xia":
                denominator = np.sqrt(d * a)
                efficiency = np.divide(f, denominator, out=np.zeros_like(f, dtype=float), where=denominator!=0)
            elif formula_name == "Gordon":
                denominator = d * a
                efficiency = np.divide(f, denominator, out=np.zeros_like(f, dtype=float), where=denominator!=0)
            elif formula_name == "PixFRET":
                denominator = d + f
                efficiency = np.divide(f, denominator, out=np.zeros_like(f, dtype=float), where=denominator!=0)
        return efficiency * 100

    def export_histogram_data(self):
        if not hasattr(self, 'current_hist_data'):
            QMessageBox.warning(self, "No Data", "No histogram data available to export.")
            return
        formula_name = self.hist_formula_combo.currentText()
        current_item = self.image_list_widget.currentItem()
        if not current_item:
            return
        file_path = self.image_paths[self.image_list_widget.row(current_item)]
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        default_filename = f"{base_name}_{formula_name.replace(' ', '_')}_histogram.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Histogram Data",
            os.path.join(os.path.expanduser("~"), default_filename),
            "CSV Files (*.csv)"
        )
        if not file_path:
            return
        try:
            if not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            centers = self.current_hist_data['centers']
            mean_hist = self.current_hist_data['mean_hist']
            sem_hist = self.current_hist_data['sem_hist']
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Efficiency (%)', 'Mean Pixel %', 'SEM'])
                for center, mean_val, sem_val in zip(centers, mean_hist, sem_hist):
                    writer.writerow([f"{center:.2f}", f"{mean_val:.4f}", f"{sem_val:.4f}"])
            QMessageBox.information(self, "Export Successful", f"Histogram data exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export histogram data:\n{str(e)}")

    def load_ramps_colormap(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            lut_path = os.path.join(script_dir, 'lut_files/5_ramps.lut')
            if not os.path.exists(lut_path):
                lut_path = resource_path('lut_files/5_ramps.lut')
            if not os.path.exists(lut_path):
                print(f"Warning: 5_ramps.lut not found at {lut_path}, using 'jet' colormap")
                return plt.get_cmap('jet')
            lut = np.loadtxt(lut_path)
            if np.max(lut) > 1.0:
                lut = lut / 255.0
            if len(lut.shape) != 2 or lut.shape[1] != 3:
                print(f"Warning: Invalid LUT format in {lut_path}, using 'jet' colormap")
                return plt.get_cmap('jet')
            if lut.shape[0] < 256:
                lut = np.vstack([lut, np.tile(lut[-1], (256 - lut.shape[0], 1))])
            elif lut.shape[0] > 256:
                lut = lut[:256]
            return ListedColormap(lut, name='5_ramps')
        except Exception as e:
            print(f"Error loading colormap: {str(e)}")
            return plt.get_cmap('jet')

    def _load_lut_file(self, filename):
        """Helper method to load a LUT file with error handling."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            lut_path = os.path.join(script_dir, filename)
            if not os.path.exists(lut_path):
                lut_path = resource_path(filename)
            if not os.path.exists(lut_path):
                print(f"Warning: {filename} not found at {lut_path}")
                return None
                
            # Load the LUT file, skipping empty lines and stripping whitespace
            with open(lut_path, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Parse the LUT values
            lut = []
            for line in lines:
                # Skip comment lines
                if line.startswith('#'):
                    continue
                # Split on whitespace and convert to float
                values = [float(x) for x in line.split()]
                if len(values) >= 3:  # Need at least R,G,B values
                    lut.append(values[:3])
            
            if not lut:
                print(f"Warning: No valid data in {filename}")
                return None
                
            lut = np.array(lut)
            
            # Normalize to [0,1] range if needed
            if np.max(lut) > 1.0:
                lut = lut / 255.0
                
            # Ensure proper shape (N,3)
            if len(lut.shape) != 2 or lut.shape[1] != 3:
                print(f"Warning: Invalid LUT format in {filename}")
                return None
                
            # Ensure exactly 256 colors by repeating the last color or truncating
            if lut.shape[0] < 256:
                lut = np.vstack([lut, np.tile(lut[-1], (256 - lut.shape[0], 1))])
            elif lut.shape[0] > 256:
                lut = lut[:256]
                
            return lut
            
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return None
            
    def load_orange_colormap(self):
        """Load the Orange.lut colormap."""
        lut = self._load_lut_file('lut_files/Orange.lut')
        if lut is not None:
            return ListedColormap(lut, name='orange_custom')
        print("Using 'Oranges' colormap as fallback")
        return plt.get_cmap('Oranges')
        
    def load_green_colormap(self):
        """Load the Green.lut colormap."""
        lut = self._load_lut_file('lut_files/Green.lut')
        if lut is not None:
            return ListedColormap(lut, name='green_custom')
        print("Using 'Greens' colormap as fallback")
        return plt.get_cmap('Greens')
        
    def load_red_colormap(self):
        """Load the Red.lut colormap."""
        lut = self._load_lut_file('lut_files/Red.lut')
        if lut is not None:
            return ListedColormap(lut, name='red_custom')
        print("Using 'Reds' colormap as fallback")
        return plt.get_cmap('Reds')

    def save_results(self, original_path, efficiencies):
        try:
            base_dir = os.path.dirname(original_path)
            base_name = os.path.basename(original_path)
            name_without_ext, _ = os.path.splitext(base_name)
            output_dir = os.path.join(base_dir, "FRET_Analysis_Results")
            os.makedirs(output_dir, exist_ok=True)
            for formula_name, eff_map in efficiencies.items():
                safe_formula_name = formula_name.replace('/', '_').replace(' ','')
                output_filename = f"{name_without_ext}_{safe_formula_name}_efficiency.tif"
                output_path = os.path.join(output_dir, output_filename)
                # Convert to 32-bit float to preserve percentage values (0-100%)
                scaled = eff_map.astype(np.float32)
                tifffile.imwrite(
                    output_path, 
                    scaled,
                    dtype=scaled.dtype,  # Use the data type of the scaled array
                    metadata={'axes': 'YX'},  # Ensure proper dimension order
                    imagej=True  # Add ImageJ metadata for better compatibility
                )
                print(f"Saved {formula_name} efficiency map to {output_path}")
                print(f"  - Shape: {eff_map.shape}, dtype: {eff_map.dtype}")
                print(f"  - Min: {np.min(eff_map):.4f}, Max: {np.max(eff_map):.4f}, Mean: {np.mean(eff_map):.4f}")
        except Exception as e:
            error_msg = f"Failed to save results for {os.path.basename(original_path)}: {e}"
            print(error_msg)
            QMessageBox.critical(self, "Save Error", error_msg)

    def update_histogram_plot(self):
        selected_formula = self.hist_formula_combo.currentText()
        current_item = self.image_list_widget.currentItem()
        if current_item is None:
            return
        file_path = self.image_paths[self.image_list_widget.row(current_item)]
        if file_path not in self.analysis_results:
            return
        efficiencies = self.analysis_results[file_path]
        if selected_formula not in efficiencies or "_labels" not in efficiencies:
            self.hist_figure.clear()
            self.hist_canvas.draw()
            return
        eff_map = efficiencies[selected_formula]
        labels_arr = efficiencies["_labels"]
        label_ids = np.unique(labels_arr)
        label_ids = label_ids[label_ids > 0]
        if label_ids.size == 0:
            self.hist_figure.clear()
            self.hist_canvas.draw()
            return
        edges = np.linspace(0, 50, 257)
        lower_thr = self.lower_threshold_spinbox.value()
        upper_thr = self.upper_threshold_spinbox.value()
        per_label_hists = []
        for lbl in label_ids:
            mask = ((labels_arr == lbl) & np.isfinite(eff_map) & (eff_map > 0))
            vals = eff_map[mask]
            if vals.size == 0:
                continue
                
            # Calculate whisker positions to identify outliers
            q1 = np.percentile(vals, 25)
            q3 = np.percentile(vals, 75)
            iqr = q3 - q1
            lower_whisker = q1 - 1.5 * iqr
            upper_whisker = q3 + 1.5 * iqr
            
            # Filter out outliers
            inliers = vals[(vals >= lower_whisker) & (vals <= upper_whisker)]
            
            # Apply thresholding to inliers
            hist_vals = inliers[(inliers >= lower_thr) & (inliers <= upper_thr)]
            if hist_vals.size == 0:
                continue
                
            hist_counts, _ = np.histogram(hist_vals, bins=edges)
            per_label_hists.append((hist_counts / inliers.size) * 100.0)
        if len(per_label_hists) == 0:
            self.hist_figure.clear()
            self.hist_canvas.draw()
            return
        hist_matrix = np.vstack(per_label_hists)
        mean_hist = np.mean(hist_matrix, axis=0)
        std_hist = np.std(hist_matrix, axis=0)
        n_cells = hist_matrix.shape[0]
        sem_hist = std_hist / np.sqrt(n_cells)
        centers = (edges[:-1] + edges[1:]) / 2
        self.current_hist_data = {
            'centers': centers,
            'mean_hist': mean_hist,
            'sem_hist': sem_hist,
            'formula': selected_formula,
            'image_path': file_path
        }
        self.hist_figure.clear()
        ax = self.hist_figure.add_subplot(111)
        ax.errorbar(
            centers,
            mean_hist,
            yerr=sem_hist,
            fmt='-o',
            color="#1f77b4",
            markersize=3,
            linewidth=1.2,
            capsize=3,
            ecolor="gray",
            elinewidth=0.8,
            alpha=0.4
        )
        ax.set_xlabel("FRET Efficiency (%)")
        ax.set_ylabel("Pixel Percentage (%)")
        ax.set_title(f"Histogram of labelled cells ({selected_formula})")
        ax.set_xlim(0, 50)
        ax.set_ylim(0, max(mean_hist + std_hist) * 1.1)
        layout = self.hist_figure.canvas.parent().layout()
        if hasattr(self, 'export_btn'):
            layout.removeWidget(self.export_btn)
            self.export_btn.deleteLater()
        btn_export = QPushButton("Export Data")
        btn_export.clicked.connect(self.export_histogram_data)
        layout.addWidget(btn_export)
        self.export_btn = btn_export
        self.hist_figure.tight_layout()
        self.hist_canvas.draw()

    def load_ramps_colormap(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            lut_path = os.path.join(script_dir, 'lut_files/5_ramps.lut')
            if not os.path.exists(lut_path):
                lut_path = resource_path('lut_files/5_ramps.lut')
            if not os.path.exists(lut_path):
                print(f"Warning: 5_ramps.lut not found at {lut_path}, using 'jet' colormap")
                return plt.get_cmap('jet')
            lut = np.loadtxt(lut_path)
            if np.max(lut) > 1.0:
                lut = lut / 255.0
            if len(lut.shape) != 2 or lut.shape[1] != 3:
                print(f"Warning: Invalid LUT format in {lut_path}, using 'jet' colormap")
                return plt.get_cmap('jet')
            if lut.shape[0] < 256:
                lut = np.vstack([lut, np.tile(lut[-1], (256 - lut.shape[0], 1))])
            elif lut.shape[0] > 256:
                lut = lut[:256]
            return ListedColormap(lut, name='5_ramps')
        except Exception as e:
            print(f"Error loading colormap: {str(e)}")
            return plt.get_cmap('jet')

    def _load_lut_file(self, filename):
        """Helper method to load a LUT file with error handling."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            lut_path = os.path.join(script_dir, filename)
            if not os.path.exists(lut_path):
                lut_path = resource_path(filename)
            if not os.path.exists(lut_path):
                print(f"Warning: {filename} not found at {lut_path}")
                return None
                
            # Load the LUT file, skipping empty lines and stripping whitespace
            with open(lut_path, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            
            # Parse the LUT values
            lut = []
            for line in lines:
                # Skip comment lines
                if line.startswith('#'):
                    continue
                # Split on whitespace and convert to float
                values = [float(x) for x in line.split()]
                if len(values) >= 3:  # Need at least R,G,B values
                    lut.append(values[:3])
            
            if not lut:
                print(f"Warning: No valid data in {filename}")
                return None
                
            lut = np.array(lut)
            
            # Normalize to [0,1] range if needed
            if np.max(lut) > 1.0:
                lut = lut / 255.0
                
            # Ensure proper shape (N,3)
            if len(lut.shape) != 2 or lut.shape[1] != 3:
                print(f"Warning: Invalid LUT format in {filename}")
                return None
                
            # Ensure exactly 256 colors by repeating the last color or truncating
            if lut.shape[0] < 256:
                lut = np.vstack([lut, np.tile(lut[-1], (256 - lut.shape[0], 1))])
            elif lut.shape[0] > 256:
                lut = lut[:256]
                
            return lut
            
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return None
            
    def load_orange_colormap(self):
        """Load the Orange.lut colormap."""
        lut = self._load_lut_file('lut_files/Orange.lut')
        if lut is not None:
            return ListedColormap(lut, name='orange_custom')
        print("Using 'Oranges' colormap as fallback")
        return plt.get_cmap('Oranges')
        
    def load_green_colormap(self):
        """Load the Green.lut colormap."""
        lut = self._load_lut_file('lut_files/Green.lut')
        if lut is not None:
            return ListedColormap(lut, name='green_custom')
        print("Using 'Greens' colormap as fallback")
        return plt.get_cmap('Greens')
        
    def load_red_colormap(self):
        """Load the Red.lut colormap."""
        lut = self._load_lut_file('lut_files/Red.lut')
        if lut is not None:
            return ListedColormap(lut, name='red_custom')
        print("Using 'Reds' colormap as fallback")
        return plt.get_cmap('Reds')

    def update_current_boxplot(self):
        current_item = self.image_list_widget.currentItem()
        if not current_item or not self.analysis_results:
            self.box_figure.clear()
            self.box_canvas.draw()
            return
        lower_thr = self.lower_threshold_spinbox.value()
        upper_thr = self.upper_threshold_spinbox.value()
        file_path = self.image_paths[self.image_list_widget.row(current_item)]
        if file_path not in self.analysis_results:
            self.box_figure.clear()
            self.box_canvas.draw()
            return
        selected_formula = self.hist_formula_combo.currentText()
        eff_map = self.analysis_results[file_path].get(selected_formula)
        labels_arr = self.analysis_results[file_path].get("_labels")
        if eff_map is None or labels_arr is None:
            self.box_figure.clear()
            self.box_canvas.draw()
            return
        avg_vals = []
        for lbl in np.unique(labels_arr)[1:]:
            mask = ((labels_arr == lbl) & np.isfinite(eff_map) & (eff_map >= lower_thr) & (eff_map <= upper_thr) & (eff_map > 0))
            vals = eff_map[mask]
            if vals.size > 0:
                avg_vals.append(np.mean(vals))
        if not avg_vals:
            self.box_figure.clear()
            self.box_canvas.draw()
            return
            
        # Calculate whisker positions to identify outliers
        q1 = np.percentile(avg_vals, 25)
        q3 = np.percentile(avg_vals, 75)
        iqr = q3 - q1
        lower_whisker = q1 - 1.5 * iqr
        upper_whisker = q3 + 1.5 * iqr
        
        # Filter out outliers for statistics
        inliers = [x for x in avg_vals if lower_whisker <= x <= upper_whisker]
        
        # Calculate statistics using only inliers
        mean_val = np.mean(inliers) if inliers else 0
        n_points = len(inliers)
        
        # Calculate compactness/variance using only inliers
        compactness = (np.sum((np.array(inliers) - mean_val) ** 2))/len(inliers) if inliers else 0
        
        self.box_figure.clear()
        ax = self.box_figure.add_subplot(111)
        # First create the boxplot to get the whisker positions
        bp = ax.boxplot(avg_vals, vert=True, patch_artist=True, widths=0.6, 
                        boxprops=dict(facecolor="#cccccc"),
                        medianprops=dict(color="red", linewidth=1.5), 
                        showmeans=True,
                        meanprops=dict(marker='D', markeredgecolor='black', 
                                     markerfacecolor='yellow', markersize=5),
                        showfliers=False)  # We'll add our own fliers
        
        # Get whisker positions (Q1 - 1.5*IQR and Q3 + 1.5*IQR)
        q1 = np.percentile(avg_vals, 25)
        q3 = np.percentile(avg_vals, 75)
        iqr = q3 - q1
        lower_whisker = q1 - 1.5 * iqr
        upper_whisker = q3 + 1.5 * iqr
        
        # Add jittered points with consistent styling
        jitter = 0.15  # Slightly more jitter for better visibility
        x_jitter = np.random.uniform(1 - jitter, 1 + jitter, size=len(avg_vals))
        
        # Separate inliers and outliers
        inliers = (avg_vals >= lower_whisker) & (avg_vals <= upper_whisker)
        outliers = ~inliers
        
        # Plot inliers (normal color)
        inlier_color = 'purple' if self.current_theme == 'dark' else 'k'
        ax.scatter(x_jitter[inliers], np.array(avg_vals)[inliers], 
                  color=inlier_color, s=30, alpha=0.9, 
                  zorder=4, edgecolor='white', linewidth=0.8,
                  label=f'Mean: {mean_val:.1f}%\nN = {n_points}')
        
        # Plot outliers (distinct color)
        if np.any(outliers):
            outlier_color = '#2ecc71' if self.current_theme == 'dark' else '#e74c3c'
            ax.scatter(x_jitter[outliers], np.array(avg_vals)[outliers],
                      color=outlier_color, s=30, alpha=0.9,
                      zorder=4, edgecolor='white', linewidth=0.8,
                      label='_nolegend_')
        ax.axhline(y=mean_val, color='red', linestyle='--', linewidth=1, alpha=0.7, zorder=3)
        ax.set_ylabel(self.box_y_label_edit.text() or "% FRET Efficiency")
        ymin, ymax = ax.get_ylim()
        ax.set_ylim(bottom=0, top=ymax if ymax > 0 else 1)
        ax.set_xticks([1])
        ax.set_xticklabels([os.path.basename(file_path)])
        ax.set_title(f"Per-cell Average ({selected_formula})\n(Threshold: {lower_thr}-{upper_thr}%)")
        
        # Add compactness/variance to the legend
        legend_text = f"Mean: {mean_val:.1f}%\nN = {n_points}\nCompactness: {compactness:.2f}"
        
        # Create legend with the updated text
        legend = ax.legend([legend_text], loc='upper right', frameon=True, framealpha=0.9, 
                          fancybox=True, shadow=True, borderpad=0.8, 
                          handlelength=0, handletextpad=0, fontsize='small')
        for text in legend.get_texts():
            text.set_ha('left')
            text.set_position((8, 0))
        self.box_figure.tight_layout()
        self.box_canvas.draw()
        
    def _open_current_image_boxplot_popout(self, figure, title):
        # Create a new figure for the popout
        new_fig = plt.figure(figsize=(8, 6), dpi=100)
        
        # Get the current image path and formula
        current_item = self.image_list_widget.currentItem()
        if not current_item or not self.analysis_results:
            return
            
        file_path = self.image_paths[self.image_list_widget.row(current_item)]
        selected_formula = self.hist_formula_combo.currentText()
        lower_thr = self.lower_threshold_spinbox.value()
        upper_thr = self.upper_threshold_spinbox.value()
        eff_map = self.analysis_results[file_path].get(selected_formula)
        labels_arr = self.analysis_results[file_path].get("_labels")
        
        if eff_map is None or labels_arr is None:
            return
            
        # Calculate per-cell averages
        avg_vals = []
        for lbl in np.unique(labels_arr)[1:]:
            mask = ((labels_arr == lbl) & np.isfinite(eff_map) & 
                   (eff_map >= lower_thr) & (eff_map <= upper_thr) & (eff_map > 0))
            vals = eff_map[mask]
            if vals.size > 0:
                avg_vals.append(np.mean(vals))
                
        if not avg_vals:
            return
            
        # Calculate whisker positions and identify outliers
        q1 = np.percentile(avg_vals, 25)
        q3 = np.percentile(avg_vals, 75)
        iqr = q3 - q1
        lower_whisker = q1 - 1.5 * iqr
        upper_whisker = q3 + 1.5 * iqr
        
        # Filter out outliers for statistics
        inliers = [x for x in avg_vals if lower_whisker <= x <= upper_whisker]
        
        # Calculate statistics using only inliers
        mean_val = np.mean(inliers) if inliers else 0
        n_points = len(inliers)
        
        # Create the boxplot in the popout
        ax = new_fig.add_subplot(111)
        
        # Create the boxplot
        bp = ax.boxplot(avg_vals, vert=True, patch_artist=True, widths=0.6, 
                       boxprops=dict(facecolor="#cccccc"),
                       medianprops=dict(color="red", linewidth=1.5), 
                       showmeans=True,
                       meanprops=dict(marker='D', markeredgecolor='black', 
                                    markerfacecolor='yellow', markersize=5),
                       showfliers=False)  # We'll add our own fliers
        
        # Add jittered points with consistent styling
        jitter = 0.15
        x_jitter = np.random.uniform(1 - jitter, 1 + jitter, size=len(avg_vals))
        
        # Separate inliers and outliers
        inliers_mask = (np.array(avg_vals) >= lower_whisker) & (np.array(avg_vals) <= upper_whisker)
        outliers_mask = ~inliers_mask
        
        # Plot inliers
        inlier_color = 'purple' if self.current_theme == 'dark' else 'k'
        ax.scatter(x_jitter[inliers_mask], np.array(avg_vals)[inliers_mask], 
                  color=inlier_color, s=30, alpha=0.9, 
                  zorder=4, edgecolor='white', linewidth=0.8)
        
        # Plot outliers
        if np.any(outliers_mask):
            outlier_color = '#2ecc71' if self.current_theme == 'dark' else '#e74c3c'
            ax.scatter(x_jitter[outliers_mask], np.array(avg_vals)[outliers_mask],
                      color=outlier_color, s=30, alpha=0.9,
                      zorder=4, edgecolor='white', linewidth=0.8)
        
        # Add mean line
        ax.axhline(y=mean_val, color='red', linestyle='--', linewidth=1, alpha=0.7, zorder=3)
        
        # Set labels and title
        ax.set_ylabel(self.box_y_label_edit.text() or "% FRET Efficiency")
        ax.set_xticks([1])
        ax.set_xticklabels([os.path.basename(file_path)])
        ax.set_title(f"Per-cell Average ({selected_formula})\n(Threshold: {lower_thr}-{upper_thr}%)")
        
        # Add legend with statistics
        compactness = (np.sum((np.array(inliers) - mean_val) ** 2))/len(inliers) if inliers else 0
        legend_text = f"Mean: {mean_val:.1f}%\nN = {n_points}\nCompactness: {compactness:.2f}"
        
        # Create legend with the updated text
        legend = ax.legend([legend_text], loc='upper right', frameon=True, framealpha=0.9, 
                          fancybox=True, shadow=True, borderpad=0.8, 
                          handlelength=0, handletextpad=0, fontsize='small')
        for text in legend.get_texts():
            text.set_ha('left')
            text.set_position((8, 0))
        
        # Adjust layout
        new_fig.tight_layout()
        
        # Create and show the dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} - {os.path.basename(file_path)}")
        dlg.setMinimumSize(800, 600)
        layout = QVBoxLayout(dlg)
        
        # Create a scroll area for the plot
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        # Create a container widget for the scroll area
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create a new canvas for the figure
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
        
        canvas = FigureCanvas(new_fig)
        container_layout.addWidget(canvas)
        
        # Add navigation toolbar
        toolbar = NavigationToolbar(canvas, dlg)
        container_layout.addWidget(toolbar)
        
        # Add a button to save the figure
        save_btn = QPushButton("Save Figure")
        save_btn.clicked.connect(lambda: self.save_figure(new_fig, f"{title}_{os.path.basename(file_path)}"))
        container_layout.addWidget(save_btn)
        
        # Set the container as the scroll area's widget
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Show the dialog
        dlg.exec_()
        
    def assign_group_to_selected(self):
        label = self.group_edit.text().strip()
        if not label:
            return
        for item in self.image_list_widget.selectedItems():
            idx = self.image_list_widget.row(item)
            path = self.image_paths[idx]
            self.image_groups[path] = label
            base = item.data(Qt.UserRole) or item.text().split(' [')[0]
            item.setData(Qt.UserRole, base)
            item.setText(f"{base} [{label}]")
        self.update_aggregate_boxplot()
        # Don't update representative images automatically - wait for button click
        # self.update_representative_images()  # Removed automatic update

    def update_aggregate_boxplot(self):
        selected_formula = self.aggregate_formula_combo.currentText()
        if not selected_formula or not self.analysis_results:
            self.agg_box_figure.clear()
            self.agg_box_canvas.draw()
            return
        from collections import defaultdict
        group_data = defaultdict(list)
        for path, efficiencies in self.analysis_results.items():
            if selected_formula not in efficiencies or "_labels" not in efficiencies:
                continue
            lower_thr = self.lower_threshold_spinbox.value()
            upper_thr = self.upper_threshold_spinbox.value()
            eff_map = efficiencies[selected_formula]
            labels_arr = efficiencies["_labels"]
            per_cell_avgs = []
            for lbl in np.unique(labels_arr)[1:]:
                mask = ((labels_arr == lbl) & np.isfinite(eff_map) & (eff_map >= lower_thr) & (eff_map <= upper_thr) & (eff_map > 0))
                vals = eff_map[mask]
                if vals.size > 0:
                    per_cell_avgs.append(np.mean(vals))
            if per_cell_avgs:
                label = os.path.splitext(os.path.basename(path))[0]
                if len(label) > 25:
                    label = '…' + label[-24:]
                gname = self.image_groups.get(path, "Ungrouped")
                group_data[gname].extend(per_cell_avgs)
        if not group_data:
            self.agg_box_figure.clear()
            self.agg_box_canvas.draw()
            return
        labels_sorted = sorted(group_data.keys())
        box_data = [group_data[g] for g in labels_sorted]
        fig_width = max(5, 1.1 * len(labels_sorted))
        self.agg_box_figure.set_size_inches(fig_width, 5, forward=True)
        self.agg_box_figure.clear()
        ax = self.agg_box_figure.add_subplot(111)
        group_stats = []
        for i, (group, data) in enumerate(zip(labels_sorted, box_data), 1):
            if not data:
                continue
                
            # Calculate whisker positions to identify outliers
            q1 = np.percentile(data, 25)
            q3 = np.percentile(data, 75)
            iqr = q3 - q1
            lower_whisker = q1 - 1.5 * iqr
            upper_whisker = q3 + 1.5 * iqr
            
            # Filter out outliers for statistics
            inliers = [x for x in data if lower_whisker <= x <= upper_whisker]
            
            # Calculate statistics using only inliers
            mean_val = np.mean(inliers) if inliers else 0
            n_points = len(inliers)
            
            # Calculate compactness/variance using only inliers
            compactness = (np.sum((np.array(inliers) - mean_val) ** 2))/len(inliers) if inliers else 0
            group_stats.append((i-1, group, mean_val, n_points, compactness))
        import scipy.stats as stats
        comparisons = []
        if len(labels_sorted) == 2:
            pval = stats.ttest_ind(box_data[0], box_data[1], equal_var=False).pvalue
            comparisons.append((0,1,pval))
        elif len(labels_sorted) > 2:
            p_anova = stats.f_oneway(*box_data).pvalue
            from itertools import combinations
            for (i,j) in combinations(range(len(labels_sorted)),2):
                p = stats.ttest_ind(box_data[i], box_data[j], equal_var=False).pvalue * len(labels_sorted)*(len(labels_sorted)-1)/2
                comparisons.append((i,j,min(p,1.0)))
        y_max = max(max(d) if d else 0 for d in box_data) * 1.05
        step = y_max * 0.05 if y_max > 0 else 1
        cur_y = y_max
        # Store the colors for the legend before creating individual box plots
        colors = plt.cm.tab10.colors
        box_colors = [colors[i % len(colors)] for i in range(len(box_data))]
        
        for i, (data, color) in enumerate(zip(box_data, box_colors), 1):
            if not data:
                continue
                
            # Create the boxplot to get the whisker positions
            bp = ax.boxplot([data], positions=[i], vert=True, patch_artist=True, widths=0.6,
                          boxprops=dict(facecolor=color, alpha=0.5),
                          medianprops=dict(color="red", linewidth=1.5),
                          showmeans=True,
                          meanprops=dict(marker='D', markeredgecolor='black',
                                       markerfacecolor='yellow', markersize=5),
                          showfliers=False)  # We'll add our own fliers
            
            # Get whisker positions (Q1 - 1.5*IQR and Q3 + 1.5*IQR)
            q1 = np.percentile(data, 25)
            q3 = np.percentile(data, 75)
            iqr = q3 - q1
            lower_whisker = q1 - 1.5 * iqr
            upper_whisker = q3 + 1.5 * iqr
            
            # Add jitter to x-positions
            jitter = 0.15
            x_jitter = np.random.uniform(i - jitter, i + jitter, size=len(data))
            
            # Separate inliers and outliers
            data_array = np.array(data)
            inliers = (data_array >= lower_whisker) & (data_array <= upper_whisker)
            outliers = ~inliers
            
            # Plot inliers with the same color as the box
            inlier_color = color
            ax.scatter(x_jitter[inliers], data_array[inliers],
                      color=inlier_color, s=25, alpha=0.9,
                      zorder=4, edgecolor='white', linewidth=0.8)
            
            # Plot outliers (red in light theme, green in dark theme)
            if np.any(outliers):
                outlier_color = '#2ecc71' if self.current_theme == 'dark' else '#e74c3c'
                ax.scatter(x_jitter[outliers], data_array[outliers],
                          color=outlier_color, s=30, alpha=0.9,
                          zorder=4, edgecolor='white', linewidth=0.8)
        for i, j, p in comparisons:
            symbol = self._p_to_symbol(p)
            self._draw_sig(ax, i+1, j+1, cur_y, symbol)
            cur_y += step
        legend_handles = []
        legend_labels = []
        for (i, group, mean_val, n_points, compactness), color in zip(group_stats, box_colors):
            legend_handles.append(plt.Rectangle((0,0), 0.8, 0.8, fc=color, ec='black', linewidth=0.5, alpha=0.5))
            legend_labels.append(f'{group}: {mean_val:.1f}% (n={n_points}, C={compactness:.1f})')
        legend = ax.legend(legend_handles, legend_labels, loc='upper right', bbox_to_anchor=(1, 1),
                           frameon=True, framealpha=0.9, fancybox=True, shadow=True, borderpad=0.8,
                           handlelength=1.5, handletextpad=0.5, columnspacing=1.0, fontsize='small')
        for text in legend.get_texts():
            text.set_ha('left')
        ax.set_ylabel(self.agg_box_y_label_edit.text() or "% FRET Efficiency")
        ymin, ymax = ax.get_ylim()
        ax.set_ylim(bottom=0, top=max(ymax, cur_y + step*1.2) if ymax > 0 else 1)
        ax.set_xticks(range(1, len(labels_sorted)+1))
        ax.set_xticklabels(labels_sorted, rotation=45, ha="right")
        ax.set_title(self.agg_box_title_edit.text() or f"Per-cell Averages by Group ({selected_formula})\n(Threshold: {lower_thr}-{upper_thr}%)")
        
        # Match the current image boxplot behavior
        self.agg_box_figure.tight_layout()
        self.agg_box_canvas.draw()
        # Ensure the figure takes up all available space
        self.agg_box_figure.set_size_inches(
            self.agg_box_canvas.width() / self.agg_box_figure.dpi,
            self.agg_box_canvas.height() / self.agg_box_figure.dpi,
            forward=True
        )
        self.agg_box_figure.tight_layout()
        self.agg_box_canvas.draw()

    def export_aggregate_histogram_data(self):
        if not hasattr(self, 'last_histogram_data') or not self.last_histogram_data:
            QMessageBox.warning(self, "No Data", "No aggregate histogram data available to export.")
            return
        selected_formula = self.aggregate_formula_combo.currentText()
        default_filename = f"FRET_aggregate_histogram_{selected_formula.replace(' ', '_')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Aggregate Histogram Data",
            os.path.join(os.path.expanduser("~"), default_filename),
            "CSV Files (*.csv)"
        )
        if not file_path:
            return
        try:
            if not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            with open(file_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                header = ['Efficiency (%)']
                for group in self.last_histogram_data.keys():
                    header.extend([f'{group} Mean %', f'{group} SEM'])
                writer.writerow(header)
                for i in range(len(self.last_histogram_data[list(self.last_histogram_data.keys())[0]][0])):
                    row = [f"{self.last_histogram_data[list(self.last_histogram_data.keys())[0]][0][i]:.2f}"]
                    for group in self.last_histogram_data.keys():
                        centers, means, sems = self.last_histogram_data[group]
                        row.extend([f"{means[i]:.4f}", f"{sems[i]:.4f}"])
                    writer.writerow(row)
            QMessageBox.information(self, "Export Successful", f"Aggregate histogram data exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export aggregate histogram data:\n{str(e)}")

    def update_aggregate_histogram_plot(self):
        selected_formula = self.aggregate_formula_combo.currentText()
        if not selected_formula or not self.analysis_results:
            self.agg_hist_figure.clear()
            self.agg_hist_canvas.draw()
            return
        edges = np.linspace(0, 50, 257)
        lower_thr = self.lower_threshold_spinbox.value()
        upper_thr = self.upper_threshold_spinbox.value()
        per_cell_hists = []
        for efficiencies in self.analysis_results.values():
            if selected_formula not in efficiencies or "_labels" not in efficiencies:
                continue
            eff_map = efficiencies[selected_formula]
            labels_arr = efficiencies["_labels"]
            for lbl in np.unique(labels_arr)[1:]:
                mask = ((labels_arr == lbl) & np.isfinite(eff_map) & (eff_map > 0))
                vals = eff_map[mask]
                if vals.size == 0:
                    continue
                    
                # Calculate whisker positions to identify outliers
                q1 = np.percentile(vals, 25)
                q3 = np.percentile(vals, 75)
                iqr = q3 - q1
                lower_whisker = q1 - 1.5 * iqr
                upper_whisker = q3 + 1.5 * iqr
                
                # Filter out outliers
                inliers = vals[(vals >= lower_whisker) & (vals <= upper_whisker)]
                
                # Apply thresholding to inliers
                hist_vals = inliers[(inliers >= lower_thr) & (inliers <= upper_thr)]
                if hist_vals.size == 0:
                    continue
                    
                counts, _ = np.histogram(hist_vals, bins=edges)
                per_cell_hists.append((counts / inliers.size) * 100)
        if len(per_cell_hists) == 0:
            self.agg_hist_figure.clear()
            self.agg_hist_canvas.draw()
            return
        hist_matrix = np.vstack(per_cell_hists)
        mean_hist = np.mean(hist_matrix, axis=0)
        std_hist = np.std(hist_matrix, axis=0)
        n_cells = hist_matrix.shape[0]
        sem_hist = std_hist / np.sqrt(n_cells)
        centers = (edges[:-1] + edges[1:]) / 2
        self.agg_hist_figure.clear()
        ax = self.agg_hist_figure.add_subplot(111)
        import matplotlib.cm as cm
        group_hists = {}
        for path, efficiencies in self.analysis_results.items():
            if selected_formula not in efficiencies or "_labels" not in efficiencies:
                continue
            gname = self.image_groups.get(path, "Ungrouped")
            eff_map = efficiencies[selected_formula]
            labels_arr = efficiencies["_labels"]
            for lbl in np.unique(labels_arr)[1:]:
                mask = ((labels_arr == lbl) & np.isfinite(eff_map) & (eff_map > 0))
                vals = eff_map[mask]
                if vals.size == 0:
                    continue
                hist_vals = vals[(vals >= lower_thr) & (vals <= upper_thr)]
                if hist_vals.size == 0:
                    continue
                counts, _ = np.histogram(hist_vals, bins=edges)
                pct = (counts / vals.size) * 100
                group_hists.setdefault(gname, []).append(pct)
        colors = cm.tab10.colors
        self.last_histogram_data = {}
        y_max = 0
        for idx, (g, mat) in enumerate(group_hists.items()):
            mat = np.vstack(mat)
            mean = np.mean(mat, axis=0)
            std = np.std(mat, axis=0)
            sem = std / np.sqrt(mat.shape[0])
            error_bars = sem if hasattr(self, 'sem_radio') and self.sem_radio.isChecked() else std
            y_max = max(y_max, np.max(mean + error_bars))
            self.last_histogram_data[g] = (centers, mean, error_bars)
            ax.errorbar(centers, mean, yerr=error_bars, fmt='-o', color=colors[idx%len(colors)], 
                        markersize=3, linewidth=1.2, capsize=3, alpha=0.7, label=g)
        ax.set_xlabel("FRET Efficiency (%)")
        ax.set_ylabel("Pixel Percentage (%)")
        if len(group_hists) > 1:
            ax.legend()
        error_type = "SEM" if hasattr(self, 'sem_radio') and self.sem_radio.isChecked() else "SD"
        title = self.agg_hist_title_edit.text() or f"Aggregate Histogram by Group (Error: {error_type})"
        ax.set_title(title)
        ax.set_xlim(0, 50)
        ax.set_ylim(0, y_max*1.1 if y_max>0 else 1)
        if not hasattr(self, 'agg_export_btn'):
            btn_export = QPushButton("Export Data")
            btn_export.clicked.connect(self.export_aggregate_histogram_data)
            layout = self.agg_hist_figure.canvas.parent().layout()
            layout.addWidget(btn_export)
            self.agg_export_btn = btn_export
        self.agg_hist_figure.tight_layout()
        self.agg_hist_canvas.draw()

    def update_aggregate_stats_table(self, *_):
        selected_formula = self.aggregate_formula_combo.currentText()
        self.aggregate_stats_table.setRowCount(0)
        if not selected_formula or not self.analysis_results:
            return
        stats_rows = []
        lower_thresh = self.lower_threshold_spinbox.value()
        upper_thresh = self.upper_threshold_spinbox.value()
        sorted_items = sorted(self.analysis_results.items(), key=lambda item: os.path.basename(item[0]))
        if self.analysis_results and selected_formula:
            for file_path, efficiencies in sorted_items:
                if "_labels" not in efficiencies or selected_formula not in efficiencies:
                    continue
                labels_arr = efficiencies["_labels"]
                eff_map = efficiencies[selected_formula]
                label_ids = np.unique(labels_arr)
                label_ids = label_ids[label_ids > 0]
                for lbl in label_ids:
                    cell_mask = (labels_arr == lbl)
                    nz_mask = cell_mask & np.isfinite(eff_map) & (eff_map > 0)
                    nz_vals = eff_map[nz_mask]
                    if nz_vals.size == 0:
                        continue
                    in_thresh_mask = nz_mask & (eff_map >= lower_thresh) & (eff_map <= upper_thresh)
                    in_thresh_vals = eff_map[in_thresh_mask]
                    avg_all = np.mean(nz_vals) if nz_vals.size > 0 else 0
                    avg_in_thresh = np.mean(in_thresh_vals) if in_thresh_vals.size > 0 else 0
                    below_thresh = np.sum(nz_vals < lower_thresh)
                    above_thresh = np.sum(nz_vals > upper_thresh)
                    total_pixels = nz_vals.size
                    percent_below = (below_thresh / total_pixels * 100) if total_pixels > 0 else 0
                    percent_above = (above_thresh / total_pixels * 100) if total_pixels > 0 else 0
                    stats_rows.append([
                        f"{os.path.basename(file_path)} | L{lbl}",
                        self.image_groups.get(file_path, "Ungrouped"),
                        f"{avg_all:.1f}",
                        f"{avg_in_thresh:.1f}",
                        f"{percent_below:.1f}%",
                        f"{percent_above:.1f}%",
                        f"{total_pixels:,d}"
                    ])
        self.aggregate_stats_table.setRowCount(len(stats_rows))
        for row_idx, row_data in enumerate(stats_rows):
            for col_idx, cell_data in enumerate(row_data):
                item = QTableWidgetItem(str(cell_data))
                if col_idx >= 2:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.aggregate_stats_table.setItem(row_idx, col_idx, item)
        # Update all plots and visualizations
        self.update_histogram_plot()
        self.update_current_boxplot()
        self.update_aggregate_histogram_plot()
        self.update_aggregate_boxplot()
        
        # Update the representative images group combo box
        self._update_rep_group_combo()
        
        # Don't update representative images automatically - wait for button click
        # self.update_representative_images()  # Removed automatic update

    def get_representative_image(self, group_name):
        """
        Find the image in the group that is closest to the group mean for the currently selected formula.
        
        Returns:
            tuple: (path, formula_used) where path is the path to the representative image
                   and formula_used is the formula that was used to select it
        """
        print(f"\n=== get_representative_image for group: {group_name} ===")
        
        # Get all images in the specified group
        group_images = [path for path, group in self.image_groups.items() 
                       if group == group_name and path in self.analysis_results]
        
        if not group_images:
            print(f"No images found in group: {group_name}")
            return None, None
            
        print(f"Found {len(group_images)} images in group {group_name}")
        
        # Get the currently selected formula
        selected_formula = self.aggregate_formula_combo.currentText()
        print(f"Using selected formula: {selected_formula}")
        
        # Validate if the formula has been analyzed
        if not selected_formula:
            print("No formula selected")
            return None, None
            
        # Check if any image has been analyzed with this formula
        has_analyzed = False
        for path in group_images:
            result = self.analysis_results[path]
            if ('efficiencies' in result and selected_formula in result['efficiencies']) or \
               (selected_formula in result and isinstance(result[selected_formula], np.ndarray)):
                has_analyzed = True
                break
        
        if not has_analyzed:
            print(f"No images have been analyzed with formula: {selected_formula}")
            return None, None
        
        # Collect valid images and their means for the selected formula
        formula_data = []
        
        for path in group_images:
            result = self.analysis_results[path]
            
            # Try to get the efficiency map for the selected formula
            eff = None
            # First try the new data structure
            if 'efficiencies' in result and selected_formula in result['efficiencies']:
                eff = result['efficiencies'][selected_formula]
            # Then try the old data structure
            elif selected_formula in result:
                eff = result[selected_formula]
            
            if eff is not None and isinstance(eff, np.ndarray) and np.any(eff > 0):
                non_zero_eff = eff[eff > 0]
                if len(non_zero_eff) > 0:
                    img_mean = np.mean(non_zero_eff)
                    formula_data.append((path, img_mean, non_zero_eff))
        
        if not formula_data:
            print(f"No valid images found for formula: {selected_formula}")
            # Fallback to first available image with any data
            for path in group_images:
                result = self.analysis_results[path]
                if any(key in result for key in ['efficiencies', 'f', 'd', 'a']):
                    print(f"Falling back to first available image: {os.path.basename(path)}")
                    return path, None
            print("No suitable representative image found in group")
            return None, None
        
        # Calculate overall mean of non-zero values across all images for the selected formula
        all_eff = np.concatenate([data[2] for data in formula_data])
        group_mean = np.mean(all_eff)
        print(f"Group mean for {selected_formula}: {group_mean:.4f}")
        
        # Find image with mean closest to group mean
        min_diff = float('inf')
        best_img_path = None
        
        for path, img_mean, _ in formula_data:
            diff = abs(img_mean - group_mean)
            print(f"  {os.path.basename(path)}: mean={img_mean:.4f}, diff={diff:.4f}")
            if diff < min_diff:
                min_diff = diff
                best_img_path = path
        
        if best_img_path:
            print(f"Selected representative using {selected_formula}: {os.path.basename(best_img_path)} (diff={min_diff:.4f})")
            return best_img_path, selected_formula
        
        # Fallback: return first valid image we can find
        for path in group_images:
            result = self.analysis_results[path]
            if any(key in result for key in ['efficiencies', 'f', 'd', 'a']):
                print(f"Falling back to first available image: {os.path.basename(path)}")
                return path, None
        
        print("No suitable representative image found in group")
        return None, None

    def update_representative_images(self):
        """Update the display of representative images for the selected group."""
        print("\n=== update_representative_images called ===")
        
        # Get the selected group from the combo box
        selected_group = self.rep_group_combo.currentText()
        if not selected_group or selected_group == "Select a group":
            return
            
        print(f"Updating representative images for group: {selected_group}")
        
        # Get the representative image for this group
        rep_image_path, formula_used = self.get_representative_image(selected_group)
        
        if not rep_image_path:
            print(f"No valid representative image found for group: {selected_group}")
            # Clear all frames
            for frame_type, widgets in self.frame_widgets.items():
                fig = widgets['figure']
                fig.clear()
                ax = fig.add_subplot(111)
                ax.set_facecolor('black' if self.current_theme == 'dark' else 'white')
                ax.axis('off')
                
                # Show different messages based on whether we have images but no analysis
                if selected_group in self.image_groups.values():
                    ax.text(0.5, 0.5, f"No analyzed data available\nfor formula: {formula_used if formula_used else 'None'}", 
                           ha='center', va='center', 
                           color='white' if self.current_theme == 'dark' else 'black',
                           fontsize=12)
                else:
                    ax.text(0.5, 0.5, "No data available", 
                           ha='center', va='center', 
                           color='white' if self.current_theme == 'dark' else 'black',
                           fontsize=12)
                widgets['canvas'].draw()
            return
            
        print(f"Using representative image: {os.path.basename(rep_image_path)}")
        if formula_used:
            print(f"Using formula: {formula_used}")
            
        # Get the analysis results for this image
        result = self.analysis_results[rep_image_path]
        
        # Update each frame type
        for frame_type, widgets in self.frame_widgets.items():
            # Clear the current figure
            fig = widgets['figure']
            fig.clear()
            ax = fig.add_subplot(111)
            
            # Set the figure facecolor based on theme
            bg_color = 'black' if self.current_theme == 'dark' else 'white'
            fg_color = 'white' if self.current_theme == 'dark' else 'black'
            
            fig.patch.set_facecolor(bg_color)
            ax.set_facecolor(bg_color)
            
            # Get the image data based on frame type
            img_data = None
            title_suffix = ""
            
            # First check if we have the new data structure with raw channels and efficiency maps
            if 'f' in result and 'd' in result and 'a' in result:
                channel_map = {
                    'fret': ('f', 'FRET Channel'),
                    'donor': ('d', 'Donor Channel'),
                    'acceptor': ('a', 'Acceptor Channel')
                }
                
                if frame_type in channel_map:
                    channel_key, channel_name = channel_map[frame_type]
                    if channel_key in result:
                        img_data = result[channel_key]
                        title_suffix = channel_name
                elif frame_type == 'efficiency':
                    # For efficiency, first try to use the formula that was used to select this image
                    if formula_used and formula_used in result:
                        img_data = result[formula_used]
                        title_suffix = f"{formula_used} Efficiency"
                    else:
                        # Otherwise, find any available efficiency map in the result
                        for key in result:
                            if key not in ['_labels', 'f', 'd', 'a', 'channels'] and isinstance(result[key], np.ndarray):
                                img_data = result[key]
                                title_suffix = f"{key} Efficiency"
                                break
            # Fallback to old data structure for backward compatibility
            else:
                if frame_type == 'efficiency':
                    # Try to get the efficiency map
                    if formula_used and formula_used in result:
                        img_data = result[formula_used]
                        title_suffix = f"{formula_used} Efficiency"
                    else:
                        # Fall back to any available efficiency data
                        for key, value in result.items():
                            if key not in ['_labels', 'f', 'd', 'a'] and isinstance(value, np.ndarray) and value.size > 1:
                                img_data = value
                                title_suffix = f"{key} Efficiency"
                                break
                else:
                    # For channel data, check the root level
                    channel_map = {
                        'fret': 'f',
                        'donor': 'd',
                        'acceptor': 'a'
                    }
                    
                    if frame_type in channel_map:
                        channel_key = channel_map[frame_type]
                        if channel_key in result and isinstance(result[channel_key], np.ndarray):
                            img_data = result[channel_key]
                            title_suffix = channel_name
            
            if img_data is None or not np.any(img_data > 0):
                print(f"No valid {frame_type} data found in result: {list(result.keys())}")
                ax.text(0.5, 0.5, f"No {frame_type} data available", 
                       ha='center', va='center', color=fg_color)
                ax.axis('off')
            else:
                # Plot the image
                if frame_type == 'efficiency':
                    # Values are already in percentage from calculate_fret_efficiency
                    
                    # Adjust the subplot to make room for the colorbar below
                    fig.subplots_adjust(bottom=0.2)
                    
                    # Load custom colormaps
                    self.ramps_colormap = self.load_ramps_colormap()
                    self.orange_colormap = self.load_orange_colormap()
                    self.green_colormap = self.load_green_colormap()
                    self.red_colormap = self.load_red_colormap()
                    
                    # Use the 5_ramps colormap for efficiency
                    cmap = self.ramps_colormap if hasattr(self, 'ramps_colormap') else 'viridis'
                    vmin, vmax = 0, 50  # Fixed range for efficiency (0-50%)
                    
                    # Create the main image plot
                    im = ax.imshow(img_data, cmap=cmap, vmin=vmin, vmax=vmax)
                    
                    # Add colorbar below the image
                    cax = fig.add_axes([0.15, 0.1, 0.7, 0.03])  # [left, bottom, width, height]
                    cbar = fig.colorbar(im, cax=cax, orientation='horizontal')  # Use fig.colorbar instead of plt.colorbar
                    cbar.ax.xaxis.set_tick_params(color=fg_color)
                    
                    # Format tick labels to show percentage
                    ticks = np.linspace(vmin, vmax, 6)  # 5 ticks from 0 to 50%
                    cbar.set_ticks(ticks)
                    cbar.set_ticklabels([f'{int(x)}%' for x in ticks])
                    
                    # Set tick colors
                    plt.setp(plt.getp(cbar.ax.axes, 'xticklabels'), color=fg_color)
                    
                    # Don't set position here - we'll handle it in the layout section below
                else:
                    # Set channel-specific colormaps
                    if frame_type == 'fret':
                        # Orange colormap for FRET channel
                        cmap = self.orange_colormap if hasattr(self, 'orange_colormap') else 'Oranges'
                    elif frame_type == 'donor':
                        # Green colormap for Donor channel
                        cmap = self.green_colormap if hasattr(self, 'green_colormap') else 'Greens'
                    elif frame_type == 'acceptor':
                        # Red colormap for Acceptor channel
                        cmap = self.red_colormap if hasattr(self, 'red_colormap') else 'Reds'
                    else:
                        cmap = 'gray'  # Fallback to grayscale
                        
                    # Validate and normalize image data
                    try:
                        # Ensure we have valid numeric data
                        if not isinstance(img_data, np.ndarray):
                            img_data = np.array(img_data)
                        
                        # Handle NaN values
                        img_data = np.nan_to_num(img_data)
                        
                        # Get valid pixel values (non-zero and non-NaN)
                        valid_pixels = img_data[img_data > 0]
                        
                        # Set default values if no valid pixels
                        if len(valid_pixels) == 0:
                            print(f"Warning: No valid pixels found for {frame_type} frame")
                            vmin, vmax = 0, 1
                        else:
                            # Calculate percentiles with robust handling
                            try:
                                vmin = float(np.percentile(valid_pixels, 1))
                                vmax = float(np.percentile(img_data, 99))
                            except Exception as e:
                                print(f"Error calculating percentiles: {e}")
                                vmin, vmax = 0, np.max(img_data) if np.max(img_data) > 0 else 1
                        
                        # Ensure vmin <= vmax
                        if vmin > vmax:
                            print(f"Warning: Adjusting vmin/vmax for {frame_type} frame")
                            if vmax > 0:
                                vmin = 0
                            else:
                                vmax = 1
                        
                        # Plot with validation
                        im = ax.imshow(img_data, cmap=cmap, vmin=vmin, vmax=vmax)
                        
                    except Exception as e:
                        print(f"Error in image plotting for {frame_type}: {str(e)}")
                        # Fallback to grayscale with default range
                        im = ax.imshow(img_data, cmap='gray', vmin=0, vmax=1)
                        ax.text(0.5, 0.5, 'Error displaying image', 
                               ha='center', va='center', color=fg_color, 
                               transform=ax.transAxes)
                
                # Set title
                ax.set_title(title_suffix, color=fg_color, pad=20)
                ax.axis('off')
                
                # Set tick colors for dark/light theme
                for spine in ax.spines.values():
                    spine.set_edgecolor(fg_color)
                
                # Set up consistent layout for all frames
                if frame_type == 'efficiency':
                    # For efficiency plot with colorbar
                    ax.set_position([0.1, 0.2, 0.8, 0.7])  # Make room for colorbar at bottom
                else:
                    # For all other plots - use the same position as efficiency plot
                    ax.set_position([0.1, 0.2, 0.8, 0.7])  # Match position with efficiency plot
            
            # Update the canvas
            widgets['canvas'].draw()
            
            # Update the export button
            for btn in widgets['group_box'].findChildren(QPushButton):
                if btn.text().startswith("Export"):
                    btn.clicked.disconnect()
                    btn.clicked.connect(lambda checked, p=rep_image_path, t=frame_type: 
                                      self.export_representative_frames(p, t))
        
        # Update the window title with the selected group
        self.setWindowTitle(f"FRET Analysis - {selected_group}")
        
        print("=== Finished updating representative images ===\n")
        self.current_representative_image = rep_image_path

    def _export_single_frame(self, image_path, frame_type, output_dir):
        """Helper method to export a single frame.
        
        Args:
            image_path (str): Path to the image to export
            frame_type (str): Type of frame to export ('efficiency', 'fret', 'donor', 'acceptor')
            output_dir (str): Directory to save the exported file
            
        Returns:
            bool: True if export was successful, False otherwise
        """
        try:
            if image_path not in self.analysis_results:
                print(f"No analysis results found for {os.path.basename(image_path)}")
                return False
                
            result = self.analysis_results[image_path]
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            
            # For channel data, load directly from the raw image
            if frame_type in ['fret', 'donor', 'acceptor']:
                try:
                    # Load the raw image
                    if image_path.lower().endswith(('.tif', '.tiff')):
                        raw_image = tifffile.imread(image_path).squeeze()
                    elif image_path.lower().endswith('.czi'):
                        with czi.CziFile(image_path) as czi_file:
                            raw_image = czi_file.asarray().squeeze()
                    else:
                        print(f"Unsupported file format for direct channel loading: {image_path}")
                        return False
                    
                    # Extract the appropriate channel (assuming order: Labels, FRET, Donor, Acceptor)
                    if frame_type == 'fret' and raw_image.ndim >= 3 and raw_image.shape[0] >= 2:
                        img_data = raw_image[1]  # FRET is the second channel
                        print("Loaded FRET channel directly from raw image")
                    elif frame_type == 'donor' and raw_image.ndim >= 3 and raw_image.shape[0] >= 3:
                        img_data = raw_image[2]  # Donor is the third channel
                        print("Loaded Donor channel directly from raw image")
                    elif frame_type == 'acceptor' and raw_image.ndim >= 3 and raw_image.shape[0] >= 4:
                        img_data = raw_image[3]  # Acceptor is the fourth channel
                        print("Loaded Acceptor channel directly from raw image")
                    else:
                        print(f"Could not extract {frame_type} channel from raw image with shape {raw_image.shape}")
                        return False
                        
                except Exception as e:
                    print(f"Error loading raw image for {frame_type} channel: {e}")
                    return False
            elif frame_type == 'efficiency':
                # Try to get the first available efficiency map
                if 'efficiencies' in result and result['efficiencies']:
                    # Get the first efficiency map from the 'efficiencies' dict
                    formula_name, eff_map = next(iter(result['efficiencies'].items()))
                    img_data = eff_map
                    print(f"Found efficiency data in 'efficiencies' dict with key: {formula_name}")
                else:
                    # Look for efficiency data at root level
                    for key in result:
                        if key not in ['_labels', 'f', 'd', 'a', 'channels'] and isinstance(result[key], np.ndarray):
                            img_data = result[key]
                            print(f"Found efficiency data with key: {key}")
                            break
            
            if img_data is not None:
                # Create output directory if it doesn't exist
                os.makedirs(output_dir, exist_ok=True)
                
                # Generate output filename
                if frame_type == 'efficiency':
                    output_path = os.path.join(output_dir, f"{base_name}_efficiency.tif")
                else:
                    output_path = os.path.join(output_dir, f"{base_name}_{frame_type}.tif")
                
                # Ensure the data is 2D and in the correct format
                if len(img_data.shape) > 2:
                    img_data = img_data.squeeze()
                
                # For efficiency, we want to maintain the original percentage values
                if frame_type == 'efficiency':
                    # Convert to 32-bit float to preserve percentage values (0-100%)
                    scaled = img_data.astype(np.float32)
                else:
                    # For raw channels, just convert to uint16 directly
                    scaled = img_data.astype(np.uint16)
                
                # Save the image with metadata
                tifffile.imwrite(
                    output_path, 
                    scaled,
                    dtype=scaled.dtype,  # Use the data type of the scaled array
                    metadata={'axes': 'YX'},  # Ensure proper dimension order
                    imagej=True  # Add ImageJ metadata for better compatibility
                )
                
                print(f"Exported {frame_type} frame to {output_path}")
                print(f"  - Shape: {img_data.shape}, dtype: {img_data.dtype}")
                print(f"  - Min: {np.min(img_data):.4f}, Max: {np.max(img_data):.4f}, Mean: {np.mean(img_data):.4f}")
                
                return True
                
            print(f"Could not find {frame_type} data in analysis results. Available keys: {list(result.keys())}")
            return False
                
        except Exception as e:
            print(f"Error exporting {frame_type} frame: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def export_representative_frames(self, image_path, frame_type):
        """Export the frames for a representative image.
        
        Args:
            image_path (str): Path to the image to export frames from
            frame_type (str): Type of frame to export ('all', 'efficiency', 'fret', 'donor', 'acceptor')
        """
        # If no image_path provided, try to use the current representative image
        if not image_path:
            if not self.current_representative_image:
                QMessageBox.warning(self, "Export Error", "No image selected for export.")
                return
            image_path = self.current_representative_image
            
        if image_path not in self.analysis_results:
            QMessageBox.warning(self, "Export Error", "No analysis data available for the selected image.")
            return
            
        # Get the output directory
        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return  # User cancelled
            
        # Create a subdirectory for the export
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        export_dir = os.path.join(output_dir, f"{base_name}_export")
        os.makedirs(export_dir, exist_ok=True)
        
        # Get the analysis result
        result = self.analysis_results[image_path]
        
        # Always try to export all four frame types when 'all' is selected
        if frame_type == 'all':
            frames_to_export = ['efficiency', 'fret', 'donor', 'acceptor']
        else:
            frames_to_export = [frame_type]
        
        # Export each frame
        success_count = 0
        for frame in frames_to_export:
            if self._export_single_frame(image_path, frame, export_dir):
                success_count += 1
        
        # Show completion message
        if success_count > 0:
            QMessageBox.information(self, "Export Complete", 
                                 f"Successfully exported {success_count} frame(s) to:\n{export_dir}")
        else:
            QMessageBox.warning(self, "Export Failed", 
                             "No frames were exported. Make sure the image has been analyzed and contains the requested data.")

    def on_cell_click(self, event):
        """Handle mouse click on the cell image to select a cell and show its FFT and histogram."""
        if not hasattr(self, 'current_efficiency_map') or self.current_efficiency_map is None:
            return
            
        if event.inaxes != self.fourier_image_figure.axes[0]:
            return
            
        x, y = int(event.xdata), int(event.ydata)
        
        # Find which cell was clicked
        for cell_id, mask in self.cell_masks.items():
            if y < mask.shape[0] and x < mask.shape[1] and mask[y, x]:
                self.current_cell_id = cell_id
                self.current_cell_mask = mask  # Store the mask for the selected cell
                self.selected_cell_label.setText(f"Selected Cell: {cell_id}")
                self.update_cell_analysis()
                break
    
    def get_cell_efficiency_values(self, cell_id):
        """Get efficiency values for a specific cell."""
        if cell_id not in self.cell_masks or self.current_efficiency_map is None:
            return None
            
        mask = self.cell_masks[cell_id]
        return self.current_efficiency_map[mask]
    
    def update_cell_analysis(self):
        """Update FFT and histogram plots for the currently selected cell."""
        if not self.distribution_enabled:
            return
            
        # Get the cell values
        cell_values = self.get_cell_efficiency_values(self.current_cell_id)
        if cell_values is None or len(cell_values) == 0:
            return
            
        # Update distribution analysis plot
        self.update_distribution_analysis(cell_values)
        
        # Update histogram plot
        self.update_cell_histogram(cell_values)
    
    def show_distribution_popup(self, cell_values):
        """Show the distribution analysis in a popup window."""
        if cell_values is None or len(cell_values) == 0:
            return
            
        # Create a new figure for the popup
        popup_fig = plt.Figure(figsize=(10, 6), facecolor='black' if self.current_theme == 'dark' else 'white')
        ax = popup_fig.add_subplot(111)
        
        # Get max components from UI if available, otherwise default to 3
        try:
            max_components = int(self.max_components_spinbox.value())
        except (AttributeError, ValueError):
            max_components = 3
            
        # Generate the plot and get the GMM model
        gmm, component_assignments = self._plot_distribution_analysis(ax, cell_values, max_components)
        
        # Create and show the popup
        popup = QDialog(self)
        popup.setWindowTitle("Distribution Analysis")
        popup.setMinimumSize(1000, 700)
        
        # Create layout
        layout = QVBoxLayout(popup)
        
        # Create a scroll area for the plot
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create a container widget for the scroll area
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        container_layout.setSpacing(5)
        
        # Create canvas and set size policy
        canvas = FigureCanvas(popup_fig)
        canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Add widgets to layout
        container_layout.addWidget(canvas)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Add buttons
        btn_layout = QHBoxLayout()
        
        # Save figure button
        save_btn = QPushButton("Save Figure")
        save_btn.clicked.connect(lambda: self._save_figure(popup_fig))
        btn_layout.addWidget(save_btn)
        
        # Show components button (only if we have a valid GMM model)
        show_components_btn = None
        if gmm is not None and hasattr(self, 'current_efficiency_map'):
            show_components_btn = QPushButton("Show Component Map")
            # Get the currently selected cell's mask
            current_cell_mask = None
            if hasattr(self, 'current_cell_mask'):
                current_cell_mask = self.current_cell_mask
            
            show_components_btn.clicked.connect(
                lambda: self._show_component_map(
                    self.current_efficiency_map,
                    component_assignments,
                    gmm.n_components,
                    cell_mask=current_cell_mask
                )
            )
            btn_layout.addWidget(show_components_btn)
        
        btn_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(popup.accept)
        btn_layout.addWidget(close_btn)
        
        # Add widgets to main layout
        layout.addLayout(btn_layout)
        
        popup.exec_()
        
    def _show_component_map(self, efficiency_map, component_assignments, n_components, cell_mask=None):
        """Show a popup with the cell image colored by GMM components.
        
        Args:
            efficiency_map: 2D array of efficiency values for the entire image
            component_assignments: 1D array of component indices for the selected cell
            n_components: Number of GMM components
            cell_mask: 2D boolean mask of the same shape as efficiency_map,
                     where True indicates the selected cell's pixels
        """
        if efficiency_map is None or component_assignments is None:
            print("Error: efficiency_map or component_assignments is None")
            return
            
        print(f"efficiency_map shape: {efficiency_map.shape}")
        print(f"component_assignments shape: {component_assignments.shape}")
        
        if cell_mask is None or not isinstance(cell_mask, np.ndarray) or cell_mask.shape != efficiency_map.shape:
            debug_msg = "Invalid cell mask. "
            if cell_mask is None:
                debug_msg += "Cell mask is None."
            elif not isinstance(cell_mask, np.ndarray):
                debug_msg += f"Cell mask is not a numpy array (type: {type(cell_mask)})."
            else:
                debug_msg += f"Cell mask shape {cell_mask.shape} doesn't match efficiency map shape {efficiency_map.shape}."
            
            print(debug_msg)
            QMessageBox.warning(self, "Error", debug_msg)
            return
            
        # Make sure component_assignments has the same length as the number of True values in cell_mask
        n_cell_pixels = np.sum(cell_mask)
        if len(component_assignments) != n_cell_pixels:
            print(f"Warning: component_assignments length ({len(component_assignments)}) "
                  f"doesn't match number of True values in cell_mask ({n_cell_pixels})")
            min_len = min(len(component_assignments), n_cell_pixels)
            component_assignments = component_assignments[:min_len]
            
            # Create a new mask with the correct number of True values
            true_indices = np.where(cell_mask.ravel())[0][:min_len]
            new_mask = np.zeros_like(cell_mask.ravel(), dtype=bool)
            new_mask[true_indices] = True
            cell_mask = new_mask.reshape(cell_mask.shape)
        
        # Create the popup window
        popup = QDialog(self)
        popup.setWindowTitle("GMM Component Analysis")
        popup.setMinimumSize(1200, 600)
        layout = QVBoxLayout(popup)
        
        # Create a new figure for the component map
        fig = plt.Figure(figsize=(12, 6), facecolor='black' if self.current_theme == 'dark' else 'white')
        
        # Create a colormap for the components with default colors
        default_colors = plt.cm.get_cmap('tab10', n_components)
        self.component_colors = [default_colors(i) for i in range(n_components)]
        
        # Create a colored version of the cell with the same shape as efficiency_map
        colored_cell = np.zeros((*efficiency_map.shape, 4))  # RGBA image
        
        # Set background to transparent
        colored_cell[..., 3] = 0  # Alpha channel
        
        # Get the indices of the cell pixels
        cell_indices = np.where(cell_mask)
        
        # Assign colors to each component
        for i in range(n_components):
            # Get the mask for this component
            comp_mask = (component_assignments == i)
            if np.any(comp_mask):
                # Get the color for this component
                color = self.component_colors[i]
                
                # Apply the color to the component pixels
                for dim in range(3):  # RGB channels
                    colored_cell[cell_indices[0][comp_mask], cell_indices[1][comp_mask], dim] = color[dim]
                # Set alpha for this component
                colored_cell[cell_indices[0][comp_mask], cell_indices[1][comp_mask], 3] = 0.8  # Alpha
        
        # Create subplots for side-by-side view
        ax1 = fig.add_subplot(121)
        ax2 = fig.add_subplot(122)
        
        # Show original cell with 5ramps colormap (0-50 range)
        im1 = ax1.imshow(efficiency_map, cmap=self.ramps_colormap, vmin=0, vmax=50)
        ax1.set_title('Original Cell (5ramps colormap, 0-50%)')
        ax1.axis('off')
        
        # Add colorbar for the original image
        cbar = fig.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04)
        cbar.set_label('Efficiency (%)')
        
        # Show colored components with grayscale background (0-50 range)
        ax2.imshow(efficiency_map, cmap='gray', vmin=0, vmax=50, alpha=0.3)
        im_components = ax2.imshow(colored_cell, alpha=0.7)
        ax2.set_title('GMM Components')
        ax2.axis('off')
        
        # Create legend handles for the components
        legend_handles = []
        for i in range(n_components):
            # Create a colored rectangle for the legend
            color = self.component_colors[i]
            rect = plt.Rectangle((0,0), 1, 1, fc=color, alpha=0.8, 
                               edgecolor='black', linewidth=0.5)
            legend_handles.append((rect, f'Component {i+1}'))
        
        # Add the legend to the plot
        ax2.legend([h[0] for h in legend_handles], 
                  [h[1] for h in legend_handles],
                  loc='upper right', 
                  bbox_to_anchor=(1.35, 1.0),
                  frameon=True,
                  framealpha=0.7,
                  edgecolor='0.5')
        
        # Update colors and legend
        def update_colors():
            nonlocal colored_cell, ax2
            
            # Reset the colored cell
            colored_cell[..., :3] = 0
            colored_cell[..., 3] = 0  # Transparent by default
            
            # Re-apply colors to each component
            for i in range(n_components):
                comp_mask = (component_assignments == i)
                if np.any(comp_mask):
                    color = self.component_colors[i]
                    for dim in range(3):  # RGB channels
                        colored_cell[cell_indices[0][comp_mask], cell_indices[1][comp_mask], dim] = color[dim]
                    # Set alpha for this component
                    colored_cell[cell_indices[0][comp_mask], cell_indices[1][comp_mask], 3] = 0.8  # Alpha
            
            # Update the plot
            if len(ax2.images) > 1:  # Make sure the image exists
                ax2.images[1].set_array(colored_cell)
            
            # Update the legend
            if ax2.legend_ is not None:
                ax2.legend_.remove()
            
            # Recreate legend with current colors
            legend_handles = []
            for i in range(n_components):
                color = self.component_colors[i]
                rect = plt.Rectangle((0, 0), 1, 1, fc=color, alpha=0.8, 
                                   edgecolor='black', linewidth=0.5)
                legend_handles.append((rect, f'Component {i+1}'))
            
            ax2.legend([h[0] for h in legend_handles], 
                      [h[1] for h in legend_handles],
                      loc='upper right', 
                      bbox_to_anchor=(1.35, 1.0),
                      frameon=True,
                      framealpha=0.7,
                      edgecolor='0.5')
            
            canvas.draw()
        
        # Add color picker buttons for each component
        color_btn_layout = QHBoxLayout()
        color_btn_layout.setSpacing(5)
        
        for i in range(n_components):
            btn = QPushButton(f'Component {i+1}')
            btn.setStyleSheet(f"background-color: rgb({int(self.component_colors[i][0]*255)}, "
                            f"{int(self.component_colors[i][1]*255)}, "
                            f"{int(self.component_colors[i][2]*255)});"
                            f"color: {'white' if sum(self.component_colors[i][:3])/3 < 0.5 else 'black'};"
                            "border: 1px solid #333; padding: 2px 5px;")
            
            # Create a closure to capture the component index
            def make_color_picker(idx):
                def pick_color():
                    color = QColorDialog.getColor(
                        QColor(*[int(c*255) for c in self.component_colors[idx][:3]]),
                        self,
                        f'Choose color for Component {idx+1}'
                    )
                    if color.isValid():
                        self.component_colors[idx] = (
                            color.red()/255.0,
                            color.green()/255.0,
                            color.blue()/255.0,
                            self.component_colors[idx][3]  # Keep original alpha
                        )
                        # Update button color
                        sender = self.sender()
                        sender.setStyleSheet(
                            f"background-color: {color.name()}; "
                            f"color: {'white' if color.lightness() < 128 else 'black'}; "
                            "border: 1px solid #333; padding: 2px 5px;"
                        )
                        update_colors()
                return pick_color
            
            btn.clicked.connect(make_color_picker(i))
            color_btn_layout.addWidget(btn)
        
        # Add a default colors button
        reset_btn = QPushButton('Reset Colors')
        reset_btn.clicked.connect(lambda: [
            setattr(self, 'component_colors', [default_colors(i) for i in range(n_components)]),
            update_colors(),
            self._show_component_map(
                self.current_efficiency_map,
                component_assignments,
                n_components,
                cell_mask=cell_mask
            )
        ])
        
        color_btn_layout.addStretch()
        color_btn_layout.addWidget(reset_btn)
        
        # Adjust layout to make room for the legend
        fig.tight_layout(rect=[0, 0.1, 1, 0.95])
        
        # Add canvas with the figure
        canvas = FigureCanvas(fig)
        canvas.setStyleSheet(f"background-color: {{'#000000' if self.current_theme == 'dark' else '#ffffff'}};")
        
        # Add navigation toolbar
        toolbar = NavigationToolbar(canvas, self)
        
        # Add buttons
        btn_layout = QHBoxLayout()
        
        # Save figure button
        save_btn = QPushButton("Save Figure")
        save_btn.clicked.connect(lambda: self._save_figure(fig))
        btn_layout.addWidget(save_btn)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(popup.accept)
        btn_layout.addWidget(close_btn)
        
        # Add widgets to main layout
        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        
        # Add a container widget for the color picker buttons with a scroll area
        color_container = QWidget()
        color_container.setLayout(color_btn_layout)
        
        # Add a scroll area for the color buttons in case there are many components
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(color_container)
        scroll.setMinimumHeight(80)  # Set a minimum height for the scroll area
        
        # Add all widgets to the main layout
        layout.addWidget(scroll)  # Color picker buttons with scroll
        layout.addLayout(btn_layout)  # Save/Close buttons
        
        # Show the popup
        popup.exec_()
    
    def _save_figure(self, figure):
        """Save the figure to a file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Figure", "", "PNG (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if file_path:
            figure.savefig(file_path, bbox_inches='tight', dpi=300)
    
    def _plot_distribution_analysis(self, ax, cell_values, max_components=3):
        """Create the distribution analysis plot on the given axes.
        
        Returns:
            tuple: (gmm_model, component_assignments) if successful, (None, None) otherwise
        """
        if not self.distribution_enabled:
            return None, None
            
        if cell_values.size < 2:
            ax.text(0.5, 0.5, 'Not enough data points for analysis', 
                   ha='center', va='center', transform=ax.transAxes)
            return None, None
            
        try:
            # Filter out any NaN or infinite values
            valid_values = cell_values[np.isfinite(cell_values)]
            if valid_values.size < 2:
                raise ValueError("Not enough valid data points")
                
            # Create histogram data with more bins for better resolution
            n_bins = min(100, max(50, len(valid_values) // 50))  # Dynamic bin count based on data size
            hist, bin_edges = np.histogram(valid_values, bins=n_bins, density=True)
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
            
            # Adaptive smoothing based on data range and number of points
            data_range = np.max(valid_values) - np.min(valid_values)
            smoothing = max(0.5, min(2.0, 2.0 * (10.0 / data_range)))
            smoothed = gaussian_filter1d(hist, sigma=smoothing)
            
            # Find peaks to estimate number of components
            min_peak_height = max(smoothed) * 0.1  # Minimum peak height as fraction of max height
            min_peak_distance = max(5, int(len(smoothed) * 0.05))  # Minimum distance between peaks
            peaks, _ = find_peaks(smoothed, height=min_peak_height, distance=min_peak_distance)
            
            # Use at least 1 and at most max_components
            n_components = min(max(1, len(peaks)), max_components)
            
            # If we have at least 2 peaks but GMM only finds 1, force it to use 2
            if len(peaks) >= 2 and n_components == 1:
                n_components = 2
            
            # Reshape for GMM
            X = valid_values.reshape(-1, 1)
            
            # Initialize means based on peak positions if we found any
            if len(peaks) > 0:
                peak_values = bin_centers[peaks[:n_components]]
                means_init = np.array(peak_values).reshape(-1, 1)
                
                # If we have fewer peaks than components, add random means
                if len(means_init) < n_components:
                    n_extra = n_components - len(means_init)
                    extra_means = np.random.uniform(
                        low=np.min(valid_values), 
                        high=np.max(valid_values),
                        size=(n_extra, 1)
                    )
                    means_init = np.vstack([means_init, extra_means])
                
                # Ensure means are sorted
                means_init = np.sort(means_init, axis=0)
            else:
                means_init = 'k-means++'
            
            # Fit Gaussian Mixture Model with better initialization
            gmm = GaussianMixture(
                n_components=n_components,
                means_init=means_init if isinstance(means_init, np.ndarray) else 'k-means++',
                random_state=42,
                n_init=5,  # Try multiple initializations
                max_iter=500,  # More iterations for convergence
                tol=1e-4  # Tighter tolerance
            )
            gmm.fit(X)
            
            # Generate points for plotting the GMM components
            x = np.linspace(0, 100, 1000).reshape(-1, 1)
            logprob = gmm.score_samples(x)
            responsibilities = gmm.predict_proba(x)
            pdf = np.exp(logprob)
            pdf_individual = responsibilities * pdf[:, np.newaxis]
            
            # Plot the histogram with more bins for better visualization
            ax.hist(valid_values, bins=n_bins, density=True, alpha=0.3, color='gray', 
                   label='Efficiency Distribution')
            
            # Plot the smoothed histogram
            ax.plot(bin_centers, smoothed, 'k-', linewidth=1.5, 
                   label='Smoothed Distribution')
            
            # Plot the individual components
            colors = ['#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
            for i in range(n_components):
                ax.plot(x, pdf_individual[:, i], '--', 
                       color=colors[i % len(colors)],
                       label=f'Component {i+1} (μ={gmm.means_[i,0]:.1f}%)')
            
            # Plot the overall GMM fit
            ax.plot(x, pdf, 'k-', linewidth=2, label='GMM Fit')
            
            # Add vertical lines for component means
            for i, mean in enumerate(gmm.means_):
                ax.axvline(mean[0], color=colors[i % len(colors)], 
                          linestyle=':', alpha=0.7)
            
            ax.set_title('Efficiency Distribution Decomposition', fontsize=12, fontweight='bold')
            ax.set_xlabel('FRET Efficiency (%)', fontsize=10)
            ax.set_ylabel('Density', fontsize=10)
            ax.legend(loc='upper right', fontsize=9)
            ax.grid(True, alpha=0.3)
            
            # Set x-axis limits based on data range
            x_range = np.max(valid_values) - np.min(valid_values)
            ax.set_xlim(max(0, np.min(valid_values) - 0.1*x_range),
                       min(100, np.max(valid_values) + 0.1*x_range))
            
            # Add statistics as text
            stats_text = []
            for i in range(n_components):
                stats_text.append(f"Component {i+1}: μ = {gmm.means_[i,0]:.2f}%, σ = {np.sqrt(gmm.covariances_[i,0,0]):.2f}, w = {gmm.weights_[i]:.2f}")
            
            stats_text = "\n".join(stats_text)
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   verticalalignment='top', fontsize=8, bbox=dict(facecolor='white', alpha=0.7))
            
            # Get component assignments for all values (including filtered ones)
            all_values = cell_values.reshape(-1, 1)
            component_assignments = gmm.predict(all_values).reshape(cell_values.shape)
            
            return gmm, component_assignments
            
        except Exception as e:
            ax.clear()
            ax.text(0.5, 0.5, f'Error in analysis: {str(e)}', 
                   ha='center', va='center', transform=ax.transAxes,
                   color='red')
            return None, None
    
    def update_distribution_analysis(self, cell_values):
        """Update the distribution analysis plot in the main tab."""
        if not self.distribution_enabled:
            return
            
        self.fft_figure.clear()
        ax = self.fft_figure.add_subplot(111)
        
        # Get max components from UI if available, otherwise default to 3
        try:
            max_components = int(self.max_components_spinbox.value())
        except (AttributeError, ValueError):
            max_components = 3
        
        if cell_values is None or len(cell_values) == 0 or cell_values.size < 2:
            ax.text(0.5, 0.5, 'Not enough data points for analysis', 
                   ha='center', va='center', transform=ax.transAxes)
            self.fft_canvas.draw()
            return
            
        # Create the plot in the main tab
        plot_success = self._plot_distribution_analysis(ax, cell_values, max_components)
        
        # If plot was successful, add a button to show the popup
        if plot_success and hasattr(self, 'show_distribution_popup'):
            # Add a small button in the top-right corner to show the popup
            popup_btn = QToolButton(self.fft_canvas)
            popup_btn.setText("⛶")  # Popout icon
            popup_btn.setToolTip("Open in popup window")
            popup_btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #888;
                    border-radius: 2px;
                    padding: 2px;
                    background: rgba(255, 255, 255, 0.7);
                }
                QToolButton:hover {
                    background: rgba(200, 230, 255, 0.9);
                }
            """)
            
            # Position the button in the top-right corner of the canvas
            def position_popup_btn():
                size = popup_btn.sizeHint()
                x = self.fft_canvas.width() - size.width() - 10
                popup_btn.move(x, 10)
            
            # Connect the button click to show the popup
            popup_btn.clicked.connect(lambda: self.show_distribution_popup(cell_values))
            
            # Show the button and position it
            popup_btn.show()
            self.fft_canvas.resizeEvent = lambda e: (FigureCanvas.resizeEvent(self.fft_canvas, e), position_popup_btn())
            position_popup_btn()
        
        # Update the canvas
        self.fft_figure.tight_layout()
        self.fft_canvas.draw()
    
    def update_cell_histogram(self, cell_values):
        """Update the histogram plot for the given cell values."""
        if not self.distribution_enabled:
            return
            
        self.cell_hist_figure.clear()
        ax = self.cell_hist_figure.add_subplot(111)
        
        # Create histogram of cell efficiency values
        n, bins, patches = ax.hist(cell_values, bins=20, alpha=0.7, 
                                 color='blue', edgecolor='black')
        
        # Add vertical line at mean
        mean_val = np.mean(cell_values)
        ax.axvline(mean_val, color='red', linestyle='dashed', linewidth=1, 
                  label=f'Mean: {mean_val:.2f}%')
        
        ax.set_xlabel('Efficiency (%)')
        ax.set_ylabel('Frequency')
        ax.set_title('Cell Efficiency Distribution')
        ax.legend()
        
        # Update the canvas
        self.cell_hist_canvas.draw()
    
    def update_plot_display(self, *args):
        """Update the display when a new image is selected."""
        # Check if we have a selected image
        if not self.image_list.currentItem():
            return
            
        current_path = self.image_list.currentItem().text()
        
        # Check if we have analysis results for this image
        if current_path not in self.analysis_results:
            # Clear the display if no analysis results
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.text(0.5, 0.5, 'Please run analysis first', 
                   ha='center', va='center', 
                   color='white' if self.current_theme == 'dark' else 'black')
            ax.axis('off')
            self.canvas.draw()
            return
            
        result = self.analysis_results[current_path]
        
        # Get the selected formula
        formula = self.fourier_formula_combo.currentText()
        if formula in result:
            self.current_efficiency_map = result[formula]
        elif 'efficiencies' in result and formula in result['efficiencies']:
            self.current_efficiency_map = result['efficiencies'][formula]
        else:
            self.current_efficiency_map = None
            
        # Get cell masks if available
        self.cell_masks = {}
        if '_labels' in result:
            self.cell_masks = {}
            labels = result['_labels']
            for cell_id in np.unique(labels):
                if cell_id > 0:  # Skip background
                    self.cell_masks[cell_id] = (labels == cell_id)
        
        # Update the image display
        self.update_fourier_image_display()
        
    def _find_analysis_result(self, path):
        """Find analysis results by matching either full path, just filename, or grouped image."""
        if not path or not self.analysis_results:
            print(f"No path or analysis results. Path: {path}, Results: {bool(self.analysis_results)}")
            return None
            
        # Debug: Print available analysis results
        print(f"Looking up analysis result for path: {path}")
        print(f"Available analysis results: {list(self.analysis_results.keys())}")
        
        # Try exact match first
        if path in self.analysis_results:
            print(f"Found exact match for {path}")
            return self.analysis_results[path]
            
        # Check if this is a grouped image path (contains ' (Group: ')
        if ' (Group: ' in path:
            # Extract the base path before the group info
            base_path = path.split(' (Group: ')[0]
            print(f"Processing grouped image path. Base path: {base_path}")
            if base_path in self.analysis_results:
                print(f"Found match for base path: {base_path}")
                return self.analysis_results[base_path]
            
        # Get just the filename part
        filename = os.path.basename(path)
        print(f"Trying to match by filename: {filename}")
        
        if not filename:
            return None
            
        # Try matching by filename
        for full_path, result in self.analysis_results.items():
            if os.path.basename(full_path) == filename:
                print(f"Matched by filename: {filename} -> {full_path}")
                return result
                
        # Try matching by path ending
        for full_path, result in self.analysis_results.items():
            if full_path.endswith(path) or path.endswith(full_path):
                print(f"Matched by path ending: {path} -> {full_path}")
                return result
                
        # Try case-insensitive match
        for full_path, result in self.analysis_results.items():
            if full_path.lower() == path.lower():
                print(f"Matched case-insensitive: {path} -> {full_path}")
                return result
                
        # If we have image groups, try to find a match in the representative images
        if hasattr(self, 'image_groups') and self.image_groups:
            print("Checking image groups for match...")
            for group_name, group_data in self.image_groups.items():
                if 'representative' in group_data and group_data['representative'] == path:
                    print(f"Found matching representative in group {group_name}")
                    # Try to find the actual analysis result for this representative
                    for img_path in group_data.get('images', []):
                        if img_path in self.analysis_results:
                            print(f"Using analysis results from group member: {img_path}")
                            return self.analysis_results[img_path]
        
        print(f"No match found for path: {path}")
        return None
        
    def update_fourier_display(self):
        """Update the Distribution Analysis tab display with current image and formula."""
        if not self.distribution_enabled:
            return
            
        print("\n=== update_fourier_display called ===")
        
        # Make sure we have the list widget and it has a selection
        if not hasattr(self, 'image_list_widget'):
            print("No image_list_widget found")
            return
            
        current_item = self.image_list_widget.currentItem()
        if not current_item:
            print("No current item selected")
            # Try to select the first item if none is selected
            if self.image_list_widget.count() > 0:
                print("Selecting first item in the list")
                self.image_list_widget.setCurrentItem(self.image_list_widget.item(0))
                current_item = self.image_list_widget.currentItem()
                if not current_item:
                    print("Failed to select first item")
                    return
            else:
                print("No items in the list to select")
                return
        
        current_path = current_item.text()
        print(f"Current path: {current_path}")
        
        # Check if we have analysis results
        if not self.analysis_results:
            print("No analysis results available")
            # Clear the display if no analysis results
            if hasattr(self, 'fourier_figure'):
                self.fourier_figure.clear()
                ax = self.fourier_figure.add_subplot(111)
                ax.text(0.5, 0.5, 'Please run analysis first', 
                       ha='center', va='center', 
                       color='white' if self.current_theme == 'dark' else 'black')
                ax.axis('off')
                self.fourier_canvas.draw()
            return
        
        # Get the actual file path from the item's data if available
        file_path = current_item.data(Qt.UserRole) if hasattr(current_item, 'data') else current_path
        print(f"Looking up analysis for file path: {file_path}")
            
        # Find matching analysis result
        result = self._find_analysis_result(file_path)
        if result is None:
            # Try one more time with the display text if we were using the data
            if file_path != current_path:
                print(f"No match found with data, trying display text: {current_path}")
                result = self._find_analysis_result(current_path)
                
        if result is None:
            print(f"No analysis results found for: {current_path}")
            print(f"Available analysis results: {list(self.analysis_results.keys())}")
            # Clear the display if no matching result found
            if hasattr(self, 'fourier_figure'):
                self.fourier_figure.clear()
                ax = self.fourier_figure.add_subplot(111)
                ax.text(0.5, 0.5, 'No matching analysis results', 
                       ha='center', va='center', 
                       color='white' if self.current_theme == 'dark' else 'black')
                ax.axis('off')
                self.fourier_canvas.draw()
            return
            
        # Get the selected formula
        if not hasattr(self, 'fourier_formula_combo') or self.fourier_formula_combo.count() == 0:
            print("No formula combo box or no formulas available")
            return
            
        formula = self.fourier_formula_combo.currentText()
        print(f"Selected formula: {formula}")
        
        # Try to get efficiency map from various possible locations
        self.current_efficiency_map = None
        efficiency_sources = [
            (result, formula),
            (result.get('efficiencies', {}), formula),
            (result.get('efficiency_maps', {}), formula),
            (result, 'efficiency_map'),
            (result, 'efficiency')
        ]
        
        for source, key in efficiency_sources:
            if source and key in source and isinstance(source[key], np.ndarray):
                self.current_efficiency_map = source[key]
                print(f"Found efficiency map in {key} with shape {self.current_efficiency_map.shape}")
                break
                
        if self.current_efficiency_map is None:
            print(f"Could not find efficiency map for formula: {formula}")
            print("Available keys in result:")
            for key, value in result.items():
                if isinstance(value, (np.ndarray, dict)):
                    print(f"- {key}: {type(value).__name__}")
                else:
                    print(f"- {key}: {type(value).__name__}")
            # Clear the display if no efficiency map found
            if hasattr(self, 'fourier_figure'):
                self.fourier_figure.clear()
                ax = self.fourier_figure.add_subplot(111)
                ax.text(0.5, 0.5, 'No efficiency map found', 
                       ha='center', va='center', 
                       color='white' if self.current_theme == 'dark' else 'black')
                ax.axis('off')
                self.fourier_canvas.draw()
            return
            
        # Get cell masks if available
        self.cell_masks = {}
        if 'cell_masks' in result:
            self.cell_masks = result['cell_masks']
            print(f"Found {len(self.cell_masks)} cell masks in 'cell_masks'")
        elif '_labels' in result:
            labels = result['_labels']
            if isinstance(labels, np.ndarray):
                for cell_id in np.unique(labels):
                    if cell_id > 0:  # Skip background
                        self.cell_masks[cell_id] = (labels == cell_id)
                print(f"Generated {len(self.cell_masks)} cell masks from '_labels'")
        
        # Update the display
        print("Updating Distribution Analysis image display...")
        self.update_fourier_image_display()
        
        # Update cell analysis if a cell is selected
        if hasattr(self, 'current_cell_id') and self.current_cell_id is not None:
            print(f"Updating analysis for cell {self.current_cell_id}")
            self.update_cell_analysis()
    
    def update_fourier_image_display(self):
        """Update the image display in the Distribution Analysis tab."""
        if not self.distribution_enabled:
            return
            
        print("\n=== update_fourier_image_display called ===")
        
        if not hasattr(self, 'fourier_image_figure') or self.fourier_image_figure is None:
            print("No fourier_image_figure found")
            return
            
        # Clear the figure
        self.fourier_image_figure.clear()
        
        if self.current_efficiency_map is None:
            print("No efficiency map available for display")
            ax = self.fourier_image_figure.add_subplot(111)
            ax.text(0.5, 0.5, 'No efficiency data available', 
                   ha='center', va='center', transform=ax.transAxes)
            ax.axis('off')
        else:
            print(f"Displaying efficiency map with shape: {self.current_efficiency_map.shape}")
            # Plot the efficiency map with cell outlines
            ax = self.fourier_image_figure.add_subplot(111)
            
            try:
                # Ensure we have valid data
                if not isinstance(self.current_efficiency_map, np.ndarray) or self.current_efficiency_map.size == 0:
                    raise ValueError("No valid efficiency map data to display")
                    
                # Plot the efficiency map
                cmap = getattr(self, 'ramps_colormap', 'viridis')
                
                # Ensure the data is in the correct format
                data = np.nan_to_num(self.current_efficiency_map, nan=0.0, posinf=50.0, neginf=0.0)
                data = np.clip(data, 0, 50)  # Clip to 0-50 range
                
                # Plot with aspect='auto' to ensure it fills the available space
                im = ax.imshow(data, cmap=cmap, vmin=0, vmax=50, aspect='auto')
                
                # Add cell outlines if available
                if hasattr(self, 'cell_masks') and self.cell_masks:
                    from skimage import measure
                    for cell_id, mask in self.cell_masks.items():
                        # Find contours of the cell
                        contours = measure.find_contours(mask, 0.5)
                        for contour in contours:
                            ax.plot(contour[:, 1], contour[:, 0], linewidth=0.5, color='red')
                
                # Add colorbar
                cbar = self.fourier_image_figure.colorbar(im, ax=ax, orientation='horizontal', 
                                                        pad=0.2, aspect=40)
                cbar.set_label('Efficiency (%)')
                
                # Format colorbar ticks
                ticks = np.linspace(0, 50, 6)
                cbar.set_ticks(ticks)
                cbar.set_ticklabels([f'{int(x)}' for x in ticks])
                
                # Set title
                if hasattr(self, 'fourier_formula_combo') and self.fourier_formula_combo.count() > 0:
                    formula = self.fourier_formula_combo.currentText()
                    ax.set_title(f'{formula} Efficiency Map')
                else:
                    ax.set_title('Efficiency Map')
                    
            except Exception as e:
                print(f"Error in update_fourier_image_display: {str(e)}")
                ax = self.fourier_image_figure.add_subplot(111)
                ax.text(0.5, 0.5, 'Error displaying image', 
                       ha='center', va='center', transform=ax.transAxes)
                ax.axis('off')
        
        # Force a redraw of the canvas
        self.fourier_image_canvas.draw()
        
        # Update the canvas
        self.fourier_image_canvas.draw()
    
    def on_analysis_completed(self, image_path):
        """Handle analysis completion by updating the Distribution Analysis tab."""
        if not self.distribution_enabled:
            return
            
        if hasattr(self, 'fourier_formula_combo') and self.fourier_formula_combo.count() > 0:
            self.update_fourier_display()
    
    def on_distribution_enabled_changed(self, state):
        """Handle changes to the distribution analysis enable checkbox."""
        self.distribution_enabled = (state == Qt.Checked)
        
        # Update all dependent components
        self.fourier_formula_combo.setEnabled(self.distribution_enabled)
        self.max_components_spinbox.setEnabled(self.distribution_enabled)
        self.update_gmm_btn.setEnabled(self.distribution_enabled)
        
        # Clear plots if disabled
        if not self.distribution_enabled:
            if hasattr(self, 'fft_figure'):
                self.fft_figure.clear()
                self.fft_canvas.draw()
            if hasattr(self, 'fourier_image_figure'):
                self.fourier_image_figure.clear()
                self.fourier_image_canvas.draw()
            if hasattr(self, 'excluded_cells_label'):
                self.excluded_cells_label.setText(f"Excluded Cells: 0")
            if hasattr(self, 'excluded_cells_ratio_label'):
                self.excluded_cells_ratio_label.setText(f"Excluded Cells: 0")
            self.current_cell_id = None
            self.selected_cell_label.setText("Selected Cell: None")
            
    def on_fourier_formula_changed(self):
        """Update the display when the Distribution Analysis formula is changed."""
        if not self.distribution_enabled:
            return
            
        if not hasattr(self, 'fourier_image_figure'):
            return
            
        # Get the current image path
        current_item = self.image_list_widget.currentItem()
        if not current_item:
            return
            
        image_path = current_item.data(Qt.UserRole)
        if not image_path or image_path not in self.analysis_results:
            return
            
        # Get the analysis results for the current image
        result = self.analysis_results[image_path]
        
        # Update the display with the new formula
        self.update_fourier_display()
        
        # Debug: Print the available keys in the result
        print("\n=== Formula changed. Available data in result: ===")
        for key, value in result.items():
            if isinstance(value, np.ndarray):
                print(f"- {key}: ndarray with shape {value.shape}")
            else:
                print(f"- {key}: {type(value).__name__}")
        
        # Update cell masks if labels are available
        if '_labels' in result and isinstance(result['_labels'], np.ndarray):
            self.cell_masks = {}
            labels = result['_labels']
            for cell_id in np.unique(labels):
                if cell_id > 0:  # Skip background
                    self.cell_masks[cell_id] = (labels == cell_id)
            print(f"Found {len(self.cell_masks)} cell masks")
        
        # Update the display
        print("Updating Distribution Analysis image display...")
        self.update_fourier_image_display()
        
        # If we have a cell selected, update its analysis
        if hasattr(self, 'current_cell_id') and self.current_cell_id is not None:
            print(f"Updating analysis for cell {self.current_cell_id}")
            self.update_cell_analysis()
    
    def update_fourier_formula_list(self):
        """Update the formula list in the Distribution Analysis tab to match the main tab."""
        if not hasattr(self, 'fourier_formula_combo'):
            return
            
        current_formula = self.fourier_formula_combo.currentText()
        self.fourier_formula_combo.clear()
        
        # Get formulas from the main formula checkboxes
        formulas = list(self.formula_checkboxes.keys())
        self.fourier_formula_combo.addItems(formulas)
        
        # Try to restore the previous selection
        if current_formula in formulas:
            index = self.fourier_formula_combo.findText(current_formula)
            if index >= 0:
                self.fourier_formula_combo.setCurrentIndex(index)
    
    def on_image_selection_changed(self, current, previous):
        """Handle image selection changes in the list widget."""
        if current is not None:
            self.update_plot_display()
    
    def update_plot_display(self, *args):
        """Update all plots when a new image is selected."""
        # Update the main display
        current_item = self.image_list_widget.currentItem()
        self.current_stats_table.setRowCount(0)
        
        # Update the Distribution Analysis tab if it exists
        if hasattr(self, 'fourier_image_figure'):
            self.update_fourier_formula_list()
            self.current_cell_id = None
            self.update_fourier_display()
            
            # Force an update of the figure
            if hasattr(self, 'fourier_image_canvas'):
                self.fourier_image_canvas.draw()
        if not current_item or not self.analysis_results:
            self.figure.clear()
            self.canvas.draw()
            return
            
        file_path = self.image_paths[self.image_list_widget.row(current_item)]
        if file_path not in self.analysis_results:
            self.figure.clear()
            self.canvas.draw()
            return
        selected_formulas = [name for name, cb in self.formula_checkboxes.items() if cb.isChecked()]
        efficiencies = self.analysis_results[file_path]
        # Update excluded cell count displays
        excluded_count = efficiencies.get("_excluded_count", 0)
        if hasattr(self, 'excluded_cells_label'):
            self.excluded_cells_label.setText(f"Excluded Cells: {excluded_count}")
        if hasattr(self, 'excluded_cells_ratio_label'):
            self.excluded_cells_ratio_label.setText(f"Excluded Cells: {excluded_count}")
        self.figure.clear()
        num_formulas = len(selected_formulas)
        axes = self.figure.subplots(1, num_formulas, squeeze=False)[0] if num_formulas > 0 else []
        if isinstance(axes, np.ndarray):
            axes = axes.tolist()
        if num_formulas > 0:
            self.figure.tight_layout(pad=3.0)
        lower_thr = self.lower_threshold_spinbox.value()
        upper_thr = self.upper_threshold_spinbox.value()
        stats_rows = []
        for i, formula_name in enumerate(selected_formulas):
            if formula_name not in efficiencies:
                if len(axes) > 0:
                    ax = axes[i]
                    ax.set_title(f"{formula_name}\n(No data)")
                    ax.set_axis_off()
                continue
            raw_eff_map = efficiencies[formula_name]
            display_eff_map = raw_eff_map.copy()
            display_eff_map[np.isnan(display_eff_map)] = 0
            display_eff_map[display_eff_map < lower_thr] = 0
            display_eff_map[display_eff_map > upper_thr] = upper_thr
            ax = axes[i]
            im = ax.imshow(display_eff_map, cmap=self.ramps_colormap, vmin=0, vmax=50)
            cbar = self.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            cbar.set_ticks([0, 10, 20, 30, 40, 50])
            cbar.set_label('Efficiency (%)')
            ax.set_title(formula_name)
            ax.set_axis_off()
            valid_mask = np.isfinite(raw_eff_map) & (raw_eff_map > 0)
            valid_vals = raw_eff_map[valid_mask]
            in_threshold_mask = (valid_vals >= lower_thr) & (valid_vals <= upper_thr)
            in_threshold_vals = valid_vals[in_threshold_mask]
            avg_all_nz = np.mean(valid_vals) if valid_vals.size > 0 else 0
            avg_in_thresh = np.mean(in_threshold_vals) if in_threshold_vals.size > 0 else 0
            total_nz = valid_vals.size
            below_thresh = np.sum(valid_vals < lower_thr)
            above_thresh = np.sum(valid_vals > upper_thr)
            in_thresh = in_threshold_vals.size
            total = max(total_nz, 1)
            percent_below = (below_thresh / total) * 100
            percent_above = (above_thresh / total) * 100
            stats_rows.append([
                formula_name,
                f"{avg_all_nz:.1f}",
                f"{avg_in_thresh:.1f}",
                f"{percent_below:.1f}%",
                f"{percent_above:.1f}%",
                str(total_nz)
            ])
        self.canvas.draw()
        self.current_stats_table.setRowCount(len(stats_rows))
        for row_idx, row_data in enumerate(stats_rows):
            for col_idx, cell_data in enumerate(row_data):
                self.current_stats_table.setItem(row_idx, col_idx, QTableWidgetItem(str(cell_data)))
        self.binned_stats_table.setRowCount(0)
        if "_labels" in efficiencies:
            labels_arr = efficiencies["_labels"]
            label_ids = np.unique(labels_arr)
            label_ids = label_ids[label_ids > 0]
            rows = []
            for lbl in label_ids:
                cell_mask = labels_arr == lbl
                for formula_name in selected_formulas:
                    if formula_name not in efficiencies:
                        continue
                    eff_map = efficiencies[formula_name]
                    mask = (cell_mask & np.isfinite(eff_map) & (eff_map > 0))
                    vals = eff_map[mask]
                    if vals.size == 0:
                        continue
                    below_thresh = vals[vals < lower_thr].size
                    above_thresh = vals[vals > upper_thr].size
                    in_threshold_vals = vals[(vals >= lower_thr) & (vals <= upper_thr)]
                    avg_all_nz = np.mean(vals) if vals.size > 0 else 0
                    avg_in_thresh = np.mean(in_threshold_vals) if in_threshold_vals.size > 0 else 0
                    total_pixels = vals.size
                    percent_below = (below_thresh / total_pixels * 100) if total_pixels > 0 else 0
                    percent_above = (above_thresh / total_pixels * 100) if total_pixels > 0 else 0
                    rows.append([
                        str(int(lbl)),
                        formula_name,
                        f"{avg_all_nz:.1f}",
                        f"{avg_in_thresh:.1f}",
                        f"{percent_below:.1f}%",
                        f"{percent_above:.1f}%",
                        f"{total_pixels:,d}"
                    ])
            column_headers = ["Label", "Formula", "Avg E (All)", "Avg E (btw thresh %)", "% < Lower", "% > Upper", "# Pixels"]
            self.binned_stats_table.setColumnCount(len(column_headers))
            self.binned_stats_table.setHorizontalHeaderLabels(column_headers)
            self.binned_stats_table.setRowCount(len(rows))
            for r, row_data in enumerate(rows):
                for c, val in enumerate(row_data):
                    self.binned_stats_table.setItem(r, c, QTableWidgetItem(str(val)))
                    if c >= 2:
                        item = self.binned_stats_table.item(r, c)
                        if item:
                            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def reset_tab(self):
        """Reset the FRET tab to its initial clean state."""
        # 1. Reset basic parameters, images, stats, and main figure
        self.reset_parameters()

        # 2. Clear ALL additional matplotlib figures
        for attr in [
            'hist_figure', 'box_figure', 'agg_hist_figure', 'agg_box_figure',
            'fft_figure', 'fourier_figure', 'fourier_image_figure', 'cell_hist_figure'
        ]:
            fig = getattr(self, attr, None)
            if fig is not None:
                fig.clear()

        # 3. Redraw canvases so cleared figures are shown instantly
        for attr in [
            'hist_canvas', 'box_canvas', 'agg_hist_canvas', 'agg_box_canvas',
            'fft_canvas', 'fourier_image_canvas', 'cell_hist_canvas', 'canvas'
        ]:
            canvas = getattr(self, attr, None)
            if canvas is not None:
                canvas.draw()

        # 4. Clear group info and refresh combo boxes
        self.image_groups.clear()
        # Only call _update_group_combo if the combo box exists
        if hasattr(self, 'group_combo'):
            self._update_group_combo()
        if hasattr(self, 'rep_group_combo'):
            self._update_rep_group_combo()
            self.rep_group_combo.setCurrentIndex(-1)

        # 5. Clear current representative image and reinitialize UI
        self.current_representative_image = None
        
        if hasattr(self, 'frame_widgets'):
            # Clear any existing frames
            for frame_type, widgets in self.frame_widgets.items():
                # Clear the figure
                fig = widgets['figure']
                fig.clear()
                
                # Set up a clean axis with instructions
                ax = fig.add_subplot(111)
                ax.set_facecolor('black' if self.current_theme == 'dark' else 'white')
                ax.axis('off')
                ax.text(0.5, 0.5, "Click 'Find Rep Image' to display", 
                       ha='center', va='center', 
                       color='white' if self.current_theme == 'dark' else 'black',
                       fontsize=12)
                
                # Force redraw
                widgets['canvas'].draw()
        
        # 6. Disable export representative button
        if hasattr(self, 'export_rep_btn'):
            self.export_rep_btn.setEnabled(False)

        # 7. Disable analysis UI until new images added
        self.update_tab_state(False)

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
