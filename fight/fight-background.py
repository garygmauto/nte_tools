import sys
import os
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext
import cv2
import numpy as np
import win32gui
import win32con
#import pyautogui
import win32ui

# 全局配置：图片匹配相似度阈值
THRESHOLD = 0.8  

# 动态引入虚拟手柄库
try:
    import vgamepad as vg
except ImportError:
    print("错误：未检测到 vgamepad 库，请运行: pip install vgamepad")
    sys.exit(1)


class GameControls:
    def __init__(self, hwnd):
        self.hwnd = hwnd

    def press_key(self, vk, duration=0.05):
        if not self.hwnd:
            return
        import ctypes
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        lparam_down = 1 | (scan_code << 16)
        lparam_up = 1 | (scan_code << 16) | (1 << 30) | (1 << 31)
        win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk, lparam_down)
        time.sleep(duration)
        win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, vk, lparam_up)


class GameBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("挂机工具 v4.0")
        
        win_w = 600
        win_h = 550
        
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        
        start_x = max(0, pt.x - (win_w // 2))
        start_y = max(0, pt.y - (win_h // 2))
        self.root.geometry(f"{win_w}x{win_h}+{start_x}+{start_y}")
        

        if getattr(sys, 'frozen', False):
            # 打包后的路径
            self.base_path = sys._MEIPASS
        else:
            # 正常运行时的路径
            self.base_path = os.path.dirname(os.path.abspath(__file__))
        
        self.hwnd = None
        self.window_dict = {}
        self.is_running = False
        self.loop_thread = None
        self.controls = None
        self.out_detected = False
        self.gamepad = None 
        self.log_text = None

        self.create_widgets()
        self.auto_init_window_selection()
        self.start_hotkey_thread()

    def create_widgets(self):
        hwnd_frame = ttk.LabelFrame(self.root, text=" 1. 绑定游戏窗口 ", padding=10)
        hwnd_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(hwnd_frame, text="目标窗口:").pack(side="left", padx=5)
        self.window_combo = ttk.Combobox(hwnd_frame, width=40, state="readonly")
        self.window_combo.pack(side="left", padx=5)
        
        ttk.Button(hwnd_frame, text="🔄 刷新列表", command=self.refresh_window_list).pack(side="left", padx=5)
        self.status_label = ttk.Label(hwnd_frame, text="未绑定", foreground="red")
        self.status_label.pack(side="left", padx=5)

        control_frame = ttk.LabelFrame(self.root, text=" 2. 挂机控制 ", padding=10)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        self.start_btn = ttk.Button(control_frame, text="▶ 启动挂机 (F10)", command=self.start_script)
        self.start_btn.pack(side="left", padx=20, expand=True, fill="x")
        
        self.stop_btn = ttk.Button(control_frame, text="■ 停止挂机 (F10)", command=self.stop_script, state="disabled")
        self.stop_btn.pack(side="left", padx=20, expand=True, fill="x")

        log_frame = ttk.LabelFrame(self.root, text=" 3. 运行日志 ", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=18, bg="#1e1e1e", fg="#d4d4d4")
        self.log_text.pack(fill="both", expand=True)
        
        self.log_text.tag_config("info", foreground="#4ec9b0")
        self.log_text.tag_config("warn", foreground="#ce9178")
        self.log_text.tag_config("error", foreground="#f44336")
        self.log_text.tag_config("success", foreground="#60cd18")

    def log(self, message, level="info"):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        full_msg = f"[{timestamp}] {message}\n"
        def append():
            if self.log_text:
                self.log_text.insert(tk.END, full_msg, level)
                self.log_text.see(tk.END)
        self.root.after(0, append)

    def auto_init_window_selection(self):
        self.refresh_window_list(silent=True)
        sorted_keys = sorted(list(self.window_dict.keys()))
        default_selection = ""
        for key in sorted_keys:
            if "NTE" in key:
                default_selection = key
                break
                
        if default_selection:
            self.window_combo.set(default_selection)
            self.hwnd = self.window_dict[default_selection]
            self.status_label.config(text="已预选", foreground="orange")
            self.log(f"自动选中 NTE 窗口: {default_selection}\nAuto-selected NTE window: {default_selection}", "success")
        else:
            self.hwnd = None
            self.window_combo.set("")
            self.status_label.config(text="未绑定", foreground="red")
            self.log("未发现含 NTE 窗口，请手动选择。\nNo NTE window found. Please select manually.", "warn")

    def refresh_window_list(self, silent=False):
        self.window_dict.clear()
        def enum_windows_proc(hwnd, lParam):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    display_name = f"{title} (HWND: {hwnd})"
                    self.window_dict[display_name] = hwnd
            return True
        win32gui.EnumWindows(enum_windows_proc, None)
        
        sorted_keys = sorted(list(self.window_dict.keys()))
        self.window_combo.config(values=sorted_keys)
        
        if not silent:
            default_selection = ""
            for key in sorted_keys:
                if "NTE" in key:
                    default_selection = key
                    break
            if default_selection:
                self.window_combo.set(default_selection)
                self.hwnd = self.window_dict[default_selection]
                self.status_label.config(text="已预选", foreground="orange")
                self.log(f"已重连目标窗口: {default_selection}\nReconnected to target window: {default_selection}", "success")
            else:
                self.hwnd = None
                self.window_combo.set("")
                self.status_label.config(text="未绑定", foreground="red")
                self.log("未检测到带 'NTE' 窗口，请手动选择。\nNo window with 'NTE' detected. Please select manually.")

    def toggle_script_via_hotkey(self):
        if not self.is_running:
            self.root.after(0, self.start_script)
        else:
            self.root.after(0, self.stop_script)

    def start_hotkey_thread(self):
        def hotkey_worker():
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            HOTKEY_ID = 99
            VK_F10 = 0x79
            if not user32.RegisterHotKey(None, HOTKEY_ID, 0, VK_F10):
                return
            msg = wintypes.MSG()
            while True:
                if user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                    if msg.message == win32con.WM_HOTKEY and msg.wParam == HOTKEY_ID:
                        self.toggle_script_via_hotkey()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
        threading.Thread(target=hotkey_worker, daemon=True).start()

    def find_image_relative_pos(self, template_name):
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            return None
        template_path = os.path.join(self.base_path, template_name)
        if not os.path.exists(template_path): return None
        
        rect = win32gui.GetClientRect(self.hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        if w <= 0 or h <= 0: return None

        hdc = win32gui.GetWindowDC(self.hwnd)
        m_dc = win32ui.CreateDCFromHandle(hdc)
        s_dc = m_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(m_dc, w, h)
        s_dc.SelectObject(bmp)
        ctypes.windll.user32.PrintWindow(self.hwnd, s_dc.GetSafeHdc(), 3)
        
        signedIntsArray = bmp.GetBitmapBits(True)
        img_np = np.frombuffer(signedIntsArray, dtype='uint8')
        img_np.shape = (h, w, 4)
        screen_img = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
        
        win32gui.DeleteObject(bmp.GetHandle())
        s_dc.DeleteDC()
        m_dc.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, hdc)
        
        template = cv2.imdecode(np.fromfile(template_path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if template is None: return None
        res = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return True if max_val >= THRESHOLD else None

    def press_gamepad_btn_once(self, button_enum, keep_time=0.03):
        if self.gamepad:
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_ACTIVATE, 1, 0)
                self.gamepad.press_button(button=button_enum)
                self.gamepad.update()
                time.sleep(keep_time)
                self.gamepad.release_button(button=button_enum)
                self.gamepad.update()
                time.sleep(0.001)
            except Exception:
                pass

    def trigger_rt_axis_once(self, keep_time=0.03):
        if self.gamepad:
            try:
                win32gui.PostMessage(self.hwnd, win32con.WM_ACTIVATE, 1, 0)
                self.gamepad.right_trigger(value=255)
                self.gamepad.update()
                time.sleep(keep_time)
                self.gamepad.right_trigger(value=0)
                self.gamepad.update()
                time.sleep(0.02)
            except Exception:
                pass

    def async_out_checker(self):
        while self.is_running and not self.out_detected:
            if self.find_image_relative_pos("out.png"):
                self.log("检测到 out.png -> 发送手柄 B 键确认退出\nDetected out.png -> Sent gamepad B to exit", "success")
                self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                self.out_detected = True
                break
            time.sleep(0.1)

    def run_workflow(self):
        while self.is_running:
            try:
                time.sleep(1.0)
                if not self.is_running: break

                self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
                time.sleep(0.8)
                self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP)
                time.sleep(0.8)                
                self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
                time.sleep(0.8)


                # --- map.png 阶段 ---
                while self.is_running:
                    if self.find_image_relative_pos("map.png"):
                        self.log("识别到 map.png -> 执行开菜单序列\nDetected map.png -> Executing menu sequence")
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_START)
                        time.sleep(0.8) 
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT)
                        time.sleep(0.8)
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
                        time.sleep(2.0)
                        break
                    time.sleep(0.5)

                if not self.is_running: break

                # --- 1.png 阶段 ---
                while self.is_running:
                    if self.find_image_relative_pos("1.png"):
                        self.log("识别到 1.png -> 发送手柄 Y 键确认进入\nDetected 1.png -> Sent gamepad Y to enter", "success")
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
                        time.sleep(1.5) 
                        break
                    time.sleep(1.5)
                
                if not self.is_running: break

                # --- 2.png 阶段 ---
                while self.is_running:
                    if self.find_image_relative_pos("2.png") and self.find_image_relative_pos("2.1.png"):
                        self.log("2.png 与 2.1.png 同时锁定 -> 发送手柄 Y 键确认进入\n2.png and 2.1.png locked -> Sent gamepad Y to enter", "success")
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y)
                        time.sleep(1.5)
                        break
                    else:
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN)
                        time.sleep(1.0) 

                while self.is_running:
                    if not self.find_image_relative_pos("2.png"):
                        break
                    time.sleep(0.5)

                # --- 3.png 阶段 ---
                while self.is_running:
                    if self.find_image_relative_pos("3.png"):
                        self.log("识别到 3.png 确认框 -> 发送双击 Y 键进战\nDetected 3.png dialog -> Sent double Y to enter battle", "success")
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y, keep_time=0.05)
                        time.sleep(0.2)
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y, keep_time=0.05)
                        break 
                    time.sleep(0.5)

                # --- 4. 连招阶段 ---
                self.log("进入战斗 -> 开启攻击连招...\nEntered battle -> Starting combo sequence...")
                self.out_detected = False
                threading.Thread(target=self.async_out_checker, daemon=True).start()

                while self.is_running:
                    if self.out_detected: 
                        raise InterruptedError()

                    # 1秒50次普攻
                    for i in range(30):
                        if not self.is_running or self.out_detected: break
                        self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_X, keep_time=0.003)

                    # 释放特殊键
                    if not self.is_running or self.out_detected: break
                    self.trigger_rt_axis_once(keep_time=0.015)

                    if not self.is_running or self.out_detected: break
                    self.press_gamepad_btn_once(vg.XUSB_BUTTON.XUSB_GAMEPAD_Y, keep_time=0.015)

            except InterruptedError:
                self.log("结算完成，重置挂机大循环\nSettlement finished, resetting loop", "warn")
                time.sleep(3.0)
                continue
            except Exception:
                time.sleep(1.0)
    
    def start_script(self):
        selected_name = self.window_combo.get()
        hwnd = self.window_dict.get(selected_name)
        if not hwnd:
            self.log("启动失败：未选择有效窗口\nStart failed: No valid window selected", "error")
            return
            
        self.hwnd = hwnd
        self.controls = GameControls(self.hwnd)
        
        if not self.gamepad:
            try:
                self.gamepad = vg.VX360Gamepad()
            except Exception:
                self.log("驱动错误：虚拟手柄加载失败\nDriver error: Failed to load vgamepad", "error")
                return

        self.is_running = True
        self.start_btn.config(state="disabled")
        self.window_combo.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_label.config(text="挂机中", foreground="green")
        self.log("脚本已启动\nScript started", "success")
        
        self.loop_thread = threading.Thread(target=self.run_workflow, daemon=True)
        self.loop_thread.start()

    def stop_script(self):
        self.is_running = False
        self.out_detected = True 
        self.start_btn.config(state="normal")
        self.window_combo.config(state="readonly")
        self.stop_btn.config(state="disabled")
        self.status_label.config(text="已停止", foreground="red")
        
        if self.gamepad:
            try:
                self.gamepad.reset()
                self.gamepad.update()
            except Exception:
                pass
        self.log("脚本已停止\nScript stopped", "warn")


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    root = tk.Tk()
    app = GameBotApp(root)
    root.mainloop()