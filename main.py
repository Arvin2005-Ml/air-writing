import cv2
import numpy as np
from src.config import *
from src.tracking import HandTracker
from src.board import Whiteboard

# بررسی کتابخانه کیبورد
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    print("Library 'keyboard' not found.")

def main():
    # --- راه اندازی ---
    cap = cv2.VideoCapture(1) # تغییر دهید به 0 اگر وبکم خارجی ندارید
    cap.set(3, CAM_W)
    cap.set(4, CAM_H)
    cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)

    tracker = HandTracker()
    board = Whiteboard()
    
    ar_mode = False 
    window_name = "AI Whiteboard Pro"
    
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    print("Started. Press ESC to exit.")

    while True:
        ret, frame = cap.read()
        if not ret: break

        frame = cv2.flip(frame, 1)
        res = tracker.process(frame)
        
        # --- UI وبکم کوچک ---
        # نمایش تنظیمات روی تصویر خام وبکم
        cv2.circle(frame, (30, 30), int(board.brush_thickness/2) + 5, board.current_color, -1)
        cv2.putText(frame, f"Size: {board.brush_thickness}", (50, 35), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (50,50,50), 2)

        cursor_x, cursor_y = 0, 0
        hand_detected = False
        is_drawing_key = False

        # بررسی کلید Shift
        if HAS_KEYBOARD and keyboard.is_pressed('shift'):
            is_drawing_key = True

        # --- پردازش دست ---
        if res.multi_hand_landmarks:
            hand_detected = True
            cursor_x, cursor_y = tracker.get_smooth_coords(res.multi_hand_landmarks)

            if is_drawing_key:
                board.start_stroke() # ذخیره برای Undo در صورت شروع خط جدید
                board.draw(cursor_x, cursor_y)
            else:
                board.end_stroke()
        else:
            board.end_stroke()

        # --- ترکیب تصاویر (Compositing) ---
        final_disp = None

        if ar_mode:
            # حالت AR: ترکیب هوشمند بوم و وبکم
            frame_resized = cv2.resize(frame, (SCREEN_W, SCREEN_H))
            
            gray_canvas = cv2.cvtColor(board.canvas, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray_canvas, 250, 255, cv2.THRESH_BINARY_INV)
            
            final_disp = frame_resized.copy()
            canvas_content = cv2.bitwise_and(board.canvas, board.canvas, mask=mask)
            background_masked = cv2.bitwise_and(final_disp, final_disp, mask=cv2.bitwise_not(mask))
            final_disp = cv2.add(canvas_content, background_masked)
        else:
            # حالت کلاسیک: تخته سفید + وبکم کوچک
            final_disp = board.canvas.copy()
            
            h_cam, w_cam = 240, 320
            frame_small = cv2.resize(frame, (w_cam, h_cam))
            cv2.rectangle(frame_small, (0,0), (w_cam, h_cam), (50,50,50), 3)
            # قرار دادن وبکم در گوشه پایین سمت راست
            final_disp[SCREEN_H-h_cam:SCREEN_H, SCREEN_W-w_cam:SCREEN_W] = frame_small

        # --- رسم نشانگر موس (Cursor) ---
        if hand_detected:
            ptr_size = 15
            ptr_color = (100,100,100) if board.current_color == (255,255,255) else board.current_color
            
            cv2.line(final_disp, (cursor_x - ptr_size, cursor_y), (cursor_x + ptr_size, cursor_y), ptr_color, 2)
            cv2.line(final_disp, (cursor_x, cursor_y - ptr_size), (cursor_x, cursor_y + ptr_size), ptr_color, 2)
            
            if is_drawing_key:
                 cv2.circle(final_disp, (cursor_x, cursor_y), ptr_size + 5, (0,0,255), 2)

        if ar_mode:
            cv2.putText(final_disp, "AR MODE", (SCREEN_W//2 - 50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

        cv2.imshow(window_name, final_disp)

        # --- مدیریت کلیدهای کیبورد (CV2) ---
        key = cv2.waitKey(1) & 0xFF
        if key == 27: break # ESC
        elif key == ord('c'): board.clear()
        elif key == ord('u'): board.undo()
        elif key in [ord('1'), ord('2'), ord('3'), ord('4'), ord('5')]:
            board.change_color(chr(key))
        elif key == ord('=') or key == ord('+'):
            board.change_size(2)
        elif key == ord('-'):
            board.change_size(-2)
        elif key == ord('m'):
            ar_mode = not ar_mode

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()