#!/usr/bin/env python3
"""
Media Server Setup Script
A user-friendly interactive script to deploy a complete media server stack.

This script uses modular components for better maintainability.
"""

import sys
from pathlib import Path

# Add src directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR / "src"))

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)

from src.setup_core import MediaServerSetup


def main() -> None:
    """Main entry point for the setup script."""
    setup = MediaServerSetup()
    setup.run()


if __name__ == "__main__":
    main()
