#!/usr/bin/env python3
"""
PasarGuard CLI Wrapper
This script provides a simple entry point for the PasarGuard CLI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from cli.main import app

    if len(sys.argv) == 1:
        sys.argv.append("--help")
    app()
except ImportError as e:
    print(f"Error importing CLI: {e}")
    print("Make sure you're running this from the PasarGuard project directory.")
    sys.exit(1)
except Exception as e:
    print(f"Error running CLI: {e}")
    sys.exit(1)
