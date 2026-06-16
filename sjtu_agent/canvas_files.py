"""sjtu_agent/canvas_files.py — Canvas processed-file tracking.

CanvasFilesTracker persists which Canvas course files have been "processed"
(integrated into notes).  The state file lives at CANVAS_PROCESSED_FILES_PATH
inside the runtime data directory and uses atomic writes to avoid corruption.

Schema (compatible with the standalone canvas/ skill)::

    {
      "13339023": {
        "display_name": "255-su260512.pdf",
        "course_id": 92337,
        "size": 12345,
        "processed_at": "2026-06-16T17:32:57.787886",
        "notes": "线性方程组与矩阵"
      }
    }

On first init, if the state file doesn't exist but a legacy file is found at
``canvas/processed_files.json`` relative to the project root, it is copied
automatically.
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from typing import Any

from sjtu_agent.paths import (
    CANVAS_PROCESSED_FILES_PATH,
    PROJECT_ROOT,
    atomic_write_json,
    read_json_safe,
)


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


class CanvasFilesTracker:
    """Track which Canvas course files have been processed.

    Usage::

        tracker = CanvasFilesTracker()
        tracker.mark(13339023, "slides.pdf", course_id=92337, notes="已整理")
        status = tracker.get_course_status(92337, tree)
    """

    def __init__(self, path: Path | None = None):
        self._path = path or CANVAS_PROCESSED_FILES_PATH
        # One-time migration from legacy canvas/processed_files.json
        self._migrate_if_needed()

    # ── public API ───────────────────────────────────────────────────────

    def mark(
        self,
        file_id: int,
        display_name: str,
        course_id: int | None = None,
        notes: str = "",
    ) -> dict:
        """Mark a file as processed.

        Returns a dict with ``success``, ``file_id``, ``display_name``, …
        """
        db = self._load()
        key = str(file_id)
        entry = db.get(key, {})
        entry["display_name"] = display_name
        if course_id is not None:
            entry["course_id"] = course_id
        entry["processed_at"] = _now_iso()
        if notes:
            entry["notes"] = notes
        db[key] = entry
        self._save(db)
        return {
            "success": True,
            "file_id": file_id,
            "display_name": display_name,
            "course_id": course_id,
            "notes": notes,
        }

    def unmark(self, file_id: int) -> dict:
        """Remove a file from the processed list.

        Raises ValueError if the file was not tracked.
        """
        db = self._load()
        key = str(file_id)
        if key not in db:
            raise ValueError(f"文件 {file_id} 不在已处理列表中")
        info = db.pop(key)
        self._save(db)
        return {
            "success": True,
            "file_id": file_id,
            "display_name": info.get("display_name", ""),
            "action": "unmarked",
        }

    def list_all(self) -> dict:
        """Return all processed files across all courses, most recent first."""
        db = self._load()
        items: list[dict] = []
        for fid, info in db.items():
            size_val = info.get("size")
            items.append({
                "file_id": int(fid),
                "display_name": info.get("display_name", "?"),
                "course_id": info.get("course_id"),
                "processed_at": info.get("processed_at", ""),
                "notes": info.get("notes", ""),
                "size": size_val,
                "size_human": _format_size_human(size_val) if size_val else "?",
            })
        items.sort(key=lambda x: x.get("processed_at") or "", reverse=True)
        return {"ok": True, "count": len(items), "files": items}

    def get_course_status(self, course_id: int, tree: dict) -> dict:
        """Annotate a folder tree with processed/unprocessed status.

        ``tree`` should be the result of ``CanvasClient.get_folder_tree()``
        (``{"ok": True, "tree": [...]}``).

        Returns the same tree shape with each file node gaining a
        ``processed`` (bool) field, plus summary counts.
        """
        db = self._load()
        stats = {"processed": 0, "unprocessed": 0}

        def _annotate_node(node: dict) -> dict:
            annotated_files = []
            for f in node.get("files", []):
                fid = str(f.get("id", ""))
                is_proc = fid in db
                entry = dict(f)
                entry["processed"] = is_proc
                if is_proc:
                    stats["processed"] += 1
                else:
                    stats["unprocessed"] += 1
                annotated_files.append(entry)
            return {
                **node,
                "files": annotated_files,
                "folders": [_annotate_node(child) for child in node.get("folders", [])],
            }

        annotated_tree = [_annotate_node(n) for n in tree.get("tree", [])]
        total = stats["processed"] + stats["unprocessed"]
        pct = (stats["processed"] / total * 100) if total > 0 else 0

        return {
            "ok": True,
            "course_id": course_id,
            "processed_count": stats["processed"],
            "unprocessed_count": stats["unprocessed"],
            "total": total,
            "pct": round(pct, 1),
            "tree": annotated_tree,
        }

    def get_course_diff(self, course_id: int, tree: dict) -> dict:
        """Return only unprocessed files from a folder tree.

        Each returned item includes its folder path for context.
        """
        db = self._load()
        unprocessed: list[dict] = []

        def _extract(node: dict, folder_path: str = ""):
            current_path = f"{folder_path}/{node.get('name','')}" if folder_path else node.get("name", "")
            for f in node.get("files", []):
                fid = str(f.get("id", ""))
                if fid not in db:
                    entry = dict(f)
                    entry["folder_path"] = current_path or "/"
                    unprocessed.append(entry)
            for child in node.get("folders", []):
                _extract(child, current_path)

        for n in tree.get("tree", []):
            _extract(n)

        return {
            "ok": True,
            "course_id": course_id,
            "count": len(unprocessed),
            "files": unprocessed,
        }

    def mark_course(self, course_id: int, files_list: list[dict]) -> dict:
        """Mark all files in a course as processed.

        ``files_list`` is a flat list of dicts with ``id`` and ``display_name``
        keys (e.g. from ``CanvasClient.list_files()["files"]``).
        """
        db = self._load()
        now = _now_iso()
        count = 0
        for f in files_list:
            fid = str(f.get("id", ""))
            if not fid:
                continue
            if fid not in db:
                db[fid] = {
                    "display_name": f.get("display_name", ""),
                    "course_id": course_id,
                    "size": f.get("size"),
                    "processed_at": now,
                }
                count += 1
        self._save(db)
        return {
            "success": True,
            "course_id": course_id,
            "files_marked": count,
            "total_in_course": len(files_list),
        }

    # ── internal ─────────────────────────────────────────────────────────

    def _load(self) -> dict[str, dict]:
        return read_json_safe(self._path, default={})

    def _save(self, data: dict[str, dict]) -> None:
        atomic_write_json(self._path, data)

    def _migrate_if_needed(self) -> None:
        """Copy legacy canvas/processed_files.json if it exists."""
        if self._path.exists():
            return
        legacy = PROJECT_ROOT / "canvas" / "processed_files.json"
        if legacy.exists() and legacy.is_file():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, self._path)


def _format_size_human(size_bytes: int | None) -> str:
    """Human-readable file size (standalone copy to avoid circular import)."""
    if size_bytes is None:
        return "?"
    s = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if s < 1024:
            return f"{s:.1f} {unit}" if unit != "B" else f"{int(s)} B"
        s /= 1024
    return f"{s:.1f} TB"
