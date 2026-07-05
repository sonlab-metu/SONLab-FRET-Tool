"""
Centralised design system for the SONLab FRET Tool.

This module is the single source of truth for the application's visual
appearance. It defines a small colour system for the light and dark themes and
builds a matching :class:`~PyQt5.QtGui.QPalette` and Qt style sheet from it, so
every tab and dialog is styled consistently from one place.

Public helpers
--------------
``build_qpalette(theme)``      -> QPalette for ``"light"`` or ``"dark"``
``build_stylesheet(theme)``    -> modern QSS string for the whole application
``apply_matplotlib_style(theme)`` -> update matplotlib rcParams to match

Semantic buttons
----------------
Give any :class:`QPushButton` one of the following ``objectName`` values to
receive a coloured, accent style that adapts to the active theme:

``primaryButton``  -> accent / call-to-action
``successButton``  -> confirming / "save & transfer" style actions
``dangerButton``   -> destructive or "acceptor" channel actions
``ghostButton``    -> low-emphasis, borderless action
"""

# ---------------------------------------------------------------------------
# Colour system
# ---------------------------------------------------------------------------
# Every value is a hex string. Keeping the two themes structurally identical
# means the same style-sheet template works for both.

LIGHT = {
    "window": "#f4f6f9",       # app background
    "surface": "#ffffff",      # cards / group boxes / panels
    "surface_alt": "#eef1f6",  # subtle raised areas (headers, hover rows)
    "base": "#ffffff",         # editable field background
    "border": "#dce1e9",       # default separators / outlines
    "border_strong": "#c4ccd8",
    "text": "#1f2733",         # primary text
    "text_muted": "#5b6673",   # secondary / hint text
    "text_disabled": "#a4adba",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_pressed": "#1b3fa8",
    "accent_soft": "#e6edfd",  # tinted background for selection / focus
    "success": "#15a24a",
    "success_hover": "#128a3f",
    "danger": "#dc2626",
    "danger_hover": "#b91c1c",
    "on_accent": "#ffffff",
    "selection": "#2563eb",
    "selection_text": "#ffffff",
    # matplotlib canvas surround / axes
    "figure": "#ffffff",
    "plot_grid": "#e2e6ec",
    "plot_edge": "#c4ccd8",
}

DARK = {
    "window": "#191c22",
    "surface": "#23272f",
    "surface_alt": "#2b3038",
    "base": "#15181d",
    "border": "#333945",
    "border_strong": "#3f4653",
    "text": "#e6e9ee",
    "text_muted": "#9aa4b2",
    "text_disabled": "#5c6470",
    "accent": "#3b82f6",
    "accent_hover": "#5a97f8",
    "accent_pressed": "#2f6fd6",
    "accent_soft": "#243447",
    "success": "#22c55e",
    "success_hover": "#38d06f",
    "danger": "#ef4444",
    "danger_hover": "#f2635f",
    "on_accent": "#ffffff",
    "selection": "#3b82f6",
    "selection_text": "#ffffff",
    "figure": "#1b1e24",
    "plot_grid": "#333945",
    "plot_edge": "#4a515e",
}


def palette(theme):
    """Return the raw colour dictionary for ``theme`` (defaults to dark)."""
    return DARK if str(theme).lower() == "dark" else LIGHT


# ---------------------------------------------------------------------------
# QPalette
# ---------------------------------------------------------------------------

def build_qpalette(theme):
    """Build a :class:`QPalette` matching ``theme``.

    The palette carries the base colours so that native/Fusion-drawn controls
    (check boxes, radio buttons, spin-box arrows, sliders) pick up the theme
    even where the style sheet stays deliberately minimal.
    """
    from PyQt5.QtGui import QPalette, QColor
    from PyQt5.QtCore import Qt

    c = palette(theme)

    def col(key):
        return QColor(c[key])

    p = QPalette()
    p.setColor(QPalette.Window, col("window"))
    p.setColor(QPalette.WindowText, col("text"))
    p.setColor(QPalette.Base, col("base"))
    p.setColor(QPalette.AlternateBase, col("surface_alt"))
    p.setColor(QPalette.ToolTipBase, col("surface"))
    p.setColor(QPalette.ToolTipText, col("text"))
    p.setColor(QPalette.Text, col("text"))
    p.setColor(QPalette.Button, col("surface"))
    p.setColor(QPalette.ButtonText, col("text"))
    p.setColor(QPalette.BrightText, QColor(c["danger"]))
    p.setColor(QPalette.Link, col("accent"))
    p.setColor(QPalette.LinkVisited, col("accent_pressed"))
    p.setColor(QPalette.Highlight, col("selection"))
    p.setColor(QPalette.HighlightedText, col("selection_text"))
    p.setColor(QPalette.PlaceholderText, col("text_muted"))

    # Disabled roles keep controls legible but visibly inactive.
    disabled = col("text_disabled")
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, disabled)
    p.setColor(QPalette.Disabled, QPalette.Highlight, col("border_strong"))

    return p


# ---------------------------------------------------------------------------
# Style sheet
# ---------------------------------------------------------------------------

def build_stylesheet(theme):
    """Return the full application style sheet for ``theme``."""
    c = palette(theme)
    return _STYLESHEET_TEMPLATE.format(**c)


def compact_stylesheet():
    """Extra QSS appended in compact mode: smaller font and tighter controls.

    Designed for small screens — it shrinks the base font and trims padding on
    every control so noticeably more fits on screen (and long button labels stop
    truncating). Appended after :func:`build_stylesheet`, so it overrides it.
    """
    return """
        QWidget { font-size: 9pt; }
        QGroupBox { margin-top: 11px; padding: 7px 8px 8px 8px; }
        QGroupBox::title { left: 8px; padding: 0 4px; }
        QPushButton { padding: 3px 9px; min-height: 14px; }
        QToolButton { padding: 2px; }
        QLineEdit, QPlainTextEdit, QTextEdit,
        QSpinBox, QDoubleSpinBox, QComboBox { padding: 2px 6px; }
        QTabBar::tab { padding: 5px 11px; }
        QMenuBar::item { padding: 3px 7px; }
        QListWidget::item, QTreeWidget::item { padding: 2px 5px; }
        QToolBar { padding: 2px; }
        QToolBar QToolButton { padding: 2px; }
    """


_STYLESHEET_TEMPLATE = """
/* ===== Base ===================================================== */
QWidget {{
    color: {text};
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background-color: {window};
}}
QToolTip {{
    color: {text};
    background-color: {surface};
    border: 1px solid {border_strong};
    border-radius: 6px;
    padding: 5px 8px;
}}

/* ===== Menu bar & menus ======================================== */
QMenuBar {{
    background-color: {window};
    color: {text};
    border-bottom: 1px solid {border};
    padding: 3px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 10px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background: {surface_alt};
}}
QMenuBar::item:pressed {{
    background: {accent_soft};
}}
QMenu {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 24px 6px 20px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {accent};
    color: {on_accent};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 6px 8px;
}}

/* ===== Tabs ==================================================== */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 10px;
    background: {surface};
    top: -1px;
}}
QTabBar {{
    qproperty-drawBase: 0;
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {text_muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 16px;
    margin: 0 2px;
    min-width: 80px;
}}
QTabBar::tab:hover:!selected {{
    color: {text};
    border-bottom: 2px solid {border_strong};
}}
QTabBar::tab:selected {{
    color: {accent};
    border-bottom: 2px solid {accent};
}}

/* ===== Group boxes (cards) ==================================== */
QGroupBox {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 12px 12px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: {text_muted};
}}

/* ===== Buttons ================================================ */
QPushButton {{
    background-color: {surface_alt};
    color: {text};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 6px 11px;
    min-height: 18px;
}}
QPushButton:hover {{
    border-color: {accent};
    background-color: {accent_soft};
}}
QPushButton:pressed {{
    background-color: {border};
}}
QPushButton:disabled {{
    color: {text_disabled};
    background-color: {surface};
    border-color: {border};
}}
QPushButton:focus {{
    outline: none;
    border-color: {accent};
}}

/* Semantic button variants (set via objectName) */
QPushButton#primaryButton {{
    background-color: {accent};
    color: {on_accent};
    border: 1px solid {accent};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{ background-color: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#primaryButton:pressed {{ background-color: {accent_pressed}; border-color: {accent_pressed}; }}

QPushButton#successButton {{
    background-color: {success};
    color: {on_accent};
    border: 1px solid {success};
    font-weight: 600;
}}
QPushButton#successButton:hover {{ background-color: {success_hover}; border-color: {success_hover}; }}

QPushButton#dangerButton {{
    background-color: {danger};
    color: {on_accent};
    border: 1px solid {danger};
    font-weight: 600;
}}
QPushButton#dangerButton:hover {{ background-color: {danger_hover}; border-color: {danger_hover}; }}

QPushButton#primaryButton:disabled,
QPushButton#successButton:disabled,
QPushButton#dangerButton:disabled {{
    background-color: {surface};
    color: {text_disabled};
    border-color: {border};
}}

QPushButton#ghostButton {{
    background: transparent;
    border: none;
    color: {accent};
    padding: 6px 10px;
}}
QPushButton#ghostButton:hover {{ background: {accent_soft}; }}

/* Info control shown next to parameter fields */
QToolButton#infoButton {{
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 1px;
}}
QToolButton#infoButton:hover {{
    background: {accent_soft};
}}

/* ===== Text & numeric inputs ================================= */
QLineEdit, QPlainTextEdit, QTextEdit,
QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {base};
    color: {text};
    border: 1px solid {border_strong};
    border-radius: 8px;
    padding: 5px 8px;
    selection-background-color: {selection};
    selection-color: {selection_text};
}}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover,
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: {border_strong};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{
    color: {text_disabled};
    background-color: {surface};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid {border};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {accent};
    selection-color: {on_accent};
    outline: none;
}}

/* ===== List / tree / table =================================== */
QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView, QTableView {{
    background-color: {base};
    color: {text};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 2px;
    outline: none;
    alternate-background-color: {surface_alt};
}}
QListWidget::item, QTreeWidget::item {{
    padding: 4px 6px;
    border-radius: 6px;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{
    background-color: {surface_alt};
}}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {{
    background-color: {accent};
    color: {on_accent};
}}
QHeaderView::section {{
    background-color: {surface_alt};
    color: {text_muted};
    padding: 6px 8px;
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    font-weight: 600;
}}

/* ===== Progress bar ========================================== */
QProgressBar {{
    background-color: {surface_alt};
    border: 1px solid {border};
    border-radius: 8px;
    height: 16px;
    text-align: center;
    color: {text};
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 7px;
}}

/* ===== Sliders =============================================== */
QSlider::groove:horizontal {{
    height: 5px;
    background: {surface_alt};
    border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {surface};
    border: 2px solid {accent};
    width: 15px;
    height: 15px;
    margin: -6px 0;
    border-radius: 9px;
}}
QSlider::handle:horizontal:hover {{
    background: {accent_soft};
}}

/* ===== Check boxes & radios ================================= */
QCheckBox, QRadioButton {{
    spacing: 7px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
}}

/* ===== Toolbar (matplotlib navigation) ====================== */
QToolBar {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 10px;
    spacing: 3px;
    padding: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 4px;
    margin: 1px;
}}
QToolBar QToolButton:hover {{
    background: {surface_alt};
    border-color: {border};
}}
QToolBar QToolButton:pressed, QToolBar QToolButton:checked {{
    background: {accent_soft};
    border-color: {accent};
}}

/* ===== Status bar ============================================ */
QStatusBar {{
    background: {window};
    color: {text_muted};
    border-top: 1px solid {border};
}}

/* ===== Scrollbars =========================================== */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {border_strong};
    border-radius: 5px;
    min-height: 28px;
    min-width: 28px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {text_muted};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ===== Splitter handle ====================================== */
QSplitter::handle {{
    background: {border};
}}
QSplitter::handle:hover {{
    background: {accent};
}}
"""


# ---------------------------------------------------------------------------
# Matplotlib
# ---------------------------------------------------------------------------
# The tabs embed many matplotlib canvases and navigation toolbars. Rather than
# let each tab hard-code its own colours (which historically drifted out of sync
# and left dark-mode toolbar icons invisible), everything routes through the
# helpers below so plots and toolbars always track the active theme.

# Bright, high-contrast line colours for dark-theme plots.
_DARK_CYCLE = ["#FF6B6B", "#4ECDC4", "#F7E967", "#C44DFF", "#1E90FF", "#FFA500"]


def mpl_colors(theme):
    """Canonical matplotlib colour set for ``theme``.

    Keys: ``bg`` (figure/axes face), ``fg`` (text/ticks/labels), ``grid``,
    ``edge`` (spines), ``icon`` (toolbar icon tint), ``cycle`` (line colours).
    """
    c = palette(theme)
    is_dark = str(theme).lower() == "dark"
    return {
        "bg": c["figure"],
        "fg": c["text"],
        "grid": c["plot_grid"],
        "edge": c["plot_edge"],
        "icon": c["text"],
        "cycle": list(_DARK_CYCLE) if is_dark else None,
        "is_dark": is_dark,
    }


def apply_matplotlib_style(theme):
    """Sync matplotlib rcParams with ``theme`` so new plots match the UI."""
    try:
        import matplotlib as mpl
    except ImportError:
        return

    c = palette(theme)
    m = mpl_colors(theme)
    mpl.rcParams.update({
        "figure.facecolor": m["bg"],
        "axes.facecolor": m["bg"],
        "savefig.facecolor": m["bg"],
        "text.color": m["fg"],
        "axes.labelcolor": m["fg"],
        "axes.edgecolor": m["edge"],
        "xtick.color": m["fg"],
        "ytick.color": m["fg"],
        "axes.grid": True,
        "grid.color": m["grid"],
        "grid.alpha": 0.5 if m["is_dark"] else 0.8,
        "figure.titleweight": "bold",
        "axes.titleweight": "bold",
        "legend.framealpha": 0.85,
        "legend.facecolor": c["surface"],
        "legend.edgecolor": c["border"],
    })


def apply_axes_theme(ax, theme, set_cycle=False):
    """Recolour a single Axes (face, ticks, spines, labels, grid, legend)."""
    m = mpl_colors(theme)
    ax.set_facecolor(m["bg"])
    ax.tick_params(axis="both", which="both", colors=m["fg"])
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(m["fg"])
    for spine in ax.spines.values():
        spine.set_edgecolor(m["edge"])
    ax.xaxis.label.set_color(m["fg"])
    ax.yaxis.label.set_color(m["fg"])
    if ax.get_title():
        ax.title.set_color(m["fg"])
    ax.grid(True, color=m["grid"], alpha=0.4)
    if set_cycle:
        ax.set_prop_cycle(color=m["cycle"]) if m["cycle"] else ax.set_prop_cycle(None)
    legend = ax.get_legend()
    if legend is not None:
        frame = legend.get_frame()
        frame.set_facecolor(m["bg"])
        frame.set_edgecolor(m["edge"])
        for text in legend.get_texts():
            text.set_color(m["fg"])


def apply_figure_theme(fig, theme, set_cycle=False):
    """Recolour a whole Figure and all of its Axes to match ``theme``."""
    if fig is None:
        return
    m = mpl_colors(theme)
    fig.set_facecolor(m["bg"])
    fig.set_edgecolor(m["edge"])
    for ax in fig.get_axes():
        apply_axes_theme(ax, theme, set_cycle=set_cycle)


def tint_pixmap(pixmap, color):
    """Return ``pixmap`` recoloured to ``color``, preserving its alpha shape.

    Matplotlib toolbar icons are monochrome PNGs; a plain style-sheet ``color``
    rule cannot touch them, so we composite the requested colour through the
    icon's alpha channel instead.
    """
    from PyQt5.QtGui import QPixmap, QPainter, QColor
    from PyQt5.QtCore import Qt

    if pixmap is None or pixmap.isNull():
        return pixmap
    out = QPixmap(pixmap.size())
    out.setDevicePixelRatio(pixmap.devicePixelRatio())
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), QColor(color) if not isinstance(color, QColor) else color)
    painter.end()
    return out


def style_toolbar(toolbar, theme):
    """Make one matplotlib navigation ``toolbar`` track ``theme``.

    Clears any per-widget style sheet so the global ``QToolBar`` styling
    applies, and tints the (pixmap) action icons to the theme's text colour so
    they stay legible on both light and dark toolbars.
    """
    from PyQt5.QtGui import QIcon, QColor
    from PyQt5.QtCore import QSize

    if toolbar is None:
        return
    toolbar.setStyleSheet("")  # defer to the global QToolBar QSS
    color = QColor(palette(theme)["text"])

    cache = getattr(toolbar, "_theme_orig_icons", None)
    if cache is None:
        cache = {}
        toolbar._theme_orig_icons = cache

    for action in toolbar.actions():
        icon = action.icon()
        if action not in cache:
            if icon is None or icon.isNull():
                continue  # separators / label actions have no icon
            cache[action] = icon
        original = cache[action]
        if original.isNull():
            continue
        size = original.actualSize(QSize(24, 24))
        action.setIcon(QIcon(tint_pixmap(original.pixmap(size), color)))


def style_navigation_toolbars(root, theme):
    """Style every matplotlib navigation toolbar under ``root`` for ``theme``."""
    try:
        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
    except ImportError:
        return
    if root is None:
        return
    for toolbar in root.findChildren(NavigationToolbar2QT):
        style_toolbar(toolbar, theme)


def current_theme_name(app=None):
    """Infer the active theme from the application palette ('dark'/'light')."""
    from PyQt5.QtWidgets import QApplication
    app = app or QApplication.instance()
    if app is None:
        return "dark"
    return "dark" if app.palette().window().color().lightness() < 128 else "light"
