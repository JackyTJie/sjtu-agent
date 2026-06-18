#!/usr/bin/env python3
"""SJTU Canteen Crowd Checker — fetch real-time canteen crowding from
campuslife.sjtu.edu.cn and recommend where to eat.

Public API — no authentication required.

Usage::

    from sjtu_agent.data.canteen_crowd import CanteenCrowdChecker

    checker = CanteenCrowdChecker()
    result = checker.get_all_crowd()
    recs = checker.recommend(campus="闵行", max_crowd=30)
"""

from __future__ import annotations

import datetime
import sys
from typing import Any

import requests

import ddl_checker as dc  # for dc.CST (UTC+8)

CST = dc.CST  # canonical alias for convenience within this module

API_BASE = "https://campuslife.sjtu.edu.cn"
MAIN_URL = f"{API_BASE}/api/jczs/main"
SUB_URL = f"{API_BASE}/api/jczs/sub"

# Real names for canteen IDs (from the API data)
CANTEEN_NAMES: dict[int, str] = {
    100: "第一餐饮大楼",
    200: "第二餐饮大楼",
    300: "第三餐饮大楼",
    400: "第四餐饮大楼",
    500: "第五餐饮大楼",
    600: "第六餐饮大楼",
    700: "第七餐饮大楼",
    800: "哈乐餐厅",
    1000: "徐汇第二食堂",
    1200: "张江食堂",
}

# Campus mapping
CANTEEN_CAMPUS: dict[int, str] = {
    100: "闵行", 200: "闵行", 300: "闵行", 400: "闵行",
    500: "闵行", 600: "闵行", 700: "闵行", 800: "闵行",
    1000: "徐汇", 1200: "张江",
}

# Crowd level thresholds
CROWD_LEVELS = [
    (0,    "空闲"),
    (15,   "适中"),
    (30,   "较挤"),
    (50,   "拥挤"),
    (float("inf"), "爆满"),
]


def _crowd_label(rate: float) -> str:
    for threshold, label in CROWD_LEVELS:
        if rate <= threshold:
            return label
    return "未知"


def _parse_time(t: str) -> datetime.datetime | None:
    try: return datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
    except Exception: return None


class CanteenCrowdChecker:
    """Fetch and analyze SJTU canteen crowd levels."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 SJTU-Skills/1.0",
            "Accept": "application/json",
        })

    # ── Raw API ────────────────────────────────────────────────────────────

    def get_all_canteens(self) -> dict:
        """Fetch all canteens from /api/jczs/main."""
        try:
            r = self.session.get(MAIN_URL, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                return {"ok": False, "error": data.get("message", "API error")}
            return {"ok": True, "canteens": data["data"]}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}

    def get_canteen_detail(self, canteen_id: int) -> dict:
        """Fetch sub-area crowd data for a specific canteen."""
        try:
            r = self.session.get(SUB_URL, params={"id": canteen_id}, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                return {"ok": False, "error": data.get("message", "API error")}
            return {"ok": True, "detail": data["data"]}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}

    # ── Aggregated ─────────────────────────────────────────────────────────

    def get_all_crowd(self, campus: str = "") -> dict:
        """Fetch all canteens with their current crowd levels.

        Args:
            campus: Filter by campus — '闵行', '徐汇', '张江'. Empty = all.

        Returns:
            {ok, canteens: [{id, name, campus, is_open, schedule_desc,
             subs: [{name, current_rate, current_label, trend, last_updated}]}]}
        """
        main = self.get_all_canteens()
        if not main["ok"]:
            return main

        results = []
        now = datetime.datetime.now(CST)

        for c in main["canteens"]:
            cid = c["id"]
            cname = CANTEEN_NAMES.get(cid, c["name"])
            ccampus = CANTEEN_CAMPUS.get(cid, c["campus"])

            if campus and ccampus != campus:
                continue

            detail = self.get_canteen_detail(cid)
            sub_data = detail.get("detail", {}) if detail["ok"] else {}

            subs = []
            for sub in sub_data.get("subs", []):
                rates = sub.get("curRates", [])
                if not rates:
                    subs.append({
                        "name": sub.get("name", "?"),
                        "is_open": bool(sub.get("isOpen")),
                        "close_desc": sub.get("closeDesc") or "",
                        "current_rate": None,
                        "current_label": "无数据",
                        "trend": "—",
                        "last_updated": None,
                    })
                    continue

                # Latest rate is the current crowd level
                latest = rates[-1]
                current_rate = latest["rate"]
                current_time = _parse_time(latest["time"])

                # Trend: compare with 10 min ago
                trend = "—"
                if len(rates) >= 10:
                    ago = rates[-10]["rate"]
                    if current_rate > ago + 3:
                        trend = "上升"
                    elif current_rate < ago - 3:
                        trend = "下降"
                    else:
                        trend = "平稳"

                subs.append({
                    "name": sub.get("name", "?"),
                    "is_open": bool(sub.get("isOpen")),
                    "close_desc": sub.get("closeDesc") or "",
                    "current_rate": round(current_rate, 1),
                    "current_label": _crowd_label(current_rate),
                    "trend": trend,
                    "last_updated": latest["time"],
                })

            # Overall canteen crowd = average of sub-area rates
            sub_rates = [s["current_rate"] for s in subs if s["current_rate"] is not None]
            overall_rate = round(sum(sub_rates) / len(sub_rates), 1) if sub_rates else None

            # Determine dining status
            is_operational = bool(c["isOpen"])         # Not on holiday/reno
            schedule_status = sub_data.get("scheduleStatus", 0)
            schedule_desc = sub_data.get("scheduleDesc", "")
            is_dining = schedule_status != 0 and "Non-Dining" not in schedule_desc

            results.append({
                "id": cid,
                "name": cname,
                "campus": ccampus,
                "is_operational": is_operational,         # 是否长期营业（非假期/装修）
                "is_dining": is_dining,                   # 当前是否在供餐时段
                "schedule_desc": schedule_desc,
                "overall_rate": overall_rate,
                "overall_label": _crowd_label(overall_rate) if overall_rate is not None else "非就餐时间",
                "subs": subs,
                "note": c.get("note") or "",
                "api_name": c["name"],
            })

        # Sort by crowd (least crowded first)
        results.sort(key=lambda x: x["overall_rate"] if x["overall_rate"] is not None else 999)

        return {
            "ok": True,
            "campus": campus or "全部",
            "total": len(results),
            "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "canteens": results,
        }

    # ── Recommendations ────────────────────────────────────────────────────

    def recommend(
        self,
        campus: str = "",
        max_crowd: float = 30.0,
        include_closed: bool = False,
        top_n: int = 5,
    ) -> dict:
        """Get personalized canteen recommendations.

        Args:
            campus: '闵行', '徐汇', '张江'. Empty = all campuses.
            max_crowd: Max overall crowd rate (0-100). Higher = more tolerant.
            include_closed: Include closed canteens in results.
            top_n: Max number of recommendations.

        Returns:
            {ok, recommendations: [...], summary}
        """
        result = self.get_all_crowd(campus=campus)
        if not result["ok"]:
            return result

        canteens = result["canteens"]

        # Filter: exclude canteens on holiday/renovation (not operational)
        if not include_closed:
            canteens = [c for c in canteens if c["is_operational"]]

        # Separate into tiers
        best = [c for c in canteens
                if c["overall_rate"] is not None and c["overall_rate"] <= max_crowd]
        crowded = [c for c in canteens
                   if c["overall_rate"] is not None and c["overall_rate"] > max_crowd]
        no_data = [c for c in canteens if c["overall_rate"] is None]

        # Best first, then crowded, then no-data
        ordered = best[:top_n] + crowded[:top_n] + no_data[:top_n]

        return {
            "ok": True,
            "campus": campus or "全部校区",
            "max_crowd_threshold": max_crowd,
            "total_canteens": len(canteens),
            "within_threshold": len(best),
            "over_threshold": len(crowded),
            "no_data": len(no_data),
            "recommendations": ordered[:top_n],
            "all_canteens": canteens,  # Full list for the agent to use
            "tip": _generate_tip(best, crowded, no_data, result),
        }


def _generate_tip(best: list, crowded: list, no_data: list, result: dict) -> str:
    campus = result.get("campus", "")
    now_desc = result.get("fetched_at", "")

    if not best and not crowded and not no_data:
        return f"当前{campus}没有查到食堂，请检查校区名称。"

    # Check if any canteen is currently serving
    any_dining = any(c.get("is_dining") for c in result.get("all_canteens", []))
    if not any_dining:
        return f"当前非供餐时段（Non-Dining Hours）。以下为上一餐段末的拥挤度数据，供参考。数据时间: {now_desc}"

    if no_data and not best and not crowded:
        return f"当前{campus}所有食堂暂无拥挤度数据。"

    if best:
        names = ", ".join(c["name"] for c in best[:3])
        return f"推荐 {names}，当前拥挤度较低。数据时间: {now_desc}"

    if crowded:
        names = ", ".join(c["name"] for c in crowded[:3])
        return f"当前{campus}食堂普遍较拥挤。相对可选: {names}。数据时间: {now_desc}"

    return "请查看详细数据自行判断。"


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="SJTU Canteen Crowd Checker — 食堂拥挤度查询")
    p.add_argument("action", nargs="?", default="recommend",
                   choices=["recommend", "all", "detail", "list"],
                   help="recommend=推荐(all) all=全部食堂 detail=单个 detail list=食堂列表")
    p.add_argument("--campus", default="", help="校区: 闵行/徐汇/张江 (默认全部)")
    p.add_argument("--max-crowd", type=float, default=30.0,
                   help="最大容忍拥挤度 0-100 (默认 30)")
    p.add_argument("--id", type=int, default=0, help="食堂 ID (detail 模式)")
    p.add_argument("--all", action="store_true", help="显示全部食堂包括关闭的")
    args = p.parse_args()

    checker = CanteenCrowdChecker()

    if args.action == "list":
        result = checker.get_all_canteens()
        if result["ok"]:
            for c in result["canteens"]:
                name = CANTEEN_NAMES.get(c["id"], c["name"])
                campus_name = CANTEEN_CAMPUS.get(c["id"], c["campus"])
                status = " 假期关闭" if not c["isOpen"] else " 运营中"
                print(f"  [{c['id']:>4}] {name:<16} {campus_name:<6} {status}")
            print(f"\n共 {len(result['canteens'])} 个食堂")

    elif args.action == "detail":
        if not args.id:
            print("请指定 --id <食堂ID>")
            sys.exit(1)
        detail = checker.get_canteen_detail(args.id)
        if detail["ok"]:
            d = detail["detail"]
            print(f"就餐时段: {d.get('scheduleDesc', '?')}")
            for sub in d.get("subs", []):
                print(f"\n  {sub.get('name', '?')}")
                print(f"  开放: {'是' if sub.get('isOpen') else '否'}")
                if sub.get("closeDesc"):
                    print(f"  关闭原因: {sub['closeDesc']}")
                rates = sub.get("curRates", [])
                if rates:
                    latest = rates[-1]
                    print(f"  当前拥挤度: {latest['rate']:.1f}% {_crowd_label(latest['rate'])}")
                    print(f"  更新时间: {latest['time']}")
                    if len(rates) >= 10:
                        print(f"  10分钟前: {rates[-10]['rate']:.1f}%")

    elif args.action == "all":
        result = checker.get_all_crowd(campus=args.campus)
        if result["ok"]:
            print(f"数据时间: {result['fetched_at']}")
            print(f"校区: {result['campus']} | 共 {result['total']} 个食堂\n")
            for c in result["canteens"]:
                if not c["is_operational"]:
                    status = ""
                elif c["is_dining"]:
                    status = " [运营]"
                else:
                    status = ""
                print(f"  [{c['id']:>4}] {status} {c['name']:<16} {c['campus']:<6} "
                      f"| {c['overall_label']} ({c['overall_rate']}%) | {c['schedule_desc']}")
                for s in c["subs"]:
                    if s["current_rate"] is not None:
                        print(f"         {s['name']:<20} {s['current_label']} "
                              f"({s['current_rate']:.1f}%) {s['trend']}")

    else:  # recommend
        result = checker.recommend(
            campus=args.campus,
            max_crowd=args.max_crowd,
            include_closed=args.all,
        )
        if result["ok"]:
            print(f"数据时间: {result.get('fetched_at', '?')}")
            print(f"校区: {result['campus']}")
            print(f"拥挤度阈值: {result['max_crowd_threshold']}%")
            print(f"阈值内: {result['within_threshold']} | 较拥挤: {result['over_threshold']} "
                  f"| 无数据: {result['no_data']}\n")

            for c in result["recommendations"]:
                if not c["is_operational"]:
                    status = ""
                elif c["is_dining"]:
                    status = " [运营]"
                else:
                    status = ""
                print(f"  {status} {c['name']} ({c['campus']}) — {c['overall_label']}")
                for s in c["subs"]:
                    if s["current_rate"] is not None:
                        print(f"     {s['name']}: {s['current_rate']:.1f}% {s['current_label']} {s['trend']}")
                print()

            tip = result.get("tip", "")
            if tip:
                print(f"{tip}")
