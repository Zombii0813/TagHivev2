"""TagHive Sidecar Entry Point for PyInstaller

This is a standalone entry point that doesn't use relative imports.
It's designed to work with PyInstaller to create a bundled executable.
"""

import sys
import os

# Add the src-python directory to Python path so 'app' package can be found
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    bundle_dir = os.path.dirname(sys.executable)
else:
    # Running in normal Python environment
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

# Add the parent directory to path so we can import 'app'
parent_dir = os.path.dirname(bundle_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Now import and run the main application
from app.main import main

if __name__ == "__main__":
    main()
