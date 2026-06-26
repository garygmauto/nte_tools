import win32gui

class WindowManager:
    def __init__(self):
        # --- 修改：不再需要 config_path，因为不存 JSON 了 ---
        pass

    def list_windows(self):
        windows = {}
        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                windows[f"{win32gui.GetWindowText(hwnd)} | {hwnd}"] = hwnd
            return True
        win32gui.EnumWindows(cb, 0)
        return windows

    # --- 修改：彻底删除 save_config 函数，因为坐标数据已固定在 config_data.py 中 ---