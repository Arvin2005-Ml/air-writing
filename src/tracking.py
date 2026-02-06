import mediapipe as mp
import numpy as np
import time
from src.config import *
from src.filters import OneEuroFilter

class HandTracker:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0, 
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        # ایجاد نمونه‌های فیلتر برای X و Y
        self.oef_x = OneEuroFilter(min_cutoff=MIN_CUTOFF, beta=BETA)
        self.oef_y = OneEuroFilter(min_cutoff=MIN_CUTOFF, beta=BETA)

    def process(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self.hands.process(rgb)

    def get_smooth_coords(self, landmarks):
        """مختصات نوک انگشت اشاره را گرفته و نسخه بدون لرزش و اسکیل شده را برمی‌گرداند"""
        current_time = time.time()
        
        # مختصات خام (نسبت به سایز وبکم)
        raw_x = landmarks[0].landmark[8].x * CAM_W
        raw_y = landmarks[0].landmark[8].y * CAM_H
        
        # اعمال فیلتر
        smooth_x = self.oef_x(raw_x, current_time)
        smooth_y = self.oef_y(raw_y, current_time)
        
        # تبدیل مختصات به سایز صفحه نمایش
        screen_x = np.interp(smooth_x, [CAL_X_MIN, CAL_X_MAX], [0, SCREEN_W])
        screen_y = np.interp(smooth_y, [CAL_Y_MIN, CAL_Y_MAX], [0, SCREEN_H])
        
        return int(screen_x), int(screen_y)