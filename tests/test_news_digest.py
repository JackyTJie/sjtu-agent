"""Tests for sjtu_agent/news_aggregator/digest.py — digest builder."""
from datetime import datetime, timezone, timedelta

import pytest

from sjtu_agent.news_aggregator.digest import (
    DigestBuilder, _report_label, _age_str,
)


class FakeNewsItem:
    def __init__(self, id=1, title="Test", source="jwc", summary="summary",
                 url="https://example.com", author="", published_hours_ago=1):
        self.id = id
        self.title = title
        self.source = source
        self.summary = summary
        self.url = url
        self.author = author
        self._published_hours_ago = published_hours_ago

    def age_hours(self):
        return self._published_hours_ago


class FakeProfile:
    def load(self):
        return {"interests": {"AI": 0.9, "学术": 0.7}, "blocked_categories": []}


class TestReportLabel:
    def test_morning(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        assert _report_label() == "早报"

    def test_noon(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 12, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        assert _report_label() == "午报"

    def test_afternoon(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 15, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        assert _report_label() == "日报"

    def test_evening(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        assert _report_label() == "晚报"

    def test_night(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 3, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        assert _report_label() == "简报"


class TestAgeStr:
    def test_just_now(self):
        item = FakeNewsItem(published_hours_ago=0.5)
        assert "刚刚" in _age_str(item)

    def test_hours_ago(self):
        item = FakeNewsItem(published_hours_ago=5)
        assert "小时前" in _age_str(item)

    def test_days_ago(self):
        item = FakeNewsItem(published_hours_ago=48)
        assert "天前" in _age_str(item)


class TestDigestBuilder:
    def setup_method(self):
        self.builder = DigestBuilder()

    def test_build_empty(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        result = self.builder.build([], FakeProfile())
        assert "SJTU" in result
        assert "今天没有" in result

    def test_build_with_items(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        item = FakeNewsItem(title="重要通知", published_hours_ago=2)
        ranked = [(item, 0.9, "important")]
        result = self.builder.build(ranked, FakeProfile())
        assert "早报" in result
        assert "重要通知" in result
        assert "重要" in result  # section header

    def test_build_sorts_by_score(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        important = FakeNewsItem(id=1, title="重要")
        relevant = FakeNewsItem(id=2, title="相关")
        general = FakeNewsItem(id=3, title="其他")
        ranked = [(important, 0.9, ""), (relevant, 0.7, ""), (general, 0.5, "")]
        result = self.builder.build(ranked, FakeProfile())
        assert "重要" in result

    def test_build_feishu_post(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        item = FakeNewsItem(title="通知", url="https://example.com", published_hours_ago=1)
        ranked = [(item, 0.9, "good reason")]
        result = self.builder.build_feishu_post(ranked, FakeProfile())
        assert isinstance(result, list)
        assert len(result) > 0
        # First paragraph should be the header
        assert any("SJTU" in el.get("text", "") for para in result for el in para if el.get("tag") == "text")

    def test_build_feishu_post_empty(self, monkeypatch):
        class FakeNow:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 6, 18, 8, 0, tzinfo=timezone(timedelta(hours=8)))
        monkeypatch.setattr("sjtu_agent.news_aggregator.digest.datetime", FakeNow)
        result = self.builder.build_feishu_post([], FakeProfile())
        assert isinstance(result, list)
        assert len(result) == 2  # header + empty message

    def test_render_item_show_reason(self):
        item = FakeNewsItem(title="A", url="https://x.com")
        lines = self.builder._render_item(item, 0.9, "good reason", show_reason=True)
        assert any("good reason" in l for l in lines)

    def test_render_item_no_reason(self):
        item = FakeNewsItem(title="A")
        lines = self.builder._render_item(item, 0.5, "reason", show_reason=False)
        assert not any("reason" in l for l in lines)

    def test_footer_includes_commands(self):
        item = FakeNewsItem(title="X")
        ranked = [(item, 0.5, "")]
        result = self.builder.build(ranked, FakeProfile())
        assert "/news_block" in result
        assert "/news_reset" in result
