"""
Tests for health_checker module.

Tests comprehensive service health checking including:
- Service connectivity and web UI responsiveness
- Docker environment validation
- File permissions and volume mount checking
- VPN health validation
- Security checks
"""

import json
import socket
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from src.health_checker import ServiceHealthChecker


class TestServiceHealthChecker:
    """Test ServiceHealthChecker class."""

    @pytest.fixture
    def health_checker(self, temp_dir):
        """Create a ServiceHealthChecker instance for testing."""
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"
        docker_dir.mkdir()
        media_dir.mkdir()

        checker = ServiceHealthChecker(docker_dir, media_dir)
        return checker

    @pytest.fixture
    def mock_services_config(self):
        """Mock services configuration."""
        return {
            "jellyfin": {
                "name": "Jellyfin",
                "port": 8096,
                "volumes": {"/config": "config"},
                "media_volumes": {"/media": "."},
                "env": ["PUID", "PGID", "TZ"],
                "setup_url": "http://{host_ip}:8096",
            },
            "qbittorrent": {
                "name": "qBittorrent",
                "port": 8080,
                "extra_ports": [6881],
                "volumes": {"/config": "config"},
                "media_volumes": {"/downloads": "downloads"},
                "env": ["PUID", "PGID", "TZ"],
                "setup_url": "http://{host_ip}:8080",
            },
            "gluetun": {
                "name": "Gluetun",
                "port": 8888,
                "extra_ports": [8388],
                "volumes": {"/gluetun": "config"},
                "env": ["TZ"],
                "setup_url": None,
            },
        }

    def test_init(self, temp_dir):
        """Test ServiceHealthChecker initialization."""
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"

        checker = ServiceHealthChecker(docker_dir, media_dir)

        assert checker.docker_dir == docker_dir
        assert checker.media_dir == media_dir
        assert checker.services_config == {}
        assert checker.health_results == {}

    def test_load_service_config(self, health_checker, mock_services_config):
        """Test loading service configuration."""
        health_checker.load_service_config(mock_services_config)

        assert health_checker.services_config == mock_services_config
        assert "jellyfin" in health_checker.services_config
        assert "qbittorrent" in health_checker.services_config

    @patch("src.health_checker.run_command")
    def test_check_docker_health_success(self, mock_run_command, health_checker):
        """Test successful Docker health check."""
        # Mock successful Docker commands
        mock_run_command.side_effect = [
            MagicMock(returncode=0, stdout="Docker info output"),  # docker info
            MagicMock(
                returncode=0, stdout="Docker Compose version"
            ),  # docker compose version
            MagicMock(
                returncode=0, stdout="TYPE     SIZE\nImages   1.2GB"
            ),  # docker system df
            MagicMock(
                returncode=0,
                stdout="NETWORK ID   NAME\n123abc   bridge\n456def   media-network",
            ),  # docker network ls
        ]

        health = health_checker._check_docker_health()

        assert health["daemon_running"] is True
        assert health["compose_available"] is True
        assert "available_networks" in health["network_status"]
        assert health["network_status"]["media_network_exists"] is True
        assert len(health["issues"]) == 0

    @patch("src.health_checker.run_command")
    def test_check_docker_health_failure(self, mock_run_command, health_checker):
        """Test Docker health check with daemon failure."""
        mock_run_command.return_value = MagicMock(returncode=1)

        health = health_checker._check_docker_health()

        assert health["daemon_running"] is False
        assert "Docker daemon not responding" in health["issues"]

    @patch.object(ServiceHealthChecker, "_is_container_running")
    @patch.object(ServiceHealthChecker, "_check_container_health_status")
    @patch.object(ServiceHealthChecker, "_check_service_ports")
    @patch.object(ServiceHealthChecker, "_check_web_ui_health")
    @patch.object(ServiceHealthChecker, "_analyze_container_logs")
    @patch.object(ServiceHealthChecker, "_get_container_resource_usage")
    def test_check_service_health_success(
        self,
        mock_resource_usage,
        mock_logs,
        mock_web_ui,
        mock_ports,
        mock_health_status,
        mock_running,
        health_checker,
        mock_services_config,
    ):
        """Test successful service health check."""
        health_checker.load_service_config(mock_services_config)

        # Mock all checks as successful
        mock_running.return_value = True
        mock_health_status.return_value = True
        mock_ports.return_value = {"main_8096": True}
        mock_web_ui.return_value = True
        mock_logs.return_value = {"healthy": True, "errors": [], "warnings": []}
        mock_resource_usage.return_value = {"cpu_percent": 5.2, "memory_usage": 512}

        health = health_checker._check_service_health("jellyfin")

        assert health["container_running"] is True
        assert health["container_healthy"] is True
        assert health["ports_accessible"]["main_8096"] is True
        assert health["web_ui_responsive"] is True
        assert health["logs_healthy"] is True
        assert len(health["issues"]) == 0

    @patch.object(ServiceHealthChecker, "_is_container_running")
    def test_check_service_health_container_not_running(
        self, mock_running, health_checker, mock_services_config
    ):
        """Test service health check when container is not running."""
        health_checker.load_service_config(mock_services_config)
        mock_running.return_value = False

        health = health_checker._check_service_health("jellyfin")

        assert health["container_running"] is False
        assert "Container jellyfin is not running" in health["issues"]

    @patch("src.health_checker.run_command")
    def test_is_container_running_true(self, mock_run_command, health_checker):
        """Test container running detection when container is running."""
        mock_run_command.return_value = MagicMock(returncode=0, stdout="jellyfin")

        result = health_checker._is_container_running("jellyfin")
        assert result is True

    @patch("src.health_checker.run_command")
    def test_is_container_running_false(self, mock_run_command, health_checker):
        """Test container running detection when container is not running."""
        mock_run_command.return_value = MagicMock(returncode=0, stdout="")

        result = health_checker._is_container_running("jellyfin")
        assert result is False

    @patch("src.health_checker.run_command")
    def test_check_container_health_status_healthy(
        self, mock_run_command, health_checker
    ):
        """Test container health status check when healthy."""
        mock_run_command.return_value = MagicMock(returncode=0, stdout="healthy")

        result = health_checker._check_container_health_status("jellyfin")
        assert result is True

    @patch("src.health_checker.run_command")
    def test_check_container_health_status_no_healthcheck(
        self, mock_run_command, health_checker
    ):
        """Test container health status when no healthcheck is defined."""
        mock_run_command.return_value = MagicMock(returncode=0, stdout="")

        result = health_checker._check_container_health_status("jellyfin")
        assert result is True  # No healthcheck defined is considered OK

    def test_test_port_accessibility_success(self, health_checker):
        """Test successful port accessibility check."""
        with patch("socket.socket") as mock_socket:
            mock_socket_instance = Mock()
            mock_socket_instance.connect_ex.return_value = 0
            mock_socket.return_value = mock_socket_instance

            result = health_checker._test_port_accessibility("localhost", 8080)
            assert result is True

    def test_test_port_accessibility_failure(self, health_checker):
        """Test failed port accessibility check."""
        with patch("socket.socket") as mock_socket:
            mock_socket_instance = Mock()
            mock_socket_instance.connect_ex.return_value = 1  # Connection failed
            mock_socket.return_value = mock_socket_instance

            result = health_checker._test_port_accessibility("localhost", 8080)
            assert result is False

    def test_check_service_ports(self, health_checker, mock_services_config):
        """Test service ports checking."""
        health_checker.load_service_config(mock_services_config)

        with patch.object(health_checker, "_test_port_accessibility") as mock_test_port:
            mock_test_port.return_value = True

            result = health_checker._check_service_ports(
                "qbittorrent", mock_services_config["qbittorrent"]
            )

            assert "main_8080" in result
            assert "extra_6881" in result
            assert result["main_8080"] is True
            assert result["extra_6881"] is True

    @patch("src.health_checker.urlopen")
    def test_check_web_ui_health_success(
        self, mock_urlopen, health_checker, mock_services_config
    ):
        """Test successful web UI health check."""
        mock_response = Mock()
        mock_response.getcode.return_value = 200
        mock_urlopen.return_value = mock_response

        result = health_checker._check_web_ui_health(
            "jellyfin", mock_services_config["jellyfin"]
        )
        assert result is True

    @patch("src.health_checker.urlopen")
    def test_check_web_ui_health_auth_redirect(
        self, mock_urlopen, health_checker, mock_services_config
    ):
        """Test web UI health check with auth redirect."""
        mock_response = Mock()
        mock_response.getcode.return_value = 401  # Auth required
        mock_urlopen.return_value = mock_response

        result = health_checker._check_web_ui_health(
            "jellyfin", mock_services_config["jellyfin"]
        )
        assert result is True  # 401 is acceptable

    @patch("src.health_checker.urlopen")
    def test_check_web_ui_health_no_url(
        self, mock_urlopen, health_checker, mock_services_config
    ):
        """Test web UI health check when no setup URL is configured."""
        result = health_checker._check_web_ui_health(
            "gluetun", mock_services_config["gluetun"]
        )
        assert result is True  # No URL to check is OK

    @patch("src.health_checker.run_command")
    def test_analyze_container_logs_healthy(self, mock_run_command, health_checker):
        """Test container log analysis with healthy logs."""
        mock_run_command.return_value = MagicMock(
            returncode=0,
            stdout="INFO: Service started successfully\nDEBUG: Configuration loaded\nINFO: Ready to serve requests",
        )

        result = health_checker._analyze_container_logs("jellyfin")

        assert result["healthy"] is True
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) == 0

    @patch("src.health_checker.run_command")
    def test_analyze_container_logs_with_errors(self, mock_run_command, health_checker):
        """Test container log analysis with errors."""
        mock_run_command.return_value = MagicMock(
            returncode=0,
            stdout="INFO: Service starting\nERROR: Database connection failed\nFATAL: Cannot continue",
        )

        result = health_checker._analyze_container_logs("jellyfin")

        assert result["healthy"] is False
        assert len(result["errors"]) == 2
        assert "ERROR: Database connection failed" in result["errors"]
        assert "FATAL: Cannot continue" in result["errors"]

    @patch("src.health_checker.run_command")
    def test_analyze_container_logs_with_warnings(
        self, mock_run_command, health_checker
    ):
        """Test container log analysis with warnings."""
        mock_run_command.return_value = MagicMock(
            returncode=0,
            stdout="INFO: Service starting\nWARNING: Configuration file not found, using defaults\nINFO: Service ready",
        )

        result = health_checker._analyze_container_logs("jellyfin")

        assert result["healthy"] is True
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) == 1
        assert (
            "WARNING: Configuration file not found, using defaults"
            in result["warnings"]
        )

    @patch.object(ServiceHealthChecker, "_is_container_running")
    @patch("src.health_checker.run_command")
    def test_test_vpn_ip_change_success(
        self, mock_run_command, mock_running, health_checker
    ):
        """Test successful VPN IP change detection."""
        mock_running.return_value = True

        # Mock local IP and VPN IP commands
        mock_run_command.side_effect = [
            MagicMock(returncode=0, stdout="203.0.113.1"),  # Local IP
            MagicMock(returncode=0, stdout="198.51.100.1"),  # VPN IP
        ]

        result = health_checker._test_vpn_ip_change()

        assert result["vpn_connected"] is True
        assert result["ip_changed"] is True
        assert result["local_ip"] == "203.0.113.1"
        assert result["external_ip"] == "198.51.100.1"

    @patch.object(ServiceHealthChecker, "_is_container_running")
    @patch("src.health_checker.run_command")
    def test_test_vpn_ip_change_no_change(
        self, mock_run_command, mock_running, health_checker
    ):
        """Test VPN IP check when IP hasn't changed (VPN not working)."""
        mock_running.return_value = True

        # Mock same IP for both local and VPN
        mock_run_command.side_effect = [
            MagicMock(returncode=0, stdout="203.0.113.1"),  # Local IP
            MagicMock(returncode=0, stdout="203.0.113.1"),  # Same IP through VPN
        ]

        result = health_checker._test_vpn_ip_change()

        assert result["vpn_connected"] is True
        assert result["ip_changed"] is False
        assert result["local_ip"] == "203.0.113.1"
        assert result["external_ip"] == "203.0.113.1"

    @patch.object(ServiceHealthChecker, "_check_docker_health")
    @patch.object(ServiceHealthChecker, "_check_service_health")
    @patch.object(ServiceHealthChecker, "_check_network_connectivity")
    @patch.object(ServiceHealthChecker, "_check_file_permissions")
    @patch.object(ServiceHealthChecker, "_check_environment_variables")
    @patch.object(ServiceHealthChecker, "_check_vpn_health")
    def test_check_all_services_success(
        self,
        mock_vpn_health,
        mock_env_vars,
        mock_file_perms,
        mock_network,
        mock_service_health,
        mock_docker_health,
        health_checker,
        mock_services_config,
    ):
        """Test comprehensive health check with all services healthy."""
        health_checker.load_service_config(mock_services_config)

        # Mock all checks as successful
        mock_docker_health.return_value = {
            "daemon_running": True,
            "compose_available": True,
        }
        mock_service_health.return_value = {
            "container_running": True,
            "container_healthy": True,
            "issues": [],
            "warnings": [],
        }
        mock_network.return_value = {"issues": []}
        mock_file_perms.return_value = {"permission_issues": []}
        mock_env_vars.return_value = {"security_issues": []}
        mock_vpn_health.return_value = {"vpn_connected": True}

        selected_services = ["jellyfin", "qbittorrent", "gluetun"]
        results = health_checker.check_all_services(selected_services)

        assert results["overall_status"] == "healthy"
        assert "docker_health" in results
        assert "services" in results
        assert len(results["services"]) == 3
        assert "vpn_status" in results
        assert "timestamp" in results

    def test_determine_overall_status_healthy(self, health_checker):
        """Test overall status determination when all checks pass."""
        results = {
            "docker_health": {"daemon_running": True},
            "services": {
                "jellyfin": {"container_running": True, "issues": []},
                "qbittorrent": {"container_running": True, "issues": []},
            },
            "vpn_status": {"vpn_connected": True},
        }

        status = health_checker._determine_overall_status(results)
        assert status == "healthy"

    def test_determine_overall_status_critical(self, health_checker):
        """Test overall status determination with critical issues."""
        results = {
            "docker_health": {"daemon_running": False},
            "services": {
                "jellyfin": {
                    "container_running": False,
                    "issues": ["Container not running"],
                },
            },
            "vpn_status": {},
        }

        status = health_checker._determine_overall_status(results)
        assert status == "critical"

    def test_determine_overall_status_warning(self, health_checker):
        """Test overall status determination with warnings."""
        results = {
            "docker_health": {"daemon_running": True},
            "services": {
                "jellyfin": {
                    "container_running": True,
                    "issues": ["Warning 1", "Warning 2"],
                },
                "qbittorrent": {
                    "container_running": True,
                    "issues": ["Warning 3", "Warning 4"],
                },
            },
            "vpn_status": {"vpn_connected": True},
        }

        status = health_checker._determine_overall_status(results)
        assert status == "warning"

    def test_export_health_report_success(self, health_checker, temp_dir):
        """Test successful health report export."""
        health_checker.health_results = {
            "overall_status": "healthy",
            "services": {"jellyfin": {"container_running": True}},
            "timestamp": time.time(),
        }

        output_file = temp_dir / "health_report.json"
        health_checker.export_health_report(output_file)

        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        assert data["overall_status"] == "healthy"
        assert "services" in data
        assert "timestamp" in data

    def test_export_health_report_no_results(self, health_checker, temp_dir, capsys):
        """Test health report export when no results are available."""
        output_file = temp_dir / "health_report.json"
        health_checker.export_health_report(output_file)

        assert not output_file.exists()
        captured = capsys.readouterr()
        assert "No health check results to export" in captured.out

    @patch("builtins.open", side_effect=IOError("Permission denied"))
    def test_export_health_report_failure(
        self, mock_open, health_checker, temp_dir, capsys
    ):
        """Test health report export failure."""
        health_checker.health_results = {"test": "data"}

        output_file = temp_dir / "health_report.json"
        health_checker.export_health_report(output_file)

        captured = capsys.readouterr()
        assert "Failed to export health report" in captured.out


class TestHealthCheckerIntegration:
    """Integration tests for ServiceHealthChecker."""

    def test_full_health_check_workflow(self, temp_dir):
        """Test complete health check workflow."""
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"
        docker_dir.mkdir()
        media_dir.mkdir()

        # Create service directories
        (docker_dir / "jellyfin" / "config").mkdir(parents=True)
        (media_dir / "movies").mkdir(parents=True)

        checker = ServiceHealthChecker(docker_dir, media_dir)

        services_config = {
            "jellyfin": {
                "name": "Jellyfin",
                "port": 8096,
                "volumes": {"/config": "config"},
                "media_volumes": {"/media": "movies"},
                "env": ["PUID", "PGID", "TZ"],
                "setup_url": "http://{host_ip}:8096",
            }
        }

        checker.load_service_config(services_config)

        # Mock all external dependencies
        with patch.object(checker, "_is_container_running", return_value=False):
            with patch.object(checker, "_check_docker_health") as mock_docker:
                mock_docker.return_value = {
                    "daemon_running": True,
                    "compose_available": True,
                    "issues": [],
                }

                results = checker.check_all_services(["jellyfin"])

                assert "overall_status" in results
                assert "services" in results
                assert "jellyfin" in results["services"]
                assert results["services"]["jellyfin"]["container_running"] is False

    def test_health_checker_with_vpn_service(self, temp_dir):
        """Test health checker with VPN service included."""
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"
        docker_dir.mkdir()
        media_dir.mkdir()

        checker = ServiceHealthChecker(docker_dir, media_dir)

        services_config = {
            "gluetun": {
                "name": "Gluetun",
                "port": 8888,
                "volumes": {"/gluetun": "config"},
                "env": ["TZ"],
                "setup_url": None,
            }
        }

        checker.load_service_config(services_config)

        with patch.object(checker, "_check_docker_health") as mock_docker:
            with patch.object(checker, "_is_container_running", return_value=True):
                with patch.object(checker, "_check_vpn_health") as mock_vpn:
                    mock_docker.return_value = {"daemon_running": True, "issues": []}
                    mock_vpn.return_value = {"vpn_connected": True, "issues": []}

                    results = checker.check_all_services(["gluetun"])

                    assert "vpn_status" in results
                    assert results["vpn_status"]["vpn_connected"] is True


@pytest.mark.integration
class TestHealthCheckerLiveIntegration:
    """Live integration tests that require actual Docker environment."""

    @pytest.mark.skipif(True, reason="Integration test - requires Docker")
    def test_real_docker_health_check(self, temp_dir):
        """Test health checker against real Docker environment."""
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"
        docker_dir.mkdir()
        media_dir.mkdir()

        checker = ServiceHealthChecker(docker_dir, media_dir)

        # This test will only pass if Docker is actually available
        docker_health = checker._check_docker_health()

        # If Docker is available, these should be true
        if docker_health["daemon_running"]:
            assert docker_health["compose_available"] is True
            assert len(docker_health["issues"]) == 0

    @pytest.mark.skipif(True, reason="Integration test - requires network access")
    def test_real_port_accessibility(self, temp_dir):
        """Test port accessibility against real network stack."""
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"
        docker_dir.mkdir()
        media_dir.mkdir()

        checker = ServiceHealthChecker(docker_dir, media_dir)

        # Test against a port that should be closed
        result = checker._test_port_accessibility("localhost", 65432, timeout=1)
        assert result is False

        # Test against a well-known service port (if available)
        # This might pass on some systems where SSH is running
        ssh_result = checker._test_port_accessibility("localhost", 22, timeout=1)
        # We don't assert this as SSH may or may not be running
