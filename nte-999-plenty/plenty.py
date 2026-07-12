import os
import time
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import keyboard
import win32gui
import win32ui
import vgamepad as vg
import math
import ctypes
import cv2
import numpy as np
import gc  # 导入垃圾回收模块
from gamepad_backend import GamepadBackend


def get_resource_path(relative_path):
    """获取动态资源（如图片）的绝对路径，兼容 PyInstaller 打包后的临时目录"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def get_output_path(relative_path):
    """获取【可写输出】文件的路径：始终落在脚本/exe 所在目录，随脚本移动而移动。
    打包成 exe(-F) 时用 exe 目录，而非只读的临时解压目录。"""
    if hasattr(sys, '_MEIPASS'):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


class NTEAutoBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NTE 智能脚本全自动挂机控制台 v1.2 (Plenty)")
        self.root.geometry("560x460")
        self.root.minsize(520, 380)

        # 初始化后端核心
        self.backend = GamepadBackend()
        self.hwnd = None
        self.running = False
        self.loop_thread = None

        # 日志语言（zh / en），由界面单选切换；工作线程只读此属性
        self.lang = "zh"

        # 超时监控维度
        self.step_active_time = time.time()
        self.watchdog_thread = None

        # 预加载所有模板图到内存（避免每帧读盘+解码，降低运行负载）
        self.templates = {}
        for _name in ("fresh.png", "bossname.png", "blood.png", "bag.png", "fire.png", "choose.png", "tele.png", "hit.png"):
            _img = cv2.imread(get_resource_path(_name))
            if _img is not None:
                self.templates[_name] = _img

        self.create_ui()

        # 自动锁定窗口
        self.log(self.t("🔍 正在自动寻找 NTE 目标窗口...",
                        "🔍 Searching for NTE target window..."), "info")
        self.find_target_window()

        # 全局热键监听 (F10 异步切换)
        keyboard.add_hotkey('f10', self.toggle_script_via_hotkey)
        self.log(self.t("💡 脚本已就绪！你可以使用界面按钮，或全局按下 [F10] 键起停挂机。",
                        "💡 Script ready! Use the button, or press [F10] globally to start/stop."), "green")

    def t(self, zh, en):
        """按当前日志语言返回中文或英文文案"""
        return en if self.lang == "en" else zh

    def create_ui(self):
        """创建带实时日志滚动的紧凑界面"""
        # ===== 第一行：主起停按钮 + 目标窗口状态 =====
        ctrl_frame = ttk.LabelFrame(self.root, text=" 脚本控制面板 ", padding=8)
        ctrl_frame.pack(fill="x", padx=8, pady=(6, 3))

        self.btn_toggle = tk.Button(ctrl_frame, text="▶ 启动挂机 (F10)", bg="#2ecc71", fg="white",
                                    font=("Helvetica", 11, "bold"), width=16, command=self.toggle_script)
        self.btn_toggle.pack(side="left", padx=(4, 8))

        self.lbl_win_status = tk.Label(ctrl_frame, text="目标窗口: 未绑定", fg="gray", font=("Helvetica", 9))
        self.lbl_win_status.pack(side="left", padx=4)

        # ===== 第二行：语言切换 + 工具按钮（全部左对齐，避免被挤出视野看不见）=====
        util_frame = ttk.Frame(self.root)
        util_frame.pack(fill="x", padx=10, pady=(0, 4))

        ttk.Label(util_frame, text="日志/Log:").pack(side="left")
        self.lang_var = tk.StringVar(value="zh")
        ttk.Radiobutton(util_frame, text="中", variable=self.lang_var, value="zh",
                        command=self._on_lang_change).pack(side="left")
        ttk.Radiobutton(util_frame, text="EN", variable=self.lang_var, value="en",
                        command=self._on_lang_change).pack(side="left", padx=(0, 12))
        ttk.Button(util_frame, text="🔄 重新绑定窗口", command=self.find_target_window).pack(side="left", padx=3)
        ttk.Button(util_frame, text="🗑️ 清空日志", command=self.clear_log).pack(side="left", padx=3)

        # ===== 实时日志（占满剩余空间）=====
        log_frame = ttk.LabelFrame(self.root, text=" 实时自动化运行日志 (Live Log) ", padding=5)
        log_frame.pack(fill="both", expand=True, padx=8, pady=(3, 6))

        self.log_box = scrolledtext.ScrolledText(log_frame, state="disabled", wrap="word", font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.log_box.pack(fill="both", expand=True)

        # 配置日志颜色高亮标签
        self.log_box.tag_config("info", foreground="#9cdcfe")
        self.log_box.tag_config("step", foreground="#ce9178")
        self.log_box.tag_config("green", foreground="#4ec9b0", font=("Consolas", 10, "bold"))
        self.log_box.tag_config("warn", foreground="#dcdcaa")
        self.log_box.tag_config("error", foreground="#f44336", font=("Consolas", 10, "bold"))

    def _on_lang_change(self):
        """切换日志语言（只影响之后新产生的日志）"""
        self.lang = self.lang_var.get()
        self.log(self.t("🌐 日志语言已切换为：中文", "🌐 Log language switched to: English"), "info")

    def clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def log(self, message, tag="info"):
        timestamp = time.strftime("[%H:%M:%S] ", time.localtime())
        full_msg = f"{timestamp}{message}\n"
        self.root.after(0, self._insert_log, full_msg, tag)

    def _insert_log(self, text, tag):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text, tag)
        self.log_box.config(state="disabled")
        self.log_box.see("end")

    def update_step_checkpoint(self):
        self.step_active_time = time.time()

    def start_watchdog(self):
        def watchdog_loop():
            while self.running:
                time.sleep(1.0)
                if self.running and (time.time() - self.step_active_time > 20.0):
                    self.running = False
                    self.root.after(0, self.trigger_timeout_alert)
                    break
        self.watchdog_thread = threading.Thread(target=watchdog_loop)
        self.watchdog_thread.daemon = True
        self.watchdog_thread.start()

    def trigger_timeout_alert(self):
        self.btn_toggle.config(text="▶ 启动挂机 (F10)", bg="#2ecc71")
        self.log(self.t("🚨 [看门狗] 检测到脚本单步运行超过 20 秒无响应，已强制停机！",
                        "🚨 [Watchdog] A single step ran over 20s with no response; force-stopped!"), "error")
        messagebox.showerror(
            self.t("运行超时警报", "Timeout Alert"),
            self.t("自动化步骤已超过 20 秒无区域刷新，脚本已安全断开！\n请检查游戏是否卡死、掉线或被弹窗阻挡。",
                   "A step exceeded 20s without any refresh; the bot has safely disconnected!\nCheck whether the game froze, disconnected, or is blocked by a popup."))

    def trigger_align_fail_alert(self):
        self.btn_toggle.config(text="▶ 启动挂机 (F10)", bg="#2ecc71")
        messagebox.showerror(
            self.t("对齐失败", "Alignment Failed"),
            self.t("多次尝试仍无法对齐篝火，为避免误传送已停止脚本！\n请检查地图/指针/篝火是否正常，再手动重启。",
                   "Could not align to the campfire after several tries; the bot has stopped to avoid a wrong teleport!\nCheck the map/pointer/campfire, then restart manually."))

    def find_target_window(self):
        self.hwnd = None
        def enum_windows_proc(h, lParam):
            if win32gui.IsWindowVisible(h):
                title = win32gui.GetWindowText(h)
                if "NTE" in title.upper():
                    self.hwnd = h
                    self.lbl_win_status.config(text=f"目标窗口: {title[:20]}...", fg="green")
                    self.log(self.t(f"🎯 成功锁定目标窗口: '{title}' (HWND: {self.hwnd})",
                                    f"🎯 Locked target window: '{title}' (HWND: {self.hwnd})"), "green")
        win32gui.EnumWindows(enum_windows_proc, None)
        if not self.hwnd:
            self.lbl_win_status.config(text="目标窗口: NTE未找到(将使用保底前台)", fg="orange")
            self.log(self.t("⚠️ 未找到含有 'NTE' 的可见窗口，挂机开始时将采用触发瞬间的前台活动窗口作为保底。",
                            "⚠️ No visible window containing 'NTE' found; will fall back to the foreground window at start."), "warn")

    def toggle_script_via_hotkey(self):
        self.root.after(0, self.toggle_script)

    def toggle_script(self):
        if not self.running:
            self.clear_log()
            if not self.hwnd:
                self.hwnd = win32gui.GetForegroundWindow()
                self.log(self.t(f"🚀 未找到NTE，采用当前聚焦的保底窗口 (HWND: {self.hwnd})",
                                f"🚀 NTE not found; using current foreground window as fallback (HWND: {self.hwnd})"))

            self.running = True
            self.btn_toggle.config(text="🛑 停止挂机 (F10)", bg="#e74c3c")
            self.log(self.t("=== 挂机启动 ===",
                            "=== BOT STARTED ==="), "green")

            self.update_step_checkpoint()
            self.start_watchdog()

            self.loop_thread = threading.Thread(target=self.master_loop)
            self.loop_thread.daemon = True
            self.loop_thread.start()
        else:
            self.running = False
            self.btn_toggle.config(text="▶ 启动挂机 (F10)", bg="#2ecc71")
            self.log(self.t("=== 挂机停止 (安全释放键位) ===",
                            "=== BOT STOPPED (keys released) ==="), "error")

    def window_screenshot(self, hwnd, region=None):
        """后台对目标窗口直接截屏（PrintWindow，无视遮挡）"""
        hwndDC = None
        mfcDC = None
        saveDC = None
        saveBitMap = None
        try:
            # 使用客户区尺寸，与 PrintWindow 抓取的客户区严格对齐（避免黑边/偏移）
            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            width = right - left
            height = bottom - top
            if width <= 0 or height <= 0:
                return None

            # 获取窗口DC和内存DC
            hwndDC = win32gui.GetWindowDC(hwnd)
            mfcDC = win32ui.CreateDCFromHandle(hwndDC)
            saveDC = mfcDC.CreateCompatibleDC()

            # 创建位图对象（标准 pywin32 写法）
            saveBitMap = win32ui.CreateBitmap()
            saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
            saveDC.SelectObject(saveBitMap)

            # 特殊API：PrintWindow 可以抓取后台/遮挡窗口的图像数据
            # flag=3 = PW_CLIENTONLY(1) | PW_RENDERFULLCONTENT(2)
            # 对 DirectX/硬件加速的游戏窗口必须带上 2，否则只抓到全黑图，找图永远失败。
            # 注意：必须用 ctypes 调 user32.PrintWindow，因为部分 pywin32 版本的
            # win32gui 没有 PrintWindow 封装（会报 AttributeError）。
            ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

            # 转成 numpy 矩阵供给 OpenCV
            bmpinfo = saveBitMap.GetInfo()
            bmpstr = saveBitMap.GetBitmapBits(True)
            img = np.frombuffer(bmpstr, dtype='uint8')
            img.shape = (bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)

            # 转为标准的BGR三通道（cvtColor 会复制出独立数组，随后即可安全释放GDI）
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            # 如果指定了局部裁剪区域
            if region:
                rx, ry, rw, rh = region
                # 限制不超出边界
                img_bgr = img_bgr[max(0, ry):min(height, ry+rh), max(0, rx):min(width, rx+rw)]

            return img_bgr
        except Exception:
            return None
        finally:
            # 无论成功或异常都释放 GDI 资源，防止句柄泄漏导致长跑卡顿
            if saveBitMap is not None:
                try: win32gui.DeleteObject(saveBitMap.GetHandle())
                except Exception: pass
            if saveDC is not None:
                try: saveDC.DeleteDC()
                except Exception: pass
            if mfcDC is not None:
                try: mfcDC.DeleteDC()
                except Exception: pass
            if hwndDC is not None:
                try: win32gui.ReleaseDC(hwnd, hwndDC)
                except Exception: pass

    def locate_img(self, img_name, confidence=0.8, screen=None):
        """后台搜图：优先使用外部传入的截图，避免同一轮重复截屏（降负载）"""
        img_target = self.templates.get(img_name)
        if img_target is None:
            return False

        # screen 为 None 时才自行截图；否则复用传入的截图
        img_screen = screen if screen is not None else self.window_screenshot(self.hwnd)
        if img_screen is None:
            return False

        try:
            # 截图比模板还小会导致 matchTemplate 抛异常，先行拦截
            if (img_screen.shape[0] < img_target.shape[0] or
                    img_screen.shape[1] < img_target.shape[1]):
                return False
            res = cv2.matchTemplate(img_screen, img_target, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return max_val >= confidence
        except Exception:
            return False

    def _walk_segment_watch(self, x, y, duration):
        """按住摇杆走一段（非阻塞，走满 duration 秒），期间持续截图找 BOSS。
        【关键】即使找到 BOSS 也【不打断走位】，只记录结果，等整条折线走完再进战斗。
        返回本段是否发现过 BOSS。"""
        if duration <= 0 or not self.running:
            return False
        found = False
        self.backend.send_joystick_persistent(self.hwnd, "L", x, y, duration=duration, block=False)
        seg_start = time.time()
        while self.running and (time.time() - seg_start < duration):
            self.update_step_checkpoint()
            _shot = self.window_screenshot(self.hwnd)
            if self.locate_img("bossname.png", screen=_shot) or self.locate_img("blood.png", screen=_shot):
                # 整条折线只播报一次（由 master_loop 在走位前重置 self._boss_announced）
                if not getattr(self, "_boss_announced", False):
                    self.log(self.t("🔥 [警报] 走位途中发现 BOSS（不打断，走完再开打）！",
                                    "🔥 [Alert] BOSS spotted mid-path (won't interrupt; finish path first)!"), "green")
                    self._boss_announced = True
                found = True
            time.sleep(0.05)
        return found

    def _open_map_and_align(self, attempt=0, total=1):
        """打开地图 → L3 出指针 → 往左上小幅推 15 次移开指针 + 按 15 次 R2 放大地图 → 识别离指针
        最近的篝火并闭环对齐（出现 hit.png 即视为已到篝火）。返回 'success' / 'lost' / 'exhausted'。"""
        # [步骤 11] 呼出地图
        self.update_step_checkpoint()
        self.log(self.t(f"==> [步骤 11] 呼出游戏地图...（第 {attempt+1}/{total} 次）",
                        f"==> [Step 11] Open the map... (attempt {attempt+1}/{total})"), "step")
        if not self.running: return "lost"
        self.backend.send_button(self.hwnd, vg.DS4_SPECIAL_BUTTONS.DS4_SPECIAL_BUTTON_TOUCHPAD, is_special=True, duration=0.2)

        # [步骤 12] 等待地图加载
        self.log(self.t("==> [步骤 12] 等待 2 秒地图图层加载...",
                        "==> [Step 12] Waiting 2s for map to load..."), "info")
        for _ in range(2):
            self.update_step_checkpoint()
            time.sleep(1.0)

        # [步骤 13] L3 激活指针，等 1 秒让指针(choose)出现再开始识别
        self.update_step_checkpoint()
        self.log(self.t("==> [步骤 13] 按下 L3 激活指针，等待指针出现后开始对齐篝火...",
                        "==> [Step 13] Press L3 to activate pointer; wait for it, then align to campfire..."), "step")
        if not self.running: return "lost"
        self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_THUMB_LEFT, duration=0.1)
        time.sleep(1.0)

        # [步骤 13a] 仍识别一下篝火(fire.png)，只为确认地图确实已经打开；打不开就交上层退图重试
        img_fire = self.templates.get("fire.png")
        if img_fire is None:
            self.log(self.t("❌ 缺失素材 fire.png，无法确认地图",
                            "❌ Missing fire.png; cannot confirm map"), "error")
            return "lost"
        self.log(self.t("==> [步骤 13a] 识别篝火 fire 确认地图已打开...",
                        "==> [Step 13a] Detect fire to confirm the map is open..."), "step")
        map_ok = False
        _confirm_start = time.time()
        while self.running and (time.time() - _confirm_start < 5.0):
            self.update_step_checkpoint()
            if self.locate_img("fire.png", confidence=0.55):
                map_ok = True
                break
            time.sleep(0.2)
        if not self.running: return "lost"
        if not map_ok:
            self.log(self.t("   ❌ 未识别到篝火，判定地图未打开，交上层退图重试。",
                            "   ❌ Campfire not detected; map likely not open, hand back to retry."), "warn")
            return "lost"
        self.log(self.t("   ✨ 已识别到篝火，确认地图已打开。",
                        "   ✨ Campfire detected; map confirmed open."), "green")

        # [步骤 13b] 指针(choose)常被角色箭头遮挡：往【左上】小幅度推 10 次移开指针，
        # 同时每次按一下 R2 放大地图，方便后续识别对齐。
        PUSH_TIMES = 15          # 往左上小幅推 / 按 R2 的次数
        PUSH_MAG = 0.3           # 小幅度（摇杆量级）；负 x = 往左, 负 y = 往上
        PUSH_DUR = 0.1           # 每次按住时长（秒）
        self.log(self.t(f"==> [步骤 13b] 往左上小幅度推 {PUSH_TIMES} 次移开指针，并放大地图...",
                        f"==> [Step 13b] Nudge up-left {PUSH_TIMES}x to clear the pointer, and zoom in the map..."), "step")
        for _i in range(PUSH_TIMES):
            if not self.running: return "lost"
            self.update_step_checkpoint()
            self.backend.send_joystick_persistent(self.hwnd, "L", -PUSH_MAG, -PUSH_MAG, duration=PUSH_DUR, block=True)
            self.backend.send_trigger(self.hwnd, "R", 255, duration=0.08)  # 同时按 R2 放大地图
            time.sleep(0.05)
        self.backend.stop_joystick(self.hwnd, "L")

        # [步骤 13c] 闭环对齐：识别指针(choose) + 离指针最近的篝火(fire)，逐步逼近直到重合
        img_choose = self.templates.get("choose.png")
        if img_choose is None:
            self.log(self.t("❌ 缺失素材 choose.png，无法对齐指针",
                            "❌ Missing choose.png; cannot align pointer"), "error")
            return "lost"

        # 只扫窗口正中央区域（横 1/4~3/4，纵 1/4~3/4），用"离指针最近"筛掉边缘其它篝火
        region = None
        try:
            _, _, win_w, win_h = win32gui.GetClientRect(self.hwnd)
            region = (win_w // 4, win_h // 4, win_w // 2, win_h // 2)
        except Exception as e:
            self.log(self.t(f"⚠️ 获取窗口坐标失败: {e}，改用全窗口分析。",
                            f"⚠️ Failed to get window rect: {e}; using full window."), "warn")

        self.log(self.t("==> [步骤 13c] 开始识别离指针最近的篝火并闭环对齐...",
                        "==> [Step 13c] Detecting the campfire nearest the pointer and aligning..."), "step")
        lost_count = 0          # 连续找不到指针(choose)的次数
        MAX_LOST = 4            # 连续唤不出指针超过该次数 → 判本次对齐失败，交上层退图重试
        last_distance = 9999.0
        lower_red1, upper_red1 = np.array([0, 30, 50]), np.array([12, 255, 255])
        lower_red2, upper_red2 = np.array([165, 30, 50]), np.array([180, 255, 255])

        for align_retry in range(50):
            if not self.running: return "lost"
            self.update_step_checkpoint()

            # hit.png 出现 = 指针已经移动到篝火上，直接判对齐成功（阈值 0.9，避免误判）
            if self.locate_img("hit.png", confidence=0.9):
                self.log(self.t("   ✨ 检测到 hit，指针已移动到篝火上，对齐成功！",
                                "   ✨ hit detected; pointer is on the campfire, aligned!"), "green")
                return "success"

            img_screen = self.window_screenshot(self.hwnd, region=region)
            if img_screen is None:
                time.sleep(0.1)
                continue
            # 防御：截图区域比模板还小会导致 matchTemplate 抛异常
            if (img_screen.shape[0] < img_fire.shape[0] or img_screen.shape[1] < img_fire.shape[1] or
                    img_screen.shape[0] < img_choose.shape[0] or img_screen.shape[1] < img_choose.shape[1]):
                time.sleep(0.1)
                continue

            res_choose = cv2.matchTemplate(img_screen, img_choose, cv2.TM_CCOEFF_NORMED)
            _, max_val_c, _, max_loc_c = cv2.minMaxLoc(res_choose)

            res_fire = cv2.matchTemplate(img_screen, img_fire, cv2.TM_CCOEFF_NORMED)
            _, max_val_f, _, _ = cv2.minMaxLoc(res_fire)

            h_f, w_f = img_fire.shape[:2]
            loc = np.where(res_fire >= 0.55)
            fires = []
            for pt in zip(*loc[::-1]):
                roi = img_screen[pt[1]:pt[1]+h_f, pt[0]:pt[0]+w_f]
                if roi.size == 0: continue
                hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                mask1 = cv2.inRange(hsv_roi, lower_red1, upper_red1)
                mask2 = cv2.inRange(hsv_roi, lower_red2, upper_red2)
                red_mask = mask1 | mask2
                if cv2.countNonZero(red_mask) < 5:
                    continue
                cx = pt[0] + w_f // 2
                cy = pt[1] + h_f // 2
                if not any(math.sqrt((cx-fx)**2 + (cy-fy)**2) < 10 for fx, fy in fires):
                    fires.append((cx, cy))

            if (max_val_f < 0.56 or len(fires) == 0) and last_distance < 60:
                self.log(self.t("   ✨ [篝火遮挡熔断触发] 判定指针已成功覆盖篝火！",
                                "   ✨ [Occlusion cutoff] Pointer has covered the campfire!"), "green")
                return "success"

            if max_val_c >= 0.70 and fires:
                lost_count = 0  # 指针已找到，重置丢失计数
                current_choose_pos = (max_loc_c[0] + img_choose.shape[1]//2, max_loc_c[1] + img_choose.shape[0]//2)
                # 篝火始终取离指针(choose)最近的那个
                fires.sort(key=lambda p: math.sqrt((p[0] - current_choose_pos[0])**2 + (p[1] - current_choose_pos[1])**2))
                current_fire_pos = fires[0]

                dx_abs = abs(current_fire_pos[0] - current_choose_pos[0])
                dy_abs = abs(current_fire_pos[1] - current_choose_pos[1])
                distance = math.sqrt(dx_abs**2 + dy_abs**2)
                last_distance = distance

                if distance < 15:
                    self.log(self.t("   ✨ 中心点已常规重合！对齐圆满成功！",
                                    "   ✨ Centers aligned! Alignment succeeded!"), "green")
                    return "success"

                duration_x = min(max(dx_abs * 0.008, 0.12), 0.45)
                duration_y = min(max(dy_abs * 0.008, 0.12), 0.45)

                dir_x = 0.28 if current_choose_pos[0] < current_fire_pos[0] else -0.28
                dir_y = 0.28 if current_choose_pos[1] < current_fire_pos[1] else -0.28

                # 合并 X/Y 为单次对角线摇杆输出，避免两线程互相清零导致抖动
                jx = dir_x if dx_abs >= 15 else 0.0
                jy = dir_y if dy_abs >= 15 else 0.0
                if (jx != 0.0 or jy != 0.0) and self.running:
                    dur = max(duration_x if jx != 0.0 else 0.0, duration_y if jy != 0.0 else 0.0)
                    self.backend.send_joystick_persistent(self.hwnd, "L", jx, jy, duration=dur, block=False)

                time.sleep(max(duration_x, duration_y) + 0.08)
            else:
                if last_distance < 60:
                    self.log(self.t("   🎯 触发近距离兜底，开始执行右下微动补正...",
                                    "   🎯 Close-range fallback: micro-adjusting toward bottom-right..."), "warn")
                    if self.running:
                        self.backend.send_joystick_persistent(self.hwnd, "L", 0.0, 0.28, duration=0.1, block=True)
                        time.sleep(0.05)
                    if self.running:
                        self.backend.send_joystick_persistent(self.hwnd, "L", 0.28, 0.0, duration=0.1, block=True)
                        time.sleep(0.1)
                    return "success"

                if max_val_c < 0.70:
                    # 指针(choose)可能被箭头遮住/静止太久消失：按 L3 唤出后再往左上推几下移开箭头，重新识别
                    lost_count += 1
                    if lost_count > MAX_LOST:
                        self.log(self.t(f"   ❌ 连续 {MAX_LOST} 次仍找不到指针，放弃本次对齐（不盲推）。",
                                        f"   ❌ Pointer stayed missing after {MAX_LOST} tries; abandoning (no blind push)."), "error")
                        return "lost"
                    self.log(self.t(f"   🔄 未检测到指针，L3 唤出并往左上移开箭头后再识别（第 {lost_count}/{MAX_LOST} 次）...",
                                    f"   🔄 Pointer missing; re-summon L3 + nudge up-left off the arrow, then re-detect ({lost_count}/{MAX_LOST})..."), "warn")
                    if self.running:
                        self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_THUMB_LEFT, duration=0.1)
                        time.sleep(0.3)
                    # 再往左上推几下，把指针从角色箭头下挪出来
                    for _j in range(5):
                        if not self.running: return "lost"
                        self.update_step_checkpoint()
                        self.backend.send_joystick_persistent(self.hwnd, "L", -PUSH_MAG, -PUSH_MAG, duration=PUSH_DUR, block=True)
                        time.sleep(0.05)
                    self.backend.stop_joystick(self.hwnd, "L")
                    continue

                # 指针在、但中央区域没有篝火：判失败，交上层退地图重试（不乱点）
                self.log(self.t("   ❌ 找到指针但中央区域未发现篝火，放弃本次对齐（不盲推）。",
                                "   ❌ Pointer found but no campfire in the central region; abandoning (no blind push)."), "error")
                return "lost"

        # 50 次微调仍未对齐
        self.log(self.t("   ⚠️ 达到最大对齐微调次数(50次)仍未对齐。",
                        "   ⚠️ Reached max alignment tries (50) without aligning."), "warn")
        return "exhausted"

    # ===== 走位/战斗 固定参数（秒）：以前在面板里调，现改为脚本常量，改这里即可 =====
    T_START_FWD = 0.2      # 起步前进
    T_P_FWD = 3.0          # 走位·前
    T_P_LEFT = 2.5         # 走位·左
    T_P_BACK = 1.5         # 走位·后
    T_P_RIGHT = 1.5        # 走位·右
    T_FACE_LEFT = 0.1      # 面朝左点按
    T_R1_INTERVAL = 1.2    # R1 间隔

    def master_loop(self):
        """核心全局死循环"""
        while self.running:
            try:
                # ----------------------------------------------------
                # [改动1] 开始挂机后往前轻推一下，再启动篝火
                _t_start = self.T_START_FWD
                self.update_step_checkpoint()
                self.log(self.t("==> [步骤 1] 移动到篝火...",
                                "==> [Step 1] Move onto the campfire..."), "step")
                if not self.running: break
                self.backend.send_joystick_persistent(self.hwnd, "L", 0.0, -1.0, duration=_t_start, block=True)
                time.sleep(0.2)

                # ----------------------------------------------------
                self.update_step_checkpoint()
                self.log(self.t("==> [步骤 2] 按 ⭕ 启动篝火...",
                                "==> [Step 2] Press ⭕ to light the campfire..."), "step")
                if not self.running: break
                self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE, duration=0.15)

                # ----------------------------------------------------
                self.update_step_checkpoint()
                self.log(self.t("==> [步骤 3] 检测 fresh 界面出现...",
                                "==> [Step 3] Detecting the fresh UI..."), "info")
                scan_start = time.time()
                fresh_found = False
                while self.running:
                    self.update_step_checkpoint()
                    if self.locate_img("fresh.png"):
                        self.log(self.t("==> fresh 界面已加载！",
                                        "==> fresh UI loaded!"), "green")
                        fresh_found = True
                        break
                    time.sleep(0.2)
                    if time.time() - scan_start > 15:
                        self.log(self.t("⏳ 找图 fresh.png 超时，为防逻辑崩坏，放弃本轮转向兜底重试。",
                                        "⏳ fresh.png scan timed out; abandoning this round and retrying."), "warn")
                        break

                if not fresh_found:
                    continue

                # ----------------------------------------------------
                self.update_step_checkpoint()
                self.log(self.t("==> [步骤 4] 按 ⏹️ 刷新 2 次",
                                "==> [Step 4] Press ⏹️ to refresh 2x"), "step")
                for _ in range(2):
                    if not self.running: break
                    self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_SQUARE, duration=0.15)
                    time.sleep(1.0)

                # ----------------------------------------------------
                self.update_step_checkpoint()
                self.log(self.t("==> [步骤 5] 按 🔼 休整 1 次",
                                "==> [Step 5] Press 🔼 to rest 1x"), "step")
                if not self.running: break
                self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_TRIANGLE, duration=0.15)

                # [改动] 从休整完成这一刻开始计一轮周期时间，用于末尾"满 60 秒才进下一轮"的冷却保护。
                _cycle_start = time.time()

                # ----------------------------------------------------
                self.log(self.t("==> [步骤 6] 等待 3 秒图层加载...",
                                "==> [Step 6] Waiting 3s for layers to load..."), "info")
                for _ in range(3):
                    self.update_step_checkpoint()
                    time.sleep(1.0)

                # ----------------------------------------------------
                # [改动2+改动3] 休整好后走折线：前 → 左 → 后 → 右（各段时长可在面板调整），
                # 最后往左轻点一下让角色面朝左。
                # 【边走边找】整条折线期间持续检测 BOSS，但发现也【不打断】，
                # 必须把整条折线走完，才进入 R1 战斗循环。
                _t_fwd = self.T_P_FWD
                _t_left = self.T_P_LEFT
                _t_back = self.T_P_BACK
                _t_right = self.T_P_RIGHT
                _t_face = self.T_FACE_LEFT
                self.update_step_checkpoint()
                self.log(self.t("==> [步骤 7] 走位并找 BOSS（不打断）",
                                "==> [Step 7] Walk the path while detecting BOSS (no interrupt)"), "step")
                if not self.running: break

                self._boss_announced = False   # 本条折线只播报一次 BOSS 发现
                boss_found = False
                boss_found |= self._walk_segment_watch(0.0, -1.0, _t_fwd)   # 向前
                time.sleep(0.1)
                boss_found |= self._walk_segment_watch(-1.0, 0.0, _t_left)  # 向左
                time.sleep(0.1)
                boss_found |= self._walk_segment_watch(0.0, 1.0, _t_back)   # 向后
                time.sleep(0.1)
                boss_found |= self._walk_segment_watch(1.0, 0.0, _t_right)  # 向右
                time.sleep(0.1)
                # 往左轻点一下让角色面朝左（同样边走边找）
                boss_found |= self._walk_segment_watch(-1.0, 0.0, _t_face)
                time.sleep(0.2)
                # 折线走完，确保摇杆归零后再开打
                self.backend.stop_joystick(self.hwnd, "L")

                if not self.running: break
                if boss_found:
                    self.log(self.t("✅ [步骤 8] 已到挂机点，已发现 BOSS，进入战斗循环。",
                                    "✅ [Step 8] Arrived at the spot; BOSS found, entering battle loop."), "green")
                else:
                    self.log(self.t("⚠️ [步骤 8] 已到挂机点，未发现 BOSS，默认进入战斗状态。",
                                    "⚠️ [Step 8] Arrived at the spot; no BOSS found, defaulting to battle state."), "warn")

                # --- 战斗循环开始 ---
                # [改动3] 战斗循环改为无脑 R1：每隔一段时间按一次 R1（间隔可在面板调整），其余不管。
                # 仍保留 BOSS 消失检测用于判定战斗结束、退出循环。
                # [改动4] 本次 BOSS 多：观察窗口延长到 6 秒，且【观察期间不停火，照常按 R1】。
                _t_r1 = self.T_R1_INTERVAL
                self.log(self.t(f"==> [步骤 9] 进入无脑战斗流（每 {_t_r1} 秒按一次 R1，观察期也不停火）...",
                                f"==> [Step 9] Mindless battle flow (R1 every {_t_r1}s, keep firing while observing)..."), "step")
                boss_missing_start = None

                while self.running:
                    self.update_step_checkpoint()
                    _shot = self.window_screenshot(self.hwnd)
                    boss_visible = self.locate_img("bossname.png", screen=_shot) or self.locate_img("blood.png", screen=_shot)

                    if not boss_visible:
                        if boss_missing_start is None:
                            boss_missing_start = time.time()
                            self.log(self.t("   ⚠️ [观察] 检测不到 BOSS 血条/名字，持续按 R1 观察 10 秒...",
                                            "   ⚠️ [Observe] BOSS HP/name not detected; keep pressing R1, observing 10s..."), "warn")
                        else:
                            elapsed_missing = time.time() - boss_missing_start
                            if elapsed_missing >= 10.0:
                                self.log(self.t("🎉 [确认] BOSS 连续 10 秒未见，判定战斗彻底结束！",
                                                "🎉 [Confirmed] BOSS gone for 10s; battle over!"), "green")
                                break
                    else:
                        # 观察中又重新看到 BOSS → 播报一次，继续战斗
                        if boss_missing_start is not None:
                            self.log(self.t("   ✅ 重新发现 BOSS，继续战斗！",
                                            "   ✅ BOSS re-detected; resuming battle!"), "green")
                        boss_missing_start = None

                    # 无脑 R1：无论是否处于观察期都照常按（本次 BOSS 多，绝不停火）
                    if not self.running: break
                    self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_SHOULDER_RIGHT, duration=0.1)
                    time.sleep(_t_r1)
                # --- 战斗循环结束 ---

                # ----------------------------------------------------
                self.log(self.t("==> [步骤 10] 等待 1 秒拾取战利品...",
                                "==> [Step 10] Waiting 1s to pick up loot..."), "step")
                self.update_step_checkpoint()
                time.sleep(1.0)

                # ===== 步骤 11~15：开地图 → L3出指针 → 对齐篝火 → 按X → 用 tele.png 确认传送 =====
                # 【绝不盲推乱点】：对齐成功后按 1 次 X 选点，再找 tele.png：
                #   有 tele.png → 确实点在篝火上、弹出了传送确认 → 按 X 真正传送；
                #   无 tele.png → 没点到篝火 → 按 ⭕ 退回，重开重找；多次仍不行则中断本轮（不乱按）。
                MAX_MAP_RETRY = 3
                teleported = False
                for map_attempt in range(MAX_MAP_RETRY):
                    if not self.running: break

                    # 1) 开图 + 对齐篝火；失败则按 ⭕ 退图，等 2 秒重试
                    if self._open_map_and_align(map_attempt, MAX_MAP_RETRY) != "success":
                        if not self.running: break
                        self.log(self.t("   ↩️ 对齐失败，按 ⭕ 退出地图，2 秒后重试...",
                                        "   ↩️ Alignment failed; press ⭕ to exit map, retry in 2s..."), "warn")
                        self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE, duration=0.15)
                        for _ in range(2):
                            self.update_step_checkpoint()
                            time.sleep(1.0)
                        continue

                    # 2) 对齐成功：按第 1 次 X 选中传送点
                    self.update_step_checkpoint()
                    self.log(self.t("==> [步骤 14] 按 X 选中传送点...",
                                    "==> [Step 14] Press X to select teleport point..."), "step")
                    if not self.running: break
                    self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_CROSS, duration=0.15)

                    # 3) 识别 tele.png：确认是否真的点到篝火、弹出了传送确认（最多找 3 秒）
                    self.update_step_checkpoint()
                    self.log(self.t("==> [步骤 15] 识别传送确认 tele...",
                                    "==> [Step 15] Detect teleport confirm..."), "step")
                    tele_ok = False
                    _tele_start = time.time()
                    while self.running and (time.time() - _tele_start < 3.0):
                        self.update_step_checkpoint()
                        if self.locate_img("tele.png"):
                            tele_ok = True
                            break
                        time.sleep(0.2)
                    if not self.running: break

                    if tele_ok:
                        # 4a) 出现传送确认 → 按 X 真正传送
                        self.log(self.t("   ✨ 检测到传送确认 (tele)，确认传送！",
                                        "   ✨ Teleport confirm (tele) detected; teleporting!"), "green")
                        self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_CROSS, duration=0.15)
                        teleported = True
                        break

                    # 4b) 没出现 → 没点到篝火，按 ⭕ 退回，2 秒后重开重找（绝不再盲按 X）
                    self.log(self.t("   ❌ 未检测到传送确认 (tele.png)，说明没点到篝火，按 ⭕ 退回重找...",
                                    "   ❌ No teleport confirm (tele.png); we missed the campfire, press ⭕ and retry..."), "warn")
                    self.backend.send_button(self.hwnd, vg.DS4_BUTTONS.DS4_BUTTON_CIRCLE, duration=0.15)
                    for _ in range(2):
                        self.update_step_checkpoint()
                        time.sleep(1.0)

                if not self.running: break

                # 多次仍未能确认传送 → 停止脚本并弹窗提醒（绝不乱按，避免误传送）
                if not teleported:
                    self.running = False
                    self.log(self.t("🚫 多次尝试仍未能确认传送 (tele.png)，为避免误传送已停止脚本！",
                                    "🚫 Could not confirm teleport (tele.png) after retries; bot STOPPED to avoid a wrong teleport!"), "error")
                    self.root.after(0, self.trigger_align_fail_alert)
                    break

                # ----------------------------------------------------
                self.log(self.t("==> [步骤 16] 传送发出，安全等待 3 秒...",
                                "==> [Step 16] Teleport sent; waiting 3s..."), "info")
                for _ in range(3):
                    self.update_step_checkpoint()
                    time.sleep(1.0)

                # 大世界加载超时
                self.log(self.t("==> [步骤 17] 正在检测主界面 UI 标志 (bag) 以确认大世界加载完毕...",
                                "==> [Step 17] Detecting main-UI marker (bag) to confirm the world has loaded..."), "info")
                bag_start_time = time.time()
                while self.running:
                    self.update_step_checkpoint()
                    if self.locate_img("bag.png"):
                        self.log(self.t("✨ [成功识别] 游戏主界面已就绪！",
                                        "✨ [Recognized] Main UI ready!"), "green")
                        break

                    if time.time() - bag_start_time > 18.0:
                        self.running = False
                        self.root.after(0, self.trigger_timeout_alert)
                        break
                    time.sleep(0.3)

                if not self.running: break

                # [改动] 冷却保护：从休整(步骤5)起整轮必须满 60 秒，防刷新冷却没到就开下一轮。
                CYCLE_MIN_SEC = 70.0
                _elapsed = time.time() - _cycle_start
                _remain = CYCLE_MIN_SEC - _elapsed
                if _remain > 0:
                    self.log(self.t(f"⏲️ 本轮自休整起仅用 {_elapsed:.1f} 秒，未满 {CYCLE_MIN_SEC:.0f} 秒，等待剩余 {_remain:.1f} 秒冷却...",
                                    f"⏲️ Only {_elapsed:.1f}s since rest (< {CYCLE_MIN_SEC:.0f}s); waiting {_remain:.1f}s for cooldown..."), "info")
                    while self.running and (time.time() - _cycle_start < CYCLE_MIN_SEC):
                        self.update_step_checkpoint()
                        time.sleep(0.5)
                    if not self.running: break
                else:
                    self.log(self.t(f"⏲️ 本轮自休整起已用 {_elapsed:.1f} 秒，超过 {CYCLE_MIN_SEC:.0f} 秒冷却，直接进入下一轮。",
                                    f"⏲️ {_elapsed:.1f}s since rest (≥ {CYCLE_MIN_SEC:.0f}s); no wait, next loop now."), "info")

                self.log(self.t("⏳ == 顺利通过防卡死校验，准备进入下一轮循环 ==\n",
                                "⏳ == Passed anti-stuck check; entering next loop ==\n"), "green")

            except Exception as e:
                self.log(self.t(f"⚠️ 挂机循环中捕获到未知异常: {e}",
                                f"⚠️ Unknown exception in loop: {e}"), "error")
                time.sleep(1.0)
            finally:
                # 【强效释放缓存】：每轮大循环结束（不管成功还是出错），强制释放 OpenCV 与系统内存
                cv2.destroyAllWindows()
                gc.collect()  # 触发 Python 强制垃圾回收

        self.running = False
        self.root.after(0, lambda: self.btn_toggle.config(text="▶ 启动挂机 (F10)", bg="#2ecc71"))

    def on_closing(self):
        self.running = False
        self.backend.close()
        cv2.destroyAllWindows()
        gc.collect()
        self.root.destroy()


if __name__ == "__main__":
    # DPI 感知：系统缩放非 100% 时，保证 GetClientRect 与 PrintWindow 抓到的像素严格对齐，
    # 否则截图会被缩放/错位导致找图不准。
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()
    app = NTEAutoBotGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

    # 打包命令：
# pyinstaller -F -w --collect-all vgamepad --add-data "fire.png;." --add-data "choose.png;." --add-data "fresh.png;." --add-data "bossname.png;." --add-data "blood.png;." --add-data "bag.png;." --add-data "tele.png;." --add-data "hit.png;." plenty.py
