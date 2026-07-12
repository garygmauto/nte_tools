# gamepad_backend.py
import time
import threading
import win32gui
import win32con
import vgamepad as vg

class GamepadBackend:
    def __init__(self):
        self.gamepad = None
        self._js_stop = threading.Event()  # 用于中途打断持续摇杆推进
        self.init_gamepad()

    def init_gamepad(self):
        try:
            self.gamepad = vg.VDS4Gamepad()
        except Exception:
            self.gamepad = None

    def _activate_window(self, hwnd):
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_ACTIVATE, 1, 0)

    def send_button(self, hwnd, button_enum, is_special=False, duration=0.1):
        """同步发送一次按键"""
        if not self.gamepad: return False
        try:
            self._activate_window(hwnd)
            if is_special:
                self.gamepad.press_special_button(special_button=button_enum)
            else:
                self.gamepad.press_button(button=button_enum)
            self.gamepad.update()
            
            time.sleep(duration)
            
            self._activate_window(hwnd)
            if is_special:
                self.gamepad.release_special_button(special_button=button_enum)
            else:
                self.gamepad.release_button(button=button_enum)
            self.gamepad.update()
            return True
        except Exception:
            return False

    def send_dpad(self, hwnd, direction_enum, duration=0.15):
        if not self.gamepad: return False
        try:
            self._activate_window(hwnd)
            self.gamepad.directional_pad(direction=direction_enum)
            self.gamepad.update()
            time.sleep(duration)
            self._activate_window(hwnd)
            self.gamepad.directional_pad(direction=vg.DS4_DPAD_DIRECTIONS.DS4_BUTTON_DPAD_NONE)
            self.gamepad.update()
            return True
        except Exception:
            return False

    def send_trigger(self, hwnd, side, value, duration=0.15):
        if not self.gamepad: return False
        try:
            self._activate_window(hwnd)
            if side == "L":
                self.gamepad.left_trigger(value=value)
                if value > 0: self.gamepad.press_button(button=vg.DS4_BUTTONS.DS4_BUTTON_TRIGGER_LEFT)
            else:
                self.gamepad.right_trigger(value=value)
                if value > 0: self.gamepad.press_button(button=vg.DS4_BUTTONS.DS4_BUTTON_TRIGGER_RIGHT)
            self.gamepad.update()

            time.sleep(duration)

            self._activate_window(hwnd)
            if side == "L":
                self.gamepad.left_trigger(value=0)
                self.gamepad.release_button(button=vg.DS4_BUTTONS.DS4_BUTTON_TRIGGER_LEFT)
            else:
                self.gamepad.right_trigger(value=0)
                self.gamepad.release_button(button=vg.DS4_BUTTONS.DS4_BUTTON_TRIGGER_RIGHT)
            self.gamepad.update()
            return True
        except Exception:
            return False

    def _joystick_thread_proc(self, hwnd, side, x_val, y_val, duration):
        try:
            start_time = time.time()
            while time.time() - start_time < duration and not self._js_stop.is_set():
                self._activate_window(hwnd)
                if side == "L":
                    self.gamepad.left_joystick_float(x_value_float=x_val, y_value_float=y_val)
                else:
                    self.gamepad.right_joystick_float(x_value_float=x_val, y_value_float=y_val)
                self.gamepad.update()
                time.sleep(0.015)

            # 归零
            self._activate_window(hwnd)
            if side == "L":
                self.gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
            else:
                self.gamepad.right_joystick_float(x_value_float=0.0, y_value_float=0.0)
            self.gamepad.update()
        except Exception:
            pass

    def send_joystick_persistent(self, hwnd, side, x_val, y_val, duration=0.5, block=True):
        """发送摇杆信号，支持阻塞或非阻塞模式"""
        if not self.gamepad: return False
        self._js_stop.clear()  # 新的推进开始前清除上一次的停止标记
        if block:
            self._joystick_thread_proc(hwnd, side, x_val, y_val, duration)
        else:
            t = threading.Thread(target=self._joystick_thread_proc, args=(hwnd, side, x_val, y_val, duration))
            t.daemon = True
            t.start()
        return True

    def stop_joystick(self, hwnd, side="L"):
        """立即打断正在进行的持续摇杆推进，并把摇杆归零。"""
        if not self.gamepad: return False
        self._js_stop.set()  # 通知后台推进线程尽快退出
        try:
            self._activate_window(hwnd)
            if side == "L":
                self.gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
            else:
                self.gamepad.right_joystick_float(x_value_float=0.0, y_value_float=0.0)
            self.gamepad.update()
            return True
        except Exception:
            return False

    def close(self):
        if self.gamepad:
            try: self.gamepad.disassociate()
            except Exception: pass