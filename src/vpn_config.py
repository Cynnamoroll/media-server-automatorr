"""
VPN configuration module for Gluetun setup.
"""

from typing import Dict, Optional

from .constants import VPN_PROVIDERS
from .utils import (
    Colors,
    get_docker_network_subnet,
    print_error,
    print_header,
    print_info,
    print_link,
    print_success,
    print_warning,
    prompt,
    prompt_secret,
    prompt_yes_no,
    validate_subnet_format,
)


class GluetunConfigurator:
    """Handles interactive Gluetun VPN configuration."""

    def __init__(self):
        self.enabled: bool = False
        self.provider: Optional[str] = None
        self.vpn_type: str = "openvpn"
        self.credentials: Dict[str, str] = {}
        self.server_countries: str = ""
        self.route_qbittorrent: bool = False
        self.docker_subnet: str = ""
        # Fields that are optional (can be empty)
        self.optional_fields = {"OPENVPN_PASSWORD", "WIREGUARD_PRESHARED_KEY"}

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

        # Configure Docker network
        self._configure_docker_network()

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
            is_optional = field in self.optional_fields

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
                            f"{Colors.DIM}  (Format: x.x.x.x/32, e.g., 10.64.0.1/32){Colors.ENDC}"
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

    def _configure_docker_network(self) -> None:
        """Configure firewall outbound subnets for Docker network."""
        print(f"\n{Colors.BOLD}Docker Network Configuration{Colors.ENDC}\n")
        print("Gluetun needs to allow outbound traffic to your Docker network.")
        print("This allows containers to communicate with each other.")

        detected_subnet = get_docker_network_subnet()
        print(f"Auto-detected Docker subnet: {detected_subnet}")
        print("(This is usually correct for most Docker installations)")

        custom_subnet = prompt(
            f"Docker network subnet (press Enter to accept auto-detected: {detected_subnet})",
            "",
        ).strip()

        if custom_subnet:
            # Validate subnet format
            if validate_subnet_format(custom_subnet):
                self.docker_subnet = custom_subnet
                print_success(f"Using custom subnet: {custom_subnet}")
            else:
                print_warning(
                    f"Invalid subnet format, using auto-detected: {detected_subnet}"
                )
                self.docker_subnet = detected_subnet
        else:
            self.docker_subnet = detected_subnet
            print_success(f"Using auto-detected subnet: {detected_subnet}")

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

        # Add firewall configuration for Docker network
        if self.docker_subnet:
            env["FIREWALL_OUTBOUND_SUBNETS"] = self.docker_subnet

        return env
