from __future__ import annotations

import os
import socket
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import messagebox

import uvicorn


APP_TITLE = "Boss 循环计时器"
APPDATA_DIR = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "BossLoopTimer"
DB_PATH = APPDATA_DIR / "data" / "boss_timer.db"


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(url: str, timeout: float = 15.0) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with opener.open(url, timeout=1.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"本地服务启动失败：{last_error!r}")


class ServerThread(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True)
        self.port = port
        self.server: uvicorn.Server | None = None

    def run(self) -> None:
        os.environ.setdefault("BOSS_TIMER_DB_PATH", str(DB_PATH))
        from app.main import app

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        self.server.run()

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True


class DesktopApp:
    def __init__(self) -> None:
        APPDATA_DIR.mkdir(parents=True, exist_ok=True)
        self.port = reserve_port()
        self.url = f"http://127.0.0.1:{self.port}/"
        self.server = ServerThread(self.port)
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("520x240")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.configure(bg="#12161f")
        self._build_ui()

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, bg="#12161f", padx=20, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text=APP_TITLE,
            font=("Microsoft YaHei UI", 18, "bold"),
            fg="#f4f7fb",
            bg="#12161f",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            frame,
            text="单机版：数据只保存在当前 Windows 电脑本机。",
            font=("Microsoft YaHei UI", 10),
            fg="#9aa4b4",
            bg="#12161f",
            anchor="w",
            pady=8,
        ).pack(fill="x")

        self.status_var = tk.StringVar(value="正在启动本地服务...")
        tk.Label(
            frame,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 11),
            fg="#f4f7fb",
            bg="#12161f",
            anchor="w",
            pady=8,
        ).pack(fill="x")

        tk.Label(
            frame,
            text=f"数据文件：{DB_PATH}",
            font=("Consolas", 9),
            fg="#9aa4b4",
            bg="#12161f",
            justify="left",
            anchor="w",
            wraplength=470,
        ).pack(fill="x", pady=(4, 12))

        button_row = tk.Frame(frame, bg="#12161f")
        button_row.pack(fill="x", pady=(8, 0))

        self.open_button = tk.Button(
            button_row,
            text="打开计时器",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="#d94a3a",
            fg="#ffffff",
            activebackground="#c63c2d",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=8,
            state="disabled",
            command=self.open_browser,
        )
        self.open_button.pack(side="left")

        tk.Button(
            button_row,
            text="退出软件",
            font=("Microsoft YaHei UI", 10),
            bg="#252c39",
            fg="#f4f7fb",
            activebackground="#30384a",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=8,
            command=self.close,
        ).pack(side="right")

    def start(self) -> None:
        self.server.start()
        self.root.after(100, self._finish_startup)
        self.root.mainloop()

    def _finish_startup(self) -> None:
        try:
            wait_for_server(self.url)
        except Exception as exc:  # noqa: BLE001
            self.status_var.set("启动失败，请查看错误提示。")
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.status_var.set(f"软件已运行，本地地址：{self.url}")
        self.open_button.config(state="normal")
        self.open_browser()

    def open_browser(self) -> None:
        webbrowser.open(self.url, new=1)

    def close(self) -> None:
        self.status_var.set("正在关闭...")
        self.server.stop()
        self.root.after(250, self.root.destroy)


if __name__ == "__main__":
    DesktopApp().start()
