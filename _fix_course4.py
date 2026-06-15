path = r'sjtu_agent\agent\tools\_core.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

new_code = '''
def tool_setup_course_community(username: str = "", password: str = "") -> dict:
    """Import course.sjtu.plus session from browser cookies.
    The new site (2026-06) uses browser-based jAccount SSO — just read
    the existing session from Chrome/Edge."""
    import json as _json
    import requests as _rq
    from sjtu_agent.paths import CONFIG_PATH as _CFG

    # Try importing from browser first
    course_cookies = {}
    source = ""
    try:
        import browser_cookie3
        for browser_name, loader in [
            ("Chrome", lambda: browser_cookie3.chrome(domain_name="course.sjtu.plus")),
            ("Edge",   lambda: browser_cookie3.edge(domain_name="course.sjtu.plus")),
            ("Firefox", lambda: browser_cookie3.firefox(domain_name="course.sjtu.plus")),
        ]:
            try:
                cj = loader()
                for c in cj:
                    course_cookies[c.name] = c.value
                if course_cookies:
                    source = browser_name
                    break
            except Exception:
                continue
    except ImportError:
        pass

    # If browser import failed, try Playwright jAccount SSO
    if not course_cookies:
        cfg = {}
        if _CFG.exists():
            try:
                cfg = _json.loads(_CFG.read_text(encoding="utf-8"))
            except Exception:
                pass
        jaccount_cookies = cfg.get("jaccount_cookies", {})
        if jaccount_cookies:
            try:
                from playwright.sync_api import sync_playwright
                import time as _time
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    ctx = browser.new_context()
                    ctx.add_cookies([
                        {"name": k, "value": v, "domain": "jaccount.sjtu.edu.cn", "path": "/"}
                        for k, v in jaccount_cookies.items()
                    ])
                    page = ctx.new_page()
                    page.goto("https://course.sjtu.plus/", wait_until="domcontentloaded", timeout=30_000)
                    _time.sleep(3)
                    # Try clicking any visible login element
                    for sel in ["text=使用 jAccount 登录", "text=jAccount 登录",
                                "text=jAccount", "button:has-text('登录')", "a:has-text('登录')"]:
                        btn = page.locator(sel)
                        if btn.count() > 0:
                            btn.first.click()
                            _time.sleep(5)
                            try:
                                page.wait_for_load_state("networkidle", timeout=20_000)
                            except Exception:
                                pass
                            break
                    _time.sleep(3)
                    for c in ctx.cookies():
                        domain = c.get("domain", "")
                        if "course.sjtu.plus" in domain:
                            course_cookies[c["name"]] = c["value"]
                    browser.close()
                    if course_cookies:
                        source = "Playwright SSO"
            except Exception:
                pass

    if not course_cookies:
        return {
            "error": "未能获取选课社区 cookie",
            "next_action": (
                "请用 Chrome 或 Edge 浏览器访问 https://course.sjtu.plus 并登录"
                "（用 jAccount），然后回来告诉我「已登录」，我就能从浏览器读取 cookie。"
            ),
        }

    # Verify cookies work
    try:
        r = _rq.get("https://course.sjtu.plus/api/auth/me",
                    cookies=course_cookies,
                    headers={"Accept": "application/json"},
                    timeout=10)
        if r.status_code != 200 or not r.json().get("username"):
            return {
                "error": "cookie 无效，请在浏览器中重新登录 course.sjtu.plus",
                "next_action": "访问 https://course.sjtu.plus 登录后告诉我「已登录」。"
            }
    except Exception:
        pass

    cfg = {}
    if _CFG.exists():
        try:
            cfg = _json.loads(_CFG.read_text(encoding="utf-8"))
        except Exception:
            pass
    cfg["course_sjtu_cookies"] = course_cookies
    _CFG.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "message": f"选课社区登录成功（从 {source} 读取了 {len(course_cookies)} 个 cookie，已验证 /api/auth/me）",
    }


_COURSE_PLUS_BASE = "https://course.sjtu.plus"


def _course_plus_request(path: str, params: dict | None = None, max_retry: int = 2):
    """Call course.sjtu.plus API (v2). Uses stored cookies; auto-refreshes on 401."""
    import json as _json
    import time as _time
    import requests as _rq
    from sjtu_agent.paths import CONFIG_PATH as _CFG

    cookies = {}
    try:
        cfg = _json.loads(_CFG.read_text(encoding="utf-8"))
        if cfg.get("course_sjtu_cookies"):
            cookies = cfg["course_sjtu_cookies"]
    except Exception:
        pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": _COURSE_PLUS_BASE + "/",
    }

    url = _COURSE_PLUS_BASE + path
    last_err = ""
    for attempt in range(max_retry):
        try:
            r = _rq.get(url, params=params or {}, headers=headers, cookies=cookies,
                        timeout=15, allow_redirects=True)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict) and data.get("error"):
                    if "unauthorized" in str(data["error"]).lower():
                        return None, "选课社区需要登录，请说「配置选课社区」重新登录"
                    return None, data.get("error", "未知错误")
                return data, None
            if r.status_code == 404:
                return None, "未找到（404）"
            last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
            _time.sleep(1 + attempt)
    return None, f"选课社区请求失败：{last_err}"


def tool_search_courses(query: str, page_size: int = 8) -> dict:
    """Search courses on course.sjtu.plus. Auto-retries with login on 401."""
    if not query.strip():
        return {"error": "请提供搜索关键词"}
    data, err = _course_plus_request("/api/course", {
        "search": query.strip(), "page_size": min(max(1, page_size), 20), "page": 1,
    })
    if err:
        if "需要登录" in err or "401" in err:
            login_result = tool_setup_course_community()
            if login_result.get("ok"):
                data, err = _course_plus_request("/api/course", {
                    "search": query.strip(), "page_size": min(max(1, page_size), 20), "page": 1,
                }, max_retry=1)
        if err:
            return {"error": err}

    if not data or not isinstance(data, dict):
        return {"error": "选课社区返回了意外的数据格式"}
    items = data.get("items", [])
    if not items:
        return {"message": f"选课社区没有找到与「{query}」相关的课程"}
    results = []
    for item in items[:page_size]:
        teacher = (item.get("main_teacher") or {})
        rating = item.get("rating") or {}
        results.append({
            "id": item.get("id"), "code": item.get("code", ""), "name": item.get("name", ""),
            "credit": item.get("credit", 0), "department": item.get("department", ""),
            "teacher": teacher.get("name", ""), "avg_rating": rating.get("avg", 0),
            "review_count": rating.get("count", 0),
            "url": f"{_COURSE_PLUS_BASE}/course/{item.get('id')}",
        })
    return {"total": data.get("total"), "returned": len(results), "courses": results}


def tool_get_course_detail(course_id: int, max_reviews: int = 10) -> dict:
    """Get course detail and reviews from course.sjtu.plus."""
    detail, err = _course_plus_request(f"/api/course/{course_id}")
    if err:
        return {"error": err}
    if not detail or not isinstance(detail, dict):
        return {"error": "选课社区返回了意外的数据格式"}
    teacher = (detail.get("main_teacher") or {})
    rating = detail.get("rating") or {}
    result = {
        "id": detail.get("id"), "code": detail.get("code", ""), "name": detail.get("name", ""),
        "credit": detail.get("credit", 0), "department": detail.get("department", ""),
        "teacher": teacher.get("name", ""), "teacher_title": teacher.get("title", ""),
        "avg_rating": rating.get("avg", 0), "review_count": rating.get("count", 0),
        "url": f"{_COURSE_PLUS_BASE}/course/{course_id}",
    }
    review_data, _ = _course_plus_request(f"/api/course/{course_id}/review", {
        "order_by": "updated_at", "page_size": min(max(1, max_reviews), 20), "page": 1,
    })
    if review_data and isinstance(review_data, dict):
        reviews = []
        for r in (review_data.get("items") or [])[:max_reviews]:
            reviews.append({
                "rating": r.get("rating", 0), "content": (r.get("content") or "")[:500],
                "semester": r.get("semester", ""), "created_at": r.get("created_at", ""),
            })
        result["reviews"] = reviews
        result["review_total"] = review_data.get("total", len(reviews))
    return result

'''

start = text.find('\ndef tool_setup_course_community(')
end = text.find('\ndef tool_save_credentials(')
text = text[:start] + new_code + text[end:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print('Done')
