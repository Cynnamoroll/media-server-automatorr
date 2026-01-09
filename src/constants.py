"""
Constants and shared configuration for media-server-automatorr.
"""

from pathlib import Path
from typing import Any, Dict

# Script directories
SCRIPT_DIR = Path(__file__).parent.parent.resolve()
TEMPLATES_DIR = SCRIPT_DIR / "templates"

# VPN provider definitions
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
        "openvpn_fields": ["OPENVPN_USER", "OPENVPN_PASSWORD"],
        "wireguard_fields": ["WIREGUARD_PRIVATE_KEY"],
        "credentials_url": "https://www.ivpn.net/account/login",
        "credentials_note": "Use your IVPN account credentials.",
    },
}

# Fields that are optional (can be empty)
OPTIONAL_CREDENTIAL_FIELDS = {"OPENVPN_PASSWORD", "WIREGUARD_PRESHARED_KEY"}

# Setup walkthrough priority order
SETUP_ORDER_PRIORITY = [
    "gluetun",
    "qbittorrent",
    "radarr",
    "sonarr",
    "lidarr",
    "mylar3",
    "prowlarr",
    "jackett",
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

# Common Docker subnet patterns (in order of preference)
COMMON_DOCKER_SUBNETS = [
    "172.17.0.0/16",
    "172.18.0.0/16",
    "172.19.0.0/16",
    "172.20.0.0/16",
]
