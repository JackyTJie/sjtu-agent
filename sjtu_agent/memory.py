"""sjtu_agent/memory.py — ChromaDB-backed semantic memory for the agent.

Stores session summaries as embeddings for cross-session semantic retrieval.
The vector DB handles similarity search; the full conversation text lives in
feishu_sessions.json.  This follows the "vector DB for lookup, relational
for full record" pattern — ChromaDB returns IDs, the caller fetches context.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))

# ── Lazy ChromaDB client (initialised on first use) ──────────────────────────

_client = None
_client_lock = threading.Lock()


def _get_client(persist_dir: str):
    """Return or create a PersistentClient (thread-safe, lazy-init)."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        import chromadb
        _client = chromadb.PersistentClient(path=persist_dir)
    return _client


# ── Public API ──────────────────────────────────────────────────────────────

def store_memory(
    user_id: str,
    text: str,
    metadata: dict | None = None,
    persist_dir: str | None = None,
) -> str:
    """Store a text as an embedding in ChromaDB. Returns the memory ID."""
    from sjtu_agent.paths import DATA_DIR
    persist_dir = persist_dir or str(DATA_DIR / "chroma_memory")
    client = _get_client(persist_dir)
    collection = client.get_or_create_collection("agent_memory")

    meta = dict(metadata or {})
    meta.setdefault("user_id", user_id)
    meta.setdefault("timestamp", datetime.now(CST).isoformat())
    memory_id = f"{user_id}:{uuid.uuid4().hex[:8]}"

    collection.add(
        documents=[text],
        metadatas=[meta],
        ids=[memory_id],
    )
    return memory_id


def search_memory(
    user_id: str,
    query: str,
    n: int = 3,
    persist_dir: str | None = None,
) -> list[dict]:
    """Semantically search stored memories for a user. Returns list of {text, metadata, distance}."""
    from sjtu_agent.paths import DATA_DIR
    persist_dir = persist_dir or str(DATA_DIR / "chroma_memory")
    client = _get_client(persist_dir)

    try:
        collection = client.get_collection("agent_memory")
    except Exception:
        return []

    try:
        results = collection.query(
            query_texts=[query],
            n_results=min(n, 10),
            where={"user_id": user_id},
        )
    except Exception:
        # where clause may fail if collection was created without user_id index
        results = collection.query(query_texts=[query], n_results=min(n, 10))

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    out = []
    for i in range(len(results["ids"][0])):
        out.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i] if results.get("documents") else "",
            "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })
    return out


def summarize_session(messages: list[dict]) -> str | None:
    """Ask the LLM to extract key facts from a conversation session.

    Returns a concise summary string, or None if there is nothing worth remembering.
    This function is synchronous — call it from a background thread in the bot.
    """
    user_msgs = [m for m in messages if m.get("role") == "user"]
    if len(user_msgs) < 3:
        return None  # 太短的对话不值得记忆

    # 构建总结 prompt
    sample = []
    for m in user_msgs[-10:]:
        content = m.get("content", "")
        if isinstance(content, str):
            sample.append(f"用户: {content[:200]}")
    if not sample:
        return None
    sample_text = "\n".join(sample)

    prompt = (
        "你是一个学习搭子的记忆助手。请从以下用户对话中提取值得记住的关键信息，"
        "用 1-2 句话总结。关注：课程、考试、作业进展、学习偏好、关注的技术方向。"
        "不要记录闲聊和无关内容。如果没有任何值得记住的，返回 '(none)'。\n\n"
        f"{sample_text}\n\n"
        "关键信息摘要："
    )

    try:
        import agent
        cfg = agent.load_agent_config()
        client = agent._make_client(cfg) if cfg.get("api_key") else None
        model = cfg.get("model", "deepseek-chat")
        if not client:
            return None

        # 直接调用 OpenAI API 做快速摘要
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        text = resp.choices[0].message.content.strip()
        if not text or text.lower() in ("(none)", "none", "无"):
            return None
        return text
    except Exception:
        return None


def build_memory_context(user_id: str, current_msg: str, n: int = 3) -> str:
    """Build a context string for the system prompt from relevant memories."""
    memories = search_memory(user_id, current_msg, n=n)
    if not memories:
        return ""

    lines = ["\n\n## 相关历史记忆"]
    for i, mem in enumerate(memories, 1):
        lines.append(f"{i}. {mem['text']}")
    return "\n".join(lines)
