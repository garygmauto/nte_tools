import win32gui, win32ui, ctypes
import cv2
import numpy as np
import time
from config_data import FISH_CONFIG # 引入硬编码配置

class GameVision:
    def __init__(self, hwnd, config=None):
        # 确保 DPI 意识
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            ctypes.windll.user32.SetProcessDPIAware()
            
        self.hwnd = hwnd
        self.config = FISH_CONFIG # 直接使用导入的硬编码配置
        self.res = self.config["game_res"] # 使用配置中的分辨率
        
        self.thresholds = {
            'cyan_bar': {
                'lower': np.array([78, 120, 130]),
                'upper': np.array([98, 255, 255]),
                'min_pixels': 20
            },
            'yellow_p': {
                'lower': np.array([20, 80, 80]), 
                'upper': np.array([40, 255, 255]), 
                'min_pixels': 1 
            }
        }

    def get_image(self):
        w, h = self.res
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
        img_cv = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
        
        win32gui.DeleteObject(bmp.GetHandle())
        s_dc.DeleteDC(); m_dc.DeleteDC(); win32gui.ReleaseDC(self.hwnd, hdc)
        return img_cv

    def find_x_center(self, img, mode):
        cfg = self.config["reeling_area"]
        y_min, y_max = cfg["y_range"]
        
        if mode == 'bar':
            x_start, x_end = cfg["bar_x_range"]
            thresh = self.thresholds['cyan_bar']
        else:
            x_start, x_end = cfg["slider_x_range"]
            thresh = self.thresholds['yellow_p']

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        roi = hsv[y_min:y_max, x_start:x_end]
        mask = cv2.inRange(roi, thresh['lower'], thresh['upper'])
        points = np.where(mask > 0)
        pixel_count = len(points[1])

        if pixel_count < thresh['min_pixels']:
            return None

        return int(np.mean(points[1])) + x_start

    def match_by_key(self, img, key):
        data = self.config["check_points"][key]
        target_rgb = data["color"]
        tol = data["tol"]
        
        img_h, img_w = img.shape[:2]
        
        for x, y in data["coords"]:
            ix, iy = int(x), int(y)
            if iy >= img_h or ix >= img_w:
                continue
                
            b, g, r = img[iy, ix]
            if (abs(int(r)-target_rgb[0]) <= tol and 
                abs(int(g)-target_rgb[1]) <= tol and 
                abs(int(b)-target_rgb[2]) <= tol):
                return True
        return False