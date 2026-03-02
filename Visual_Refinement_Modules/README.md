# 👁️ Watermark Modules (The Invisibility Cloak)

## Use Case
This module is designed to identify and mathematically erase watermarks (logos, floating handles) from video content using AI and Computer Vision.

## What it is good at
1.  **Hybrid Vision Detection**: Combines Gemini Vision (to "understand" what a logo looks like) with OpenCV (to track it precisely across movement).
2.  **Trajectory Tracking**: If a watermark moves (common in TikToks), the module calculates its path so the "erasure" follows it perfectly.
3.  **Face Safety**: It has a "FaceProtector" built-in that ensures the watermark mask NEVER accidentally covers a human face.

## Step-by-Step Usage

1.  **Installation**:
    ```bash
    pip install opencv-python numpy google-generativeai
    ```
2.  **Standalone Execution**:
    ```python
    from hybrid_watermark import hybrid_detector
    
    # Process a video for watermark removal
    output_status = hybrid_detector.process_video("input_video.mp4")
    print(f"Outcome: {output_status}")
    ```
3.  **Local Testing**:
    You can run `python hybrid_watermark.py` directly (if you have an input.mp4 in the folder) to test the detector locally.
