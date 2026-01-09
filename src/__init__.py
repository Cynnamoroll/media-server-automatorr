"""
Media Server Automatorr - Modular Setup Components

This package contains the modular components for the media server setup script.
"""

__version__ = "1.0.0"

from .compose_generator import ComposeGenerator
from .setup_core import MediaServerSetup
from .template_loader import TemplateLoader
from .vpn_config import GluetunConfigurator

__all__ = [
    "MediaServerSetup",
    "GluetunConfigurator",
    "TemplateLoader",
    "ComposeGenerator",
]
