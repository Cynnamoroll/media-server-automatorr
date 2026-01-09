"""
Directory management utilities for media-server-automatorr.
"""

import os
from pathlib import Path
from typing import List, Tuple

from .utils import print_error, print_info, print_success, print_warning, run_command


class DirectoryManager:
    """Handles directory creation and permission management."""

    def __init__(self):
        self.created_directories: List[Path] = []
        self.permission_fixes_needed: List[Path] = []

    def create_directory_structure(
        self, docker_dir: Path, media_dir: Path, uid: int, gid: int
    ) -> Tuple[bool, List[str]]:
        """
        Create complete directory structure for the media server.

        Args:
            docker_dir: Base directory for Docker volumes
            media_dir: Base directory for media files
            uid: User ID for ownership
            gid: Group ID for ownership

        Returns:
            Tuple of (success, list_of_errors)
        """
        errors = []

        # Main directories
        main_dirs = [docker_dir, media_dir, docker_dir / "compose"]

        # Create main directories
        for directory in main_dirs:
            success, error = self._create_single_directory(directory, uid, gid)
            if not success:
                errors.append(error)

        # Create media subdirectories
        media_subdirs = [
            "downloads/incomplete",
            "downloads/complete",
            "movies",
            "tv",
            "music",
            "books",
            "comics",
            "podcasts",
            "audiobooks",
        ]

        for subdir in media_subdirs:
            subdir_path = media_dir / subdir
            success, error = self._create_single_directory(subdir_path, uid, gid)
            if not success:
                errors.append(error)

        return len(errors) == 0, errors

    def create_service_directories(
        self, docker_dir: Path, selected_services: List[str], uid: int, gid: int
    ) -> Tuple[bool, List[str]]:
        """
        Create directories for selected services.

        Args:
            docker_dir: Base Docker directory
            selected_services: List of service names
            uid: User ID for ownership
            gid: Group ID for ownership

        Returns:
            Tuple of (success, list_of_errors)
        """
        errors = []

        for service in selected_services:
            service_dir = docker_dir / service / "config"
            success, error = self._create_single_directory(service_dir, uid, gid)
            if not success:
                errors.append(error)

        return len(errors) == 0, errors

    def _create_single_directory(
        self, directory: Path, uid: int, gid: int
    ) -> Tuple[bool, str]:
        """
        Create a single directory with proper permissions.

        Args:
            directory: Directory path to create
            uid: User ID for ownership
            gid: Group ID for ownership

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Try to create directory normally first
            directory.mkdir(parents=True, exist_ok=True)
            self.created_directories.append(directory)

            # Try to set ownership
            if self._set_directory_ownership(directory, uid, gid):
                print_success(f"Created directory: {directory}")
                return True, ""
            else:
                self.permission_fixes_needed.append(directory)
                print_warning(
                    f"Created directory but couldn't set ownership: {directory}"
                )
                return True, ""

        except PermissionError:
            # Try with sudo
            try:
                run_command(["mkdir", "-p", str(directory)], sudo=True)
                self.created_directories.append(directory)

                if self._set_directory_ownership(directory, uid, gid, use_sudo=True):
                    print_success(f"Created directory with sudo: {directory}")
                    return True, ""
                else:
                    self.permission_fixes_needed.append(directory)
                    print_warning(
                        f"Created directory but couldn't set ownership: {directory}"
                    )
                    return True, ""

            except Exception as e:
                error_msg = f"Failed to create {directory}: {str(e)}"
                print_error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Failed to create {directory}: {str(e)}"
            print_error(error_msg)
            return False, error_msg

    def _set_directory_ownership(
        self, directory: Path, uid: int, gid: int, use_sudo: bool = False
    ) -> bool:
        """
        Set ownership of a directory.

        Args:
            directory: Directory to set ownership for
            uid: User ID
            gid: Group ID
            use_sudo: Whether to use sudo

        Returns:
            True if successful, False otherwise
        """
        try:
            if use_sudo or os.geteuid() == 0:
                run_command(
                    ["chown", "-R", f"{uid}:{gid}", str(directory)],
                    sudo=not (os.geteuid() == 0),
                )
                run_command(
                    ["chmod", "-R", "755", str(directory)], sudo=not (os.geteuid() == 0)
                )
            else:
                os.chown(directory, uid, gid)
                directory.chmod(0o755)
            return True

        except Exception:
            return False

    def fix_permissions(self, uid: int, gid: int) -> List[str]:
        """
        Fix permissions for directories that need it.

        Args:
            uid: User ID
            gid: Group ID

        Returns:
            List of directories that couldn't be fixed
        """
        failed_fixes = []

        print_info("Fixing directory permissions...")

        for directory in self.permission_fixes_needed:
            if not self._set_directory_ownership(directory, uid, gid, use_sudo=True):
                failed_fixes.append(str(directory))
                print_error(f"Could not fix permissions for: {directory}")
            else:
                print_success(f"Fixed permissions for: {directory}")

        return failed_fixes

    def validate_directory_access(self, directories: List[Path], uid: int) -> List[str]:
        """
        Validate that directories are accessible for the given user.

        Args:
            directories: List of directories to check
            uid: User ID to check access for

        Returns:
            List of directories with access issues
        """
        access_issues = []

        for directory in directories:
            if not directory.exists():
                access_issues.append(f"{directory}: Does not exist")
                continue

            if not directory.is_dir():
                access_issues.append(f"{directory}: Not a directory")
                continue

            # Check if we can read the directory
            try:
                list(directory.iterdir())
            except PermissionError:
                access_issues.append(f"{directory}: No read access")
                continue

            # Check if we can write to the directory
            try:
                test_file = directory / ".test_write"
                test_file.touch()
                test_file.unlink()
            except PermissionError:
                access_issues.append(f"{directory}: No write access")
                continue
            except Exception:
                # Other errors (like disk full) we'll ignore for now
                pass

        return access_issues

    def get_directory_info(self, directory: Path) -> dict:
        """
        Get information about a directory.

        Args:
            directory: Directory to get info for

        Returns:
            Dictionary with directory information
        """
        try:
            if not directory.exists():
                return {"exists": False}

            stat_info = directory.stat()
            return {
                "exists": True,
                "is_directory": directory.is_dir(),
                "size_mb": sum(
                    f.stat().st_size for f in directory.rglob("*") if f.is_file()
                )
                / (1024 * 1024),
                "owner_uid": stat_info.st_uid,
                "owner_gid": stat_info.st_gid,
                "permissions": oct(stat_info.st_mode)[-3:],
                "file_count": (
                    len(list(directory.rglob("*"))) if directory.is_dir() else 0
                ),
            }
        except Exception as e:
            return {"exists": True, "error": str(e)}

    def cleanup_empty_directories(self, base_path: Path) -> int:
        """
        Remove empty directories under the base path.

        Args:
            base_path: Base directory to clean up

        Returns:
            Number of directories removed
        """
        removed_count = 0

        if not base_path.exists() or not base_path.is_dir():
            return 0

        # Walk the directory tree bottom-up
        for directory in sorted(
            base_path.rglob("*"), key=lambda p: len(p.parts), reverse=True
        ):
            if directory.is_dir():
                try:
                    # Try to remove if empty
                    directory.rmdir()
                    print_info(f"Removed empty directory: {directory}")
                    removed_count += 1
                except OSError:
                    # Directory not empty or other error, skip
                    pass

        return removed_count

    def get_disk_usage(self, directory: Path) -> dict:
        """
        Get disk usage information for a directory.

        Args:
            directory: Directory to check

        Returns:
            Dictionary with disk usage info
        """
        try:
            import shutil

            total, used, free = shutil.disk_usage(directory)

            return {
                "total_gb": total / (1024**3),
                "used_gb": used / (1024**3),
                "free_gb": free / (1024**3),
                "used_percent": (used / total) * 100,
            }
        except Exception as e:
            return {"error": str(e)}
