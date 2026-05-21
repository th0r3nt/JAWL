"""
Skills for searching files and generating directory trees.
"""

import asyncio
from pathlib import Path

from src.utils.logger import main_logger
from src.utils._tools import format_size, get_python_module_docstring

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class HostOSSearch:
    """File search and directory tree mapping tools."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def list_directory(self, path: str = ".", max_depth: int = 1) -> SkillResult:
        """
        Lists directory contents.

        max_depth: Subfolder scan depth (0 = current only).
        """
        limit = self.host_os.config.file_list_limit

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(f"Error: Path is not a directory ({path}).")

            try:
                dir_display = safe_path.relative_to(self.host_os.framework_dir).as_posix()
            except ValueError:
                dir_display = safe_path.name

            meta = self.host_os.get_file_metadata()

            ignore_exts = {".pyc", ".pyo", ".pyd", ".tmp", ".swp"}
            ignore_dirs = {
                ".git",
                "venv",
                ".venv",
                "env",
                "__pycache__",
                "node_modules",
                ".pytest_cache",
            }

            lines = []
            lines_count = 0

            def _build_tree(current_dir: Path, current_depth: int, prefix: str):
                nonlocal lines_count
                if current_depth > max_depth or lines_count >= limit:
                    return

                try:
                    items = []
                    for p in current_dir.iterdir():
                        if p.name.startswith(".") and p.name not in {".env"}:
                            continue
                        if p.is_dir() and p.name in ignore_dirs:
                            continue
                        if p.is_file() and p.suffix.lower() in ignore_exts:
                            continue
                        items.append(p)

                    items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
                    total_items = len(items)

                    for i, item in enumerate(items):
                        if lines_count >= limit:
                            return

                        is_last = i == total_items - 1
                        connector = "└── " if is_last else "├── "

                        if item.is_dir():
                            lines.append(f"{prefix}{connector}📂 {item.name}/")
                            lines_count += 1

                            if current_depth < max_depth:
                                extension = "    " if is_last else "│   "
                                _build_tree(item, current_depth + 1, prefix + extension)
                        else:
                            try:
                                size_str = format_size(item.stat().st_size)
                            except Exception:
                                size_str = "???"

                            desc = ""
                            try:
                                if item.is_relative_to(self.host_os.sandbox_dir):
                                    rel_path = item.relative_to(
                                        self.host_os.sandbox_dir
                                    ).as_posix()
                                    if rel_path in meta:
                                        desc = f" [Description: {meta[rel_path]}]"
                            except Exception:
                                pass

                            desc += get_python_module_docstring(item)

                            lines.append(
                                f"{prefix}{connector}📄 {item.name} ({size_str}){desc}"
                            )
                            lines_count += 1

                except Exception:
                    pass

            root_icon = "🏠" if dir_display == self.host_os.framework_dir.name else "📂"
            lines.append(f"{root_icon} {dir_display}/")

            _build_tree(safe_path, 0, "")

            if lines_count >= limit:
                lines.append(
                    f"└── ... [Output limit of {limit} elements reached. Others hidden]"
                )

            if len(lines) == 1:
                lines.append("└── (Empty directory)")

            main_logger.info(f"[Host OS] Directory lookup (tree): {safe_path.name}")
            return SkillResult.ok("\n".join(lines))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error reading directory: {e}")

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def search_files(self, pattern: str, path: str = ".") -> SkillResult:
        """
        Searches files by glob pattern (e.g., '*.py', 'log_*.txt').
        """

        limit = self.host_os.config.file_list_limit

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail("Error: Base search path must be a directory.")

            meta = self.host_os.get_file_metadata()

            found = []
            for i, file_path in enumerate(safe_path.rglob(pattern)):
                if i >= limit:
                    found.append(f"...[Search limit: found more than {limit} matches] ...")
                    break

                try:
                    rel_path = file_path.relative_to(self.host_os.framework_dir).as_posix()
                except ValueError:
                    rel_path = str(file_path)

                try:
                    size_str = (
                        format_size(file_path.stat().st_size) if file_path.is_file() else "DIR"
                    )
                except Exception:
                    size_str = "???"

                desc = ""
                try:
                    if file_path.is_relative_to(self.host_os.sandbox_dir):
                        full_rel_path = file_path.relative_to(
                            self.host_os.sandbox_dir
                        ).as_posix()
                        if full_rel_path in meta:
                            desc = f" [Description: {meta[full_rel_path]}]"
                except Exception:
                    pass

                desc += get_python_module_docstring(file_path)

                found.append(f"- {rel_path} ({size_str}){desc}")

            if not found:
                return SkillResult.ok(f"No matches found for pattern '{pattern}'.")

            main_logger.info(f"[Host OS] Searching files '{pattern}' in {safe_path.name}")
            return SkillResult.ok("\n".join(found))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error searching files: {e}")

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def search_content_in_files(
        self,
        search_string: str,
        path: str = ".",
        case_sensitive: bool = False,
        recursive: bool = True,
    ) -> SkillResult:
        """
        Global search.
        Finds exact text string across all files in directory.
        """

        if not search_string:
            return SkillResult.fail("Search string cannot be empty.")

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(f"Error: Path is not a directory ({path}).")

            max_matches = 150

            def _search():
                matches = []
                ignore_dirs = {
                    ".git",
                    "venv",
                    ".venv",
                    "env",
                    "__pycache__",
                    "node_modules",
                    ".pytest_cache",
                }

                iterator = safe_path.rglob("*") if recursive else safe_path.iterdir()
                search_query = search_string if case_sensitive else search_string.lower()

                for item in iterator:
                    if not item.is_file():
                        continue

                    rel_path = item.relative_to(safe_path)

                    if any(part in ignore_dirs for part in rel_path.parts):
                        continue

                    try:
                        with open(item, "r", encoding="utf-8") as f:
                            for line_num, line in enumerate(f, 1):
                                check_line = line if case_sensitive else line.lower()

                                if search_query in check_line:
                                    try:
                                        display_path = item.relative_to(
                                            self.host_os.framework_dir
                                        ).as_posix()
                                    except ValueError:
                                        display_path = item.name

                                    clean_line = line.strip()
                                    limit = 300
                                    if len(clean_line) > limit:
                                        clean_line = (
                                            clean_line[:limit] + " ... [line truncated]"
                                        )

                                    matches.append(
                                        f"- {display_path}:{line_num}: {clean_line}"
                                    )

                                    if len(matches) >= max_matches:
                                        matches.append(
                                            f"\n... [Reached limit of {max_matches} matches. Search stopped]"
                                        )
                                        return matches

                    except UnicodeDecodeError:
                        continue

                    except Exception:
                        continue

                return matches

            results = await asyncio.to_thread(_search)

            if not results:
                return SkillResult.ok(
                    f"No matches found for string '{search_string}' in '{safe_path.name}'."
                )

            main_logger.info(
                f"[Host OS] Executed global search for text '{search_string}' in {safe_path.name}"
            )
            return SkillResult.ok(
                f"Search results for '{search_string}':\n" + "\n".join(results)
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error searching text: {e}")
