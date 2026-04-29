import pytest
from pathlib import Path
from src.l3_agent.swarm.prompt.builder import SwarmPromptBuilder
from src.l3_agent.swarm.roles import SubagentRole


@pytest.fixture
def mock_prompt_dir(tmp_path: Path):
    swarm_dir = tmp_path / "src" / "l3_agent" / "swarm" / "prompt"
    roles_dir = swarm_dir / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    (roles_dir / "CODER.md").write_text("ROLE: CODER", encoding="utf-8")
    (swarm_dir / "INSTRUCTIONS.md").write_text("INSTRUCTIONS TEXT", encoding="utf-8")
    (swarm_dir / "FUNCTIONS_CALL.md").write_text("FUNCTION CALL TEXT", encoding="utf-8")

    return tmp_path


@pytest.fixture
def dummy_role():
    return SubagentRole(id="coder", name="Coder", description="", prompt_file="CODER.md")


def test_swarm_prompt_builder_success(mock_prompt_dir, dummy_role):
    builder = SwarmPromptBuilder(mock_prompt_dir)
    result = builder.build(dummy_role)

    assert "ROLE: CODER" in result
    assert "INSTRUCTIONS TEXT" in result
    assert "FUNCTION CALL TEXT" in result


def test_swarm_prompt_builder_missing_role(mock_prompt_dir):
    builder = SwarmPromptBuilder(mock_prompt_dir)
    bad_role = SubagentRole(
        id="hacker", name="Hacker", description="", prompt_file="HACKER.md"
    )

    with pytest.raises(FileNotFoundError, match="Файл роли не найден"):
        builder.build(bad_role)


def test_swarm_prompt_builder_missing_base_files(tmp_path: Path, dummy_role):
    swarm_dir = tmp_path / "src" / "l3_agent" / "swarm" / "prompt"
    roles_dir = swarm_dir / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    (roles_dir / "CODER.md").write_text("ROLE: CODER", encoding="utf-8")

    builder = SwarmPromptBuilder(tmp_path)

    with pytest.raises(FileNotFoundError, match="INSTRUCTIONS.md"):
        builder.build(dummy_role)
