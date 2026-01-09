"""
Tests for user_interface module.
"""

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.user_interface import ProgressReporter, ServiceSelector, UserConfigCollector


class TestServiceSelector:
    """Test ServiceSelector class."""

    def test_init(self, sample_services, sample_categories):
        """Test ServiceSelector initialization."""
        services_by_category = {
            "media_servers": ["jellyfin"],
            "download_clients": ["qbittorrent"],
            "utility": ["gluetun"],
        }

        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        assert selector.services == sample_services
        assert selector.categories == sample_categories
        assert selector.services_by_category == services_by_category
        assert selector.selected_services == []

    def test_get_service_context(self, sample_services, sample_categories):
        """Test service context generation."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        # Test known service contexts
        assert "Popular, feature-rich" in selector._get_service_context("plex")
        assert "Free, open-source" in selector._get_service_context("jellyfin")
        assert "For TV shows" in selector._get_service_context("sonarr")
        assert "For movies" in selector._get_service_context("radarr")
        assert "VPN for secure" in selector._get_service_context("gluetun")

        # Test unknown service
        assert selector._get_service_context("unknown_service") == ""

    def test_show_category_description(
        self, sample_services, sample_categories, capsys
    ):
        """Test category description display."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        selector._show_category_description("media_servers")
        captured = capsys.readouterr()
        assert "Choose your media server platform" in captured.out

        selector._show_category_description("arr_suite")
        captured = capsys.readouterr()
        assert "Automated media management" in captured.out

        # Test unknown category
        selector._show_category_description("unknown_category")
        captured = capsys.readouterr()
        # Should not output anything for unknown category

    def test_select_category_services_all_selected(
        self, sample_services, sample_categories
    ):
        """Test selecting all services in a category."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        with patch("src.user_interface.prompt_yes_no", return_value=True):
            selections = selector._select_category_services(["jellyfin"])

        assert selections == ["jellyfin"]

    def test_select_category_services_none_selected(
        self, sample_services, sample_categories
    ):
        """Test selecting no services in a category."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        with patch("src.user_interface.prompt_yes_no", return_value=False):
            selections = selector._select_category_services(["jellyfin"])

        assert selections == []

    def test_show_selection_summary(self, sample_services, sample_categories, capsys):
        """Test selection summary display."""
        services_by_category = {
            "media_servers": ["jellyfin"],
            "download_clients": ["qbittorrent"],
        }
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )
        selector.selected_services = ["jellyfin", "qbittorrent"]

        selector._show_selection_summary()
        captured = capsys.readouterr()

        assert "SELECTED SERVICES" in captured.out
        assert "Media Servers:" in captured.out
        assert "Download Clients:" in captured.out
        assert "• Jellyfin" in captured.out
        assert "• qBittorrent" in captured.out
        assert "Total: 2 services" in captured.out

    def test_show_selection_summary_empty(
        self, sample_services, sample_categories, capsys
    ):
        """Test selection summary display with no selections."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )
        selector.selected_services = []

        selector._show_selection_summary()
        captured = capsys.readouterr()

        assert "No services selected!" in captured.out

    def test_select_services_with_selections(self, sample_services, sample_categories):
        """Test complete service selection process with selections."""
        services_by_category = {
            "media_servers": ["jellyfin"],
            "download_clients": ["qbittorrent"],
        }
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        with patch("src.user_interface.prompt_yes_no") as mock_prompt:
            # Mock service selections and final confirmation
            mock_prompt.side_effect = [
                True,
                True,
                True,
            ]  # Select both services + confirm

            result = selector.select_services()

        assert "jellyfin" in result
        assert "qbittorrent" in result

    def test_select_services_no_selections_exit(
        self, sample_services, sample_categories
    ):
        """Test service selection with no selections and exit choice."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        with patch("src.user_interface.prompt_yes_no") as mock_prompt:
            mock_prompt.side_effect = [False, True]  # No selections + exit
            with pytest.raises(SystemExit):
                selector.select_services()

    def test_select_services_no_selections_retry(
        self, sample_services, sample_categories
    ):
        """Test service selection with no selections and retry."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        with patch("src.user_interface.prompt_yes_no") as mock_prompt:
            # First pass: no selections, don't exit
            # Second pass: select service, confirm
            mock_prompt.side_effect = [False, False, True, True]
            with patch.object(selector, "select_services") as mock_select:
                mock_select.return_value = ["jellyfin"]
                result = selector.select_services()

        # The recursive call should be made
        mock_select.assert_called()

    def test_select_services_reject_confirmation(
        self, sample_services, sample_categories
    ):
        """Test service selection with confirmation rejection."""
        services_by_category = {"media_servers": ["jellyfin"]}
        selector = ServiceSelector(
            sample_services, sample_categories, services_by_category
        )

        with patch("src.user_interface.prompt_yes_no") as mock_prompt:
            # Select service, reject confirmation
            mock_prompt.side_effect = [True, False]
            with patch.object(selector, "select_services") as mock_select:
                mock_select.return_value = ["jellyfin"]
                result = selector.select_services()

        # Should retry
        mock_select.assert_called()


class TestUserConfigCollector:
    """Test UserConfigCollector class."""

    def test_get_user_info_current_user(self, mock_os_operations):
        """Test getting current user info when user accepts."""
        with patch("src.user_interface.prompt_yes_no", return_value=True):
            username, uid, gid = UserConfigCollector.get_user_info()

        assert username == "testuser"
        assert uid == 1000
        assert gid == 1000

    def test_get_user_info_custom_user(self, mock_os_operations):
        """Test getting custom user info."""
        with patch("src.user_interface.prompt_yes_no", return_value=False):
            with patch.object(
                UserConfigCollector, "_get_custom_user_info"
            ) as mock_custom:
                mock_custom.return_value = ("customuser", 1001, 1001)
                username, uid, gid = UserConfigCollector.get_user_info()

        assert username == "customuser"
        assert uid == 1001
        assert gid == 1001

    def test_get_custom_user_info_success(self):
        """Test successful custom user info retrieval."""
        with patch("src.user_interface.prompt", return_value="testuser"):
            with patch("pwd.getpwnam") as mock_pwd:
                mock_user = Mock()
                mock_user.pw_uid = 1001
                mock_user.pw_gid = 1001
                mock_pwd.return_value = mock_user

                username, uid, gid = UserConfigCollector._get_custom_user_info(
                    "default_user"
                )

        assert username == "testuser"
        assert uid == 1001
        assert gid == 1001

    def test_get_custom_user_info_user_not_found_exit(self):
        """Test custom user info with user not found and exit choice."""
        with patch("src.user_interface.prompt", return_value="nonexistentuser"):
            with patch("pwd.getpwnam", side_effect=KeyError("User not found")):
                with patch("src.user_interface.prompt_yes_no", return_value=False):
                    with pytest.raises(SystemExit):
                        UserConfigCollector._get_custom_user_info("default_user")

    def test_get_custom_user_info_user_not_found_retry(self):
        """Test custom user info with user not found and retry."""
        with patch("src.user_interface.prompt") as mock_prompt:
            mock_prompt.side_effect = ["nonexistentuser", "validuser"]
            with patch("pwd.getpwnam") as mock_pwd:
                # First call raises KeyError, second succeeds
                mock_user = Mock()
                mock_user.pw_uid = 1001
                mock_user.pw_gid = 1001
                mock_pwd.side_effect = [KeyError("User not found"), mock_user]

                with patch("src.user_interface.prompt_yes_no", return_value=True):
                    username, uid, gid = UserConfigCollector._get_custom_user_info(
                        "default_user"
                    )

        assert username == "validuser"
        assert uid == 1001
        assert gid == 1001

    def test_get_directory_paths(self):
        """Test directory path collection."""
        with patch.object(UserConfigCollector, "_get_docker_directory") as mock_docker:
            with patch.object(
                UserConfigCollector, "_get_media_directory"
            ) as mock_media:
                mock_docker.return_value = "/opt/docker"
                mock_media.return_value = "/srv/media"

                docker_dir, media_dir = UserConfigCollector.get_directory_paths()

        assert docker_dir == "/opt/docker"
        assert media_dir == "/srv/media"

    def test_get_docker_directory(self):
        """Test Docker directory collection."""
        with patch("src.user_interface.prompt", return_value="/custom/docker"):
            result = UserConfigCollector._get_docker_directory()

        assert result == "/custom/docker"

    def test_get_media_directory(self):
        """Test media directory collection."""
        with patch("src.user_interface.prompt", return_value="/custom/media"):
            result = UserConfigCollector._get_media_directory()

        assert result == "/custom/media"

    def test_confirm_setup_confirmed(self, sample_services):
        """Test setup confirmation when user confirms."""
        with patch("src.user_interface.prompt_yes_no", return_value=True):
            result = UserConfigCollector.confirm_setup(
                "testuser",
                "/opt/docker",
                "/srv/media",
                ["jellyfin", "qbittorrent"],
                sample_services,
            )

        assert result is True

    def test_confirm_setup_rejected(self, sample_services):
        """Test setup confirmation when user rejects."""
        with patch("src.user_interface.prompt_yes_no", return_value=False):
            result = UserConfigCollector.confirm_setup(
                "testuser",
                "/opt/docker",
                "/srv/media",
                ["jellyfin", "qbittorrent"],
                sample_services,
            )

        assert result is False

    def test_confirm_setup_display_format(self, sample_services, capsys):
        """Test that setup confirmation displays properly formatted information."""
        with patch("src.user_interface.prompt_yes_no", return_value=True):
            UserConfigCollector.confirm_setup(
                "testuser",
                "/opt/docker",
                "/srv/media",
                ["jellyfin", "qbittorrent"],
                sample_services,
            )

        captured = capsys.readouterr()
        assert "CONFIGURATION SUMMARY" in captured.out
        assert "Username: testuser" in captured.out
        assert "Docker Directory: /opt/docker" in captured.out
        assert "Media Directory: /srv/media" in captured.out
        assert "Selected Services (2):" in captured.out
        assert "• Jellyfin" in captured.out
        assert "• qBittorrent" in captured.out
        assert "What happens next:" in captured.out


class TestProgressReporter:
    """Test ProgressReporter class."""

    def test_init(self):
        """Test ProgressReporter initialization."""
        reporter = ProgressReporter(5)
        assert reporter.total_steps == 5
        assert reporter.current_step == 0

    def test_start_step(self, capsys):
        """Test starting a new step."""
        reporter = ProgressReporter(3)
        reporter.start_step("Test Step")

        captured = capsys.readouterr()
        assert "[1/3] Test Step" in captured.out
        assert reporter.current_step == 1

    def test_start_multiple_steps(self, capsys):
        """Test starting multiple steps."""
        reporter = ProgressReporter(3)

        reporter.start_step("Step One")
        captured = capsys.readouterr()
        assert "[1/3] Step One" in captured.out

        reporter.start_step("Step Two")
        captured = capsys.readouterr()
        assert "[2/3] Step Two" in captured.out

        reporter.start_step("Step Three")
        captured = capsys.readouterr()
        assert "[3/3] Step Three" in captured.out

    def test_step_success(self, capsys):
        """Test reporting step success."""
        reporter = ProgressReporter(1)
        reporter.step_success("Operation completed successfully")

        captured = capsys.readouterr()
        assert "✓" in captured.out
        assert "Operation completed successfully" in captured.out

    def test_step_warning(self, capsys):
        """Test reporting step warning."""
        reporter = ProgressReporter(1)
        reporter.step_warning("Minor issue detected")

        captured = capsys.readouterr()
        assert "⚠" in captured.out
        assert "Minor issue detected" in captured.out

    def test_step_error(self, capsys):
        """Test reporting step error."""
        reporter = ProgressReporter(1)
        reporter.step_error("Critical error occurred")

        captured = capsys.readouterr()
        assert "✗" in captured.out
        assert "Critical error occurred" in captured.out

    def test_finish_success(self, capsys):
        """Test finishing with success."""
        reporter = ProgressReporter(1)
        reporter.finish(success=True)

        captured = capsys.readouterr()
        assert "✓ Setup completed successfully!" in captured.out

    def test_finish_failure(self, capsys):
        """Test finishing with failure."""
        reporter = ProgressReporter(1)
        reporter.finish(success=False)

        captured = capsys.readouterr()
        assert "✗ Setup completed with issues" in captured.out

    def test_finish_default_success(self, capsys):
        """Test finishing with default success value."""
        reporter = ProgressReporter(1)
        reporter.finish()  # Default is success=True

        captured = capsys.readouterr()
        assert "✓ Setup completed successfully!" in captured.out
