import cv2
import numpy as np
from collections import deque
from src.config import SCREEN_W, SCREEN_H, COLORS

class Whiteboard:
    def __init__(self):
        # بوم سفید
        self.canvas = np.ones((SCREEN_H, SCREEN_W, 3), dtype="uint8") * 255
        self.undo_stack = deque(maxlen=10)
        
        self.current_color = COLORS['1'] # پیش‌فرض سیاه
        self.brush_thickness = 5
        self.prev_x, self.prev_y = 0, 0
        self.was_drawing = False

    def start_stroke(self):
        """ذخیره وضعیت فعلی قبل از شروع خط جدید برای Undo"""
        if not self.was_drawing:
            self.undo_stack.append(self.canvas.copy())
            self.was_drawing = True

    def end_stroke(self):
        self.was_drawing = False
        self.prev_x, self.prev_y = 0, 0

    def draw(self, x, y):
        if self.prev_x == 0 and self.prev_y == 0:
            self.prev_x, self.prev_y = x, y
            
        cv2.line(self.canvas, (self.prev_x, self.prev_y), (x, y), 
                 self.current_color, self.brush_thickness, cv2.LINE_AA)
        self.prev_x, self.prev_y = x, y

    def clear(self):
        self.undo_stack.append(self.canvas.copy())
        self.canvas = np.ones((SCREEN_H, SCREEN_W, 3), dtype="uint8") * 255

    def undo(self):
        if len(self.undo_stack) > 0:
            self.canvas = self.undo_stack.pop()
            print("Undo performed.")
        else:
            print("Nothing to undo.")

    def change_color(self, color_key):
        if color_key in COLORS:
            self.current_color = COLORS[color_key]

    def change_size(self, amount):
        new_size = self.brush_thickness + amount
        # محدود کردن سایز بین 2 تا 50
        self.brush_thickness = max(2, min(new_size, 50))