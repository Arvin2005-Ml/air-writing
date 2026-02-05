import cv2
import numpy as np
import mediapipe as mp
import time
import math

# بررسی کتابخانه کیبورد
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    print("Keyboard lib not found. Use 's' key to toggle.")

# ==========================================
# 1. کلاس فیلتر "یک یورو" (One Euro Filter)
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
        # min_cutoff: هرچه کمتر باشد، در سرعت‌های پایین لرزش کمتر است (اما کمی تاخیر دارد)
        # beta: هرچه بیشتر باشد، در سرعت‌های بالا تاخیر کمتر می‌شود
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
        
        # جلوگیری از تقسیم بر صفر
        if t_e <= 0: return self._x_filt.s 

        self._t_prev = t
        
        # محاسبه نرخ برش (Cutoff Frequency) بر اساس سرعت
        # فیلتر کردن مشتق (سرعت)
        alpha_d = self.__alpha(t_e, self._d_cutoff)
        dx = (x - self._x_filt.y) / t_e
        dx_hat = self._dx_filt.filter(dx, alpha=alpha_d)

        # محاسبه ضریب آلفای اصلی
        cutoff = self._min_cutoff + self._beta * abs(dx_hat)
        alpha = self.__alpha(t_e, cutoff)
        
        return self._x_filt.filter(x, alpha=alpha)

    def __alpha(self, t_e, cutoff):
        r = 2 * math.pi * cutoff * t_e
        return r / (r + 1)

# ==========================================
# تنظیمات صفحه و دوربین
# ==========================================
try:
    import ctypes
    user32 = ctypes.windll.user32
    SCREEN_W, SCREEN_H = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
except:
    SCREEN_W, SCREEN_H = 1920, 1080

CAM_W, CAM_H = 640, 480

# ==========================================
# تنظیمات اصلی حساسیت (اینجا را دستکاری کنید)
# ==========================================
# MIN_CUTOFF: (پیش‌فرض 0.05) 
# اگر دستتان خیلی می‌لرزد، این را کمتر کنید (مثلاً 0.01)
# اگر احساس کندی می‌کنید، این را بیشتر کنید (مثلاً 0.1)
MIN_CUTOFF = 0.01 

# BETA: (پیش‌فرض 0.05)
# اگر وقتی سریع می‌نویسید خط جا می‌ماند، این را زیاد کنید (مثلاً 0.5)
# اگر وقتی سریع می‌نویسید خط پرش دارد، این را کم کنید.
BETA = 0.03

# ایجاد فیلترها برای X و Y جداگانه
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

cap = cv2.VideoCapture(1)
cap.set(3, CAM_W)
cap.set(4, CAM_H)
cap.set(cv2.CAP_PROP_AUTOFOCUS, 0) # خاموش کردن فوکوس خودکار خیلی مهم است

canvas = np.ones((SCREEN_H, SCREEN_W, 3), dtype="uint8") * 255
window_name = "OneEuro Board"
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

# متغیرهای وضعیت
prev_x, prev_y = 0, 0
cal_x_min, cal_y_min = 80, 80
cal_x_max, cal_y_max = CAM_W - 80, CAM_H - 80
calibration_mode = False
calibration_step = 0
is_drawing_toggle = False

print("System Started with One Euro Filter.")

while True:
    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = hands.process(rgb)
    
    current_time = time.time()

    if res.multi_hand_landmarks:
        # نوک انگشت اشاره
        raw_x = res.multi_hand_landmarks[0].landmark[8].x * CAM_W
        raw_y = res.multi_hand_landmarks[0].landmark[8].y * CAM_H
        
        if calibration_mode:
             cv2.circle(frame, (int(raw_x), int(raw_y)), 8, (0, 255, 255), -1)
             cv2.putText(frame, "Calibrating...", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)
        else:
            # 1. اعمال فیلتر One Euro (جادوی اصلی)
            # این فیلتر مقدار خام را می‌گیرد و مقدار تمیز شده را پس می‌دهد
            smooth_x = oef_x(raw_x, current_time)
            smooth_y = oef_y(raw_y, current_time)
            
            # 2. نگاشت به صفحه (Mapping)
            screen_x = np.interp(smooth_x, [cal_x_min, cal_x_max], [0, SCREEN_W])
            screen_y = np.interp(smooth_y, [cal_y_min, cal_y_max], [0, SCREEN_H])
            
            curr_x, curr_y = int(screen_x), int(screen_y)

            # 3. لاجیک رسم
            should_draw = False
            if HAS_KEYBOARD:
                if keyboard.is_pressed('shift'): should_draw = True
            else:
                should_draw = is_drawing_toggle

            if should_draw:
                cv2.circle(frame, (int(smooth_x), int(smooth_y)), 5, (0, 0, 255), -1)
                
                if prev_x == 0 and prev_y == 0:
                    prev_x, prev_y = curr_x, curr_y
                
                # رسم خط ضخیم‌تر برای خوانایی بهتر
                cv2.line(canvas, (prev_x, prev_y), (curr_x, curr_y), (0, 0, 0), 6, cv2.LINE_AA)
                prev_x, prev_y = curr_x, curr_y
            else:
                cv2.circle(frame, (int(smooth_x), int(smooth_y)), 5, (0, 255, 0), 2)
                prev_x, prev_y = 0, 0

    # نمایش تصویر
    h, w = 240, 320
    frame_small = cv2.resize(frame, (w, h))
    final_disp = canvas.copy()
    final_disp[SCREEN_H-h:SCREEN_H, SCREEN_W-w:SCREEN_W] = frame_small
    cv2.rectangle(final_disp, (SCREEN_W-w, SCREEN_H-h), (SCREEN_W, SCREEN_H), (100,100,100), 3)

    cv2.imshow(window_name, final_disp)
    
    key = cv2.waitKey(1) & 0xFF
    if key == 27: break
    elif key == ord('x'): canvas = np.ones((SCREEN_H, SCREEN_W, 3), dtype="uint8") * 255
    elif key == ord('s'): is_drawing_toggle = not is_drawing_toggle
    elif key == ord('c'):
        calibration_mode = True
        calibration_step = 1
        print("Calibration: Click Space at Top-Left")
    
    if calibration_mode and key == 32:
        if calibration_step == 1:
            cal_x_min, cal_y_min = raw_x, raw_y
            calibration_step = 2
            print("Calibration: Click Space at Bottom-Right")
            time.sleep(0.2)
        elif calibration_step == 2:
            cal_x_max, cal_y_max = raw_x, raw_y
            calibration_mode = False
            calibration_step = 0
            print("Done.")

cap.release()
cv2.destroyAllWindows()