"""
Docker Compose generator module for creating docker-compose.yml files.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .template_loader import TemplateLoader
from .vpn_config import GluetunConfigurator


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
        """Build a regular service block."""
        lines = [
            f"  {service_id}:",
            f"    image: {svc['image']}",
            f"    container_name: {service_id}",
            "    restart: unless-stopped",
        ]

        # Network mode for services using Gluetun
        if use_gluetun_network:
            lines.append("    network_mode: service:gluetun")
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
            "",
        ]
