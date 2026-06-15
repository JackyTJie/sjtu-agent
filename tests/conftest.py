"""pytest config — set up test environment before any test module is imported."""

import json
import os
import tempfile
from pathlib import Path


def pytest_configure(config):
    """Create a minimal config.json for modules that require it (e.g. feishu_bot)."""
    home = os.environ.get("SJTU_AGENT_HOME")
    if home and Path(home, "config.json").exists():
        return  # already configured

    fake_home = tempfile.mkdtemp(prefix="sjtu_test_")
    fake_config = Path(fake_home) / "config.json"
    fake_config.write_text(json.dumps({
        "feishu_app_id": "cli_test",
        "feishu_app_secret": "test_secret",
    }), encoding="utf-8")
    os.environ["SJTU_AGENT_HOME"] = fake_home
