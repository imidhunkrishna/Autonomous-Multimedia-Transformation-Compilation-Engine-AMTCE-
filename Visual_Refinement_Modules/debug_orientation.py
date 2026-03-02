
import cv2
import os

video_path = r"C:\Users\midhunkrishnapv\AppData\Local\Temp\gradio\3e59423e83ff2e96740d46f63aedee12ea573a6641ff22342404adc2a391043a\Priyanka_Chahar_Chaudhary_1.mp4"
if not os.path.exists(video_path):
    print("Video not found at that path.")
else:
    cap = cv2.VideoCapture(video_path)
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    print(f"Dimensions: {w}x{h}")
    ret, frame = cap.read()
    if ret:
        print(f"Actual Frame shape: {frame.shape}")
    cap.release()
