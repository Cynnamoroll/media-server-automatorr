"""
Tests for system_validators module.
"""

import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.system_validators import ContainerTester, ServiceTester, SystemValidator


class TestSystemValidator:
    """Test SystemValidator class."""

    def test_init(self):
        """Test SystemValidator initialization."""
        validator = SystemValidator()
        assert not validator.docker_available
        assert not validator.compose_available
        assert not validator.docker_permissions

    def test_check_docker_success(self, mock_docker_commands):
        """Test successful Docker check."""
        validator = SystemValidator()
        result = validator._check_docker()
        assert result is True
        assert validator.docker_available is False  # Not set in individual check

    def test_check_docker_failure(self, mock_subprocess):
        """Test Docker check failure."""
        mock_subprocess.side_effect = FileNotFoundError()
        validator = SystemValidator()
        result = validator._check_docker()
        assert result is False

    def test_check_docker_compose_success(self, mock_docker_commands):
        """Test successful Docker Compose check."""
        validator = SystemValidator()
        result = validator._check_docker_compose()
        assert result is True

    def test_check_docker_compose_failure(self, mock_subprocess):
        """Test Docker Compose check failure."""
        mock_subprocess.return_value.returncode = 1
        validator = SystemValidator()
        result = validator._check_docker_compose()
        assert result is False

    def test_check_docker_permissions_success(self, mock_docker_commands):
        """Test successful Docker permissions check."""
        validator = SystemValidator()
        result = validator._check_docker_permissions()
        assert result is True

    def test_check_docker_permissions_failure(self, mock_subprocess):
        """Test Docker permissions check failure."""
        mock_subprocess.return_value.returncode = 1
        validator = SystemValidator()
        result = validator._check_docker_permissions()
        assert result is False

    def test_validate_all_success(self, mock_docker_commands):
        """Test successful validation of all prerequisites."""
        validator = SystemValidator()
        result = validator.validate_all()
        assert result is True
        assert validator.docker_available is True
        assert validator.compose_available is True
        assert validator.docker_permissions is True

    def test_validate_all_failure(self, mock_subprocess):
        """Test validation failure."""
        mock_subprocess.return_value.returncode = 1
        validator = SystemValidator()
        result = validator.validate_all()
        assert result is False


class TestContainerTester:
    """Test ContainerTester class."""

    def test_is_container_running_true(self, mock_subprocess):
        """Test container running detection."""
        mock_subprocess.return_value = MagicMock(stdout="gluetun", returncode=0)
        result = ContainerTester._is_container_running("gluetun")
        assert result is True

    def test_is_container_running_false(self, mock_subprocess):
        """Test container not running detection."""
        mock_subprocess.return_value = MagicMock(stdout="", returncode=0)
        result = ContainerTester._is_container_running("gluetun")
        assert result is False

    def test_is_valid_ip_valid(self):
        """Test valid IP validation."""
        assert ContainerTester._is_valid_ip("192.168.1.1") is True
        assert ContainerTester._is_valid_ip("10.0.0.1") is True
        assert ContainerTester._is_valid_ip("172.16.0.1") is True

    def test_is_valid_ip_invalid(self):
        """Test invalid IP validation."""
        assert ContainerTester._is_valid_ip("256.1.1.1") is False
        assert ContainerTester._is_valid_ip("192.168.1") is False
        assert ContainerTester._is_valid_ip("not.an.ip") is False
        assert ContainerTester._is_valid_ip("") is False

    def test_wait_for_container_ready_success(self, mock_subprocess):
        """Test successful container ready wait."""
        mock_subprocess.return_value = MagicMock(
            returncode=0, stdout="INFO: VPN is up\nSUCCESS: Connected"
        )

        result = ContainerTester._wait_for_container_ready("gluetun", 5)
        assert result is True

    def test_wait_for_container_ready_error(self, mock_subprocess):
        """Test container ready wait with error."""
        mock_subprocess.return_value = MagicMock(
            returncode=0, stdout="ERROR: Connection failed\nFATAL: Cannot connect"
        )

        result = ContainerTester._wait_for_container_ready("gluetun", 5)
        assert result is False

    def test_wait_for_container_ready_timeout(self, mock_subprocess):
        """Test container ready wait timeout."""
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="Starting...")

        # Mock time to speed up test
        with patch("time.time", side_effect=[0, 10]):  # Simulate timeout
            result = ContainerTester._wait_for_container_ready("gluetun", 5)
            assert result is False

    def test_test_gluetun_connection_not_running(self, mock_subprocess):
        """Test Gluetun connection when container not running."""
        mock_subprocess.return_value = MagicMock(stdout="", returncode=0)

        success, message = ContainerTester.test_gluetun_connection(timeout=1)
        assert success is False
        assert "not running" in message

    def test_test_gluetun_connection_success(self, mock_container_operations):
        """Test successful Gluetun connection test."""
        # Mock container as running
        with patch.object(ContainerTester, "_is_container_running", return_value=True):
            with patch.object(
                ContainerTester, "_wait_for_container_ready", return_value=True
            ):
                success, message = ContainerTester.test_gluetun_connection(timeout=1)
                assert success is True
                assert "VPN connection successful" in message
                assert "198.51.100.1" in message

    def test_test_gluetun_connection_not_ready(self, mock_subprocess):
        """Test Gluetun connection when container not ready."""
        mock_subprocess.return_value = MagicMock(stdout="gluetun", returncode=0)

        with patch.object(
            ContainerTester, "_wait_for_container_ready", return_value=False
        ):
            success, message = ContainerTester.test_gluetun_connection(timeout=1)
            assert success is False
            assert "not become ready" in message

    def test_test_gluetun_connection_vpn_failure(self, mock_subprocess):
        """Test Gluetun connection with VPN failure."""
        # Mock container as running and ready
        mock_subprocess.return_value = MagicMock(stdout="gluetun", returncode=0)

        with patch.object(ContainerTester, "_is_container_running", return_value=True):
            with patch.object(
                ContainerTester, "_wait_for_container_ready", return_value=True
            ):
                # Mock VPN test failure
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        returncode=1, stderr="Connection failed"
                    )

                    success, message = ContainerTester.test_gluetun_connection(
                        timeout=1
                    )
                    assert success is False
                    assert "VPN test failed" in message

    def test_get_container_logs_success(self, mock_subprocess):
        """Test successful container log retrieval."""
        mock_subprocess.return_value = MagicMock(
            returncode=0, stdout="Log line 1\nLog line 2"
        )

        logs = ContainerTester.get_container_logs("test_container", 10)
        assert "Log line 1" in logs
        assert "Log line 2" in logs

    def test_get_container_logs_failure(self, mock_subprocess):
        """Test container log retrieval failure."""
        mock_subprocess.return_value = MagicMock(
            returncode=1, stderr="Container not found"
        )

        logs = ContainerTester.get_container_logs("test_container", 10)
        assert "Error getting logs" in logs

    def test_show_container_status(self, mock_subprocess, capsys):
        """Test container status display."""

        # Mock some containers as running, others not
        def mock_is_running(container):
            return container in ["gluetun", "qbittorrent"]

        with patch.object(
            ContainerTester, "_is_container_running", side_effect=mock_is_running
        ):
            ContainerTester.show_container_status(["gluetun", "qbittorrent", "sonarr"])

        captured = capsys.readouterr()
        assert "Container Status:" in captured.out
        assert "gluetun: Running" in captured.out
        assert "qbittorrent: Running" in captured.out
        assert "sonarr: Not running" in captured.out


class TestServiceTester:
    """Test ServiceTester class."""

    def test_test_service_connectivity_success(self, mock_network_operations):
        """Test successful service connectivity."""
        success, message = ServiceTester.test_service_connectivity(
            "test_service", "localhost", 8080
        )
        assert success is True
        assert "accessible" in message

    def test_test_service_connectivity_failure(self):
        """Test failed service connectivity."""
        with patch("socket.socket") as mock_socket:
            mock_socket_instance = Mock()
            mock_socket_instance.connect_ex.return_value = 1  # Connection failed
            mock_socket.return_value = mock_socket_instance

            success, message = ServiceTester.test_service_connectivity(
                "test_service", "localhost", 8080
            )
            assert success is False
            assert "not accessible" in message

    def test_test_qbittorrent_through_gluetun_success(self, mock_subprocess):
        """Test successful qBittorrent connectivity through Gluetun."""
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="200")

        success, message = ServiceTester.test_qbittorrent_through_gluetun()
        assert success is True
        assert "accessible through Gluetun" in message

    def test_test_qbittorrent_through_gluetun_failure(self, mock_subprocess):
        """Test failed qBittorrent connectivity through Gluetun."""
        mock_subprocess.return_value = MagicMock(
            returncode=1, stderr="Connection failed"
        )

        success, message = ServiceTester.test_qbittorrent_through_gluetun()
        assert success is False
        assert "Could not connect" in message

    def test_test_qbittorrent_through_gluetun_wrong_status(self, mock_subprocess):
        """Test qBittorrent connectivity with wrong status code."""
        mock_subprocess.return_value = MagicMock(returncode=0, stdout="500")

        success, message = ServiceTester.test_qbittorrent_through_gluetun()
        assert success is False
        assert "status code: 500" in message
