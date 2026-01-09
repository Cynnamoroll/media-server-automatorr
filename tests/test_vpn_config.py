"""
Tests for vpn_config module.
"""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.vpn_config import GluetunConfigurator


class TestGluetunConfigurator:
    """Test GluetunConfigurator class."""

    def test_init(self):
        """Test GluetunConfigurator initialization."""
        config = GluetunConfigurator()

        assert config.enabled is False
        assert config.provider is None
        assert config.vpn_type == "openvpn"
        assert config.credentials == {}
        assert config.server_countries == ""
        assert config.route_qbittorrent is False
        assert config.docker_subnet == ""
        assert "OPENVPN_PASSWORD" in config.optional_fields
        assert "WIREGUARD_PRESHARED_KEY" in config.optional_fields

    def test_configure_declined(self):
        """Test configuration when user declines VPN."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt_yes_no", return_value=False):
            result = config.configure()

        assert result is False
        assert config.enabled is False

    def test_configure_accepted_nordvpn_openvpn(self):
        """Test complete VPN configuration for NordVPN with OpenVPN."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt_yes_no") as mock_prompt:
            with patch("src.vpn_config.prompt") as mock_input:
                with patch("src.vpn_config.prompt_secret") as mock_secret:
                    with patch(
                        "src.vpn_config.get_docker_network_subnet"
                    ) as mock_subnet:
                        # Configure mocks
                        mock_prompt.side_effect = [
                            True,  # Would you like to configure VPN?
                            True,  # Route qBittorrent through VPN?
                        ]
                        mock_input.side_effect = [
                            "1",  # Select NordVPN
                            "1",  # Select OpenVPN
                            "testuser",  # OpenVPN user
                            "Netherlands,Germany",  # Server countries
                            "",  # Accept auto-detected subnet
                        ]
                        mock_secret.return_value = "testpass"  # OpenVPN password
                        mock_subnet.return_value = "172.17.0.0/16"

                        result = config.configure()

        assert result is True
        assert config.enabled is True
        assert config.provider == "nordvpn"
        assert config.vpn_type == "openvpn"
        assert config.credentials["OPENVPN_USER"] == "testuser"
        assert config.credentials["OPENVPN_PASSWORD"] == "testpass"
        assert config.server_countries == "Netherlands,Germany"
        assert config.route_qbittorrent is True
        assert config.docker_subnet == "172.17.0.0/16"

    def test_configure_mullvad_wireguard(self):
        """Test VPN configuration for Mullvad with WireGuard."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt_yes_no") as mock_prompt:
            with patch("src.vpn_config.prompt") as mock_input:
                with patch("src.vpn_config.prompt_secret") as mock_secret:
                    with patch(
                        "src.vpn_config.get_docker_network_subnet"
                    ) as mock_subnet:
                        # Configure mocks
                        mock_prompt.side_effect = [
                            True,  # Would you like to configure VPN?
                            False,  # Don't route qBittorrent through VPN
                        ]
                        mock_input.side_effect = [
                            "2",  # Select Mullvad
                            "2",  # Select WireGuard
                            "10.64.0.1/32",  # WireGuard addresses (uses prompt, not prompt_secret)
                            "",  # No server countries
                            "",  # Accept auto-detected subnet
                        ]
                        mock_secret.side_effect = [
                            "wg_private_key_here",  # WireGuard private key
                        ]
                        mock_subnet.return_value = "172.17.0.0/16"

                        result = config.configure()

        assert result is True
        assert config.enabled is True
        assert config.provider == "mullvad"
        assert config.vpn_type == "wireguard"
        assert config.credentials["WIREGUARD_PRIVATE_KEY"] == "wg_private_key_here"
        assert config.credentials["WIREGUARD_ADDRESSES"] == "10.64.0.1/32"
        assert config.server_countries == ""
        assert config.route_qbittorrent is False

    def test_configure_custom_provider(self):
        """Test VPN configuration with custom provider."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt_yes_no") as mock_prompt:
            with patch("src.vpn_config.prompt") as mock_input:
                with patch("src.vpn_config.get_docker_network_subnet") as mock_subnet:
                    # Configure mocks
                    mock_prompt.side_effect = [
                        True,  # Would you like to configure VPN?
                        True,  # Route qBittorrent through VPN?
                    ]
                    mock_input.side_effect = [
                        "8",  # Select "Other (manual configuration)"
                        "",  # Accept auto-detected subnet
                    ]
                    mock_subnet.return_value = "172.17.0.0/16"

                    result = config.configure()

        assert result is True
        assert config.enabled is True
        assert config.provider == "custom"
        assert config.route_qbittorrent is True

    def test_select_provider_invalid_then_valid(self):
        """Test provider selection with invalid then valid choice."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt") as mock_input:
            mock_input.side_effect = ["99", "abc", "1"]  # Invalid, invalid, valid

            config._select_provider()

        assert config.provider == "nordvpn"

    def test_select_vpn_type_provider_supports_both(self):
        """Test VPN type selection when provider supports both protocols."""
        config = GluetunConfigurator()
        config.provider = "nordvpn"  # Supports both

        with patch("src.vpn_config.prompt") as mock_input:
            mock_input.return_value = "2"  # Select WireGuard

            config._select_vpn_type()

        assert config.vpn_type == "wireguard"

    def test_select_vpn_type_openvpn_only(self):
        """Test VPN type selection for OpenVPN-only provider."""
        config = GluetunConfigurator()
        config.provider = "expressvpn"  # OpenVPN only

        config._select_vpn_type()

        assert config.vpn_type == "openvpn"

    def test_select_vpn_type_wireguard_only(self):
        """Test VPN type selection for WireGuard-only provider."""
        config = GluetunConfigurator()
        config.provider = "custom_wg"  # Would need to be added to constants

        # Mock provider info for WireGuard-only
        with patch(
            "src.vpn_config.VPN_PROVIDERS",
            {
                "custom_wg": {
                    "name": "Custom WG",
                    "supports_openvpn": False,
                    "supports_wireguard": True,
                }
            },
        ):
            config._select_vpn_type()

        assert config.vpn_type == "wireguard"

    def test_collect_credentials_custom_provider(self):
        """Test credential collection for custom provider."""
        config = GluetunConfigurator()
        config.provider = "custom"

        config._collect_credentials()

        # Should not collect credentials for custom provider
        assert config.credentials == {}

    def test_collect_credentials_with_optional_fields(self):
        """Test credential collection with optional fields."""
        config = GluetunConfigurator()
        config.provider = "nordvpn"
        config.vpn_type = "openvpn"

        with patch("src.vpn_config.prompt") as mock_input:
            with patch("src.vpn_config.prompt_secret") as mock_secret:
                mock_input.return_value = "testuser"
                mock_secret.return_value = ""  # Empty password (optional)

                config._collect_credentials()

        assert config.credentials["OPENVPN_USER"] == "testuser"
        assert config.credentials["OPENVPN_PASSWORD"] == ""

    def test_collect_credentials_required_field_retry(self):
        """Test credential collection with required field retry."""
        config = GluetunConfigurator()
        config.provider = "nordvpn"
        config.vpn_type = "openvpn"

        with patch("src.vpn_config.prompt") as mock_input:
            with patch("src.vpn_config.prompt_secret") as mock_secret:
                # First empty (should retry), then valid
                mock_input.side_effect = ["", "testuser"]
                mock_secret.return_value = "testpass"

                config._collect_credentials()

        assert config.credentials["OPENVPN_USER"] == "testuser"
        assert config.credentials["OPENVPN_PASSWORD"] == "testpass"

    def test_configure_server_location_specified(self):
        """Test server location configuration with specific countries."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt") as mock_input:
            mock_input.return_value = "Netherlands,Germany,Sweden"

            config._configure_server_location()

        assert config.server_countries == "Netherlands,Germany,Sweden"

    def test_configure_server_location_empty(self):
        """Test server location configuration with empty input."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt") as mock_input:
            mock_input.return_value = ""

            config._configure_server_location()

        assert config.server_countries == ""

    def test_configure_docker_network_auto_detected(self):
        """Test Docker network configuration with auto-detection."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.get_docker_network_subnet") as mock_subnet:
            with patch("src.vpn_config.prompt") as mock_input:
                mock_subnet.return_value = "172.18.0.0/16"
                mock_input.return_value = ""  # Accept auto-detected

                config._configure_docker_network()

        assert config.docker_subnet == "172.18.0.0/16"

    def test_configure_docker_network_custom_valid(self):
        """Test Docker network configuration with valid custom subnet."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.get_docker_network_subnet") as mock_subnet:
            with patch("src.vpn_config.prompt") as mock_input:
                mock_subnet.return_value = "172.17.0.0/16"
                mock_input.return_value = "192.168.100.0/24"  # Custom subnet

                config._configure_docker_network()

        assert config.docker_subnet == "192.168.100.0/24"

    def test_configure_docker_network_custom_invalid(self):
        """Test Docker network configuration with invalid custom subnet."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.get_docker_network_subnet") as mock_subnet:
            with patch("src.vpn_config.prompt") as mock_input:
                mock_subnet.return_value = "172.17.0.0/16"
                mock_input.return_value = "invalid.subnet"  # Invalid format

                config._configure_docker_network()

        # Should fall back to auto-detected
        assert config.docker_subnet == "172.17.0.0/16"

    def test_configure_qbittorrent_routing_enabled(self):
        """Test qBittorrent routing configuration - enabled."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt_yes_no") as mock_prompt:
            mock_prompt.return_value = True

            config._configure_qbittorrent_routing()

        assert config.route_qbittorrent is True

    def test_configure_qbittorrent_routing_disabled(self):
        """Test qBittorrent routing configuration - disabled."""
        config = GluetunConfigurator()

        with patch("src.vpn_config.prompt_yes_no") as mock_prompt:
            mock_prompt.return_value = False

            config._configure_qbittorrent_routing()

        assert config.route_qbittorrent is False

    def test_get_environment_vars_disabled(self):
        """Test environment variable generation when disabled."""
        config = GluetunConfigurator()
        config.enabled = False

        env_vars = config.get_environment_vars()

        assert env_vars == {}

    def test_get_environment_vars_custom_provider(self):
        """Test environment variable generation for custom provider."""
        config = GluetunConfigurator()
        config.enabled = True
        config.provider = "custom"

        env_vars = config.get_environment_vars()

        assert env_vars == {}

    def test_get_environment_vars_complete_config(self):
        """Test environment variable generation with complete configuration."""
        config = GluetunConfigurator()
        config.enabled = True
        config.provider = "nordvpn"
        config.vpn_type = "openvpn"
        config.credentials = {
            "OPENVPN_USER": "testuser",
            "OPENVPN_PASSWORD": "testpass",
        }
        config.server_countries = "Netherlands,Germany"
        config.docker_subnet = "172.17.0.0/16"

        env_vars = config.get_environment_vars()

        assert env_vars["VPN_SERVICE_PROVIDER"] == "nordvpn"
        assert env_vars["VPN_TYPE"] == "openvpn"
        assert env_vars["OPENVPN_USER"] == "testuser"
        assert env_vars["OPENVPN_PASSWORD"] == "testpass"
        assert env_vars["SERVER_COUNTRIES"] == "Netherlands,Germany"
        assert env_vars["FIREWALL_OUTBOUND_SUBNETS"] == "172.17.0.0/16"

    def test_get_environment_vars_empty_credentials(self):
        """Test environment variable generation with empty credentials."""
        config = GluetunConfigurator()
        config.enabled = True
        config.provider = "nordvpn"
        config.vpn_type = "openvpn"
        config.credentials = {
            "OPENVPN_USER": "testuser",
            "OPENVPN_PASSWORD": "",  # Empty password
        }

        env_vars = config.get_environment_vars()

        assert env_vars["OPENVPN_USER"] == "testuser"
        assert "OPENVPN_PASSWORD" not in env_vars  # Should not include empty values

    def test_get_environment_vars_no_server_countries(self):
        """Test environment variable generation without server countries."""
        config = GluetunConfigurator()
        config.enabled = True
        config.provider = "nordvpn"
        config.vpn_type = "openvpn"
        config.credentials = {"OPENVPN_USER": "testuser"}
        config.server_countries = ""  # No server countries specified

        env_vars = config.get_environment_vars()

        assert "SERVER_COUNTRIES" not in env_vars

    def test_get_environment_vars_no_docker_subnet(self):
        """Test environment variable generation without Docker subnet."""
        config = GluetunConfigurator()
        config.enabled = True
        config.provider = "nordvpn"
        config.vpn_type = "openvpn"
        config.credentials = {"OPENVPN_USER": "testuser"}
        config.docker_subnet = ""  # No Docker subnet specified

        env_vars = config.get_environment_vars()

        assert "FIREWALL_OUTBOUND_SUBNETS" not in env_vars

    def test_vpn_provider_constants_validation(self):
        """Test that VPN provider constants have required fields."""
        from src.constants import VPN_PROVIDERS

        for provider_id, provider_info in VPN_PROVIDERS.items():
            # Required fields
            assert "name" in provider_info
            assert "provider_name" in provider_info
            assert "supports_openvpn" in provider_info
            assert "supports_wireguard" in provider_info
            assert "credentials_url" in provider_info
            assert "credentials_note" in provider_info

            # At least one protocol should be supported
            assert (
                provider_info["supports_openvpn"] or provider_info["supports_wireguard"]
            )

            # Protocol-specific fields
            if provider_info["supports_openvpn"]:
                assert "openvpn_fields" in provider_info
                assert isinstance(provider_info["openvpn_fields"], list)

            if provider_info["supports_wireguard"]:
                assert "wireguard_fields" in provider_info
                assert isinstance(provider_info["wireguard_fields"], list)
