"""
Tests for utils module.
"""

import socket
import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.utils import (
    Colors,
    generate_encryption_key,
    get_docker_network_subnet,
    get_local_network_ip,
    get_timezone,
    print_error,
    print_header,
    print_info,
    print_link,
    print_success,
    print_warning,
    prompt,
    prompt_secret,
    prompt_yes_no,
    replace_placeholders,
    run_command,
    validate_subnet_format,
    wait_for_done,
)


class TestPrintFunctions:
    """Test print utility functions."""

    def test_print_header(self, capsys):
        """Test print_header function."""
        print_header("Test Header")
        captured = capsys.readouterr()

        assert "Test Header" in captured.out
        assert "=" * len("Test Header") in captured.out
        assert Colors.BOLD in captured.out
        assert Colors.CYAN in captured.out

    def test_print_success(self, capsys):
        """Test print_success function."""
        print_success("Success message")
        captured = capsys.readouterr()

        assert "✓ Success message" in captured.out
        assert Colors.GREEN in captured.out

    def test_print_warning(self, capsys):
        """Test print_warning function."""
        print_warning("Warning message")
        captured = capsys.readouterr()

        assert "⚠ Warning message" in captured.out
        assert Colors.YELLOW in captured.out

    def test_print_error(self, capsys):
        """Test print_error function."""
        print_error("Error message")
        captured = capsys.readouterr()

        assert "✗ Error message" in captured.out
        assert Colors.RED in captured.out

    def test_print_info(self, capsys):
        """Test print_info function."""
        print_info("Info message")
        captured = capsys.readouterr()

        assert "ℹ Info message" in captured.out
        assert Colors.CYAN in captured.out

    def test_print_link(self, capsys):
        """Test print_link function."""
        print_link("Test Link", "https://example.com")
        captured = capsys.readouterr()

        assert "Test Link: https://example.com" in captured.out
        assert Colors.UNDERLINE in captured.out
        assert Colors.BLUE in captured.out


class TestPromptFunctions:
    """Test user prompt functions."""

    def test_prompt_with_default(self, monkeypatch):
        """Test prompt function with default value."""
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = prompt("Test question", "default_value")
        assert result == "default_value"

    def test_prompt_with_user_input(self, monkeypatch):
        """Test prompt function with user input."""
        monkeypatch.setattr("builtins.input", lambda _: "user_input")
        result = prompt("Test question", "default_value")
        assert result == "user_input"

    def test_prompt_no_default(self, monkeypatch):
        """Test prompt function without default."""
        monkeypatch.setattr("builtins.input", lambda _: "user_input")
        result = prompt("Test question")
        assert result == "user_input"

    def test_prompt_secret(self, monkeypatch):
        """Test prompt_secret function."""
        with patch("getpass.getpass", return_value="secret_value"):
            result = prompt_secret("Enter secret")
            assert result == "secret_value"

    def test_prompt_secret_keyboard_interrupt(self, monkeypatch):
        """Test prompt_secret with keyboard interrupt."""
        with patch("getpass.getpass", side_effect=KeyboardInterrupt()):
            with pytest.raises(SystemExit):
                prompt_secret("Enter secret")

    def test_prompt_yes_no_yes_responses(self, monkeypatch):
        """Test prompt_yes_no with various yes responses."""
        yes_responses = ["y", "yes", "true", "1", "Y", "YES", "True"]

        for response in yes_responses:
            monkeypatch.setattr("builtins.input", lambda _: response)
            result = prompt_yes_no("Test question?", default=False)
            assert result is True

    def test_prompt_yes_no_no_responses(self, monkeypatch):
        """Test prompt_yes_no with various no responses."""
        no_responses = ["n", "no", "false", "0", "N", "NO", "False"]

        for response in no_responses:
            monkeypatch.setattr("builtins.input", lambda _: response)
            result = prompt_yes_no("Test question?", default=True)
            assert result is False

    def test_prompt_yes_no_default_true(self, monkeypatch):
        """Test prompt_yes_no with default True."""
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = prompt_yes_no("Test question?", default=True)
        assert result is True

    def test_prompt_yes_no_default_false(self, monkeypatch):
        """Test prompt_yes_no with default False."""
        monkeypatch.setattr("builtins.input", lambda _: "")
        result = prompt_yes_no("Test question?", default=False)
        assert result is False

    def test_prompt_yes_no_invalid_then_valid(self, monkeypatch, capsys):
        """Test prompt_yes_no with invalid then valid response."""
        responses = iter(["maybe", "invalid", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))

        result = prompt_yes_no("Test question?", default=False)
        assert result is True

        captured = capsys.readouterr()
        assert "Please answer yes or no" in captured.out

    def test_wait_for_done_enter(self, monkeypatch):
        """Test wait_for_done with Enter key."""
        monkeypatch.setattr("builtins.input", lambda _: "")
        # Should not raise any exception
        wait_for_done(1, 3)

    def test_wait_for_done_skip(self, monkeypatch, capsys):
        """Test wait_for_done with skip."""
        monkeypatch.setattr("builtins.input", lambda _: "skip")
        wait_for_done(2, 5)

        captured = capsys.readouterr()
        assert "Step skipped" in captured.out

    def test_wait_for_done_invalid_then_valid(self, monkeypatch, capsys):
        """Test wait_for_done with invalid then valid response."""
        responses = iter(["invalid", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(responses))

        wait_for_done(1, 1)

        captured = capsys.readouterr()
        assert "Press Enter to continue" in captured.out


class TestSystemUtilities:
    """Test system utility functions."""

    def test_run_command_success(self):
        """Test successful command execution."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="success")

            result = run_command(["echo", "test"])

            assert result.returncode == 0
            mock_run.assert_called_once()

    def test_run_command_with_sudo(self):
        """Test command execution with sudo."""
        with patch("subprocess.run") as mock_run:
            with patch("os.geteuid", return_value=1000):  # Non-root user
                mock_run.return_value = MagicMock(returncode=0)

                run_command(["mkdir", "test"], sudo=True)

                # Should prepend sudo
                call_args = mock_run.call_args[0][0]
                assert call_args[0] == "sudo"
                assert call_args[1:] == ["mkdir", "test"]

    def test_run_command_as_root_no_sudo(self):
        """Test command execution as root doesn't add sudo."""
        with patch("subprocess.run") as mock_run:
            with patch("os.geteuid", return_value=0):  # Root user
                mock_run.return_value = MagicMock(returncode=0)

                run_command(["mkdir", "test"], sudo=True)

                # Should not prepend sudo
                call_args = mock_run.call_args[0][0]
                assert call_args == ["mkdir", "test"]

    def test_run_command_failure(self):
        """Test command execution failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["false"])

            # Should raise exception with check=True (default)
            with pytest.raises(subprocess.CalledProcessError):
                run_command(["false"])

    def test_run_command_no_check(self):
        """Test command execution without check."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")

            result = run_command(["false"], check=False)
            assert result.returncode == 1

    def test_generate_encryption_key(self):
        """Test encryption key generation."""
        key = generate_encryption_key()

        assert isinstance(key, str)
        assert len(key) == 32
        # Should only contain alphanumeric characters
        assert key.isalnum()

    def test_generate_encryption_key_uniqueness(self):
        """Test that generated keys are unique."""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()

        assert key1 != key2

    def test_get_timezone_success(self):
        """Test successful timezone detection."""
        with patch("src.utils.run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout="America/New_York\n")

            timezone = get_timezone()
            assert timezone == "America/New_York"

    def test_get_timezone_failure(self):
        """Test timezone detection failure."""
        with patch(
            "src.utils.run_command", side_effect=subprocess.CalledProcessError(1, "cmd")
        ):
            timezone = get_timezone()
            assert timezone == "UTC"

    def test_get_timezone_file_not_found(self):
        """Test timezone detection with missing timedatectl."""
        with patch("src.utils.run_command", side_effect=FileNotFoundError()):
            timezone = get_timezone()
            assert timezone == "UTC"

    def test_get_timezone_empty_result(self):
        """Test timezone detection with empty result."""
        with patch("src.utils.run_command") as mock_run:
            mock_run.return_value = MagicMock(stdout="")

            timezone = get_timezone()
            assert timezone == "UTC"


class TestNetworkUtilities:
    """Test network utility functions."""

    def test_get_local_network_ip_via_ip_route(self):
        """Test local IP detection via ip route."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="192.168.1.1 dev eth0 src 192.168.1.100 uid 1000"
            )

            ip = get_local_network_ip()
            assert ip == "192.168.1.100"

    def test_get_local_network_ip_via_hostname(self):
        """Test local IP detection via hostname -I."""
        with patch("subprocess.run") as mock_run:
            # First call (ip route) fails, second call (hostname -I) succeeds
            mock_run.side_effect = [
                subprocess.CalledProcessError(1, "cmd"),
                MagicMock(returncode=0, stdout="192.168.1.100 127.0.0.1"),
            ]

            ip = get_local_network_ip()
            assert ip == "192.168.1.100"

    def test_get_local_network_ip_via_ifconfig(self):
        """Test local IP detection via ifconfig."""
        with patch("subprocess.run") as mock_run:
            # First two calls fail, ifconfig succeeds
            mock_run.side_effect = [
                subprocess.CalledProcessError(1, "cmd"),
                subprocess.CalledProcessError(1, "cmd"),
                MagicMock(returncode=0, stdout="inet 192.168.1.100 netmask"),
            ]

            ip = get_local_network_ip()
            assert ip == "192.168.1.100"

    def test_get_local_network_ip_via_socket(self):
        """Test local IP detection via socket."""
        with patch(
            "subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")
        ):
            with patch("socket.socket") as mock_socket:
                mock_sock_instance = MagicMock()
                mock_sock_instance.getsockname.return_value = ("192.168.1.100", 12345)
                mock_socket.return_value = mock_sock_instance

                ip = get_local_network_ip()
                assert ip == "192.168.1.100"

    def test_get_local_network_ip_fallback_localhost(self):
        """Test local IP detection fallback to localhost."""
        with patch(
            "subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")
        ):
            with patch("socket.socket", side_effect=Exception("Socket error")):
                ip = get_local_network_ip()
                assert ip == "localhost"

    def test_get_docker_network_subnet_via_inspect(self):
        """Test Docker subnet detection via network inspect."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='[{"IPAM":{"Config":[{"Subnet":"172.17.0.0/16"}]}}]',
            )

            subnet = get_docker_network_subnet()
            assert subnet == "172.17.0.0/16"

    def test_get_docker_network_subnet_fallback(self):
        """Test Docker subnet detection fallback."""
        with patch(
            "subprocess.run", side_effect=subprocess.CalledProcessError(1, "cmd")
        ):
            subnet = get_docker_network_subnet()
            assert subnet == "172.17.0.0/16"  # Default fallback

    def test_get_docker_network_subnet_invalid_json(self):
        """Test Docker subnet detection with invalid JSON."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="invalid json")

            subnet = get_docker_network_subnet()
            assert subnet == "172.17.0.0/16"  # Fallback

    def test_get_docker_network_subnet_timeout(self):
        """Test Docker subnet detection with timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
            subnet = get_docker_network_subnet()
            assert subnet == "172.17.0.0/16"  # Fallback

    def test_validate_subnet_format_valid(self):
        """Test valid subnet format validation."""
        valid_subnets = ["192.168.1.0/24", "10.0.0.0/8", "172.16.0.0/16", "0.0.0.0/0"]

        for subnet in valid_subnets:
            assert validate_subnet_format(subnet) is True

    def test_validate_subnet_format_invalid(self):
        """Test invalid subnet format validation."""
        invalid_subnets = [
            "",
            "192.168.1.0",
            "192.168.1.0/",
            "192.168.1.0/33",
            "256.1.1.1/24",
            "192.168.1/24",
            "not.a.subnet/24",
            "192.168.1.0/-1",
        ]

        for subnet in invalid_subnets:
            assert validate_subnet_format(subnet) is False

    def test_replace_placeholders(self):
        """Test placeholder replacement."""
        template = "Hello {name}, your age is {age} and city is {city}"
        replacements = {"name": "John", "age": "30", "city": "New York"}

        result = replace_placeholders(template, replacements)
        expected = "Hello John, your age is 30 and city is New York"
        assert result == expected

    def test_replace_placeholders_missing_keys(self):
        """Test placeholder replacement with missing keys."""
        template = "Hello {name}, your age is {age}"
        replacements = {"name": "John"}

        result = replace_placeholders(template, replacements)
        # Missing keys should remain as placeholders
        assert result == "Hello John, your age is {age}"

    def test_replace_placeholders_extra_keys(self):
        """Test placeholder replacement with extra keys."""
        template = "Hello {name}"
        replacements = {"name": "John", "age": "30", "city": "New York"}

        result = replace_placeholders(template, replacements)
        assert result == "Hello John"

    def test_replace_placeholders_empty_template(self):
        """Test placeholder replacement with empty template."""
        result = replace_placeholders("", {"key": "value"})
        assert result == ""

    def test_replace_placeholders_empty_replacements(self):
        """Test placeholder replacement with empty replacements."""
        template = "Hello {name}"
        result = replace_placeholders(template, {})
        assert result == "Hello {name}"
