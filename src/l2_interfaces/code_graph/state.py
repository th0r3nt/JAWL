"""
L0 State для интерфейса Кодового графа (Code Graph).

Кодовые графы хранят зависимости, описания и помогают разбираться в сложных кодовых базах,
благодаря векторному поиску по связям в детерминированном графе.
"""

import json
from pathlib import Path
from typing import Dict


class CodeGraphState:
    """Хранит список проиндексированных проектов (кодовых баз)."""

    def __init__(self, data_dir: Path):
        self.is_online = False
        self.persist_file = data_dir / "interfaces" / "code_graph" / "indexes.json"
        self.persist_file.parent.mkdir(parents=True, exist_ok=True)

        # Кэш: {"project_id": "path/to/folder"}
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
