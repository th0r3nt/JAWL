def format_size(size_bytes: int) -> str:
    """Переводит байты в человекочитаемый формат (B, KB, MB)."""

    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
