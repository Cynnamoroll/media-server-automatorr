"""
Media Server Setup Script
A user-friendly interactive script to deploy a complete media server stack.

This script reads all configuration and templates from ./templates
"""

import os
import re
import secrets
import socket
import string
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
# VPN PROVIDER DEFINITIONS
# ============================================================================

VPN_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "nordvpn": {
        "name": "NordVPN",
        "provider_name": "nordvpn",
        "supports_openvpn": True,
        "supports_wireguard": True,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": ["WIREGUARD_PRIVATE_KEY"],
        "credentials_url": "https://my.nordaccount.com/dashboard/nordvpn/manual-configuration/service-credentials/",
        "credentials_note": "Use your SERVICE CREDENTIALS (not your email/password). Get them from your NordVPN account dashboard.",
    },
    "mullvad": {
        "name": "Mullvad",
        "provider_name": "mullvad",
        "supports_openvpn": True,
        "supports_wireguard": True,
        "openvpn_fields": ["OPENVPN_USER"],
        "wireguard_fields": ["WIREGUARD_PRIVATE_KEY", "WIREGUARD_ADDRESSES"],
        "credentials_url": "https://mullvad.net/en/account/#/wireguard-config",
        "credentials_note": "For OpenVPN, use your account number. For WireGuard, generate a config file to get your private key and address.",
    },
    "protonvpn": {
        "name": "ProtonVPN",
        "provider_name": "protonvpn",
        "supports_openvpn": True,
        "supports_wireguard": True,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": ["WIREGUARD_PRIVATE_KEY"],
        "credentials_url": "https://account.proton.me/u/0/vpn/OpenVpnIKEv2",
        "wireguard_url": "https://account.proton.me/u/0/vpn/WireGuard",
        "credentials_note": "Use your OpenVPN/IKEv2 credentials (NOT your Proton account password).",
    },
    "surfshark": {
        "name": "Surfshark",
        "provider_name": "surfshark",
        "supports_openvpn": True,
        "supports_wireguard": True,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": ["WIREGUARD_PRIVATE_KEY", "WIREGUARD_ADDRESSES"],
        "credentials_url": "https://my.surfshark.com/vpn/manual-setup/main",
        "credentials_note": "Find credentials in: VPN → Manual setup → Credentials (OpenVPN) or generate WireGuard keypair.",
    },
    "private internet access": {
        "name": "Private Internet Access (PIA)",
        "provider_name": "private internet access",
        "supports_openvpn": True,
        "supports_wireguard": False,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": [],
        "credentials_url": "https://www.privateinternetaccess.com/account/client-control-panel",
        "credentials_note": "Use your PIA username and password.",
    },
    "expressvpn": {
        "name": "ExpressVPN",
        "provider_name": "expressvpn",
        "supports_openvpn": True,
        "supports_wireguard": False,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": [],
        "credentials_url": "https://www.expressvpn.com/setup",
        "credentials_note": "Get your manual configuration credentials from the ExpressVPN setup page.",
    },
    "ivpn": {
        "name": "IVPN",
        "provider_name": "ivpn",
        "supports_openvpn": True,
        "supports_wireguard": True,
        "openvpn_fields": ["OPENVPN_USER"],
        "wireguard_fields": ["WIREGUARD_PRIVATE_KEY", "WIREGUARD_ADDRESSES"],
        "credentials_url": "https://www.ivpn.net/account/",
        "credentials_note": "For OpenVPN, use your account ID (i-xxxx-xxxx-xxxx). For WireGuard, generate keys in your account.",
    },
    "windscribe": {
        "name": "Windscribe",
        "provider_name": "windscribe",
        "supports_openvpn": True,
        "supports_wireguard": True,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": [
            "WIREGUARD_PRIVATE_KEY",
            "WIREGUARD_ADDRESSES",
            "WIREGUARD_PRESHARED_KEY",
        ],
        "credentials_url": "https://fra.windscribe.com/getconfig/openvpn",
        "wireguard_url": "https://fra.windscribe.com/getconfig/wireguard",
        "credentials_note": "Generate config files from Windscribe to get your credentials.",
    },
    "cyberghost": {
        "name": "CyberGhost",
        "provider_name": "cyberghost",
        "supports_openvpn": True,
        "supports_wireguard": False,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": [],
        "credentials_url": "https://my.cyberghostvpn.com/",
        "credentials_note": "Get your manual configuration credentials from your CyberGhost account.",
    },
    "torguard": {
        "name": "TorGuard",
        "provider_name": "torguard",
        "supports_openvpn": True,
        "supports_wireguard": True,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": ["WIREGUARD_PRIVATE_KEY", "WIREGUARD_ADDRESSES"],
        "credentials_url": "https://torguard.net/clientarea.php",
        "credentials_note": "Use your TorGuard VPN credentials.",
    },
    "vyprvpn": {
        "name": "VyprVPN",
        "provider_name": "vyprvpn",
        "supports_openvpn": True,
        "supports_wireguard": False,
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": [],
        "credentials_url": "https://www.vyprvpn.com/",
        "credentials_note": "Use your VyprVPN account email and password.",
    },
}

# Fields that are optional (can be empty)
OPTIONAL_CREDENTIAL_FIELDS = {"OPENVPN_PASSWORD", "WIREGUARD_PRESHARED_KEY"}


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
    DIM = "\033[2m"


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


def print_link(text: str, url: str) -> None:
    """Print a clickable link (terminals that support it will make it clickable)."""
    print(f"{Colors.CYAN}  → {text}: {Colors.ENDC}{url}")


def prompt(message: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    if default:
        user_input = input(f"{Colors.BOLD}{message}{Colors.ENDC} [{default}]: ").strip()
        return user_input if user_input else default
    return input(f"{Colors.BOLD}{message}{Colors.ENDC}: ").strip()


def prompt_secret(message: str) -> str:
    """Prompt user for sensitive input (passwords, keys)."""
    import getpass

    try:
        return getpass.getpass(f"{Colors.BOLD}{message}{Colors.ENDC}: ")
    except Exception:
        # Fallback if getpass doesn't work (e.g., some IDEs)
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


def get_local_network_ip() -> str:
    """Get the device's IP address on the local network."""
    # Method 1: Try using ip command (most reliable on Linux)
    try:
        result = subprocess.run(
            ["ip", "route", "get", "1"], capture_output=True, text=True, check=True
        )
        parts = result.stdout.split("src ")
        if len(parts) > 1:
            ip = parts[1].split()[0]
            if ip and not ip.startswith("127."):
                return ip
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError):
        pass

    # Method 2: Try hostname -I
    try:
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, check=True
        )
        ips = result.stdout.strip().split()
        for ip in ips:
            if ip and not ip.startswith("127.") and ":" not in ip:
                return ip
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Method 3: Try ifconfig (fallback for older systems)
    try:
        result = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, check=True
        )
        matches = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
        for ip in matches:
            if not ip.startswith("127."):
                return ip
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Method 4: Python socket method (last resort)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "localhost"


def replace_placeholders(text: str, replacements: Dict[str, str]) -> str:
    """Replace placeholders in text with values from replacements dict."""
    result = text
    for key, value in replacements.items():
        result = result.replace(f"{{{key}}}", value)
    return result


# ============================================================================
# GLUETUN CONFIGURATOR
# ============================================================================


class GluetunConfigurator:
    """Handles interactive Gluetun VPN configuration."""

    def __init__(self):
        self.enabled: bool = False
        self.provider: Optional[str] = None
        self.vpn_type: str = "openvpn"
        self.credentials: Dict[str, str] = {}
        self.server_countries: str = ""
        self.route_qbittorrent: bool = False

    def configure(self) -> bool:
        """Run interactive Gluetun configuration. Returns True if configured."""
        print_header("VPN CONFIGURATION (GLUETUN)")

        print("Gluetun routes your download traffic through a VPN for privacy.")
        print("This is optional but recommended for torrent downloads.\n")

        if not prompt_yes_no("Would you like to configure a VPN?", default=False):
            print_info("Skipping VPN configuration.")
            self.enabled = False
            return False

        self.enabled = True

        # Select provider
        self._select_provider()

        # Select VPN type (skip for custom)
        if self.provider != "custom":
            self._select_vpn_type()

        # Collect credentials (skip for custom)
        if self.provider != "custom":
            self._collect_credentials()

        # Optional: Server location (skip for custom)
        if self.provider != "custom":
            self._configure_server_location()

        # Route qBittorrent through VPN
        self._configure_qbittorrent_routing()

        print_success("VPN configuration complete!")
        return True

    def _select_provider(self) -> None:
        """Let user select their VPN provider."""
        print(f"\n{Colors.BOLD}Select your VPN provider:{Colors.ENDC}\n")

        providers = list(VPN_PROVIDERS.items())
        for i, (key, provider) in enumerate(providers, 1):
            print(f"  {i:2}. {provider['name']}")

        print(f"  {len(providers) + 1:2}. Other (manual configuration)")

        while True:
            choice = prompt("\nEnter your choice", "1")
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= len(providers):
                    self.provider = providers[choice_num - 1][0]
                    provider_info = VPN_PROVIDERS[self.provider]
                    print_success(f"Selected: {provider_info['name']}")
                    return
                elif choice_num == len(providers) + 1:
                    print_warning("Manual configuration selected.")
                    print_info(
                        "You'll need to edit docker-compose.yml manually after setup."
                    )
                    print_link(
                        "Gluetun Wiki",
                        "https://github.com/qdm12/gluetun-wiki/tree/main/setup/providers",
                    )
                    self.provider = "custom"
                    return
                else:
                    print_error(f"Please enter 1-{len(providers) + 1}")
            except ValueError:
                print_error("Please enter a valid number")

    def _select_vpn_type(self) -> None:
        """Let user select OpenVPN or WireGuard."""
        if self.provider is None or self.provider == "custom":
            self.vpn_type = "openvpn"
            return

        provider_info = VPN_PROVIDERS[self.provider]

        if provider_info["supports_openvpn"] and provider_info["supports_wireguard"]:
            print(f"\n{Colors.BOLD}Select VPN protocol:{Colors.ENDC}\n")
            print("  1. OpenVPN (wider compatibility, slightly slower)")
            print("  2. WireGuard (faster, modern, recommended)")

            while True:
                choice = prompt("\nEnter your choice", "2")
                if choice == "1":
                    self.vpn_type = "openvpn"
                    print_success("Selected: OpenVPN")
                    return
                elif choice == "2":
                    self.vpn_type = "wireguard"
                    print_success("Selected: WireGuard")
                    return
                else:
                    print_error("Please enter 1 or 2")
        elif provider_info["supports_wireguard"]:
            self.vpn_type = "wireguard"
            print_info(f"{provider_info['name']} uses WireGuard.")
        else:
            self.vpn_type = "openvpn"
            print_info(f"{provider_info['name']} uses OpenVPN.")

    def _collect_credentials(self) -> None:
        """Collect VPN credentials from user."""
        if self.provider is None or self.provider == "custom":
            print_info(
                "Configure your VPN credentials in docker-compose.yml after setup."
            )
            return

        provider_info = VPN_PROVIDERS[self.provider]

        print(f"\n{Colors.BOLD}Enter your VPN credentials:{Colors.ENDC}\n")

        # Show helpful information
        print(
            f"{Colors.YELLOW}Note: {provider_info['credentials_note']}{Colors.ENDC}\n"
        )

        # Show relevant URL
        if self.vpn_type == "wireguard" and provider_info.get("wireguard_url"):
            print_link("Get your credentials here", provider_info["wireguard_url"])
        else:
            print_link("Get your credentials here", provider_info["credentials_url"])
        print()

        # Determine which fields to collect
        if self.vpn_type == "openvpn":
            fields = provider_info["openvpn_fields"]
        else:
            fields = provider_info["wireguard_fields"]

        # Collect each field
        for field in fields:
            field_display = field.replace("_", " ").title()
            is_optional = field in OPTIONAL_CREDENTIAL_FIELDS

            # Determine if this is a sensitive field
            is_sensitive = any(
                word in field.lower() for word in ["password", "key", "secret"]
            )

            while True:
                if is_sensitive:
                    # Show guidance for specific fields
                    if "PRIVATE_KEY" in field:
                        print(
                            f"{Colors.DIM}  (Base64 encoded, ~44 characters){Colors.ENDC}"
                        )
                    elif "ADDRESSES" in field:
                        print(
                            f"{Colors.DIM}  (Format: x.x.x.x/32, e.g., 10.64.0.1/32, available in the WireGuard/OpenVPN config file from your provider.){Colors.ENDC}"
                        )
                    elif "PRESHARED_KEY" in field:
                        print(
                            f"{Colors.DIM}  (Base64 encoded preshared key, optional){Colors.ENDC}"
                        )

                    value = prompt_secret(f"  {field_display}")
                else:
                    value = prompt(f"  {field_display}")

                # Validate required fields
                if not value and not is_optional:
                    print_error(f"{field_display} is required.")
                    continue

                self.credentials[field] = value
                break

    def _configure_server_location(self) -> None:
        """Optionally configure server location."""
        print(f"\n{Colors.BOLD}Server Location (Optional){Colors.ENDC}\n")
        print("You can specify which country/region to connect to.")
        print("Leave blank to use the provider's default/fastest server.\n")

        countries = prompt(
            "Server countries (comma-separated, e.g., 'Netherlands,Germany')", ""
        )
        self.server_countries = countries.strip()

        if self.server_countries:
            print_success(f"Will connect to: {self.server_countries}")
        else:
            print_info("Using provider's default server selection")

    def _configure_qbittorrent_routing(self) -> None:
        """Ask if qBittorrent should be routed through VPN."""
        print(f"\n{Colors.BOLD}Route qBittorrent through VPN?{Colors.ENDC}\n")
        print("This ensures all torrent traffic goes through the VPN.")
        print("Highly recommended for privacy when torrenting.\n")

        self.route_qbittorrent = prompt_yes_no(
            "Route qBittorrent through Gluetun VPN?", default=True
        )

        if self.route_qbittorrent:
            print_success("qBittorrent will use VPN for all traffic")
            print_info("qBittorrent's web UI will be accessible via Gluetun's ports")
        else:
            print_info("qBittorrent will use direct connection")

    def get_environment_vars(self) -> Dict[str, str]:
        """Get environment variables for docker-compose."""
        if not self.enabled or self.provider is None or self.provider == "custom":
            return {}

        provider_info = VPN_PROVIDERS[self.provider]
        env: Dict[str, str] = {
            "VPN_SERVICE_PROVIDER": provider_info["provider_name"],
            "VPN_TYPE": self.vpn_type,
        }

        # Add credentials (only non-empty values)
        for key, value in self.credentials.items():
            if value:  # Only add non-empty credentials
                env[key] = value

        # Add server location if specified
        if self.server_countries:
            env["SERVER_COUNTRIES"] = self.server_countries

        return env


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
        host_ip: str = "localhost",
        qbittorrent_host: str = "qbittorrent",
    ) -> str:
        """Generate the complete setup guide."""
        services = self.loader.get_services()

        # Build service URL table
        service_table_lines = []
        for service_id in selected_services:
            svc = services[service_id]
            if svc.get("setup_url"):
                url = replace_placeholders(svc["setup_url"], {"host_ip": host_ip})
            else:
                url = "(no web UI)"
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
            section = self._build_service_section(svc, host_ip, qbittorrent_host)
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

    def _build_service_section(
        self,
        service: Dict[str, Any],
        host_ip: str = "localhost",
        qbittorrent_host: str = "qbittorrent",
    ) -> str:
        """Build markdown section for a single service."""
        lines = [
            f"### {service['name']}",
            "",
            f"**Description:** {service['description']}",
            "",
        ]

        # Prepare replacements
        replacements = {
            "host_ip": host_ip,
            "qbittorrent_host": qbittorrent_host,
        }

        if service.get("setup_url"):
            url = replace_placeholders(service["setup_url"], replacements)
            lines.append(f"**URL:** {url}")
            lines.append("")

        lines.append("**Setup Steps:**")
        lines.append("")

        for i, step in enumerate(service.get("setup_steps", []), 1):
            # Replace placeholders in each step
            step_text = replace_placeholders(step, replacements)
            lines.append(f"{i}. {step_text}")

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
        gluetun_config: Optional[GluetunConfigurator] = None,
    ) -> str:
        """Generate docker-compose.yml content."""
        services = self.loader.get_services()

        lines = ["---", "services:", ""]

        # Determine if qBittorrent should be routed through Gluetun
        route_qbit_through_vpn = (
            gluetun_config is not None
            and gluetun_config.enabled
            and gluetun_config.route_qbittorrent
            and "qbittorrent" in selected_services
        )

        # Build Gluetun first if enabled (other services may depend on it)
        if (
            gluetun_config is not None
            and gluetun_config.enabled
            and "gluetun" in selected_services
        ):
            lines.extend(
                self._build_gluetun_block(
                    services["gluetun"],
                    uid,
                    gid,
                    docker_dir,
                    timezone,
                    gluetun_config,
                    route_qbit_through_vpn,
                    services.get("qbittorrent", {}),
                )
            )

        for service_id in selected_services:
            if service_id == "gluetun":
                continue  # Already handled above

            svc = services[service_id]

            # Check if this service should use Gluetun's network
            use_gluetun_network = service_id == "qbittorrent" and route_qbit_through_vpn

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
                    use_gluetun_network,
                )
            )

        # Add Watchtower
        lines.extend(self._build_watchtower_block(timezone))

        # Add network
        lines.extend(["", "networks:", "  media-network:", "    driver: bridge"])

        return "\n".join(lines)

    def _build_gluetun_block(
        self,
        svc: Dict[str, Any],
        uid: int,
        gid: int,
        docker_dir: Path,
        timezone: str,
        gluetun_config: GluetunConfigurator,
        route_qbittorrent: bool,
        qbittorrent_svc: Dict[str, Any],
    ) -> List[str]:
        """Build Gluetun service block with proper configuration."""
        lines = [
            "  gluetun:",
            f"    image: {svc['image']}",
            "    container_name: gluetun",
            "    restart: unless-stopped",
            "    cap_add:",
            "      - NET_ADMIN",
            "    devices:",
            "      - /dev/net/tun:/dev/net/tun",
        ]

        # Environment variables
        lines.append("    environment:")
        lines.append(f"      - TZ={timezone}")

        # Add VPN configuration from gluetun_config
        env_vars = gluetun_config.get_environment_vars()
        for key, value in env_vars.items():
            lines.append(f"      - {key}={value}")

        # Volumes - use the svc definition properly
        lines.append("    volumes:")
        for container_path, vol_name in svc.get("volumes", {}).items():
            host_path = docker_dir / "gluetun" / vol_name
            lines.append(f"      - {host_path}:{container_path}")

        # Ports
        lines.append("    ports:")
        # Main port from YAML
        main_port = svc.get("port", 8888)
        lines.append(f"      - '{main_port}:{main_port}/tcp'  # HTTP proxy")

        # Extra ports from YAML
        for extra_port in svc.get("extra_ports", []):
            if isinstance(extra_port, dict):
                for port, comment in extra_port.items():
                    lines.append(f"      - '{port}'  # {comment}")
            else:
                lines.append(f"      - '{extra_port}:{extra_port}/tcp'")
                lines.append(f"      - '{extra_port}:{extra_port}/udp'")

        if route_qbittorrent:
            # Add qBittorrent's ports to Gluetun
            qbit_port = qbittorrent_svc.get("port", 8080)
            lines.append(f"      - '{qbit_port}:{qbit_port}'  # qBittorrent Web UI")
            for extra_port in qbittorrent_svc.get("extra_ports", []):
                lines.append(f"      - '{extra_port}:{extra_port}'  # qBittorrent")
                lines.append(f"      - '{extra_port}:{extra_port}/udp'")

        lines.append("    networks:")
        lines.append("      - media-network")
        lines.append("")

        return lines

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
        use_gluetun_network: bool = False,
    ) -> List[str]:
        """Build docker-compose block for a single service."""
        lines = [
            f"  {service_id}:",
            f"    image: {svc['image']}",
            f"    container_name: {service_id}",
            "    restart: unless-stopped",
        ]

        # If using Gluetun network, add network_mode instead of ports/networks
        if use_gluetun_network:
            lines.append('    network_mode: "service:gluetun"')
            lines.append("    depends_on:")
            lines.append("      - gluetun")

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

        # Ports and networks (skip if using Gluetun network)
        if not use_gluetun_network:
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
        self.host_ip: str = "localhost"
        self.is_remote_access: bool = False
        self.gluetun_config: GluetunConfigurator = GluetunConfigurator()

    def run(self) -> None:
        """Run the complete setup process."""
        try:
            self._validate_templates()
            self._print_welcome()
            self._detect_access_mode()
            self._check_prerequisites()
            self._setup_user()
            self._setup_directories()
            self._select_services()
            self._configure_vpn()
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
        print("  - VPN support for private downloads")
        print("  - Companion apps and dashboards\n")
        print(
            f"{Colors.YELLOW}Note: This script requires sudo privileges.{Colors.ENDC}\n"
        )

        if not prompt_yes_no("Ready to begin?"):
            print("Setup cancelled.")
            sys.exit(0)

    def _detect_access_mode(self) -> None:
        """Detect whether user is accessing locally or remotely and set appropriate IP."""
        print_header("ACCESS MODE")

        print("How are you accessing this device?\n")
        print("  1. Local (monitor/display attached)")
        print("  2. Remote (SSH, VNC, or similar)\n")

        while True:
            choice = prompt("Select access mode (1/2)", "1")
            if choice in ("1", "2"):
                break
            print_error("Please enter 1 or 2")

        if choice == "1":
            # Local access - use localhost
            self.is_remote_access = False
            self.host_ip = "localhost"
            print_success("Using localhost for service URLs")
            print_info("Services will be accessible at: http://localhost:<port>")
        else:
            # Remote access - detect network IP
            self.is_remote_access = True
            print_info("Detecting network IP address...")

            self.host_ip = get_local_network_ip()

            if self.host_ip == "localhost":
                print_warning("Could not auto-detect network IP.")
                self.host_ip = prompt("Enter this device's IP address on your network")
            else:
                print_success(f"Detected IP: {self.host_ip}")
                if not prompt_yes_no(f"Use {self.host_ip}?"):
                    self.host_ip = prompt("Enter the correct IP address")

            print_info(f"Services will be accessible at: http://{self.host_ip}:<port>")

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
                "default": 1,
            },
            {
                "name": "Indexer Manager",
                "options": ["prowlarr", "jackett"],
                "default": 1,
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

            handled_services.update(group["options"])

        # Handle remaining services by category
        categorized: Dict[str, List[tuple]] = {}
        for service_id, svc in services.items():
            if service_id in handled_services:
                continue
            cat = svc["category"]
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append((service_id, svc))

        for cat_id, cat_name in categories.items():
            if cat_id not in categorized:
                continue

            print(f"\n{Colors.BOLD}=== {cat_name} ==={Colors.ENDC}")

            for service_id, svc in categorized[cat_id]:
                # Skip gluetun here - we'll handle it in VPN configuration
                if service_id == "gluetun":
                    continue

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

    def _configure_vpn(self) -> None:
        """Configure VPN if user wants it."""
        # Only offer VPN if qBittorrent is selected
        if "qbittorrent" not in self.selected_services:
            print_info("VPN configuration skipped (no torrent client selected)")
            return

        if self.gluetun_config.configure():
            # Add gluetun to selected services
            self.selected_services.insert(0, "gluetun")

    def _get_qbittorrent_host(self) -> str:
        """Get the hostname to use for qBittorrent connections from other containers."""
        if self.gluetun_config.enabled and self.gluetun_config.route_qbittorrent:
            # When qBittorrent uses gluetun's network, other containers must connect via gluetun
            return "gluetun"
        return "qbittorrent"

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
            self.gluetun_config if self.gluetun_config.enabled else None,
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
            f"HOST_IP={self.host_ip}",
        ]
        if self.encryption_key:
            env_lines.append(f"SECRET_ENCRYPTION_KEY={self.encryption_key}")

        env_path = self.output_dir / ".env"
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        run_command(["chown", f"{self.uid}:{self.gid}", str(env_path)], sudo=True)
        run_command(["chmod", "600", str(env_path)], sudo=True)
        print_success(f"Created {env_path}")

        # Generate setup guide
        qbittorrent_host = self._get_qbittorrent_host()
        guide_content = self.guide_gen.generate(
            self.selected_services,
            self.username,
            self.uid,
            self.gid,
            self.docker_dir,
            self.media_dir,
            self.output_dir,
            self.timezone,
            self.host_ip,
            qbittorrent_host,
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

        images_to_pull: Dict[str, str] = {}
        for service_id in self.selected_services:
            svc = services[service_id]
            images_to_pull[svc["image"]] = svc["name"]

        images_to_pull["containrrr/watchtower:latest"] = "Watchtower"

        image_status: Dict[str, str] = {img: "Waiting" for img in images_to_pull}

        def print_progress() -> None:
            lines_count = len(images_to_pull) + 2
            print(f"\033[{lines_count}A", end="")

            print(
                f"{Colors.BOLD}{'Service':<20} {'Image':<45} {'Status':<15}{Colors.ENDC}"
            )
            print("-" * 80)

            for image, name in images_to_pull.items():
                status = image_status.get(image, "Waiting")

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

                image_short = image[:43] + ".." if len(image) > 45 else image
                print(f"{name:<20} {image_short:<45} {status_display:<15}")

        print("\n" * (len(images_to_pull) + 2))
        print_progress()

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

                    for image in images_to_pull:
                        image_short = image.split("/")[-1]

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
        qbittorrent_host = self._get_qbittorrent_host()
        replacements = {"host_ip": self.host_ip, "qbittorrent_host": qbittorrent_host}

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
                url = replace_placeholders(svc["setup_url"], replacements)
                print(f"\n{Colors.GREEN}Open: {url}{Colors.ENDC}\n")
            else:
                print(f"\n{Colors.YELLOW}(No web interface){Colors.ENDC}\n")

            print(f"{Colors.BOLD}Setup Steps:{Colors.ENDC}\n")
            for j, step in enumerate(svc.get("setup_steps", []), 1):
                step_text = replace_placeholders(step, replacements)
                print(f"  {j}. {step_text}")

            wait_for_done(i, total)

        print_success("All services configured!")

    def _print_congratulations(self) -> None:
        """Print congratulations message."""
        print_header("CONGRATULATIONS!")

        services = self.loader.get_services()
        replacements = {
            "host_ip": self.host_ip,
            "qbittorrent_host": self._get_qbittorrent_host(),
        }

        print(f"{Colors.GREEN}Your media server has been set up!{Colors.ENDC}\n")

        print(f"{Colors.BOLD}Quick Reference:{Colors.ENDC}")
        for service_id in self.selected_services:
            svc = services[service_id]
            if svc.get("setup_url"):
                url = replace_placeholders(svc["setup_url"], replacements)
                print(f"  - {svc['name']}: {url}")

        if self.gluetun_config.enabled and self.gluetun_config.route_qbittorrent:
            print(
                f"\n{Colors.YELLOW}Note: qBittorrent traffic is routed through VPN{Colors.ENDC}"
            )
            print("  Verify VPN is working: docker exec gluetun wget -qO- ifconfig.me")
            print(
                f"  *arr apps should use 'gluetun' as the qBittorrent host (not 'qbittorrent')"
            )

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
