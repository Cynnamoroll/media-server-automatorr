"""
Tests for setup_core module.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.setup_core import MediaServerSetup


class TestMediaServerSetup:
    """Test MediaServerSetup class."""

    def test_init(self):
        """Test MediaServerSetup initialization."""
        setup = MediaServerSetup()

        assert setup.template_loader is not None
        assert setup.system_validator is not None
        assert setup.directory_manager is not None
        assert setup.file_generator is not None
        assert setup.gluetun_configurator is not None
        assert setup.progress.total_steps == 7

        # Check initial state
        assert setup.username == ""
        assert setup.uid == 0
        assert setup.gid == 0
        assert setup.selected_services == []
        assert setup.remote_access is False

    def test_print_welcome_local_mode(self, capsys, mock_os_operations):
        """Test welcome message in local mode."""
        setup = MediaServerSetup()
        setup._print_welcome()

        captured = capsys.readouterr()
        assert "MEDIA SERVER SETUP" in captured.out
        assert "Welcome to the Media Server Setup Script!" in captured.out
        assert "Local setup mode" in captured.out

    def test_print_welcome_ssh_mode(self, capsys):
        """Test welcome message in SSH mode."""
        with patch.dict(os.environ, {"SSH_CLIENT": "192.168.1.100"}):
            setup = MediaServerSetup()
            setup._print_welcome()

        captured = capsys.readouterr()
        assert "SSH connection detected - remote setup mode" in captured.out

    def test_detect_access_mode_local(self, mock_os_operations):
        """Test access mode detection for local access."""
        setup = MediaServerSetup()
        setup._detect_access_mode()

        assert setup.remote_access is False
        assert setup.host_ip == "localhost"

    def test_detect_access_mode_ssh(self):
        """Test access mode detection for SSH access."""
        with patch.dict(os.environ, {"SSH_CLIENT": "192.168.1.100"}):
            with patch("src.setup_core.get_local_network_ip", return_value="10.0.0.5"):
                setup = MediaServerSetup()
                setup._detect_access_mode()

        assert setup.remote_access is True
        assert setup.host_ip == "10.0.0.5"

    def test_validate_system_success(self):
        """Test successful system validation."""
        setup = MediaServerSetup()

        with patch.object(setup.system_validator, "validate_all", return_value=True):
            result = setup._validate_system()

        assert result is True

    def test_validate_system_failure(self):
        """Test failed system validation."""
        setup = MediaServerSetup()

        with patch.object(setup.system_validator, "validate_all", return_value=False):
            result = setup._validate_system()

        assert result is False

    def test_validate_templates_success(self):
        """Test successful template validation."""
        setup = MediaServerSetup()

        with patch.object(setup.template_loader, "validate_services", return_value=[]):
            result = setup._validate_templates()

        assert result is True

    def test_validate_templates_failure(self):
        """Test failed template validation."""
        setup = MediaServerSetup()

        with patch.object(
            setup.template_loader,
            "validate_services",
            return_value=["Error 1", "Error 2"],
        ):
            result = setup._validate_templates()

        assert result is False

    def test_validate_templates_exception(self):
        """Test template validation with exception."""
        setup = MediaServerSetup()

        with patch.object(
            setup.template_loader,
            "validate_services",
            side_effect=Exception("Template error"),
        ):
            result = setup._validate_templates()

        assert result is False

    def test_collect_user_configuration(self, mock_os_operations):
        """Test user configuration collection."""
        setup = MediaServerSetup()

        with patch("src.setup_core.UserConfigCollector") as mock_collector:
            mock_collector.get_user_info.return_value = ("testuser", 1000, 1000)
            mock_collector.get_directory_paths.return_value = (
                "/opt/docker",
                "/srv/media",
            )

            with patch("src.setup_core.get_timezone", return_value="UTC"):
                setup._collect_user_configuration()

        assert setup.username == "testuser"
        assert setup.uid == 1000
        assert setup.gid == 1000
        assert setup.docker_dir == Path("/opt/docker")
        assert setup.media_dir == Path("/srv/media")
        assert setup.output_dir == Path("/opt/docker/compose")
        assert setup.timezone == "UTC"

    def test_select_services(self, sample_services):
        """Test service selection."""
        setup = MediaServerSetup()

        with patch.object(
            setup.template_loader, "get_services", return_value=sample_services
        ):
            with patch.object(setup.template_loader, "get_categories", return_value={}):
                with patch.object(
                    setup.template_loader, "get_services_by_category", return_value={}
                ):
                    with patch("src.setup_core.ServiceSelector") as mock_selector:
                        mock_selector_instance = Mock()
                        mock_selector_instance.select_services.return_value = [
                            "jellyfin"
                        ]
                        mock_selector.return_value = mock_selector_instance

                        with patch(
                            "src.setup_core.UserConfigCollector"
                        ) as mock_collector:
                            mock_collector.confirm_setup.return_value = True

                            # Set up required attributes
                            setup.username = "testuser"
                            setup.docker_dir = Path("/opt/docker")
                            setup.media_dir = Path("/srv/media")

                            setup._select_services()

        assert setup.selected_services == ["jellyfin"]

    def test_select_services_user_cancels(self, sample_services):
        """Test service selection when user cancels."""
        setup = MediaServerSetup()

        with patch.object(
            setup.template_loader, "get_services", return_value=sample_services
        ):
            with patch.object(setup.template_loader, "get_categories", return_value={}):
                with patch.object(
                    setup.template_loader, "get_services_by_category", return_value={}
                ):
                    with patch("src.setup_core.ServiceSelector") as mock_selector:
                        mock_selector_instance = Mock()
                        mock_selector_instance.select_services.return_value = [
                            "jellyfin"
                        ]
                        mock_selector.return_value = mock_selector_instance

                        with patch(
                            "src.setup_core.UserConfigCollector"
                        ) as mock_collector:
                            mock_collector.confirm_setup.return_value = False

                            # Set up required attributes
                            setup.username = "testuser"
                            setup.docker_dir = Path("/opt/docker")
                            setup.media_dir = Path("/srv/media")

                            with pytest.raises(SystemExit):
                                setup._select_services()

    def test_configure_vpn_no_qbittorrent(self):
        """Test VPN configuration when qBittorrent is not selected."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin"]

        setup._configure_vpn()

        # Should not configure VPN without qBittorrent
        assert not setup.gluetun_configurator.enabled

    def test_configure_vpn_with_qbittorrent_enabled(self):
        """Test VPN configuration with qBittorrent selected and VPN enabled."""
        setup = MediaServerSetup()
        setup.selected_services = ["qbittorrent"]

        with patch.object(setup.gluetun_configurator, "configure", return_value=True):
            setup._configure_vpn()

        assert "gluetun" in setup.selected_services

    def test_configure_vpn_with_qbittorrent_disabled(self):
        """Test VPN configuration with qBittorrent selected but VPN disabled."""
        setup = MediaServerSetup()
        setup.selected_services = ["qbittorrent"]

        with patch.object(setup.gluetun_configurator, "configure", return_value=False):
            setup._configure_vpn()

        assert "gluetun" not in setup.selected_services

    def test_setup_directories_and_files_success(self, temp_dir):
        """Test successful directories and files setup."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin"]
        setup.docker_dir = temp_dir / "docker"
        setup.media_dir = temp_dir / "media"
        setup.output_dir = temp_dir / "output"
        setup.uid = 1000
        setup.gid = 1000
        setup.timezone = "UTC"

        # Mock successful operations
        with patch.object(
            setup.directory_manager,
            "create_directory_structure",
            return_value=(True, []),
        ):
            with patch.object(
                setup.directory_manager,
                "create_service_directories",
                return_value=(True, []),
            ):
                with patch.object(
                    setup.file_generator,
                    "generate_all_files",
                    return_value={
                        "docker-compose.yml": True,
                        ".env": True,
                        "SETUP_GUIDE.md": True,
                    },
                ):
                    with patch.object(
                        setup.file_generator,
                        "validate_generated_files",
                        return_value=[],
                    ):
                        with patch.object(
                            setup.directory_manager, "fix_permissions", return_value=[]
                        ):
                            result = setup._setup_directories_and_files()

        assert result is True

    def test_setup_directories_and_files_directory_failure(self, temp_dir):
        """Test directories and files setup with directory creation failure."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin"]

        # Mock directory creation failure
        with patch.object(
            setup.directory_manager,
            "create_directory_structure",
            return_value=(False, ["Failed to create directory"]),
        ):
            result = setup._setup_directories_and_files()

        assert result is False

    def test_setup_directories_and_files_file_generation_failure(self, temp_dir):
        """Test directories and files setup with file generation failure."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin"]

        # Mock successful directory creation but failed file generation
        with patch.object(
            setup.directory_manager,
            "create_directory_structure",
            return_value=(True, []),
        ):
            with patch.object(
                setup.directory_manager,
                "create_service_directories",
                return_value=(True, []),
            ):
                with patch.object(
                    setup.file_generator,
                    "generate_all_files",
                    return_value={
                        "docker-compose.yml": False,
                        ".env": True,
                        "SETUP_GUIDE.md": True,
                    },
                ):
                    result = setup._setup_directories_and_files()

        assert result is False

    def test_start_containers_success(self, temp_dir, mock_subprocess):
        """Test successful container startup."""
        setup = MediaServerSetup()
        setup.output_dir = temp_dir
        setup.gluetun_configurator.enabled = False
        setup.selected_services = ["jellyfin"]
        setup.host_ip = "localhost"

        # Mock successful subprocess run
        mock_subprocess.return_value.returncode = 0

        with patch.object(
            setup.template_loader,
            "get_services",
            return_value={"jellyfin": {"name": "Jellyfin", "port": 8096}},
        ):
            setup._start_containers()

        # Should call docker compose up
        mock_subprocess.assert_called()

    def test_start_containers_failure(self, temp_dir, mock_subprocess):
        """Test container startup failure."""
        setup = MediaServerSetup()
        setup.output_dir = temp_dir
        setup.gluetun_configurator.enabled = False

        # Mock failed subprocess run
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "Container startup failed"

        setup._start_containers()

        # Should handle the error gracefully
        mock_subprocess.assert_called()

    def test_test_gluetun_connection_success(self):
        """Test successful Gluetun connection test."""
        setup = MediaServerSetup()

        with patch("src.setup_core.ContainerTester") as mock_tester:
            mock_tester.test_gluetun_connection.return_value = (True, "VPN working!")

            setup._test_gluetun_connection()

        mock_tester.test_gluetun_connection.assert_called_once()

    def test_test_gluetun_connection_failure(self):
        """Test failed Gluetun connection test."""
        setup = MediaServerSetup()

        with patch("src.setup_core.ContainerTester") as mock_tester:
            mock_tester.test_gluetun_connection.return_value = (False, "VPN failed!")

            setup._test_gluetun_connection()

        mock_tester.test_gluetun_connection.assert_called_once()

    def test_show_access_information(self, capsys):
        """Test access information display."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin", "qbittorrent"]
        setup.host_ip = "192.168.1.100"
        setup.gluetun_configurator.enabled = False
        setup.gluetun_configurator.route_qbittorrent = False

        services = {
            "jellyfin": {"name": "Jellyfin", "port": 8096},
            "qbittorrent": {"name": "qBittorrent", "port": 8080},
        }

        with patch.object(setup.template_loader, "get_services", return_value=services):
            setup._show_access_information()

        captured = capsys.readouterr()
        assert "SERVICE ACCESS INFORMATION" in captured.out
        assert "Jellyfin" in captured.out
        assert "qBittorrent" in captured.out
        assert "192.168.1.100:8096" in captured.out
        assert "192.168.1.100:8080" in captured.out

    def test_show_access_information_with_vpn(self, capsys):
        """Test access information display with VPN routing."""
        setup = MediaServerSetup()
        setup.selected_services = ["qbittorrent"]
        setup.host_ip = "192.168.1.100"
        setup.gluetun_configurator.enabled = True
        setup.gluetun_configurator.route_qbittorrent = True

        services = {"qbittorrent": {"name": "qBittorrent", "port": 8080}}

        with patch.object(setup.template_loader, "get_services", return_value=services):
            setup._show_access_information()

        captured = capsys.readouterr()
        assert "via Gluetun" in captured.out

    def test_interactive_walkthrough(self, mock_os_operations):
        """Test interactive walkthrough."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin", "qbittorrent"]
        setup.host_ip = "localhost"
        setup.gluetun_configurator.enabled = False

        services = {
            "jellyfin": {
                "name": "Jellyfin",
                "port": 8096,
                "setup_steps": ["Open web interface", "Complete setup"],
            },
            "qbittorrent": {
                "name": "qBittorrent",
                "port": 8080,
                "setup_steps": ["Get password from logs"],
            },
        }

        with patch.object(setup.template_loader, "get_services", return_value=services):
            with patch("src.setup_core.wait_for_done") as mock_wait:
                setup._interactive_walkthrough()

        # Should call wait_for_done for each service
        assert mock_wait.call_count == 2

    def test_should_show_debug_info_enabled(self):
        """Test debug info detection when enabled."""
        setup = MediaServerSetup()

        with patch.dict(os.environ, {"DEBUG": "1"}):
            result = setup._should_show_debug_info()

        assert result is True

    def test_should_show_debug_info_disabled(self):
        """Test debug info detection when disabled."""
        setup = MediaServerSetup()

        with patch.dict(os.environ, {}, clear=True):
            result = setup._should_show_debug_info()

        assert result is False

    def test_run_success_flow(self, mock_os_operations):
        """Test successful complete run flow."""
        setup = MediaServerSetup()

        # Mock all steps to succeed
        with patch.object(setup, "_print_welcome"):
            with patch.object(setup, "_run_setup_steps"):
                with patch.object(setup, "_print_completion_message"):
                    setup.run()

        # Should complete without exceptions

    def test_run_keyboard_interrupt(self):
        """Test run with keyboard interrupt."""
        setup = MediaServerSetup()

        with patch.object(setup, "_print_welcome", side_effect=KeyboardInterrupt()):
            with pytest.raises(SystemExit) as exc_info:
                setup.run()

        assert exc_info.value.code == 1

    def test_run_general_exception(self):
        """Test run with general exception."""
        setup = MediaServerSetup()

        with patch.object(setup, "_print_welcome", side_effect=Exception("Test error")):
            with patch.object(setup, "_should_show_debug_info", return_value=False):
                with pytest.raises(SystemExit) as exc_info:
                    setup.run()

        assert exc_info.value.code == 1

    def test_run_general_exception_with_debug(self):
        """Test run with general exception and debug enabled."""
        setup = MediaServerSetup()

        with patch.object(setup, "_print_welcome", side_effect=Exception("Test error")):
            with patch.object(setup, "_should_show_debug_info", return_value=True):
                with patch("traceback.print_exc") as mock_traceback:
                    with pytest.raises(SystemExit) as exc_info:
                        setup.run()

        assert exc_info.value.code == 1
        mock_traceback.assert_called_once()

    def test_handle_final_setup_start_containers(self, temp_dir):
        """Test final setup with container start."""
        setup = MediaServerSetup()
        setup.output_dir = temp_dir

        with patch("src.setup_core.prompt_yes_no") as mock_prompt:
            mock_prompt.side_effect = [True, False]  # Start containers, no walkthrough

            with patch.object(setup, "_start_containers") as mock_start:
                setup._handle_final_setup()

        mock_start.assert_called_once()

    def test_handle_final_setup_walkthrough(self, temp_dir):
        """Test final setup with walkthrough."""
        setup = MediaServerSetup()
        setup.output_dir = temp_dir

        with patch("src.setup_core.prompt_yes_no") as mock_prompt:
            mock_prompt.side_effect = [
                False,
                True,
            ]  # Don't start containers, do walkthrough

            with patch.object(setup, "_interactive_walkthrough") as mock_walkthrough:
                setup._handle_final_setup()

        mock_walkthrough.assert_called_once()

    def test_print_completion_message(self, capsys):
        """Test completion message printing."""
        setup = MediaServerSetup()
        setup.selected_services = ["jellyfin", "qbittorrent"]
        setup.docker_dir = Path("/opt/docker")
        setup.media_dir = Path("/srv/media")
        setup.output_dir = Path("/opt/docker/compose")
        setup.gluetun_configurator.enabled = True
        setup.gluetun_configurator.route_qbittorrent = True

        setup._print_completion_message()

        captured = capsys.readouterr()
        assert "SETUP COMPLETE!" in captured.out
        assert "Services: 2 selected" in captured.out
        assert "VPN Configuration:" in captured.out
        assert "qBittorrent traffic is routed through VPN" in captured.out
        assert "Next Steps:" in captured.out
        assert "Useful Commands:" in captured.out

    def test_run_setup_steps_complete_flow(self, mock_os_operations):
        """Test complete setup steps flow."""
        setup = MediaServerSetup()
        setup.progress = Mock()

        # Mock all step methods to succeed
        with patch.object(setup, "_validate_system", return_value=True):
            with patch.object(setup, "_validate_templates", return_value=True):
                with patch.object(setup, "_collect_user_configuration"):
                    with patch.object(setup, "_select_services"):
                        with patch.object(setup, "_configure_vpn"):
                            with patch.object(
                                setup, "_setup_directories_and_files", return_value=True
                            ):
                                with patch.object(setup, "_handle_final_setup"):
                                    setup._run_setup_steps()

        # Progress should be called for each step
        assert setup.progress.start_step.call_count == 7
        assert setup.progress.step_success.call_count == 7

    def test_run_setup_steps_system_validation_failure(self):
        """Test setup steps with system validation failure."""
        setup = MediaServerSetup()
        setup.progress = Mock()

        with patch.object(setup, "_validate_system", return_value=False):
            with pytest.raises(SystemExit):
                setup._run_setup_steps()

    def test_run_setup_steps_template_validation_failure(self):
        """Test setup steps with template validation failure."""
        setup = MediaServerSetup()
        setup.progress = Mock()

        with patch.object(setup, "_validate_system", return_value=True):
            with patch.object(setup, "_validate_templates", return_value=False):
                with pytest.raises(SystemExit):
                    setup._run_setup_steps()

    def test_run_setup_steps_directory_setup_failure(self, mock_os_operations):
        """Test setup steps with directory/file setup failure."""
        setup = MediaServerSetup()
        setup.progress = Mock()

        with patch.object(setup, "_validate_system", return_value=True):
            with patch.object(setup, "_validate_templates", return_value=True):
                with patch.object(setup, "_collect_user_configuration"):
                    with patch.object(setup, "_select_services"):
                        with patch.object(setup, "_configure_vpn"):
                            with patch.object(
                                setup,
                                "_setup_directories_and_files",
                                return_value=False,
                            ):
                                with pytest.raises(SystemExit):
                                    setup._run_setup_steps()
