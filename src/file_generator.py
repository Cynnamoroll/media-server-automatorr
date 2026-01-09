"""
File generation utilities for media-server-automatorr.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

from .compose_generator import ComposeGenerator
from .template_loader import TemplateLoader
from .utils import (
    Colors,
    generate_encryption_key,
    get_timezone,
    print_error,
    print_info,
    print_success,
    replace_placeholders,
    run_command,
)
from .vpn_config import GluetunConfigurator


class FileGenerator:
    """Handles generation of configuration files and documentation."""

    def __init__(self, loader: TemplateLoader):
        self.loader = loader
        self.compose_generator = ComposeGenerator(loader)

    def generate_all_files(
        self,
        selected_services: List[str],
        uid: int,
        gid: int,
        docker_dir: Path,
        media_dir: Path,
        output_dir: Path,
        timezone: str,
        gluetun_config: Optional[GluetunConfigurator] = None,
    ) -> Dict[str, bool]:
        """
        Generate all configuration files.

        Args:
            selected_services: List of selected service IDs
            uid: User ID
            gid: Group ID
            docker_dir: Docker base directory
            media_dir: Media base directory
            output_dir: Output directory for generated files
            timezone: System timezone
            gluetun_config: VPN configuration

        Returns:
            Dictionary mapping file names to success status
        """
        results = {}

        # Generate encryption key if needed
        encryption_key = ""
        if "homarr" in selected_services:
            encryption_key = generate_encryption_key()
            print_info("Generated encryption key for Homarr")

        # Generate docker-compose.yml
        results["docker-compose.yml"] = self._generate_compose_file(
            selected_services,
            uid,
            gid,
            docker_dir,
            media_dir,
            output_dir,
            timezone,
            encryption_key,
            gluetun_config,
        )

        # Generate .env file
        results[".env"] = self._generate_env_file(output_dir, timezone)

        # Generate setup guide
        results["SETUP_GUIDE.md"] = self._generate_setup_guide(
            selected_services, docker_dir, media_dir, output_dir, gluetun_config
        )

        # Set file permissions
        self._set_file_permissions(output_dir, uid, gid)

        return results

    def _generate_compose_file(
        self,
        selected_services: List[str],
        uid: int,
        gid: int,
        docker_dir: Path,
        media_dir: Path,
        output_dir: Path,
        timezone: str,
        encryption_key: str,
        gluetun_config: Optional[GluetunConfigurator],
    ) -> bool:
        """Generate docker-compose.yml file."""
        try:
            compose_content = self.compose_generator.generate(
                selected_services,
                uid,
                gid,
                docker_dir,
                media_dir,
                timezone,
                encryption_key,
                gluetun_config,
            )

            compose_path = output_dir / "docker-compose.yml"
            compose_path.write_text(compose_content, encoding="utf-8")
            print_success(f"Created {compose_path}")
            return True

        except Exception as e:
            print_error(f"Failed to generate docker-compose.yml: {e}")
            return False

    def _generate_env_file(self, output_dir: Path, timezone: str) -> bool:
        """Generate .env file with environment variables."""
        try:
            env_content = [
                "# Environment variables for docker-compose",
                f"COMPOSE_PROJECT_NAME=mediaserver",
                f"TZ={timezone}",
                "",
                "# Uncomment and modify these if needed:",
                "# DOCKER_SUBNET=172.17.0.0/16",
                "# PLEX_CLAIM=claim-xxxxxxxxxx",
                "",
            ]

            env_path = output_dir / ".env"
            env_path.write_text("\n".join(env_content), encoding="utf-8")
            print_success(f"Created {env_path}")
            return True

        except Exception as e:
            print_error(f"Failed to generate .env file: {e}")
            return False

    def _generate_setup_guide(
        self,
        selected_services: List[str],
        docker_dir: Path,
        media_dir: Path,
        output_dir: Path,
        gluetun_config: Optional[GluetunConfigurator],
    ) -> bool:
        """Generate comprehensive setup guide."""
        try:
            services = self.loader.get_services()

            # Load templates
            header_template = self.loader.load_template("setup-guide-header.md")
            footer_template = self.loader.load_template("setup-guide-footer.md")

            # Start building the guide
            guide_lines = []

            # Add header with basic information
            guide_lines.append(
                header_template.format(
                    docker_dir=docker_dir,
                    media_dir=media_dir,
                    compose_dir=output_dir,
                )
            )

            # Add service-specific setup instructions
            guide_lines.append("## Service Configuration\n")
            guide_lines.append(
                "Configure each service in the order shown below for best results:\n"
            )

            # Sort services by setup priority
            from .constants import SETUP_ORDER_PRIORITY

            sorted_services = sorted(
                selected_services,
                key=lambda x: SETUP_ORDER_PRIORITY.index(x)
                if x in SETUP_ORDER_PRIORITY
                else 999,
            )

            # Generate setup steps for each service
            for i, service_id in enumerate(sorted_services, 1):
                if service_id not in services:
                    continue

                service = services[service_id]
                guide_lines.extend(
                    self._generate_service_setup_section(
                        service_id, service, i, len(sorted_services), gluetun_config
                    )
                )

            # Add VPN-specific information if configured
            if gluetun_config and gluetun_config.enabled:
                guide_lines.extend(self._generate_vpn_setup_section(gluetun_config))

            # Add troubleshooting section
            guide_lines.extend(
                self._generate_troubleshooting_section(selected_services)
            )

            # Add footer
            guide_lines.append(footer_template)

            # Write the guide
            guide_path = output_dir / "SETUP_GUIDE.md"
            guide_path.write_text("\n".join(guide_lines), encoding="utf-8")
            print_success(f"Created {guide_path}")
            return True

        except Exception as e:
            print_error(f"Failed to generate setup guide: {e}")
            return False

    def _generate_service_setup_section(
        self,
        service_id: str,
        service: Dict,
        step_num: int,
        total_steps: int,
        gluetun_config: Optional[GluetunConfigurator],
    ) -> List[str]:
        """Generate setup section for a specific service."""
        lines = []

        name = service.get("name", service_id.title())
        port = service.get("port", "Unknown")

        # Adjust port information for services routed through VPN
        if (
            service_id == "qbittorrent"
            and gluetun_config
            and gluetun_config.enabled
            and gluetun_config.route_qbittorrent
        ):
            port_info = f"{port} (accessed via Gluetun)"
        else:
            port_info = str(port)

        lines.append(f"### {step_num}. {name}")
        lines.append("")

        # Basic access information
        setup_url = service.get("setup_url")
        if setup_url and setup_url != "null":
            lines.append(f"**Access URL:** {setup_url}")
        else:
            lines.append(f"**Access URL:** http://localhost:{port_info}")

        lines.append(f"**Port:** {port_info}")
        lines.append("")

        # Add service-specific setup steps
        setup_steps = service.get("setup_steps", [])
        if setup_steps:
            lines.append("**Setup Steps:**")
            for step in setup_steps:
                # Replace placeholders in setup steps
                if gluetun_config and gluetun_config.enabled:
                    qbit_host = (
                        "gluetun" if gluetun_config.route_qbittorrent else "qbittorrent"
                    )
                    step = step.replace("{qbittorrent_host}", qbit_host)

                lines.append(f"- {step}")
            lines.append("")

        # Add configuration notes if available
        config_notes = service.get("config_notes", [])
        if config_notes:
            lines.append("**Configuration Notes:**")
            for note in config_notes:
                lines.append(f"- {note}")
            lines.append("")

        # Add important warnings
        warnings = service.get("warnings", [])
        if warnings:
            lines.append("**⚠️ Important:**")
            for warning in warnings:
                lines.append(f"- {warning}")
            lines.append("")

        lines.append("---")
        lines.append("")

        return lines

    def _generate_vpn_setup_section(
        self, gluetun_config: GluetunConfigurator
    ) -> List[str]:
        """Generate VPN-specific setup information."""
        lines = []

        lines.append("## VPN Configuration")
        lines.append("")

        if gluetun_config.enabled:
            lines.append("Your VPN (Gluetun) has been configured with the following:")
            lines.append("")

            if gluetun_config.provider and gluetun_config.provider != "custom":
                lines.append(f"- **Provider:** {gluetun_config.provider.title()}")
                lines.append(f"- **Protocol:** {gluetun_config.vpn_type.upper()}")

                if gluetun_config.server_countries:
                    lines.append(
                        f"- **Server Countries:** {gluetun_config.server_countries}"
                    )

                if gluetun_config.route_qbittorrent:
                    lines.append(
                        "- **qBittorrent Routing:** Enabled (traffic goes through VPN)"
                    )
                else:
                    lines.append(
                        "- **qBittorrent Routing:** Disabled (direct connection)"
                    )

            lines.append("")
            lines.append("**Testing VPN Connection:**")
            lines.append("```bash")
            lines.append("# Test VPN connection")
            lines.append("docker exec gluetun wget -qO- ifconfig.me")
            lines.append("")
            lines.append("# Check Gluetun logs")
            lines.append("docker logs gluetun")
            lines.append("```")
            lines.append("")

            if gluetun_config.route_qbittorrent:
                lines.append("**Important for *arr Apps:**")
                lines.append(
                    "- Use `gluetun` as the qBittorrent host (not `qbittorrent`)"
                )
                lines.append(
                    "- qBittorrent's web UI is accessible through Gluetun's ports"
                )
                lines.append("")

        return lines

    def _generate_troubleshooting_section(
        self, selected_services: List[str]
    ) -> List[str]:
        """Generate troubleshooting section based on selected services."""
        lines = []

        lines.append("## Troubleshooting")
        lines.append("")

        # Common issues
        lines.append("### Common Issues")
        lines.append("")

        lines.append("**Can't access web interfaces:**")
        lines.append("1. Check containers are running: `docker compose ps`")
        lines.append("2. Check firewall settings")
        lines.append("3. Try server IP instead of localhost")
        lines.append("")

        # Service-specific troubleshooting
        if "qbittorrent" in selected_services:
            lines.append("**qBittorrent Issues:**")
            lines.append(
                "- Initial password: Check logs with `docker logs qbittorrent`"
            )
            lines.append("- If using VPN: Access via Gluetun's ports")
            lines.append("- *arr apps should use 'gluetun' as host if VPN is enabled")
            lines.append("")

        if any(s in selected_services for s in ["sonarr", "radarr", "lidarr"]):
            lines.append("***arr App Issues:**")
            lines.append("- Use internal Docker hostnames (not localhost)")
            lines.append(
                "- qBittorrent host: Use 'gluetun' if VPN enabled, 'qbittorrent' if not"
            )
            lines.append("- Check indexer connectivity in Settings > Indexers")
            lines.append("")

        if "gluetun" in selected_services:
            lines.append("**VPN (Gluetun) Issues:**")
            lines.append("- Check logs: `docker logs gluetun`")
            lines.append("- Verify credentials in docker-compose.yml")
            lines.append(
                "- Test connection: `docker exec gluetun wget -qO- ifconfig.me`"
            )
            lines.append("")

        # General debugging
        lines.append("### General Debugging")
        lines.append("")
        lines.append("**Check container status:**")
        lines.append("```bash")
        lines.append("docker compose ps")
        lines.append("```")
        lines.append("")

        lines.append("**View logs:**")
        lines.append("```bash")
        lines.append("docker compose logs -f [service_name]")
        lines.append("```")
        lines.append("")

        lines.append("**Restart services:**")
        lines.append("```bash")
        lines.append("docker compose restart [service_name]")
        lines.append("```")
        lines.append("")

        return lines

    def _set_file_permissions(self, output_dir: Path, uid: int, gid: int) -> None:
        """Set proper permissions on generated files."""
        try:
            # Set ownership of all files in output directory
            for file_path in output_dir.glob("*"):
                if file_path.is_file():
                    try:
                        if os.geteuid() == 0:
                            os.chown(file_path, uid, gid)
                        else:
                            run_command(
                                ["chown", f"{uid}:{gid}", str(file_path)], sudo=True
                            )
                    except Exception:
                        # If we can't set ownership, that's ok for files
                        pass

        except Exception:
            # Non-critical error
            pass

    def validate_generated_files(self, output_dir: Path) -> List[str]:
        """
        Validate that all expected files were generated correctly.

        Returns:
            List of validation errors (empty if all good)
        """
        errors = []

        # Check required files exist
        required_files = ["docker-compose.yml", ".env", "SETUP_GUIDE.md"]

        for filename in required_files:
            file_path = output_dir / filename
            if not file_path.exists():
                errors.append(f"Missing required file: {filename}")
            elif file_path.stat().st_size == 0:
                errors.append(f"Empty file: {filename}")

        # Validate docker-compose.yml format
        compose_path = output_dir / "docker-compose.yml"
        if compose_path.exists():
            try:
                import yaml

                with open(compose_path, "r") as f:
                    yaml.safe_load(f)
            except yaml.YAMLError as e:
                errors.append(f"Invalid docker-compose.yml format: {e}")
            except Exception as e:
                errors.append(f"Could not read docker-compose.yml: {e}")

        return errors
