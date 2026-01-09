"""
Pytest configuration and shared fixtures for media-server-automatorr tests.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Generator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_docker_dir(temp_dir: Path) -> Path:
    """Create a mock Docker directory structure."""
    docker_dir = temp_dir / "docker"
    docker_dir.mkdir()
    (docker_dir / "compose").mkdir()
    return docker_dir


@pytest.fixture
def mock_media_dir(temp_dir: Path) -> Path:
    """Create a mock media directory structure."""
    media_dir = temp_dir / "media"
    media_dir.mkdir()

    # Create subdirectories
    subdirs = [
        "downloads/incomplete",
        "downloads/complete",
        "movies",
        "tv",
        "music",
        "books",
        "comics",
    ]

    for subdir in subdirs:
        (media_dir / subdir).mkdir(parents=True)

    return media_dir


@pytest.fixture
def sample_services() -> Dict:
    """Return sample service definitions for testing."""
    return {
        "jellyfin": {
            "name": "Jellyfin",
            "description": "Free media server",
            "category": "media_servers",
            "image": "jellyfin/jellyfin:latest",
            "port": 8096,
            "volumes": {"/config": "config"},
            "media_volumes": {"/media": "."},
            "env": ["PUID", "PGID", "TZ"],
            "setup_steps": ["Open web interface", "Complete setup wizard"],
        },
        "qbittorrent": {
            "name": "qBittorrent",
            "description": "Torrent client",
            "category": "download_clients",
            "image": "lscr.io/linuxserver/qbittorrent:latest",
            "port": 8080,
            "extra_ports": [6881],
            "volumes": {"/config": "config"},
            "media_volumes": {"/downloads": "downloads"},
            "env": ["PUID", "PGID", "TZ"],
            "setup_steps": [
                "Get initial password from logs",
                "Configure downloads path",
            ],
        },
        "gluetun": {
            "name": "Gluetun",
            "description": "VPN client container",
            "category": "utility",
            "image": "qmcgaw/gluetun:latest",
            "port": 8888,
            "extra_ports": [8388],
            "volumes": {"/gluetun": "config"},
            "env": ["TZ"],
            "setup_steps": ["Check VPN connection", "Verify routing"],
        },
    }


@pytest.fixture
def sample_categories() -> Dict:
    """Return sample category definitions for testing."""
    return {
        "media_servers": "Media Servers",
        "download_clients": "Download Clients",
        "utility": "Utility Services",
    }


@pytest.fixture
def mock_subprocess():
    """Mock subprocess.run for testing system commands."""
    with patch("subprocess.run") as mock_run:
        # Default successful response
        mock_run.return_value = MagicMock(
            returncode=0, stdout="success output", stderr=""
        )
        yield mock_run


@pytest.fixture
def mock_docker_commands(mock_subprocess):
    """Configure subprocess mock for Docker commands."""

    def side_effect(cmd, **kwargs):
        mock_result = MagicMock()

        if cmd[0] == "docker" and cmd[1] == "--version":
            mock_result.returncode = 0
            mock_result.stdout = "Docker version 24.0.0"
        elif cmd[0] == "docker" and cmd[1] == "compose" and cmd[2] == "version":
            mock_result.returncode = 0
            mock_result.stdout = "Docker Compose version 2.20.0"
        elif cmd[0] == "docker" and cmd[1] == "ps":
            mock_result.returncode = 0
            mock_result.stdout = "CONTAINER ID   IMAGE"
        else:
            mock_result.returncode = 0
            mock_result.stdout = ""

        mock_result.stderr = ""
        return mock_result

    mock_subprocess.side_effect = side_effect
    return mock_subprocess


@pytest.fixture
def mock_os_operations():
    """Mock OS operations like getuid, geteuid, etc."""
    with patch("os.getuid", return_value=1000), patch(
        "os.getgid", return_value=1000
    ), patch("os.geteuid", return_value=1000), patch("os.getenv") as mock_getenv:
        mock_getenv.side_effect = lambda key, default=None: {
            "USER": "testuser",
            "SSH_CLIENT": None,
            "SSH_CONNECTION": None,
        }.get(key, default)

        yield


@pytest.fixture
def mock_network_operations():
    """Mock network operations for testing."""
    with patch("socket.socket") as mock_socket, patch(
        "src.utils.get_local_network_ip", return_value="192.168.1.100"
    ), patch("src.utils.get_docker_network_subnet", return_value="172.17.0.0/16"):
        # Mock socket for connectivity tests
        mock_socket_instance = MagicMock()
        mock_socket_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_socket_instance

        yield


@pytest.fixture
def templates_dir(temp_dir: Path) -> Path:
    """Create a temporary templates directory with sample files."""
    templates_dir = temp_dir / "templates"
    templates_dir.mkdir()

    # Create docker-services.yaml
    services_yaml = templates_dir / "docker-services.yaml"
    services_yaml.write_text(
        """
categories:
  media_servers: "Media Servers"
  download_clients: "Download Clients"
  utility: "Utility Services"

services:
  jellyfin:
    name: Jellyfin
    description: Free media server
    category: media_servers
    image: jellyfin/jellyfin:latest
    port: 8096
    volumes:
      /config: config
    media_volumes:
      /media: "."
    env:
      - PUID
      - PGID
      - TZ
    setup_steps:
      - "Open web interface"
      - "Complete setup wizard"
"""
    )

    # Create template files
    header_template = templates_dir / "setup-guide-header.md"
    header_template.write_text(
        "# Setup Guide\n\nDocker Dir: {docker_dir}\nMedia Dir: {media_dir}\n"
    )

    footer_template = templates_dir / "setup-guide-footer.md"
    footer_template.write_text("## Support\n\nFor help, check the documentation.")

    return templates_dir


@pytest.fixture
def mock_yaml_load(templates_dir: Path):
    """Mock YAML loading to use test templates."""
    with patch("src.constants.TEMPLATES_DIR", templates_dir):
        yield


@pytest.fixture
def gluetun_config():
    """Create a mock Gluetun configuration for testing."""
    from src.vpn_config import GluetunConfigurator

    config = GluetunConfigurator()
    config.enabled = True
    config.provider = "nordvpn"
    config.vpn_type = "openvpn"
    config.credentials = {"OPENVPN_USER": "testuser", "OPENVPN_PASSWORD": "testpass"}
    config.server_countries = "Netherlands,Germany"
    config.route_qbittorrent = True
    config.docker_subnet = "172.17.0.0/16"

    return config


@pytest.fixture
def mock_container_operations():
    """Mock Docker container operations."""
    with patch("subprocess.run") as mock_run:

        def container_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.stderr = ""

            if "docker" in cmd and "exec" in cmd and "gluetun" in cmd:
                # Mock VPN IP test
                mock_result.returncode = 0
                mock_result.stdout = "198.51.100.1"  # VPN IP
            elif "docker" in cmd and "logs" in cmd and "gluetun" in cmd:
                # Mock container logs
                mock_result.returncode = 0
                mock_result.stdout = "INFO: VPN is up\nSUCCESS: Connected to VPN"
            elif "docker" in cmd and "ps" in cmd:
                # Mock container status
                mock_result.returncode = 0
                mock_result.stdout = "gluetun\nqbittorrent"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""

            return mock_result

        mock_run.side_effect = container_side_effect
        yield mock_run


# Test markers
pytest_plugins = []


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (slower)"
    )
    config.addinivalue_line("markers", "docker: marks tests that require Docker")
    config.addinivalue_line(
        "markers", "network: marks tests that require network access"
    )
