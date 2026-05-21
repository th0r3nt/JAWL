from pathlib import Path
import pytest
from unittest.mock import patch

from src.utils._tools import (
    format_size,
    parse_int_or_str,
    truncate_text,
    clean_html,
    validate_sandbox_path,
    draw_image_grid,
    is_agent_running,
    SystemInstanceLock,
)


def test_format_size() -> None:
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024 * 5.5) == "5.5 MB"
    assert format_size(-1024) == "-1.0 KB"


def test_parse_int_or_str() -> None:
    assert parse_int_or_str("12345") == 12345
    assert parse_int_or_str(12345) == 12345
    assert parse_int_or_str("@username") == "@username"
    assert parse_int_or_str("  @username  ") == "@username"


def test_truncate_text() -> None:
    text = "Hello World!"
    assert truncate_text(text, 50) == "Hello World!"
    truncated = truncate_text(text, 5, suffix="...")
    assert truncated == "He..."
    assert len(truncated) == 5


def test_truncate_text_never_exceeds_max_chars() -> None:
    long_text = "a" * 1000
    for limit in (1, 10, 50, 100, 200, 500, 999):
        result = truncate_text(long_text, limit)
        assert len(result) <= limit


def test_truncate_text_suffix_longer_than_limit() -> None:
    result = truncate_text("abcdef", max_chars=3, suffix="...[long suffix]")
    assert len(result) == 3


def test_truncate_text_zero_and_negative_max() -> None:
    assert truncate_text("abc", 0) == ""
    assert truncate_text("abc", -5) == ""


class TestHTMLCleaner:
    def test_clean_html_removes_scripts_and_styles(self) -> None:
        html = "<html><style>body {color: red;}</style><script>alert('xss');</script><body>Text</body></html>"
        cleaned = clean_html(html)
        assert "alert" not in cleaned
        assert "color: red" not in cleaned
        assert cleaned == "Text"

    def test_clean_html_unescapes_entities(self) -> None:
        html = "<p>Tom &amp; Jerry said &quot;Hi&quot; &#39;today&#39;</p>"
        cleaned = clean_html(html)
        assert cleaned == "Tom & Jerry said \"Hi\" 'today'"

    def test_clean_html_collapses_whitespace(self) -> None:
        html = "<div>Line 1</div>    \n\n  <div>Line 2</div>"
        cleaned = clean_html(html)
        assert cleaned == "Line 1 Line 2"


class TestGatekeeper:
    def test_validate_sandbox_path_valid_files(self) -> None:
        sandbox_dir = (Path.cwd() / "sandbox").resolve()

        path1 = validate_sandbox_path("test.txt")
        assert path1 == sandbox_dir / "test.txt"

        path2 = validate_sandbox_path("sandbox/folder/test.txt")
        assert path2 == sandbox_dir / "folder" / "test.txt"

    def test_validate_sandbox_path_blocks_traversal(self) -> None:
        # FIXED: Changed regex exception match to English
        with pytest.raises(
            PermissionError, match="Access denied: you can work with files"
        ):
            validate_sandbox_path("../main.py")

        with pytest.raises(
            PermissionError, match="Access denied: you can work with files"
        ):
            validate_sandbox_path("sandbox/../../etc/passwd")

    def test_validate_sandbox_path_blocks_absolute_paths(self) -> None:
        import os

        forbidden_path = "C:\\Windows\\System32" if os.name == "nt" else "/etc/passwd"

        # FIXED: Changed regex exception match to English
        with pytest.raises(
            PermissionError, match="Access denied: you can work with files"
        ):
            validate_sandbox_path(forbidden_path)


class TestImageGrid:
    def test_draw_image_grid_creates_correct_overlay(self, tmp_path):
        from PIL import Image

        test_img_path = tmp_path / "test_screenshot.png"
        img = Image.new("RGBA", (300, 300), color=(255, 255, 255, 255))
        img.save(test_img_path)

        draw_image_grid(test_img_path, step=100)

        with Image.open(test_img_path) as modified_img:
            assert modified_img.mode == "RGB"
            assert modified_img.size == (300, 300)

            r, g, b = modified_img.getpixel((100, 0))
            assert r == 255
            assert g < 255
            assert b < 255


def test_system_instance_lock(tmp_path):
    lock_file = tmp_path / "agent.pid"

    lock1 = SystemInstanceLock(lock_file)
    lock2 = SystemInstanceLock(lock_file)

    assert lock1.acquire() is True
    assert lock_file.exists()

    assert lock2.acquire() is False

    lock1.release()

    assert lock2.acquire() is True
    lock2.release()


@patch("src.utils._tools.get_lock_file_path")
@patch("src.utils._tools.get_pid_file_path")
def test_is_agent_running_with_lock(mock_get_pid, mock_get_lock, tmp_path):
    pid_file = tmp_path / "agent.pid"
    lock_file = tmp_path / "agent.lock"

    mock_get_pid.return_value = pid_file
    mock_get_lock.return_value = lock_file

    assert is_agent_running() is False

    pid_file.write_text("12345")
    lock = SystemInstanceLock(lock_file)
    assert lock.acquire() is True

    assert is_agent_running() is True

    lock.release()

    assert is_agent_running() is False
    assert not pid_file.exists()
    assert not lock_file.exists()
