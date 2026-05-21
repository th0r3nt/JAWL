"""
L0 State for the Code Graph interface.

Code graphs store dependencies, descriptions, and help understand complex codebases,
thanks to semantic vector search over relations in a deterministic graph.
"""

import json
from pathlib import Path
from typing import Dict


class CodeGraphState:
    """Stores the list of indexed projects (codebases)."""

    def __init__(self, data_dir: Path):
        self.is_online = False
        self.persist_file = data_dir / "interfaces" / "code_graph" / "indexes.json"
        self.persist_file.parent.mkdir(parents=True, exist_ok=True)

        # Cache: {"project_id": "path/to/folder"}
        self.active_indexes: Dict[str, str] = self._load()

    def _load(self) -> Dict[str, str]:
        if not self.persist_file.exists():
            return {}
        try:
            with open(self.persist_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self) -> None:
        with open(self.persist_file, "w", encoding="utf-8") as f:
            json.dump(self.active_indexes, f, ensure_ascii=False, indent=4)
