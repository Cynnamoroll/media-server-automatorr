"""
Utility functions for media-server-automatorr.
"""

import json
import os
import re
import secrets
import socket
import string
import subprocess
import sys
from typing import Dict

# ============================================================================
# COLOR DEFINITIONS
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
    UNDERLINE = "\033[4m"
    DIM = "\033[2m"


# ============================================================================
# USER INTERFACE FUNCTIONS
# ============================================================================


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{text}{Colors.ENDC}")
    print("=" * len(text))


def print_success(text: str) -> None:
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_warning(text: str) -> None:
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")


def print_error(text: str) -> None:
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")


def print_info(text: str) -> None:
    print(f"{Colors.CYAN}ℹ {text}{Colors.ENDC}")


def print_link(description: str, url: str) -> None:
    """Print a formatted link."""
    print(f"{Colors.UNDERLINE}{Colors.BLUE}{description}: {url}{Colors.ENDC}")


def prompt(question: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    if default:
        return input(f"{question} [{default}]: ") or default
    return input(f"{question}: ")


def prompt_secret(question: str) -> str:
    """Prompt for secret input (like passwords)."""
    import getpass

    try:
        return getpass.getpass(f"{question}: ")
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)


def prompt_yes_no(question: str, default: bool = False) -> bool:
    """Prompt user for yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{question} [{default_str}]: ").lower().strip()
        if not answer:
            return default
        if answer in ["y", "yes", "true", "1"]:
            return True
        elif answer in ["n", "no", "false", "0"]:
            return False
        else:
            print_error("Please answer yes or no.")


def wait_for_done(current: int, total: int) -> None:
    """Wait for user to indicate they've completed a step."""
    while True:
        response = input(
            f"\n{Colors.BOLD}Press Enter when done with step {current}/{total} "
            f"(or 'skip' to continue): {Colors.ENDC}"
        )
        if response.lower() == "skip":
            print_warning("Step skipped.")
            break
        elif response == "":
            break
        else:
            print_info("Press Enter to continue or type 'skip' to skip this step.")


# ============================================================================
# SYSTEM UTILITIES
# ============================================================================


def run_command(
    command: list, check: bool = True, sudo: bool = False
) -> subprocess.CompletedProcess:
    """Run a system command."""
    if sudo and os.geteuid() != 0:
        command = ["sudo"] + command

    return subprocess.run(command, capture_output=True, text=True, check=check)


def generate_encryption_key() -> str:
    """Generate a random encryption key."""
    return "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
    )


def get_timezone() -> str:
    """Get system timezone."""
    try:
        result = run_command(["timedatectl", "show", "--property=Timezone", "--value"])
        return result.stdout.strip() or "UTC"
    except (subprocess.CalledProcessError, FileNotFoundError):
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


def get_docker_network_subnet() -> str:
    """Detect the Docker network subnet for firewall configuration."""
    # Common Docker subnet patterns (in order of preference)
    COMMON_DOCKER_SUBNETS = [
        "172.17.0.0/16",
        "172.18.0.0/16",
        "172.19.0.0/16",
        "172.20.0.0/16",
    ]

    try:
        # Try to get the default bridge network subnet
        result = subprocess.run(
            ["docker", "network", "inspect", "bridge"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

        # Parse JSON output to extract subnet

        bridge_data = json.loads(result.stdout)
        if bridge_data and len(bridge_data) > 0:
            ipam_config = bridge_data[0].get("IPAM", {}).get("Config", [])
            for config in ipam_config:
                subnet = config.get("Subnet")
                if subnet and not subnet.startswith("127."):
                    return subnet
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ):
        pass

    try:
        # Try to inspect current Docker daemon default network pool
        result = subprocess.run(
            ["docker", "system", "info", "--format", "{{.DefaultAddressPools}}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        info_output = result.stdout.strip()
        if info_output and info_output != "<no value>":
            # Extract first subnet from pools
            for subnet in COMMON_DOCKER_SUBNETS:
                if subnet.split("/")[0].split(".")[0:2] == ["172", "17"]:
                    return subnet
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        pass

    # Return most common Docker default
    return COMMON_DOCKER_SUBNETS[0]


def replace_placeholders(text: str, replacements: Dict[str, str]) -> str:
    """Replace placeholders in text with values from replacements dict."""
    result = text
    for placeholder, value in replacements.items():
        result = result.replace(f"{{{placeholder}}}", str(value))
    return result


def validate_subnet_format(subnet: str) -> bool:
    """Validate subnet format (e.g., 172.17.0.0/16)."""
    if not subnet or "/" not in subnet:
        return False

    try:
        ip_part, cidr_part = subnet.split("/")
        # Basic IP validation
        parts = ip_part.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            if not (0 <= int(part) <= 255):
                return False
        # CIDR validation
        cidr = int(cidr_part)
        if not (0 <= cidr <= 32):
            return False
        return True
    except (ValueError, AttributeError):
        return False
