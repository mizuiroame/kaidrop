"""The message log, like FileZilla's: what KaiDrop did and what the server said, with the time."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk

MAX_LINES = 2000
INFO, GOOD, ERROR = "info", "good", "error"


class LogView(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.text = tk.Text(self, height=7, wrap="word", state="disabled", relief="flat",
                            font=("Consolas", 9), background="#fbfbfb")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.tag_configure("time", foreground="#888")
        self.text.tag_configure(GOOD, foreground="#1e7d32")
        self.text.tag_configure(ERROR, foreground="#c0392b")

    def add(self, message: str, kind: str = INFO) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", datetime.now().strftime("%H:%M:%S  "), "time")
        self.text.insert("end", message.strip() + "\n", kind)
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > MAX_LINES:
            self.text.delete("1.0", f"{lines - MAX_LINES}.0")
        self.text.configure(state="disabled")
        self.text.see("end")
