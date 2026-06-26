import win32gui
import win32con
import time

class GameControls:
    def __init__(self, hwnd):
        self.hwnd = hwnd

    def fake_activate(self):
        """后台发送伪激活消息"""
        if self.hwnd:
            win32gui.SendMessage(self.hwnd, win32con.WM_ACTIVATE, 1, 0)
            win32gui.SendMessage(self.hwnd, win32con.WM_SETFOCUS, 0, 0)

    def press(self, vk, duration=0.1):
        self.fake_activate()
        win32gui.PostMessage(self.hwnd, win32con.WM_KEYDOWN, vk, 0)
        time.sleep(duration)
        win32gui.PostMessage(self.hwnd, win32con.WM_KEYUP, vk, 0)

    def set_key_state(self, vk, is_down):
        """用于AD长按"""
        msg = win32con.WM_KEYDOWN if is_down else win32con.WM_KEYUP
        win32gui.PostMessage(self.hwnd, msg, vk, 0)