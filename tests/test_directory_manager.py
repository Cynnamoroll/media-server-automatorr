"""
Tests for directory_manager module.
"""

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.directory_manager import DirectoryManager


class TestDirectoryManager:
    """Test DirectoryManager class."""

    def test_create_single_directory_success(self, temp_dir):
        """Test successful single directory creation."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"

        success, error = manager._create_single_directory(test_dir, 1000, 1000)

        assert success is True
        assert error == ""
        assert test_dir.exists()
        assert test_dir in manager.created_directories

    def test_create_single_directory_with_parents(self, temp_dir):
        """Test directory creation with parent directories."""
        manager = DirectoryManager()
        test_dir = temp_dir / "parent" / "child" / "grandchild"

        success, error = manager._create_single_directory(test_dir, 1000, 1000)

        assert success is True
        assert error == ""
        assert test_dir.exists()
        assert test_dir.parent.exists()
        assert test_dir.parent.parent.exists()

    def test_create_single_directory_permission_error(self, temp_dir):
        """Test directory creation with permission error and sudo fallback."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"

        with patch.object(Path, "mkdir", side_effect=PermissionError("Access denied")):
            with patch("src.directory_manager.run_command") as mock_run:
                mock_run.return_value = None  # Successful sudo mkdir
                with patch.object(
                    manager, "_set_directory_ownership", return_value=True
                ):
                    success, error = manager._create_single_directory(
                        test_dir, 1000, 1000
                    )

        assert success is True
        assert error == ""
        mock_run.assert_called_with(["mkdir", "-p", str(test_dir)], sudo=True)

    def test_create_single_directory_complete_failure(self, temp_dir):
        """Test directory creation complete failure."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"

        with patch.object(Path, "mkdir", side_effect=PermissionError("Access denied")):
            with patch(
                "src.directory_manager.run_command",
                side_effect=Exception("Sudo failed"),
            ):
                success, error = manager._create_single_directory(test_dir, 1000, 1000)

        assert success is False
        assert "Failed to create" in error

    def test_set_directory_ownership_as_root(self, temp_dir):
        """Test setting directory ownership as root."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        with patch("os.geteuid", return_value=0):  # Root user
            with patch("src.directory_manager.run_command") as mock_run:
                result = manager._set_directory_ownership(
                    test_dir, 1000, 1000, use_sudo=True
                )

        assert result is True
        mock_run.assert_called()

    def test_set_directory_ownership_with_sudo(self, temp_dir):
        """Test setting directory ownership with sudo."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        with patch("os.geteuid", return_value=1000):  # Non-root user
            with patch("src.directory_manager.run_command") as mock_run:
                result = manager._set_directory_ownership(
                    test_dir, 1000, 1000, use_sudo=True
                )

        assert result is True
        mock_run.assert_called()

    def test_set_directory_ownership_failure(self, temp_dir):
        """Test directory ownership setting failure."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        with patch(
            "src.directory_manager.run_command", side_effect=Exception("Failed")
        ):
            result = manager._set_directory_ownership(
                test_dir, 1000, 1000, use_sudo=True
            )

        assert result is False

    def test_create_directory_structure_success(self, temp_dir):
        """Test successful directory structure creation."""
        manager = DirectoryManager()
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"

        success, errors = manager.create_directory_structure(
            docker_dir, media_dir, 1000, 1000
        )

        assert success is True
        assert errors == []
        assert docker_dir.exists()
        assert media_dir.exists()
        assert (docker_dir / "compose").exists()
        assert (media_dir / "downloads" / "incomplete").exists()
        assert (media_dir / "downloads" / "complete").exists()
        assert (media_dir / "movies").exists()
        assert (media_dir / "tv").exists()
        assert (media_dir / "music").exists()
        assert (media_dir / "books").exists()
        assert (media_dir / "comics").exists()
        assert (media_dir / "podcasts").exists()
        assert (media_dir / "audiobooks").exists()

    def test_create_directory_structure_partial_failure(self, temp_dir):
        """Test directory structure creation with partial failures."""
        manager = DirectoryManager()
        docker_dir = temp_dir / "docker"
        media_dir = temp_dir / "media"

        # Mock one directory creation to fail
        original_create = manager._create_single_directory

        def mock_create(directory, uid, gid):
            if "movies" in str(directory):
                return False, "Failed to create movies directory"
            return original_create(directory, uid, gid)

        manager._create_single_directory = mock_create

        success, errors = manager.create_directory_structure(
            docker_dir, media_dir, 1000, 1000
        )

        assert success is False
        assert len(errors) == 1
        assert "Failed to create movies directory" in errors[0]

    def test_create_service_directories_success(self, temp_dir):
        """Test successful service directories creation."""
        manager = DirectoryManager()
        docker_dir = temp_dir / "docker"
        services = ["jellyfin", "qbittorrent", "sonarr"]

        success, errors = manager.create_service_directories(
            docker_dir, services, 1000, 1000
        )

        assert success is True
        assert errors == []
        assert (docker_dir / "jellyfin" / "config").exists()
        assert (docker_dir / "qbittorrent" / "config").exists()
        assert (docker_dir / "sonarr" / "config").exists()

    def test_fix_permissions_success(self, temp_dir):
        """Test successful permission fixing."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        # Add directory to permission fixes needed
        manager.permission_fixes_needed.append(test_dir)

        with patch.object(manager, "_set_directory_ownership", return_value=True):
            failed_fixes = manager.fix_permissions(1000, 1000)

        assert failed_fixes == []

    def test_fix_permissions_failure(self, temp_dir):
        """Test permission fixing with failures."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        # Add directory to permission fixes needed
        manager.permission_fixes_needed.append(test_dir)

        with patch.object(manager, "_set_directory_ownership", return_value=False):
            failed_fixes = manager.fix_permissions(1000, 1000)

        assert len(failed_fixes) == 1
        assert str(test_dir) in failed_fixes[0]

    def test_validate_directory_access_success(self, temp_dir):
        """Test successful directory access validation."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        issues = manager.validate_directory_access([test_dir], 1000)

        assert issues == []

    def test_validate_directory_access_not_exists(self, temp_dir):
        """Test directory access validation for non-existent directory."""
        manager = DirectoryManager()
        test_dir = temp_dir / "non_existent"

        issues = manager.validate_directory_access([test_dir], 1000)

        assert len(issues) == 1
        assert "Does not exist" in issues[0]

    def test_validate_directory_access_not_directory(self, temp_dir):
        """Test directory access validation for file instead of directory."""
        manager = DirectoryManager()
        test_file = temp_dir / "test_file.txt"
        test_file.write_text("test content")

        issues = manager.validate_directory_access([test_file], 1000)

        assert len(issues) == 1
        assert "Not a directory" in issues[0]

    def test_validate_directory_access_no_read_permission(self, temp_dir):
        """Test directory access validation with no read permission."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        with patch.object(
            Path, "iterdir", side_effect=PermissionError("No read access")
        ):
            issues = manager.validate_directory_access([test_dir], 1000)

        assert len(issues) == 1
        assert "No read access" in issues[0]

    def test_validate_directory_access_no_write_permission(self, temp_dir):
        """Test directory access validation with no write permission."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        with patch.object(
            Path, "touch", side_effect=PermissionError("No write access")
        ):
            issues = manager.validate_directory_access([test_dir], 1000)

        assert len(issues) == 1
        assert "No write access" in issues[0]

    def test_get_directory_info_exists(self, temp_dir):
        """Test getting directory information for existing directory."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        # Create some test files
        (test_dir / "file1.txt").write_text("content1")
        (test_dir / "file2.txt").write_text("content2")

        info = manager.get_directory_info(test_dir)

        assert info["exists"] is True
        assert info["is_directory"] is True
        assert "owner_uid" in info
        assert "owner_gid" in info
        assert "permissions" in info
        assert info["file_count"] >= 2

    def test_get_directory_info_not_exists(self, temp_dir):
        """Test getting directory information for non-existent directory."""
        manager = DirectoryManager()
        test_dir = temp_dir / "non_existent"

        info = manager.get_directory_info(test_dir)

        assert info["exists"] is False

    def test_get_directory_info_error(self, temp_dir):
        """Test getting directory information with error."""
        manager = DirectoryManager()
        test_dir = temp_dir / "test_directory"
        test_dir.mkdir()

        with patch.object(Path, "stat", side_effect=Exception("Access error")):
            info = manager.get_directory_info(test_dir)

        assert info["exists"] is True
        assert "error" in info

    def test_cleanup_empty_directories_success(self, temp_dir):
        """Test successful cleanup of empty directories."""
        manager = DirectoryManager()

        # Create nested empty directories
        empty_dir1 = temp_dir / "empty1"
        empty_dir1.mkdir()
        empty_dir2 = temp_dir / "parent" / "empty2"
        empty_dir2.mkdir(parents=True)

        # Create non-empty directory
        non_empty_dir = temp_dir / "non_empty"
        non_empty_dir.mkdir()
        (non_empty_dir / "file.txt").write_text("content")

        removed_count = manager.cleanup_empty_directories(temp_dir)

        assert removed_count >= 1  # At least some empty directories removed
        assert not empty_dir1.exists()

    def test_cleanup_empty_directories_not_exists(self, temp_dir):
        """Test cleanup of empty directories for non-existent path."""
        manager = DirectoryManager()
        non_existent = temp_dir / "non_existent"

        removed_count = manager.cleanup_empty_directories(non_existent)

        assert removed_count == 0

    def test_get_disk_usage_success(self, temp_dir):
        """Test successful disk usage retrieval."""
        manager = DirectoryManager()

        usage = manager.get_disk_usage(temp_dir)

        assert "total_gb" in usage
        assert "used_gb" in usage
        assert "free_gb" in usage
        assert "used_percent" in usage
        assert usage["total_gb"] > 0
        assert usage["used_percent"] >= 0
        assert usage["used_percent"] <= 100

    def test_get_disk_usage_error(self, temp_dir):
        """Test disk usage retrieval with error."""
        manager = DirectoryManager()

        with patch("shutil.disk_usage", side_effect=Exception("Disk error")):
            usage = manager.get_disk_usage(temp_dir)

        assert "error" in usage
        assert "Disk error" in usage["error"]
