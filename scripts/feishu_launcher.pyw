"""SJTU Agent Windows 桌面启动器 — 无需命令行，一键管理飞书 Bot + 邮件监控。

双击此文件即可运行（关联 pythonw.exe），不会弹出终端窗口。
"""

from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
BOT_SCRIPT = ROOT / "scripts" / "feishu_bot.py"
EMAIL_SCRIPT = ROOT / "scripts" / "email_watcher.py"

if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW
    _STARTUP = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW,
                                       wShowWindow=subprocess.SW_HIDE)
else:
    _NO_WINDOW = 0
    _STARTUP = None


# ── psmux 工具函数 ──────────────────────────────────────────────────────────

def _run_psmux(*args: str, timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psmux", *args],
        capture_output=True, text=True, timeout=timeout,
        creationflags=_NO_WINDOW, startupinfo=_STARTUP,
    )


def session_running(name: str) -> bool:
    try:
        result = _run_psmux("has-session", "-t", name, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def start_session(name: str, script: Path) -> str:
    if session_running(name):
        return f"{name} 已在运行中"
    try:
        _run_psmux("kill-session", "-t", name, timeout=5)
    except Exception:
        pass
    result = subprocess.run(
        ["psmux", "new", "-s", name, "-d", "--",
         str(VENV_PYTHON), str(script)],
        capture_output=True, text=True, timeout=15,
        creationflags=_NO_WINDOW, startupinfo=_STARTUP,
    )
    if result.returncode == 0:
        return f"{name} 已启动"
    return f"启动失败: {result.stderr.strip() or '未知错误'}"


def stop_session(name: str) -> str:
    if not session_running(name):
        return f"{name} 未在运行"
    try:
        _run_psmux("kill-session", "-t", name, timeout=10)
        return f"{name} 已停止"
    except Exception as e:
        return f"停止失败: {e}"


def _get_icon() -> Path:
    return ROOT / "install" / "sjtu_agent.ico"


# ── 单个服务的按钮+状态组件 ─────────────────────────────────────────────────

class ServiceRow(tk.Frame):
    def __init__(self, parent, name: str, label: str, session: str,
                 script: Path, fg, btn_bg, green, red, accent, log_fn):
        super().__init__(parent, bg=parent["bg"])
        self.name = name
        self.session = session
        self.script = script
        self.green = green
        self.red = red
        self.fg = fg
        self.btn_bg = btn_bg
        self.accent = accent
        self.log = log_fn

        tk.Label(self, text=label, font=("Segoe UI", 12, "bold"),
                 fg=fg, bg=parent["bg"]).pack(side=tk.LEFT, padx=(0, 10))

        self.start_btn = tk.Button(self, text="▶ 启动", font=("Segoe UI", 10),
                                    fg=green, bg=btn_bg, width=6,
                                    command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=3)

        self.stop_btn = tk.Button(self, text="■ 停止", font=("Segoe UI", 10),
                                   fg=red, bg=btn_bg, width=6,
                                   command=self._stop)
        self.stop_btn.pack(side=tk.LEFT, padx=3)

        self.status_label = tk.Label(self, text="○", font=("Segoe UI", 11),
                                     fg=fg, bg=parent["bg"])
        self.status_label.pack(side=tk.LEFT, padx=10)

    def refresh(self):
        running = session_running(self.session)
        self.status_label.config(
            text="● 运行中" if running else "○ 未运行",
            fg=self.green if running else self.fg,
        )

    def _start(self):
        self.start_btn.config(state=tk.DISABLED)
        self.log(f"[{self.name}] 正在启动…")
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        msg = start_session(self.session, self.script)
        self.after(0, lambda: self.log(f"[{self.name}] {msg}"))
        self.after(0, self.refresh)
        self.after(0, lambda: self.start_btn.config(state=tk.NORMAL))

    def _stop(self):
        self.stop_btn.config(state=tk.DISABLED)
        self.log(f"[{self.name}] 正在停止…")
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_stop(self):
        msg = stop_session(self.session)
        self.after(0, lambda: self.log(f"[{self.name}] {msg}"))
        self.after(0, self.refresh)
        self.after(0, lambda: self.stop_btn.config(state=tk.NORMAL))


# ── 主窗口 ──────────────────────────────────────────────────────────────────

class LauncherApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SJTU Agent 启动器")
        self.root.geometry("600x360")
        self.root.resizable(True, True)
        self.root.configure(bg="#1e1e2e")

        icon = _get_icon()
        if icon.exists():
            self.root.iconbitmap(default=str(icon))

        self.fg = "#cdd6f4"
        self.bg = "#1e1e2e"
        self.btn_bg = "#313244"
        self.accent = "#89b4fa"
        self.green = "#a6e3a1"
        self.red = "#f38ba8"

        tk.Label(self.root, text="SJTU Agent 启动器", font=("Segoe UI", 16, "bold"),
                 fg=self.accent, bg=self.bg).pack(pady=(15, 5))
        tk.Label(self.root, text="Windows — 无需命令行，一键管理后台服务",
                 font=("Segoe UI", 9), fg=self.fg, bg=self.bg).pack(pady=(0, 10))

        # 飞书 Bot 行
        self.bot_row = ServiceRow(
            self.root, "feishu-bot", "🪶 飞书 Bot",
            "feishu-bot", BOT_SCRIPT,
            self.fg, self.btn_bg, self.green, self.red, self.accent,
            self._log,
        )
        self.bot_row.pack(pady=5, padx=20, fill=tk.X)

        # 分隔线
        tk.Frame(self.root, height=1, bg="#45475a").pack(fill=tk.X, padx=20, pady=5)

        # 邮件监控行
        self.email_row = ServiceRow(
            self.root, "email-watcher", "📧 邮件监控",
            "email-watcher", EMAIL_SCRIPT,
            self.fg, self.btn_bg, self.green, self.red, self.accent,
            self._log,
        )
        self.email_row.pack(pady=5, padx=20, fill=tk.X)

        # 日志区域
        self.output = scrolledtext.ScrolledText(
            self.root, height=8, font=("Cascadia Code", 9),
            bg="#11111b", fg="#cdd6f4", insertbackground=self.fg,
            relief=tk.FLAT, borderwidth=0,
        )
        self.output.pack(fill=tk.BOTH, expand=True, padx=20, pady=(10, 15))

        self._refresh_all()
        self.root.mainloop()

    def _log(self, msg: str) -> None:
        self.output.insert(tk.END, msg + "\n")
        self.output.see(tk.END)

    def _refresh_all(self) -> None:
        self.bot_row.refresh()
        self.email_row.refresh()


if __name__ == "__main__":
    if sys.platform != "win32":
        messagebox.showerror("平台不支持", "此启动器仅支持 Windows 系统。")
        sys.exit(1)
    LauncherApp()
