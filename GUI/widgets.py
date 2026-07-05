"""
Shared UI building blocks for the SONLab FRET Tool.

Two things live here:

* a small, self-contained **vector icon set** drawn with QPainter (no external
  asset files, no QtSvg dependency) that is tinted to the active theme, and
* the **info button** used next to parameter fields, so every tab shows the same
  control instead of three slightly different hand-rolled ones.

Icons are attached to buttons via :func:`set_button_icon`, which records the
icon name as a Qt dynamic property. :func:`apply_icon_theme` walks a widget tree
and re-tints every such button, so icons follow light/dark theme switches.
"""

import os

from PyQt5.QtCore import Qt, QSize, QRectF, QPointF
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPainterPath, QBrush
from PyQt5.QtWidgets import (QToolButton, QAbstractButton, QDialog, QVBoxLayout,
                             QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
                             QPushButton, QLabel)

try:
    from GUI import theme as theme_system
except (ImportError, ModuleNotFoundError):
    import theme as theme_system


# ---------------------------------------------------------------------------
# Icon drawing (24x24 reference grid, stroke based)
# ---------------------------------------------------------------------------

def _pen(painter, color, width=2.0):
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    return pen


def _draw_info(p, c):
    _pen(p, c, 1.8)
    p.drawEllipse(QRectF(3, 3, 18, 18))
    p.setBrush(QBrush(QColor(c)))
    p.drawEllipse(QRectF(11, 6.7, 2, 2))
    _pen(p, c, 2.0)
    p.drawLine(QPointF(12, 11), QPointF(12, 17))


def _draw_folder(p, c):
    _pen(p, c, 1.8)
    path = QPainterPath()
    path.moveTo(3, 8)
    path.lineTo(9, 8)
    path.lineTo(11, 10)
    path.lineTo(21, 10)
    path.lineTo(21, 19)
    path.lineTo(3, 19)
    path.closeSubpath()
    p.drawPath(path)


def _draw_trash(p, c):
    _pen(p, c, 1.8)
    p.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
    p.drawPath(_poly([(9, 7), (9, 5), (15, 5), (15, 7)]))
    p.drawPath(_poly([(6, 7), (7, 20), (17, 20), (18, 7)]))
    p.drawLine(QPointF(10, 10), QPointF(10.5, 17))
    p.drawLine(QPointF(14, 10), QPointF(13.5, 17))


def _draw_play(p, c):
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(c)))
    p.drawPath(_poly([(8, 6), (8, 18), (18, 12)], close=True))


def _draw_save(p, c):
    _pen(p, c, 2.0)
    p.drawLine(QPointF(12, 4), QPointF(12, 14))
    p.drawPath(_poly([(8, 10.5), (12, 14.5), (16, 10.5)]))
    p.drawPath(_poly([(5, 15), (5, 19), (19, 19), (19, 15)]))


def _draw_send(p, c):
    _pen(p, c, 2.0)
    p.drawLine(QPointF(4, 12), QPointF(18, 12))
    p.drawPath(_poly([(13, 7), (18, 12), (13, 17)]))


def _draw_plus(p, c):
    _pen(p, c, 2.0)
    p.drawLine(QPointF(12, 5), QPointF(12, 19))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))


def _draw_check(p, c):
    _pen(p, c, 2.2)
    p.drawPath(_poly([(5, 13), (10, 18), (19, 6)]))


def _draw_clear(p, c):
    _pen(p, c, 2.0)
    p.drawLine(QPointF(7, 7), QPointF(17, 17))
    p.drawLine(QPointF(17, 7), QPointF(7, 17))


def _draw_refresh(p, c):
    _pen(p, c, 1.9)
    p.drawArc(QRectF(4, 4, 16, 16), 60 * 16, 250 * 16)
    p.drawPath(_poly([(18.5, 3), (19.5, 8.5), (14, 8)]))


def _draw_undo(p, c):
    _pen(p, c, 1.9)
    p.drawArc(QRectF(4, 6, 16, 14), 30 * 16, 300 * 16)
    p.drawPath(_poly([(4, 4), (5, 10), (10.5, 8.5)]))


def _draw_layers(p, c):
    _pen(p, c, 1.8)
    p.drawPath(_poly([(12, 4), (20, 8.5), (12, 13), (4, 8.5)], close=True))
    p.drawPath(_poly([(4, 13), (12, 17.5), (20, 13)]))


def _draw_image(p, c):
    _pen(p, c, 1.8)
    p.drawRoundedRect(QRectF(4, 5, 16, 14), 2, 2)
    p.setBrush(QBrush(QColor(c)))
    p.drawEllipse(QRectF(8, 8.5, 2.6, 2.6))
    p.setBrush(Qt.NoBrush)
    p.drawPath(_poly([(6, 17), (11, 12), (14, 15), (16, 13), (18, 17)]))


def _poly(points, close=False):
    path = QPainterPath()
    path.moveTo(*points[0])
    for pt in points[1:]:
        path.lineTo(*pt)
    if close:
        path.closeSubpath()
    return path


_ICONS = {
    "info": _draw_info,
    "folder": _draw_folder,
    "trash": _draw_trash,
    "play": _draw_play,
    "save": _draw_save,
    "send": _draw_send,
    "plus": _draw_plus,
    "check": _draw_check,
    "clear": _draw_clear,
    "refresh": _draw_refresh,
    "undo": _draw_undo,
    "layers": _draw_layers,
    "image": _draw_image,
}


def make_icon(name, color, size=18):
    """Return a :class:`QIcon` for ``name`` drawn in ``color`` at ``size`` px."""
    drawer = _ICONS.get(name)
    if drawer is None:
        return QIcon()
    scale = 2  # render at 2x for crisp downscaling
    px = size * scale
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(px / 24.0, px / 24.0)
    drawer(painter, color)
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Attaching theme-aware icons to buttons
# ---------------------------------------------------------------------------

def _icon_color(theme, on_accent):
    c = theme_system.palette(theme)
    return c["on_accent"] if on_accent else c["text"]


def set_button_icon(button, name, size=18, on_accent=False):
    """Give ``button`` a themed icon that survives theme switches.

    ``on_accent=True`` keeps the icon white (for coloured semantic buttons).
    The icon name is stored as a dynamic property so :func:`apply_icon_theme`
    can re-tint it later.
    """
    button.setProperty("iconName", name)
    button.setProperty("iconOnAccent", bool(on_accent))
    theme = theme_system.current_theme_name()
    button.setIcon(make_icon(name, _icon_color(theme, on_accent), size))
    button.setIconSize(QSize(size, size))
    return button


def apply_icon_theme(root, theme):
    """Re-tint every button under ``root`` that carries an ``iconName`` prop."""
    if root is None:
        return
    for button in root.findChildren(QAbstractButton):
        name = button.property("iconName")
        if not name:
            continue
        on_accent = bool(button.property("iconOnAccent"))
        size = button.iconSize().width() or 18
        button.setIcon(make_icon(name, _icon_color(theme, on_accent), size))


# ---------------------------------------------------------------------------
# Info button
# ---------------------------------------------------------------------------

def info_button(tooltip_text, parent=None):
    """A small, borderless, theme-aware info control with a wrapped tooltip."""
    btn = QToolButton(parent)
    btn.setObjectName("infoButton")
    btn.setCursor(Qt.WhatsThisCursor)
    btn.setFocusPolicy(Qt.NoFocus)
    btn.setAutoRaise(True)
    # HTML wrapper keeps long help text from becoming one very wide line.
    btn.setToolTip(
        f'<div style="max-width:320px; white-space:normal;">{tooltip_text}</div>'
    )
    set_button_icon(btn, "info", size=15)
    return btn


# ---------------------------------------------------------------------------
# Image metadata / EXIF viewer
# ---------------------------------------------------------------------------

def _fmt_value(value, limit=2000):
    """Render an arbitrary tag value as a readable, length-capped string."""
    try:
        text = str(value)
    except Exception:
        text = repr(value)
    text = text.replace('\r\n', '\n')
    if len(text) > limit:
        text = text[:limit] + f"\n… (+{len(text) - limit} more characters)"
    return text


def read_image_metadata(image_path):
    """Collect metadata for a TIFF or CZI image as ``[(section, [(key, value), ...])]``.

    Reads TIFF tags via :mod:`tifffile` and CZI metadata via ``czifile`` when
    available. Never raises: any failure is reported as a section entry so the
    dialog can still open.
    """
    sections = []

    file_info = [("Path", image_path), ("Name", os.path.basename(image_path))]
    try:
        file_info.append(("Size", f"{os.path.getsize(image_path):,} bytes"))
    except OSError:
        pass
    ext = os.path.splitext(image_path)[1].lower()
    file_info.append(("Format", ext.lstrip('.').upper() or "unknown"))
    sections.append(("File", file_info))

    try:
        if ext in ('.tif', '.tiff'):
            import tifffile
            with tifffile.TiffFile(image_path) as tif:
                series = tif.series[0] if tif.series else None
                image_info = [("Pages / frames", str(len(tif.pages)))]
                if series is not None:
                    image_info.append(("Shape", str(series.shape)))
                    image_info.append(("Dtype", str(series.dtype)))
                    if getattr(series, 'axes', None):
                        image_info.append(("Axes", str(series.axes)))
                sections.append(("Image", image_info))

                page = tif.pages[0]
                tags = [(tag.name, _fmt_value(tag.value)) for tag in page.tags.values()]
                sections.append((f"TIFF tags (page 0) — {len(tags)}",
                                 tags or [("(none)", "No tags present")]))

                # ImageJ / OME / shaped metadata blobs, when present.
                extra = []
                for attr in ('imagej_metadata', 'shaped_metadata', 'ome_metadata'):
                    val = getattr(tif, attr, None)
                    if val:
                        extra.append((attr, _fmt_value(val)))
                if extra:
                    sections.append(("Embedded metadata", extra))
        elif ext == '.czi':
            try:
                import czifile
            except (ImportError, ModuleNotFoundError):
                czifile = None
            if czifile is None:
                sections.append(("CZI", [("Unavailable", "czifile is not installed")]))
            else:
                with czifile.CziFile(image_path) as czi_file:
                    image_info = [("Shape", str(czi_file.shape))]
                    if getattr(czi_file, 'axes', None):
                        image_info.append(("Axes", str(czi_file.axes)))
                    if getattr(czi_file, 'dtype', None):
                        image_info.append(("Dtype", str(czi_file.dtype)))
                    sections.append(("Image", image_info))
                    try:
                        meta = czi_file.metadata()
                    except Exception as e:  # pragma: no cover - defensive
                        meta = f"<could not read metadata: {e}>"
                    sections.append(("CZI metadata (XML)", [("metadata", _fmt_value(meta, limit=20000))]))
        else:
            sections.append(("Unsupported", [("Format", f"No metadata reader for '{ext}'")]))
    except Exception as e:
        sections.append(("Error", [("Failed to read metadata", str(e))]))

    return sections


def show_metadata_dialog(parent, image_path):
    """Open a modal dialog showing the metadata of ``image_path``.

    Reused by all tabs so the metadata viewer looks and behaves identically
    everywhere. Inherits the application stylesheet/palette for theming.
    """
    if not image_path or not os.path.exists(image_path):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(parent, "Image Metadata",
                               "Select an image first to view its metadata.")
        return None

    sections = read_image_metadata(image_path)

    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Metadata — {os.path.basename(image_path)}")
    dialog.resize(640, 520)
    layout = QVBoxLayout(dialog)

    header = QLabel(os.path.basename(image_path))
    header.setStyleSheet("font-weight: 600;")
    layout.addWidget(header)

    tree = QTreeWidget()
    tree.setColumnCount(2)
    tree.setHeaderLabels(["Property", "Value"])
    tree.setAlternatingRowColors(True)
    tree.setUniformRowHeights(True)

    plain_lines = []
    for section_name, entries in sections:
        parent_item = QTreeWidgetItem([section_name, ""])
        font = parent_item.font(0)
        font.setBold(True)
        parent_item.setFont(0, font)
        tree.addTopLevelItem(parent_item)
        plain_lines.append(f"[{section_name}]")
        for key, value in entries:
            value_str = str(value)
            child = QTreeWidgetItem([str(key), value_str])
            child.setToolTip(1, value_str)
            parent_item.addChild(child)
            plain_lines.append(f"{key}: {value_str}")
        plain_lines.append("")
        parent_item.setExpanded(True)

    tree.resizeColumnToContents(0)
    layout.addWidget(tree, 1)

    # A copy-friendly plain-text view of everything.
    raw = QPlainTextEdit()
    raw.setReadOnly(True)
    raw.setPlainText("\n".join(plain_lines).strip())
    raw.setMaximumHeight(150)
    layout.addWidget(raw)

    button_row = QHBoxLayout()
    button_row.addStretch(1)
    copy_btn = QPushButton("Copy All")
    ok_btn = QPushButton("Close")
    ok_btn.setDefault(True)
    button_row.addWidget(copy_btn)
    button_row.addWidget(ok_btn)
    layout.addLayout(button_row)

    def _copy_all():
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(raw.toPlainText())
        copy_btn.setText("Copied")

    copy_btn.clicked.connect(_copy_all)
    ok_btn.clicked.connect(dialog.accept)

    dialog.exec_()
    return dialog
