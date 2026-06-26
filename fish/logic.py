import time
from tkinter import messagebox

class FishingLogic:
    def __init__(self, hwnd, app, config, vision_class, controls_class):
        self.hwnd = hwnd
        self.app = app
        self.config = config
        self.vis = vision_class(hwnd, config)
        self.ctrl = controls_class(hwnd)
        self.fish_count = 1 
        self.last_state_time = time.time() # 状态追踪计时器

    def run(self):
        self.app.log("助手启动成功，防卡死监控中...")
        self.ctrl.fake_activate()

        while self.app.running:
            img = self.vis.get_image()
            if img is None:
                time.sleep(0.1)
                continue

            # --- 状态 A: 判定抛竿 ---
            if self.vis.match_by_key(img, "cast_fishing"):
                self.last_state_time = time.time() # 看到关键图标，重置计时
                self.app.log(f"--- 第 {self.fish_count} 次钓鱼 ---")
                self.app.log("已抛钩")
                self.ctrl.press(0x46) # 按 F
                
                # --- 状态 B: 进入等待上钩循环 ---
                while self.app.running:
                    time.sleep(0.05)
                    img_h = self.vis.get_image()
                    if img_h is None: continue
                    
                    if self.vis.match_by_key(img_h, "fish_hooked"):
                        self.app.log("上钩了！")
                        self.last_state_time = time.time()
                        time.sleep(1.0) # 响应优化：等1秒开始
                        self.ctrl.press(0x46) 
                        time.sleep(1.0) # 等待UI弹出
                        
                        self.app.log("遛鱼中")
                        self.reeling_loop()
                        self.fish_count += 1 # 增加计数
                        break 
                    
                    # 等待鱼上钩时的超时检查
                    if time.time() - self.last_state_time > 10.0:
                        self.emergency_reset()
                        break
            
            # 主循环超时检查：如果场景既没显示抛竿也没显示鱼钩超过10秒
            if time.time() - self.last_state_time > 10.0:
                self.emergency_reset()

            time.sleep(0.4)

    def reeling_loop(self):
        fail_count = 0
        while self.app.running:
            img = self.vis.get_image()
            if img is None: continue
            
            bar_mid = self.vis.find_x_center(img, 'bar')
            slider_pos = self.vis.find_x_center(img, 'slider')

            # --- 核心判定：双重检测 + 3次容错退出 ---
            # 如果判定不到进度条，或者进度条与滑杆同时消失
            if bar_mid is None or (bar_mid is None and slider_pos is None):
                fail_count += 1
                # 连续 3 次识别不到 UI 则判定遛鱼结束
                if fail_count >= 3:
                    break
            else:
                fail_count = 0 # 识别成功，重置计数
                self.last_state_time = time.time() 
                
                # 只有明确识别到滑杆位置才执行按键逻辑
                if slider_pos:
                    if slider_pos < bar_mid - 10:
                        self.ctrl.set_key_state(0x41, False); self.ctrl.set_key_state(0x44, True)
                    elif slider_pos > bar_mid + 10:
                        self.ctrl.set_key_state(0x44, False); self.ctrl.set_key_state(0x41, True)
                    else:
                        self.ctrl.set_key_state(0x41, False); self.ctrl.set_key_state(0x44, False)
                else:
                    # 识别到条但没识别到滑杆，先松开按键防止误按
                    self.ctrl.set_key_state(0x41, False)
                    self.ctrl.set_key_state(0x44, False)
            
            time.sleep(0.04)

        # 退出循环后，确保按键状态清空
        self.ctrl.set_key_state(0x41, False)
        self.ctrl.set_key_state(0x44, False)
        self.app.log("遛鱼结束，准备结算")
        self.settle_result()

    def emergency_reset(self):
        """核心重置逻辑：探测当前所处阶段"""
        self.app.log("!!! 检测到状态长时间无变化，开始扫描画面阶段 !!!")
        img = self.vis.get_image()
        if img is None: return

        # 1. 检查是否在结算界面
        if self.vis.match_by_key(img, "success_text"):
            self.app.log("自检结果：处于结算界面，执行清理...")
            self.settle_result()
            self.last_state_time = time.time()
        
        # 2. 检查是否正在遛鱼
        elif self.vis.find_x_center(img, 'bar') is not None:
            self.app.log("自检结果：进度条尚在，重新接管遛鱼...")
            self.reeling_loop()
            self.last_state_time = time.time()

        # 3. 检查是否处于抛竿待机
        elif self.vis.match_by_key(img, "cast_fishing"):
            self.app.log("自检结果：正常待机中。")
            self.last_state_time = time.time()
        
        # 4. 彻底无法识别：弹窗提示并暂停
        else:
            self.app.log("自检结果：无法识别当前阶段，脚本已挂起。")
            messagebox.showwarning("脚本提示", "脚本检测不到钓鱼相关标志，处理完成后点击确定恢复。")
            self.last_state_time = time.time()

    def settle_result(self):
        """结算收尾逻辑"""
        start_monitor = time.time()
        while self.app.running:
            # 5秒安全超时
            if time.time() - start_monitor > 5.0:
                break

            img = self.vis.get_image()
            if img is None: continue

            # 判定 A: 钓到鱼了
            if self.vis.match_by_key(img, "success_text"):
                self.app.log("已钓到")
                self.ctrl.press(0x1B) # 按 ESC
                time.sleep(1.0)
                break

            # 判定 B: 已回到抛竿状态
            if self.vis.match_by_key(img, "cast_fishing"):
                break

            time.sleep(1.0)