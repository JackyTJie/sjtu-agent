"""sjtu_agent/homework_agent.py — Canvas 作业自动获取、分析与回传。

核心流程：
  1. 拉取 DDL → 过滤 Canvas + N 天内到期
  2. 下载作业文件到 ASSIGNMENTS_DIR / 课程 / 作业 /
  3. 读取各类文件（PDF/DOCX/HTML/MD/TXT）
  4. 调 LLM 生成：摘要 + 题目分析 + 参考答案
  5. 结果通过飞书推送回用户
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from sjtu_agent.paths import ASSIGNMENTS_DIR

import agent


def _get_feishu_config() -> dict | None:
    """读取飞书配置用于推送。"""
    from sjtu_agent.paths import CONFIG_PATH
    if not CONFIG_PATH.exists():
        return None
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if cfg.get("feishu_app_id") and cfg.get("feishu_open_id"):
            return cfg
    except Exception:
        pass
    return None


def _read_file(file_path: Path) -> str:
    """读取单个文件，返回文本内容。根据扩展名选择解析方式。"""
    ext = file_path.suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            text = ""
            for page in reader.pages[:10]:  # 最多读 10 页
                t = page.extract_text()
                if t:
                    text += t + "\n"
            return text.strip() or "[PDF 内容为空]"

        elif ext in (".docx", ".doc"):
            from docx import Document
            doc = Document(str(file_path))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paras) or "[DOCX 内容为空]"

        elif ext in (".html", ".htm"):
            from html.parser import HTMLParser
            class _Stripper(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                def handle_data(self, d):
                    self.text.append(d)
            s = _Stripper()
            s.feed(file_path.read_text(encoding="utf-8", errors="replace"))
            return "".join(s.text).strip() or "[HTML 内容为空]"

        elif ext in (".md", ".txt", ".tex", ".py", ".json", ".yaml", ".yml"):
            return file_path.read_text(encoding="utf-8", errors="replace").strip()

        else:
            return f"[不支持的文件格式: {ext}]"
    except Exception as e:
        return f"[读取失败: {e}]"


def _latex_to_unicode(text: str) -> str:
    """简单 LaTeX → Unicode 转换。"""
    replacements = {
        r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
        r"\epsilon": "ε", r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ",
        r"\pi": "π", r"\sigma": "σ", r"\phi": "φ", r"\omega": "ω",
        r"\times": "×", r"\div": "÷", r"\pm": "±", r"\cdot": "·",
        r"\sum": "∑", r"\prod": "∏", r"\int": "∫", r"\infty": "∞",
        r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\approx": "≈",
        r"\sqrt": "√", r"\frac": "/", r"\partial": "∂", r"\nabla": "∇",
        r"\rightarrow": "→", r"\Rightarrow": "⇒", r"\leftarrow": "←",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def read_assignment_content(assignment_dir: Path) -> str:
    """读取一个作业目录下所有文件，返回合并文本。"""
    if not assignment_dir.exists():
        return f"[目录不存在: {assignment_dir}]"
    parts = []
    for f in sorted(assignment_dir.iterdir()):
        if f.is_file() and not f.name.startswith("."):
            content = _read_file(f)
            if content:
                parts.append(f"[{f.name}]\n{content}")
    return "\n\n".join(parts) if parts else "[无可读文件]"


def analyze_homework(course: str, assignment_name: str, content: str,
                     llm_client=None, model: str = "") -> str:
    """将作业内容发给 LLM 分析并返回结果。"""
    if llm_client is None:
        agent_cfg = agent.load_agent_config()
        if not agent_cfg.get("api_key"):
            return "[LLM 未配置，无法分析]"
        llm_client = agent._make_client(agent_cfg)
        model = agent_cfg.get("model", "deepseek-chat")

    content = _latex_to_unicode(content)
    prompt = f"""你是一位学习助手，请分析以下作业内容并给出回答。

课程：{course}
作业名称：{assignment_name}

作业内容：
{content[:8000]}  # 截断过长内容

请按以下格式输出：
**摘要**：用 1-2 句话概括这份作业的要求
**题目分析**：列出每道题的要点和考察的知识点
**参考答案**：给出解题思路或具体答案（如为编程题给出代码）
**注意事项**：提醒易错点或提交注意

如题目无法完全确定，请标注"根据已有信息推断"。
"""

    try:
        if agent._is_anthropic_model(model):
            resp = llm_client.messages.create(
                model=model, max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text or "[空响应]"
        else:
            resp = llm_client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            text = resp.choices[0].message.content or ""
            think_re = re.compile(r"<think>.*?</think>", re.DOTALL)
            return think_re.sub("", text).strip() or "[空响应]"
    except Exception as e:
        return f"[分析失败: {e}]"


def _fetch_pending() -> list[dict]:
    """获取所有未提交的 Canvas 作业。"""
    import ddl_checker as dc
    cfg = dc.load_config()
    ddls = dc.fetch_canvas(cfg)
    pending = [d for d in ddls if not d.get("submitted")]
    print(f"[homework] Canvas 共 {len(ddls)} 个作业，{len(pending)} 个未提交")
    return pending


def _filter_by_due(pending: list[dict], due_within_days: int) -> list[dict]:
    """按截止天数过滤。due_within_days=0 表示不限制。"""
    if due_within_days <= 0:
        return pending
    import ddl_checker as dc
    from datetime import timedelta
    now_time = dc.NOW
    window = timedelta(days=due_within_days)
    filtered = []
    for d in pending:
        due = d.get("due")
        if due and hasattr(due, 'timestamp'):
            remaining = due - now_time
            if remaining <= window and remaining.total_seconds() > 0:
                filtered.append(d)
    return filtered


def _download_and_analyze_one(d: dict, idx: int) -> str:
    """下载并分析单个作业。"""
    course = d["course"]
    aname = d["name"]
    due_str = d["due"].strftime("%m月%d日 %H:%M") if hasattr(d["due"], 'strftime') else str(d["due"])
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    days_left = (d["due"] - datetime.now(CST)).days if d.get("due") else "?"
    remaining = f"{days_left} 天" if isinstance(days_left, int) else "?"

    safe_course = re.sub(r'[\\/*?:"<>|]', '_', course)
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', aname)
    hw_dir = ASSIGNMENTS_DIR / safe_course / safe_name

    # 下载
    try:
        import ddl_checker as dc
        cfg = dc.load_config()
        dc.download_assignments(
            cfg,  # 必需的第一个参数
            course_filter=course, assignment_filter=aname,
            output_dir=str(ASSIGNMENTS_DIR), due_within_days=3650,  # 不限天数
        )
    except Exception as e:
        print(f"[homework] 下载失败 {course}/{aname}: {e}")

    content = read_assignment_content(hw_dir)
    if "[无可读文件]" in content:
        return (
            f"**[{idx}] {course} — {aname}**\n"
            f"  截止：{due_str}（{remaining} 天）\n"
            f"  {content}"
        )

    print(f"[homework] 分析: {course} - {aname}")
    analysis = analyze_homework(course, aname, content)
    return (
        f"**[{idx}] {course} — {aname}**\n"
        f"  截止：{due_str}（{remaining} 天）\n\n"
        f"{analysis}"
    )


def _format_list(pending: list[dict]) -> str:
    """格式化作业列表。"""
    if not pending:
        return "[homework] 暂无未提交的 Canvas 作业"
    lines = [f"共 {len(pending)} 个未提交 Canvas 作业："]
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    for i, d in enumerate(pending):
        course = d["course"]
        aname = d["name"]
        due_str = d["due"].strftime("%m/%d") if hasattr(d["due"], 'strftime') else str(d["due"])
        days = (d["due"] - datetime.now(CST)).days if d.get("due") else "?"
        lines.append(f"  [{i}] {course} — {aname}（{due_str}，{days} 天）")
    lines.append("\n/hw do <序号> 下载分析")
    return "\n".join(lines)


def run_homework_check(due_within_days: int = 0, specific_idx: int | None = None,
                       list_only: bool = False) -> str:
    """主入口：列出或分析 Canvas 作业。

    Args:
        due_within_days: 过滤 N 天内到期（0=不限）
        specific_idx: 分析指定序号（0-based）
        list_only: 仅列出，不下载分析
    """
    pending = _fetch_pending()
    if due_within_days > 0:
        pending = _filter_by_due(pending, due_within_days)
        print(f"[homework] 过滤后 {len(pending)} 个 {due_within_days} 天内到期")

    if not pending:
        label = f"{due_within_days} 天内" if due_within_days > 0 else ""
        return f"[homework] 暂无{label}未提交的 Canvas 作业"

    # 仅列出
    if list_only:
        return _format_list(pending)

    # 分析指定作业
    if specific_idx is not None:
        if 0 <= specific_idx < len(pending):
            return _download_and_analyze_one(pending[specific_idx], specific_idx)
        return f"[homework] 无效序号：{specific_idx}，共 {len(pending)} 个（0~{len(pending)-1}）"

    # 默认：列出
    return _format_list(pending)


def run_homework_check_and_push(due_within_days: int = 3,
                                 specific_idx: int | None = None) -> None:
    """运行作业检查并通过飞书推送结果。"""
    result = run_homework_check(due_within_days, specific_idx)
    cfg = _get_feishu_config()
    if not cfg:
        print("[homework] 飞书未配置，仅打印：\n" + result)
        return

    import requests
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": cfg["feishu_app_id"], "app_secret": cfg["feishu_app_secret"]},
            timeout=10,
        )
        if r.status_code != 200 or r.json().get("code") != 0:
            print(f"[homework] 飞书 token 获取失败")
            return
        token = r.json()["tenant_access_token"]

        chunks = [result[i:i + 3800] for i in range(0, len(result), 3800)]
        for chunk in chunks:
            resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                params={"receive_id_type": "open_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": cfg["feishu_open_id"],
                    "msg_type": "text",
                    "content": json.dumps({"text": chunk}, ensure_ascii=False),
                },
                timeout=15,
            )
            if resp.status_code != 200 or resp.json().get("code") != 0:
                print(f"[homework] 推送失败: {resp.text[:100]}")
                return
        print("[homework] 飞书推送完成")
    except Exception as e:
        print(f"[homework] 推送异常: {e}")
