"""
Intensity / Densitometry analysis tab.

Object-based intensiometric analysis of segmented cells for fluorophore-tagged
proteins: per-cell mean/median/std, area, integrated density, background-
corrected total cell fluorescence (CTCF), and — when a membrane (outline) mask
is available — membrane-vs-interior enrichment and the membrane fraction of the
total signal. This is the standard read-out for asking "did the tagged protein
localize where expected (e.g. the membrane)?".

Input stacks come from the Segmentation tab's "Segment both" mode, laid out as
``[outline, filled, ...raw channels]``, but the layout is fully user-declared via
this tab's own channel registry so hand-made segmented stacks work too.
"""

import os
import csv

import numpy as np
import tifffile
from scipy.ndimage import binary_erosion
from scipy import stats as sp_stats

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QSpinBox, QDoubleSpinBox,
    QCheckBox, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QTabWidget,
    QFileDialog, QMessageBox, QDialog, QTextEdit, QSplitter, QHeaderView,
    QAbstractItemView, QSizePolicy,
)
from PyQt5.QtCore import Qt

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.cm as cm

try:
    from GUI.debug import dprint
    from GUI import theme as theme_system
    from GUI import widgets as ui_widgets
    from GUI import stats_utils as su
    from GUI.bt_calculation import subtract_background, apply_gaussian_blur
except (ImportError, ModuleNotFoundError):
    from debug import dprint
    import theme as theme_system
    import widgets as ui_widgets
    import stats_utils as su
    from bt_calculation import subtract_background, apply_gaussian_blur


# Per-cell metrics. ``needs_membrane`` marks metrics that are only defined when a
# membrane (outline) region exists. ``region`` is used for axis labels.
METRICS = [
    ("membrane_enrichment",       "Membrane enrichment (membrane / interior)", True),
    ("membrane_enrichment_whole", "Membrane enrichment (membrane / whole-cell)", True),
    ("membrane_fraction",         "Membrane fraction of total (Σmembrane / Σwhole)", True),
    ("whole_mean",                "Whole-cell mean intensity", False),
    ("membrane_mean",             "Membrane mean intensity", True),
    ("interior_mean",             "Interior mean intensity", True),
    ("whole_median",              "Whole-cell median intensity", False),
    ("whole_std",                 "Whole-cell std intensity", False),
    ("whole_area",                "Whole-cell area (px)", False),
    ("membrane_area",             "Membrane area (px)", True),
    ("interior_area",             "Interior area (px)", True),
    ("whole_intden",              "Whole-cell integrated density (Σintensity)", False),
    ("membrane_intden",           "Membrane integrated density", True),
    ("interior_intden",           "Interior integrated density", True),
    ("whole_ctcf",                "Whole-cell CTCF (background-corrected)", False),
]
METRIC_LABELS = {k: lbl for k, lbl, _ in METRICS}


class IntensityAnalysisTab(QWidget):
    """Intensiometric / densitometric analysis of segmented cells."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.image_paths = []          # ordered list of stack paths
        self.image_groups = {}         # path -> group label
        self.results = {}              # path -> list[dict] per-cell rows
        self._popup_refs = []
        self._prefs_dirty = False
        self.current_theme = theme_system.current_theme_name()
        self.setAcceptDrops(True)

        self.init_ui()
        self.load_preferences()
        self.update_theme()

        if parent is not None and hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(self.update_theme)

    # ------------------------------------------------------------------ UI ---
    def init_ui(self):
        outer = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter)

        # ---- Left control panel ----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        left_layout.addWidget(self._build_image_group())
        left_layout.addWidget(self._build_registry_group())
        left_layout.addWidget(self._build_preprocess_group())

        self.run_btn = QPushButton("Measure Cells")
        self.run_btn.setObjectName("primaryButton")
        ui_widgets.set_button_icon(self.run_btn, "play", on_accent=True)
        self.run_btn.clicked.connect(self.measure_all)
        left_layout.addWidget(self.run_btn)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)
        left_layout.addStretch()

        # ---- Right plotting panel ----
        right = self._build_plot_panel()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 900])
        self.splitter = splitter

    def _build_image_group(self):
        group = QGroupBox("Segmented Images")
        v = QVBoxLayout(group)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add…")
        ui_widgets.set_button_icon(add_btn, "plus")
        add_btn.clicked.connect(self.add_images_dialog)
        remove_btn = QPushButton("Remove")
        ui_widgets.set_button_icon(remove_btn, "trash")
        remove_btn.clicked.connect(self.remove_selected)
        clear_btn = QPushButton("Clear")
        ui_widgets.set_button_icon(clear_btn, "clear")
        clear_btn.clicked.connect(self.clear_all)
        meta_btn = QPushButton("Metadata")
        ui_widgets.set_button_icon(meta_btn, "info")
        meta_btn.clicked.connect(self.view_metadata)
        for b in (add_btn, remove_btn, clear_btn, meta_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        v.addLayout(btn_row)

        self.image_list = QListWidget()
        self.image_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.image_list.setToolTip(
            "Segmented stacks (e.g. 'both_segmented_*.tif' from the Segmentation tab).\n"
            "Drag & drop TIFF or CZI files here to add them.")
        v.addWidget(self.image_list)

        grp_row = QHBoxLayout()
        grp_row.addWidget(QLabel("Group:"))
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Enter group label")
        grp_row.addWidget(self.group_edit)
        apply_btn = QPushButton("Apply to Selected")
        ui_widgets.set_button_icon(apply_btn, "check")
        apply_btn.clicked.connect(self.assign_group_to_selected)
        grp_row.addWidget(apply_btn)
        v.addLayout(grp_row)
        return group

    def _build_registry_group(self):
        group = QGroupBox("Channel Registry (frame layout)")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        self.outline_frame_spin = QSpinBox()
        self.outline_frame_spin.setRange(-1, 63)
        self.outline_frame_spin.setValue(0)
        self.outline_frame_spin.setToolTip("0-based frame index of the outline/membrane label mask. Use -1 if there is none.")
        self.outline_frame_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Outline (membrane) frame:", self.outline_frame_spin)

        self.filled_frame_spin = QSpinBox()
        self.filled_frame_spin.setRange(0, 63)
        self.filled_frame_spin.setValue(1)
        self.filled_frame_spin.setToolTip("0-based frame index of the filled whole-cell label mask.")
        self.filled_frame_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Whole-cell (filled) frame:", self.filled_frame_spin)

        # Membrane source: use the stored outline frame, or derive by eroding the
        # filled mask (works even for whole-cell-only stacks).
        self.membrane_source_combo = QComboBox()
        self.membrane_source_combo.addItems(["From outline frame", "Erode whole-cell"])
        self.membrane_source_combo.currentIndexChanged.connect(self._on_membrane_source_changed)
        form.addRow("Membrane source:", self.membrane_source_combo)

        self.erosion_spin = QSpinBox()
        self.erosion_spin.setRange(1, 40)
        self.erosion_spin.setValue(5)
        self.erosion_spin.setToolTip("Membrane band width (px) when deriving the membrane by erosion.")
        self.erosion_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Erosion width (px):", self.erosion_spin)

        # Fluorophore channels table: frame index + label.
        self.channels_table = QTableWidget(0, 2)
        self.channels_table.setHorizontalHeaderLabels(["Frame", "Label"])
        self.channels_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.channels_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.channels_table.setToolTip("Fluorophore channels to analyse: 0-based frame index and a label.")
        self.channels_table.setMaximumHeight(140)
        self.channels_table.itemChanged.connect(self._mark_dirty)
        form.addRow(self.channels_table)

        ch_btns = QHBoxLayout()
        add_ch = QPushButton("Add Channel")
        ui_widgets.set_button_icon(add_ch, "plus")
        add_ch.clicked.connect(lambda: self._add_channel_row(self._next_channel_frame(), ""))
        del_ch = QPushButton("Remove Channel")
        ui_widgets.set_button_icon(del_ch, "trash")
        del_ch.clicked.connect(self._remove_channel_row)
        ch_btns.addWidget(add_ch)
        ch_btns.addWidget(del_ch)
        ch_btns.addStretch()
        form.addRow(ch_btns)

        note = QLabel("Segment-both layout: outline=0, filled=1, channels from 2.")
        note.setWordWrap(True)
        note.setStyleSheet("font-style: italic;")
        form.addRow(note)
        return group

    def _build_preprocess_group(self):
        group = QGroupBox("Preprocessing")
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)

        self.bg_check = QCheckBox("Subtract background")
        self.bg_check.setChecked(True)
        self.bg_check.setToolTip("Estimate a local-mean background and subtract it (same method as the Bleed-Through tab).")
        self.bg_check.toggled.connect(self._mark_dirty)
        form.addRow(self.bg_check)

        self.bg_kernel_spin = QSpinBox()
        self.bg_kernel_spin.setRange(3, 200)
        self.bg_kernel_spin.setValue(30)
        self.bg_kernel_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("BG kernel (px):", self.bg_kernel_spin)

        self.blur_check = QCheckBox("Gaussian blur")
        self.blur_check.setChecked(False)
        self.blur_check.setToolTip("Optional Gaussian smoothing before measuring (reduces pixel noise).")
        self.blur_check.toggled.connect(self._mark_dirty)
        form.addRow(self.blur_check)

        self.blur_sigma_spin = QDoubleSpinBox()
        self.blur_sigma_spin.setRange(0.1, 20.0)
        self.blur_sigma_spin.setSingleStep(0.5)
        self.blur_sigma_spin.setValue(2.0)
        self.blur_sigma_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Blur sigma:", self.blur_sigma_spin)
        return group

    def _build_plot_panel(self):
        right = QWidget()
        v = QVBoxLayout(right)

        # Metric + channel selectors drive every plot.
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Metric:"))
        self.metric_combo = QComboBox()
        for key, label, _ in METRICS:
            self.metric_combo.addItem(label, key)
        self.metric_combo.currentIndexChanged.connect(self.refresh_plots)
        sel_row.addWidget(self.metric_combo, 2)

        sel_row.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.currentIndexChanged.connect(self.refresh_plots)
        sel_row.addWidget(self.channel_combo, 1)

        self.export_btn = QPushButton("Export CSV")
        ui_widgets.set_button_icon(self.export_btn, "save")
        self.export_btn.clicked.connect(self.export_csv)
        sel_row.addWidget(self.export_btn)
        v.addLayout(sel_row)

        self.plot_tabs = QTabWidget()
        v.addWidget(self.plot_tabs)

        # Histogram tab
        self.hist_fig = Figure(figsize=(6, 4))
        self.hist_ax = self.hist_fig.add_subplot(111)
        self.hist_canvas = FigureCanvas(self.hist_fig)
        self.plot_tabs.addTab(self._plot_container(
            self.hist_canvas, "hist"), "Histogram")

        # Box plot tab
        self.box_fig = Figure(figsize=(6, 4))
        self.box_ax = self.box_fig.add_subplot(111)
        self.box_canvas = FigureCanvas(self.box_fig)
        self.plot_tabs.addTab(self._plot_container(
            self.box_canvas, "box"), "Box Plot")

        # Scatter / correlation tab
        self.scatter_fig = Figure(figsize=(6, 4))
        self.scatter_ax = self.scatter_fig.add_subplot(111)
        self.scatter_canvas = FigureCanvas(self.scatter_fig)
        scatter_widget = self._plot_container(self.scatter_canvas, "scatter")
        # X/Y metric selectors for the scatter
        xy_row = QHBoxLayout()
        xy_row.addWidget(QLabel("X:"))
        self.scatter_x_combo = QComboBox()
        self.scatter_y_combo = QComboBox()
        for key, label, _ in METRICS:
            self.scatter_x_combo.addItem(label, key)
            self.scatter_y_combo.addItem(label, key)
        self.scatter_x_combo.setCurrentIndex([k for k, _, _ in METRICS].index("whole_area"))
        self.scatter_y_combo.setCurrentIndex([k for k, _, _ in METRICS].index("whole_intden"))
        self.scatter_x_combo.currentIndexChanged.connect(self.update_scatter)
        self.scatter_y_combo.currentIndexChanged.connect(self.update_scatter)
        xy_row.addWidget(self.scatter_x_combo, 1)
        xy_row.addWidget(QLabel("Y:"))
        xy_row.addWidget(self.scatter_y_combo, 1)
        xy_row.addStretch()
        scatter_widget.layout().insertLayout(0, xy_row)

        # Per-group visibility toggles: each group gets its own colour, marker
        # and regression line, and can be shown or hidden independently.
        self.scatter_group_row = QHBoxLayout()
        self._scatter_group_checks = {}
        self.scatter_group_row.addWidget(QLabel("Groups:"))
        self.scatter_pooled_check = QCheckBox("Pooled fit")
        self.scatter_pooled_check.setToolTip(
            "Also fit a single regression across every visible group (dashed).")
        self.scatter_pooled_check.toggled.connect(self.update_scatter)
        scatter_widget.layout().insertLayout(1, self.scatter_group_row)
        self.plot_tabs.addTab(scatter_widget, "Scatter / Correlation")

        # Summary tab
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setLineWrapMode(QTextEdit.NoWrap)
        self.summary_text.setFontFamily("Monospace")
        self.plot_tabs.addTab(self.summary_text, "Summary")
        return right

    def _plot_container(self, canvas, kind):
        """Wrap a canvas with a toolbar and Pop Out / Save / Legend buttons."""
        w = QWidget()
        lay = QVBoxLayout(w)
        toolbar = ui_widgets.plot_toolbar(canvas, w, self.current_theme)
        lay.addWidget(toolbar)
        lay.addWidget(canvas)
        setattr(self, f"{kind}_toolbar", toolbar)

        btns = QHBoxLayout()
        popout = QPushButton("Pop Out (publication)")
        ui_widgets.set_button_icon(popout, "image")
        popout.clicked.connect(lambda: self.popout(kind))
        btns.addWidget(popout)
        save_btn = QPushButton("Save Plot (300 DPI)")
        save_btn.setToolTip("Save as PNG or TIFF at 300 DPI. The legend is saved\n"
                            "next to it as its own image (plot.tif + plot_legend.tif).")
        ui_widgets.set_button_icon(save_btn, "save")
        save_btn.clicked.connect(
            lambda: self._save_figure(getattr(self, f"{kind}_fig"), kind))
        btns.addWidget(save_btn)
        legend_btn = QPushButton("Legend")
        ui_widgets.set_button_icon(legend_btn, "layers")
        legend_btn.clicked.connect(lambda: self.open_legend(kind))
        btns.addWidget(legend_btn)
        btns.addStretch()
        lay.addLayout(btns)
        return w

    # -------------------------------------------------------- drag & drop ---
    STACK_EXTENSIONS = ('.tif', '.tiff', '.czi')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        valid = [f for f in files if f.lower().endswith(self.STACK_EXTENSIONS)]
        if valid:
            self.add_image_paths(valid)
        elif files:
            self.update_status(
                f"Ignored {len(files)} dropped file(s): expected "
                f"{', '.join(self.STACK_EXTENSIONS)} stacks.")

    # -------------------------------------------------------- image list ---
    def add_images_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add segmented stacks", "",
            "Image stacks (*.tif *.tiff *.czi);;All files (*)")
        if paths:
            self.add_image_paths(paths)

    def add_image_paths(self, paths, group=None):
        """Public receiver used by the Segmentation tab's Send-to-Intensity."""
        added = 0
        for path in paths:
            if path in self.image_paths:
                continue
            self.image_paths.append(path)
            if group:
                self.image_groups[path] = group
            self._add_list_item(path)
            added += 1
        if added:
            self.update_status(f"Added {added} image(s).")

    def _add_list_item(self, path):
        base = os.path.basename(path)
        item = QListWidgetItem(base)
        item.setData(Qt.UserRole, path)
        group = self.image_groups.get(path)
        if group:
            item.setText(f"{base} [{group}]")
        item.setToolTip(path)
        self.image_list.addItem(item)

    def assign_group_to_selected(self):
        label = self.group_edit.text().strip()
        if not label:
            return
        for item in self.image_list.selectedItems():
            path = item.data(Qt.UserRole)
            self.image_groups[path] = label
            base = os.path.basename(path)
            item.setText(f"{base} [{label}]")
        self.update_status(f"Assigned group '{label}'.")
        self.refresh_plots()

    def remove_selected(self):
        for item in self.image_list.selectedItems():
            path = item.data(Qt.UserRole)
            self.image_paths = [p for p in self.image_paths if p != path]
            self.image_groups.pop(path, None)
            self.results.pop(path, None)
            self.image_list.takeItem(self.image_list.row(item))
        self.refresh_plots()

    def clear_all(self):
        self.image_paths.clear()
        self.image_groups.clear()
        self.results.clear()
        self.image_list.clear()
        self.refresh_plots()

    def view_metadata(self):
        item = self.image_list.currentItem()
        if item is None:
            self.update_status("Select an image to view its metadata.")
            return
        ui_widgets.show_metadata_dialog(self, item.data(Qt.UserRole))

    # ------------------------------------------------------ channel table ---
    def _add_channel_row(self, frame_index, label):
        self.channels_table.blockSignals(True)
        row = self.channels_table.rowCount()
        self.channels_table.insertRow(row)
        idx_item = QTableWidgetItem(str(int(frame_index)))
        idx_item.setTextAlignment(Qt.AlignCenter)
        self.channels_table.setItem(row, 0, idx_item)
        self.channels_table.setItem(row, 1, QTableWidgetItem(str(label)))
        self.channels_table.blockSignals(False)
        self._mark_dirty()

    def _remove_channel_row(self):
        row = self.channels_table.currentRow()
        if row < 0:
            row = self.channels_table.rowCount() - 1
        if row >= 0:
            self.channels_table.removeRow(row)
            self._mark_dirty()

    def _next_channel_frame(self):
        existing = [c[0] for c in self._channels_from_table()]
        return (max(existing) + 1) if existing else max(self.filled_frame_spin.value() + 1, 2)

    def _channels_from_table(self):
        channels = []
        for row in range(self.channels_table.rowCount()):
            idx_item = self.channels_table.item(row, 0)
            lbl_item = self.channels_table.item(row, 1)
            if idx_item is None:
                continue
            try:
                idx = int(str(idx_item.text()).strip())
            except (ValueError, TypeError):
                continue
            label = str(lbl_item.text()).strip() if lbl_item is not None else ""
            if not label:
                label = f"Frame {idx}"
            channels.append((idx, label))
        return channels

    def _on_membrane_source_changed(self):
        self.erosion_spin.setEnabled(self.membrane_source_combo.currentText() == "Erode whole-cell")
        self._mark_dirty()

    # --------------------------------------------------------- preprocess ---
    def _preprocess_channel(self, raw):
        """Apply the configured blur + background subtraction to a raw channel."""
        data = np.asarray(raw, dtype=np.float32)
        if self.blur_check.isChecked():
            data = apply_gaussian_blur(data, sigma=float(self.blur_sigma_spin.value())).astype(np.float32)
        if self.bg_check.isChecked():
            # subtract_background estimates the level from the (unblurred) image.
            data = subtract_background(data, np.asarray(raw, dtype=np.float32),
                                       kernel_size=int(self.bg_kernel_spin.value())).astype(np.float32)
        return data

    # ------------------------------------------------------- measurement ---
    def measure_all(self):
        if not self.image_paths:
            self.update_status("No images to measure.")
            return
        channels = self._channels_from_table()
        if not channels:
            self.update_status("Add at least one fluorophore channel in the registry.")
            return

        self.results.clear()
        total_cells = 0
        for path in self.image_paths:
            try:
                rows = self._measure_image(path, channels)
                self.results[path] = rows
                total_cells += len(rows)
            except Exception as e:
                dprint(f"Intensity: failed to measure {path}: {e}")
                self.update_status(f"Error measuring {os.path.basename(path)}: {e}")
        self._rebuild_channel_combo(channels)
        self.update_status(f"Measured {total_cells} cell(s) across {len(self.results)} image(s).")
        self.refresh_plots()

    def _load_stack(self, path):
        if path.lower().endswith('.czi'):
            import czifile
            arr = czifile.CziFile(path).asarray().squeeze()
        else:
            arr = tifffile.imread(path)
        if arr.ndim == 2:
            arr = arr[np.newaxis, ...]
        return arr

    def _measure_image(self, path, channels):
        arr = self._load_stack(path)
        n = arr.shape[0]

        filled_idx = self.filled_frame_spin.value()
        if not (0 <= filled_idx < n):
            raise ValueError(f"filled frame {filled_idx} out of range (stack has {n} frames)")
        filled = arr[filled_idx].astype(np.int32)

        outline_idx = self.outline_frame_spin.value()
        use_outline = (self.membrane_source_combo.currentText() == "From outline frame"
                       and 0 <= outline_idx < n)
        outline = arr[outline_idx].astype(np.int32) if use_outline else None

        # Precompute per-label whole-cell pixel index groups on the filled mask.
        flat_filled = filled.ravel()
        order = np.argsort(flat_filled, kind='stable')
        sorted_labels = flat_filled[order]
        uniq, starts = np.unique(sorted_labels, return_index=True)
        starts = np.append(starts, sorted_labels.size)
        label_slices = {int(u): (int(starts[k]), int(starts[k + 1]))
                        for k, u in enumerate(uniq) if int(u) != 0}

        # Membrane membership map (flattened), per source.
        if use_outline:
            membrane_flat = outline.ravel()
            membrane_is_label = True   # membrane pixel of cell L where membrane_flat == L
        else:
            binary = filled > 0
            eroded = binary_erosion(binary, iterations=int(self.erosion_spin.value()))
            membrane_full = binary & ~eroded
            membrane_flat = np.where(membrane_full.ravel(), flat_filled, 0)
            membrane_is_label = True

        # Preprocess each requested channel once.
        prepped = {}
        bg_level = {}
        background_mask = (filled == 0)
        for idx, label in channels:
            if not (0 <= idx < n):
                continue
            ch = self._preprocess_channel(arr[idx])
            prepped[label] = ch.ravel()
            bg_pixels = ch[background_mask]
            bg_level[label] = float(np.mean(bg_pixels)) if bg_pixels.size else 0.0

        group = self.image_groups.get(path, "Ungrouped")
        rows = []
        for lbl, (s, e) in label_slices.items():
            idx_pixels = order[s:e]
            mem_membership = None
            if membrane_flat is not None:
                mem_membership = membrane_flat[idx_pixels] == lbl
            for label, flat_ch in prepped.items():
                whole = flat_ch[idx_pixels]
                whole = whole[np.isfinite(whole)]
                if whole.size == 0:
                    continue
                row = {
                    "image": os.path.basename(path), "group": group,
                    "cell": int(lbl), "channel": label,
                }
                row["whole_area"] = float(whole.size)
                row["whole_mean"] = float(np.mean(whole))
                row["whole_median"] = float(np.median(whole))
                row["whole_std"] = float(np.std(whole, ddof=1)) if whole.size > 1 else 0.0
                whole_sum = float(np.sum(whole))
                row["whole_intden"] = whole_sum
                row["whole_ctcf"] = whole_sum - whole.size * bg_level.get(label, 0.0)

                if mem_membership is not None and mem_membership.any():
                    ch_cell = flat_ch[idx_pixels]
                    mem = ch_cell[mem_membership]
                    interior = ch_cell[~mem_membership]
                    mem = mem[np.isfinite(mem)]
                    interior = interior[np.isfinite(interior)]
                    row["membrane_area"] = float(mem.size)
                    row["interior_area"] = float(interior.size)
                    mem_mean = float(np.mean(mem)) if mem.size else float('nan')
                    int_mean = float(np.mean(interior)) if interior.size else float('nan')
                    row["membrane_mean"] = mem_mean
                    row["interior_mean"] = int_mean
                    mem_sum = float(np.sum(mem)) if mem.size else 0.0
                    int_sum = float(np.sum(interior)) if interior.size else 0.0
                    row["membrane_intden"] = mem_sum
                    row["interior_intden"] = int_sum
                    row["membrane_enrichment"] = (mem_mean / int_mean) if int_mean not in (0, float('nan')) and np.isfinite(int_mean) and int_mean != 0 else float('nan')
                    row["membrane_enrichment_whole"] = (mem_mean / row["whole_mean"]) if row["whole_mean"] else float('nan')
                    row["membrane_fraction"] = (mem_sum / whole_sum) if whole_sum else float('nan')
                else:
                    for k in ("membrane_area", "interior_area", "membrane_mean",
                              "interior_mean", "membrane_intden", "interior_intden",
                              "membrane_enrichment", "membrane_enrichment_whole",
                              "membrane_fraction"):
                        row[k] = float('nan')
                rows.append(row)
        return rows

    # --------------------------------------------------------- data access ---
    def _rebuild_channel_combo(self, channels):
        current = self.channel_combo.currentText()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        for _idx, label in channels:
            self.channel_combo.addItem(label)
        i = self.channel_combo.findText(current)
        if i >= 0:
            self.channel_combo.setCurrentIndex(i)
        self.channel_combo.blockSignals(False)

    def _active_channel(self):
        return self.channel_combo.currentText()

    def _values_by_group(self, metric_key, channel=None):
        """Return (ordered_groups, {group: np.array of per-cell values})."""
        channel = channel or self._active_channel()
        from collections import defaultdict
        data = defaultdict(list)
        for path, rows in self.results.items():
            for r in rows:
                if channel and r["channel"] != channel:
                    continue
                val = r.get(metric_key)
                if val is None or not np.isfinite(val):
                    continue
                data[r["group"]].append(val)
        groups = sorted(data.keys())
        return groups, {g: np.asarray(data[g], dtype=float) for g in groups}

    def _group_color(self, i, n):
        cmap = cm.get_cmap('tab10' if n <= 10 else 'tab20')
        return cmap(i % cmap.N)

    # Marker shapes back up the colours so groups stay distinguishable in
    # greyscale print and for colour-blind readers.
    GROUP_MARKERS = ['o', 's', '^', 'D', 'v', 'P', 'X', '*', '<', '>']

    def _group_marker(self, i):
        return self.GROUP_MARKERS[i % len(self.GROUP_MARKERS)]

    # ------------------------------------------------------------ plotting ---
    def refresh_plots(self):
        self.update_histogram()
        self.update_boxplot()
        self.update_scatter()
        self.update_summary()

    def _metric_key(self):
        return self.metric_combo.currentData()

    def _draw_histogram(self, ax):
        metric = self._metric_key()
        groups, data = self._values_by_group(metric)
        entries = []
        if not groups:
            ax.text(0.5, 0.5, "No data — add images and click Measure Cells",
                    ha='center', va='center', transform=ax.transAxes)
            return entries
        all_vals = np.concatenate([data[g] for g in groups if data[g].size]) if groups else np.array([])
        if all_vals.size == 0:
            ax.text(0.5, 0.5, "No finite values for this metric/channel",
                    ha='center', va='center', transform=ax.transAxes)
            return entries
        bins = np.linspace(np.min(all_vals), np.max(all_vals), 40)
        for i, g in enumerate(groups):
            vals = data[g]
            if vals.size == 0:
                continue
            color = self._group_color(i, len(groups))
            ax.hist(vals, bins=bins, alpha=0.5, color=color, label=g)
            mean = float(np.mean(vals))
            ax.axvline(mean, color=color, linestyle='--', linewidth=1.2)
            entries.append((color, f"{g}: mean {mean:.3g} (n={vals.size} cells)"))
        ax.set_xlabel(METRIC_LABELS.get(metric, metric))
        ax.set_ylabel("Cell count")
        ax.set_title(f"Distribution — {self._active_channel()}")
        return entries

    def update_histogram(self):
        self.hist_ax.clear()
        self._hist_entries = self._draw_histogram(self.hist_ax)
        theme_system.apply_axes_theme(self.hist_ax, self.current_theme)
        self.hist_fig.tight_layout()
        self.hist_canvas.draw_idle()

    def _draw_boxplot(self, ax):
        metric = self._metric_key()
        groups, data = self._values_by_group(metric)
        entries = []
        arrays = [data[g] for g in groups if data[g].size]
        used_groups = [g for g in groups if data[g].size]
        if not arrays:
            ax.text(0.5, 0.5, "No data — add images and click Measure Cells",
                    ha='center', va='center', transform=ax.transAxes)
            return entries
        positions = np.arange(1, len(arrays) + 1)
        bp = ax.boxplot(arrays, positions=positions, widths=0.6,
                        showfliers=False, patch_artist=True)
        for i, box in enumerate(bp['boxes']):
            color = self._group_color(i, len(arrays))
            box.set_facecolor(color)
            box.set_alpha(0.55)
            mean = float(np.mean(arrays[i]))
            entries.append((color, f"{used_groups[i]}: mean {mean:.3g} (n={arrays[i].size})"))
        for med in bp['medians']:
            med.set_color('black')
        # jittered points
        rng = np.random.default_rng(42)
        for i, arr in enumerate(arrays):
            x = positions[i] + rng.uniform(-0.12, 0.12, size=arr.size)
            ax.scatter(x, arr, s=8, color=self._group_color(i, len(arrays)),
                       edgecolors='none', alpha=0.6, zorder=3)
        ax.set_xticks(positions)
        ax.set_xticklabels(used_groups, rotation=20, ha='right')
        ax.set_ylabel(METRIC_LABELS.get(metric, metric))
        ax.set_title(f"{METRIC_LABELS.get(metric, metric)} — {self._active_channel()}")

        # Significance bars (assumption-aware).
        comps, report = su.compute_significance_comparisons(
            arrays, labels=used_groups,
            data_note="Data: per-cell values of the selected metric (finite only).")
        self._last_stats_report = report
        if comps:
            all_vals = np.concatenate(arrays)
            top = np.max(all_vals)
            span = (np.max(all_vals) - np.min(all_vals)) or 1.0
            step = span * 0.08
            cap = span * 0.02
            level = top + step
            for (i, j, p) in comps:
                su.draw_sig(ax, positions[i], positions[j], level, su.p_to_symbol(p), cap)
                level += step
        return entries

    def update_boxplot(self):
        self.box_ax.clear()
        self._box_entries = self._draw_boxplot(self.box_ax)
        theme_system.apply_axes_theme(self.box_ax, self.current_theme)
        self.box_fig.tight_layout()
        self.box_canvas.draw_idle()

    def _all_rows_for_channel(self, channel=None):
        channel = channel or self._active_channel()
        rows = []
        for _p, rlist in self.results.items():
            for r in rlist:
                if not channel or r["channel"] == channel:
                    rows.append(r)
        return rows

    def _scatter_xy_by_group(self, xkey, ykey):
        """Return (ordered_groups, {group: (x_array, y_array)}) for the active channel."""
        from collections import defaultdict
        data = defaultdict(lambda: ([], []))
        for r in self._all_rows_for_channel():
            xv, yv = r.get(xkey), r.get(ykey)
            if xv is None or yv is None or not (np.isfinite(xv) and np.isfinite(yv)):
                continue
            data[r["group"]][0].append(xv)
            data[r["group"]][1].append(yv)
        groups = sorted(data.keys())
        return groups, {g: (np.asarray(data[g][0], dtype=float),
                            np.asarray(data[g][1], dtype=float)) for g in groups}

    def _rebuild_scatter_group_toggles(self):
        """Sync the per-group check boxes with the groups present in the results."""
        groups, _ = self._scatter_xy_by_group(self.scatter_x_combo.currentData(),
                                              self.scatter_y_combo.currentData())
        if list(self._scatter_group_checks.keys()) == groups:
            return

        # Empty the row, keeping the pooled-fit box (it is re-added below).
        while self.scatter_group_row.count():
            item = self.scatter_group_row.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.scatter_pooled_check:
                widget.setParent(None)
                widget.deleteLater()
        self._scatter_group_checks = {}

        self.scatter_group_row.addWidget(QLabel("Groups:"))
        for i, g in enumerate(groups):
            check = QCheckBox(g)
            check.setChecked(True)
            color = self._group_color(i, len(groups))
            hexcol = '#%02x%02x%02x' % tuple(int(255 * c) for c in color[:3])
            check.setToolTip(f"Show '{g}' (marker '{self._group_marker(i)}') and its fit.")
            check.setStyleSheet(f"QCheckBox {{ color: {hexcol}; font-weight: 600; }}")
            check.toggled.connect(self.update_scatter)
            self._scatter_group_checks[g] = check
            self.scatter_group_row.addWidget(check)
        self.scatter_group_row.addWidget(self.scatter_pooled_check)
        self.scatter_group_row.addStretch()

    def _scatter_visible(self, group):
        check = self._scatter_group_checks.get(group)
        return check is None or check.isChecked()

    def _fit_label(self, name, xs, ys):
        """Fit y~x and return (label, line_xy) — line_xy is None when no fit is possible."""
        if xs.size < 2 or np.ptp(xs) == 0:
            return f"{name}: n={xs.size} (too few points to fit)", None
        try:
            lr = sp_stats.linregress(xs, ys)
        except Exception as e:
            dprint(f"scatter fit failed for {name}: {e}")
            return f"{name}: n={xs.size} (fit failed)", None
        xln = np.linspace(xs.min(), xs.max(), 100)
        label = (f"{name}: y={lr.slope:.3g}x+{lr.intercept:.3g}, "
                 f"r={lr.rvalue:.3f}, p={lr.pvalue:.2e} (n={xs.size})")
        return label, (xln, lr.slope * xln + lr.intercept)

    def _draw_scatter(self, ax):
        xkey = self.scatter_x_combo.currentData()
        ykey = self.scatter_y_combo.currentData()
        groups, data = self._scatter_xy_by_group(xkey, ykey)
        entries = []
        visible = [g for g in groups if self._scatter_visible(g)]
        n_points = sum(data[g][0].size for g in visible)
        if n_points < 2:
            ax.text(0.5, 0.5, "Need ≥2 cells with finite X and Y",
                    ha='center', va='center', transform=ax.transAxes)
            return entries

        # Index over *all* groups so a group keeps its colour and marker when
        # other groups are toggled off.
        for i, g in enumerate(groups):
            if g not in visible:
                continue
            xs, ys = data[g]
            color = self._group_color(i, len(groups))
            marker = self._group_marker(i)
            ax.scatter(xs, ys, s=14, alpha=0.55, color=color, marker=marker,
                       edgecolors='none', zorder=2)
            label, line = self._fit_label(g, xs, ys)
            if line is not None:
                ax.plot(line[0], line[1], color=color, lw=1.5, zorder=3)
            entries.append((color, label, marker))

        # Optional single fit across every visible group, for comparison.
        if self.scatter_pooled_check.isChecked() and len(visible) > 1:
            pooled_x = np.concatenate([data[g][0] for g in visible])
            pooled_y = np.concatenate([data[g][1] for g in visible])
            label, line = self._fit_label("Pooled", pooled_x, pooled_y)
            if line is not None:
                ax.plot(line[0], line[1], color='0.4', lw=1.8, ls='--', zorder=4)
            entries.append(('0.4', label, None))

        ax.set_xlabel(METRIC_LABELS.get(xkey, xkey))
        ax.set_ylabel(METRIC_LABELS.get(ykey, ykey))
        ax.set_title(f"Correlation — {self._active_channel()}")
        return entries

    def update_scatter(self):
        self._rebuild_scatter_group_toggles()
        self.scatter_ax.clear()
        self._scatter_entries = self._draw_scatter(self.scatter_ax)
        theme_system.apply_axes_theme(self.scatter_ax, self.current_theme)
        self.scatter_fig.tight_layout()
        self.scatter_canvas.draw_idle()

    def update_summary(self):
        metric = self._metric_key()
        groups, data = self._values_by_group(metric)
        lines = [f"Metric: {METRIC_LABELS.get(metric, metric)}",
                 f"Channel: {self._active_channel()}", ""]
        lines.append(f"{'Group':<20}{'n':>6}{'mean':>12}{'SD':>12}{'median':>12}")
        lines.append("-" * 62)
        for g in groups:
            vals = data[g]
            if vals.size == 0:
                continue
            lines.append(f"{g:<20}{vals.size:>6}{np.mean(vals):>12.4g}"
                         f"{(np.std(vals, ddof=1) if vals.size > 1 else 0):>12.4g}"
                         f"{np.median(vals):>12.4g}")
        report = getattr(self, "_last_stats_report", None)
        if report:
            lines.append("")
            lines.append(report)
        self.summary_text.setPlainText("\n".join(lines))

    # --------------------------------------------------------- popouts ---
    def popout(self, kind):
        title = {"hist": "Histogram", "box": "Box Plot",
                 "scatter": "Scatter / Correlation"}.get(kind, "Plot")
        fig = Figure(figsize=(11, 7.5))
        ax = fig.add_subplot(111)
        if kind == "hist":
            self._draw_histogram(ax)
        elif kind == "box":
            self._draw_boxplot(ax)
        else:
            self._draw_scatter(ax)
        theme_system.apply_figure_theme(fig, self.current_theme)
        fig.tight_layout()
        self._show_figure_dialog(fig, title, kind)

    def _legend_entries(self, kind):
        """The (color, label[, marker]) entries backing ``kind``'s legend."""
        return getattr(self, f"_{kind}_entries", None) or []

    def _show_figure_dialog(self, fig, title, kind):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(900, 680)
        lay = QVBoxLayout(dlg)
        canvas = FigureCanvas(fig)
        toolbar = ui_widgets.plot_toolbar(canvas, dlg, self.current_theme)
        lay.addWidget(toolbar)
        lay.addWidget(canvas)

        btns = QHBoxLayout()
        save_btn = QPushButton("Save Plot (300 DPI)")
        save_btn.setToolTip("Save as PNG or TIFF at 300 DPI. The legend is saved\n"
                            "next to it as its own image (plot.tif + plot_legend.tif).")
        ui_widgets.set_button_icon(save_btn, "save")
        save_btn.clicked.connect(lambda: self._save_figure(fig, kind))
        btns.addWidget(save_btn)
        if kind in ("hist", "box", "scatter"):
            legend_btn = QPushButton("Legend")
            ui_widgets.set_button_icon(legend_btn, "layers")
            legend_btn.clicked.connect(lambda: self.open_legend(kind))
            btns.addWidget(legend_btn)
        if kind == "box":
            stats_btn = QPushButton("Stats info")
            ui_widgets.set_button_icon(stats_btn, "info")
            stats_btn.clicked.connect(self.show_stats_dialog)
            btns.addWidget(stats_btn)
        export_btn = QPushButton("Export Data")
        ui_widgets.set_button_icon(export_btn, "save")
        export_btn.clicked.connect(self.export_csv)
        btns.addWidget(export_btn)
        btns.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.close)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

        canvas.draw_idle()
        self._popup_refs.append(dlg)
        dlg.show()

    def open_legend(self, kind):
        entries = self._legend_entries(kind)
        if not entries:
            self.update_status("No legend entries — measure first.")
            return
        title = "Legend — " + {"hist": "Histogram", "box": "Box Plot",
                               "scatter": "Scatter / Correlation"}.get(kind, "Plot")
        fig = ui_widgets.make_legend_figure(entries, self.current_theme)
        self._show_figure_dialog(fig, title, "legend")

    def _save_figure(self, fig, kind):
        """Save ``fig`` at 300 DPI, writing its legend beside it as its own image."""
        path, legend_path = ui_widgets.save_plot_dialog(
            self, fig, f"intensity_{kind}.png",
            legend_entries=self._legend_entries(kind), theme=self.current_theme)
        if not path:
            return
        saved = os.path.basename(path)
        if legend_path:
            saved += f" + {os.path.basename(legend_path)}"
        self.update_status(f"Saved: {saved}")

    def show_stats_dialog(self):
        report = getattr(self, "_last_stats_report", None)
        if not report:
            QMessageBox.information(self, "Statistics details",
                                    "No statistics yet. Measure cells and open the box plot first.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Statistics details")
        dlg.setMinimumSize(560, 520)
        lay = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.NoWrap)
        text.setFontFamily("Monospace")
        text.setPlainText(report)
        lay.addWidget(text)
        self._popup_refs.append(dlg)
        dlg.show()

    # ------------------------------------------------------------ export ---
    def export_csv(self):
        if not self.results:
            self.update_status("Nothing to export — measure first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export per-cell measurements", "intensity_measurements.csv",
            "CSV (*.csv)")
        if not path:
            return
        # Union of keys across rows, with identifying columns first.
        lead = ["image", "group", "cell", "channel"]
        metric_keys = [k for k, _, _ in METRICS]
        header = lead + metric_keys
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(header)
                for _p, rows in self.results.items():
                    for r in rows:
                        writer.writerow([r.get(k, "") for k in header])
            self.update_status(f"Exported {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))

    # ------------------------------------------------------------- theme ---
    def update_theme(self):
        self.current_theme = theme_system.current_theme_name()
        theme_system.apply_matplotlib_style(self.current_theme)
        theme_system.style_navigation_toolbars(self, self.current_theme)
        for fig, canvas in ((self.hist_fig, self.hist_canvas),
                            (self.box_fig, self.box_canvas),
                            (self.scatter_fig, self.scatter_canvas)):
            theme_system.apply_figure_theme(fig, self.current_theme)
            canvas.draw_idle()

    # ------------------------------------------------------------ status ---
    def update_status(self, message):
        self.status_label.setText(message)
        dprint(f"Intensity: {message}")

    # ------------------------------------------------------- preferences ---
    def _mark_dirty(self, *args):
        self._prefs_dirty = True

    def save_preferences(self):
        if not self.config:
            return
        self.config.set('intensity.registry.outline_index', int(self.outline_frame_spin.value()))
        self.config.set('intensity.registry.filled_index', int(self.filled_frame_spin.value()))
        self.config.set('intensity.registry.membrane_source', self.membrane_source_combo.currentText())
        self.config.set('intensity.registry.erosion_width', int(self.erosion_spin.value()))
        self.config.set('intensity.registry.channels',
                        [[idx, label] for idx, label in self._channels_from_table()])
        self.config.set('intensity.preprocess.subtract_background', bool(self.bg_check.isChecked()))
        self.config.set('intensity.preprocess.bg_kernel', int(self.bg_kernel_spin.value()))
        self.config.set('intensity.preprocess.gaussian_enabled', bool(self.blur_check.isChecked()))
        self.config.set('intensity.preprocess.gaussian_sigma', float(self.blur_sigma_spin.value()))
        self.config.sync()

    def load_preferences(self):
        if not self.config:
            self._add_channel_row(2, "Fluor 1")
            return
        try:
            self.outline_frame_spin.setValue(int(self.config.get('intensity.registry.outline_index', 0)))
            self.filled_frame_spin.setValue(int(self.config.get('intensity.registry.filled_index', 1)))
            source = str(self.config.get('intensity.registry.membrane_source', 'From outline frame'))
            i = self.membrane_source_combo.findText(source)
            if i >= 0:
                self.membrane_source_combo.setCurrentIndex(i)
            self.erosion_spin.setValue(int(self.config.get('intensity.registry.erosion_width', 5)))
            self.bg_check.setChecked(bool(self.config.get('intensity.preprocess.subtract_background', True)))
            self.bg_kernel_spin.setValue(int(self.config.get('intensity.preprocess.bg_kernel', 30)))
            self.blur_check.setChecked(bool(self.config.get('intensity.preprocess.gaussian_enabled', False)))
            self.blur_sigma_spin.setValue(float(self.config.get('intensity.preprocess.gaussian_sigma', 2.0)))

            channels = self.config.get('intensity.registry.channels', None)
            self.channels_table.setRowCount(0)
            if channels:
                for entry in channels:
                    try:
                        idx, label = int(entry[0]), str(entry[1])
                    except (ValueError, TypeError, IndexError):
                        continue
                    self._add_channel_row(idx, label)
            else:
                self._add_channel_row(2, "Fluor 1")
        except Exception as e:
            dprint(f"Intensity: load_preferences failed: {e}")
            if self.channels_table.rowCount() == 0:
                self._add_channel_row(2, "Fluor 1")
        self._on_membrane_source_changed()
        self._prefs_dirty = False

    def closeEvent(self, event):
        if getattr(self, '_prefs_dirty', False):
            self.save_preferences()
        super().closeEvent(event)
