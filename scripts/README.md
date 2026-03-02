# 🛠️ Scripts (Developer Utility Folder)

## Use Case
Contains all the "Extra" tools that aren't needed for the daily bot run but are vital for setup, debugging, and diagnostics.

## What's inside?
1.  **`check_hw.py`**: Hardware diagnostic—run this first to see if your GPU is ready for AI.
2.  **`debug_overlay_layout.py`**: Visualizes the video layout so you can tweak branding positions.
3.  **`auth_youtube.py`**: The one-time setup script to link your YouTube channel to the engine.
4.  **`nightly_retrain.py`**: A developer utility for the watermark detection system.

## Step-by-Step Usage

1.  **Diagnostic**:
    `python scripts/check_hw.py`
2.  **Authentication**:
    `python scripts/auth_youtube.py`
3.  **Layout Tweak**:
    `python scripts/debug_overlay_layout.py`
