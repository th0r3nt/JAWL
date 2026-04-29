from pathlib import Path
from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.host.os.polls.utils import is_ignored


class TreeBuilder:
    """Генератор ASCII-дерева директорий для контекста агента."""

    def __init__(self, client: HostOSClient):
        self.client = client

    def build_tree(
        self,
        dir_path: Path,
        use_emojis: bool,
        max_depth: int,
        current_depth: int = 0,
        prefix: str = "",
    ) -> list[str]:
        meta = self.client.get_file_metadata()
        lines = []

        try:
            items = [item for item in dir_path.iterdir() if not is_ignored(item)]
            items = sorted(items, key=lambda x: (not x.is_dir(), x.name.lower()))

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└── " if is_last else "├── "

                icon = ""
                if use_emojis:
                    icon = "📂 " if item.is_dir() else "📄 "

                desc = ""
                if item.is_file():
                    try:
                        rel_path = item.relative_to(self.client.sandbox_dir).as_posix()
                        if rel_path in meta:
                            desc = f" — [{meta[rel_path]}]"
                    except ValueError:
                        pass  # Файл вне песочницы, метаданных нет

                # Папка sandbox/ выводится отдельным блоком - проверяем, чтобы не дублировать
                is_sandbox = item == self.client.sandbox_dir
                is_truncated_dir = item.is_dir() and current_depth >= max_depth

                if is_sandbox:
                    display_name = f"{item.name}/ [См. блок Sandbox Directory ниже]"
                    should_traverse = False
                elif is_truncated_dir:
                    display_name = f"{item.name}/..."
                    should_traverse = False
                else:
                    display_name = item.name
                    should_traverse = item.is_dir()

                lines.append(f"{prefix}{connector}{icon}{display_name}{desc}")

                if should_traverse:
                    extension = "    " if is_last else "│   "
                    lines.extend(
                        self.build_tree(
                            item,
                            use_emojis,
                            max_depth,
                            current_depth + 1,
                            prefix + extension,
                        )
                    )
        except Exception:
            pass

        return lines
