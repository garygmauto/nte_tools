import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os
import ctypes
import time

# 导入自定义模块
from window_manager import WindowManager
from controls import GameControls
from vision import GameVision
from logic import FishingLogic
from config_data import FISH_CONFIG  # <--- 改动：直接导入 Python 字典

class FishingBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NTE_autofish v1.2")
        self.root.geometry("360x550")
        self.root.attributes("-topmost", True)
        
        # --- 改动：不再需要 self.config_path 和 self.load_config() ---
        self.running = False
        self.wm = WindowManager()
        self.setup_ui()

    def setup_ui(self):
        frame = tk.LabelFrame(self.root, text="设置", padx=10, pady=10)
        frame.pack(fill="x", padx=10, pady=5)
        
        self.combo = ttk.Combobox(frame, state="readonly")
        self.combo.pack(fill="x", pady=5)
        tk.Button(frame, text="刷新窗口", command=self.refresh).pack()

        self.status_var = tk.StringVar(value="状态: 停止")
        tk.Label(self.root, textvariable=self.status_var).pack(pady=5)
        
        self.btn_run = tk.Button(self.root, text="启动脚本", bg="green", fg="white", 
                                 width=20, height=2, command=self.toggle)
        self.btn_run.pack(pady=10)

        self.log_box = tk.Text(self.root, height=15, font=("Consolas", 9))
        self.log_box.pack(fill="both", padx=10, pady=5)

    def log(self, text):
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {text}\n")
        self.log_box.see("end")

    def refresh(self):
        self.windows = self.wm.list_windows()
        self.combo['values'] = list(self.windows.keys())
        if self.windows: self.combo.current(0)

    def toggle(self):
        if not self.running:
            if not self.combo.get(): return
            self.running = True
            self.btn_run.config(text="停止脚本", bg="red")
            self.status_var.set("状态: 运行中")
            threading.Thread(target=self.start_logic, daemon=True).start()
        else:
            self.running = False
            self.btn_run.config(text="启动脚本", bg="green")
            self.status_var.set("状态: 停止")

    def start_logic(self):
        hwnd_str = self.combo.get()
        hwnd = self.windows[hwnd_str]
        # --- 改动：传入 FISH_CONFIG 代替 self.config ---
        worker = FishingLogic(hwnd, self, FISH_CONFIG, GameVision, GameControls)
        worker.run()

if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1) 
    except:
        ctypes.windll.user32.SetProcessDPIAware()
    
    root = tk.Tk()
    app = FishingBotApp(root)
    root.mainloop()