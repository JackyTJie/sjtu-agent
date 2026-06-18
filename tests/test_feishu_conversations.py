"""Tests for sjtu_agent/feishu/conversations.py — FeishuConversationManager."""
import tempfile
from pathlib import Path

import pytest

from sjtu_agent.feishu.conversations import FeishuConversationManager


@pytest.fixture
def mgr():
    """Create a manager with a temp directory (no disk persistence)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        m = FeishuConversationManager(Path(tmpdir))
        yield m


class TestEnsureUser:
    def test_creates_default_conv(self, mgr):
        mgr.ensure_user("user-a")
        assert "user-a" in mgr.sessions
        assert "user-a" in mgr.locks
        convs = mgr.sessions["user-a"]["conversations"]
        assert len(convs) == 1
        assert convs[0]["name"] == "默认"

    def test_ensure_user_idempotent(self, mgr):
        mgr.ensure_user("user-a")
        first_len = len(mgr.sessions["user-a"]["conversations"])
        mgr.ensure_user("user-a")
        assert len(mgr.sessions["user-a"]["conversations"]) == first_len

    def test_multi_user_isolation(self, mgr):
        mgr.ensure_user("user-a")
        mgr.ensure_user("user-b")
        assert "user-a" in mgr.sessions
        assert "user-b" in mgr.sessions
        # Each should have their own lock
        assert mgr.locks["user-a"] is not mgr.locks["user-b"]


class TestGetActive:
    def test_returns_conv_meta_lock(self, mgr):
        conv, meta, lock = mgr.get_active("user-x")
        assert conv["name"] == "默认"
        assert meta["current_idx"] == 0
        assert lock is mgr.locks["user-x"]


class TestHandleCommand:
    def test_list_empty(self, mgr):
        result = mgr.handle_command("u1", "/list", ["/list"])
        assert "1 个对话" in result or "共" in result

    def test_new(self, mgr):
        result = mgr.handle_command("u1", "/new", ["/new", "学习"])
        assert "OK" in result
        assert "学习" in result
        assert len(mgr.sessions["u1"]["conversations"]) == 2

    def test_new_default_name(self, mgr):
        result = mgr.handle_command("u1", "/new", ["/new"])
        assert "OK" in result

    def test_switch_valid(self, mgr):
        mgr.handle_command("u1", "/new", ["/new", "conv2"])
        result = mgr.handle_command("u1", "/switch", ["/switch", "1"])
        assert "OK" in result

    def test_switch_invalid_index(self, mgr):
        result = mgr.handle_command("u1", "/switch", ["/switch", "99"])
        assert "无效序号" in result

    def test_switch_missing_arg(self, mgr):
        result = mgr.handle_command("u1", "/switch", ["/switch"])
        assert "用法" in result

    def test_name_rename(self, mgr):
        mgr.handle_command("u1", "/new", ["/new", "原名"])
        result = mgr.handle_command("u1", "/name", ["/name", "2", "新名"])
        assert "新名" in result
        assert "OK" in result

    def test_name_invalid_index(self, mgr):
        result = mgr.handle_command("u1", "/name", ["/name", "99", "x"])
        assert "无效序号" in result

    def test_delete(self, mgr):
        mgr.handle_command("u1", "/new", ["/new", "c2"])
        result = mgr.handle_command("u1", "/delete", ["/delete", "1"])
        assert "已删除" in result

    def test_delete_last_conv(self, mgr):
        result = mgr.handle_command("u1", "/delete", ["/delete", "1"])
        assert "至少保留一个" in result

    def test_history(self, mgr):
        result = mgr.handle_command("u1", "/history", ["/history"])
        assert "暂无消息" in result

    def test_unknown_command_returns_none(self, mgr):
        result = mgr.handle_command("u1", "/unknown", ["/unknown"])
        assert result is None


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        mgr1 = FeishuConversationManager(tmp_path)
        mgr1.ensure_user("user-a")
        mgr1.handle_command("user-a", "/new", ["/new", "测试对话"])
        mgr1.save()

        mgr2 = FeishuConversationManager(tmp_path)
        mgr2.load()
        assert "user-a" in mgr2.sessions
        convs = mgr2.sessions["user-a"]["conversations"]
        assert len(convs) == 2
        assert convs[1]["name"] == "测试对话"
