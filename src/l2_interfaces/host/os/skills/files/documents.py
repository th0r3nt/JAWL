"""
Skills for secure reading of binary text documents (.pdf, .docx).
"""

import pypdf
import docx
import asyncio
from typing import Optional

from src.utils.logger import main_logger
from src.utils._tools import truncate_text, format_size

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class HostOSDocuments:
    """Tools for extracting raw text from documents."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm=[Subagents.CODER, Subagents.QA_ENGINEER, Subagents.WEB_RESEARCHER])
    @require_access(HostOSAccessLevel.SANDBOX)
    async def read_document(
        self, filepath: str, page_start: Optional[int] = None, page_end: Optional[int] = None
    ) -> SkillResult:
        """
        Extracts text from .pdf/.docx.

        filepath: Sandbox relative path.
        page_start/page_end: 1-based page range (PDF only).
        """
        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Error: File not found ({safe_path.name}).")

            ext = safe_path.suffix.lower()
            if ext not in [".pdf", ".docx"]:
                return SkillResult.fail(
                    f"Error: Format '{ext}' is not supported by this skill. "
                    f"Supported formats: .pdf, .docx."
                )

            size_str = format_size(safe_path.stat().st_size)
            max_chars = self.host_os.config.file_read_max_chars

            def _extract_text() -> str:
                # ==========================
                # PDF Parsing
                # ==========================
                if ext == ".pdf":

                    with open(safe_path, "rb") as f:
                        reader = pypdf.PdfReader(f)
                        total_pages = len(reader.pages)

                        start_idx = max(0, page_start - 1) if page_start else 0
                        end_idx = min(total_pages, page_end) if page_end else total_pages

                        if start_idx >= total_pages or start_idx >= end_idx:
                            raise ValueError(
                                f"Invalid page range. The document only has {total_pages} pages."
                            )

                        extracted_pages = []
                        for i in range(start_idx, end_idx):
                            page_text = reader.pages[i].extract_text() or ""
                            extracted_pages.append(f"--- Page {i + 1} ---\n{page_text}")

                        return "\n\n".join(extracted_pages)

                # ==========================
                # DOCX Parsing
                # ==========================
                elif ext == ".docx":

                    doc = docx.Document(str(safe_path))
                    full_text = []
                    for para in doc.paragraphs:
                        full_text.append(para.text)

                    return "\n".join(full_text)

                return ""

            main_logger.info(f"[Host OS] Reading document: {safe_path.name} ({size_str})")

            # Parsing documents requires CPU, running in a separate thread pool
            raw_text = await asyncio.to_thread(_extract_text)

            if not raw_text.strip():
                return SkillResult.ok(
                    "Document read, but no text found (possibly scans or an empty file)."
                )

            # Context protection against overflow
            clean_text = truncate_text(
                raw_text,
                max_chars,
                f"\n... [Text truncated. Reached limit of {max_chars} characters]",
            )

            return SkillResult.ok(f"Content of {safe_path.name}:\n\n{clean_text}")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except ValueError as e:
            return SkillResult.fail(str(e))

        except RuntimeError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            main_logger.error(f"[Host OS] Error reading document: {e}")
            return SkillResult.fail(f"Error parsing document: {e}")
