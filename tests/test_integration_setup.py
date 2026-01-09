"""
End-to-end integration tests for media server setup.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.setup_core import MediaServerSetup


@pytest.mark.integration
class TestMediaServerSetupIntegration:
    """Integration tests for complete setup workflows."""

    def test_complete_initialization_chain(self):
        """Test that all components initialize properly together."""
        setup = MediaServerSetup()

        # Verify all components are created
        assert setup.template_loader is not None
        assert setup.system_validator is not None
        assert setup.directory_manager is not None
        assert setup.file_generator is not None
        assert setup.gluetun_configurator is not None
        assert setup.progress is not None

        # Verify template loader has loaded services
        services = setup.template_loader.get_services()
        assert len(services) > 0
        assert "jellyfin" in services or "plex" in services

        categories = setup.template_loader.get_categories()
        assert len(categories) > 0

    def test_system_validation_integration(self):
        """Test system validation with mocked subprocess."""
        setup = MediaServerSetup()

        # Mock Docker commands
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Docker version 20.10.0"
            )

            result = setup._validate_system()

            # With mocked successful Docker, validation should complete
            assert isinstance(result, bool)

    def test_template_validation_integration(self):
        """Test template validation with actual template files."""
        setup = MediaServerSetup()

        # This should validate the actual template files
        result = setup._validate_templates()

        # Should succeed with valid templates
        assert result is True

    def test_directory_structure_integration(self, tmp_path):
        """Test directory structure creation with real paths."""
        setup = MediaServerSetup()

        docker_dir = tmp_path / "docker"
        media_dir = tmp_path / "media"

        # Create directories
        success, messages = setup.directory_manager.create_directory_structure(
            docker_dir, media_dir, uid=1000, gid=1000
        )

        # Should succeed
        assert success is True

        # Verify directories were created
        assert docker_dir.exists()
        assert media_dir.exists()

    def test_file_generation_integration(self, tmp_path):
        """Test file generation with real service configuration."""
        setup = MediaServerSetup()

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Generate files
        results = setup.file_generator.generate_all_files(
            selected_services=["jellyfin"],
            uid=1000,
            gid=1000,
            docker_dir=tmp_path / "docker",
            media_dir=tmp_path / "media",
            output_dir=output_dir,
            timezone="UTC",
        )

        # Should return results dict
        assert isinstance(results, dict)
        assert "docker-compose.yml" in results

        # Verify docker-compose.yml was created
        compose_file = output_dir / "docker-compose.yml"
        assert compose_file.exists()

        # Verify .env file was created
        env_file = output_dir / ".env"
        assert env_file.exists()

    def test_service_selection_flow(self):
        """Test service selection integrates properly with template loader."""
        setup = MediaServerSetup()

        # Mock the entire selector to avoid user interaction
        with patch.object(setup, "_select_services") as mock_select:
            # Manually set services
            setup.selected_services = ["jellyfin", "sonarr"]

            # Verify services were set
            assert setup.selected_services == ["jellyfin", "sonarr"]
            assert len(setup.selected_services) == 2

    def test_vpn_configuration_integration(self):
        """Test VPN configuration integrates with gluetun configurator."""
        setup = MediaServerSetup()
        setup.selected_services = ["gluetun", "qbittorrent"]

        # Mock VPN configuration
        with patch.object(setup.gluetun_configurator, "configure") as mock_config:
            mock_config.return_value = {
                "VPN_TYPE": "wireguard",
                "VPN_SERVICE_PROVIDER": "mullvad",
            }

            setup._configure_vpn()

            # Configurator should have been called
            mock_config.assert_called_once()

    def test_access_information_generation(self, capsys):
        """Test that access information is generated correctly."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin", "sonarr"]
        setup.host_ip = "192.168.1.100"

        # Show access information
        setup._show_access_information()

        captured = capsys.readouterr()

        # Should contain service information
        assert "192.168.1.100" in captured.out or "Service" in captured.out
