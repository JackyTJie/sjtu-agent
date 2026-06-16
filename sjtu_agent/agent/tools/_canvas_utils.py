"""sjtu_agent/agent/tools/_canvas_utils.py — shared Canvas helpers.

These are used by both ``_core.py`` and ``_canvas_files.py`` to avoid
circular imports when submodules need Canvas client access.
"""

from __future__ import annotations

from sjtu_agent.canvas_client import CanvasError, make_client_from_config

_CANVAS_DEFAULT_BASE_URL = "https://oc.sjtu.edu.cn"


def _canvas_settings_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/profile/settings"


def _make_canvas_client():
    """Create a CanvasClient from config.json."""
    return make_client_from_config()


def _canvas_error_payload(exc: CanvasError) -> dict:
    """Format a CanvasError into a dict the LLM can understand."""
    import ddl_checker as dc
    payload = exc.to_dict()
    if exc.code in ("missing_token", "invalid_token"):
        base = dc.load_config().get("canvas_base_url", _CANVAS_DEFAULT_BASE_URL)
        payload["settings_url"] = _canvas_settings_url(base)
        payload["next_action"] = "请先调用 setup_canvas 获取或刷新 Canvas Token。"
    return payload


def _resolve_canvas_course_or_error(client, course) -> dict:
    """Resolve a course by name/code/id. Returns {"ok": True, "course": ...} or error."""
    resolved = client.resolve_course(course)
    if not resolved.get("ok"):
        return resolved
    return {"ok": True, "course": resolved["course"]}
