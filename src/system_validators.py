"""
System validation and testing utilities for media-server-automatorr.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .utils import (Colors, print_error, print_info, print_success,
                    print_warning, run_command)


class SystemValidator:
    """Handles system prerequisite validation."""

    def __init__(self):
        self.docker_available = False
        self.compose_available = False
        self.docker_permissions = False

    def validate_all(self) -> bool:
        """Run all system validations. Returns True if all checks pass."""
        print_info("Checking system prerequisites...")

        docker_ok = self._check_docker()
        compose_ok = self._check_docker_compose()
        permissions_ok = self._check_docker_permissions()

        self.docker_available = docker_ok
        self.compose_available = compose_ok
        self.docker_permissions = permissions_ok

        return all([docker_ok, compose_ok, permissions_ok])

    def _check_docker(self) -> bool:
        """Check if Docker is installed and accessible."""
        try:
            result = run_command(["docker", "--version"], check=False)
            if result.returncode != 0:
                print_error("Docker is not installed or not accessible")
                return False

            version_info = result.stdout.strip()
            print_success(f"Docker found: {version_info}")
            return True

        except FileNotFoundError:
            print_error("Docker is not installed")
            print_info("Install Docker from: https://docs.docker.com/engine/install/")
            return False

    def _check_docker_compose(self) -> bool:
        """Check if Docker Compose V2 is available."""
        try:
            result = run_command(["docker", "compose", "version"], check=False)
            if result.returncode != 0:
                print_error("Docker Compose V2 is not available")
                print_info("Ensure Docker Compose V2 is installed")
                return False

            version_info = result.stdout.strip()
            print_success(f"Docker Compose found: {version_info}")
            return True

        except FileNotFoundError:
            print_error("Docker Compose is not installed")
            return False

    def _check_docker_permissions(self) -> bool:
        """Check if current user can run Docker without sudo."""
        try:
            result = run_command(["docker", "ps"], check=False)
            if result.returncode != 0:
                print_warning("Cannot run Docker without sudo")
                print_info("You may need to:")
                print_info("  1. Run: sudo usermod -aG docker $USER")
                print_info("  2. Log out and back in")
                print_info("  3. Or run this script with sudo")
                return False

            print_success("Docker permissions OK")
            return True

        except Exception:
            print_warning("Could not verify Docker permissions")
            return False


class ContainerTester:
    """Handles testing of running containers."""

    @staticmethod
    def test_gluetun_connection(timeout: int = 30) -> Tuple[bool, str]:
        """
        Test Gluetun VPN connection with improved feedback.

        Args:
            timeout: Maximum time to wait for container to be ready

        Returns:
            Tuple of (success, message)
        """
        # First check if container is running
        if not ContainerTester._is_container_running("gluetun"):
            return False, "Gluetun container is not running"

        # Wait for container to be ready
        print_info("Waiting for Gluetun to establish VPN connection...")

        ready = ContainerTester._wait_for_container_ready("gluetun", timeout)
        if not ready:
            return False, f"Gluetun did not become ready within {timeout} seconds"

        # Test VPN connection by checking external IP
        try:
            print_info("Testing VPN connection...")

            # Get IP through Gluetun
            result = subprocess.run(
                ["docker", "exec", "gluetun", "wget", "-qO-", "ifconfig.me"],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Unknown error"
                return False, f"VPN test failed: {error_msg}"

            vpn_ip = result.stdout.strip()

            if not vpn_ip or vpn_ip == "":
                return False, "Could not retrieve VPN IP address"

            # Validate IP format
            if not ContainerTester._is_valid_ip(vpn_ip):
                return False, f"Invalid IP address returned: {vpn_ip}"

            # Get local IP for comparison (optional)
            try:
                local_result = subprocess.run(
                    ["curl", "-s", "ifconfig.me"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                local_ip = (
                    local_result.stdout.strip()
                    if local_result.returncode == 0
                    else "unknown"
                )
            except:
                local_ip = "unknown"

            success_msg = f"VPN connection successful!\n"
            success_msg += f"  VPN IP: {vpn_ip}"
            if local_ip != "unknown" and local_ip != vpn_ip:
                success_msg += f"\n  Local IP: {local_ip}"
                success_msg += f"\n  ✓ IP address is different (VPN is working)"
            elif local_ip == vpn_ip:
                success_msg += (
                    f"\n  ⚠ Warning: VPN IP matches local IP - VPN may not be working"
                )

            return True, success_msg

        except subprocess.TimeoutExpired:
            return False, "VPN test timed out - check Gluetun logs"
        except Exception as e:
            return False, f"VPN test error: {str(e)}"

    @staticmethod
    def _is_container_running(container_name: str) -> bool:
        """Check if a container is running."""
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"name={container_name}",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return container_name in result.stdout
        except:
            return False

    @staticmethod
    def _wait_for_container_ready(container_name: str, timeout: int) -> bool:
        """Wait for container to be ready by checking its logs for success indicators."""
        start_time = time.time()

        # Keywords that indicate Gluetun is ready
        ready_keywords = ["VPN is up", "Tunnel is up", "Connected", "ready", "SUCCESS"]

        error_keywords = [
            "ERROR",
            "FATAL",
            "authentication failed",
            "connection failed",
        ]

        while time.time() - start_time < timeout:
            try:
                # Check logs for ready/error indicators
                result = subprocess.run(
                    ["docker", "logs", "--tail", "50", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    logs = result.stdout.lower()

                    # Check for error conditions first
                    for error_keyword in error_keywords:
                        if error_keyword.lower() in logs:
                            print_warning(f"Detected error in {container_name} logs")
                            return False

                    # Check for ready conditions
                    for ready_keyword in ready_keywords:
                        if ready_keyword.lower() in logs:
                            return True

                time.sleep(2)

            except Exception:
                time.sleep(2)
                continue

        return False

    @staticmethod
    def _is_valid_ip(ip: str) -> bool:
        """Validate IP address format."""
        try:
            parts = ip.split(".")
            if len(parts) != 4:
                return False

            for part in parts:
                num = int(part)
                if not (0 <= num <= 255):
                    return False

            return True
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def get_container_logs(container_name: str, lines: int = 20) -> str:
        """Get recent logs from a container."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(lines), container_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error getting logs: {result.stderr}"

        except Exception as e:
            return f"Error getting logs: {str(e)}"

    @staticmethod
    def show_container_status(container_names: List[str]) -> None:
        """Display status of multiple containers."""
        print_info("Container Status:")

        for container in container_names:
            if ContainerTester._is_container_running(container):
                print_success(f"  {container}: Running")
            else:
                print_warning(f"  {container}: Not running")


class ServiceTester:
    """Handles testing of specific services and their connectivity."""

    @staticmethod
    def test_service_connectivity(
        service_name: str, host: str, port: int, timeout: int = 10
    ) -> Tuple[bool, str]:
        """Test if a service is accessible on the given host and port."""
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)

            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                return True, f"{service_name} is accessible on {host}:{port}"
            else:
                return False, f"{service_name} is not accessible on {host}:{port}"

        except Exception as e:
            return False, f"Error testing {service_name}: {str(e)}"

    @staticmethod
    def test_qbittorrent_through_gluetun() -> Tuple[bool, str]:
        """Test if qBittorrent is accessible through Gluetun."""
        # Test if we can reach qBittorrent through Gluetun's network
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "gluetun",
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "http://localhost:8080",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                status_code = result.stdout.strip()
                if status_code in ["200", "401", "302"]:  # Common success/auth codes
                    return True, "qBittorrent is accessible through Gluetun"
                else:
                    return False, f"qBittorrent returned status code: {status_code}"
            else:
                return False, "Could not connect to qBittorrent through Gluetun"

        except Exception as e:
            return False, f"Error testing qBittorrent connectivity: {str(e)}"
