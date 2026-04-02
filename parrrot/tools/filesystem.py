"""
Parrrot — Filesystem tools (read, write, list, delete, move, search)
Part of the Parrrot open-source personal AI assistant.
https://github.com/Ahilan-1/parrrot
"""

from __future__ import annotations

import os
import platform
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from parrrot.tools.registry import registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _desktop_path() -> Path:
    """Find the real Desktop path — handles OneDrive-moved Desktop on Windows."""
    system = platform.system()
    candidates: list[Path] = []

    if system == "Windows":
        # OneDrive often moves Desktop to OneDrive/Desktop
        onedrive = os.environ.get("OneDrive", "")
        if onedrive:
            candidates.append(Path(onedrive) / "Desktop")
        candidates.append(Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop")
        # Registry query for the actual shell folder path
        try:
            import winreg  # type: ignore[import]
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            )
            val, _ = winreg.QueryValueEx(key, "Desktop")
            winreg.CloseKey(key)
            candidates.insert(0, Path(val))
        except Exception:
            pass
    else:
        candidates.append(Path.home() / "Desktop")

    for p in candidates:
        if p.exists():
            return p
    return Path.home()


def _safe_path(path: str) -> Path:
    """Expand ~ and env vars, return absolute Path."""
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _list_files(path: str = ".", pattern: Optional[str] = None) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"Path not found: {p}"
    if not p.is_dir():
        return f"Not a directory: {p}"

    if pattern:
        items = list(p.glob(pattern))
    else:
        items = list(p.iterdir())

    if not items:
        return f"Empty directory: {p}"

    lines = []
    for item in sorted(items):
        suffix = "/" if item.is_dir() else ""
        size = f"  ({item.stat().st_size:,} bytes)" if item.is_file() else ""
        lines.append(f"{'📁' if item.is_dir() else '📄'} {item.name}{suffix}{size}")
    return "\n".join(lines)


def _read_file(path: str, max_chars: int = 50000) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"File not found: {p}"
    if not p.is_file():
        return f"Not a file: {p}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + f"\n\n[...truncated — {len(text)} total chars]"
        return text
    except Exception as e:
        return f"Error reading file: {e}"


def _write_file(path: str, content: str) -> str:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {p}"


def _delete_file(path: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        return f"Not found: {p}"
    if p.is_dir():
        shutil.rmtree(p)
        return f"Deleted directory: {p}"
    p.unlink()
    return f"Deleted: {p}"


def _move_file(src: str, dst: str) -> str:
    s = _safe_path(src)
    d = _safe_path(dst)
    if not s.exists():
        return f"Source not found: {s}"
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return f"Moved {s} → {d}"


def _search_files(query: str, directory: str = "~", content_search: bool = False) -> str:
    base = _safe_path(directory)
    if not base.exists():
        return f"Directory not found: {base}"

    results: list[str] = []
    q = query.lower()

    for item in base.rglob("*"):
        if item.is_file():
            # Name match
            if q in item.name.lower():
                results.append(f"📄 {item}")
            # Content match
            elif content_search:
                try:
                    text = item.read_text(encoding="utf-8", errors="ignore")
                    if q in text.lower():
                        results.append(f"📝 {item}  [content match]")
                except Exception:
                    pass
        if len(results) >= 50:
            results.append("... (too many results, showing first 50)")
            break

    if not results:
        return f"No files matching '{query}' found in {base}"
    return "\n".join(results)


def get_desktop_contents() -> list[str]:
    """Return list of items on the user's desktop (used by onboarding demo)."""
    desktop = _desktop_path()
    if not desktop.exists():
        return []
    return [item.name for item in desktop.iterdir()]


def _get_desktop_contents_tool() -> str:
    items = get_desktop_contents()
    if not items:
        return "Your desktop is empty."
    lines = [f"{'📁' if ((_desktop_path() / i).is_dir()) else '📄'} {i}" for i in items]
    return f"Desktop ({len(items)} items):\n" + "\n".join(lines)


def _clean_desktop(organize_by: str = "type") -> str:
    desktop = _desktop_path()
    if not desktop.exists():
        return f"Desktop not found. Searched: {desktop}"

    # Collect items — skip hidden files, the special "desktop.ini", and the
    # organiser folders we're about to create (so re-running is safe).
    _SKIP_NAMES = {"desktop.ini", "Desktop.ini", "thumbs.db", ".DS_Store"}
    _SKIP_FOLDERS = {
        "images", "documents", "spreadsheets", "presentations",
        "videos", "audio", "archives", "code", "shortcuts", "folders", "misc",
    }

    items = [
        i for i in desktop.iterdir()
        if i.name not in _SKIP_NAMES
        and not i.name.startswith(".")
        and not (i.is_dir() and i.name.lower() in _SKIP_FOLDERS)
    ]

    if not items:
        return f"Desktop is already clean! ({desktop})"

    type_map = {
        "images":        {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic", ".tiff", ".raw"},
        "documents":     {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md", ".epub"},
        "spreadsheets":  {".xls", ".xlsx", ".csv", ".ods", ".numbers"},
        "presentations": {".ppt", ".pptx", ".odp", ".key"},
        "videos":        {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v", ".3gp"},
        "audio":         {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma"},
        "archives":      {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz", ".iso"},
        "code":          {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".go", ".rs", ".sh", ".bat", ".ps1", ".json", ".xml", ".yaml", ".toml"},
        "shortcuts":     {".lnk", ".url", ".webloc"},
    }

    ext_to_folder: dict[str, str] = {}
    for folder, exts in type_map.items():
        for ext in exts:
            ext_to_folder[ext] = folder

    moved: dict[str, list[str]] = {}
    skipped: list[str] = []
    errors: list[str] = []

    for item in items:
        # Decide destination folder
        if item.is_dir():
            dest_folder = "folders"
        else:
            dest_folder = ext_to_folder.get(item.suffix.lower(), "misc")

        dest_dir = desktop / dest_folder
        try:
            dest_dir.mkdir(exist_ok=True)
        except Exception as e:
            errors.append(f"Cannot create {dest_folder}/: {e}")
            continue

        dest = dest_dir / item.name

        # Safe rename if destination exists
        if dest.exists():
            stem, suffix = item.stem, item.suffix
            for n in range(1, 1000):
                candidate = dest_dir / f"{stem} ({n}){suffix}"
                if not candidate.exists():
                    dest = candidate
                    break

        try:
            shutil.move(str(item), str(dest))
            moved.setdefault(dest_folder, []).append(item.name)
        except PermissionError:
            skipped.append(f"{item.name} (in use / protected)")
        except Exception as e:
            errors.append(f"{item.name}: {e}")

    total = sum(len(v) for v in moved.values())
    lines = [f"✓ Cleaned desktop at {desktop}"]
    lines.append(f"  Moved {total} item(s), skipped {len(skipped)}, failed {len(errors)}\n")

    for folder, names in sorted(moved.items()):
        preview = ", ".join(names[:4])
        more = f" … +{len(names)-4} more" if len(names) > 4 else ""
        lines.append(f"  📁 {folder}/  ← {len(names)}: {preview}{more}")

    if skipped:
        lines.append(f"\n  ⚠ Skipped (in use or protected):")
        for s in skipped:
            lines.append(f"    • {s}")
    if errors:
        lines.append(f"\n  ✗ Errors:")
        for e in errors:
            lines.append(f"    • {e}")

    return "\n".join(lines)


def _zip_files(files: list[str], output: str) -> str:
    out = _safe_path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            p = _safe_path(f)
            if p.is_file():
                zf.write(p, p.name)
                count += 1
            elif p.is_dir():
                for sub in p.rglob("*"):
                    if sub.is_file():
                        zf.write(sub, sub.relative_to(p.parent))
                        count += 1
    return f"Created {out} with {count} file(s)"


def _get_recent_files(n: int = 10, directory: str = "~") -> str:
    base = _safe_path(directory)
    files = [f for f in base.rglob("*") if f.is_file()]
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    lines = []
    for f in files[:n]:
        import datetime
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
        lines.append(f"📄 {f}  ({mtime.strftime('%Y-%m-%d %H:%M')})")
    return "\n".join(lines) if lines else "No files found."


# ---------------------------------------------------------------------------
# Register tools
# ---------------------------------------------------------------------------

registry.register(
    "list_files",
    "List files and folders at a path",
    {"path": "directory path (default: current dir)", "pattern": "optional glob pattern like *.txt"},
)(_list_files)

registry.register(
    "read_file",
    "Read the text content of a file",
    {"path": "file path"},
)(_read_file)

registry.register(
    "write_file",
    "Write or overwrite a file with given content",
    {"path": "file path", "content": "text content to write"},
)(_write_file)

registry.register(
    "delete_file",
    "Delete a file or directory",
    {"path": "file or directory path"},
    requires_confirm=True,
)(_delete_file)

registry.register(
    "move_file",
    "Move or rename a file or directory",
    {"src": "source path", "dst": "destination path"},
)(_move_file)

registry.register(
    "search_files",
    "Search for files by name or content",
    {
        "query": "search term",
        "directory": "directory to search (default: home)",
        "content_search": "also search inside files (true/false)",
    },
)(_search_files)

registry.register(
    "get_desktop_contents",
    "List everything on the user's desktop",
    {},
)(_get_desktop_contents_tool)

registry.register(
    "clean_desktop",
    "Organize the desktop by moving files into subfolders by type (images, documents, videos, etc.)",
    {"organize_by": "how to organize: 'type' (default)"},
)(_clean_desktop)

registry.register(
    "zip_files",
    "Create a zip archive from a list of files/folders",
    {"files": "list of file paths", "output": "output zip file path"},
)(_zip_files)

registry.register(
    "get_recent_files",
    "Get recently modified files",
    {"n": "number of files (default 10)", "directory": "search directory (default: home)"},
)(_get_recent_files)
