"""
Skills for working with archives.
Includes robust protection against ZIP/TAR Slip vulnerabilities (escaping directory bounds).
"""

import shutil
import asyncio
import zipfile
import tarfile
from pathlib import Path

from src.utils.logger import main_logger

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSArchive:
    """Archive tools with security checks."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    def _is_safe_archive(self, archive_path: Path, extract_to: Path) -> bool:
        """
        Validates internal archive paths against ZIP Slip vulnerabilities.
        """

        extract_to_resolved = extract_to.resolve()

        def _member_in_sandbox(name: str) -> bool:
            member_path = Path(name)
            if member_path.is_absolute():
                return False
            resolved = (extract_to / member_path).resolve()
            return resolved.is_relative_to(extract_to_resolved)

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for name in zf.namelist():
                    if not _member_in_sandbox(name):
                        return False
            return True

        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r") as tf:
                for member in tf.getmembers():
                    if not _member_in_sandbox(member.name):
                        return False

                    if member.issym() or member.islnk():
                        linkname = member.linkname
                        if not linkname:
                            continue
                        link_path = Path(linkname)
                        if link_path.is_absolute():
                            return False
                        link_parent = (extract_to / Path(member.name)).parent
                        resolved_link = (link_parent / link_path).resolve()
                        if not resolved_link.is_relative_to(extract_to_resolved):
                            return False
            return True

        return True

    @skill()
    @require_access(HostOSAccessLevel.SANDBOX)
    async def extract_archive(self, archive_path: str, extract_to: str = ".") -> SkillResult:
        """
        Extracts archive.
        """
        try:
            safe_archive = self.host_os.validate_path(archive_path, is_write=False)
            safe_dest = self.host_os.validate_path(extract_to, is_write=True)

            if not safe_archive.is_file():
                return SkillResult.fail(f"Error: Archive not found ({safe_archive.name}).")

            safe_dest.mkdir(parents=True, exist_ok=True)

            if not await asyncio.to_thread(self._is_safe_archive, safe_archive, safe_dest):
                main_logger.warning(
                    f"[Security] Blocked extraction of {safe_archive.name}: ZIP Slip vulnerability detected."
                )
                return SkillResult.fail(
                    "Security error: Attempt to escape directory bounds detected inside the archive (ZIP Slip). Extraction blocked."
                )

            await asyncio.to_thread(shutil.unpack_archive, str(safe_archive), str(safe_dest))

            main_logger.info(
                f"[Host OS] Extracted archive {safe_archive.name} into {safe_dest.name}"
            )

            try:
                dest_display = safe_dest.relative_to(self.host_os.sandbox_dir).as_posix()
                dest_msg = f"sandbox/{dest_display}"
            except ValueError:
                dest_msg = safe_dest.as_posix()

            return SkillResult.ok(
                f"Archive {safe_archive.name} successfully extracted to directory: {dest_msg}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except shutil.ReadError:
            return SkillResult.fail("Error: Unsupported archive format or file corrupted.")
        except Exception as e:
            return SkillResult.fail(f"Error extracting archive: {e}")
