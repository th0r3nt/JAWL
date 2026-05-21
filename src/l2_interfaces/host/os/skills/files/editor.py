"""
Skills for targeted editing (patching) of files.
Saves context tokens and reduces the risk of file corruption compared to full rewrites.
"""

import asyncio

from src.utils.logger import main_logger

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.swarm.roles import Subagents

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSEditor:
    """Skills for targeted code editing."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def delete_lines_matching(
        self, filepath: str, match_string: str, exact_match: bool = False
    ) -> SkillResult:
        """
        Deletes lines containing 'match_string'.

        exact_match: Requires full string match (ignoring edge whitespace).
        """

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)
            if not safe_path.is_file():
                return SkillResult.fail(f"Error: File not found ({filepath}).")

            def _delete():
                with open(safe_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                new_lines = []
                deleted_count = 0

                for line in lines:
                    if exact_match:
                        if line.strip() == match_string.strip():
                            deleted_count += 1
                            continue
                    else:
                        if match_string in line:
                            deleted_count += 1
                            continue
                    new_lines.append(line)

                if deleted_count == 0:
                    return False, "No matches found. No lines deleted."

                with open(safe_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

                return True, f"Successfully deleted lines: {deleted_count}."

            is_success, msg = await asyncio.to_thread(_delete)

            if is_success:
                main_logger.info(f"[Host OS] Deleted lines in file: {safe_path.name}")
                return SkillResult.ok("True")
            else:
                return SkillResult.fail(msg)

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error deleting lines: {e}")

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def patch_file(
        self, filepath: str, search_block: str, replace_block: str
    ) -> SkillResult:
        """
        Targeted file modification. Saves tokens/reduces corruption risk vs full rewrite.

        search_block: Exact fragment to replace.
        replace_block: New code insert.
        """

        if not search_block:
            return SkillResult.fail("Error: search_block cannot be empty.")

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)
            if not safe_path.is_file():
                return SkillResult.fail(f"Error: File not found ({filepath}).")

            def _patch():
                with open(safe_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if search_block not in content:
                    clean_search = search_block.replace("\r\n", "\n").strip()
                    clean_content = content.replace("\r\n", "\n")

                    if clean_search not in clean_content:
                        return (
                            False,
                            "The block to search for (search_block) was not found in the file.",
                        )

                    new_content = clean_content.replace(clean_search, replace_block.strip())
                else:
                    new_content = content.replace(search_block, replace_block)

                with open(safe_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                return True, "File successfully patched."

            is_success, msg = await asyncio.to_thread(_patch)

            if is_success:
                main_logger.info(f"[Host OS] Patched file: {safe_path.name}")
                return SkillResult.ok("True")
            else:
                return SkillResult.fail(msg)

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error patching file: {e}")
