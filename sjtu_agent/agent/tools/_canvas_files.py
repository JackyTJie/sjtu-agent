"""sjtu_agent/agent/tools/_canvas_files.py — Canvas file browsing, download & tracking tools.

Exports:
- ``TOOLS_ENTRIES`` — list of OpenAI function-calling schema dicts
- ``tool_*`` functions — each returns a dict; dispatched by ``run_tool()``
"""

from __future__ import annotations

from sjtu_agent.canvas_client import CanvasError
from sjtu_agent.canvas_files import CanvasFilesTracker
from sjtu_agent.agent.tools._canvas_utils import (
    _make_canvas_client,
    _canvas_error_payload,
    _resolve_canvas_course_or_error,
)

# ══════════════════════════════════════════════════════════════════════════════
# Tool schema definitions
# ══════════════════════════════════════════════════════════════════════════════

TOOLS_ENTRIES = [
    {
        "type": "function",
        "function": {
            "name": "list_canvas_folders",
            "description": (
                "列出 Canvas 课程中的文件夹。可以指定某个文件夹 ID 来列出其子文件夹。"
                "用课程名称/代码/ID 来定位课程。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course": {
                        "type": "string",
                        "description": "课程名称、课程代码或 course_id，如「高等数学」「MATH1201」「92337」",
                    },
                    "folder_id": {
                        "type": "integer",
                        "description": "可选，指定文件夹 ID 以列出子文件夹",
                    },
                },
                "required": ["course"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_canvas_files",
            "description": (
                "列出 Canvas 课程中的文件。可以按文件夹 ID 或搜索关键词筛选。"
                "用于查找课程资料、课件、作业文件等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course": {
                        "type": "string",
                        "description": "课程名称、课程代码或 course_id",
                    },
                    "folder_id": {
                        "type": "integer",
                        "description": "可选，只列出指定文件夹中的文件",
                    },
                    "search": {
                        "type": "string",
                        "description": "可选，按文件名搜索（支持 Canvas search_term 参数）",
                    },
                },
                "required": ["course"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_file_tree",
            "description": (
                "显示 Canvas 课程中所有文件夹和文件的完整目录树。"
                "包含文件夹层级结构和每个文件的 size/mime 信息。"
                "参数需要课程名/代码或数字 course_id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course": {
                        "type": "string",
                        "description": "课程名称、课程代码或 course_id",
                    },
                },
                "required": ["course"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download_canvas_file",
            "description": (
                "根据文件 ID 下载 Canvas 课程文件到本地。"
                "下载路径默认为 canvas_downloads 目录，可自定义。"
                "先通过 list_canvas_files 或 canvas_file_tree 获取文件 ID。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "integer",
                        "description": "Canvas 文件 ID（从 list_canvas_files 或 canvas_file_tree 获取）",
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "可选，下载目录路径。默认为 canvas_downloads 目录",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_track_mark",
            "description": (
                "将 Canvas 文件标记为「已处理」（已整合到笔记）。"
                "可以添加备注说明该文件被整合到了哪里。"
                "用户说「把这个文件标记为已读」「标记为已处理」「这个课件我已经整理了」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "integer",
                        "description": "Canvas 文件 ID",
                    },
                    "name": {
                        "type": "string",
                        "description": "可选，文件名称。不提供则自动从 Canvas 获取",
                    },
                    "course_id": {
                        "type": "integer",
                        "description": "可选，课程 ID。不提供则自动从 Canvas 获取",
                    },
                    "notes": {
                        "type": "string",
                        "description": "可选备注，如「已整理到第3章笔记」「已做思维导图」",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_track_unmark",
            "description": (
                "取消 Canvas 文件的「已处理」标记，将其从处理列表中移除。"
                "用户说「取消标记」「这个文件还没整理」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "integer",
                        "description": "Canvas 文件 ID",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_track_list",
            "description": (
                "列出所有已标记为已处理的 Canvas 文件（跨全部课程）。"
                "按处理时间倒序排列。用户说「列出已处理的文件」「哪些课件我已经整理过了」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_track_status",
            "description": (
                "显示 Canvas 课程的文件处理进度。在文件树中标注 ✅ 已处理 / ⏳ 未处理，"
                "并在末尾显示完成百分比。用户说「看看这门课还有多少没整理」「课件处理进度」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course": {
                        "type": "string",
                        "description": "课程名称、课程代码或 course_id",
                    },
                },
                "required": ["course"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_track_diff",
            "description": (
                "只显示 Canvas 课程中尚未处理的文件（新增/未整理）。"
                "用于快速查看有哪些课件还没看。用户说「有哪些新文件」「哪些课件没看」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course": {
                        "type": "string",
                        "description": "课程名称、课程代码或 course_id",
                    },
                },
                "required": ["course"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "canvas_track_mark_course",
            "description": (
                "将 Canvas 课程中的全部文件标记为已处理。"
                "适用于初次同步时批量标记。用户说「标记这门课的所有文件」「这门课已经全部整理完了」时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course": {
                        "type": "string",
                        "description": "课程名称、课程代码或 course_id",
                    },
                },
                "required": ["course"],
            },
        },
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# Tool implementations
# ══════════════════════════════════════════════════════════════════════════════

def tool_list_canvas_folders(course: str, folder_id: int | None = None) -> dict:
    """List folders in a Canvas course."""
    try:
        client = _make_canvas_client()
        resolved = _resolve_canvas_course_or_error(client, course)
        if not resolved.get("ok"):
            return resolved
        course_info = resolved["course"]
        result = client.list_folders(course_info["course_id"], folder_id=folder_id)
        result["course"] = course_info
        return result
    except CanvasError as exc:
        return _canvas_error_payload(exc)


def tool_list_canvas_files(
    course: str,
    folder_id: int | None = None,
    search: str | None = None,
) -> dict:
    """List files in a Canvas course."""
    try:
        client = _make_canvas_client()
        resolved = _resolve_canvas_course_or_error(client, course)
        if not resolved.get("ok"):
            return resolved
        course_info = resolved["course"]
        result = client.list_files(
            course_info["course_id"],
            folder_id=folder_id,
            search=search,
        )
        result["course"] = course_info
        return result
    except CanvasError as exc:
        return _canvas_error_payload(exc)


def tool_canvas_file_tree(course: str) -> dict:
    """Show folder/file tree for a Canvas course."""
    try:
        client = _make_canvas_client()
        resolved = _resolve_canvas_course_or_error(client, course)
        if not resolved.get("ok"):
            return resolved
        course_info = resolved["course"]
        result = client.get_folder_tree(course_info["course_id"])
        result["course"] = course_info
        return result
    except CanvasError as exc:
        return _canvas_error_payload(exc)


def tool_download_canvas_file(file_id: int, output_dir: str = "") -> dict:
    """Download a Canvas file by file ID."""
    try:
        client = _make_canvas_client()
        od = output_dir if output_dir else None
        result = client.download_file(file_id, output_dir=od)
        return result
    except CanvasError as exc:
        return _canvas_error_payload(exc)


def tool_canvas_track_mark(
    file_id: int,
    name: str = "",
    course_id: int | None = None,
    notes: str = "",
) -> dict:
    """Mark a file as processed."""
    tracker = CanvasFilesTracker()
    display_name = name
    resolved_course_id = course_id

    # If name or course_id missing, fetch from Canvas API
    if not display_name or resolved_course_id is None:
        try:
            client = _make_canvas_client()
            info = client.get_file(file_id)
            if info.get("ok"):
                fdata = info["file"]
                if not display_name:
                    display_name = fdata.get("display_name", str(file_id))
                if resolved_course_id is None:
                    resolved_course_id = fdata.get("course_id")
        except Exception:
            if not display_name:
                display_name = str(file_id)

    return tracker.mark(file_id, display_name, course_id=resolved_course_id, notes=notes)


def tool_canvas_track_unmark(file_id: int) -> dict:
    """Remove a file from the processed list."""
    tracker = CanvasFilesTracker()
    try:
        return tracker.unmark(file_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}


def tool_canvas_track_list() -> dict:
    """List all processed files."""
    tracker = CanvasFilesTracker()
    return tracker.list_all()


def tool_canvas_track_status(course: str) -> dict:
    """Show course file tree with processed/unprocessed markers."""
    try:
        client = _make_canvas_client()
        resolved = _resolve_canvas_course_or_error(client, course)
        if not resolved.get("ok"):
            return resolved
        course_info = resolved["course"]
        course_id = course_info["course_id"]

        tree = client.get_folder_tree(course_id)
        if not tree.get("ok"):
            return tree

        tracker = CanvasFilesTracker()
        result = tracker.get_course_status(course_id, tree)
        result["course"] = course_info
        return result
    except CanvasError as exc:
        return _canvas_error_payload(exc)


def tool_canvas_track_diff(course: str) -> dict:
    """Show only unprocessed files in a course."""
    try:
        client = _make_canvas_client()
        resolved = _resolve_canvas_course_or_error(client, course)
        if not resolved.get("ok"):
            return resolved
        course_info = resolved["course"]
        course_id = course_info["course_id"]

        tree = client.get_folder_tree(course_id)
        if not tree.get("ok"):
            return tree

        tracker = CanvasFilesTracker()
        result = tracker.get_course_diff(course_id, tree)
        result["course"] = course_info
        return result
    except CanvasError as exc:
        return _canvas_error_payload(exc)


def tool_canvas_track_mark_course(course: str) -> dict:
    """Mark all files in a course as processed."""
    try:
        client = _make_canvas_client()
        resolved = _resolve_canvas_course_or_error(client, course)
        if not resolved.get("ok"):
            return resolved
        course_info = resolved["course"]
        course_id = course_info["course_id"]

        # Get flat list of ALL files
        files_result = client.list_files(course_id)
        files_list = files_result.get("files", [])

        tracker = CanvasFilesTracker()
        result = tracker.mark_course(course_id, files_list)
        result["course"] = course_info
        return result
    except CanvasError as exc:
        return _canvas_error_payload(exc)
