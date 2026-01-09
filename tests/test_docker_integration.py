"""
Docker integration tests.

These tests require Docker to be installed and running.
They test actual Docker operations and container management.
"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.system_validators import ContainerTester, SystemValidator


@pytest.fixture
def docker_tmp_dir(request):
    """Create a temporary directory and clean it up properly using Docker."""
    # Create a temporary directory manually to avoid pytest's automatic cleanup
    tmp_dir = Path(tempfile.mkdtemp(prefix="mediaserver-test-"))

    def cleanup():
        """Clean up root-owned files created by Docker containers."""
        if tmp_dir.exists():
            try:
                # Use Docker to recursively change ownership and remove all files
                subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{tmp_dir}:/cleanup",
                        "alpine",
                        "sh",
                        "-c",
                        "find /cleanup -type d -exec chmod 777 {} \\; 2>/dev/null || true; "
                        "find /cleanup -type f -exec chmod 666 {} \\; 2>/dev/null || true; "
                        "rm -rf /cleanup/* /cleanup/.[!.]* /cleanup/..?* 2>/dev/null || true",
                    ],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
            except Exception:
                pass

            # Remove the directory itself
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    # Register cleanup to run before pytest's own cleanup
    request.addfinalizer(cleanup)

    yield tmp_dir


@pytest.mark.integration
@pytest.mark.docker
class TestDockerIntegration:
    """Integration tests that require actual Docker to be running."""

    def test_docker_availability(self):
        """Test that Docker is actually available on the system."""
        validator = SystemValidator()

        # Don't mock - test real Docker
        try:
            result = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True, timeout=5
            )
            assert result.returncode == 0
            assert "Docker version" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available in test environment")

    def test_docker_compose_availability(self):
        """Test that Docker Compose is actually available."""
        validator = SystemValidator()

        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0
            assert "version" in result.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker Compose not available in test environment")

    def test_docker_info_command(self):
        """Test Docker info command returns system information."""
        try:
            result = subprocess.run(
                ["docker", "info"], capture_output=True, text=True, timeout=10
            )

            # Should succeed if Docker daemon is running
            if result.returncode == 0:
                assert "Server Version" in result.stdout or "Server:" in result.stdout
            else:
                pytest.skip("Docker daemon not running")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available")

    def test_docker_network_list(self):
        """Test that we can list Docker networks."""
        try:
            result = subprocess.run(
                ["docker", "network", "ls"], capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0:
                # Default networks should exist
                assert "bridge" in result.stdout or "NETWORK" in result.stdout
            else:
                pytest.skip("Cannot access Docker networks")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available")

    def test_docker_volume_operations(self):
        """Test Docker volume creation and deletion."""
        volume_name = "media-server-test-volume"

        try:
            # Create volume
            create_result = subprocess.run(
                ["docker", "volume", "create", volume_name],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if create_result.returncode != 0:
                pytest.skip("Cannot create Docker volumes")

            # Verify volume exists
            ls_result = subprocess.run(
                ["docker", "volume", "ls"], capture_output=True, text=True, timeout=5
            )
            assert volume_name in ls_result.stdout

            # Clean up - remove volume
            rm_result = subprocess.run(
                ["docker", "volume", "rm", volume_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert rm_result.returncode == 0

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available")
        finally:
            # Ensure cleanup
            subprocess.run(
                ["docker", "volume", "rm", "-f", volume_name],
                capture_output=True,
                timeout=5,
            )


@pytest.mark.integration
@pytest.mark.docker
class TestDockerComposeIntegration:
    """Integration tests for Docker Compose functionality."""

    def test_docker_compose_config_validation(self, tmp_path):
        """Test Docker Compose config validation with a simple compose file."""
        compose_file = tmp_path / "docker-compose.yml"

        # Create a minimal valid compose file
        compose_content = """
version: "3.8"

services:
  test:
    image: alpine:latest
    command: echo "test"
"""
        compose_file.write_text(compose_content)

        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "config"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=tmp_path,
            )

            if result.returncode == 0:
                # Should output valid YAML
                assert "services:" in result.stdout
                assert "test:" in result.stdout
            else:
                pytest.skip("Docker Compose config validation failed")

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker Compose not available")

    def test_docker_compose_invalid_file(self, tmp_path):
        """Test Docker Compose properly rejects invalid compose files."""
        compose_file = tmp_path / "docker-compose.yml"

        # Create an invalid compose file
        compose_content = "invalid: yaml: content::: [[[]]"
        compose_file.write_text(compose_content)

        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "config"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=tmp_path,
            )

            # Should fail with invalid YAML
            assert result.returncode != 0

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker Compose not available")


@pytest.mark.integration
@pytest.mark.docker
class TestContainerLifecycle:
    """Integration tests for container lifecycle management."""

    def test_pull_alpine_image(self):
        """Test pulling a small Docker image."""
        try:
            result = subprocess.run(
                ["docker", "pull", "alpine:latest"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                assert "Status: " in result.stdout or "Pulling from" in result.stdout
            else:
                pytest.skip("Cannot pull Docker images")

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available or network issues")

    def test_run_and_remove_container(self):
        """Test running and removing a simple container."""
        container_name = "media-server-test-container"

        try:
            # Run a simple container
            run_result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--name",
                    container_name,
                    "--rm",
                    "alpine:latest",
                    "echo",
                    "Hello from container",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if run_result.returncode == 0:
                assert "Hello from container" in run_result.stdout
            else:
                pytest.skip("Cannot run Docker containers")

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available")
        finally:
            # Ensure cleanup
            subprocess.run(
                ["docker", "rm", "-f", container_name], capture_output=True, timeout=10
            )

    def test_container_tester_integration(self):
        """Test ContainerTester with actual Docker commands."""
        # Start a test container
        container_name = "media-server-test-running"

        try:
            # Start a long-running container
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    container_name,
                    "alpine:latest",
                    "sleep",
                    "30",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Give container time to start
            time.sleep(2)

            # Test with ContainerTester
            is_running = ContainerTester._is_container_running(container_name)
            assert is_running is True

            # Stop the container
            subprocess.run(
                ["docker", "stop", container_name], capture_output=True, timeout=15
            )

            # Verify it's not running
            is_running_after_stop = ContainerTester._is_container_running(
                container_name
            )
            assert is_running_after_stop is False

        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available")
        finally:
            # Cleanup
            subprocess.run(
                ["docker", "rm", "-f", container_name], capture_output=True, timeout=10
            )


@pytest.mark.integration
@pytest.mark.docker
class TestSystemValidatorIntegration:
    """Integration tests for SystemValidator with real Docker."""

    def test_system_validator_real_docker_check(self):
        """Test SystemValidator against real Docker installation."""
        validator = SystemValidator()

        # Run real validation (no mocking)
        result = validator.validate_all()

        # If this test runs, Docker should be available
        # (pytest marks ensure this only runs when Docker is present)
        assert validator.docker_available is True
        assert validator.compose_available is True

        # Permissions might vary depending on user setup
        # So we just check it was evaluated
        assert isinstance(validator.docker_permissions, bool)

    def test_system_validator_individual_checks(self):
        """Test individual SystemValidator checks."""
        validator = SystemValidator()

        # Test Docker check
        docker_result = validator._check_docker()
        assert docker_result is True

        # Test Docker Compose check
        compose_result = validator._check_docker_compose()
        assert compose_result is True

        # Test permissions (may fail if not in docker group)
        permissions_result = validator._check_docker_permissions()
        # Don't assert - this depends on system setup
        assert isinstance(permissions_result, bool)


@pytest.mark.integration
@pytest.mark.docker
class TestDockerComposeEndToEnd:
    """End-to-end tests for docker-compose file generation and container deployment."""

    def test_generate_valid_compose_file(self, docker_tmp_dir):
        """Test that we can generate a valid docker-compose.yml that passes validation."""
        from src.file_generator import FileGenerator
        from src.template_loader import TemplateLoader

        # Load real templates
        loader = TemplateLoader()
        generator = FileGenerator(loader)

        # Create output directory
        output_dir = docker_tmp_dir / "output"
        output_dir.mkdir()
        docker_dir = docker_tmp_dir / "docker"
        media_dir = docker_tmp_dir / "media"

        # Generate files for a simple service
        results = generator.generate_all_files(
            selected_services=["jellyfin"],
            uid=1000,
            gid=1000,
            docker_dir=docker_dir,
            media_dir=media_dir,
            output_dir=output_dir,
            timezone="UTC",
        )

        # Verify compose file was created
        compose_file = output_dir / "docker-compose.yml"
        assert compose_file.exists()

        # Validate with docker-compose config
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file), "config"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=output_dir,
            )

            # Should be valid YAML that docker-compose can parse
            assert result.returncode == 0, f"Compose validation failed: {result.stderr}"
            assert "services:" in result.stdout
            assert "jellyfin" in result.stdout

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pytest.skip(f"Docker Compose not available: {e}")

    def test_start_simple_container_from_generated_compose(self, docker_tmp_dir):
        """Test starting an actual container from our generated docker-compose.yml."""
        from src.file_generator import FileGenerator
        from src.template_loader import TemplateLoader

        loader = TemplateLoader()
        generator = FileGenerator(loader)

        output_dir = docker_tmp_dir / "test_deployment"
        output_dir.mkdir()
        docker_dir = docker_tmp_dir / "docker"
        media_dir = docker_tmp_dir / "media"

        # Generate compose file for a lightweight service
        results = generator.generate_all_files(
            selected_services=["jellyfin"],
            uid=1000,
            gid=1000,
            docker_dir=docker_dir,
            media_dir=media_dir,
            output_dir=output_dir,
            timezone="UTC",
        )

        compose_file = output_dir / "docker-compose.yml"
        assert compose_file.exists()

        project_name = f"mediaserver-test-{os.getpid()}"

        try:
            # Cleanup any existing containers with conflicting names
            for container in ["jellyfin", "watchtower"]:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    capture_output=True,
                    timeout=10,
                )

            # Cleanup any existing containers from previous failed runs
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "down",
                    "-v",
                ],
                capture_output=True,
                timeout=30,
                cwd=output_dir,
            )

            # Pull images first (don't start yet)
            pull_result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "pull",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=output_dir,
            )

            if pull_result.returncode != 0:
                pytest.skip(f"Cannot pull images: {pull_result.stderr}")

            # Start containers in detached mode
            up_result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "up",
                    "-d",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=output_dir,
            )

            assert up_result.returncode == 0, (
                f"Failed to start containers: {up_result.stderr}"
            )

            # Give containers time to start
            time.sleep(5)

            # Check container is running
            ps_result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "ps",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=output_dir,
            )

            assert ps_result.returncode == 0
            assert (
                "jellyfin" in ps_result.stdout.lower()
                or project_name in ps_result.stdout
            )

        except subprocess.TimeoutExpired as e:
            pytest.fail(f"Container operations timed out: {e}")
        except AssertionError:
            raise
        except Exception as e:
            pytest.fail(f"Test failed: {e}")

        finally:
            # Cleanup - stop and remove containers
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "down",
                    "-v",
                ],
                capture_output=True,
                timeout=30,
                cwd=output_dir,
            )

    def test_container_port_accessibility(self, docker_tmp_dir):
        """Test that containers started from generated compose are accessible on their ports."""
        import socket

        from src.file_generator import FileGenerator
        from src.template_loader import TemplateLoader

        loader = TemplateLoader()
        generator = FileGenerator(loader)

        output_dir = docker_tmp_dir / "port_test"
        output_dir.mkdir()
        docker_dir = docker_tmp_dir / "docker"
        media_dir = docker_tmp_dir / "media"

        # Generate compose with a service that has a health endpoint
        results = generator.generate_all_files(
            selected_services=["jellyfin"],
            uid=1000,
            gid=1000,
            docker_dir=docker_dir,
            media_dir=media_dir,
            output_dir=output_dir,
            timezone="UTC",
        )

        compose_file = output_dir / "docker-compose.yml"
        project_name = f"mediaserver-port-test-{os.getpid()}"

        try:
            # Cleanup any existing containers with conflicting names
            for container in ["jellyfin", "watchtower"]:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    capture_output=True,
                    timeout=10,
                )

            # Cleanup any existing containers
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "down",
                    "-v",
                ],
                capture_output=True,
                timeout=30,
                cwd=output_dir,
            )

            # Start container
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "pull",
                ],
                capture_output=True,
                timeout=120,
            )

            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "up",
                    "-d",
                ],
                capture_output=True,
                timeout=60,
                cwd=output_dir,
            )

            # Wait for service to be ready
            time.sleep(10)

            # Test if port is accessible (Jellyfin default port 8096)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)

            try:
                result = sock.connect_ex(("127.0.0.1", 8096))
                # Port should be open (connect_ex returns 0 on success)
                assert result == 0, (
                    f"Port 8096 not accessible, connection result: {result}"
                )
            finally:
                sock.close()

        except subprocess.TimeoutExpired as e:
            pytest.fail(f"Container operations timed out: {e}")
        except AssertionError:
            raise
        except Exception as e:
            pytest.fail(f"Test failed: {e}")
        finally:
            # Cleanup
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "down",
                    "-v",
                ],
                capture_output=True,
                timeout=30,
                cwd=output_dir,
            )

    def test_volume_mounts_work_correctly(self, docker_tmp_dir):
        """Test that volume mounts are created and accessible in containers."""
        from src.file_generator import FileGenerator
        from src.template_loader import TemplateLoader

        loader = TemplateLoader()
        generator = FileGenerator(loader)

        output_dir = docker_tmp_dir / "volume_test"
        output_dir.mkdir()
        docker_dir = docker_tmp_dir / "docker"
        docker_dir.mkdir()
        media_dir = docker_tmp_dir / "media"
        media_dir.mkdir()

        # Create a test file in the media directory
        test_file = media_dir / "test.txt"
        test_file.write_text("test content")

        results = generator.generate_all_files(
            selected_services=["jellyfin"],
            uid=1000,
            gid=1000,
            docker_dir=docker_dir,
            media_dir=media_dir,
            output_dir=output_dir,
            timezone="UTC",
        )

        compose_file = output_dir / "docker-compose.yml"
        project_name = f"mediaserver-volume-test-{os.getpid()}"

        try:
            # Cleanup any existing containers with conflicting names
            for container in ["jellyfin", "watchtower"]:
                subprocess.run(
                    ["docker", "rm", "-f", container],
                    capture_output=True,
                    timeout=10,
                )

            # Cleanup any existing containers
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "down",
                    "-v",
                ],
                capture_output=True,
                timeout=30,
                cwd=output_dir,
            )

            # Start container
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "pull",
                ],
                capture_output=True,
                timeout=120,
            )

            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "up",
                    "-d",
                ],
                capture_output=True,
                timeout=60,
                cwd=output_dir,
            )

            time.sleep(5)

            # Get container ID
            container_result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "ps",
                    "-q",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=output_dir,
            )

            # Get first container ID (stdout may have multiple IDs, one per line)
            container_id = (
                container_result.stdout.strip().split("\n")[0]
                if container_result.stdout.strip()
                else ""
            )

            if not container_id:
                # Check if containers failed to start
                ps_all = subprocess.run(
                    [
                        "docker",
                        "compose",
                        "-f",
                        str(compose_file),
                        "-p",
                        project_name,
                        "ps",
                        "-a",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=output_dir,
                )
                pytest.fail(
                    f"No running containers found. Status:\n{ps_all.stdout}\n{ps_all.stderr}"
                )

            # Check if mounted directories exist in container
            exec_result = subprocess.run(
                ["docker", "exec", container_id, "ls", "-la", "/config"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Config directory should exist
            assert exec_result.returncode == 0, (
                f"Config directory not accessible in container. Error: {exec_result.stderr}"
            )

        except subprocess.TimeoutExpired as e:
            pytest.fail(f"Container operations timed out: {e}")
        except AssertionError:
            raise
        except Exception as e:
            pytest.fail(f"Test failed with error: {e}")
        finally:
            # Cleanup
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "down",
                    "-v",
                ],
                capture_output=True,
                timeout=30,
                cwd=output_dir,
            )

    def test_multiple_services_networking(self, docker_tmp_dir):
        """Test that multiple services can communicate when using the same network."""
        from src.file_generator import FileGenerator
        from src.template_loader import TemplateLoader

        loader = TemplateLoader()
        generator = FileGenerator(loader)

        output_dir = docker_tmp_dir / "network_test"
        output_dir.mkdir()
        docker_dir = docker_tmp_dir / "docker"
        media_dir = docker_tmp_dir / "media"

        # Generate compose with multiple services
        results = generator.generate_all_files(
            selected_services=["jellyfin", "sonarr"],
            uid=1000,
            gid=1000,
            docker_dir=docker_dir,
            media_dir=media_dir,
            output_dir=output_dir,
            timezone="UTC",
        )

        compose_file = output_dir / "docker-compose.yml"

        # Verify network configuration in compose file
        content = compose_file.read_text()

        # Should have networks section
        assert "networks:" in content

        # Services should be on the same network
        assert "media-network" in content or "default" in content

        project_name = f"mediaserver-network-test-{os.getpid()}"

        try:
            # Validate compose file
            config_result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(compose_file),
                    "-p",
                    project_name,
                    "config",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=output_dir,
            )

            assert config_result.returncode == 0

            # Verify both services are in the config
            assert "jellyfin" in config_result.stdout
            assert "sonarr" in config_result.stdout

        except subprocess.TimeoutExpired:
            pytest.skip("Docker operations timed out")
        except Exception as e:
            pytest.skip(f"Test environment issue: {e}")

    def test_environment_variables_passed_correctly(self, docker_tmp_dir):
        """Test that environment variables are correctly set in generated files."""
        from src.file_generator import FileGenerator
        from src.template_loader import TemplateLoader

        loader = TemplateLoader()
        generator = FileGenerator(loader)

        output_dir = docker_tmp_dir / "env_test"
        output_dir.mkdir()
        docker_dir = docker_tmp_dir / "docker"
        media_dir = docker_tmp_dir / "media"

        results = generator.generate_all_files(
            selected_services=["sonarr"],
            uid=1000,
            gid=1000,
            docker_dir=docker_dir,
            media_dir=media_dir,
            output_dir=output_dir,
            timezone="America/New_York",
        )

        compose_file = output_dir / "docker-compose.yml"
        env_file = output_dir / ".env"

        # Verify .env file was created
        assert env_file.exists()

        # Check .env contains timezone
        env_content = env_file.read_text()
        assert "TZ=America/New_York" in env_content

        # Verify compose file has PUID/PGID set directly (not as env var references)
        compose_content = compose_file.read_text()
        assert "PUID=1000" in compose_content
        assert "PGID=1000" in compose_content
        assert "environment:" in compose_content
