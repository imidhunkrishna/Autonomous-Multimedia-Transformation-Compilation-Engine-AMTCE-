# 🏎️ Upscale Modules (The Visual Polisher)

## Use Case
Enhances the raw resolution of downloaded videos to ensure they look "Premium" and professional on 4K displays.

## What it is good at
1.  **AI Upscaling**: Uses models like Real-ESRGAN to turn 480p/720p content into crisp 1080p+ media.
2.  **Hardware Awareness**: Consults `compute_caps.py` to only attempt upscaling if a compatible GPU (NVIDIA) is present to avoid massive CPU lag.

## Step-by-Step Usage

1.  **Check Capability**:
    ```python
    from compute_caps import can_upscale
    if can_upscale():
        print("GPU Power Detected!")
    ```
2.  **Installation**:
    Requires a working PyTorch installation with CUDA support.
