"""
Media Server Setup Script
A user-friendly interactive script to deploy a complete media server stack.

This script reads all configuration and templates from ./templates
"""

import os
import secrets
import string
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)


# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
TEMPLATES_DIR = SCRIPT_DIR / "templates"


# ============================================================================
# TEMPLATE LOADER
# ============================================================================


class TemplateLoader:
    """Handles loading and rendering of external template files."""

    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self._services: Dict[str, Any] = {}
        self._categories: Dict[str, str] = {}
        self._loaded: bool = False

    def load_template(self, filename: str) -> str:
        """Load a template file and return its contents."""
        filepath = self.templates_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Template not found: {filepath}")
        return filepath.read_text(encoding="utf-8")

    def render_template(self, filename: str, **kwargs: Any) -> str:
        """Load a template and substitute placeholders."""
        template = self.load_template(filename)
        return template.format(**kwargs)

    def _load_yaml_data(self) -> None:
        """Load and cache YAML data from docker-services.yaml."""
        if self._loaded:
            return

        yaml_path = self.templates_dir / "docker-services.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"Services config not found: {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._services = data.get("services", {}) if data else {}
        self._categories = data.get("categories", {}) if data else {}
        self._loaded = True

    def get_services(self) -> Dict[str, Any]:
        """Get service definitions from YAML."""
        self._load_yaml_data()
        return self._services

    def get_categories(self) -> Dict[str, str]:
        """Get category definitions from YAML."""
        self._load_yaml_data()
        return self._categories


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_header(text: str) -> None:
    """Print a formatted header."""
    width = 60
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(width)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * width}{Colors.ENDC}\n")


def print_success(text: str) -> None:
    print(f"{Colors.GREEN}[OK] {text}{Colors.ENDC}")


def print_warning(text: str) -> None:
    print(f"{Colors.YELLOW}[WARN] {text}{Colors.ENDC}")


def print_error(text: str) -> None:
    print(f"{Colors.RED}[ERROR] {text}{Colors.ENDC}")


def print_info(text: str) -> None:
    print(f"{Colors.BLUE}[INFO] {text}{Colors.ENDC}")


def prompt(message: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    if default:
        user_input = input(f"{Colors.BOLD}{message}{Colors.ENDC} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{Colors.BOLD}{message}{Colors.ENDC}: ").strip()


def prompt_yes_no(message: str, default: bool = True) -> bool:
    """Prompt user for yes/no input."""
    default_str = "Y/n" if default else "y/N"
    response = (
        input(f"{Colors.BOLD}{message}{Colors.ENDC} [{default_str}]: ").strip().lower()
    )
    if not response:
        return default
    return response in ("y", "yes")


def wait_for_done(step_num: int, total_steps: int) -> None:
    """Wait for user to type 'done' to proceed."""
    while True:
        response = (
            input(
                f"\n{Colors.YELLOW}[Step {step_num}/{total_steps}] "
                f"Type 'done' to proceed, 'skip' to skip: {Colors.ENDC}"
            )
            .strip()
            .lower()
        )
        if response in ("done", "skip", "d", "s"):
            break
        print("Please type 'done' or 'skip'")


def run_command(
    cmd: List[str], sudo: bool = False, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a shell command."""
    if sudo:
        cmd = ["sudo"] + cmd
    try:
        return subprocess.run(cmd, check=check, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed: {' '.join(cmd)}")
        print_error(f"Error: {e.stderr}")
        raise


def generate_encryption_key(length: int = 64) -> str:
    """Generate a random encryption key."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_timezone() -> str:
    """Get the system timezone."""
    try:
        with open("/etc/timezone", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "UTC"


# ============================================================================
# GUIDE GENERATOR
# ============================================================================


class GuideGenerator:
    """Generates the setup guide from templates."""

    def __init__(self, loader: TemplateLoader):
        self.loader = loader

    def generate(
        self,
        selected_services: List[str],
        username: str,
        uid: int,
        gid: int,
        docker_dir: Path,
        media_dir: Path,
        output_dir: Path,
        timezone: str,
    ) -> str:
        """Generate the complete setup guide."""
        services = self.loader.get_services()

        # Build service URL table
        service_table_lines = []
        for service_id in selected_services:
            svc = services[service_id]
            url = svc.get("setup_url") or "(no web UI)"
            port = svc["port"]
            service_table_lines.append(f"| {svc['name']} | {url} | {port} |")
        service_table_lines.append("| Watchtower | (auto-updates containers) | - |")
        service_table = "\n".join(service_table_lines)

        # Build service directory tree
        service_dirs_lines = []
        for service_id in selected_services:
            service_dirs_lines.append(f"├── {service_id}/")
            service_dirs_lines.append(f"│   └── config/")
        service_dirs = "\n".join(service_dirs_lines)

        # Render header
        header = self.loader.render_template(
            "setup-guide-header.md",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            username=username,
            uid=uid,
            gid=gid,
            docker_dir=docker_dir,
            media_dir=media_dir,
            output_dir=output_dir,
            timezone=timezone,
            service_table=service_table,
        )

        # Build service sections
        service_sections = []
        for service_id in selected_services:
            svc = services[service_id]
            section = self._build_service_section(svc)
            service_sections.append(section)

        # Render footer
        footer = self.loader.render_template(
            "setup-guide-footer.md",
            docker_dir=docker_dir,
            media_dir=media_dir,
            service_dirs=service_dirs,
        )

        # Combine all parts
        return header + "\n".join(service_sections) + "\n" + footer

    def _build_service_section(self, service: Dict[str, Any]) -> str:
        """Build markdown section for a single service."""
        lines = [
            f"### {service['name']}",
            "",
            f"**Description:** {service['description']}",
            "",
        ]

        if service.get("setup_url"):
            lines.append(f"**URL:** {service['setup_url']}")
            lines.append("")

        lines.append("**Setup Steps:**")
        lines.append("")

        for i, step in enumerate(service.get("setup_steps", []), 1):
            lines.append(f"{i}. {step}")

        lines.extend(["", "---", ""])

        return "\n".join(lines)


# ============================================================================
# DOCKER COMPOSE GENERATOR
# ============================================================================


class ComposeGenerator:
    """Generates docker-compose.yml from service definitions."""

    def __init__(self, loader: TemplateLoader):
        self.loader = loader

    def generate(
        self,
        selected_services: List[str],
        uid: int,
        gid: int,
        docker_dir: Path,
        media_dir: Path,
        timezone: str,
        encryption_key: str = "",
    ) -> str:
        """Generate docker-compose.yml content."""
        services = self.loader.get_services()

        lines = ["---", "services:", ""]

        for service_id in selected_services:
            svc = services[service_id]
            lines.extend(
                self._build_service_block(
                    service_id,
                    svc,
                    uid,
                    gid,
                    docker_dir,
                    media_dir,
                    timezone,
                    encryption_key,
                )
            )

        # Add Watchtower
        lines.extend(self._build_watchtower_block(timezone))

        # Add network
        lines.extend(["", "networks:", "  media-network:", "    driver: bridge"])

        return "\n".join(lines)

    def _build_service_block(
        self,
        service_id: str,
        svc: Dict[str, Any],
        uid: int,
        gid: int,
        docker_dir: Path,
        media_dir: Path,
        timezone: str,
        encryption_key: str,
    ) -> List[str]:
        """Build docker-compose block for a single service."""
        lines = [
            f"  {service_id}:",
            f"    image: {svc['image']}",
            f"    container_name: {service_id}",
            "    restart: unless-stopped",
        ]

        # Environment
        env_lines = []
        for e in svc.get("env", []):
            if e == "PUID":
                env_lines.append(f"      - PUID={uid}")
            elif e == "PGID":
                env_lines.append(f"      - PGID={gid}")
            elif e == "TZ":
                env_lines.append(f"      - TZ={timezone}")
            elif e == "SECRET_ENCRYPTION_KEY":
                env_lines.append(f"      - SECRET_ENCRYPTION_KEY={encryption_key}")
            else:
                env_lines.append(f"      - {e}")

        if env_lines:
            lines.append("    environment:")
            lines.extend(env_lines)

        # Volumes
        volume_lines = []
        for container_path, vol_name in svc.get("volumes", {}).items():
            host_path = docker_dir / service_id / vol_name
            volume_lines.append(f"      - {host_path}:{container_path}")

        for container_path, vol_name in svc.get("media_volumes", {}).items():
            host_path = media_dir / vol_name
            volume_lines.append(f"      - {host_path}:{container_path}")

        for container_path, host_path in svc.get("extra_volumes", {}).items():
            volume_lines.append(f"      - {host_path}:{container_path}")

        if volume_lines:
            lines.append("    volumes:")
            lines.extend(volume_lines)

        # Ports
        port_lines = [f"      - '{svc['port']}:{svc['port']}'"]
        for extra_port in svc.get("extra_ports", []):
            port_lines.append(f"      - '{extra_port}:{extra_port}'")
            port_lines.append(f"      - '{extra_port}:{extra_port}/udp'")

        lines.append("    ports:")
        lines.extend(port_lines)

        lines.append("    networks:")
        lines.append("      - media-network")
        lines.append("")

        return lines

    def _build_watchtower_block(self, timezone: str) -> List[str]:
        """Build Watchtower service block."""
        return [
            "  watchtower:",
            "    image: containrrr/watchtower:latest",
            "    container_name: watchtower",
            "    restart: unless-stopped",
            "    environment:",
            f"      - TZ={timezone}",
            "      - WATCHTOWER_CLEANUP=true",
            "      - WATCHTOWER_SCHEDULE=0 0 5 * * *",
            "    volumes:",
            "      - /var/run/docker.sock:/var/run/docker.sock",
            "    networks:",
            "      - media-network",
        ]


# ============================================================================
# MAIN SETUP CLASS
# ============================================================================


class MediaServerSetup:
    """Main setup orchestrator."""

    def __init__(self) -> None:
        self.loader = TemplateLoader(TEMPLATES_DIR)
        self.guide_gen = GuideGenerator(self.loader)
        self.compose_gen = ComposeGenerator(self.loader)

        self.username: str = ""
        self.uid: int = 0
        self.gid: int = 0
        self.docker_dir: Path = Path("/opt/docker")
        self.media_dir: Path = Path("/srv/media")
        self.selected_services: List[str] = []
        self.timezone: str = get_timezone()
        self.encryption_key: str = ""
        self.output_dir: Path = Path.cwd() / "output"

    def run(self) -> None:
        """Run the complete setup process."""
        try:
            self._validate_templates()
            self._print_welcome()
            self._check_prerequisites()
            self._setup_user()
            self._setup_directories()
            self._select_services()
            self._generate_files()
            self._setup_permissions()
            self._offer_walkthrough()
            self._print_congratulations()
        except KeyboardInterrupt:
            print("\n\nSetup cancelled by user.")
            sys.exit(1)
        except Exception as e:
            print_error(f"Setup failed: {e}")
            raise

    def _validate_templates(self) -> None:
        """Ensure all required template files exist."""
        required = [
            "setup-guide-header.md",
            "setup-guide-footer.md",
            "docker-services.yaml",
        ]
        missing = [f for f in required if not (TEMPLATES_DIR / f).exists()]

        if missing:
            print_error(f"Missing template files in {TEMPLATES_DIR}:")
            for f in missing:
                print_error(f"  - {f}")
            sys.exit(1)

    def _print_welcome(self) -> None:
        """Print welcome message."""
        print_header("MEDIA SERVER SETUP")
        print("Welcome to the Media Server Setup Script!\n")
        print("This script will help you set up a complete media server with:")
        print("  - Media servers (Jellyfin, Plex)")
        print("  - *Arr suite for media management")
        print("  - Download clients and indexers")
        print("  - Companion apps and dashboards\n")
        print(
            f"{Colors.YELLOW}Note: This script requires sudo privileges.{Colors.ENDC}\n"
        )

        if not prompt_yes_no("Ready to begin?"):
            print("Setup cancelled.")
            sys.exit(0)

    def _check_prerequisites(self) -> None:
        """Check that required software is installed."""
        print_header("CHECKING PREREQUISITES")

        # Check Docker
        try:
            result = run_command(["docker", "--version"], check=False)
            if result.returncode == 0:
                print_success(f"Docker found: {result.stdout.strip()}")
            else:
                raise FileNotFoundError
        except FileNotFoundError:
            print_error("Docker is not installed!")
            print_info("Install Docker: https://docs.docker.com/engine/install/")
            sys.exit(1)

        # Check Docker Compose
        try:
            result = run_command(["docker", "compose", "version"], check=False)
            if result.returncode == 0:
                print_success(f"Docker Compose found: {result.stdout.strip()}")
            else:
                raise FileNotFoundError
        except FileNotFoundError:
            print_error("Docker Compose V2 is not installed!")
            sys.exit(1)

        print_success("All prerequisites met!")

    def _setup_user(self) -> None:
        """Set up the user for running services."""
        print_header("USER SETUP")

        print("We need a user account to run the media server services.\n")

        create_new = prompt_yes_no("Create a new user?", default=True)

        if create_new:
            while True:
                self.username = prompt("Enter username for the new user", "mediaserver")

                if not all(c.isalnum() or c == "_" for c in self.username):
                    print_error(
                        "Username must contain only letters, numbers, and underscores"
                    )
                    continue

                result = run_command(["id", self.username], check=False)
                if result.returncode == 0:
                    print_warning(f"User '{self.username}' already exists.")
                    if prompt_yes_no("Use this existing user?"):
                        break
                    continue

                print_info(f"Creating user '{self.username}'...")
                try:
                    run_command(
                        ["useradd", "-m", "-s", "/bin/bash", self.username], sudo=True
                    )
                    run_command(["usermod", "-aG", "docker", self.username], sudo=True)
                    print_success(f"User '{self.username}' created!")
                    break
                except subprocess.CalledProcessError:
                    print_error(f"Failed to create user '{self.username}'")
                    continue
        else:
            while True:
                self.username = prompt("Enter existing username")
                result = run_command(["id", self.username], check=False)
                if result.returncode == 0:
                    run_command(
                        ["usermod", "-aG", "docker", self.username],
                        sudo=True,
                        check=False,
                    )
                    print_success(f"User '{self.username}' configured!")
                    break
                print_error(f"User '{self.username}' does not exist.")

        result = run_command(["id", "-u", self.username])
        self.uid = int(result.stdout.strip())
        result = run_command(["id", "-g", self.username])
        self.gid = int(result.stdout.strip())

        print_info(f"User: {self.username} (UID: {self.uid}, GID: {self.gid})")

    def _setup_directories(self) -> None:
        """Set up directory structure."""
        print_header("DIRECTORY SETUP")

        print(
            f"{Colors.YELLOW}IMPORTANT:{Colors.ENDC} The Docker directory stores container"
        )
        print(
            f"configurations. This is {Colors.BOLD}NOT{Colors.ENDC} where media files go!\n"
        )

        docker_dir_input = prompt(
            "Docker configuration directory", str(self.docker_dir)
        )
        self.docker_dir = Path(docker_dir_input).resolve()

        print(f"\n{Colors.CYAN}Media Directory:{Colors.ENDC}")
        print("This is where your actual media files will be stored.\n")

        media_dir_input = prompt("Media storage directory", str(self.media_dir))
        self.media_dir = Path(media_dir_input).resolve()

        print_info("Creating directory structure...")

        directories = [
            self.docker_dir / "compose",
            self.media_dir / "downloads" / "incomplete",
            self.media_dir / "downloads" / "complete",
            self.media_dir / "movies",
            self.media_dir / "tv",
            self.media_dir / "music",
            self.media_dir / "books",
            self.media_dir / "comics",
            self.media_dir / "audiobooks",
            self.media_dir / "podcasts",
        ]

        for directory in directories:
            try:
                run_command(["mkdir", "-p", str(directory)], sudo=True)
            except subprocess.CalledProcessError:
                print_warning(f"Could not create {directory}")

        run_command(
            ["chown", "-R", f"{self.uid}:{self.gid}", str(self.docker_dir)], sudo=True
        )
        run_command(
            ["chown", "-R", f"{self.uid}:{self.gid}", str(self.media_dir)], sudo=True
        )

        print_success("Directories created!")
        self.output_dir = self.docker_dir / "compose"

    def _select_services(self) -> None:
        """Let user select which services to install."""
        print_header("SERVICE SELECTION")
        print("Select the services you want to install.\n")

        services = self.loader.get_services()
        categories = self.loader.get_categories()

        # Default selections for standard yes/no services
        defaults = ["sonarr", "radarr", "qbittorrent", "seerr"]

        # Services that are mutually exclusive (user picks one or none)
        exclusive_choices = [
            {
                "name": "Media Server",
                "options": ["jellyfin", "plex", "emby"],
                "default": 1,  # Jellyfin
            },
            {
                "name": "Indexer Manager",
                "options": ["prowlarr", "jackett"],
                "default": 1,  # Prowlarr
            },
            {
                "name": "Download Client (Usenet)",
                "options": ["sabnzbd", "nzbget"],
                "default": 1,
            },
        ]

        # Track which services we've already handled
        handled_services: set = set()

        # Handle mutually exclusive choices first
        for group in exclusive_choices:
            available = [s for s in group["options"] if s in services]
            if not available:
                continue

            print(f"\n{Colors.BOLD}=== {group['name']} ==={Colors.ENDC}")
            print(f"\nWhich {group['name'].lower()} would you like to use?")

            for i, service_id in enumerate(available, 1):
                svc = services[service_id]
                default_marker = " (default)" if i == group["default"] else ""
                print(
                    f"  {i}. {svc['name']} (port {svc['port']}) - "
                    f"{svc['description']}{default_marker}"
                )
            print(f"  {len(available) + 1}. None - skip")

            while True:
                choice = prompt(
                    f"Enter choice (1-{len(available) + 1})",
                    str(group["default"]),
                )
                try:
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(available):
                        selected_id = available[choice_num - 1]
                        self.selected_services.append(selected_id)
                        print_success(f"    {services[selected_id]['name']} selected")
                        break
                    elif choice_num == len(available) + 1:
                        print_info(f"    No {group['name'].lower()} selected")
                        break
                    else:
                        print_error(f"Please enter 1-{len(available) + 1}")
                except ValueError:
                    print_error("Please enter a valid number")

            # Mark all options in this group as handled
            handled_services.update(group["options"])

        # Handle remaining services by category
        # Group remaining services by category
        categorized: Dict[str, List[tuple]] = {}
        for service_id, svc in services.items():
            if service_id in handled_services:
                continue  # Skip already-handled exclusive services
            cat = svc["category"]
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append((service_id, svc))

        for cat_id, cat_name in categories.items():
            if cat_id not in categorized:
                continue

            print(f"\n{Colors.BOLD}=== {cat_name} ==={Colors.ENDC}")

            for service_id, svc in categorized[cat_id]:
                is_default = service_id in defaults
                if prompt_yes_no(
                    f"  {svc['name']} (port {svc['port']}) - {svc['description']}?",
                    default=is_default,
                ):
                    self.selected_services.append(service_id)
                    print_success(f"    {svc['name']} selected")

        if not self.selected_services:
            print_error("No services selected!")
            sys.exit(1)

        print(f"\n{Colors.GREEN}Selected services:{Colors.ENDC}")
        for service_id in self.selected_services:
            print(f"  - {services[service_id]['name']}")

    def _generate_files(self) -> None:
        """Generate all configuration files."""
        print_header("GENERATING FILES")

        services = self.loader.get_services()

        # Check if encryption key needed
        for service_id in self.selected_services:
            if services[service_id].get("needs_encryption_key"):
                self.encryption_key = generate_encryption_key()
                break

        # Create service directories
        for service_id in self.selected_services:
            svc = services[service_id]
            for vol_name in svc.get("volumes", {}).values():
                dir_path = self.docker_dir / service_id / vol_name
                run_command(["mkdir", "-p", str(dir_path)], sudo=True)

        # Generate docker-compose.yml
        compose_content = self.compose_gen.generate(
            self.selected_services,
            self.uid,
            self.gid,
            self.docker_dir,
            self.media_dir,
            self.timezone,
            self.encryption_key,
        )
        compose_path = self.output_dir / "docker-compose.yml"
        compose_path.parent.mkdir(parents=True, exist_ok=True)
        compose_path.write_text(compose_content, encoding="utf-8")
        run_command(["chown", f"{self.uid}:{self.gid}", str(compose_path)], sudo=True)
        print_success(f"Created {compose_path}")

        # Generate .env
        env_lines = [
            "# Media Server Environment Configuration",
            f"# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"PUID={self.uid}",
            f"PGID={self.gid}",
            f"TZ={self.timezone}",
            f"DOCKER_DIR={self.docker_dir}",
            f"MEDIA_DIR={self.media_dir}",
        ]
        if self.encryption_key:
            env_lines.append(f"SECRET_ENCRYPTION_KEY={self.encryption_key}")

        env_path = self.output_dir / ".env"
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        run_command(["chown", f"{self.uid}:{self.gid}", str(env_path)], sudo=True)
        run_command(["chmod", "600", str(env_path)], sudo=True)
        print_success(f"Created {env_path}")

        # Generate setup guide
        guide_content = self.guide_gen.generate(
            self.selected_services,
            self.username,
            self.uid,
            self.gid,
            self.docker_dir,
            self.media_dir,
            self.output_dir,
            self.timezone,
        )
        guide_path = self.output_dir / "SETUP_GUIDE.md"
        guide_path.write_text(guide_content, encoding="utf-8")
        run_command(["chown", f"{self.uid}:{self.gid}", str(guide_path)], sudo=True)
        print_success(f"Created {guide_path}")

    def _setup_permissions(self) -> None:
        """Set up proper permissions."""
        print_header("SETTING PERMISSIONS")

        run_command(
            ["chown", "-R", f"{self.uid}:{self.gid}", str(self.docker_dir)], sudo=True
        )
        run_command(
            ["chown", "-R", f"{self.uid}:{self.gid}", str(self.media_dir)], sudo=True
        )
        run_command(["chmod", "-R", "755", str(self.docker_dir)], sudo=True)
        run_command(["chmod", "-R", "755", str(self.media_dir)], sudo=True)

        print_success("Permissions configured!")

    def _offer_walkthrough(self) -> None:
        """Offer interactive setup walkthrough."""
        print_header("SETUP WALKTHROUGH")

        print("Your configuration files have been generated!\n")
        print("  1. Follow interactive setup in terminal")
        print(f"  2. Read the guide at: {self.output_dir / 'SETUP_GUIDE.md'}")
        print("  3. Skip and start containers manually\n")

        choice = prompt("Choose an option (1/2/3)", "1")

        if choice == "3":
            print_info(f"To start: cd {self.output_dir} && docker compose up -d")
            return

        if choice == "2":
            print_info(f"Guide saved to: {self.output_dir / 'SETUP_GUIDE.md'}")
            if prompt_yes_no("Start the containers now?"):
                self._start_containers()
            return

        self._interactive_walkthrough()

    def _start_containers(self) -> None:
        """Pull images and start Docker containers with progress display."""
        print_info("Pulling Docker images...\n")

        services = self.loader.get_services()

        # Build list of images to track
        images_to_pull: Dict[str, str] = {}  # image -> service name
        for service_id in self.selected_services:
            svc = services[service_id]
            images_to_pull[svc["image"]] = svc["name"]

        # Add Watchtower
        images_to_pull["containrrr/watchtower:latest"] = "Watchtower"

        # Track status for each image
        image_status: Dict[str, str] = {img: "Waiting" for img in images_to_pull}

        def print_progress() -> None:
            """Print current status of all images."""
            # Move cursor up and clear lines (ANSI escape codes)
            lines = len(images_to_pull) + 2
            print(f"\033[{lines}A", end="")  # Move up

            print(
                f"{Colors.BOLD}{'Service':<20} {'Image':<45} {'Status':<15}{Colors.ENDC}"
            )
            print("-" * 80)

            for image, name in images_to_pull.items():
                status = image_status.get(image, "Waiting")

                # Color-code status
                if status == "Done":
                    status_display = f"{Colors.GREEN}✓ Done{Colors.ENDC}"
                elif status == "Pulling":
                    status_display = f"{Colors.CYAN}⟳ Pulling...{Colors.ENDC}"
                elif status == "Exists":
                    status_display = f"{Colors.GREEN}✓ Exists{Colors.ENDC}"
                elif "Error" in status:
                    status_display = f"{Colors.RED}✗ Error{Colors.ENDC}"
                else:
                    status_display = f"{Colors.YELLOW}○ Waiting{Colors.ENDC}"

                # Truncate image name if too long
                image_short = image[:43] + ".." if len(image) > 45 else image
                print(f"{name:<20} {image_short:<45} {status_display:<15}")

        # Print initial status
        print("\n" * (len(images_to_pull) + 2))  # Make room
        print_progress()

        # Run docker compose pull and parse output
        try:
            os.chdir(self.output_dir)

            process = subprocess.Popen(
                ["docker", "compose", "pull"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            if process.stdout:
                for line in process.stdout:
                    line = line.strip()

                    # Parse Docker Compose pull output
                    # Format: " Container image Pulling" or " Container image Pulled"
                    for image in images_to_pull:
                        image_short = image.split("/")[
                            -1
                        ]  # Get just the image:tag part

                        if image_short in line or image in line:
                            if "Pulling" in line:
                                image_status[image] = "Pulling"
                            elif "Pulled" in line or "Downloaded" in line:
                                image_status[image] = "Done"
                            elif (
                                "exists" in line.lower() or "up to date" in line.lower()
                            ):
                                image_status[image] = "Exists"
                            elif "error" in line.lower():
                                image_status[image] = "Error"

                            print_progress()
                            break

            process.wait()

            # Mark any remaining as done (already existed)
            for image in images_to_pull:
                if image_status[image] == "Waiting":
                    image_status[image] = "Exists"
            print_progress()

            if process.returncode != 0:
                print_error("\nSome images failed to pull. Check the errors above.")
                return

            print(f"\n{Colors.GREEN}All images pulled successfully!{Colors.ENDC}\n")

        except Exception as e:
            print_error(f"Failed to pull images: {e}")
            return

        # Start containers
        print_info("Starting containers...")
        try:
            result = run_command(["docker", "compose", "up", "-d"], check=False)
            if result.returncode == 0:
                print_success("All containers started!")
                print_info("Waiting for services to initialize...")
                import time

                time.sleep(10)
            else:
                print_error(f"Failed to start containers: {result.stderr}")
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to start containers: {e}")

    def _interactive_walkthrough(self) -> None:
        """Run interactive setup walkthrough."""
        print_header("INTERACTIVE SETUP")

        if prompt_yes_no("Start the containers now?"):
            self._start_containers()
        else:
            print_warning("Containers not started.")
            return

        services = self.loader.get_services()

        # Determine setup order
        order_priority = [
            "gluetun",
            "qbittorrent",
            "prowlarr",
            "jackett",
            "radarr",
            "sonarr",
            "lidarr",
            "mylar3",
            "bazarr",
            "audiobookshelf",
            "jellyfin",
            "plex",
            "emby",
            "seerr",
            "tautulli",
            "nzbget",
            "sabnzbd",
            "homarr",
            "flaresolverr",
        ]

        setup_order = [s for s in order_priority if s in self.selected_services]
        for s in self.selected_services:
            if s not in setup_order:
                setup_order.append(s)

        total = len(setup_order)

        for i, service_id in enumerate(setup_order, 1):
            svc = services[service_id]

            print(f"\n{'=' * 60}")
            print(f"{Colors.BOLD}{Colors.CYAN}[{i}/{total}] {svc['name']}{Colors.ENDC}")
            print("=" * 60)

            if svc.get("setup_url"):
                print(f"\n{Colors.GREEN}Open: {svc['setup_url']}{Colors.ENDC}\n")
            else:
                print(f"\n{Colors.YELLOW}(No web interface){Colors.ENDC}\n")

            print(f"{Colors.BOLD}Setup Steps:{Colors.ENDC}\n")
            for j, step in enumerate(svc.get("setup_steps", []), 1):
                print(f"  {j}. {step}")

            wait_for_done(i, total)

        print_success("All services configured!")

    def _print_congratulations(self) -> None:
        """Print congratulations message."""
        print_header("CONGRATULATIONS!")

        services = self.loader.get_services()

        print(f"{Colors.GREEN}Your media server has been set up!{Colors.ENDC}\n")

        print(f"{Colors.BOLD}Quick Reference:{Colors.ENDC}")
        for service_id in self.selected_services:
            svc = services[service_id]
            if svc.get("setup_url"):
                print(f"  - {svc['name']}: {svc['setup_url']}")

        print(f"\n{Colors.BOLD}Files Created:{Colors.ENDC}")
        print(f"  - Docker Compose: {self.output_dir / 'docker-compose.yml'}")
        print(f"  - Environment:    {self.output_dir / '.env'}")
        print(f"  - Setup Guide:    {self.output_dir / 'SETUP_GUIDE.md'}")

        print(f"\n{Colors.BOLD}Commands:{Colors.ENDC}")
        print(f"  - Start:  cd {self.output_dir} && docker compose up -d")
        print(f"  - Stop:   cd {self.output_dir} && docker compose down")
        print(f"  - Logs:   cd {self.output_dir} && docker compose logs -f")

        print(f"\n{Colors.GREEN}Enjoy your media server!{Colors.ENDC}\n")


# ============================================================================
# MAIN
# ============================================================================


def main():
    setup = MediaServerSetup()
    setup.run()


if __name__ == "__main__":
    main()
