import cv2
import numpy as np
import mediapipe as mp
import fitz  # PyMuPDF
import keyboard
import os

# ==========================================
# تنظیمات کاربر (اینجا را تغییر دهید)
# ==========================================
PDF_PATH = "sample.pdf"  # نام فایل پی‌دی‌اف خود را اینجا بنویسید
SCREEN_W, SCREEN_H = 1280, 720  # رزولوشن خروجی
SMOOTHING = 4  # مقدار نرم‌کنندگی خط (هرچه بیشتر، خط صاف‌تر اما با تاخیر)
BRUSH_THICKNESS = 3

# رنگ‌ها (B, G, R)
COLOR_RED = (0, 0, 255)
COLOR_BLUE = (255, 0, 0)
COLOR_BLACK = (0, 0, 0)
COLOR_ERASER = (0, 0, 0) # برای پاک کردن (البته روی پی‌دی‌اف منطق فرق دارد)

# ==========================================
# توابع کمکی PDF
# ==========================================
def get_pdf_page_image(doc, page_num, width, height):
    """
    یک صفحه از PDF را می‌گیرد و به تصویر OpenCV تبدیل می‌کند
    """
    try:
        page = doc.load_page(page_num)
        pix = page.get_pixmap()
        # تبدیل به فرمت numpy
        img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        
        # اگر تصویر کانال آلفا (شفافیت) دارد، حذف کن
        if pix.n >= 4:
            img_data = cv2.cvtColor(img_data, cv2.COLOR_RGBA2RGB)
        else:
            img_data = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
            
        # تغییر سایز به اندازه صفحه نمایش
        img_resized = cv2.resize(img_data, (width, height))
        return img_resized
    except Exception as e:
        print(f"Error reading page {page_num}: {e}")
        return np.ones((height, width, 3), dtype=np.uint8) * 255

# ==========================================
# راه‌اندازی MediaPipe
# ==========================================
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)
mp_draw = mp.solutions.drawing_utils

# ==========================================
# متغیرهای سراسری
# ==========================================
cap = cv2.VideoCapture(1)
cap.set(3, 640) # عرض دوربین
cap.set(4, 480) # ارتفاع دوربین

# ناحیه فعال برای حرکت دست (کالیبراسیون ساده)
frame_r = 100 

# متغیرهای مربوط به PDF
doc = None
try:
    doc = fitz.open(PDF_PATH)
    total_pages = len(doc)
    print(f"PDF Loaded: {total_pages} pages.")
except:
    print("PDF File Not Found! Creating a blank whiteboard.")
    total_pages = 0

current_page_num = 0
# بوم نقاشی (لایه‌ای که روی PDF کشیده می‌شود)
# ما یک لایه شفاف برای نقاشی می‌سازیم تا PDF اصلی خراب نشود
drawing_layer = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)

# رنگ فعلی قلم
draw_color = COLOR_BLUE

# متغیرهای نرم‌کننده حرکت
prev_x, prev_y = 0, 0
curr_x, curr_y = 0, 0

print("Controls:")
print("- TAB (Hold): Draw")
print("- N: Next Page")
print("- P: Previous Page")
print("- C: Clear Drawing")
print("- R: Red Color | B: Blue Color | E: Eraser")
print("- S: Save Page")
print("- ESC: Exit")

while True:
    success, img = cap.read()
    if not success: break
    
    img = cv2.flip(img, 1) # آینه‌ای کردن تصویر
    h_cam, w_cam, _ = img.shape
    
    # 1. آماده‌سازی پس‌زمینه (صفحه PDF)
    if doc and total_pages > 0:
        # همیشه صفحه تمیز PDF را می‌گیریم
        background = get_pdf_page_image(doc, current_page_num, SCREEN_W, SCREEN_H)
    else:
        background = np.ones((SCREEN_H, SCREEN_W, 3), dtype=np.uint8) * 255
    
    # 2. پردازش دست
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    
    cv2.rectangle(img, (frame_r, frame_r), (w_cam - frame_r, h_cam - frame_r), (255, 0, 255), 2)
    
    if results.multi_hand_landmarks:
        for hand_lms in results.multi_hand_landmarks:
            lm_list = []
            for id, lm in enumerate(hand_lms.landmark):
                px, py = int(lm.x * w_cam), int(lm.y * h_cam)
                lm_list.append([id, px, py])
            
            if len(lm_list) != 0:
                # نوک انگشت اشاره (8) و انگشت کوچک (20)
                x1, y1 = lm_list[8][1], lm_list[8][2] # اشاره
                x2, y2 = lm_list[20][1], lm_list[20][2] # کوچک (برای هاور)
                
                # تبدیل مختصات (Map) از کادر کوچک دوربین به کل صفحه PDF
                x3 = np.interp(x1, (frame_r, w_cam - frame_r), (0, SCREEN_W))
                y3 = np.interp(y1, (frame_r, h_cam - frame_r), (0, SCREEN_H))
                
                # نرم‌کردن حرکت (Smoothing)
                curr_x = prev_x + (x3 - prev_x) / SMOOTHING
                curr_y = prev_y + (y3 - prev_y) / SMOOTHING
                
                # منطق رسم: اگر کلید TAB نگه داشته شده باشد
                if keyboard.is_pressed('tab'):
                    if prev_x == 0 and prev_y == 0:
                        prev_x, prev_y = curr_x, curr_y
                    
                    if draw_color == COLOR_ERASER:
                        # پاک‌کن: کشیدن خط سیاه روی لایه ماسک (که بعدا حذف میشه)
                        # اما اینجا پاک‌کن یعنی حذف از لایه Drawing
                        # ساده‌ترین راه برای پاک‌کن در این روش: کشیدن دایره‌های سیاه روی ماسک
                         cv2.circle(drawing_layer, (int(curr_x), int(curr_y)), 20, (0,0,0), -1)
                         # نکته: این روش ساده پاک‌کن است. برای پاک‌کن واقعی باید مقادیر پیکسل را 0 کرد
                         # راه بهتر:
                         temp_mask = np.zeros_like(drawing_layer)
                         cv2.circle(temp_mask, (int(curr_x), int(curr_y)), 20, (255,255,255), -1)
                         # هر جا که سفید است را در لایه اصلی سیاه کن
                         drawing_layer = cv2.bitwise_and(drawing_layer, cv2.bitwise_not(temp_mask))

                    else:
                        cv2.line(drawing_layer, (int(prev_x), int(prev_y)), (int(curr_x), int(curr_y)), draw_color, BRUSH_THICKNESS)
                    
                    cv2.circle(background, (int(curr_x), int(curr_y)), 10, draw_color, -1) # نشانگر موس
                    
                else:
                    # حالت Hover (فقط نشانگر)
                    cv2.circle(background, (int(curr_x), int(curr_y)), 10, (0, 255, 0), -1)
                    prev_x, prev_y = curr_x, curr_y # ریست کردن برای خط نکشیدن
                
                prev_x, prev_y = curr_x, curr_y

    # 3. ترکیب لایه‌ها
    # لایه نقاشی را روی پی‌دی‌اف بینداز
    # جاهایی از drawing_layer که سیاه نیستند (یعنی رنگی شده‌اند) را روی بک‌گراند کپی کن
    img_gray = cv2.cvtColor(drawing_layer, cv2.COLOR_BGR2GRAY)
    _, img_inv = cv2.threshold(img_gray, 10, 255, cv2.THRESH_BINARY)
    img_inv = cv2.cvtColor(img_inv, cv2.COLOR_GRAY2BGR)
    
    # ماسک کردن نواحی رنگی از بک‌گراند اصلی
    background = cv2.bitwise_and(background, cv2.bitwise_not(img_inv))
    # اضافه کردن رنگ‌ها
    background = cv2.add(background, drawing_layer)

    # 4. تصویر در تصویر (Webcam کوچک گوشه تصویر)
    img_small = cv2.resize(img, (213, 160))
    h_s, w_s, _ = img_small.shape
    background[SCREEN_H - h_s - 10 : SCREEN_H - 10, SCREEN_W - w_s - 10 : SCREEN_W - 10] = img_small

    # 5. کنترل‌های کیبورد
    # تغییر رنگ
    if keyboard.is_pressed('r'): draw_color = COLOR_RED
    if keyboard.is_pressed('b'): draw_color = COLOR_BLUE
    if keyboard.is_pressed('e'): draw_color = COLOR_ERASER
    
    # پاک کردن صفحه (فقط نوشته‌ها را پاک می‌کند، نه PDF را)
    if keyboard.is_pressed('c'):
        drawing_layer[:] = 0 
    
    # ورق زدن
    if keyboard.is_pressed('n') and doc:
        if current_page_num < total_pages - 1:
            current_page_num += 1
            drawing_layer[:] = 0 # صفحه جدید باید تمیز باشد
            cv2.waitKey(200) # تاخیر کوچک برای جلوگیری از پرش سریع
            
    if keyboard.is_pressed('p') and doc:
        if current_page_num > 0:
            current_page_num -= 1
            drawing_layer[:] = 0
            cv2.waitKey(200)

    # ذخیره تصویر
    if keyboard.is_pressed('s'):
        filename = f"Slide_{current_page_num}_Annotated.png"
        cv2.imwrite(filename, background)
        print(f"Saved: {filename}")
        cv2.waitKey(300)

    cv2.imshow("Smart Presentation Board", background)
    
    if cv2.waitKey(1) & 0xFF == 27: # ESC
        break

cap.release()
cv2.destroyAllWindows()
