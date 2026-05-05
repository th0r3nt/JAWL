from pathlib import Path

import pytest

from src.utils.templates._sandbox_guard import PathChecker


def test_path_checker_blocks_host_paths_outside_sandbox(tmp_path: Path) -> None:
    framework_dir = tmp_path / "JAWL"
    sandbox_dir = framework_dir / "sandbox"
    sandbox_dir.mkdir(parents=True)

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("host secret", encoding="utf-8")

    checker = PathChecker(framework_dir=framework_dir, sandbox_dir=sandbox_dir)

    with pytest.raises(PermissionError):
        checker.check(outside_file)


def test_path_checker_blocks_writes_outside_sandbox_even_if_missing(tmp_path: Path) -> None:
    framework_dir = tmp_path / "JAWL"
    sandbox_dir = framework_dir / "sandbox"
    sandbox_dir.mkdir(parents=True)

    checker = PathChecker(framework_dir=framework_dir, sandbox_dir=sandbox_dir)

    with pytest.raises(PermissionError):
        checker.check(tmp_path / "new-host-file.txt")


def test_path_checker_allows_sandbox_paths(tmp_path: Path) -> None:
    framework_dir = tmp_path / "JAWL"
    sandbox_dir = framework_dir / "sandbox"
    sandbox_dir.mkdir(parents=True)
    sandbox_file = sandbox_dir / "allowed.txt"
    sandbox_file.write_text("ok", encoding="utf-8")

    checker = PathChecker(framework_dir=framework_dir, sandbox_dir=sandbox_dir)

    checker.check(sandbox_file)


def test_path_checker_blocks_framework_paths_outside_sandbox(tmp_path: Path) -> None:
    framework_dir = tmp_path / "JAWL"
    sandbox_dir = framework_dir / "sandbox"
    sandbox_dir.mkdir(parents=True)
    framework_file = framework_dir / "README.md"
    framework_file.write_text("project", encoding="utf-8")

    checker = PathChecker(framework_dir=framework_dir, sandbox_dir=sandbox_dir)

    with pytest.raises(PermissionError):
        checker.check(framework_file)
