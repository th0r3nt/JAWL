import ast
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PYTHON_BOUNDARIES = (
    ROOT / "src/l2_interfaces/telegram/kurigram",
    ROOT / "tests/l2/kurigram",
)
DEPENDENCY_FILES = (
    ROOT / "requirements.txt",
    ROOT / "pyproject.toml",
)


def _python_files():
    for directory in PYTHON_BOUNDARIES:
        yield from directory.rglob("*.py")


def _direct_legacy_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] == "telethon":
                    yield f"{path.relative_to(ROOT)}:{node.lineno} import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".", 1)[0] == "telethon":
                yield f"{path.relative_to(ROOT)}:{node.lineno} from {module}"
        elif isinstance(node, ast.Call):
            if _is_direct_legacy_dynamic_import(node):
                yield f"{path.relative_to(ROOT)}:{node.lineno} dynamic telethon import"


def _is_direct_legacy_dynamic_import(node):
    if (
        isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
        and node.args
        and _is_legacy_module_literal(node.args[0])
    ):
        return True

    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.args
        and _is_legacy_module_literal(node.args[0])
    ):
        return True

    return False


def _is_legacy_module_literal(node):
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.split(".", 1)[0] == "telethon"
    )


def _telegram_log_labels(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"debug", "info", "warning", "error", "critical"}:
            continue
        if not node.args:
            continue

        segment = ast.get_source_segment(source, node.args[0]) or ""
        if "[Telegram " in segment:
            yield node.lineno, segment


def _dependency_name(spec):
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", spec)
    if not match:
        return ""
    return match.group(1).replace("_", "-").lower()


def _dependency_specs_from_pyproject(path):
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    def walk(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from walk(item)

    yield from walk(data)


def _dependency_specs_from_requirements(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        spec = line.split("#", 1)[0].strip()
        if spec and not spec.startswith(("-r", "--")):
            yield spec


def test_telegram_interface_avoids_direct_legacy_imports():
    direct_imports = [
        import_line
        for path in _python_files()
        for import_line in _direct_legacy_imports(path)
    ]

    assert direct_imports == [], "\n".join(direct_imports)


def test_telegram_log_labels_use_kurigram_brand():
    stale_labels = []
    for path in _python_files():
        if "tests/l2/kurigram" in str(path.relative_to(ROOT)):
            continue
        stale_labels.extend(
            f"{path.relative_to(ROOT)}:{lineno} {label}"
            for lineno, label in _telegram_log_labels(path)
            if "[Telegram Kurigram]" not in label
        )

    assert stale_labels == [], "\n".join(stale_labels)


def test_project_dependencies_do_not_include_legacy_client_package():
    dependency_specs = []
    for path in DEPENDENCY_FILES:
        if path.name == "pyproject.toml":
            dependency_specs.extend(_dependency_specs_from_pyproject(path))
        else:
            dependency_specs.extend(_dependency_specs_from_requirements(path))

    legacy_specs = [
        spec for spec in dependency_specs if _dependency_name(spec) == "telethon"
    ]

    assert legacy_specs == []
