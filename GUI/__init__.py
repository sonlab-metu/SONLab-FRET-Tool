"""
SONLab FRET Tool - GUI Package
"""

# Import main GUI class with lazy loading to avoid circular imports
__all__ = ['SONLabGUI']

# Initialize module-level variables to None
SONLabGUI = None

def __getattr__(name):
    global SONLabGUI
    if name == 'SONLabGUI':
        if SONLabGUI is None:
            from .main_gui import SONLabGUI as _SONLabGUI
            SONLabGUI = _SONLabGUI
        return SONLabGUI
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
