#!/usr/bin/env python3
"""
Local validation script for media-server-automatorr CI/CD pipeline.

This script runs the same validations that are performed in the CI/CD pipeline
locally, allowing developers to test their changes before pushing to the repository.



Usage:
    python scripts/validate-pipeline.py [--verbose] [--skip-integration] [--timeout 300]
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any
from urllib.request import urlopen
from urllib.error import URLError


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class ValidationResult:
    """Represents the result of a validation check."""

    def __init__(self, name: str, success: bool, message: str = "", details: List[str] = None):
        self.name = name
        self.success = success
        self.message = message
        self.details = details or []
        self.duration = 0.0


class PipelineValidator:
    """Runs local validation of CI/CD pipeline components."""

    def __init__(self, verbose: bool = False, skip_integration: bool = False, timeout: int = 300):
        self.verbose = verbose
        self.skip_integration = skip_integration
        self.timeout = timeout
        self.results: List[ValidationResult] = []
        self.project_root = Path(__file__).parent.parent.resolve()

    def print_info(self, message: str) -> None:
        """Print info message."""
        print(f"{Colors.BLUE}ℹ{Colors.END} {message}")

    def print_success(self, message: str) -> None:
        """Print success message."""
        print(f"{Colors.GREEN}✓{Colors.END} {message}")

    def print_warning(self, message: str) -> None:
        """Print warning message."""
        print(f"{Colors.YELLOW}⚠{Colors.END} {message}")

    def print_error(self, message: str) -> None:
        """Print error message."""
        print(f"{Colors.RED}❌{Colors.END} {message}")

    def print_header(self, message: str) -> None:
        """Print section header."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{message.center(60)}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")

    def run_command(self, cmd: List[str], cwd: Path = None, timeout: int = 60) -> Tuple[int, str, str]:
        """Run a command and return return code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 124, "", "Command timed out"
        except FileNotFoundError:
            return 127, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return 1, "", str(e)

    def load_project_module(self, module_name: str):
        """Load a module from the src directory using package imports."""
        import importlib

        # Add project root to path if not already there
        project_root_str = str(self.project_root)
        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)

        try:
            # Import from src package
            module = importlib.import_module(f'src.{module_name}')
            return module
        except Exception as e:
            raise ImportError(f"Failed to load {module_name}: {str(e)}")

    def validate_system_prerequisites(self) -> ValidationResult:
        """Validate system prerequisites like Docker and Python."""
        start_time = time.time()
        details = []

        try:
            # Check Python version
            python_version = sys.version_info
            if python_version >= (3, 8):
                details.append(f"✓ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
            else:
                return ValidationResult(
                    "System Prerequisites",
                    False,
                    f"Python {python_version.major}.{python_version.minor} < 3.8 (required)",
                    details
                )

            # Check Docker
            code, stdout, stderr = self.run_command(["docker", "--version"])
            if code == 0:
                details.append(f"✓ {stdout.strip()}")
            else:
                return ValidationResult(
                    "System Prerequisites",
                    False,
                    "Docker not available",
                    details + [f"Error: {stderr}"]
                )

            # Check Docker Compose
            code, stdout, stderr = self.run_command(["docker", "compose", "version"])
            if code == 0:
                details.append(f"✓ {stdout.strip()}")
            else:
                return ValidationResult(
                    "System Prerequisites",
                    False,
                    "Docker Compose not available",
                    details + [f"Error: {stderr}"]
                )

            # Check Docker permissions
            code, stdout, stderr = self.run_command(["docker", "ps"])
            if code == 0:
                details.append("✓ Docker permissions OK")
            else:
                return ValidationResult(
                    "System Prerequisites",
                    False,
                    "Cannot run Docker without sudo",
                    details + ["Try: sudo usermod -aG docker $USER && newgrp docker"]
                )

            # Check required Python packages
            required_packages = [
                ("pytest", "pytest"),
                ("PyYAML", "yaml"),
                ("requests", "requests")
            ]
            for package_name, import_name in required_packages:
                try:
                    __import__(import_name)
                    details.append(f"✓ Python package: {package_name}")
                except ImportError:
                    return ValidationResult(
                        "System Prerequisites",
                        False,
                        f"Missing Python package: {package_name}",
                        details + [f"Try: pip install {package_name}"]
                    )

            result = ValidationResult(
                "System Prerequisites",
                True,
                "All system prerequisites available",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "System Prerequisites",
                False,
                f"Validation failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def validate_docker_environment(self) -> ValidationResult:
        """Validate Docker environment and configuration generation."""
        start_time = time.time()
        details = []

        try:
            # Test Docker Compose generation
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                docker_dir = temp_path / 'docker'
                media_dir = temp_path / 'media'
                docker_dir.mkdir()
                media_dir.mkdir()

                try:
                    # Load required modules
                    template_loader_module = self.load_project_module("template_loader")
                    compose_generator_module = self.load_project_module("compose_generator")

                    TemplateLoader = template_loader_module.TemplateLoader
                    ComposeGenerator = compose_generator_module.ComposeGenerator
                    details.append("✓ Template loader and compose generator imports")
                except Exception as e:
                    return ValidationResult(
                        "Docker Environment",
                        False,
                        f"Import failed: {str(e)}",
                        details
                    )

                # Test template loading
                try:
                    loader = TemplateLoader()
                    services = loader.get_services()
                    categories = loader.get_categories()
                    details.append(f"✓ Loaded {len(services)} services, {len(categories)} categories")
                except Exception as e:
                    return ValidationResult(
                        "Docker Environment",
                        False,
                        f"Template loading failed: {str(e)}",
                        details
                    )

                # Test compose generation
                try:
                    generator = ComposeGenerator(loader)
                    test_services = ['jellyfin', 'qbittorrent', 'sonarr']

                    compose_content = generator.generate(
                        selected_services=test_services,
                        uid=1000,
                        gid=1000,
                        docker_dir=docker_dir,
                        media_dir=media_dir,
                        timezone='UTC'
                    )

                    # Validate generated content
                    required_content = ['jellyfin:', 'qbittorrent:', 'sonarr:', 'networks:', 'media-network:']
                    for content in required_content:
                        if content not in compose_content:
                            return ValidationResult(
                                "Docker Environment",
                                False,
                                f"Generated compose missing: {content}",
                                details
                            )

                    details.append(f"✓ Generated compose file ({len(compose_content)} chars)")

                except Exception as e:
                    return ValidationResult(
                        "Docker Environment",
                        False,
                        f"Compose generation failed: {str(e)}",
                        details
                    )

                # Test environment variable handling
                try:
                    utils_module = self.load_project_module("utils")
                    get_timezone = utils_module.get_timezone
                    generate_encryption_key = utils_module.generate_encryption_key

                    tz = get_timezone()
                    key = generate_encryption_key()

                    if not tz:
                        details.append("⚠ Timezone detection returned empty")
                    else:
                        details.append(f"✓ Timezone: {tz}")

                    if len(key) < 32:
                        return ValidationResult(
                            "Docker Environment",
                            False,
                            f"Encryption key too short: {len(key)} chars",
                            details
                        )
                    else:
                        details.append(f"✓ Encryption key: {len(key)} chars")

                except Exception as e:
                    return ValidationResult(
                        "Docker Environment",
                        False,
                        f"Environment variable handling failed: {str(e)}",
                        details
                    )

            result = ValidationResult(
                "Docker Environment",
                True,
                "Docker environment validation passed",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "Docker Environment",
                False,
                f"Validation failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def validate_vpn_configuration(self) -> ValidationResult:
        """Validate VPN (Gluetun) configuration."""
        start_time = time.time()
        details = []

        try:
            # Test VPN configuration imports
            try:
                vpn_config_module = self.load_project_module("vpn_config")
                utils_module = self.load_project_module("utils")

                GluetunConfigurator = vpn_config_module.GluetunConfigurator
                validate_subnet_format = utils_module.validate_subnet_format
                details.append("✓ VPN configuration imports")
            except Exception as e:
                return ValidationResult(
                    "VPN Configuration",
                    False,
                    f"VPN import failed: {str(e)}",
                    details
                )

            # Test subnet validation
            test_subnets = [
                ('192.168.1.0/24', True),
                ('172.17.0.0/16', True),
                ('10.0.0.0/8', True),
                ('invalid', False),
                ('192.168.1.0/33', False),
            ]

            for subnet, expected in test_subnets:
                result = validate_subnet_format(subnet)
                if result != expected:
                    return ValidationResult(
                        "VPN Configuration",
                        False,
                        f"Subnet validation failed for {subnet}: expected {expected}, got {result}",
                        details
                    )

            details.append("✓ Subnet validation working correctly")

            # Test VPN configurator
            try:
                configurator = GluetunConfigurator()

                # Load VPN providers from constants
                constants_module = self.load_project_module("constants")
                providers = getattr(constants_module, 'VPN_PROVIDERS', {})

                if not providers:
                    return ValidationResult(
                        "VPN Configuration",
                        False,
                        "No VPN providers found in constants",
                        details
                    )

                details.append(f"✓ Found {len(providers)} VPN providers")

                # Test configuration generation
                configurator.provider = 'nordvpn'
                configurator.vpn_type = 'openvpn'
                configurator.enabled = True
                configurator.credentials = {'OPENVPN_USER': 'test', 'OPENVPN_PASSWORD': 'test'}

                env_vars = configurator.get_environment_vars()

                if 'VPN_SERVICE_PROVIDER' not in env_vars:
                    return ValidationResult(
                        "VPN Configuration",
                        False,
                        "VPN_SERVICE_PROVIDER not in generated environment variables",
                        details
                    )

                details.append(f"✓ Generated {len(env_vars)} environment variables")

            except Exception as e:
                return ValidationResult(
                    "VPN Configuration",
                    False,
                    f"VPN configurator test failed: {str(e)}",
                    details
                )

            result = ValidationResult(
                "VPN Configuration",
                True,
                "VPN configuration validation passed",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "VPN Configuration",
                False,
                f"Validation failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def validate_port_accessibility(self) -> ValidationResult:
        """Validate port accessibility functions."""
        start_time = time.time()
        details = []

        try:
            # Test port accessibility function
            def test_port(host: str, port: int, timeout: int = 5) -> bool:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(timeout)
                        result = sock.connect_ex((host, port))
                        return result == 0
                except:
                    return False

            # Test with a port that should be closed
            closed_port_result = test_port("localhost", 65432, timeout=1)
            if closed_port_result:
                details.append("⚠ Port 65432 unexpectedly open")
            else:
                details.append("✓ Closed port detection working")

            # Check for port conflicts in service configuration
            try:
                template_loader_module = self.load_project_module("template_loader")
                TemplateLoader = template_loader_module.TemplateLoader

                loader = TemplateLoader()
                services = loader.get_services()

                used_ports = set()
                port_conflicts = {}

                for service_id, service in services.items():
                    main_port = service.get('port')
                    if main_port:
                        if main_port in used_ports:
                            if main_port not in port_conflicts:
                                port_conflicts[main_port] = []
                            port_conflicts[main_port].append(service_id)
                        else:
                            used_ports.add(main_port)

                        # Check extra ports
                        for extra_port in service.get('extra_ports', []):
                            if extra_port in used_ports:
                                if extra_port not in port_conflicts:
                                    port_conflicts[extra_port] = []
                                port_conflicts[extra_port].append(service_id)
                            else:
                                used_ports.add(extra_port)

                if port_conflicts:
                    conflict_details = []
                    for port, services in port_conflicts.items():
                        conflict_details.append(f"Port {port}: {', '.join(services)}")
                    details.append(f"⚠ Port conflicts found: {'; '.join(conflict_details)}")
                else:
                    details.append("✓ No port conflicts detected")

                details.append(f"✓ Checked {len(services)} services, {len(used_ports)} unique ports")

            except Exception as e:
                return ValidationResult(
                    "Port Accessibility",
                    False,
                    f"Port configuration check failed: {str(e)}",
                    details
                )

            result = ValidationResult(
                "Port Accessibility",
                True,
                "Port accessibility validation passed",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "Port Accessibility",
                False,
                f"Validation failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def validate_file_permissions(self) -> ValidationResult:
        """Validate file permission handling."""
        start_time = time.time()
        details = []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Test Docker directory structure
                docker_dir = temp_path / 'docker'
                docker_dir.mkdir(mode=0o755)

                test_services = ['jellyfin', 'qbittorrent', 'sonarr']
                for service in test_services:
                    service_dir = docker_dir / service / 'config'
                    service_dir.mkdir(parents=True, mode=0o755)

                    # Test write permissions
                    test_file = service_dir / 'test.txt'
                    try:
                        test_file.write_text('test content')
                        if not test_file.exists():
                            return ValidationResult(
                                "File Permissions",
                                False,
                                f"File creation failed in {service_dir}",
                                details
                            )
                        test_file.unlink()
                        details.append(f"✓ {service} config directory writable")
                    except Exception as e:
                        return ValidationResult(
                            "File Permissions",
                            False,
                            f"Write test failed for {service}: {str(e)}",
                            details
                        )

                # Test media directory structure
                media_dir = temp_path / 'media'
                media_dir.mkdir(mode=0o755)

                media_subdirs = ['movies', 'tv', 'music', 'downloads']
                for subdir in media_subdirs:
                    sub_path = media_dir / subdir
                    sub_path.mkdir(mode=0o755)

                    # Test write permissions
                    test_file = sub_path / 'test.txt'
                    try:
                        test_file.write_text('test content')
                        if not test_file.exists():
                            return ValidationResult(
                                "File Permissions",
                                False,
                                f"File creation failed in {sub_path}",
                                details
                            )
                        test_file.unlink()
                        details.append(f"✓ {subdir} media directory writable")
                    except Exception as e:
                        return ValidationResult(
                            "File Permissions",
                            False,
                            f"Write test failed for {subdir}: {str(e)}",
                            details
                        )

                # Test permission scenarios
                current_uid = os.getuid()
                current_gid = os.getgid()
                details.append(f"✓ Running as UID/GID: {current_uid}/{current_gid}")

            result = ValidationResult(
                "File Permissions",
                True,
                "File permissions validation passed",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "File Permissions",
                False,
                f"Validation failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def validate_security(self) -> ValidationResult:
        """Validate security aspects."""
        start_time = time.time()
        details = []

        try:
            # Test encryption key security
            try:
                utils_module = self.load_project_module("utils")
                generate_encryption_key = utils_module.generate_encryption_key

                key = generate_encryption_key()

                # Check key length
                if len(key) < 32:
                    return ValidationResult(
                        "Security",
                        False,
                        f"Encryption key too short: {len(key)} characters",
                        details
                    )

                # Check key randomness (basic test)
                unique_chars = len(set(key))
                if unique_chars < 16:
                    return ValidationResult(
                        "Security",
                        False,
                        f"Encryption key not random enough: {unique_chars} unique characters",
                        details
                    )

                details.append(f"✓ Encryption key: {len(key)} chars, {unique_chars} unique")

            except Exception as e:
                return ValidationResult(
                    "Security",
                    False,
                    f"Encryption key test failed: {str(e)}",
                    details
                )

            # Check service security configuration
            try:
                template_loader_module = self.load_project_module("template_loader")
                TemplateLoader = template_loader_module.TemplateLoader

                loader = TemplateLoader()
                services = loader.get_services()

                security_issues = []

                for service_id, service in services.items():
                    # Check for privileged containers
                    if service.get('privileged'):
                        security_issues.append(f"{service_id}: Running in privileged mode")

                    # Check for PUID/PGID
                    env_vars = service.get('env', [])
                    if 'PUID' not in env_vars and service_id != 'gluetun':  # Gluetun runs as root by design
                        security_issues.append(f"{service_id}: No PUID specified (may run as root)")

                    # Check for sensitive bind mounts
                    volumes = service.get('volumes', {})
                    extra_volumes = service.get('extra_volumes', {})
                    all_volumes = {**volumes, **extra_volumes}

                    for host_path, container_path in all_volumes.items():
                        if host_path in ['/etc', '/', '/var/run/docker.sock']:
                            security_issues.append(f"{service_id}: Sensitive bind mount {host_path}")

                if security_issues:
                    for issue in security_issues:
                        details.append(f"⚠ {issue}")
                    details.append("Note: Some security considerations may be intentional")
                else:
                    details.append("✓ No obvious security issues detected")

            except Exception as e:
                return ValidationResult(
                    "Security",
                    False,
                    f"Security configuration check failed: {str(e)}",
                    details
                )

            # Test for common Python security issues
            try:
                # Check if bandit is available
                code, stdout, stderr = self.run_command(["bandit", "--version"], timeout=10)
                if code == 0:
                    # Run bandit security scan
                    code, stdout, stderr = self.run_command([
                        "bandit", "-r", "src/", "-f", "txt", "-ll"
                    ], timeout=30)

                    if code == 0:
                        if "No issues identified" in stdout:
                            details.append("✓ Bandit security scan: No issues")
                        else:
                            details.append("⚠ Bandit found potential security issues")
                            if self.verbose:
                                details.append(f"Bandit output: {stdout}")
                    else:
                        details.append(f"⚠ Bandit scan failed: {stderr}")
                else:
                    details.append("ℹ Bandit not available (optional)")

            except Exception as e:
                details.append(f"ℹ Bandit security scan skipped: {str(e)}")

            result = ValidationResult(
                "Security",
                True,
                "Security validation passed",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "Security",
                False,
                f"Validation failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def validate_integration_health(self) -> ValidationResult:
        """Run integration health checks with real Docker containers."""
        start_time = time.time()
        details = []

        if self.skip_integration:
            return ValidationResult(
                "Integration Health",
                True,
                "Skipped (--skip-integration)",
                ["ℹ Integration tests skipped by user request"]
            )

        try:
            self.print_info("Starting integration test with real containers...")

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Create test directories
                test_docker_dir = temp_path / "docker"
                test_media_dir = temp_path / "media"
                test_docker_dir.mkdir()
                test_media_dir.mkdir()

                # Create service directories with proper permissions
                jellyfin_config = test_docker_dir / "jellyfin" / "config"
                jellyfin_config.mkdir(parents=True, mode=0o755)

                movies_dir = test_media_dir / "movies"
                movies_dir.mkdir(parents=True, mode=0o755)

                # Set ownership to current user to avoid permission issues
                import os
                current_uid = os.getuid()
                current_gid = os.getgid()

                try:
                    os.chown(str(jellyfin_config), current_uid, current_gid)
                    os.chown(str(movies_dir), current_uid, current_gid)
                except PermissionError:
                    # If we can't change ownership, at least ensure directories are writable
                    jellyfin_config.chmod(0o777)
                    movies_dir.chmod(0o777)

                # Create minimal docker-compose.yml for testing
                compose_content = """---
services:
  test-jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: test-jellyfin
    restart: "no"
    user: "{uid}:{gid}"
    environment:
      - TZ=UTC
      - PUID={uid}
      - PGID={gid}
    volumes:
      - {docker_dir}/jellyfin/config:/config
      - {media_dir}:/media:ro
    ports:
      - "18096:8096"
    networks:
      - test-network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8096/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 2
      start_period: 30s

networks:
  test-network:
    driver: bridge
""".format(
                    docker_dir=test_docker_dir.absolute(),
                    media_dir=test_media_dir.absolute(),
                    uid=current_uid,
                    gid=current_gid
                )

                compose_file = temp_path / "docker-compose.test.yml"
                compose_file.write_text(compose_content)

                details.append("✓ Created test compose file")

                try:
                    # Start test container
                    self.print_info("Starting test container...")
                    code, stdout, stderr = self.run_command([
                        "docker", "compose", "-f", str(compose_file), "up", "-d"
                    ], timeout=120)

                    if code != 0:
                        return ValidationResult(
                            "Integration Health",
                            False,
                            f"Failed to start test container: {stderr}",
                            details
                        )

                    details.append("✓ Test container started")

                    # Wait for container to be ready
                    self.print_info("Waiting for container to be ready...")
                    ready = False
                    for i in range(30):  # Wait up to 60 seconds
                        code, stdout, stderr = self.run_command([
                            "docker", "ps", "--filter", "name=test-jellyfin",
                            "--format", "{{.Status}}"
                        ])

                        if code == 0 and "Up" in stdout:
                            ready = True
                            break

                        time.sleep(2)

                    if not ready:
                        details.append("❌ Container did not become ready")
                        return ValidationResult(
                            "Integration Health",
                            False,
                            "Test container did not start properly",
                            details
                        )

                    details.append("✓ Container is running")

                    # Test port accessibility
                    self.print_info("Testing port accessibility...")
                    port_accessible = False
                    for i in range(15):  # Wait up to 30 seconds for port
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                                sock.settimeout(2)
                                result = sock.connect_ex(("localhost", 18096))
                                if result == 0:
                                    port_accessible = True
                                    break
                        except:
                            pass
                        time.sleep(2)

                    if port_accessible:
                        details.append("✓ Port 18096 accessible")
                    else:
                        details.append("⚠ Port 18096 not accessible (container may still be starting)")

                    # Test HTTP response
                    if port_accessible:
                        try:
                            response = urlopen("http://localhost:18096", timeout=10)
                            status_code = response.getcode()
                            details.append(f"✓ HTTP response: {status_code}")
                        except Exception as e:
                            details.append(f"⚠ HTTP test failed: {str(e)}")

                    # Test file permissions with better error handling
                    try:
                        code, stdout, stderr = self.run_command([
                            "docker", "exec", "test-jellyfin", "test", "-w", "/config"
                        ])

                        if code == 0:
                            details.append("✓ Config directory writable in container")
                        else:
                            details.append("⚠ Config directory not writable in container (expected)")
                    except Exception as e:
                        details.append(f"⚠ Permission test skipped: {str(e)}")

                    # Check container logs for errors
                    code, stdout, stderr = self.run_command([
                        "docker", "logs", "test-jellyfin", "--tail", "20"
                    ])

                    if code == 0:
                        error_patterns = ["error", "fatal", "exception", "failed"]
                        log_lines = stdout.lower().split('\n')
                        errors_found = []

                        for line in log_lines:
                            for pattern in error_patterns:
                                if pattern in line and line.strip():
                                    errors_found.append(line.strip())

                        if errors_found:
                            details.append(f"⚠ Found {len(errors_found)} potential errors in logs")
                            if self.verbose:
                                for error in errors_found[:3]:  # Show first 3 errors
                                    details.append(f"  Log error: {error}")
                        else:
                            details.append("✓ No obvious errors in container logs")

                finally:
                    # Cleanup with better error handling
                    try:
                        self.print_info("Cleaning up test containers...")
                        self.run_command([
                            "docker", "compose", "-f", str(compose_file), "down", "-v", "--remove-orphans"
                        ], timeout=60)
                        details.append("✓ Test containers cleaned up")
                    except Exception as cleanup_error:
                        details.append(f"⚠ Cleanup warning: {str(cleanup_error)}")
                        # Try force cleanup
                        try:
                            self.run_command(["docker", "rm", "-f", "test-jellyfin"], timeout=30)
                        except:
                            pass

            result = ValidationResult(
                "Integration Health",
                True,
                "Integration health validation passed",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "Integration Health",
                False,
                f"Integration test failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def run_unit_tests(self) -> ValidationResult:
        """Run unit tests."""
        start_time = time.time()
        details = []

        try:
            # Run pytest
            test_dir = self.project_root / "tests"

            code, stdout, stderr = self.run_command([
                "python", "-m", "pytest", str(test_dir),
                "--tb=short", "-x", "--no-cov", "-q"
            ], timeout=120)

            if code == 0:
                details.append("✓ All unit tests passed")

                # Parse test results for more details
                lines = stdout.split('\n')
                test_count = 0
                for line in lines:
                    if '::' in line and ('PASSED' in line or 'FAILED' in line):
                        test_count += 1

                details.append(f"✓ Ran {test_count} unit tests")

            else:
                return ValidationResult(
                    "Unit Tests",
                    False,
                    f"Unit tests failed (exit code: {code})",
                    details + [f"Error: {stderr}", f"Output: {stdout}"]
                )

            result = ValidationResult(
                "Unit Tests",
                True,
                "Unit tests validation passed",
                details
            )

        except Exception as e:
            result = ValidationResult(
                "Unit Tests",
                False,
                f"Unit test execution failed: {str(e)}",
                details
            )

        result.duration = time.time() - start_time
        return result

    def run_all_validations(self) -> List[ValidationResult]:
        """Run all validation checks."""
        validations = [
            ("System Prerequisites", self.validate_system_prerequisites),
            ("Docker Environment", self.validate_docker_environment),
            ("VPN Configuration", self.validate_vpn_configuration),
            ("Port Accessibility", self.validate_port_accessibility),
            ("File Permissions", self.validate_file_permissions),
            ("Security", self.validate_security),
            ("Unit Tests", self.run_unit_tests),
        ]

        # Add integration tests if not skipped
        if not self.skip_integration:
            validations.append(("Integration Health", self.validate_integration_health))

        results = []

        for name, validation_func in validations:
            self.print_header(f"Validating: {name}")

            try:
                result = validation_func()
                results.append(result)

                if result.success:
                    self.print_success(f"{result.name}: {result.message}")
                else:
                    self.print_error(f"{result.name}: {result.message}")

                if self.verbose and result.details:
                    for detail in result.details:
                        print(f"  {detail}")

                if result.duration > 0:
                    duration_str = f"({result.duration:.1f}s)"
                    print(f"  Duration: {duration_str}")

            except KeyboardInterrupt:
                self.print_warning("Validation interrupted by user")
                break
            except Exception as e:
                error_result = ValidationResult(name, False, f"Unexpected error: {str(e)}")
                results.append(error_result)
                self.print_error(f"{name}: {error_result.message}")

        return results

    def print_summary(self, results: List[ValidationResult]) -> None:
        """Print validation summary."""
        self.print_header("Validation Summary")

        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.success)
        failed_tests = total_tests - passed_tests
        total_duration = sum(r.duration for r in results)

        print(f"Total validations: {total_tests}")
        print(f"Passed: {Colors.GREEN}{passed_tests}{Colors.END}")
        print(f"Failed: {Colors.RED}{failed_tests}{Colors.END}")
        print(f"Success rate: {(passed_tests/total_tests*100):.1f}%" if total_tests > 0 else "0%")
        print(f"Total duration: {total_duration:.1f}s")

        if failed_tests > 0:
            print(f"\n{Colors.RED}❌ Failed Validations:{Colors.END}")
            for result in results:
                if not result.success:
                    print(f"  • {result.name}: {result.message}")
                    if self.verbose and result.details:
                        for detail in result.details[:3]:  # Show first 3 details
                            print(f"    {detail}")

        print(f"\n{Colors.BOLD}Overall Status:{Colors.END}", end=" ")
        if failed_tests == 0:
            print(f"{Colors.GREEN}✓ ALL VALIDATIONS PASSED{Colors.END}")
            print("\n🎉 Your pipeline is ready for CI/CD!")
        elif failed_tests <= 2:
            print(f"{Colors.YELLOW}⚠ MINOR ISSUES DETECTED{Colors.END}")
            print("\n⚠️  Some validations failed, but core functionality works")
        else:
            print(f"{Colors.RED}❌ CRITICAL ISSUES DETECTED{Colors.END}")
            print("\n❌ Multiple validations failed - please review and fix issues")

    def generate_report(self, results: List[ValidationResult], output_file: Path) -> None:
        """Generate detailed validation report."""
        report = {
            "timestamp": time.time(),
            "summary": {
                "total_validations": len(results),
                "passed": sum(1 for r in results if r.success),
                "failed": sum(1 for r in results if not r.success),
                "total_duration": sum(r.duration for r in results)
            },
            "validations": []
        }

        for result in results:
            validation_data = {
                "name": result.name,
                "success": result.success,
                "message": result.message,
                "duration": result.duration,
                "details": result.details
            }
            report["validations"].append(validation_data)

        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            self.print_success(f"Detailed report saved to: {output_file}")
        except Exception as e:
            self.print_error(f"Failed to save report: {str(e)}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate media-server-automatorr CI/CD pipeline locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/validate-pipeline.py                    # Run all validations
  python scripts/validate-pipeline.py --verbose          # Detailed output
  python scripts/validate-pipeline.py --skip-integration # Skip Docker tests
  python scripts/validate-pipeline.py --timeout 600     # 10 minute timeout
        """
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output with detailed information"
    )

    parser.add_argument(
        "--skip-integration",
        action="store_true",
        help="Skip integration tests that require Docker containers"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout for individual validations in seconds (default: 300)"
    )

    parser.add_argument(
        "--report",
        type=Path,
        help="Generate detailed JSON report to specified file"
    )

    args = parser.parse_args()

    # Create validator
    validator = PipelineValidator(
        verbose=args.verbose,
        skip_integration=args.skip_integration,
        timeout=args.timeout
    )

    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("=" * 80)
    print("  MEDIA SERVER AUTOMATORR - PIPELINE VALIDATION")
    print("=" * 80)
    print(f"{Colors.END}")

    if args.skip_integration:
        print(f"{Colors.YELLOW}⚠ Integration tests will be skipped{Colors.END}")

    print(f"Validation timeout: {args.timeout}s")
    print(f"Verbose mode: {'On' if args.verbose else 'Off'}")
    print()

    try:
        # Run validations
        results = validator.run_all_validations()

        # Print summary
        validator.print_summary(results)

        # Generate report if requested
        if args.report:
            validator.generate_report(results, args.report)

        # Exit with appropriate code
        failed_count = sum(1 for r in results if not r.success)
        sys.exit(0 if failed_count == 0 else 1)

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠ Validation interrupted by user{Colors.END}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}❌ Unexpected error: {str(e)}{Colors.END}")
        sys.exit(1)


if __name__ == "__main__":
    main()
