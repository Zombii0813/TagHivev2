"""TagHive Sidecar Entry Point for PyInstaller

This is a standalone entry point that doesn't use relative imports.
It's designed to work with PyInstaller to create a bundled executable.
"""

import sys
import os

# PyInstaller multiprocessing support - MUST be first
if getattr(sys, 'frozen', False):
    import multiprocessing
    multiprocessing.freeze_support()

# Add the src-python directory to Python path so 'app' package can be found
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle (onedir mode)
    # sys.executable is <sidecar_dir>/taghive-sidecar.exe
    # _MEIPASS is the temp extraction dir in onefile, or the exe dir in onedir
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    # Running in normal Python environment
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

# In onedir mode, 'app' package is placed directly inside bundle_dir via --add-data
# In normal mode, 'app' is a sibling of this file (both in src-python/)
if bundle_dir not in sys.path:
    sys.path.insert(0, bundle_dir)

# Now import and run the main application
from app.main import main

if __name__ == "__main__":
    main()
