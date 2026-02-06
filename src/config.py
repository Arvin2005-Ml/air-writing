import cv2
import ctypes

# --- تنظیمات صفحه نمایش و دوربین ---
try:
    user32 = ctypes.windll.user32
    SCREEN_W, SCREEN_H = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
except:
    SCREEN_W, SCREEN_H = 1920, 1080

CAM_W, CAM_H = 640, 480

# --- تنظیمات فیلتر لرزش‌گیر ---
MIN_CUTOFF = 0.01 
BETA = 0.05

# --- تنظیمات کالیبراسیون (محدوده حرکت دست) ---
CAL_X_MIN, CAL_Y_MIN = 80, 80
CAL_X_MAX, CAL_Y_MAX = CAM_W - 80, CAM_H - 80

# --- رنگ‌ها ---
COLORS = {
    '1': (0, 0, 0),       # سیاه
    '2': (255, 0, 0),     # آبی
    '3': (0, 0, 255),     # قرمز
    '4': (0, 255, 0),     # سبز
    '5': (255, 255, 255)  # پاک‌کن
}