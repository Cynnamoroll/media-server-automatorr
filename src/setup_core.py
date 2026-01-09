"""
Core setup module for media-server-automatorr.

Refactored to use modular components and smaller, focused functions.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List

from .constants import SETUP_ORDER_PRIORITY
from .directory_manager import DirectoryManager
from .file_generator import FileGenerator
from .system_validators import ContainerTester, SystemValidator
from .template_loader import TemplateLoader
from .user_interface import (ProgressReporter, ServiceSelector,
                             UserConfigCollector)
from .utils import (Colors, get_local_network_ip, get_timezone, print_error,
                    print_header, print_info, print_success, print_warning,
                    prompt_yes_no, wait_for_done)
from .vpn_config import GluetunConfigurator


class MediaServerSetup:
    """Main setup orchestrator with modular architecture."""

    def __init__(self):
        # Core components
        self.template_loader = TemplateLoader()
        self.system_validator = SystemValidator()
        self.directory_manager = DirectoryManager()
        self.file_generator = FileGenerator(self.template_loader)
        self.gluetun_configurator = GluetunConfigurator()

        # Progress tracking
        self.progress = ProgressReporter(7)  # Total setup steps

        # Configuration state
        self.username: str = ""
        self.uid: int = 0
        self.gid: int = 0
        self.docker_dir: Path = Path()
        self.media_dir: Path = Path()
        self.output_dir: Path = Path()
        self.timezone: str = ""
        self.host_ip: str = ""
        self.selected_services: List[str] = []
        self.remote_access: bool = False

    def run(self) -> None:
        """Run the complete setup process with error handling."""
        try:
            self._print_welcome()
            self._run_setup_steps()
            self._print_completion_message()

        except KeyboardInterrupt:
            print_error("\nSetup cancelled by user.")
            sys.exit(1)
        except Exception as e:
            print_error(f"Setup failed: {e}")
            if self._should_show_debug_info():
                import traceback

                traceback.print_exc()
            sys.exit(1)

    def _print_welcome(self) -> None:
        """Print welcome message and detect access mode."""
        print_header("MEDIA SERVER SETUP")
        print("Welcome to the Media Server Setup Script!")
        print(
            "This script will guide you through setting up a complete media server stack."
        )
        print()

        self._detect_access_mode()

    def _detect_access_mode(self) -> None:
        """Detect if setup is running via SSH or locally."""
        ssh_client = os.environ.get("SSH_CLIENT")
        ssh_connection = os.environ.get("SSH_CONNECTION")

        if ssh_client or ssh_connection:
            print_info("SSH connection detected - remote setup mode")
            self.remote_access = True
            self.host_ip = get_local_network_ip()
            print_info(f"Server IP address: {self.host_ip}")
        else:
            print_info("Local setup mode")
            self.remote_access = False
            self.host_ip = "localhost"

    def _run_setup_steps(self) -> None:
        """Execute all setup steps in order."""
        # Step 1: Validate system
        self.progress.start_step("System Validation")
        if not self._validate_system():
            sys.exit(1)
        self.progress.step_success("System validation complete")

        # Step 2: Load and validate templates
        self.progress.start_step("Template Validation")
        if not self._validate_templates():
            sys.exit(1)
        self.progress.step_success("Templates validated")

        # Step 3: Collect user configuration
        self.progress.start_step("User Configuration")
        self._collect_user_configuration()
        self.progress.step_success("User configuration complete")

        # Step 4: Select services
        self.progress.start_step("Service Selection")
        self._select_services()
        self.progress.step_success(f"Selected {len(self.selected_services)} services")

        # Step 5: Configure VPN (optional)
        self.progress.start_step("VPN Configuration")
        self._configure_vpn()
        if self.gluetun_configurator.enabled:
            self.progress.step_success("VPN configured")
        else:
            self.progress.step_success("VPN configuration skipped")

        # Step 6: Create directories and generate files
        self.progress.start_step("Directory Setup & File Generation")
        if not self._setup_directories_and_files():
            sys.exit(1)
        self.progress.step_success("Directories and files created")

        # Step 7: Final setup options
        self.progress.start_step("Final Configuration")
        self._handle_final_setup()
        self.progress.step_success("Setup complete")

    def _validate_system(self) -> bool:
        """Validate system prerequisites."""
        if not self.system_validator.validate_all():
            print_error(
                "System validation failed. Please fix the issues above and try again."
            )
            return False
        return True

    def _validate_templates(self) -> bool:
        """Validate template files exist and are valid."""
        try:
            issues = self.template_loader.validate_services()
            if issues:
                print_error("Template validation failed:")
                for issue in issues:
                    print_error(f"  - {issue}")
                return False
            return True
        except Exception as e:
            print_error(f"Failed to load templates: {e}")
            return False

    def _collect_user_configuration(self) -> None:
        """Collect user and directory configuration."""
        # Get user information
        self.username, self.uid, self.gid = UserConfigCollector.get_user_info()

        # Get directory paths
        docker_dir_str, media_dir_str = UserConfigCollector.get_directory_paths()
        self.docker_dir = Path(docker_dir_str)
        self.media_dir = Path(media_dir_str)
        self.output_dir = self.docker_dir / "compose"

        # Get timezone
        self.timezone = get_timezone()
        print_info(f"Detected timezone: {self.timezone}")

    def _select_services(self) -> None:
        """Handle service selection with improved UX."""
        services = self.template_loader.get_services()
        categories = self.template_loader.get_categories()
        services_by_category = self.template_loader.get_services_by_category()

        service_selector = ServiceSelector(services, categories, services_by_category)
        self.selected_services = service_selector.select_services()

        # Confirm final configuration
        if not UserConfigCollector.confirm_setup(
            self.username,
            str(self.docker_dir),
            str(self.media_dir),
            self.selected_services,
            services,
        ):
            print_info("Setup cancelled by user.")
            sys.exit(0)

    def _configure_vpn(self) -> None:
        """Configure VPN if user wants it and qBittorrent is selected."""
        if "qbittorrent" not in self.selected_services:
            print_info("VPN configuration skipped (no torrent client selected)")
            return

        if self.gluetun_configurator.configure():
            # Add gluetun to selected services if not already present
            if "gluetun" not in self.selected_services:
                self.selected_services.insert(0, "gluetun")

    def _setup_directories_and_files(self) -> bool:
        """Create directories and generate configuration files."""
        # Create directory structure
        success, errors = self.directory_manager.create_directory_structure(
            self.docker_dir, self.media_dir, self.uid, self.gid
        )

        if not success:
            print_error("Failed to create directory structure:")
            for error in errors:
                print_error(f"  - {error}")
            return False

        # Create service-specific directories
        success, errors = self.directory_manager.create_service_directories(
            self.docker_dir, self.selected_services, self.uid, self.gid
        )

        if not success:
            print_warning("Some service directories could not be created:")
            for error in errors:
                print_warning(f"  - {error}")

        # Generate configuration files
        file_results = self.file_generator.generate_all_files(
            self.selected_services,
            self.uid,
            self.gid,
            self.docker_dir,
            self.media_dir,
            self.output_dir,
            self.timezone,
            self.gluetun_configurator,
        )

        # Check file generation results
        failed_files = [name for name, success in file_results.items() if not success]
        if failed_files:
            print_error("Failed to generate some files:")
            for filename in failed_files:
                print_error(f"  - {filename}")
            return False

        # Validate generated files
        validation_errors = self.file_generator.validate_generated_files(
            self.output_dir
        )
        if validation_errors:
            print_warning("File validation issues:")
            for error in validation_errors:
                print_warning(f"  - {error}")

        # Fix any remaining permission issues
        failed_permissions = self.directory_manager.fix_permissions(self.uid, self.gid)
        if failed_permissions:
            print_warning("Could not fix permissions for some directories:")
            for directory in failed_permissions:
                print_warning(f"  - {directory}")

        return True

    def _handle_final_setup(self) -> None:
        """Handle final setup options like starting containers and walkthroughs."""
        print_info(f"Setup files are ready in: {self.output_dir}")
        print_info("Review SETUP_GUIDE.md for detailed configuration instructions")

        # Offer to start containers
        if prompt_yes_no("Start containers now?", default=True):
            self._start_containers()
        else:
            print_info("You can start containers later with: docker compose up -d")

        # Offer walkthrough
        if prompt_yes_no(
            "Would you like an interactive setup walkthrough?", default=False
        ):
            self._interactive_walkthrough()

    def _start_containers(self) -> None:
        """Start Docker containers with error handling."""
        print_info("Starting containers...")

        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=self.output_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode == 0:
                print_success("Containers started successfully!")

                # Test Gluetun connection if enabled
                if (
                    self.gluetun_configurator.enabled
                    and "gluetun" in self.selected_services
                ):
                    self._test_gluetun_connection()

                self._show_access_information()

            else:
                print_error("Failed to start containers:")
                print_error(result.stderr)
                print_info("Check the logs with: docker compose logs")

        except subprocess.TimeoutExpired:
            print_warning("Container startup timed out - they may still be starting")
            print_info("Check status with: docker compose ps")
        except Exception as e:
            print_error(f"Error starting containers: {e}")

    def _test_gluetun_connection(self) -> None:
        """Test Gluetun VPN connection with improved feedback."""
        print_info("Testing VPN connection...")

        success, message = ContainerTester.test_gluetun_connection(timeout=60)

        if success:
            print_success("VPN Connection Test:")
            for line in message.split("\n"):
                if line.strip():
                    print(f"  {line}")
        else:
            print_warning(f"VPN test failed: {message}")
            print_info("Check Gluetun logs with: docker logs gluetun")

    def _show_access_information(self) -> None:
        """Show service access information."""
        services = self.template_loader.get_services()

        print_header("SERVICE ACCESS INFORMATION")

        for service_id in self.selected_services:
            if service_id not in services:
                continue

            service = services[service_id]
            name = service.get("name", service_id.title())
            port = service.get("port")

            if not port:
                continue

            # Adjust port for services routed through VPN
            if (
                service_id == "qbittorrent"
                and self.gluetun_configurator.enabled
                and self.gluetun_configurator.route_qbittorrent
            ):
                access_info = f"http://{self.host_ip}:{port} (via Gluetun)"
            else:
                access_info = f"http://{self.host_ip}:{port}"

            print(f"  {name:15} - {access_info}")

    def _interactive_walkthrough(self) -> None:
        """Interactive setup walkthrough for each service."""
        print_header("INTERACTIVE SETUP WALKTHROUGH")
        print("This will guide you through configuring each service step by step.")
        print("You can skip any step by typing 'skip' when prompted.\n")

        services = self.template_loader.get_services()

        # Sort services by setup priority
        sorted_services = sorted(
            self.selected_services,
            key=lambda x: (
                SETUP_ORDER_PRIORITY.index(x) if x in SETUP_ORDER_PRIORITY else 999
            ),
        )

        for i, service_id in enumerate(sorted_services, 1):
            if service_id not in services:
                continue

            service = services[service_id]
            name = service.get("name", service_id.title())

            print_header(f"STEP {i}/{len(sorted_services)}: {name}")

            # Show service information
            port = service.get("port")
            if port:
                if (
                    service_id == "qbittorrent"
                    and self.gluetun_configurator.enabled
                    and self.gluetun_configurator.route_qbittorrent
                ):
                    print(f"Access URL: http://{self.host_ip}:{port} (via Gluetun)")
                else:
                    print(f"Access URL: http://{self.host_ip}:{port}")

            # Show setup steps
            setup_steps = service.get("setup_steps", [])
            if setup_steps:
                print("\nSetup Steps:")
                for step in setup_steps:
                    # Replace placeholders
                    if self.gluetun_configurator.enabled:
                        qbit_host = (
                            "gluetun"
                            if self.gluetun_configurator.route_qbittorrent
                            else "qbittorrent"
                        )
                        step = step.replace("{qbittorrent_host}", qbit_host)
                    print(f"  • {step}")

            wait_for_done(i, len(sorted_services))

    def _print_completion_message(self) -> None:
        """Print final completion message with summary."""
        self.progress.finish(success=True)

        print_header("SETUP COMPLETE!")
        print("Your media server stack has been configured successfully!")
        print()

        print(f"{Colors.BOLD}Configuration Summary:{Colors.ENDC}")
        print(f"  • Services: {len(self.selected_services)} selected")
        print(f"  • Docker Directory: {self.docker_dir}")
        print(f"  • Media Directory: {self.media_dir}")
        print(f"  • Configuration: {self.output_dir}")

        if self.gluetun_configurator.enabled:
            print(f"\n{Colors.BOLD}VPN Configuration:{Colors.ENDC}")
            print("  • VPN is configured and will start automatically")
            print("  • Test connection: docker exec gluetun wget -qO- ifconfig.me")
            if self.gluetun_configurator.route_qbittorrent:
                print("  • qBittorrent traffic is routed through VPN")
                print("  • *arr apps should use 'gluetun' as qBittorrent host")

        print(f"\n{Colors.BOLD}Next Steps:{Colors.ENDC}")
        print("  1. Review the generated SETUP_GUIDE.md")
        print("  2. Configure each service through its web interface")
        print("  3. Set up your indexers and download paths")
        print("  4. Start adding your media!")

        print(f"\n{Colors.BOLD}Useful Commands:{Colors.ENDC}")
        print("  • View status: docker compose ps")
        print("  • View logs: docker compose logs -f [service_name]")
        print("  • Stop all: docker compose down")
        print("  • Update all: docker compose pull && docker compose up -d")

    def _should_show_debug_info(self) -> bool:
        """Determine if debug information should be shown on errors."""
        return os.environ.get("DEBUG", "").lower() in ["1", "true", "yes"]
