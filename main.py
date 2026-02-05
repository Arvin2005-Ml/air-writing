import cv2
import numpy as np
import mediapipe as mp
import time
import math
from collections import deque

# بررسی کتابخانه کیبورد برای عملکرد بهتر
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    print("Keyboard lib not found. Use 'Space' or 's' key logic instead.")

# ==========================================
# 1. کلاس فیلتر One Euro (بدون تغییر، چون عالی کار می‌کند)
# ==========================================
class LowPassFilter:
    def __init__(self, alpha):
        self.__setAlpha(alpha)
        self.y = None
        self.s = None

    def __setAlpha(self, alpha):
        alpha = float(alpha)
        if alpha <= 0 or alpha > 1.0:
            raise ValueError("alpha should be in (0.0, 1.0]")
        self.alpha = alpha

    def filter(self, value, timestamp=None, alpha=None):
        if alpha: self.__setAlpha(alpha)
        if self.y is None:
            s = value
        else:
            s = self.alpha * value + (1.0 - self.alpha) * self.s
        self.y = value
        self.s = s
        return s

class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.first_time = True
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._dx = 0
        self._x_filt = LowPassFilter(alpha=1)
        self._dx_filt = LowPassFilter(alpha=1)
        self._t_prev = None

    def __call__(self, x, t):
        if self._t_prev is None:
            self._t_prev = t
            self._x_filt.filter(x)
            return x
        t_e = t - self._t_prev
        if t_e <= 0: return self._x_filt.s 
        self._t_prev = t
        alpha_d = self.__alpha(t_e, self._d_cutoff)
        dx = (x - self._x_filt.y) / t_e
        dx_hat = self._dx_filt.filter(dx, alpha=alpha_d)
        cutoff = self._min_cutoff + self._beta * abs(dx_hat)
        alpha = self.__alpha(t_e, cutoff)
        return self._x_filt.filter(x, alpha=alpha)

    def __alpha(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

# ==========================================
# تنظیمات اولیه
# ==========================================
try:
    import ctypes
    user32 = ctypes.windll.user32
    SCREEN_W, SCREEN_H = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
except:
    SCREEN_W, SCREEN_H = 1920, 1080

CAM_W, CAM_H = 640, 480

# تنظیمات لرزش‌گیر
MIN_CUTOFF = 0.01 
BETA = 0.05
oef_x = OneEuroFilter(min_cutoff=MIN_CUTOFF, beta=BETA)
oef_y = OneEuroFilter(min_cutoff=MIN_CUTOFF, beta=BETA)

# مدیاپایپ
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    model_complexity=0, 
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

cap = cv2.VideoCapture(1) # معمولاً 0 وبکم اصلی است
cap.set(3, CAM_W)
cap.set(4, CAM_H)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)

# بوم نقاشی و تاریخچه (برای Undo)
canvas = np.ones((SCREEN_H, SCREEN_W, 3), dtype="uint8") * 255
undo_stack = deque(maxlen=10) # ذخیره 10 حرکت آخر

# متغیرهای ابزار نقاشی
colors = {
    '1': (0, 0, 0),       # سیاه
    '2': (255, 0, 0),     # آبی (OpenCV BGR است)
    '3': (0, 0, 255),     # قرمز
    '4': (0, 255, 0),     # سبز
    '5': (255, 255, 255)  # پاک‌کن (سفید)
}
current_color = (0, 0, 0) # پیش‌فرض سیاه
brush_thickness = 5
ar_mode = False # حالت نوشتن روی وبکم

# وضعیت‌ها
prev_x, prev_y = 0, 0
cal_x_min, cal_y_min = 80, 80
cal_x_max, cal_y_max = CAM_W - 80, CAM_H - 80
is_drawing = False
was_drawing = False # برای تشخیص پایان یک خط جهت ذخیره در Undo

window_name = "AI Whiteboard Pro"
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

print("=== Controls ===")
print("Shift (Hold): Draw")
print("1: Black, 2: Blue, 3: Red, 4: Green, 5: Eraser")
print("+ / - : Increase/Decrease Thickness")
print("u: Undo")
print("c: Clear All")
print("m: Toggle Mode (Whiteboard / AR Webcam)")
print("ESC: Exit")

while True:
    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = hands.process(rgb)
    current_time = time.time()

    # --- رابط کاربری (UI) روی تصویر وبکم ---
    # نمایش رنگ فعلی و ضخامت گوشه تصویر وبکم
    cv2.circle(frame, (30, 30), int(brush_thickness/2) + 5, current_color, -1)
    cv2.circle(frame, (30, 30), int(brush_thickness/2) + 7, (100,100,100), 1)
    cv2.putText(frame, f"Thick: {brush_thickness}", (50, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50,50,50), 2)

    cursor_x, cursor_y = 0, 0
    hand_detected = False

    if res.multi_hand_landmarks:
        hand_detected = True
        raw_x = res.multi_hand_landmarks[0].landmark[8].x * CAM_W
        raw_y = res.multi_hand_landmarks[0].landmark[8].y * CAM_H
        
        # فیلتر کردن و تبدیل مختصات
        smooth_x = oef_x(raw_x, current_time)
        smooth_y = oef_y(raw_y, current_time)
        
        screen_x = np.interp(smooth_x, [cal_x_min, cal_x_max], [0, SCREEN_W])
        screen_y = np.interp(smooth_y, [cal_y_min, cal_y_max], [0, SCREEN_H])
        
        cursor_x, cursor_y = int(screen_x), int(screen_y)

        # بررسی کلید برای رسم
        is_drawing = False
        if HAS_KEYBOARD:
            if keyboard.is_pressed('shift'): is_drawing = True
        
        # --- منطق Undo ---
        # اگر کاربر شروع به کشیدن کرد (فریم اول)، وضعیت قبلی را ذخیره کن
        if is_drawing and not was_drawing:
            undo_stack.append(canvas.copy())
        
        was_drawing = is_drawing

        # --- رسم ---
        if is_drawing:
            if prev_x == 0 and prev_y == 0:
                prev_x, prev_y = cursor_x, cursor_y
            
            cv2.line(canvas, (prev_x, prev_y), (cursor_x, cursor_y), current_color, brush_thickness, cv2.LINE_AA)
            prev_x, prev_y = cursor_x, cursor_y
        else:
            prev_x, prev_y = 0, 0

    # --- ساخت تصویر نهایی ---
    if ar_mode:
        # حالت AR: تصویر وبکم را بزرگ می‌کنیم و نقاشی‌ها را روی آن می‌اندازیم
        frame_resized = cv2.resize(frame, (SCREEN_W, SCREEN_H))
        
        # ماسک کردن برای ترکیب رنگ‌ها (سیاه را شفاف نمی‌کنیم چون رنگ قلم است)
        # روش ساده: جاهایی که کانواس سفید نیست را روی وبکم کپی کن
        gray_canvas = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray_canvas, 250, 255, cv2.THRESH_BINARY_INV)
        
        final_disp = frame_resized.copy()
        # کپی پیکسل‌های نقاشی روی فریم وبکم
        canvas_content = cv2.bitwise_and(canvas, canvas, mask=mask)
        background_masked = cv2.bitwise_and(final_disp, final_disp, mask=cv2.bitwise_not(mask))
        final_disp = cv2.add(canvas_content, background_masked)

    else:
        # حالت تخته سفید کلاسیک + وبکم در گوشه
        final_disp = canvas.copy()
        
        # اضافه کردن وبکم کوچک در گوشه پایین
        h_cam, w_cam = 240, 320
        frame_small = cv2.resize(frame, (w_cam, h_cam))
        # ایجاد کادر دور وبکم
        cv2.rectangle(frame_small, (0,0), (w_cam, h_cam), (50,50,50), 3)
        final_disp[SCREEN_H-h_cam:SCREEN_H, SCREEN_W-w_cam:SCREEN_W] = frame_small

    # --- رسم نشانگر (Pointer) ---
    if hand_detected:
        # رسم یک نشانگر صلیبی (+)
        ptr_size = 15
        # رنگ نشانگر: اگر پاک‌کن باشد طوسی، اگر نه همان رنگ قلم
        ptr_color = (100,100,100) if current_color == (255,255,255) else current_color
        
        # خط افقی و عمودی نشانگر
        cv2.line(final_disp, (cursor_x - ptr_size, cursor_y), (cursor_x + ptr_size, cursor_y), ptr_color, 2)
        cv2.line(final_disp, (cursor_x, cursor_y - ptr_size), (cursor_x, cursor_y + ptr_size), ptr_color, 2)
        
        # دایره توخالی دور نشانگر
        if is_drawing:
             cv2.circle(final_disp, (cursor_x, cursor_y), ptr_size + 5, (0,0,255), 2) # قرمز یعنی در حال نوشتن

    # نمایش اطلاعات ابزار روی صفحه اصلی
    cv2.putText(final_disp, f"Color Mode: {current_color}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150,150,150), 2)
    cv2.putText(final_disp, f"Size: {brush_thickness}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (150,150,150), 2)
    if ar_mode:
        cv2.putText(final_disp, "AR MODE", (SCREEN_W//2 - 50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

    cv2.imshow(window_name, final_disp)
    
    # --- پردازش کلیدها ---
    key = cv2.waitKey(1) & 0xFF
    
    if key == 27: break # ESC
    elif key == ord('c'): # Clear
        undo_stack.append(canvas.copy()) # قبل پاک کردن ذخیره کن
        canvas = np.ones((SCREEN_H, SCREEN_W, 3), dtype="uint8") * 255
    
    elif key == ord('u'): # Undo
        if len(undo_stack) > 0:
            print("Undoing...")
            canvas = undo_stack.pop()
        else:
            print("Nothing to undo.")

    elif key == ord('1'): current_color = colors['1'] # Black
    elif key == ord('2'): current_color = colors['2'] # Blue
    elif key == ord('3'): current_color = colors['3'] # Red
    elif key == ord('4'): current_color = colors['4'] # Green
    elif key == ord('5'): current_color = colors['5'] # Eraser
    
    elif key == ord('=') or key == ord('+'): # Increase size
        brush_thickness = min(brush_thickness + 2, 50)
    elif key == ord('-'): # Decrease size
        brush_thickness = max(brush_thickness - 2, 2)
        
    elif key == ord('m'): # Toggle Mode
        ar_mode = not ar_mode

cap.release()
cv2.destroyAllWindows()