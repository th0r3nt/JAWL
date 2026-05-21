"""
Subagents Roles Directory (RBAC).

Defines static definitions, identifiers, prompts, and system descriptions
for background subagents to enforce strict Role-Based Access Control.
"""

from typing import List, Optional
from pydantic import BaseModel


class SubagentRole(BaseModel):
    """Model container for subagent role metadata."""

    id: str
    name: str
    description: str
    prompt_file: str


class Subagents:
    """
    Directory of active subagent roles and privileges.
    Sets execution boundaries and authorized skills pool for each role.
    """

    CODER = SubagentRole(
        id="coder",
        name="Software Engineer",
        description="Invoke to delegate software development, refactoring, debugging, file system operations, and git version control tasks.",
        prompt_file="CODER.md",
    )

    WEB_RESEARCHER = SubagentRole(
        id="web_researcher",
        name="OSINT Analyst",
        description="Invoke to delegate deep parallel web research, article parsing, data scraping, and fact-checking.",
        prompt_file="WEB_SEARCHER.md",
    )

    ARCHIVIST = SubagentRole(
        id="archivist",
        name="Database Archivist",
        description="Invoke to delegate memory audits. Capable of reading Vector DB to purge old garbage and consolidate facts.",
        prompt_file="ARCHIVIST.md",
    )

    QA_ENGINEER = SubagentRole(
        id="qa_engineer",
        name="QA Engineer",
        description="Invoke to delegate unit testing. Gathers edge cases, runs test suites, and returns prioritized bug reports.",
        prompt_file="QA_ENGINEER.md",
    )

    SYSADMIN = SubagentRole(
        id="sysadmin",
        name="System Administrator",
        description="Invoke to delegate dependency installation, raw shell commands execution, OS metrics monitoring, process management, and network diagnostics.",
        prompt_file="SYSADMIN.md",
    )

    @classmethod
    def all(cls) -> List[SubagentRole]:
        """Returns list of all registered roles."""
        return [v for k, v in vars(cls).items() if isinstance(v, SubagentRole)]

    @classmethod
    def get_by_id(cls, role_id: str) -> Optional[SubagentRole]:
        """Resolves role by its unique string identifier."""
        for role in cls.all():
            if role.id == role_id:
                return role
        return None
