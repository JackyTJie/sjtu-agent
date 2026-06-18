"""sjtu_agent/news_aggregator/digest.py — 日报 Markdown 生成器。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sjtu_agent.news_aggregator.sources.base import NewsItem
    from sjtu_agent.news_aggregator.profile import UserProfile

CST = timezone(timedelta(hours=8))


def _report_label() -> str:
    """根据当前小时返回对应报别。"""
    h = datetime.now(CST).hour
    if 6 <= h < 11:
        return "早报"
    if 11 <= h < 14:
        return "午报"
    if 14 <= h < 18:
        return "日报"
    if 18 <= h < 23:
        return "晚报"
    return "简报"


_SOURCE_EMOJI = {
    "jwc":      "🏫",
    "shuiyuan": "💬",
    "official": "📰",
    "canvas":   "📚",
    "wechat_mp": "📱",
}

_SOURCE_NAME = {
    "jwc":      "教务处",
    "shuiyuan": "水源社区",
    "official": "交大新闻网",
    "canvas":   "Canvas",
    "wechat_mp": "微信公众号",
}


def _age_str(item: "NewsItem") -> str:
    try:
        h = item.age_hours()
        if h < 1:
            return "刚刚"
        elif h < 24:
            return f"{int(h)}小时前"
        else:
            return f"{int(h/24)}天前"
    except Exception:
        return ""


class DigestBuilder:
    """生成 Markdown 格式的日报。"""

    def build(
        self,
        ranked: list[tuple["NewsItem", float, str]],
        profile: "UserProfile",
    ) -> str:
        now = datetime.now(CST)
        label = _report_label()
        weekday = "一二三四五六日"[now.weekday()]
        date_str = now.strftime(f"%Y-%m-%d 周{weekday}")

        if not ranked:
            return (
                f"📰 **SJTU {label} · {date_str}**\n\n"
                "今天没有特别值得关注的新内容，继续加油！"
            )

        profile_data = profile.load()
        interests = profile_data.get("interests", {})
        top_tags = sorted(interests.items(), key=lambda x: x[1], reverse=True)[:3]
        tags_str = "、".join(f"「{t}」" for t, _ in top_tags) if top_tags else "校园动态"

        lines = [
            f"📰 **SJTU {label} · {date_str}**",
            "",
            f"💡 为你精选 **{len(ranked)} 条**（基于 {tags_str}）",
            "",
            "---",
            "",
        ]

        # 按分数分层
        important = [(i, s, r) for i, s, r in ranked if s >= 0.8]
        relevant  = [(i, s, r) for i, s, r in ranked if 0.6 <= s < 0.8]
        general   = [(i, s, r) for i, s, r in ranked if s < 0.6]

        if important:
            lines.append("## 🔥 重要")
            lines.append("")
            for item, score, reason in important:
                lines.extend(self._render_item(item, score, reason, show_reason=True))
                lines.append("")

        if relevant:
            lines.append("## 📚 相关")
            lines.append("")
            for item, score, reason in relevant:
                lines.extend(self._render_item(item, score, reason))
                lines.append("")

        if general:
            lines.append("## 📌 其他")
            lines.append("")
            for item, score, reason in general:
                lines.extend(self._render_item(item, score, reason))
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("_推送越用越准，多和我聊天我会更懂你。_")

        return "\n".join(lines)

    def _render_item(
        self,
        item: "NewsItem",
        score: float,
        reason: str,
        show_reason: bool = False,
    ) -> list[str]:
        emoji = _SOURCE_EMOJI.get(item.source, "📄")
        src_name = _SOURCE_NAME.get(item.source, item.source)
        age = _age_str(item)
        score_pct = f"{int(score * 100)}%"

        lines = [f"### {emoji} {item.title}（推荐度 {score_pct}）"]
        if show_reason and reason:
            lines.append(f"> {reason}")
            lines.append("")
        lines.append(f"📍 {src_name} · {age}" + (f" · {item.author}" if item.author else ""))
        if item.summary and item.summary != item.title:
            lines.append(f"📝 {item.summary[:120]}")
        if item.url:
            lines.append(f"🔗 [阅读原文]({item.url})")
        return lines

    def build_telegram_html(
        self,
        ranked: list[tuple["NewsItem", float, str]],
        profile: "UserProfile",
    ) -> str:
        """生成 Telegram HTML 格式（用于 bot 推送）。"""
        now = datetime.now(CST)
        label = _report_label()
        weekday = "一二三四五六日"[now.weekday()]
        date_str = now.strftime(f"%Y-%m-%d 周{weekday}")

        if not ranked:
            return f"📰 <b>SJTU {label} · {date_str}</b>\n\n今天没有特别值得关注的新内容。"

        profile_data = profile.load()
        interests = profile_data.get("interests", {})
        top_tags = sorted(interests.items(), key=lambda x: x[1], reverse=True)[:3]
        tags_str = "、".join(f"「{t}」" for t, _ in top_tags) if top_tags else "校园动态"

        lines = [
            f"📰 <b>SJTU {label} · {date_str}</b>",
            "",
            f"💡 为你精选 <b>{len(ranked)} 条</b>（基于 {tags_str}）",
            "",
        ]

        for i, (item, score, reason) in enumerate(ranked, 1):
            emoji = _SOURCE_EMOJI.get(item.source, "📄")
            src_name = _SOURCE_NAME.get(item.source, item.source)
            age = _age_str(item)
            score_pct = f"{int(score * 100)}%"

            lines.append(f"{i}. {emoji} <b>{item.title}</b>（{score_pct}）")
            if reason and score >= 0.8:
                lines.append(f"   <i>{reason}</i>")
            lines.append(f"   📍 {src_name} · {age}")
            if item.url:
                lines.append(f"   🔗 <a href='{item.url}'>阅读原文</a>")
            lines.append("")

        return "\n".join(lines)

    def build_feishu_post(
        self,
        ranked: list[tuple["NewsItem", float, str]],
        profile: "UserProfile",
    ) -> list[list[dict]]:
        """生成飞书 post 格式段落列表，供 ``send_post_message`` 直接使用。

        每段格式::

            [{tag:"text", text:"emoji 标题（推荐度）"},
             {tag:"a", text:"阅读原文", href:url}]
        """
        now = datetime.now(CST)
        label = _report_label()
        weekday = "一二三四五六日"[now.weekday()]
        date_str = now.strftime(f"%Y-%m-%d 周{weekday}")

        paras: list[list[dict]] = []

        # 标题
        paras.append([{"tag": "text", "text": f"📰 SJTU {label} · {date_str}"}])

        if not ranked:
            paras.append([{"tag": "text", "text": "今天没有特别值得关注的新内容，继续加油！"}])
            return paras

        profile_data = profile.load()
        interests = profile_data.get("interests", {})
        top_tags = sorted(interests.items(), key=lambda x: x[1], reverse=True)[:3]
        tags_str = "、".join(f"「{t}」" for t, _ in top_tags) if top_tags else "校园动态"

        paras.append([{"tag": "text", "text": f"💡 为你精选 {len(ranked)} 条（基于 {tags_str}）"}])
        paras.append([{"tag": "text", "text": ""}])

        # 按分数分层
        important = [(i, s, r) for i, s, r in ranked if s >= 0.8]
        relevant  = [(i, s, r) for i, s, r in ranked if 0.6 <= s < 0.8]
        general   = [(i, s, r) for i, s, r in ranked if s < 0.6]

        def _render_group(label: str, group: list) -> None:
            paras.append([{"tag": "text", "text": label}])
            for i, (item, score, reason) in enumerate(group, 1):
                emoji = _SOURCE_EMOJI.get(item.source, "📄")
                src_name = _SOURCE_NAME.get(item.source, item.source)
                age = _age_str(item)
                score_pct = f"{int(score * 100)}%"

                title_el = {"tag": "text", "text": f"{i}. {emoji} {item.title}（{score_pct}）"}
                subtitle_el = {"tag": "text", "text": f"   📍 {src_name} · {age}"}

                if item.url:
                    paras.append([title_el])
                    paras.append([subtitle_el, {"tag": "a", "text": "🔗 阅读原文", "href": item.url}])
                else:
                    paras.append([title_el])
                    paras.append([subtitle_el])

                if reason and score >= 0.8:
                    paras.append([{"tag": "text", "text": f"   💬 {reason}"}])

        if important:
            _render_group("🔥 重要", important)
        if relevant:
            _render_group("📚 相关", relevant)
        if general:
            _render_group("📌 其他", general)

        paras.append([{"tag": "text", "text": ""}])
        paras.append([{"tag": "text", "text": "推送越用越准，多和我聊天我会更懂你。"}])

        return paras
