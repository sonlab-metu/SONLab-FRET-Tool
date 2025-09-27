#!/usr/bin/env python3
"""
Main entry point for the SONLab FRET Tool GUI.
This file allows the package to be run using `python -m GUI`
"""
import os
import sys

def main():
    # Add the parent directory to Python path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Add the parent directory of project_root to Python path
    parent_dir = os.path.dirname(project_root)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    
    # Print debug info
    print("Python path:", sys.path)
    print("Current working directory:", os.getcwd())
    
    try:
        # First try direct import (works when run as python -m GUI)
        from .main_gui import main as gui_main
        gui_main()
    except (ImportError, SystemError) as e:
        print(f"Direct import failed: {e}")
        try:
            # Try absolute import (works when run as python -m SONLab.GUI)
            from SONLab.GUI.main_gui import main as gui_main
            gui_main()
        except ImportError as e2:
            print(f"Absolute import failed: {e2}")
            try:
                # Final fallback - try direct file import
                from main_gui import main as gui_main
                gui_main()
            except ImportError as e3:
                print(f"All import attempts failed. Last error: {e3}")
                print("\nTroubleshooting steps:")
                print(f"1. Current working directory: {os.getcwd()}")
                print(f"2. Python path: {sys.path}")
                print(f"3. Directory contents: {os.listdir(os.getcwd())}")
                print("\nPlease ensure you're running from the project root directory.")
                print("Try: python -m SONLab.GUI from the project root.")
                raise

if __name__ == "__main__":
    main()
