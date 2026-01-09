"""
User interface utilities for media-server-automatorr.
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

from .utils import (
    Colors,
    print_error,
    print_header,
    print_info,
    print_success,
    print_warning,
    prompt,
    prompt_yes_no,
)


class ServiceSelector:
    """Handles interactive service selection with improved UX."""

    def __init__(self, services: Dict, categories: Dict, services_by_category: Dict):
        self.services = services
        self.categories = categories
        self.services_by_category = services_by_category
        self.selected_services: List[str] = []

    def select_services(self) -> List[str]:
        """
        Interactive service selection with better organization and feedback.

        Returns:
            List of selected service IDs
        """
        print_header("SERVICE SELECTION")
        print("Select services to install for your media server.")
        print("Services are organized by category for easier selection.\n")

        # Show selection menu
        self._show_selection_menu()

        # Validate selection
        if not self.selected_services:
            print_warning("No services selected.")
            if prompt_yes_no("Exit setup?", default=True):
                sys.exit(0)
            else:
                return self.select_services()  # Try again

        # Show final selection summary
        self._show_selection_summary()

        if not prompt_yes_no("Continue with these services?", default=True):
            return self.select_services()  # Start over

        return self.selected_services

    def _show_selection_menu(self) -> None:
        """Display the service selection menu by category."""
        for category_id, service_list in self.services_by_category.items():
            category_name = self.categories.get(
                category_id, category_id.replace("_", " ").title()
            )

            print_header(f"{category_name}")

            # Show category description if available
            self._show_category_description(category_id)

            # Select services in this category
            category_selections = self._select_category_services(service_list)
            self.selected_services.extend(category_selections)

            print()  # Add spacing between categories

    def _show_category_description(self, category_id: str) -> None:
        """Show helpful description for each category."""
        descriptions = {
            "media_servers": "Choose your media server platform. Most users need only one.",
            "arr_suite": "Automated media management tools. Choose based on your content types.",
            "indexers": "Tools to find content. Choose Prowlarr (recommended) or Jackett.",
            "download_clients": "Download and manage your content transfers.",
            "companion_apps": "Additional features like subtitles, requests, and monitoring.",
            "dashboards": "Web interfaces to manage all your services in one place.",
            "utility": "Supporting services like VPN and Cloudflare bypass.",
            "usenet": "Usenet download clients (alternative to torrents).",
        }

        if category_id in descriptions:
            print(f"{Colors.DIM}{descriptions[category_id]}{Colors.ENDC}\n")

    def _select_category_services(self, service_list: List[str]) -> List[str]:
        """Select services within a single category."""
        category_selections = []

        for service_id in service_list:
            service = self.services[service_id]

            # Format service information
            name = service["name"]
            description = service.get("description", "")

            # Add helpful context for some services
            context = self._get_service_context(service_id)
            if context:
                description += f" {context}"

            # Ask for selection
            question = f"Install {name}?"
            if description:
                question += f" ({description})"

            if prompt_yes_no(question, default=False):
                category_selections.append(service_id)
                print_success(f"✓ Selected: {name}")

        return category_selections

    def _get_service_context(self, service_id: str) -> str:
        """Get helpful context for specific services."""
        contexts = {
            "plex": "- Popular, feature-rich, some features require Plex Pass",
            "jellyfin": "- Free, open-source alternative to Plex",
            "emby": "- Another Plex alternative with live TV support",
            "sonarr": "- For TV shows",
            "radarr": "- For movies",
            "lidarr": "- For music",
            "readarr": "- For books/audiobooks",
            "mylar3": "- For comics",
            "prowlarr": "- Manages indexers for all *arr apps (recommended)",
            "jackett": "- Alternative indexer proxy",
            "qbittorrent": "- Popular torrent client",
            "bazarr": "- Automatic subtitles for movies/TV",
            "seerr": "- Request interface for users",
            "tautulli": "- Plex usage statistics",
            "homarr": "- Customizable dashboard",
            "gluetun": "- VPN for secure downloads",
            "flaresolverr": "- Bypasses Cloudflare protection",
            "nzbget": "- Fast usenet client",
            "sabnzbd": "- User-friendly usenet client",
        }

        return contexts.get(service_id, "")

    def _show_selection_summary(self) -> None:
        """Show a summary of selected services."""
        print_header("SELECTED SERVICES")

        if not self.selected_services:
            print_warning("No services selected!")
            return

        # Group by category for better presentation
        selected_by_category = {}
        for service_id in self.selected_services:
            service = self.services[service_id]
            category = service.get("category", "other")

            if category not in selected_by_category:
                selected_by_category[category] = []
            selected_by_category[category].append(service_id)

        # Display grouped selections
        for category_id, service_list in selected_by_category.items():
            category_name = self.categories.get(
                category_id, category_id.replace("_", " ").title()
            )
            print(f"\n{Colors.BOLD}{category_name}:{Colors.ENDC}")

            for service_id in service_list:
                service_name = self.services[service_id]["name"]
                print(f"  • {service_name}")

        print(
            f"\n{Colors.BOLD}Total: {len(self.selected_services)} services{Colors.ENDC}"
        )


class UserConfigCollector:
    """Collects user configuration with validation and helpful prompts."""

    @staticmethod
    def get_user_info() -> Tuple[str, int, int]:
        """
        Collect user information for Docker containers.

        Returns:
            Tuple of (username, uid, gid)
        """
        print_header("USER CONFIGURATION")
        print("Docker containers need to run with proper user permissions.")
        print("This ensures your files have the correct ownership.\n")

        # Get current user info
        current_username = os.getenv("USER", "docker")
        current_uid = os.getuid()
        current_gid = os.getgid()

        print_info(
            f"Current user: {current_username} (UID: {current_uid}, GID: {current_gid})"
        )

        # Ask if user wants to use current user
        if prompt_yes_no("Use current user for Docker containers?", default=True):
            print_success(f"Using user: {current_username}")
            return current_username, current_uid, current_gid

        # Get custom user
        return UserConfigCollector._get_custom_user_info(current_username)

    @staticmethod
    def _get_custom_user_info(default_username: str) -> Tuple[str, int, int]:
        """Get custom user information with validation."""
        while True:
            username = prompt("Enter username for Docker containers", default_username)

            try:
                import pwd

                user_info = pwd.getpwnam(username)
                uid = user_info.pw_uid
                gid = user_info.pw_gid

                print_success(f"Using user: {username} (UID: {uid}, GID: {gid})")
                return username, uid, gid

            except KeyError:
                print_error(f"User '{username}' not found")
                if not prompt_yes_no("Try a different username?", default=True):
                    sys.exit(1)

    @staticmethod
    def get_directory_paths() -> Tuple[str, str]:
        """
        Collect directory paths with validation and helpful suggestions.

        Returns:
            Tuple of (docker_dir, media_dir)
        """
        print_header("DIRECTORY CONFIGURATION")
        print("Choose where to store your Docker configurations and media files.")
        print("These directories will be created if they don't exist.\n")

        # Docker directory
        docker_dir = UserConfigCollector._get_docker_directory()

        # Media directory
        media_dir = UserConfigCollector._get_media_directory()

        return docker_dir, media_dir

    @staticmethod
    def _get_docker_directory() -> str:
        """Get Docker directory with helpful guidance."""
        print_info(
            "Docker Directory: Stores container configurations and persistent data"
        )
        print("  • Should be on a fast drive (SSD recommended)")
        print("  • Needs ~10-50GB depending on services selected")
        print("  • Common locations: /opt/docker, /home/user/docker\n")

        default_docker = "/opt/docker"
        return prompt("Docker directory", default_docker)

    @staticmethod
    def _get_media_directory() -> str:
        """Get media directory with helpful guidance."""
        print_info("\nMedia Directory: Stores your actual media files")
        print("  • Should have lots of storage space")
        print("  • Will contain movies, TV shows, music, etc.")
        print("  • Common locations: /srv/media, /mnt/media, /media\n")

        default_media = "/srv/media"
        return prompt("Media directory", default_media)

    @staticmethod
    def confirm_setup(
        username: str,
        docker_dir: str,
        media_dir: str,
        selected_services: List[str],
        services: Dict,
    ) -> bool:
        """
        Show final configuration confirmation.

        Returns:
            True if user confirms, False otherwise
        """
        print_header("CONFIGURATION SUMMARY")

        print(f"{Colors.BOLD}User Configuration:{Colors.ENDC}")
        print(f"  Username: {username}")
        print(f"  Docker Directory: {docker_dir}")
        print(f"  Media Directory: {media_dir}")

        print(
            f"\n{Colors.BOLD}Selected Services ({len(selected_services)}):{Colors.ENDC}"
        )
        for service_id in selected_services:
            service_name = services[service_id]["name"]
            print(f"  • {service_name}")

        print(f"\n{Colors.BOLD}What happens next:{Colors.ENDC}")
        print("  1. Create directory structure")
        print("  2. Generate docker-compose.yml")
        print("  3. Create setup guide")
        print("  4. Set proper permissions")
        print("  5. Offer to start containers")

        return prompt_yes_no(f"\nProceed with setup?", default=True)


class ProgressReporter:
    """Handles progress reporting and user feedback during setup."""

    def __init__(self, total_steps: int):
        self.total_steps = total_steps
        self.current_step = 0

    def start_step(self, step_name: str) -> None:
        """Start a new step with progress indication."""
        self.current_step += 1
        progress = f"[{self.current_step}/{self.total_steps}]"
        print(f"\n{Colors.BOLD}{Colors.CYAN}{progress} {step_name}{Colors.ENDC}")

    def step_success(self, message: str) -> None:
        """Report step success."""
        print_success(message)

    def step_warning(self, message: str) -> None:
        """Report step warning."""
        print_warning(message)

    def step_error(self, message: str) -> None:
        """Report step error."""
        print_error(message)

    def finish(self, success: bool = True) -> None:
        """Report overall completion."""
        if success:
            print(
                f"\n{Colors.BOLD}{Colors.GREEN}✓ Setup completed successfully!{Colors.ENDC}"
            )
        else:
            print(
                f"\n{Colors.BOLD}{Colors.RED}✗ Setup completed with issues{Colors.ENDC}"
            )
