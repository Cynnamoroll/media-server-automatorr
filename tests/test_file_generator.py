"""
Tests for file_generator module.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml

from src.file_generator import FileGenerator


class TestFileGenerator:
    """Test FileGenerator class."""

    def test_init(self):
        """Test FileGenerator initialization."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        assert generator.loader == mock_loader
        assert generator.compose_generator is not None

    def test_generate_env_file_success(self, temp_dir):
        """Test successful .env file generation."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        success = generator._generate_env_file(temp_dir, "America/New_York")

        assert success is True
        env_file = temp_dir / ".env"
        assert env_file.exists()

        content = env_file.read_text()
        assert "COMPOSE_PROJECT_NAME=mediaserver" in content
        assert "TZ=America/New_York" in content
        assert "# Environment variables for docker-compose" in content

    def test_generate_env_file_failure(self, temp_dir):
        """Test .env file generation failure."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Mock write_text to fail
        with patch.object(Path, "write_text", side_effect=OSError("Permission denied")):
            success = generator._generate_env_file(temp_dir, "UTC")

        assert success is False

    def test_generate_compose_file_success(
        self, temp_dir, sample_services, gluetun_config
    ):
        """Test successful docker-compose.yml generation."""
        mock_loader = Mock()
        mock_compose_gen = Mock()
        mock_compose_gen.generate.return_value = (
            "version: '3.8'\nservices:\n  test:\n    image: test:latest"
        )

        generator = FileGenerator(mock_loader)
        generator.compose_generator = mock_compose_gen

        success = generator._generate_compose_file(
            ["jellyfin"],
            1000,
            1000,
            temp_dir / "docker",
            temp_dir / "media",
            temp_dir,
            "UTC",
            "test_key",
            gluetun_config,
        )

        assert success is True
        compose_file = temp_dir / "docker-compose.yml"
        assert compose_file.exists()

        content = compose_file.read_text()
        assert "version: '3.8'" in content
        assert "services:" in content

    def test_generate_compose_file_failure(self, temp_dir, gluetun_config):
        """Test docker-compose.yml generation failure."""
        mock_loader = Mock()
        mock_compose_gen = Mock()
        mock_compose_gen.generate.side_effect = Exception("Generation failed")

        generator = FileGenerator(mock_loader)
        generator.compose_generator = mock_compose_gen

        success = generator._generate_compose_file(
            ["jellyfin"],
            1000,
            1000,
            temp_dir / "docker",
            temp_dir / "media",
            temp_dir,
            "UTC",
            "test_key",
            gluetun_config,
        )

        assert success is False

    def test_generate_setup_guide_success(
        self, temp_dir, sample_services, gluetun_config
    ):
        """Test successful setup guide generation."""
        mock_loader = Mock()
        mock_loader.get_services.return_value = sample_services
        mock_loader.load_template.side_effect = [
            "# Setup Guide Header\nDocker: {docker_dir}\nMedia: {media_dir}",
            "## Footer\nEnd of guide",
        ]

        generator = FileGenerator(mock_loader)

        success = generator._generate_setup_guide(
            ["jellyfin", "qbittorrent"],
            temp_dir / "docker",
            temp_dir / "media",
            temp_dir,
            gluetun_config,
        )

        assert success is True
        guide_file = temp_dir / "SETUP_GUIDE.md"
        assert guide_file.exists()

        content = guide_file.read_text()
        assert "Setup Guide Header" in content
        assert "Service Configuration" in content
        assert "Footer" in content

    def test_generate_setup_guide_failure(self, temp_dir):
        """Test setup guide generation failure."""
        mock_loader = Mock()
        mock_loader.get_services.side_effect = Exception("Template load failed")

        generator = FileGenerator(mock_loader)

        success = generator._generate_setup_guide(
            ["jellyfin"], temp_dir / "docker", temp_dir / "media", temp_dir, None
        )

        assert success is False

    def test_generate_service_setup_section(self, sample_services, gluetun_config):
        """Test service setup section generation."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        service = sample_services["jellyfin"]

        lines = generator._generate_service_setup_section(
            "jellyfin", service, 1, 3, gluetun_config
        )

        assert any("1. Jellyfin" in line for line in lines)
        assert any("Access URL:" in line for line in lines)
        assert any("Port:" in line for line in lines)
        assert any("Setup Steps:" in line for line in lines)

    def test_generate_service_setup_section_qbittorrent_via_vpn(self, sample_services):
        """Test qBittorrent service section when routed through VPN."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Create gluetun config with qBittorrent routing
        mock_gluetun = Mock()
        mock_gluetun.enabled = True
        mock_gluetun.route_qbittorrent = True

        service = sample_services["qbittorrent"]

        lines = generator._generate_service_setup_section(
            "qbittorrent", service, 1, 3, mock_gluetun
        )

        # Should indicate access via Gluetun
        assert any("via Gluetun" in line for line in lines)

    def test_generate_vpn_setup_section_enabled(self):
        """Test VPN setup section when VPN is enabled."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        mock_gluetun = Mock()
        mock_gluetun.enabled = True
        mock_gluetun.provider = "nordvpn"
        mock_gluetun.vpn_type = "openvpn"
        mock_gluetun.server_countries = "Netherlands"
        mock_gluetun.route_qbittorrent = True

        lines = generator._generate_vpn_setup_section(mock_gluetun)

        assert any("VPN Configuration" in line for line in lines)
        assert any("nordvpn" in line.lower() for line in lines)
        assert any("openvpn" in line.lower() for line in lines)
        assert any("Netherlands" in line for line in lines)
        assert any("Testing VPN Connection:" in line for line in lines)
        assert any("gluetun" in line for line in lines)

    def test_generate_troubleshooting_section_basic(self):
        """Test troubleshooting section generation."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        lines = generator._generate_troubleshooting_section(["jellyfin"])

        assert any("Troubleshooting" in line for line in lines)
        assert any("Common Issues" in line for line in lines)
        assert any("Can't access web interfaces" in line for line in lines)

    def test_generate_troubleshooting_section_with_services(self):
        """Test troubleshooting section with specific services."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        lines = generator._generate_troubleshooting_section(
            ["qbittorrent", "sonarr", "gluetun"]
        )

        assert any("qBittorrent Issues:" in line for line in lines)
        assert any("*arr App Issues:" in line for line in lines)
        assert any("VPN (Gluetun) Issues:" in line for line in lines)

    def test_set_file_permissions_success(self, temp_dir):
        """Test successful file permissions setting."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Create test files
        test_file1 = temp_dir / "test1.txt"
        test_file1.write_text("content1")
        test_file2 = temp_dir / "test2.txt"
        test_file2.write_text("content2")

        with patch("src.file_generator.run_command") as mock_run:
            with patch("os.geteuid", return_value=1000):  # Non-root
                generator._set_file_permissions(temp_dir, 1000, 1000)

        # Should have called run_command with chown
        assert mock_run.called

    def test_set_file_permissions_as_root(self, temp_dir):
        """Test file permissions setting as root."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Create test file
        test_file = temp_dir / "test.txt"
        test_file.write_text("content")

        with patch("os.chown") as mock_chown:
            with patch("os.geteuid", return_value=0):  # Root
                generator._set_file_permissions(temp_dir, 1000, 1000)

        # Should have called os.chown directly
        mock_chown.assert_called()

    def test_generate_all_files_success(
        self, temp_dir, sample_services, gluetun_config
    ):
        """Test successful generation of all files."""
        mock_loader = Mock()
        mock_loader.get_services.return_value = sample_services
        mock_loader.load_template.side_effect = [
            "# Header template",
            "# Footer template",
        ]

        mock_compose_gen = Mock()
        mock_compose_gen.generate.return_value = (
            "version: '3.8'\nservices:\n  test:\n    image: test"
        )

        generator = FileGenerator(mock_loader)
        generator.compose_generator = mock_compose_gen

        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        results = generator.generate_all_files(
            ["homarr", "jellyfin"],  # Include homarr to test encryption key
            1000,
            1000,
            docker_dir,
            media_dir,
            output_dir,
            "UTC",
            gluetun_config,
        )

        # All files should be generated successfully
        assert results["docker-compose.yml"] is True
        assert results[".env"] is True
        assert results["SETUP_GUIDE.md"] is True

        # Files should exist
        assert (output_dir / "docker-compose.yml").exists()
        assert (output_dir / ".env").exists()
        assert (output_dir / "SETUP_GUIDE.md").exists()

    def test_generate_all_files_with_failures(self, temp_dir, sample_services):
        """Test file generation with some failures."""
        mock_loader = Mock()
        mock_loader.get_services.return_value = sample_services

        # Mock compose generator to fail
        mock_compose_gen = Mock()
        mock_compose_gen.generate.side_effect = Exception("Compose generation failed")

        generator = FileGenerator(mock_loader)
        generator.compose_generator = mock_compose_gen

        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        results = generator.generate_all_files(
            ["jellyfin"], 1000, 1000, docker_dir, media_dir, output_dir, "UTC", None
        )

        # Docker compose should fail, others might succeed
        assert results["docker-compose.yml"] is False

    def test_validate_generated_files_success(self, temp_dir):
        """Test successful file validation."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Create required files with valid content
        (temp_dir / "docker-compose.yml").write_text("version: '3.8'\nservices: {}")
        (temp_dir / ".env").write_text("TZ=UTC")
        (temp_dir / "SETUP_GUIDE.md").write_text("# Setup Guide")

        errors = generator.validate_generated_files(temp_dir)

        assert errors == []

    def test_validate_generated_files_missing_files(self, temp_dir):
        """Test file validation with missing files."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Don't create any files
        errors = generator.validate_generated_files(temp_dir)

        assert len(errors) == 3  # All required files missing
        assert any(
            "Missing required file: docker-compose.yml" in error for error in errors
        )
        assert any("Missing required file: .env" in error for error in errors)
        assert any("Missing required file: SETUP_GUIDE.md" in error for error in errors)

    def test_validate_generated_files_empty_files(self, temp_dir):
        """Test file validation with empty files."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Create empty files
        (temp_dir / "docker-compose.yml").write_text("")
        (temp_dir / ".env").write_text("")
        (temp_dir / "SETUP_GUIDE.md").write_text("")

        errors = generator.validate_generated_files(temp_dir)

        assert len(errors) == 3  # All files are empty
        assert any("Empty file: docker-compose.yml" in error for error in errors)
        assert any("Empty file: .env" in error for error in errors)
        assert any("Empty file: SETUP_GUIDE.md" in error for error in errors)

    def test_validate_generated_files_invalid_yaml(self, temp_dir):
        """Test file validation with invalid YAML."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Create files with valid content except for invalid YAML
        (temp_dir / "docker-compose.yml").write_text("invalid: yaml: content:")
        (temp_dir / ".env").write_text("TZ=UTC")
        (temp_dir / "SETUP_GUIDE.md").write_text("# Setup Guide")

        errors = generator.validate_generated_files(temp_dir)

        assert len(errors) == 1
        assert "Invalid docker-compose.yml format" in errors[0]

    def test_validate_generated_files_yaml_read_error(self, temp_dir):
        """Test file validation with YAML read error."""
        mock_loader = Mock()
        generator = FileGenerator(mock_loader)

        # Create files
        (temp_dir / "docker-compose.yml").write_text("version: '3.8'")
        (temp_dir / ".env").write_text("TZ=UTC")
        (temp_dir / "SETUP_GUIDE.md").write_text("# Setup Guide")

        # Mock open to fail for compose file
        original_open = open

        def mock_open(file, *args, **kwargs):
            if "docker-compose.yml" in str(file):
                raise OSError("Cannot read file")
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open):
            errors = generator.validate_generated_files(temp_dir)

        assert len(errors) == 1
        assert "Could not read docker-compose.yml" in errors[0]
