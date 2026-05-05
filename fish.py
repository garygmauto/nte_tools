import tkinter as tk
from tkinter import messagebox
import threading
import cv2
import numpy as np
import pyautogui
import time
import ctypes
import json
import os
import sys
import keyboard
import random
from PIL import Image, ImageTk

# ================= 硬件级模拟 =================
A_KEY = 0x1E
D_KEY = 0x20
F_KEY = 0x21

def resource_path(relative_path):
    """ 获取资源绝对路径，适配 PyInstaller 打包后的路径 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # 获取当前脚本所在目录
    base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def PressKey(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hexKeyCode, 0x0008, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def ReleaseKey(hexKeyCode):
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hexKeyCode, 0x0008 | 0x0002, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short), ("wParamH", ctypes.c_ushort)]
class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]
class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

# =============================================

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    ctypes.windll.user32.SetProcessDPIAware()

# --- 路径兼容性处理 ---
if getattr(sys, 'frozen', False):
    # 打包后的 EXE 所在的文件夹
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 直接运行 py 所在的文件夹
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "fish_config.json")

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# 自动申请管理员权限
if not is_admin():
    try:
        # 明确指定工作目录为脚本所在目录，防止路径丢失
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), BASE_DIR, 1)
    except:
        pass
    # 稍微等待 0.5 秒再退出，给系统一点反应时间，防止临时文件夹删除报错
    time.sleep(0.5)
    os._exit(0) # 使用 os._exit(0) 强制退出，跳过某些可能触发报错的清理逻辑

class AreaSelector:
    def __init__(self, tip):
        self.root = tk.Toplevel()
        self.root.attributes('-alpha', 0.3, '-fullscreen', True, "-topmost", True)
        self.root.config(cursor="cross")
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bg="grey")
        self.canvas.pack(fill="both", expand=True)
        tk.Label(self.root, text=tip, font=("微软雅黑", 20), fg="white", bg="red").place(relx=0.5, rely=0.1, anchor="center")
        self.selection = None
        
        self.start_x = self.start_y = None
        self.rect = None
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.grab_set()
        self.root.wait_window()

    def on_press(self, e):
        self.start_x, self.start_y = e.x, e.y
        self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=3)

    def on_move(self, e):
        self.canvas.coords(self.rect, self.start_x, self.start_y, e.x, e.y)

    def on_release(self, e):
        x1, x2 = min(self.start_x, e.x), max(self.start_x, e.x)
        y1, y2 = min(self.start_y, e.y), max(self.start_y, e.y)
        if x2 - x1 > 5: self.selection = [x1, y1, x2 - x1, y2 - y1]
        self.root.destroy()

class AutoFishV3:
    def __init__(self, root):
        self.root = root
        self.root.title("钓鱼助手-2.6")
        self.root.geometry("300x650")  # 增加高度以容纳新按钮
        self.root.attributes("-topmost", True)
        
        self.running = False
        self.regs = {'f_zone': None, 'bar': None, 'close': None}
        self.labels = {}
        self.deadzone = 15
        self.count = 0 
        self.hotkey = "未绑定" 
        
        self.setup_ui()
        # 1. 尝试加载
        self.load_config() 
        # 2. 如果加载后文件依然不存在，强制创建一份初始配置
        if not os.path.exists(CONFIG_FILE):
            self.save_config()
            
        self.setup_hotkey()

    def setup_ui(self):
        for key, name in [('f_zone', 'F键/咬钩区'), ('bar', '进度条区域'), ('close', '结算点击区')]:
            f = tk.Frame(self.root); f.pack(pady=5)
            tk.Button(f, text=f"框选 {name}", command=lambda k=key: self.do_select(k), width=20).pack()
            self.labels[key] = tk.Label(f, text="未设置", fg="red")
            self.labels[key].pack()

        # 功能按钮区
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="预览框选区域", command=self.preview_areas, width=22, bg="#607D8B", fg="white").pack(pady=5)
        
        # 新增：查看教程按钮
        tk.Button(btn_frame, text="查看教程", command=self.show_tutorial, width=22, bg="#9C27B0", fg="white").pack(pady=5)
        
        # 新增：设置热键按钮
        self.hotkey_btn = tk.Button(btn_frame, text=f"热键: {self.hotkey}", command=self.record_hotkey, width=22, bg="#2196F3", fg="white")
        self.hotkey_btn.pack(pady=5)

        # 启动按钮
        self.toggle_btn = tk.Button(self.root, text="启动脚本", command=self.toggle, height=2, width=22, bg="#4CAF50", fg="white")
        self.toggle_btn.pack(pady=10)
        
        self.status = tk.Label(self.root, text="状态: 等待启动", font=("微软雅黑", 12))
        self.status.pack()
        self.count_label = tk.Label(self.root, text="运行次数: 0", font=("微软雅黑", 12), fg="blue")
        self.count_label.pack(pady=5)

    def setup_hotkey(self):
        """设置全局热键 - 防崩溃稳健版"""
        if self.hotkey == "未绑定":
            return

        try:
            # 尝试清除，但忽略报错
            try: keyboard.unhook_all_hotkeys()
            except: pass
            
            keyboard.add_hotkey(self.hotkey, lambda: self.root.after(0, self.toggle), suppress=False)
            print(f"成功绑定热键: {self.hotkey}")
        except Exception as e:
            print(f"热键绑定失败: {e}")

    def record_hotkey(self):
        """记录并覆盖保存新的热键"""
        # 立即反馈 UI
        self.hotkey_btn.config(text="请按下新热键...", bg="#FF9800")
        self.root.update_idletasks()

        def _record():
            try:
                # 屏蔽错误
                try: keyboard.unhook_all_hotkeys()
                except: pass
                
                # 捕获下一个按键动作
                new_key = keyboard.read_hotkey(suppress=True)
                if new_key:
                    self.hotkey = new_key
                    self.root.after(0, self.apply_new_hotkey)
            except Exception as e:
                print(f"录制过程出错: {e}")
                self.root.after(0, self.update_hotkey_ui)
        
        threading.Thread(target=_record, daemon=True).start()

    def update_hotkey_ui(self):
        """恢复热键按钮 UI"""
        self.hotkey_btn.config(text=f"热键: {self.hotkey}", bg="#2196F3")
        self.setup_hotkey()

    def apply_new_hotkey(self):
        """应用新热键并持久化保存"""
        self.hotkey_btn.config(text=f"热键: {self.hotkey}", bg="#2196F3")
        self.setup_hotkey() # 重新注册热键
        self.save_config()  # 覆盖保存到 json
        messagebox.showinfo("提示", f"热键已更新为: {self.hotkey}")

    def _create_scrollable_window(self, title, image_path=None, cv_img=None):
        """创建一个带滚动条的通用图片显示窗口"""
        top = tk.Toplevel(self.root)
        top.title(title)
        top.geometry("900x700")
        top.attributes("-topmost", True)
        
        canvas = tk.Canvas(top, bg="grey")
        v_bar = tk.Scrollbar(top, orient="vertical", command=canvas.yview)
        h_bar = tk.Scrollbar(top, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=v_bar.set, xscrollcommand=h_bar.set)
        
        v_bar.pack(side="right", fill="y")
        h_bar.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)
        
        try:
            if image_path:
                photo = ImageTk.PhotoImage(Image.open(image_path))
            elif cv_img is not None:
                # BGR 转 RGB
                rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                photo = ImageTk.PhotoImage(Image.fromarray(rgb_img))
            
            canvas.create_image(0, 0, anchor="nw", image=photo)
            canvas.image = photo 
            canvas.config(scrollregion=(0, 0, photo.width(), photo.height()))
        except Exception as e:
            messagebox.showerror("错误", f"显示图片失败: {e}")
            top.destroy()

    def show_tutorial(self):
        """显示教程图片 - 带滚动条"""
        img_path = resource_path("trail.png")
        if not os.path.exists(img_path):
            messagebox.showerror("错误", f"找不到教程图片: {img_path}")
            return
        self._create_scrollable_window("使用教程", image_path=img_path)

    def preview_areas(self):
        """用醒目红框展示当前所有已保存的框选区域 - 带滚动条"""
        img = pyautogui.screenshot()
        frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        
        found_any = False
        for key, reg in self.regs.items():
            if reg:
                found_any = True
                x, y, w, h = reg
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 4)
                cv2.putText(frame, key, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        if not found_any:
            messagebox.showinfo("提示", "目前没有任何框选区域可展示")
            return
        
        self._create_scrollable_window("框选区域预览", cv_img=frame)

    def load_config(self):
        """加载配置并更新 UI 状态"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    # 读取区域设置
                    for k in self.regs:
                        if k in data and data[k]:
                            self.regs[k] = data[k]
                            self.labels[k].config(text="√ 已读取", fg="green")
                    # 读取热键设置
                    if 'hotkey' in data:
                        self.hotkey = data['hotkey']
                        self.hotkey_btn.config(text=f"热键: {self.hotkey}")
            except Exception as e:
                print(f"读取配置失败: {e}")

    def save_config(self):
        """将当前设置持久化到本地文件"""
        try:
            data = self.regs.copy()
            data['hotkey'] = self.hotkey
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f)
            print("配置已保存到本地。")
        except Exception as e:
            print(f"保存配置失败: {e}")

    def do_select(self, key):
        self.root.withdraw()
        time.sleep(0.2)
        res = AreaSelector(f"框选：{key}").selection
        self.root.deiconify()
        if res:
            self.regs[key] = res
            self.labels[key].config(text="√ 已设置", fg="green")
            self.save_config() # 框选完成后立即自动保存

    def check_color(self, region, color_type):
        """核心识别算法 - 独立分支逻辑"""
        if not region: return None
        try:
            img = pyautogui.screenshot(region=region)
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # --- 1. 咬钩蓝色识别 (F键) ---
            if color_type == 'blue_hook':
                lower, upper = np.array([100, 150, 100]), np.array([130, 255, 255])
                mask = cv2.inRange(hsv, lower, upper)
                M = cv2.moments(mask)
                if M["m00"] > 10: 
                    return int(M["m10"] / M["m00"])
                return None

            # --- 2. 进度条青色识别 (抗干扰版) ---
            elif color_type == 'cyan_bar':
                # 安全平衡阈值：H: 78-98, S: 100-255, V: 110-255
                lower = np.array([78, 100, 110]) 
                upper = np.array([98, 255, 255])
                mask = cv2.inRange(hsv, lower, upper)
                
                pixel_count = np.sum(mask > 0)
                if pixel_count < 30: 
                    return None
                
                M = cv2.moments(mask)
                if M["m00"] > 0:
                    return int(M["m10"] / M["m00"])
                return None

            # --- 3. 黄色指针识别 ---
            elif color_type == 'yellow_p':
                lower, upper = np.array([20, 100, 100]), np.array([35, 255, 255])
                mask = cv2.inRange(hsv, lower, upper)
                M = cv2.moments(mask)
                if M["m00"] > 5: 
                    return int(M["m10"] / M["m00"])
                return None
                    
        except: pass
        return None

    def toggle(self):
        if not self.regs['bar']:
            messagebox.showwarning("提示", "进度条区域必须设置")
            return
            
        self.running = not self.running
        
        if self.running:
            self.toggle_btn.config(text="停止脚本", bg="#F44336")
            self.status.config(text="运行中...")
            threading.Thread(target=self.work, daemon=True).start()
        else:
            self.toggle_btn.config(text="启动脚本", bg="#4CAF50")
            self.status.config(text="已停止")

    def work(self):
        time.sleep(2.0)
        while self.running:
            self.count += 1
            self.count_label.config(text=f"运行次数: {self.count}")

            # 1. 抛竿
            self.status.config(text="状态: 抛竿中...")
            PressKey(F_KEY); time.sleep(0.1); ReleaseKey(F_KEY)
            
            # 2. 等待咬钩
            self.status.config(text="状态: 等待鱼咬钩...")
            hooked = False
            start_wait = time.time()
            last_close_click = 0 # 容错计时器初始化
            
            while self.running and (time.time() - start_wait < 15):
                # 【强化容错】每隔 3 秒在结算区进行一次带随机偏移的点击
                if self.regs['close'] and (time.time() - last_close_click > 3.0):
                    r = self.regs['close']
                    # 加入 ±5 像素的随机偏移，确保点击“鲜活”且有效
                    target_x = r[0] + r[2]//2 + random.randint(-5, 5)
                    target_y = r[1] + r[3]//2 + random.randint(-5, 5)
                    pyautogui.click(target_x, target_y)
                    last_close_click = time.time()

                if self.check_color(self.regs['f_zone'], 'blue_hook') is not None:
                    PressKey(F_KEY); time.sleep(0.1); ReleaseKey(F_KEY)
                    hooked = True
                    break
                time.sleep(0.05)
            
            if not hooked: continue
            
            # 3. 遛鱼环节
            time.sleep(0.5)
            self.status.config(text="状态: 遛鱼中！")
            while self.running:
                y_pos = self.check_color(self.regs['bar'], 'yellow_p')
                c_pos = self.check_color(self.regs['bar'], 'cyan_bar')
                
                if y_pos is not None and c_pos is not None:
                    diff = y_pos - c_pos
                    if diff > self.deadzone:
                        ReleaseKey(D_KEY); PressKey(A_KEY)
                    elif diff < -self.deadzone:
                        ReleaseKey(A_KEY); PressKey(D_KEY)
                    else:
                        ReleaseKey(A_KEY); ReleaseKey(D_KEY)
                else:
                    ReleaseKey(A_KEY); ReleaseKey(D_KEY)
                    break
                time.sleep(0.01)
            
            # 4. 结算
            self.status.config(text="状态: 自动结算")
            if self.regs['close']:
                time.sleep(2.5)
                r = self.regs['close']
                # 结算区正式点击也加入随机偏移
                pyautogui.click(r[0] + r[2]//2 + random.randint(-5, 5), r[1] + r[3]//2 + random.randint(-5, 5))
            
            time.sleep(2.0)

if __name__ == "__main__":
    root = tk.Tk(); app = AutoFishV3(root); root.mainloop()
